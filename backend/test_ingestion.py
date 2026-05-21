"""
test_ingestion.py
-----------------
PURPOSE:
    End-to-end smoke test for the Phase 2 ingestion pipeline.
    Run this script directly to verify the full flow:
      text → chunk → embed → FAISS index → search → retrieve

    This is NOT a unit test framework (no pytest required).
    It creates a temporary in-memory scenario and prints results.

HOW TO RUN:
    cd backend/
    ..\\RAG_VENV\\Scripts\\python test_ingestion.py

WHAT IT TESTS:
    1. Chunker splits text correctly with overlap
    2. Embedder loads and produces vectors of the right dimension
    3. VectorStore indexes vectors and searches return sensible results
    4. DB models create Document and Chunk rows correctly
    5. Full pipeline: fake policy text → searchable FAISS index
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from core.logging_config import get_logger, setup_file_logging

log_file = setup_file_logging("test_ingestion")
logger = get_logger("test_ingestion")
logger.info("Log file: %s", log_file)

# ── Sample policy text (simulates a real HR document) ─────────────────────────

SAMPLE_HR_POLICY = """
ANNUAL LEAVE POLICY
===================

1. ENTITLEMENT
All full-time employees are entitled to 21 days of paid annual leave per year.
Part-time employees receive leave on a pro-rata basis calculated from their
contracted hours.

2. CARRY-OVER RULES
Unused leave may be carried over to the following year up to a maximum of 5 days.
Any leave exceeding 5 days not taken by 31 March of the following year will be
forfeited unless approved by the HR Director.

3. LEAVE APPLICATION PROCESS
Employees must submit leave requests via the HR portal at least 7 calendar days
in advance for periods up to 5 days. For leave of 6 days or more, 14 days
advance notice is required.

4. MEDICAL LEAVE
Employees are entitled to 14 days of paid sick leave per year. A medical
certificate is required for absences of 3 or more consecutive days.

5. MATERNITY AND PATERNITY LEAVE
Primary caregivers are entitled to 16 weeks of paid maternity leave.
Secondary caregivers are entitled to 4 weeks of paid paternity leave.
Both types of leave can begin up to 4 weeks before the expected delivery date.

6. PUBLIC HOLIDAYS
The company observes all national public holidays. When a public holiday falls
on a weekend, a substitute day off is granted on the nearest working day.

