"""
test_query_engine.py
--------------------
PURPOSE:
    End-to-end test for the Phase 3 RAG query engine.

    Tests:
      1. Ingest sample HR policy text into the HR FAISS index and DB
      2. Run the QueryEngine and stream an answer to a policy question
      3. Verify session + message rows are saved in SQLite
      4. Clean up test data

HOW TO RUN:
    cd backend/
    ..\\RAG_VENV\\Scripts\\python test_query_engine.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from core.logging_config import get_logger, setup_file_logging

log_file = setup_file_logging("test_query_engine")
logger = get_logger("test_query_engine")
logger.info("Log file: %s", log_file)

SAMPLE_POLICY = """
SICK LEAVE POLICY
=================

1. ENTITLEMENT
All permanent employees are entitled to 14 days of paid sick leave per year.
Contract employees receive 7 days of paid sick leave per year.

2. CERTIFICATE REQUIREMENT
A medical certificate from a registered doctor is required for:
  - Any absence of 3 or more consecutive working days
  - The fourth and subsequent sick leave instances within a calendar year

3. NOTIFICATION
Employees must notify their direct manager before 9:00 AM on the first day
of absence, or as soon as reasonably practicable.

4. HOSPITALISATION LEAVE
Employees who require hospitalisation are entitled to an additional 60 days
of hospitalisation leave per year, on top of the standard 14 sick days.

