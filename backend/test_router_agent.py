"""
test_router_agent.py
--------------------
PURPOSE:
    Tests the Phase 4 RouterAgent in isolation and integrated with
    the /chat/message endpoint flow.

    Tests:
      1. RouterAgent routes clear department queries correctly
      2. RouterAgent returns CLARIFICATION_NEEDED for vague messages
      3. Full /chat/message flow: route → QueryEngine → stream → save messages

HOW TO RUN:
    cd backend/
    ..\\RAG_VENV\\Scripts\\python test_router_agent.py

OUTPUT:
    Console + temp/test_router_agent.log
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from core.logging_config import get_logger, setup_file_logging

log_file = setup_file_logging("test_router_agent")
logger = get_logger("test_router_agent")
logger.info("Log file: %s", log_file)


# ── Test cases for the router ─────────────────────────────────────────────────

# (message, expected_department or None for clarification_needed)
ROUTING_TEST_CASES = [
    ("How many days of annual leave do I get?",         "hr"),
    ("I forgot my VPN password, how do I reset it?",    "it"),
    ("How do I submit an expense claim for a client lunch?", "finance"),
    ("We need to sign an NDA with a vendor, what's the process?", "legal"),
    ("How do I book a meeting room for next Monday?",   "admin"),
    ("Hello",                                           None),   # too vague → clarify
]


def test_routing_cases():
    """Test that the RouterAgent correctly classifies known department queries."""
    logger.info("=" * 55)
    logger.info("TEST 1: RouterAgent routing accuracy")

    from agents.router_agent import RouterAgent, CLARIFICATION_NEEDED

    agent = RouterAgent()
    passed = 0
    failed = 0

    for message, expected_dept in ROUTING_TEST_CASES:
        result = agent.route(message)
        actual = result.department

        if expected_dept is None:
            # We expect clarification_needed (low confidence).
            ok = actual == CLARIFICATION_NEEDED
        else:
            ok = actual == expected_dept

        status = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        else:
            failed += 1

        logger.info(
            "  [%s] '%s...' → expected=%s | got=%s (conf=%.2f)",
            status,
            message[:45],
            expected_dept or "clarify",
            actual,
            result.confidence,
        )
        if not ok:
            logger.warning("       reason: %s", result.reason)

    logger.info(
        "  Result: %d/%d passed", passed, len(ROUTING_TEST_CASES)
    )

    # We allow 1 miss — LLMs may occasionally disagree on edge cases.
    assert failed <= 1, (
        f"Too many routing failures: {failed}/{len(ROUTING_TEST_CASES)}. "
        "Check the routing prompt or the available model."
    )
    logger.info("  PASSED")


def test_clarification_path():
    """Verify CLARIFICATION_NEEDED is returned for vague input."""
    logger.info("=" * 55)
    logger.info("TEST 2: Clarification path for vague messages")

    from agents.router_agent import RouterAgent, CLARIFICATION_NEEDED, CONFIDENCE_THRESHOLD

    agent = RouterAgent()
    vague_messages = ["Hello", "I have a question", "Can you help me?"]

    for msg in vague_messages:
        result = agent.route(msg)
        logger.info(
            "  '%s' → dept=%s conf=%.2f",
            msg, result.department, result.confidence,
        )

        if result.confidence < CONFIDENCE_THRESHOLD:
            assert result.department == CLARIFICATION_NEEDED, (
                f"Expected CLARIFICATION_NEEDED for low confidence, got '{result.department}'"
            )

    logger.info("  PASSED")


def test_full_message_flow():
    """
    Full integration test: ingest a doc, route a message, stream answer, verify DB.
    """
    logger.info("=" * 55)
    logger.info("TEST 3: Full /chat/message flow (route → answer → save)")

    from db.database import engine, Base, SessionLocal
    from db import models
    from core.security import hash_password
    from ingestion.chunker import chunk_text
    from ingestion.embedder import get_embedder
    from ingestion.vector_store import get_vector_store
    from agents.router_agent import RouterAgent, CLARIFICATION_NEEDED
    from agents.query_engine import QueryEngine

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    POLICY_TEXT = """
IT ACCESS POLICY
================

