"""
admin/router.py
---------------
PURPOSE:
    Admin-only HTTP endpoints for managing the policy documents that power
    each department's RAG knowledge base.

    These endpoints let an admin user upload PDFs/DOCX/TXT files (or URLs)
    to a department, list what's been uploaded, and delete documents.

CONCEPT — File Upload in FastAPI
    HTTP file uploads use the multipart/form-data encoding.  FastAPI handles
    this with two special types:
        UploadFile  — async file handle (content read with await file.read())
        Form(...)   — for non-file form fields sent in the same multipart body

    Example curl:
        curl -X POST /admin/documents/upload \
             -H "Authorization: Bearer <token>" \
             -F "file=@policy.pdf" \
             -F "department=hr"

CONCEPT — BackgroundTasks
    Document ingestion (parse → chunk → embed → FAISS) can take 5–30 seconds
    for a large PDF.  Blocking the HTTP response for that long is poor UX.

    FastAPI's BackgroundTask mechanism lets us:
      1. Save the uploaded file to disk
      2. Return 202 Accepted immediately
      3. Run the embedding pipeline AFTER the response is sent

    The client polls GET /admin/documents to see when the doc appears.

    Under the hood, BackgroundTasks runs in the same process event loop after
    the response is flushed — so it's NOT truly concurrent with other requests
    during a long embedding job.  For production you'd use Celery or ARQ.

CONCEPT — RBAC (Role-Based Access Control)
    The `require_admin` dependency from core/security.py extends get_current_user
    with a role check.  Any route that Depends(require_admin) will return 403
    if the caller is not an admin.  Regular user routes use get_current_user.

    This means we share the same JWT infrastructure but gate sensitive routes
    behind a second check — without any middleware or separate auth flow.

ENDPOINTS:
    POST   /admin/documents/upload      — upload file or URL, trigger ingestion
    GET    /admin/documents             — list documents (optional dept filter)
    DELETE /admin/documents/{id}        — delete document + rebuild FAISS index
    GET    /admin/documents/{id}/status — check whether ingestion is complete
"""

import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import (
    APIRouter, BackgroundTasks, Depends, File, Form,
    HTTPException, Query, UploadFile, status,
)
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session as DBSession

from core.logging_config import get_logger
from core.security import require_admin, get_current_user
from db.database import get_db, SessionLocal
from db import models
from ingestion.pipeline import ingest_document, rebuild_faiss_index

logger = get_logger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])

# Temp directory for uploaded files awaiting ingestion.
UPLOAD_TEMP_DIR = Path("temp") / "uploads"
UPLOAD_TEMP_DIR.mkdir(parents=True, exist_ok=True)

# Allowed file extensions for upload.
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}


# ── Background ingestion task ─────────────────────────────────────────────────

def _background_ingest(temp_path: str, department: str, filename: str, source_type: str) -> None:
    """
    Run full ingestion pipeline in a background task.

    Opens its own DB session (the request session is closed by the time
    BackgroundTasks fires) and cleans up the temp file when done.

    Args:
        temp_path:   Path to the saved upload file.
        department:  Target department.
        filename:    Original filename (displayed in document list).
        source_type: File type string (pdf, docx, txt).
    """
    db = SessionLocal()
    try:
        ingest_document(
            source=temp_path,
            department=department,
            db=db,
            filename=filename,
            source_type=source_type,
        )
        logger.info("Background ingestion complete: %s -> %s", filename, department)
    except Exception as exc:
        logger.error(
            "Background ingestion failed for '%s': %s", filename, exc, exc_info=True
        )
    finally:
        db.close()
        # Remove temp file regardless of success or failure.
        try:
            os.remove(temp_path)
        except OSError:
            pass


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post(
    "/documents/upload",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a policy document and trigger background ingestion",
)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: Optional[UploadFile] = File(default=None),
    url: Optional[str] = Form(default=None),
    department: str = Form(...),
    current_user: models.User = Depends(require_admin),
    db: DBSession = Depends(get_db),
):
    """
    Upload a file (PDF, DOCX, TXT/MD) or provide a URL for ingestion.

    One of `file` or `url` must be provided; `department` is always required.

    The endpoint returns 202 Accepted immediately.  The actual parsing,
    chunking, embedding, and FAISS indexing runs as a background task.
    Poll GET /admin/documents to see the document once ingestion completes.

    Raises:
        400 if neither file nor url is provided.
        400 if the file extension is not allowed.
        400 if the department is not recognised.
    """
    # ── Validate department ───────────────────────────────────────────────────
    valid_departments = [d.value for d in models.Department if d.value != "general"]
    if department not in valid_departments:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown department '{department}'. Valid: {valid_departments}",
        )

    # ── Handle URL ingestion ──────────────────────────────────────────────────
    if url:
        if not url.startswith(("http://", "https://")):
            raise HTTPException(
                status_code=400, detail="URL must start with http:// or https://"
            )
        logger.info(
            "URL ingestion queued | dept=%s | url=%s | admin=%s",
            department, url, current_user.email,
        )
        # For URLs we ingest synchronously in the background (no temp file needed).
        background_tasks.add_task(
            _background_ingest,
            temp_path=url,
            department=department,
            filename=url,
            source_type="url",
        )
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={"detail": "URL queued for ingestion", "url": url, "department": department},
        )

    # ── Handle file upload ────────────────────────────────────────────────────
    if file is None:
        raise HTTPException(
            status_code=400, detail="Provide either 'file' (upload) or 'url' (web page)."
        )

    original_name = file.filename or "upload"
    ext = Path(original_name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' not allowed. Supported: {sorted(ALLOWED_EXTENSIONS)}",
        )

    source_type = ext.lstrip(".")
    if source_type == "md":
        source_type = "txt"

    # Save to temp file so the background task can access it after the request ends.
    # NamedTemporaryFile with delete=False gives us a path we manage ourselves.
    fd, temp_path = tempfile.mkstemp(suffix=ext, dir=UPLOAD_TEMP_DIR)
    try:
        with os.fdopen(fd, "wb") as tmp:
            content = await file.read()
            tmp.write(content)
    except Exception as exc:
        os.remove(temp_path)
        raise HTTPException(status_code=500, detail=f"Failed to save upload: {exc}") from exc

    logger.info(
        "File upload received | dept=%s | file=%s | size=%d bytes | admin=%s",
        department, original_name, len(content), current_user.email,
    )

    background_tasks.add_task(
        _background_ingest,
        temp_path=temp_path,
        department=department,
        filename=original_name,
        source_type=source_type,
    )

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "detail": "File queued for ingestion",
            "filename": original_name,
            "department": department,
        },
    )


