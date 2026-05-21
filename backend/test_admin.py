"""
test_admin.py
-------------
PURPOSE:
    Tests the Phase 5 admin document management pipeline in isolation —
    without spinning up the HTTP server.

    Tests:
      1. ingest_document()  — parse → chunk → embed → FAISS → SQLite
      2. List documents via SQLite query (mirrors GET /admin/documents)
      3. Delete document + cascade → chunks removed
      4. rebuild_faiss_index() — rebuilt from remaining chunks

HOW TO RUN:
    cd backend/
    ..\\RAG_VENV\\Scripts\\python test_admin.py

OUTPUT:
    Console + temp/test_admin.log
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from core.logging_config import get_logger, setup_file_logging

log_file = setup_file_logging("test_admin")
logger = get_logger("test_admin")
logger.info("Log file: %s", log_file)


# ── Sample documents ──────────────────────────────────────────────────────────

HR_POLICY = """
ANNUAL LEAVE POLICY
===================

1. ENTITLEMENT
All full-time employees are entitled to 18 days of annual leave per calendar year.
Part-time employees receive leave on a pro-rata basis.
Unused leave may be carried forward to the next calendar year, up to a maximum of 5 days.

2. APPLYING FOR LEAVE
Submit leave requests via the HR portal at least 3 working days in advance.
For leave longer than 5 consecutive days, manager approval is required 2 weeks in advance.
Emergency leave requests are handled on a case-by-case basis by HR.

3. SICK LEAVE
Employees receive 14 days of paid sick leave per year.
A medical certificate is required for sick leave exceeding 2 consecutive days.
Sick leave does not accumulate and cannot be converted to cash.
"""

FINANCE_POLICY = """
EXPENSE REIMBURSEMENT POLICY
=============================

1. ELIGIBLE EXPENSES
Business meals, travel (flights, hotels, ground transport), client entertainment,
and professional development expenses are eligible for reimbursement.

2. SUBMISSION PROCESS
Submit expense claims within 30 days of the expense date.
All claims must be submitted via the Finance portal with original receipts attached.
Claims without receipts will not be processed.