1. VPN ACCESS
All employees working remotely must use the company VPN.
VPN credentials are issued by the IT helpdesk upon joining.
To reset a forgotten VPN password, raise a ticket at helpdesk.company.com
or call the IT support line at ext. 4400.

2. PASSWORD POLICY
Passwords must be at least 12 characters and changed every 90 days.
Do not share passwords with colleagues. Use the company password manager.

3. SOFTWARE INSTALLATION
Only IT-approved software may be installed on company devices.
Submit a software request via the IT portal at least 3 business days
before you need it.
"""

    doc_id = session_id = user_id = None

    try:
        # Ingest sample IT policy.
        chunks = chunk_text(POLICY_TEXT, chunk_size=100, overlap=20)
        embedder = get_embedder()
        vectors = embedder.embed_batch(chunks)
        store = get_vector_store("it")
        faiss_ids = store.add_vectors(vectors)
        store.save()

        doc = models.Document(
            department="it", filename="test_it_policy.txt",
            source_type="txt", chunk_count=len(chunks),
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        doc_id = doc.id

        db.add_all([
            models.Chunk(
                document_id=doc.id, department="it",
                chunk_index=i, chunk_text=t, faiss_id=fid,
            )
            for i, (t, fid) in enumerate(zip(chunks, faiss_ids))
        ])
        db.commit()
        logger.info("  IT policy ingested: %d chunks", len(chunks))

        # Create test user + session.
        user = db.query(models.User).filter(models.User.email == "routertest@company.com").first()
        if not user:
            user = models.User(
                email="routertest@company.com",
                hashed_password=hash_password("pass"),
                full_name="Router Test",
                role=models.UserRole.user,
                department="it",
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        user_id = user.id

        session = models.Session(user_id=user.id, department="it")
        db.add(session)
        db.commit()
        db.refresh(session)
        session_id = session.id

        # Route the message.
        question = "How do I reset my VPN password?"
        agent = RouterAgent()
        routing = agent.route(question)

        logger.info(
            "  Routing result: dept=%s conf=%.2f reason='%s'",
            routing.department, routing.confidence, routing.reason,
        )
        assert routing.department == "it", (
            f"Expected 'it', got '{routing.department}'"
        )
        assert routing.department != CLARIFICATION_NEEDED

        # Stream answer from the routed engine.
        engine = QueryEngine(routing.department)
        tokens = []
        logger.info("  Streaming answer:")
        print("  " + "-" * 50)
        for token in engine.stream_answer(question, db, session_id):
            tokens.append(token)
            safe = token.encode("cp1252", errors="replace").decode("cp1252")
            print(safe, end="", flush=True)
        print()
        print("  " + "-" * 50)

        full_answer = "".join(tokens)
        assert len(full_answer) > 20, "Answer too short"
        assert any(kw in full_answer.lower() for kw in ["vpn", "password", "helpdesk", "4400", "reset"]), (
            f"Expected VPN-related content in answer: {full_answer[:200]}"
        )
        logger.info("  Answer length: %d chars  PASSED", len(full_answer))

        # Save messages.
        db.add_all([
            models.Message(session_id=session_id, role="user", content=question),
            models.Message(session_id=session_id, role="assistant", content=full_answer),
        ])
        db.commit()

        # Verify.
        msgs = db.query(models.Message).filter(models.Message.session_id == session_id).all()
        assert len(msgs) == 2
        logger.info("  Message persistence verified  PASSED")

    finally:
        # Cleanup.
        if session_id:
            s = db.get(models.Session, session_id)
            if s:
                db.delete(s)
        if doc_id:
            d = db.get(models.Document, doc_id)
            if d:
                db.delete(d)
        if user_id:
            u = db.query(models.User).filter(models.User.email == "routertest@company.com").first()
            if u:
                db.delete(u)
        db.commit()
        db.close()

        store = get_vector_store("it")
        store.reset()
        logger.info("  Test data cleaned up")


if __name__ == "__main__":
    logger.info("Phase 4 RouterAgent — End-to-End Test")
    logger.info("=" * 55)

    try:
        test_routing_cases()
        test_clarification_path()
        test_full_message_flow()

        logger.info("=" * 55)
        logger.info("ALL TESTS PASSED — Phase 4 multi-agent routing is working")

    except Exception as exc:
        logger.error("TEST FAILED: %s", exc, exc_info=True)
        sys.exit(1)