5. CARRY OVER
Unused sick leave does NOT carry over to the following year. Sick leave
entitlement resets on 1 January each year.
"""


def step1_ingest_sample_policy():
    """Ingest the sample policy into the HR FAISS index and SQLite."""
    logger.info("=" * 55)
    logger.info("STEP 1: Ingesting sample HR policy into FAISS + SQLite")

    from db.database import engine, Base, SessionLocal
    from db import models
    from ingestion.chunker import chunk_text
    from ingestion.embedder import get_embedder
    from ingestion.vector_store import get_vector_store

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        chunks = chunk_text(SAMPLE_POLICY, chunk_size=100, overlap=20)
        logger.info("  Split into %d chunks", len(chunks))

        embedder = get_embedder()
        vectors = embedder.embed_batch(chunks)

        store = get_vector_store("hr")
        faiss_ids = store.add_vectors(vectors)
        store.save()
        logger.info("  Added %d vectors to HR FAISS index", len(faiss_ids))

        doc = models.Document(
            department="hr",
            filename="test_sick_leave_policy.txt",
            source_type="txt",
            chunk_count=len(chunks),
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)

        chunk_rows = [
            models.Chunk(
                document_id=doc.id,
                department="hr",
                chunk_index=i,
                chunk_text=text,
                faiss_id=fid,
            )
            for i, (text, fid) in enumerate(zip(chunks, faiss_ids))
        ]
        db.add_all(chunk_rows)
        db.commit()
        logger.info("  Saved document id=%d with %d chunk rows", doc.id, len(chunk_rows))

    finally:
        db.close()

    return doc.id


def step2_create_test_user_and_session():
    """Create a test user and session for the query."""
    logger.info("=" * 55)
    logger.info("STEP 2: Creating test user and session")

    from db.database import engine, Base, SessionLocal
    from db import models
    from core.security import hash_password

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        # Reuse existing test user if present.
        user = db.query(models.User).filter(models.User.email == "testbot@company.com").first()
        if not user:
            user = models.User(
                email="testbot@company.com",
                hashed_password=hash_password("testpass"),
                full_name="Test Bot",
                role=models.UserRole.user,
                department="hr",
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            logger.info("  Test user created: id=%d", user.id)
        else:
            logger.info("  Reusing existing test user: id=%d", user.id)

        session = models.Session(user_id=user.id, department="hr")
        db.add(session)
        db.commit()
        db.refresh(session)
        logger.info("  Test session created: id=%d", session.id)

        return user.id, session.id

    finally:
        db.close()


def step3_run_query_engine(session_id: int):
    """Run the QueryEngine and stream an answer, verifying it makes sense."""
    logger.info("=" * 55)
    logger.info("STEP 3: Running QueryEngine with streaming")

    from db.database import SessionLocal
    from agents.query_engine import QueryEngine

    question = "How many sick days am I entitled to?"
    logger.info("  Question: '%s'", question)

    db = SessionLocal()
    engine = QueryEngine("hr")

    try:
        tokens = []
        logger.info("  Streaming response:")
        print("  " + "-" * 50)

        for token in engine.stream_answer(question, db, session_id):
            tokens.append(token)
            # Encode to cp1252 (Windows console) replacing unmappable chars with '?'
            safe = token.encode("cp1252", errors="replace").decode("cp1252")
            print(safe, end="", flush=True)

        print()
        print("  " + "-" * 50)

        full_answer = "".join(tokens)
        assert len(full_answer) > 20, "Answer too short — LLM may have failed"

        # The answer should mention 14 days (from the sample policy).
        assert "14" in full_answer or "fourteen" in full_answer.lower(), (
            f"Expected '14' in answer, got: {full_answer[:200]}"
        )
        logger.info("  Answer length: %d chars  PASSED", len(full_answer))

        # Save messages explicitly — in production the HTTP router does this,
        # but the test calls stream_answer() directly without the router.
        from db import models as _models
        db.add_all([
            _models.Message(session_id=session_id, role="user", content=question),
            _models.Message(session_id=session_id, role="assistant", content=full_answer),
        ])
        db.commit()
        logger.info("  Messages saved to session %d", session_id)

    finally:
        db.close()


def step4_verify_messages_saved(session_id: int):
    """Verify that the user message and assistant response were saved to SQLite."""
    logger.info("=" * 55)
    logger.info("STEP 4: Verifying messages were saved to DB")

    from db.database import SessionLocal
    from db import models

    db = SessionLocal()
    try:
        messages = (
            db.query(models.Message)
            .filter(models.Message.session_id == session_id)
            .order_by(models.Message.created_at)
            .all()
        )

        assert len(messages) == 2, f"Expected 2 messages, got {len(messages)}"
        assert messages[0].role == "user"
        assert messages[1].role == "assistant"
        assert len(messages[1].content) > 10

        logger.info(
            "  Saved: user='%s...' | assistant='%s...'",
            messages[0].content[:40],
            messages[1].content[:40],
        )
        logger.info("  PASSED")

    finally:
        db.close()


def cleanup(doc_id: int, session_id: int, user_id: int):
    """Remove all test data created by this script."""
    logger.info("=" * 55)
    logger.info("Cleaning up test data")

    from db.database import SessionLocal
    from db import models
    from ingestion.vector_store import get_vector_store

    db = SessionLocal()
    try:
        # Delete session (cascades to messages).
        s = db.get(models.Session, session_id)
        if s:
            db.delete(s)

        # Delete document (cascades to chunks).
        d = db.get(models.Document, doc_id)
        if d:
            db.delete(d)

        # Remove test user only if we created it (by email).
        u = db.query(models.User).filter(models.User.email == "testbot@company.com").first()
        if u:
            db.delete(u)

        db.commit()
        logger.info("  DB test data removed")

        # Reset the HR FAISS index (it only had test data).
        store = get_vector_store("hr")
        store.reset()
        logger.info("  HR FAISS index reset")

    finally:
        db.close()


if __name__ == "__main__":
    logger.info("Phase 3 Query Engine — End-to-End Test")
    logger.info("=" * 55)

    doc_id, user_id, session_id = None, None, None

    try:
        doc_id = step1_ingest_sample_policy()
        user_id, session_id = step2_create_test_user_and_session()
        step3_run_query_engine(session_id)
        step4_verify_messages_saved(session_id)

        logger.info("=" * 55)
        logger.info("ALL STEPS PASSED — Phase 3 RAG pipeline is working correctly")

    except Exception as exc:
        logger.error("TEST FAILED: %s", exc, exc_info=True)
        sys.exit(1)

    finally:
        if doc_id and session_id and user_id:
            cleanup(doc_id, session_id, user_id)
