"""
db/models.py
------------
PURPOSE:
    Defines all SQLAlchemy ORM models (database tables).
    Each Python class here maps to one table in chatbot.db.

CONCEPT — ORM Models:
    A class that inherits from `Base` and has `__tablename__` is an ORM model.
    Each `Column(...)` declaration becomes a database column.
    SQLAlchemy reads these class definitions when `Base.metadata.create_all()`
    is called and issues the correct CREATE TABLE IF NOT EXISTS SQL statements.

CONCEPT — Why store role and department as plain strings?
    We define enums in Python for type safety and IDE autocomplete, but store
    their string values in SQLite. SQLite has no native ENUM type, and storing
    strings keeps the data human-readable when you inspect the DB file directly.

CONCEPT — Relationship between Document and Chunk (Phase 2):
    One Document row → many Chunk rows (one per text segment).
    Each Chunk stores the raw text AND the integer FAISS ID so we can map
    FAISS search results back to human-readable text.

TABLES:
    users     — registered user accounts (Phase 1)
    documents — uploaded policy files, one row per file (Phase 2)
    chunks    — text segments from documents, linked to FAISS IDs (Phase 2)

FUTURE TABLES (added in later phases):
    sessions, messages
"""

import enum
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from .database import Base


class UserRole(str, enum.Enum):
    """
    Roles control what a user can do in the system.
      user  — can chat with department agents
      admin — can also upload/delete documents via the admin panel
    """
    user = "user"
    admin = "admin"


class Department(str, enum.Enum):
    """
    Each value matches one department agent and one FAISS vector index.
    `general` is the default when a user has not been assigned a department.
    The router agent still routes their messages correctly regardless of this field.
    """
    hr = "hr"
    it = "it"
    finance = "finance"
    legal = "legal"
    admin = "admin"
    general = "general"


class User(Base):
    """
    Represents one registered user account.

    Columns:
        id              — auto-incrementing primary key
        email           — unique login identifier; indexed for fast lookups
        hashed_password — bcrypt hash; the plaintext password is NEVER stored
        full_name       — display name shown in the mobile app
        role            — 'user' or 'admin' (see UserRole enum)
        department      — default department hint for the routing agent
        created_at      — UTC timestamp of account creation
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)

    # Stored as the string value of the enum (e.g. "admin", "user").
    role = Column(String, default=UserRole.user)
    department = Column(String, default=Department.general)

    # timezone.utc produces a timezone-aware datetime; avoids ambiguity
    # when the server and database are in different timezones.
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ── Phase 2 Models ────────────────────────────────────────────────────────────

class Document(Base):
    """
    Represents one uploaded source document (PDF, DOCX, TXT, or URL).

    When a document is uploaded, it is:
      1. Parsed into plain text (ingestion/parsers.py)
      2. Split into chunks (ingestion/chunker.py)
      3. Each chunk embedded and stored in FAISS (ingestion/embedder.py + vector_store.py)
      4. This Document row created, with chunk_count recording how many chunks were made

    Columns:
        id          — auto-incrementing primary key
        department  — which department's FAISS index this doc belongs to
        filename    — original filename or URL; shown in the admin panel
        source_type — 'pdf', 'docx', 'txt', 'md', or 'url'
        chunk_count — number of text chunks ingested from this document
        uploaded_at — UTC timestamp of ingestion
        chunks      — SQLAlchemy relationship to the Chunk rows for this doc
    """
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    department = Column(String, nullable=False, index=True)
    filename = Column(String, nullable=False)
    source_type = Column(String, nullable=False)   # 'pdf', 'docx', 'txt', 'md', 'url'
    chunk_count = Column(Integer, default=0)
    uploaded_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # SQLAlchemy relationship: document.chunks gives all Chunk objects for this doc.
    # cascade="all, delete-orphan" means deleting a Document also deletes its chunks.
    chunks = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")


class Chunk(Base):
    """
    Represents one text segment extracted from a Document.

    Each Chunk has two parallel identifiers:
      - id (SQLite PK)  — used internally in SQL queries
      - faiss_id        — the integer index in the FAISS vector array

    At query time:
      1. FAISS search returns faiss_ids with similarity scores
      2. We query: SELECT * FROM chunks WHERE department=? AND faiss_id IN (?)
      3. Return chunk_text to the LLM as context

    Columns:
        id          — auto-incrementing SQLite primary key
        document_id — FK to the parent Document row
        department  — duplicated here for fast filtering (avoids JOIN)
        chunk_index — position of this chunk within its document (0-based)
        chunk_text  — the raw text of this segment (sent to the LLM as context)
        faiss_id    — integer ID in the department's FAISS index
    """
    __tablename__ = "chunks"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False, index=True)

    # department is denormalised (also on Document) for fast lookup without JOIN.
    department = Column(String, nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)   # 0-based position in document
    chunk_text = Column(Text, nullable=False)        # Text = unbounded String in SQLite
    faiss_id = Column(Integer, nullable=False, index=True)

    # Back-reference to parent Document.
    document = relationship("Document", back_populates="chunks")


# ── Phase 3 Models ────────────────────────────────────────────────────────────

class Session(Base):
    """
    Represents one conversation between a user and a department agent.

    A new Session is created when:
      - The user opens a chat screen for a department (explicit), OR
      - The primary router sends the first message to a department (implicit)

    A Session groups all messages so the query engine can inject recent
    conversation history into the LLM prompt for follow-up question support.

    Columns:
        id          — auto-incrementing primary key
        user_id     — FK to the User who owns this session
        department  — which department agent this session is with
        created_at  — UTC timestamp when the session started
        messages    — relationship to all Message rows in this session
    """
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    department = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    messages = relationship("Message", back_populates="session", cascade="all, delete-orphan")


class Message(Base):
    """
    Represents one turn (user or assistant) in a chat session.

    Both user messages and LLM responses are stored here so we can:
      1. Show chat history in the mobile app
      2. Inject recent turns into the LLM prompt for follow-up questions
      3. Audit what the bot said

    Columns:
        id          — auto-incrementing primary key
        session_id  — FK to the parent Session
        role        — 'user' or 'assistant' (matches OpenAI/Ollama message roles)
        content     — the full text of the message
        created_at  — UTC timestamp (used to order messages chronologically)
    """
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False, index=True)

    # 'user' or 'assistant' — intentionally matches the Ollama/OpenAI role names
    # so messages can be passed directly to the chat API without transformation.
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    session = relationship("Session", back_populates="messages")
