"""
chat/router.py
--------------
PURPOSE:
    Defines the HTTP endpoints for department-specific chat and session management.
    This is what the mobile app calls to send a user message and receive an AI response.

CONCEPT — StreamingResponse
    FastAPI's StreamingResponse sends the HTTP response body as an iterator.
    Instead of:
        client waits 15s → receives full response at once
    We get:
        client receives first token in ~0.5s → tokens flow in as LLM generates them

    We use Server-Sent Events (SSE) format, which the React Native app can consume
    with EventSource or a simple streaming fetch. Each event is one line:
        data: token text here\n\n

CONCEPT — Session Creation
    A session is a persistent conversation thread. The flow is:
      First message  → no session_id → server creates one → returns it
      Follow-up msg  → client sends session_id → server loads history → injects into prompt
    The client (mobile app) stores the session_id in state/AsyncStorage.

CONCEPT — Saving Messages
    After streaming completes, both the user message and the full assembled
    assistant response are saved to SQLite. We must collect the full response
    during streaming to save it — we can't save token-by-token efficiently.

ENDPOINTS:
    POST /chat/query          — stream an answer from a named department agent (Phase 3)
    POST /chat/message        — primary endpoint: router picks department (Phase 4)
    GET  /chat/history/{sid}  — fetch message history for a session
    POST /chat/session        — create a new session explicitly
"""

import json
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session as DBSession

from core.config import settings
from core.logging_config import get_logger
from core.rate_limit import limiter
from core.security import get_current_user
from db.database import get_db
from db import models
from agents.query_engine import QueryEngine
from agents.router_agent import RouterAgent, CLARIFICATION_NEEDED, DEPARTMENT_DESCRIPTIONS
from .schemas import QueryRequest, MessageRequest, SessionResponse, MessageResponse

logger = get_logger(__name__)

router = APIRouter(prefix="/chat", tags=["Chat"])


# ── Helper ────────────────────────────────────────────────────────────────────

def _get_or_create_session(
    department: str,
    user: models.User,
    session_id: int | None,
    db: DBSession,
) -> models.Session:
    """
    Return an existing session or create a new one.

    Args:
        department: Target department for this conversation.
        user:       Authenticated user making the request.
        session_id: Client-provided session ID (None for new conversations).
        db:         Active DB session.

    Returns:
        Session ORM object (persisted).

    Raises:
        404 if session_id is provided but not found or belongs to another user.
    """
    if session_id is not None:
        session = db.query(models.Session).filter(
            models.Session.id == session_id,
            models.Session.user_id == user.id,   # ownership check
        ).first()

        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found",
            )
        logger.debug("Reusing session %d for user %d", session_id, user.id)
        return session

    # Create a new session.
    session = models.Session(user_id=user.id, department=department)
    db.add(session)
    db.commit()
    db.refresh(session)
    logger.info(
        "New session created: id=%d dept=%s user=%d",
        session.id, department, user.id,
    )
    return session


