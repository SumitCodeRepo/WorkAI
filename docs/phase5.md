# Phase 5 — Admin Document Management API

## Concept to Learn

### 1. File Upload in FastAPI (`UploadFile` + `Form`)

HTTP file uploads use **multipart/form-data** encoding — a single request body that
contains both binary file content and text form fields separated by a boundary string.

FastAPI handles this with two special types imported from `fastapi`:

```python
from fastapi import File, Form, UploadFile

async def upload(
    file: UploadFile = File(default=None),   # binary file content
    department: str  = Form(...),            # text field in the same request
):
    content = await file.read()   # async read — required because UploadFile is async
```

Key points:
- `UploadFile` has `.filename`, `.content_type`, `.read()` (async), `.seek()`, `.close()`
- `Form(...)` means the field is required; `Form(default=None)` makes it optional
- The endpoint function **must be `async def`** to use `await file.read()`
- You cannot use `response_model` with multipart endpoints that return `JSONResponse`

Example curl:
```bash
curl -X POST http://localhost:8000/admin/documents/upload \
     -H "Authorization: Bearer <token>" \
     -F "file=@hr_policy.pdf" \
     -F "department=hr"
```

### 2. FastAPI `BackgroundTasks`

Embedding a large PDF takes 5–30 seconds.  Blocking the HTTP response that long
is poor UX. FastAPI's `BackgroundTasks` mechanism solves this:

```
Client → POST /upload
            ↓
      Save file to disk          (sync, fast, ~10ms)
      Schedule background task   (instant)
            ↓
      Return 202 Accepted  ←──── Client gets response immediately
            |
      [after response is flushed]
            ↓
      parse → chunk → embed → FAISS → SQLite  (slow, 5–30s)
```

Usage:

```python
from fastapi import BackgroundTasks

def my_endpoint(background_tasks: BackgroundTasks):
    background_tasks.add_task(my_function, arg1, arg2)
    return {"detail": "processing started"}
```

**Important limitation:** `BackgroundTasks` runs in the same process/event loop. During a long
embedding job, other requests are not blocked (uvicorn handles them in other threads/workers),
but there is no queue, retry, or failure notification mechanism built in.  For production
at scale, use Celery + Redis or ARQ instead.

**DB session in background tasks:** The request's DB session is closed when the response is
sent.  Background tasks must open their own `SessionLocal()` session and close it in a
`finally` block.

### 3. FAISS Persistence

FAISS indexes are held in memory for fast search.  They must be saved to disk so they
survive a server restart.

```python
import faiss

# Save
faiss.write_index(index, "/path/to/index.faiss")

# Load
index = faiss.read_index("/path/to/index.faiss")
```

The `VectorStore.save()` method (Phase 2) uses an atomic write: it writes to a temp file
then calls `Path.replace()` so a crash mid-write never leaves a corrupt index file.

At startup, `load_all_stores()` pre-loads all 5 department indexes from disk.  If no
file exists yet (department has no documents), a fresh empty `IndexFlatIP` is created.

**Why there is no FAISS vector deletion:**

`IndexFlatIP` is an exhaustive flat index — it stores all vectors in a contiguous array.
Removing a single vector from the middle would shift all subsequent IDs and invalidate
every `faiss_id` stored in SQLite.

The solution used here: when a document is deleted, **rebuild the entire index** from
the remaining chunks in SQLite.  This re-embeds every remaining chunk and assigns new
contiguous IDs, then updates `faiss_id` in every Chunk row.

### 4. Role-Based Access Control (RBAC)

