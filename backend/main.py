"""
main.py
-------
PURPOSE:
    Entry point for the FastAPI application.
    Responsibilities:
      1. Database table creation on first start (SQLAlchemy).
      2. FAISS index pre-loading on startup, save on shutdown (lifespan).
      3. CORS middleware for the mobile app.
      4. Rate limiting via slowapi (20 req/min on /chat/message by default).
      5. Global exception handlers for consistent error response shape.
      6. Mounting all API routers.
      7. Enhanced /health endpoint checking DB + Ollama connectivity.

CONCEPT — FastAPI Lifespan (startup + shutdown events)
    The modern way to run code at server start/stop is the lifespan context
    manager (FastAPI 0.93+). It replaces the deprecated @app.on_event decorators:

        @asynccontextmanager
        async def lifespan(app):
            # --- startup ---
            load_resources()
            yield
            # --- shutdown ---
            save_and_cleanup()

    This guarantees cleanup runs even when the server is killed with SIGINT/SIGTERM.

CONCEPT — Global Exception Handlers
    Without a global handler, unhandled Python exceptions return a raw 500
    response with a stack trace — leaking internal details to clients.
    We register two handlers:
      - Exception          → generic 500 with a safe message (details in logs)
      - RequestValidationError → 422 with structured field errors (Pydantic)

CONCEPT — Rate Limiting (slowapi)
    slowapi wraps the limits library and integrates with FastAPI's dependency
    injection. It tracks request counts per key (default: client IP) in memory.
    We apply it only to the expensive /chat/message endpoint.

CONCEPT — Health Check
    A /health endpoint that returns 200 + a JSON payload is essential for:
      - Load balancers (decide whether to route traffic to this instance)
      - Monitoring tools (alert when DB or Ollama is unreachable)
      - The mobile app (show a "server offline" message on startup)

HOW TO START THE SERVER (run from the backend/ folder):
    Windows:  ..\\RAG_VENV\\Scripts\\python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
    Mac/Linux: ../RAG_VENV/bin/python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000

    API docs: http://localhost:8000/docs
"""

from contextlib import asynccontextmanager

import requests as http_requests
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from core.config import settings
from core.logging_config import get_logger
from core.rate_limit import limiter
from db.database import SessionLocal, engine, Base
from auth.router import router as auth_router
from chat.router import router as chat_router
from admin.router import router as admin_router
from ingestion.vector_store import load_all_stores, save_all_stores

logger = get_logger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic for the FastAPI application."""
    # ── Startup ──────────────────────────────────────────────────────────────
    logger.info("Starting Enterprise AI Chatbot API...")

    # Create all SQLite tables (safe to call repeatedly — CREATE TABLE IF NOT EXISTS).
    logger.info("Initialising database tables...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables ready")

    # Pre-load all FAISS indexes so the first query to any department is fast.
    load_all_stores()

    logger.info("Enterprise AI Chatbot API ready — http://localhost:8000/docs")

    yield  # ← application runs here

    # ── Shutdown ─────────────────────────────────────────────────────────────
    logger.info("Shutting down — saving FAISS indexes...")
    save_all_stores()
    logger.info("Shutdown complete")


# ── Application instance ──────────────────────────────────────────────────────
app = FastAPI(
    title="Enterprise AI Chatbot",
    description=(
        "Multi-agent, department-aware RAG chatbot API. "
        "Departments: HR, IT, Finance, Legal, Admin."
    ),
    version="0.9.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Attach the rate limiter to app state (required by slowapi).
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ── Middleware ────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # replace with specific origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Global exception handlers ─────────────────────────────────────────────────

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """
    Return a 422 with structured field errors instead of FastAPI's default format.
    This gives the mobile app a consistent shape to parse.
    """
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()},
    )


@app.exception_handler(Exception)
async def global_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """
    Catch-all for any unhandled exception.

    Logs the full stack trace server-side but returns only a safe generic
    message to the client (no internal details, no stack traces in responses).
    """
    logger.error(
        "Unhandled exception: %s %s → %s",
        request.method, request.url, exc,
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred. Please try again later."},
    )


# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(admin_router)


# ── System endpoints ──────────────────────────────────────────────────────────

@app.get("/health", tags=["System"], summary="Enhanced server health check")
def health():
    """
    Returns status of the server, SQLite database, and Ollama LLM server.

    Status values:
        "ok"       — all systems operational
        "degraded" — server is running but a dependency is unreachable

    Used by monitoring tools and the mobile app to verify connectivity.
    """
    # ── Database check ────────────────────────────────────────────────────────
    db_ok = False
    try:
        logger.info("HEALTH CHECK: Verifying database connectivity...")

        db = SessionLocal()
        db.execute(__import__("sqlalchemy").text("SELECT 1"))
        db.close()
        db_ok = True
    except Exception as exc:
        logger.warning("Health check: DB unreachable — %s", exc)

    # ── Ollama check ──────────────────────────────────────────────────────────
    ollama_ok = False
    try:
        resp = http_requests.get(
            f"{settings.OLLAMA_BASE_URL}/api/tags",
            timeout=3,
        )
        ollama_ok = resp.status_code == 200
    except Exception as exc:
        logger.warning("Health check: Ollama unreachable — %s", exc)

    overall = "ok" if (db_ok and ollama_ok) else "degraded"

    logger.debug("Health check: status=%s db=%s ollama=%s", overall, db_ok, ollama_ok)

    return {
        "status": overall,
        "db":     "ok" if db_ok     else "error",
        "ollama": "ok" if ollama_ok else "error",
        "phase":  9,
    }
