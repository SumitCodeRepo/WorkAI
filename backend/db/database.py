"""
db/database.py
--------------
PURPOSE:
    Creates and exposes the SQLAlchemy engine, session factory, and ORM base
    class used by every database model in the project.

CONCEPT — SQLAlchemy ORM:
    SQLAlchemy lets you map Python classes to database tables.
    Instead of writing raw SQL, you work with Python objects and SQLAlchemy
    translates them to SQL behind the scenes.

    Key pieces:
      engine        — the database connection (knows the DB file path)
      SessionLocal  — a factory that produces short-lived DB sessions
      Base          — parent class all ORM model classes inherit from
      get_db()      — FastAPI dependency that opens a session per request
                      and guarantees it is closed even if an error occurs

CONCEPT — SQLite `check_same_thread=False`:
    SQLite normally raises an error if the same connection is used from
    multiple threads. FastAPI runs async handlers in a thread pool, so we
    must disable that check. SQLAlchemy's session-per-request pattern keeps
    this safe — each request gets its own session object.

USAGE:
    # In a route:
    from db.database import get_db
    def my_route(db: Session = Depends(get_db)):
        ...
"""

import logging
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker
from core.logging_config import get_logger

logger = get_logger(__name__)

# SQLite stores the entire database in a single file (chatbot.db) in the
# directory where uvicorn is started (backend/).
SQLALCHEMY_DATABASE_URL = "sqlite:///./chatbot.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    # Required for SQLite + FastAPI thread model (see module docstring).
    connect_args={"check_same_thread": False},
)

# autocommit=False  — changes are only written when session.commit() is called,
#                     giving us transaction control.
# autoflush=False   — prevents SQLAlchemy from issuing SQL between operations
#                     unexpectedly; we flush manually when needed.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# All ORM model classes inherit from Base so SQLAlchemy knows about them
# when Base.metadata.create_all() is called at startup.
Base = declarative_base()


@event.listens_for(engine, "connect")
def _on_connect(dbapi_connection, connection_record):
    """Enable WAL mode on every new SQLite connection for better concurrency."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()
    logger.debug("SQLite WAL mode enabled on new connection")


def get_db():
    """
    FastAPI dependency that provides a database session for one request.

    Usage in a route:
        def my_route(db: Session = Depends(get_db)):

    The `try/finally` guarantees the session is always closed, even when the
    route raises an exception — preventing connection leaks.
    """
    db = SessionLocal()
    logger.debug("Database session opened")
    try:
        yield db
    finally:
        db.close()
        logger.debug("Database session closed")