The `require_admin` dependency (built in Phase 1's `core/security.py`) extends
`get_current_user` with a role check:

```python
def require_admin(
    current_user: models.User = Depends(get_current_user),
) -> models.User:
    if current_user.role != models.UserRole.admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user
```

Any route that uses `Depends(require_admin)` will:
- Return 401 if no JWT token is provided
- Return 403 if the user exists but is not an admin
- Return the `User` object if the user is an authenticated admin

The same JWT infrastructure is reused — no separate admin login is needed.

### 5. Pipeline Pattern

Phases 2–3 built each ingestion step as a standalone module so concepts could be
learned in isolation.  Phase 5 adds `ingestion/pipeline.py` as an **orchestrator**
that wires the steps together in one function call:

```
ingest_document(source, department, db)
    ├── parse_document(source)          ← parsers.py
    ├── chunk_text(text)                ← chunker.py
    ├── embedder.embed_batch(chunks)    ← embedder.py
    ├── store.add_vectors(vectors)      ← vector_store.py
    └── SQLite: Document + Chunk rows   ← models.py
```

Benefits of the orchestrator pattern:
- HTTP endpoint stays thin (one function call)
- Background tasks and test scripts share the same logic
- One place to add retry / error handling later

---

## What Was Built

### Files Created / Modified

| File | Status | Description |
|---|---|---|
| `backend/ingestion/pipeline.py` | **New** | Orchestrates full ingest + FAISS rebuild |
| `backend/admin/__init__.py` | **New** | Package marker |
| `backend/admin/router.py` | **New** | Upload, list, delete, get endpoints |
| `backend/main.py` | Updated | Mounts `admin_router` |
| `backend/test_admin.py` | **New** | Three-test pipeline suite |
| `docs/phase5.md` | **New** | This document |

---

## File Deep-Dives

### `backend/ingestion/pipeline.py`

Two exported functions:

**`ingest_document(source, department, db, *, filename, source_type)`**
- Accepts a file path (str/Path) or URL
- Infers `source_type` from file extension if not provided
- Runs: parse → chunk → embed → FAISS add → SQLite Document + Chunk rows
- Returns the committed `Document` ORM object

**`rebuild_faiss_index(department, db)`**
- Queries all remaining `Chunk` rows for the department from SQLite
- Calls `store.reset()` to clear and recreate the empty index
- Re-embeds all chunk texts and adds them back
- Updates `faiss_id` on every Chunk row to match new positions
- Saves the rebuilt index to disk
- Returns the new vector count

### `backend/admin/router.py`

```
POST   /admin/documents/upload
    ├── Validates department + file extension
    ├── Saves UploadFile to temp/uploads/ (file) or passes URL directly
    ├── Returns 202 Accepted
    └── background_tasks: _background_ingest(temp_path, department, ...)
            ├── Opens own DB session
            ├── Calls ingest_document()
            └── Deletes temp file + closes session

GET    /admin/documents?department=hr
    └── SQLite query, returns list of document dicts

GET    /admin/documents/{id}
    └── Single document by ID (useful for polling after upload)

DELETE /admin/documents/{id}
    ├── Loads Document, raises 404 if missing
    ├── db.delete(doc) → cascade deletes Chunk rows
    ├── db.commit()
    ├── Returns 200 immediately
    └── background_tasks: _rebuild_index_task(department)
            └── Calls rebuild_faiss_index() with its own DB session
```

---

## API Reference

### `POST /admin/documents/upload`

**Auth:** JWT required, admin role required

**Form fields:**
- `department` (required): `hr`, `it`, `finance`, `legal`, `admin`
- `file` (optional): PDF, DOCX, TXT, or MD file
- `url` (optional): Web URL to scrape

One of `file` or `url` must be provided.

**Response (202):**
```json
{
  "detail": "File queued for ingestion",
  "filename": "hr_policy.pdf",
  "department": "hr"
}
```

### `GET /admin/documents`

**Auth:** JWT required, admin role required

**Query params:**
- `department` (optional): filter results

**Response (200):**
```json
[
  {
    "id": 1,
    "filename": "hr_policy.pdf",
    "department": "hr",
    "source_type": "pdf",
    "chunk_count": 23,
    "uploaded_at": "2026-05-20T12:00:00"
  }
]
```

### `DELETE /admin/documents/{id}`

**Auth:** JWT required, admin role required

**Response (200):**
```json
{
  "detail": "Document 'hr_policy.pdf' deleted. FAISS index for 'hr' is rebuilding.",
  "document_id": 1,
  "department": "hr"
}
```

---

## Test Results

```
Phase 5 Admin Document Management — Test Suite

TEST 1: ingest_document() — HR policy
  Document created: id=1  chunks=1
  SQLite chunk count verified: 1
  FAISS vector count: 1   PASSED

TEST 2: List documents + delete + cascade
  Ingested 'test_hr_policy.txt' (id=1, chunks=1)
  Ingested 'test_finance_policy.txt' (id=2, chunks=1)
  List verified: 2 documents total
  HR filter: 1 doc(s)   PASSED
  Delete + cascade verified: 1 chunks before, 0 after   PASSED

TEST 3: rebuild_faiss_index() after document deletion
  FAISS vectors before delete: 2
  FAISS vectors after rebuild: 1
  faiss_id consistency verified   PASSED
  Search on rebuilt index returned 1 result(s)   PASSED

ALL TESTS PASSED — Phase 5 admin pipeline is working
```

---

## Running the Test

```bash
cd backend/
..\RAG_VENV\Scripts\python test_admin.py
```

Log output: `temp/test_admin.log`

---

## Known Issues / Notes

- BackgroundTasks opens a new `SessionLocal()` because the request's DB session is
  closed by the time the background function runs.  Forgetting this causes
  `sqlalchemy.exc.InvalidRequestError: Session is closed`.
- FAISS `IndexFlatIP` does not support single-vector deletion.  The rebuild approach
  (re-embed all remaining chunks) is correct but O(n) in chunks for the department.
  For very large indexes (100k+ chunks), consider a background job queue instead of
  a BackgroundTask so the server isn't tied up re-embedding.
- The `temp/uploads/` directory is created at module import time.  On a fresh install,
  ensure `temp/` exists or the `UPLOAD_TEMP_DIR.mkdir(parents=True, exist_ok=True)`
  call will create it.
- URL ingestion is asynchronous: a URL is passed directly to `_background_ingest` as
  the `temp_path` argument.  The pipeline's `parse_document()` detects the `http://`
  prefix and routes to `parse_url()`.
