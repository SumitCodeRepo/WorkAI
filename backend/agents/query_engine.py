"""
agents/query_engine.py
----------------------
PURPOSE:
    The QueryEngine is the heart of the RAG pipeline for one department.
    It ties together retrieval (FAISS), context building (prompts.py),
    and generation (Ollama LLM) into one callable interface.

    Given a user question and a department, it:
      1. Embeds the question into a vector
      2. Searches FAISS for the most similar document chunks
      3. Fetches chunk texts from SQLite
      4. Builds a prompt: system + context + chat history + question
      5. Calls the Ollama chat API and streams the response token by token

CONCEPT — Streaming (Generator pattern)
    Instead of blocking until the LLM finishes (10-30s), we use Python
    generators: the function yields each token as it arrives.

    The caller (FastAPI route) wraps this generator in StreamingResponse,
    which sends each yielded chunk to the client immediately as a
    Server-Sent Event (SSE). The mobile app renders text progressively.

    Generator flow:
        query_engine.stream_answer(...)
            → yields "Annual"
            → yields " leave"
            → yields " is"
            → yields " 21 days"
            → StopIteration (done)

CONCEPT — Chat History Injection
    To support follow-up questions ("What about part-time?"), we load the
    last N messages from the session and include them BEFORE the current
    question. The LLM sees:
        [SYSTEM]
        [CONTEXT]
        [user]: How many days of annual leave do I get?
        [assistant]: Full-time employees get 21 days...
        [user]: What about part-time?   ← current question

CONCEPT — Chunk Retrieval from SQLite
    FAISS returns integer IDs. We convert them back to text by querying:
        SELECT chunk_text FROM chunks
        WHERE department = ? AND faiss_id IN (?, ?, ...)
        ORDER BY faiss_id   ← preserves relevance order

CONCEPT — No-document Fallback
    If the department index is empty (no documents ingested yet), FAISS
    raises a RuntimeError. We catch it and return a clear informational
    message instead of a 500 error.

USAGE:
    engine = QueryEngine("hr")
    for token in engine.stream_answer(question, db, session_id):
        print(token, end="", flush=True)
"""

import json
import requests
from sqlalchemy.orm import Session as DBSession
from core.config import settings
from core.logging_config import get_logger
from db import models
from ingestion.embedder import get_embedder
from ingestion.vector_store import get_vector_store
from agents.prompts import build_context_block, get_system_prompt

logger = get_logger(__name__)

# Number of recent message pairs (user+assistant) to include as chat history.
# Higher = better follow-up support, but uses more of the LLM context window.
HISTORY_TURNS = 4

# Number of document chunks to retrieve from FAISS for each query.
# Higher = more context, but dilutes relevance and fills the context window faster.
TOP_K_CHUNKS = 5