3. APPROVAL LIMITS
Expenses below SGD 500 require line-manager approval only.
Expenses between SGD 500 and SGD 2,000 require Finance Manager approval.
Expenses above SGD 2,000 require CFO approval.
"""


def test_ingest_document():
    """Test that ingest_document() produces chunks in both FAISS and SQLite."""
    logger.info("=" * 55)
    logger.info("TEST 1: ingest_document() — HR policy")

    import tempfile, pathlib
    from db.database import engine, Base, SessionLocal
    from db import models
    from ingestion.pipeline import ingest_document
    from ingestion.vector_store import get_vector_store

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    doc_id = None
    try:
        # Write policy text to a temp file.
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write(HR_POLICY)
            tmp_path = f.name

        doc = ingest_document(
            source=tmp_path,
            department="hr",
            db=db,
            filename="test_hr_policy.txt",
            source_type="txt",
        )
        doc_id = doc.id

        assert doc.chunk_count > 0, "Expected at least 1 chunk"
        logger.info("  Document created: id=%d  chunks=%d", doc.id, doc.chunk_count)

        # Verify chunks in SQLite.
        chunks = db.query(models.Chunk).filter(
            models.Chunk.document_id == doc.id
        ).all()
        assert len(chunks) == doc.chunk_count, (
            f"Chunk count mismatch: doc says {doc.chunk_count}, SQLite has {len(chunks)}"
        )
        logger.info("  SQLite chunk count verified: %d", len(chunks))

        # Verify vectors in FAISS.
        store = get_vector_store("hr")
        assert store.index.ntotal >= doc.chunk_count, (
            f"FAISS has {store.index.ntotal} vectors, expected >= {doc.chunk_count}"
        )
        logger.info("  FAISS vector count: %d  PASSED", store.index.ntotal)

    finally:
        if doc_id:
            d = db.get(models.Document, doc_id)
            if d:
                db.delete(d)
            db.commit()
        db.close()
        try:
            os.remove(tmp_path)
        except OSError:
            pass

        store = get_vector_store("hr")
        store.reset()
        logger.info("  Cleanup done")

    logger.info("  PASSED")


def test_list_and_delete():
    """Test document listing and deletion with cascade chunk removal."""
    logger.info("=" * 55)
    logger.info("TEST 2: List documents + delete + cascade")

    import tempfile
    from db.database import engine, Base, SessionLocal
    from db import models
    from ingestion.pipeline import ingest_document
    from ingestion.vector_store import get_vector_store

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    hr_doc_id = fin_doc_id = None
    try:
        # Ingest two docs into two departments.
        for policy_text, dept, fname in [
            (HR_POLICY, "hr", "test_hr_policy.txt"),
            (FINANCE_POLICY, "finance", "test_finance_policy.txt"),
        ]:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, encoding="utf-8"
            ) as f:
                f.write(policy_text)
                tmp = f.name

            doc = ingest_document(tmp, dept, db, filename=fname, source_type="txt")
            if dept == "hr":
                hr_doc_id = doc.id
            else:
                fin_doc_id = doc.id
            os.remove(tmp)
            logger.info("  Ingested '%s' (id=%d, chunks=%d)", fname, doc.id, doc.chunk_count)

        # List all docs.
        all_docs = db.query(models.Document).all()
        assert any(d.department == "hr" for d in all_docs)
        assert any(d.department == "finance" for d in all_docs)
        logger.info("  List verified: %d documents total", len(all_docs))

        # Filter by department.
        hr_docs = db.query(models.Document).filter(
            models.Document.department == "hr"
        ).all()
        assert len(hr_docs) >= 1
        logger.info("  HR filter: %d doc(s)  PASSED", len(hr_docs))

        # Delete HR doc — chunks should cascade.
        hr_chunks_before = db.query(models.Chunk).filter(
            models.Chunk.document_id == hr_doc_id
        ).count()
        assert hr_chunks_before > 0

        d = db.get(models.Document, hr_doc_id)
        db.delete(d)
        db.commit()

        hr_chunks_after = db.query(models.Chunk).filter(
            models.Chunk.document_id == hr_doc_id
        ).count()
        assert hr_chunks_after == 0, (
            f"Expected 0 chunks after delete, found {hr_chunks_after}"
        )
        logger.info(
            "  Delete + cascade verified: %d chunks before, 0 after  PASSED",
            hr_chunks_before,
        )
        hr_doc_id = None  # Already deleted.

    finally:
        for doc_id in [hr_doc_id, fin_doc_id]:
            if doc_id:
                d = db.get(models.Document, doc_id)
                if d:
                    db.delete(d)
        db.commit()
        db.close()
        for dept in ("hr", "finance"):
            get_vector_store(dept).reset()
        logger.info("  Cleanup done")

    logger.info("  PASSED")


def test_rebuild_faiss_index():
    """Test that rebuild_faiss_index restores a consistent FAISS index after deletion."""
    logger.info("=" * 55)
    logger.info("TEST 3: rebuild_faiss_index() after document deletion")

    import tempfile
    from db.database import engine, Base, SessionLocal
    from db import models
    from ingestion.pipeline import ingest_document, rebuild_faiss_index
    from ingestion.vector_store import get_vector_store
    from ingestion.embedder import get_embedder

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    doc1_id = doc2_id = None
    try:
        # Ingest two HR documents.
        for text, fname in [
            (HR_POLICY, "hr_leave.txt"),
            (FINANCE_POLICY[:200], "hr_extra.txt"),  # small second doc
        ]:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, encoding="utf-8"
            ) as f:
                f.write(text)
                tmp = f.name
            doc = ingest_document(tmp, "hr", db, filename=fname, source_type="txt")
            os.remove(tmp)
            if doc1_id is None:
                doc1_id = doc.id
            else:
                doc2_id = doc.id
            logger.info(
                "  Ingested '%s': doc_id=%d chunks=%d", fname, doc.id, doc.chunk_count
            )

        store = get_vector_store("hr")
        vectors_before = store.index.ntotal
        logger.info("  FAISS vectors before delete: %d", vectors_before)

        # Delete first doc (cascade removes its chunks).
        d1 = db.get(models.Document, doc1_id)
        doc1_chunks = d1.chunk_count
        db.delete(d1)
        db.commit()
        doc1_id = None

        # Rebuild index.
        count = rebuild_faiss_index("hr", db)
        store = get_vector_store("hr")
        logger.info("  FAISS vectors after rebuild: %d", store.index.ntotal)

        # After rebuild, the index should only contain doc2's chunks.
        d2 = db.get(models.Document, doc2_id)
        assert store.index.ntotal == d2.chunk_count, (
            f"Expected {d2.chunk_count} vectors, got {store.index.ntotal}"
        )
        assert store.index.ntotal < vectors_before

        # Verify faiss_ids were updated in SQLite.
        chunks = db.query(models.Chunk).filter(
            models.Chunk.document_id == doc2_id
        ).all()
        faiss_ids = [c.faiss_id for c in chunks]
        assert all(fid < store.index.ntotal for fid in faiss_ids), (
            f"faiss_ids {faiss_ids} out of range for index of size {store.index.ntotal}"
        )
        logger.info("  faiss_id consistency verified  PASSED")

        # Verify the rebuilt index is searchable.
        embedder = get_embedder()
        q_vec = embedder.embed_text("expense reimbursement")
        results = store.search(q_vec, k=1)
        assert len(results) == 1
        logger.info("  Search on rebuilt index returned %d result(s)  PASSED", len(results))

    finally:
        for doc_id in [doc1_id, doc2_id]:
            if doc_id:
                d = db.get(models.Document, doc_id)
                if d:
                    db.delete(d)
        db.commit()
        db.close()
        get_vector_store("hr").reset()
        logger.info("  Cleanup done")

    logger.info("  PASSED")


if __name__ == "__main__":
    logger.info("Phase 5 Admin Document Management — Test Suite")
    logger.info("=" * 55)

    try:
        test_ingest_document()
        test_list_and_delete()
        test_rebuild_faiss_index()

        logger.info("=" * 55)
        logger.info("ALL TESTS PASSED — Phase 5 admin pipeline is working")

    except Exception as exc:
        logger.error("TEST FAILED: %s", exc, exc_info=True)
        sys.exit(1)