@router.get(
    "/documents",
    summary="List uploaded documents with optional department filter",
)
def list_documents(
    department: Optional[str] = Query(default=None, description="Filter by department"),
    current_user: models.User = Depends(require_admin),
    db: DBSession = Depends(get_db),
):
    """
    Return all documents, optionally filtered to a single department.

    Each document includes its id, filename, department, source type,
    chunk count, and upload timestamp.

    Args:
        department: Optional query param to restrict results (e.g. ?department=hr).
    """
    query = db.query(models.Document)
    if department:
        query = query.filter(models.Document.department == department)
    docs = query.order_by(models.Document.uploaded_at.desc()).all()

    logger.debug(
        "Document list fetched | dept_filter=%s | count=%d | admin=%s",
        department, len(docs), current_user.email,
    )

    return [
        {
            "id": d.id,
            "filename": d.filename,
            "department": d.department,
            "source_type": d.source_type,
            "chunk_count": d.chunk_count,
            "uploaded_at": d.uploaded_at.isoformat(),
        }
        for d in docs
    ]


@router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a document and rebuild the FAISS index",
)
def delete_document(
    document_id: int,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(require_admin),
    db: DBSession = Depends(get_db),
):
    """
    Delete a document and its chunks, then rebuild the department FAISS index.

    Deleting a document means its embedded vectors are no longer meaningful.
    Rather than trying to surgically remove individual FAISS vectors (FAISS
    IndexFlatIP does not support deletion), we rebuild the entire index from
    the remaining chunks in SQLite.

    The delete is synchronous (fast — just DB rows).  The index rebuild is
    queued as a background task because it requires re-embedding all remaining
    chunks, which can be slow for large departments.

    Raises:
        404 if the document ID doesn't exist.
    """
    doc = db.get(models.Document, document_id)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found",
        )

    department = doc.department
    filename = doc.filename

    # SQLAlchemy cascade deletes the Chunk rows automatically (see models.py).
    db.delete(doc)
    db.commit()

    logger.info(
        "Document deleted | doc_id=%d | dept=%s | file=%s | admin=%s",
        document_id, department, filename, current_user.email,
    )

    # Rebuild FAISS index in the background.
    background_tasks.add_task(_rebuild_index_task, department=department)

    return {
        "detail": f"Document '{filename}' deleted. FAISS index for '{department}' is rebuilding.",
        "document_id": document_id,
        "department": department,
    }


def _rebuild_index_task(department: str) -> None:
    """Background wrapper for rebuild_faiss_index — opens its own DB session."""
    db = SessionLocal()
    try:
        count = rebuild_faiss_index(department, db)
        logger.info("Index rebuild complete for '%s': %d vectors", department, count)
    except Exception as exc:
        logger.error("Index rebuild failed for '%s': %s", department, exc, exc_info=True)
    finally:
        db.close()


@router.get(
    "/documents/{document_id}",
    summary="Get details for a single document",
)
def get_document(
    document_id: int,
    current_user: models.User = Depends(require_admin),
    db: DBSession = Depends(get_db),
):
    """
    Return metadata for a single document.

    Useful for the mobile admin panel to show chunk count after ingestion completes.

    Raises:
        404 if not found.
    """
    doc = db.get(models.Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found")

    return {
        "id": doc.id,
        "filename": doc.filename,
        "department": doc.department,
        "source_type": doc.source_type,
        "chunk_count": doc.chunk_count,
        "uploaded_at": doc.uploaded_at.isoformat(),
    }