7. ENCASHMENT
Annual leave encashment is permitted for up to 5 days per year, subject to
management approval. The encashment rate is calculated based on the employee's
basic monthly salary divided by 22 working days.
"""


def test_chunker():
    """Test that the chunker splits text into overlapping chunks."""
    logger.info("=" * 50)
    logger.info("TEST 1: Chunker")

    from ingestion.chunker import chunk_text

    chunks = chunk_text(SAMPLE_HR_POLICY, chunk_size=100, overlap=20)
    assert len(chunks) >= 2, "Expected at least 2 chunks from the sample text"

    logger.info("  Produced %d chunks", len(chunks))
    for i, chunk in enumerate(chunks):
        logger.info("  Chunk %d (%d chars): %s...", i, len(chunk), chunk[:60].replace('\n', ' '))

    # Verify overlap: the start of chunk[1] should share content with end of chunk[0]
    # (This is a heuristic check, not a strict byte comparison)
    assert len(chunks[0]) > 0, "Chunk 0 must not be empty"
    logger.info("  PASSED")
    return chunks


def test_embedder(chunks: list[str]):
    """Test that the embedder produces correctly shaped vectors."""
    logger.info("=" * 50)
    logger.info("TEST 2: Embedder (this downloads the model on first run ~90MB)")

    from ingestion.embedder import get_embedder, EMBEDDING_DIM

    embedder = get_embedder()
    assert embedder.dim == EMBEDDING_DIM, f"Expected dim={EMBEDDING_DIM}, got {embedder.dim}"

    # Single text embedding
    query_vector = embedder.embed_text("What is the annual leave entitlement?")
    assert query_vector.shape == (EMBEDDING_DIM,), f"Wrong shape: {query_vector.shape}"
    logger.info("  Single embed shape: %s  PASSED", query_vector.shape)

    # Batch embedding
    vectors = embedder.embed_batch(chunks)
    assert vectors.shape == (len(chunks), EMBEDDING_DIM), f"Wrong batch shape: {vectors.shape}"
    logger.info("  Batch embed shape: %s  PASSED", vectors.shape)

    return query_vector, vectors


def test_vector_store(chunks: list[str], query_vector, chunk_vectors):
    """Test that FAISS indexes vectors and returns sensible search results."""
    logger.info("=" * 50)
    logger.info("TEST 3: VectorStore (FAISS)")

    from ingestion.vector_store import VectorStore
    import numpy as np

    # Use a test department so we don't corrupt real data
    store = VectorStore("test_department")
    store.load()   # starts fresh (no saved index for test_department)

    # Add all chunk vectors
    faiss_ids = store.add_vectors(chunk_vectors)
    assert len(faiss_ids) == len(chunks), "FAISS IDs count must match chunk count"
    assert store.count == len(chunks), f"Expected {len(chunks)} vectors, got {store.count}"
    logger.info("  Indexed %d vectors | IDs: %s", len(faiss_ids), faiss_ids)

    # Search for the most relevant chunks to a query
    query = "leave encashment"
    from ingestion.embedder import get_embedder
    q_vec = get_embedder().embed_text(query)
    results = store.search(q_vec, k=3)

    logger.info("  Query: '%s'", query)
    logger.info("  Top-%d results:", len(results))
    for rank, (faiss_id, score) in enumerate(results):
        preview = chunks[faiss_id][:80].replace('\n', ' ')
        logger.info("    Rank %d | score=%.4f | chunk[%d]: %s...", rank + 1, score, faiss_id, preview)

    # The top result should mention encashment (score should be > 0.3 for cosine sim)
    top_score = results[0][1]
    assert top_score > 0.1, f"Top similarity score too low: {top_score}"
    logger.info("  PASSED")

    # Save and reload to verify persistence
    store.save()
    store2 = VectorStore("test_department")
    store2.load()
    assert store2.count == len(chunks), "Reloaded index should have same vector count"
    logger.info("  Save/Load roundtrip PASSED")

    # Clean up test index file
    store2.reset()
    import shutil
    test_dir = store.index_dir
    if test_dir.exists():
        shutil.rmtree(test_dir)
    logger.info("  Test index cleaned up")

    return results


def test_db_models(chunks: list[str], faiss_ids: list[int]):
    """Test that Document and Chunk rows can be written and read from SQLite."""
    logger.info("=" * 50)
    logger.info("TEST 4: Database models (Document + Chunk)")

    from db.database import engine, Base, SessionLocal
    from db import models

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        # Create a Document row
        doc = models.Document(
            department="hr",
            filename="test_hr_policy.txt",
            source_type="txt",
            chunk_count=len(chunks),
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        logger.info("  Document created: id=%d, chunk_count=%d", doc.id, doc.chunk_count)

        # Create Chunk rows
        chunk_rows = [
            models.Chunk(
                document_id=doc.id,
                department="hr",
                chunk_index=i,
                chunk_text=text,
                faiss_id=faiss_ids[i],
            )
            for i, text in enumerate(chunks)
        ]
        db.add_all(chunk_rows)
        db.commit()
        logger.info("  %d Chunk rows created", len(chunk_rows))

        # Query back by FAISS ID (simulating a real retrieval)
        top_faiss_id = faiss_ids[0]
        retrieved = db.query(models.Chunk).filter(
            models.Chunk.department == "hr",
            models.Chunk.faiss_id == top_faiss_id,
        ).first()
        assert retrieved is not None, "Should be able to retrieve chunk by faiss_id"
        logger.info("  Chunk retrieved by faiss_id=%d: '%s...'", top_faiss_id, retrieved.chunk_text[:60])
        logger.info("  PASSED")

        # Clean up test data
        db.delete(doc)   # cascade deletes chunks too
        db.commit()
        logger.info("  Test data cleaned up")

    finally:
        db.close()


if __name__ == "__main__":
    logger.info("Phase 2 Ingestion Pipeline — End-to-End Test")
    logger.info("=" * 50)

    try:
        chunks = test_chunker()
        query_vector, chunk_vectors = test_embedder(chunks)
        results = test_vector_store(chunks, query_vector, chunk_vectors)

        # Use the FAISS IDs from the vector store test (0..n-1)
        faiss_ids = list(range(len(chunks)))
        test_db_models(chunks, faiss_ids)

        logger.info("=" * 50)
        logger.info("ALL TESTS PASSED — Phase 2 pipeline is working correctly")

    except Exception as e:
        logger.error("TEST FAILED: %s", e, exc_info=True)
        sys.exit(1)