def _save_messages(
    session_id: int,
    user_message: str,
    assistant_response: str,
    db: DBSession,
) -> None:
    """
    Persist both the user message and the full assistant response to SQLite.

    Called after streaming completes — we save the assembled full response,
    not individual tokens.

    Args:
        session_id:          Session to attach messages to.
        user_message:        The original user question.
        assistant_response:  The complete LLM response (assembled from tokens).
        db:                  Active DB session.
    """
    user_msg = models.Message(
        session_id=session_id,
        role="user",
        content=user_message,
    )
    assistant_msg = models.Message(
        session_id=session_id,
        role="assistant",
        content=assistant_response,
    )
    db.add_all([user_msg, assistant_msg])
    db.commit()
    logger.debug(
        "Saved message pair to session %d (user: %d chars, assistant: %d chars)",
        session_id, len(user_message), len(assistant_response),
    )


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post(
    "/query",
    summary="Send a message to a department agent and stream the AI response",
)
def query(
    body: QueryRequest,
    current_user: models.User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """
    Main chat endpoint. Streams the AI response token by token using SSE format.

    Flow:
      1. Authenticate user via JWT
      2. Get or create a session for this department
      3. Emit a metadata SSE event with the session_id (so client can store it)
      4. Run the RAG query engine: embed → FAISS → LLM stream
      5. Yield each token as an SSE event
      6. After stream ends, save both messages to SQLite
      7. Emit a done event so the client knows streaming is complete

    The client should handle these SSE event types:
        event: metadata  → JSON with session_id and department
        event: token     → a text fragment to append to the UI
        event: done      → streaming finished, safe to enable input again
        event: error     → something went wrong

    Returns:
        StreamingResponse with Content-Type: text/event-stream
    """
    logger.info(
        "Chat query | user=%s dept=%s session=%s | '%s...'",
        current_user.email, body.department, body.session_id, body.message[:60],
    )

    # Resolve/create session before streaming so we have the session_id.
    session = _get_or_create_session(
        department=body.department,
        user=current_user,
        session_id=body.session_id,
        db=db,
    )
    engine = QueryEngine(department=body.department)

    def event_stream():
        """
        Generator that produces SSE-formatted lines.
        Each SSE event has the format:
            event: <type>\ndata: <payload>\n\n
        """
        # Step 1: Send session metadata so the client can save the session_id.
        meta = json.dumps({"session_id": session.id, "department": body.department})
        yield f"event: metadata\ndata: {meta}\n\n"

        # Step 2: Stream tokens from the RAG engine.
        collected_tokens = []
        try:
            for token in engine.stream_answer(body.message, db, session.id):
                collected_tokens.append(token)
                # Escape newlines inside SSE data lines (SSE spec: \n ends the field).
                safe_token = token.replace("\n", "\\n")
                yield f"event: token\ndata: {safe_token}\n\n"

            # Step 3: Save messages to DB after the stream completes.
            full_response = "".join(collected_tokens)
            _save_messages(session.id, body.message, full_response, db)

            # Step 4: Signal completion.
            yield "event: done\ndata: {}\n\n"

        except Exception as exc:
            logger.error(
                "Error during stream for session %d: %s", session.id, exc, exc_info=True
            )
            yield f"event: error\ndata: {json.dumps({'detail': str(exc)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            # Prevent proxies/load balancers from buffering the stream.
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/history/{session_id}",
    response_model=list[MessageResponse],
    summary="Retrieve message history for a session",
)
def get_history(
    session_id: int,
    current_user: models.User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """
    Return all messages in a session in chronological order.

    Used by the mobile app to restore chat history when re-opening a session.

    Raises:
        404 if the session doesn't exist or belongs to another user.
    """
    session = db.query(models.Session).filter(
        models.Session.id == session_id,
        models.Session.user_id == current_user.id,
    ).first()

    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = (
        db.query(models.Message)
        .filter(models.Message.session_id == session_id)
        .order_by(models.Message.created_at.asc())
        .all()
    )

    logger.debug(
        "History fetched: session=%d user=%s messages=%d",
        session_id, current_user.email, len(messages),
    )

    return [
        MessageResponse(
            id=m.id,
            role=m.role,
            content=m.content,
            created_at=m.created_at.isoformat(),
        )
        for m in messages
    ]


@router.post(
    "/session",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new chat session for a department",
)
def create_session(
    department: str,
    current_user: models.User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """
    Explicitly create a new session before the first message.

    The mobile app can call this when the user opens a department chat screen,
    then pass the returned session_id with the first /chat/query call.
    Alternatively, /chat/query creates a session automatically if none is provided.

    Args:
        department: Target department (query parameter).
    """
    if department not in [d.value for d in models.Department]:
        raise HTTPException(status_code=400, detail=f"Unknown department: {department}")

    session = models.Session(user_id=current_user.id, department=department)
    db.add(session)
    db.commit()
    db.refresh(session)

    logger.info(
        "Session created explicitly: id=%d dept=%s user=%s",
        session.id, department, current_user.email,
    )
    return SessionResponse(session_id=session.id, department=department)


# ── Phase 4: Primary chat endpoint (router decides department) ────────────────

@router.post(
    "/message",
    summary="Send a message — the AI router picks the right department automatically",
)
@limiter.limit(settings.RATE_LIMIT_CHAT)
def message(
    request: Request,
    body: MessageRequest,
    current_user: models.User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """
    Primary chat endpoint used by the mobile app.

    The client sends a plain message without specifying a department.
    The RouterAgent classifies it and hands off to the correct QueryEngine.

    SSE Event types emitted (same format as /chat/query plus extras):
        event: routing    → JSON with {department, confidence, reason}
                            emitted before the answer starts so the UI can
                            show "Answering via HR Agent..." instantly
        event: metadata   → JSON with {session_id, department}
        event: token      → text fragment to append to the chat bubble
        event: done       → streaming finished
        event: clarify    → confidence too low; JSON with suggested departments
                            so the UI can show department selection buttons

    Flow:
        1. RouterAgent classifies message → {department, confidence, reason}
        2a. confidence >= threshold → route to QueryEngine, stream answer
        2b. confidence <  threshold → emit clarify event, ask user to pick
        3. Save messages to SQLite (if answered)
    """
    logger.info(
        "Primary /chat/message | user=%s | session=%s | '%s...'",
        current_user.email, body.session_id, body.message[:60],
    )

    router_agent = RouterAgent()

    # Load recent history for context-aware routing (follow-up support).
    history_for_router = []
    if body.session_id is not None:
        history_rows = (
            db.query(models.Message)
            .filter(models.Message.session_id == body.session_id)
            .order_by(models.Message.created_at.desc())
            .limit(4)
            .all()
        )
        history_for_router = [
            {"role": m.role, "content": m.content}
            for m in reversed(history_rows)
        ]

    # Run the router (non-streaming — one LLM call with JSON mode).
    routing = router_agent.route(body.message, history=history_for_router)

    def event_stream():
        # ── Step 1: Emit routing decision so UI can show the agent badge early ──
        routing_meta = json.dumps({
            "department": routing.department,
            "confidence": round(routing.confidence, 3),
            "reason": routing.reason,
        })
        yield f"event: routing\ndata: {routing_meta}\n\n"

        # ── Step 2a: Clarification needed — confidence too low ────────────────
        if routing.department == CLARIFICATION_NEEDED:
            clarify_payload = json.dumps({
                "message": (
                    "I'm not sure which team can best help you. "
                    "Could you clarify which area your question relates to?"
                ),
                "departments": list(DEPARTMENT_DESCRIPTIONS.keys()),
            })
            logger.info(
                "Clarification requested for user=%s message='%s...'",
                current_user.email, body.message[:40],
            )
            yield f"event: clarify\ndata: {clarify_payload}\n\n"
            return

        # ── Step 2b: Route to the correct QueryEngine and stream the answer ───
        session = _get_or_create_session(
            department=routing.department,
            user=current_user,
            session_id=body.session_id,
            db=db,
        )

        # Emit session metadata AFTER routing so client has both pieces.
        meta = json.dumps({"session_id": session.id, "department": routing.department})
        yield f"event: metadata\ndata: {meta}\n\n"

        engine = QueryEngine(department=routing.department)
        collected_tokens = []

        try:
            for token in engine.stream_answer(body.message, db, session.id):
                collected_tokens.append(token)
                safe_token = token.replace("\n", "\\n")
                yield f"event: token\ndata: {safe_token}\n\n"

            full_response = "".join(collected_tokens)
            _save_messages(session.id, body.message, full_response, db)
            yield "event: done\ndata: {}\n\n"

        except Exception as exc:
            logger.error(
                "Error streaming for session %d: %s", session.id, exc, exc_info=True
            )
            yield f"event: error\ndata: {json.dumps({'detail': str(exc)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
