# Phase 9 — Polish + Production Hardening

## Concepts Learned

### FastAPI Lifespan (startup + shutdown)
The modern way to run code at server start/stop is the `lifespan` context manager
(FastAPI 0.93+). It replaces the deprecated `@app.on_event("startup")` decorators:

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup code here
    load_resources()
    yield          # ← server runs, handling requests
    # Shutdown code here (runs even on SIGINT/SIGTERM)
    save_and_cleanup()

app = FastAPI(lifespan=lifespan)
```

We use the lifespan to:
- **Startup**: Create DB tables, pre-load all FAISS indexes from disk
- **Shutdown**: Save all in-memory FAISS indexes to disk before the process exits

### FAISS Save on Shutdown
`IndexFlatIP` stores vectors in RAM. Without a save-on-shutdown, any vectors added
during the session (from document uploads) would be lost on restart. The new
`save_all_stores()` function iterates the `_stores` dict and calls `store.save()`
for every department that has loaded vectors.

### Global Exception Handlers
Without them, any unhandled Python exception returns a raw 500 response that may
expose stack traces or internal details. We register two handlers:

```python
@app.exception_handler(RequestValidationError)
async def validation_handler(request, exc):
    return JSONResponse(422, {"detail": exc.errors()})

@app.exception_handler(Exception)
async def global_handler(request, exc):
    logger.error("...", exc_info=True)   # full traceback in logs
    return JSONResponse(500, {"detail": "An internal server error occurred."})
```

The global handler logs the full traceback (so developers can debug) while
returning only a safe generic message to clients.

### Rate Limiting with slowapi
`slowapi` wraps the `limits` library and integrates with FastAPI via dependency
injection. Key design decisions:

**Separate module to avoid circular imports:**
`main.py` imports `chat/router.py`, which would need to import the `Limiter`
from `main.py` — a circular import. We solve this by putting the `Limiter`
singleton in `core/rate_limit.py`, imported by both.

```python
# core/rate_limit.py
from slowapi import Limiter
from slowapi.util import get_remote_address
limiter = Limiter(key_func=get_remote_address, default_limits=[])
```

**Applying the limit** (endpoint must accept `Request`):
```python
@router.post("/message")
@limiter.limit(settings.RATE_LIMIT_CHAT)   # "20/minute" from config
def message(request: Request, body: MessageRequest, ...):
    ...
```

**Attaching to app:**
```python
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
```

### Enhanced /health Endpoint
A robust health endpoint checks all dependencies, not just that the process is alive:

```python
@app.get("/health")
def health():
    db_ok     = check_db()      # SELECT 1
    ollama_ok = check_ollama()  # GET /api/tags with timeout=3s
    return {
        "status": "ok" if (db_ok and ollama_ok) else "degraded",
        "db":     "ok" if db_ok     else "error",
        "ollama": "ok" if ollama_ok else "error",
        "phase":  9,
    }
```

Return `"degraded"` (not 500) so load balancers can distinguish "process is up
but a dependency is unavailable" from "process is completely dead".

### Consistent Error Response Shape
All API errors now have the same JSON shape:
```json
{ "detail": "Human-readable message or structured validation errors" }
```

This makes the mobile app's error handling trivial — always parse `err.response.data.detail`.

---

## What Was Built

### `backend/ingestion/vector_store.py` (updated)
Added `save_all_stores()`:
```python
def save_all_stores() -> None:
    for dept, store in _stores.items():
        if store.index is not None and store.index.ntotal > 0:
            store.save()
```

### `backend/core/config.py` (updated)
Added rate limit setting:
```python
RATE_LIMIT_CHAT: str = "20/minute"
```

### `backend/core/rate_limit.py` (new)
Shared `Limiter` singleton to avoid circular imports:
```python
limiter = Limiter(key_func=get_remote_address, default_limits=[])
```

### `backend/main.py` (rewritten)
- `lifespan` context manager for startup (DB init + FAISS load) and shutdown (FAISS save)
- `app.state.limiter = limiter` + `RateLimitExceeded` exception handler
- `global_exception_handler` — catches all unhandled exceptions, logs traceback
- `validation_exception_handler` — 422 with structured Pydantic errors
- Enhanced `/health` checking DB connectivity (SELECT 1) and Ollama (`/api/tags`)
- Version bumped to `"0.9.0"`

### `backend/chat/router.py` (updated)
- Fixed missing `DEPARTMENT_DESCRIPTIONS` import from `router_agent`
- `request: Request` parameter added to `/chat/message`
- `@limiter.limit(settings.RATE_LIMIT_CHAT)` decorator on `/chat/message`

---

## File Checklist

| File | Status |
|---|---|
| `backend/ingestion/vector_store.py` | ✅ Updated — save_all_stores() |
| `backend/core/config.py` | ✅ Updated — RATE_LIMIT_CHAT setting |
| `backend/core/rate_limit.py` | ✅ New — shared Limiter singleton |
| `backend/main.py` | ✅ Rewritten — lifespan, handlers, /health |
| `backend/chat/router.py` | ✅ Updated — rate limit + import fix |

**Import check:** `python -c "import main; print('OK')"` → OK.

---

## How to Test

**Rate limiting:**
```bash
# Send 21 rapid requests — the 21st should return 429 Too Many Requests
for i in $(seq 1 21); do curl -s -o /dev/null -w "%{http_code}\n" \
  -X POST http://localhost:8000/chat/message \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"message": "test"}'; done
```

**Health check:**
```bash
curl http://localhost:8000/health
# {"status": "ok", "db": "ok", "ollama": "ok", "phase": 9}
```

**FAISS persistence:**
1. Upload a document (Phase 5/8 admin panel)
2. Restart the server — no re-ingestion needed
3. Query the same department — answer still grounded in the uploaded document

---

## .env Configuration Reference

| Variable | Default | Notes |
|---|---|---|
| `SECRET_KEY` | (change this!) | JWT signing key — use a long random string in production |
| `ALGORITHM` | `HS256` | JWT algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | Token lifetime |
| `DATABASE_URL` | `sqlite:///./chatbot.db` | SQLite file path |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `gpt-oss:120b-cloud` | Model name (must exist in `ollama list`) |
| `RATE_LIMIT_CHAT` | `20/minute` | Rate limit for `/chat/message` per IP |