class QueryEngine:
    """
    Department-scoped RAG engine: retrieves relevant chunks and streams LLM answers.

    One instance per department is sufficient — it is stateless between queries
    (all state lives in the DB session and FAISS index, not in this object).

    Attributes:
        department: The department this engine serves (e.g. 'hr').
        model:      Ollama model name to use for generation.
    """

    def __init__(self, department: str, model: str | None = None) -> None:
        """
        Args:
            department: Lowercase department name.
            model:      Override the Ollama model. Defaults to settings value.
        """
        self.department = department.lower()
        self.model = model or settings.OLLAMA_MODEL
        logger.info(
            "QueryEngine created for department='%s' model='%s'",
            self.department, self.model,
        )

    # ── Retrieval ─────────────────────────────────────────────────────────────

    def _retrieve_chunks(self, question: str, db: DBSession) -> list[str]:
        """
        Embed the question, search FAISS, return the top-k chunk texts.

        Returns an empty list (not an exception) when the FAISS index is empty,
        so the query engine can still respond (with a "no documents" message).

        Args:
            question: The user's raw question string.
            db:       Active SQLAlchemy session for chunk text lookup.

        Returns:
            List of chunk text strings, ordered best-match first.
        """
        embedder = get_embedder()
        query_vector = embedder.embed_text(question)
        logger.debug("Question embedded: shape=%s", query_vector.shape)

        try:
            store = get_vector_store(self.department)
            results = store.search(query_vector, k=TOP_K_CHUNKS)
        except RuntimeError as exc:
            # Index is empty — no documents ingested for this department yet.
            logger.warning("FAISS search failed for '%s': %s", self.department, exc)
            return []

        if not results:
            logger.info("FAISS returned no results for department '%s'", self.department)
            return []

        # results = [(faiss_id, score), ...] sorted best-first
        faiss_ids = [fid for fid, _ in results]
        scores = [s for _, s in results]
        logger.info(
            "FAISS top-%d results for '%s': ids=%s scores=%s",
            len(results), self.department, faiss_ids,
            [f"{s:.3f}" for s in scores],
        )

        # Look up chunk texts in SQLite using the FAISS IDs.
        # We preserve retrieval order by sorting manually after fetching.
        chunk_rows = (
            db.query(models.Chunk)
            .filter(
                models.Chunk.department == self.department,
                models.Chunk.faiss_id.in_(faiss_ids),
            )
            .all()
        )

        # Build a dict {faiss_id: chunk_text} then re-order by retrieval rank.
        id_to_text = {row.faiss_id: row.chunk_text for row in chunk_rows}
        ordered_texts = [id_to_text[fid] for fid in faiss_ids if fid in id_to_text]

        logger.info(
            "Retrieved %d chunk texts from SQLite for department '%s'",
            len(ordered_texts), self.department,
        )
        return ordered_texts

    # ── History ───────────────────────────────────────────────────────────────

    def _load_history(self, session_id: int | None, db: DBSession) -> list[dict]:
        """
        Load the last HISTORY_TURNS * 2 messages from the session.

        Returns them in chronological order so the LLM sees the conversation
        in the correct sequence.

        Args:
            session_id: DB session ID, or None if this is a new session.
            db:         Active SQLAlchemy session.

        Returns:
            List of {"role": ..., "content": ...} dicts for the Ollama API.
        """
        if session_id is None:
            return []

        messages = (
            db.query(models.Message)
            .filter(models.Message.session_id == session_id)
            .order_by(models.Message.created_at.desc())
            .limit(HISTORY_TURNS * 2)  # user + assistant per turn
            .all()
        )

        # Reverse to chronological order (we fetched newest-first for the LIMIT).
        history = [{"role": m.role, "content": m.content} for m in reversed(messages)]
        logger.debug("Loaded %d history messages for session %s", len(history), session_id)
        return history

    # ── LLM Call ──────────────────────────────────────────────────────────────

    def _build_messages(
        self,
        question: str,
        chunks: list[str],
        history: list[dict],
    ) -> list[dict]:
        """
        Assemble the full message list sent to the Ollama chat API.

        Structure:
            system  — department identity + grounding instruction
            (user/assistant pairs from history)
            user    — context block + current question

        The context is attached to the current user message rather than the
        system prompt so the LLM treats it as fresh information per query,
        not as static background.

        Args:
            question: The user's current question.
            chunks:   Retrieved document chunks (empty list if none available).
            history:  Prior messages from this session.

        Returns:
            List of message dicts in Ollama/OpenAI format.
        """
        system_prompt = get_system_prompt(self.department)
        context_block = build_context_block(chunks)

        user_message = f"{context_block}\n\nQuestion: {question}"

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        logger.debug(
            "Built prompt: %d messages | context chunks=%d | history turns=%d",
            len(messages), len(chunks), len(history),
        )
        return messages

    def stream_answer(
        self,
        question: str,
        db: DBSession,
        session_id: int | None = None,
    ):
        """
        Main entry point. Retrieves context and streams the LLM response.

        This is a Python generator — iterate over it to receive tokens:
            for token in engine.stream_answer(question, db, session_id):
                send_to_client(token)

        Args:
            question:   The user's message.
            db:         Active SQLAlchemy session (for chunk lookup + history).
            session_id: Existing session ID for history injection, or None.

        Yields:
            str — individual token strings as they arrive from the LLM.
                  May include punctuation, spaces, or newlines.

        Raises:
            requests.RequestException if Ollama is unreachable.
        """
        logger.info(
            "stream_answer | dept='%s' | session=%s | question='%s...'",
            self.department, session_id, question[:60],
        )

        # Step 1: Retrieve relevant chunks.
        chunks = self._retrieve_chunks(question, db)

        # Step 2: Load conversation history.
        history = self._load_history(session_id, db)

        # Step 3: Build the full message list.
        messages = self._build_messages(question, chunks, history)

        # Step 4: Call Ollama with stream=True and yield each token.
        url = f"{settings.OLLAMA_BASE_URL}/api/chat"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            # thinking=False suppresses the <think> reasoning block from appearing
            # in the streamed output (the gpt-oss model supports this flag).
            "think": False,
        }

        logger.info("Calling Ollama: model=%s url=%s", self.model, url)

        try:
            with requests.post(url, json=payload, stream=True, timeout=120) as resp:
                resp.raise_for_status()

                full_response = []
                for line in resp.iter_lines():
                    if not line:
                        continue

                    try:
                        chunk_data = json.loads(line)
                    except json.JSONDecodeError:
                        logger.warning("Non-JSON line from Ollama: %s", line[:80])
                        continue

                    token = chunk_data.get("message", {}).get("content", "")
                    if token:
                        full_response.append(token)
                        yield token

                    # done=True signals the end of the stream.
                    if chunk_data.get("done"):
                        break

                full_text = "".join(full_response)
                logger.info(
                    "Stream complete | dept='%s' | response length=%d chars",
                    self.department, len(full_text),
                )

        except requests.Timeout:
            logger.error("Ollama request timed out for dept='%s'", self.department)
            yield "\n\n[Error: The AI took too long to respond. Please try again.]"
        except requests.RequestException as exc:
            logger.error("Ollama request failed: %s", exc)
            yield "\n\n[Error: Could not reach the AI service. Please try again later.]"
