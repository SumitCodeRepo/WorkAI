"""
ingestion/pipeline.py
---------------------
PURPOSE:
    Orchestrates the full document ingestion pipeline:
        parse → chunk → embed → FAISS index → SQLite rows

    This module is the single entry point for turning an uploaded file (or URL)
    into searchable vector data.  It is called by the admin upload endpoint and
    can also be called directly from test scripts.

CONCEPT — Pipeline vs. Individual Steps
    Phases 2-3 built each step (parser, chunker, embedder, vector_store) as a
    standalone module so you could learn each concept in isolation.  Phase 5 adds
    this orchestrator that wires them together in one call.

    Having a single `ingest_document()` function:
      - Keeps the HTTP endpoint thin (5 lines instead of 50)
      - Makes it easy to call from background tasks without duplicating logic
      - Gives a single place to add retry/error handling later

CONCEPT — FastAPI BackgroundTasks
    When the admin uploads a file the server should:
      a) Acknowledge the upload immediately (201 Created)
      b) Process the file (parse, embed, index) asynchronously in the background
    The client doesn't have to wait 30 seconds for a large PDF to be embedded.

    BackgroundTasks is a lightweight mechanism built into FastAPI/Starlette.
    It runs the callback in the same process after the response is sent.
    For heavy production workloads you'd use Celery/RQ, but BackgroundTasks
    is perfect for a single-server setup like this.

EXPORTS:
    ingest_document(source, department, db, *, filename=None, source_type=None)
        → Document ORM object (already committed)
"""

import os
from pathlib import Path
from sqlalchemy.orm import Session as DBSession

from core.logging_config import get_logger
from db import models
from ingestion.parsers import parse_document
from ingestion.chunker import chunk_text
from ingestion.embedder import get_embedder
from ingestion.vector_store import get_vector_store

logger = get_logger(__name__)


def ingest_document(
    source: str | Path,
    department: str,
    db: DBSession,
    *,
    filename: str | None = None,
    source_type: str | None = None,
) -> models.Document:
    """
    Full ingestion pipeline: parse → chunk → embed → FAISS → SQLite.

    Args:
        source:       File path (str or Path) or URL string.
        department:   Target department (hr, it, finance, legal, admin).
        db:           Active SQLAlchemy session.
        filename:     Display name stored in the Document row.
                      Defaults to the basename of `source`.
        source_type:  One of 'pdf', 'docx', 'txt', 'url'.
                      Inferred from file extension / URL prefix if omitted.

    Returns:
        Committed Document ORM object with id, chunk_count, etc.

    Raises:
        ValueError: If the source produces no usable text.
        Any exception from the parser, embedder, or FAISS is propagated.
    """
    source = str(source)

    # Derive display name and source type if not provided.
    if filename is None:
        filename = Path(source).name if not source.startswith("http") else source

    if source_type is None:
        if source.startswith("http"):
            source_type = "url"
        else:
            ext = Path(source).suffix.lower().lstrip(".")
            source_type = ext if ext in ("pdf", "docx", "txt", "md") else "txt"

    logger.info(
        "Ingestion started | dept=%s | source_type=%s | file=%s",
        department, source_type, filename,
    )

    # ── Step 1: Parse raw text ────────────────────────────────────────────────
    text = parse_document(source)
    if not text or not text.strip():
        raise ValueError(f"No text extracted from '{filename}'")

    logger.info("Parsed %d characters from '%s'", len(text), filename)

    # ── Step 2: Chunk ─────────────────────────────────────────────────────────
    chunks = chunk_text(text)
    if not chunks:
        raise ValueError(f"Chunking produced no chunks for '{filename}'")

    logger.info("Produced %d chunks", len(chunks))

    # ── Step 3: Embed ─────────────────────────────────────────────────────────
    embedder = get_embedder()
    vectors = embedder.embed_batch(chunks)

    # ── Step 4: Add to FAISS index ────────────────────────────────────────────
    store = get_vector_store(department)
    faiss_ids = store.add_vectors(vectors)
    store.save()

    # ── Step 5: Persist to SQLite ─────────────────────────────────────────────
    doc = models.Document(
        department=department,
        filename=filename,
        source_type=source_type,
        chunk_count=len(chunks),
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    chunk_rows = [
        models.Chunk(
            document_id=doc.id,
            department=department,
            chunk_index=i,
            chunk_text=text,
            faiss_id=fid,
        )
        for i, (text, fid) in enumerate(zip(chunks, faiss_ids))
    ]
    db.add_all(chunk_rows)
    db.commit()

    logger.info(
        "Ingestion complete | doc_id=%d | dept=%s | chunks=%d",
        doc.id, department, len(chunks),
    )
    return doc


def rebuild_faiss_index(department: str, db: DBSession) -> int:
    """
    Rebuild the FAISS index for a department from SQLite chunk data.

    Called after document deletion to keep the FAISS index consistent
    with the chunks table.  Re-embeds all remaining chunks for the department.

    Args:
        department: Department whose index should be rebuilt.
        db:         Active SQLAlchemy session.

    Returns:
        Number of vectors in the rebuilt index.
    """
    logger.info("Rebuilding FAISS index for department: %s", department)

    chunks = (
        db.query(models.Chunk)
        .filter(models.Chunk.department == department)
        .order_by(models.Chunk.id.asc())
        .all()
    )

    # Reset (clear) the index before rebuilding.
    store = get_vector_store(department)
    store.reset()

    if not chunks:
        logger.info("No chunks remain for '%s' — index left empty", department)
        return 0

    texts = [c.chunk_text for c in chunks]
    embedder = get_embedder()
    vectors = embedder.embed_batch(texts)
    new_faiss_ids = store.add_vectors(vectors)
    store.save()

    # Update faiss_id on each chunk row to match the new index positions.
    for chunk, new_fid in zip(chunks, new_faiss_ids):
        chunk.faiss_id = new_fid
    db.commit()

    logger.info(
        "Index rebuild complete for '%s': %d vectors", department, len(new_faiss_ids)
    )
    return len(new_faiss_ids)
