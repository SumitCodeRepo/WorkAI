# Phase 1 — Backend Foundation + JWT Authentication

## Overview

**Goal:** Stand up a fully working FastAPI backend with user registration, login, and
JWT-protected routes. This is the security and data layer every other phase builds on.

**What you built:**
- A Python FastAPI project with a clean folder structure
- SQLite database with a `users` table
- Email + password registration with bcrypt hashing
- Login endpoint that returns a signed JWT access token
- A protected `/auth/me` route that reads the token and returns the user
- Centralised logging so every module emits structured, timestamped log lines

---

## Concepts Covered

### 1. REST API + FastAPI

A **REST API** is a set of HTTP endpoints that a client (mobile app, browser) calls
to interact with the server. Each endpoint has a method (GET, POST, PUT, DELETE)
and a URL path.

**FastAPI** is a Python web framework that:
- Lets you define endpoints with decorators (`@app.get(...)`, `@app.post(...)`)
- Automatically validates request/response bodies using Pydantic
- Auto-generates interactive API docs at `/docs` (Swagger UI)
- Supports Python's `async/await` for high-concurrency workloads

```python
# Minimal FastAPI example
from fastapi import FastAPI
app = FastAPI()

@app.get("/hello")
def hello():
    return {"message": "Hello World"}
```

### 2. SQLite + SQLAlchemy ORM

**SQLite** stores the entire database in a single file (`chatbot.db`). No separate
database server is needed — perfect for development.

**SQLAlchemy ORM** lets you define database tables as Python classes:

```python
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True)
```

You then query with Python (`db.query(User).filter(...).first()`) instead of
raw SQL. SQLAlchemy translates this to `SELECT * FROM users WHERE ... LIMIT 1`.

**Key objects:**
| Object | Role |
|---|---|
| `engine` | Database connection (knows the file path) |
| `SessionLocal` | Factory that creates short-lived sessions |
| `Base` | Parent class all ORM models inherit from |
| `get_db()` | FastAPI dependency that opens/closes a session per request |

### 3. JWT (JSON Web Tokens)

A JWT has three parts separated by dots, each base64-encoded:

```
eyJhbGciOiJIUzI1NiJ9   ← Header  (algorithm: HS256)
.eyJzdWIiOiJ1c2VyQGV4YW1wbGUuY29tIiwiZXhwIjoxNjk5OTk5OTk5fQ==   ← Payload (claims)
.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c   ← Signature
```

The **payload** contains claims:
- `sub` (subject) — the user identifier (email)
- `exp` (expiry) — Unix timestamp after which the token is rejected

The **signature** is an HMAC-SHA256 hash of `header + payload` using `SECRET_KEY`.
The server never stores tokens — it verifies the signature on every request.

```
Login:    server creates token → client stores it
Request:  client sends "Authorization: Bearer <token>"
Server:   decodes token, verifies signature, extracts email, loads user from DB
```

### 4. bcrypt Password Hashing

Passwords are **never stored as plaintext**. bcrypt is used because:
- It is intentionally slow (configurable work factor) — brute-force attacks are impractical
- It generates a unique random **salt** for every hash — two identical passwords produce different hashes
- Verifying a password just requires calling `verify(plain, stored_hash)` — no decryption

```
"mypassword" → bcrypt → "$2b$12$eImiTXuWVxfM37uY4JANjOe5..." (stored)
```

### 5. Pydantic Schemas

Pydantic models validate incoming request data automatically:

```python
class RegisterRequest(BaseModel):
    email: EmailStr     # validates email format
    password: str       # must be present
    department: Department = Department.general   # must be a valid enum value
```

If the client sends `"email": "not-an-email"`, FastAPI returns a 422 error before
the route function even runs. This eliminates manual input validation code.

---

## File Map

```
backend/
├── main.py                  Application entry point
├── .env                     Environment variables (secrets, config)
│
├── core/
│   ├── config.py            Reads .env into a typed Settings object
│   ├── security.py          bcrypt hashing, JWT creation/validation, FastAPI dependencies
│   └── logging_config.py    Centralised logger factory used by all modules
│
├── db/
│   ├── database.py          SQLAlchemy engine, session factory, get_db()
│   └── models.py            ORM models: User table, UserRole enum, Department enum
│
└── auth/
    ├── schemas.py            Pydantic request/response models for auth endpoints
    └── router.py             POST /auth/register, POST /auth/login, GET /auth/me
```

---

## File-by-File Purpose

### `main.py`
**Purpose:** FastAPI application factory and startup.

Responsibilities:
- Calls `Base.metadata.create_all()` to ensure all DB tables exist before the first request
- Configures CORS so the React Native mobile app can reach the API
- Mounts all routers (auth in Phase 1, chat + admin in later phases)
- Exposes `GET /health` for monitoring

**Why it matters:** Every other part of the app flows through here at startup.
If something is broken at the application level, this is where you look first.

---

### `core/logging_config.py`
**Purpose:** Defines a single `get_logger(name)` function used by every module.

Responsibilities:
- Configures the root logger once with a consistent format and level
- Suppresses noisy third-party loggers (uvicorn, sqlalchemy, passlib)
- Returns named loggers so log lines show which module produced them

**Why it matters:** Without centralised logging, each module configures its own
logger differently, producing inconsistent output. One place to change the format
means all modules update at once.

**Log format:**
```
2024-01-15 10:23:45 | INFO     | auth.router | Login successful: id=1 email=alice@company.com role=user
```

---

### `core/config.py`
**Purpose:** Reads `.env` and exposes all configuration as a typed `settings` object.

Responsibilities:
- Defines all environment variable names and their default values
- Validates types at startup (a non-integer `ACCESS_TOKEN_EXPIRE_MINUTES` crashes immediately)
- Provides a single `settings` import used everywhere instead of `os.environ.get()`

**Why it matters:** Prevents configuration drift — if a variable is renamed in `.env`,
there is exactly one place to update in the codebase.

---

### `core/security.py`
**Purpose:** All authentication and authorisation logic.

Responsibilities:
- `hash_password / verify_password` — bcrypt wrappers
- `create_access_token` — builds and signs a JWT
- `get_current_user` — FastAPI dependency: decodes JWT → loads user from DB
- `require_admin` — extends `get_current_user` with role check

**Why it matters:** Security-sensitive code is intentionally isolated so it can be
audited in one file. No route should implement its own token decoding.

---

### `db/database.py`
**Purpose:** Database connection setup shared by all models and routes.

Responsibilities:
- Creates the SQLAlchemy engine (connection to `chatbot.db`)
- Defines `SessionLocal` (session factory)
- Defines `Base` (ORM model parent class)
- Provides `get_db()` FastAPI dependency
- Enables SQLite WAL mode for better read/write concurrency

**Why it matters:** Centralises the connection string. Changing from SQLite to
PostgreSQL in the future only requires updating this file and the `DATABASE_URL`.

---

### `db/models.py`
**Purpose:** Defines the `users` database table as a Python class.

Responsibilities:
- Declares `UserRole` and `Department` enums for type safety
- Maps the `User` class to the `users` table with all its columns

**Why it matters:** This is the schema definition. All database migrations,
queries, and API responses ultimately reference these column definitions.

Future phases add: `Document`, `Chunk`, `Session`, `Message` models.

---

### `auth/schemas.py`
**Purpose:** Pydantic models for the auth API's request/response shapes.

Responsibilities:
- `RegisterRequest` — validates registration input (email format, required fields)
- `LoginRequest` — validates login input
- `TokenResponse` — structures the JWT response
- `UserResponse` — safe user representation (no hashed_password)

**Why it matters:** Decouples API shape from DB shape. The `hashed_password`
column exists in the ORM model but is never included in `UserResponse`, so it
can never accidentally leak to clients.

---

### `auth/router.py`
**Purpose:** HTTP route handlers for registration, login, and profile retrieval.

| Endpoint | Method | Auth required | Purpose |
|---|---|---|---|
| `/auth/register` | POST | No | Create account, returns UserResponse |
| `/auth/login` | POST | No | Verify credentials, returns JWT |
| `/auth/me` | GET | Yes (JWT) | Return current user's profile |

**Why it matters:** This is the only file clients interact with for authentication.
All the heavy lifting (hashing, token creation, validation) is delegated to
`core/security.py`, keeping this file readable.

---

## API Reference

### POST `/auth/register`

**Request body:**
```json
{
  "email": "alice@company.com",
  "password": "mypassword",
  "full_name": "Alice Smith",
  "department": "hr"
}
```

**Response (201 Created):**
```json
{
  "id": 1,
  "email": "alice@company.com",
  "full_name": "Alice Smith",
  "role": "user",
  "department": "hr"
}
```

**Error (400):** `"Email already registered"`

---

### POST `/auth/login`

**Request body:**
```json
{
  "email": "alice@company.com",
  "password": "mypassword"
}
```

**Response (200 OK):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**Error (401):** `"Incorrect email or password"` (same message for both wrong email and wrong password)

---

### GET `/auth/me`

**Header:** `Authorization: Bearer <access_token>`

**Response (200 OK):**
```json
{
  "id": 1,
  "email": "alice@company.com",
  "full_name": "Alice Smith",
  "role": "user",
  "department": "hr"
}
```

**Error (401):** Token missing, expired, or tampered.

---

## How to Start the Server

```bash
# From the backend/ folder:
..\RAG_VENV\Scripts\python -m uvicorn main:app --reload --port 8000
```

- API docs (Swagger UI): http://localhost:8000/docs
- Alternative docs (ReDoc): http://localhost:8000/redoc
- Health check: http://localhost:8000/health

---

## Logging Output Reference

```
2024-01-15 10:23:01 | INFO     | __main__        | Initialising database tables...
2024-01-15 10:23:01 | INFO     | __main__        | Database tables ready
2024-01-15 10:23:01 | INFO     | __main__        | Enterprise AI Chatbot API started
2024-01-15 10:23:45 | INFO     | auth.router     | Registration attempt for email: alice@company.com
2024-01-15 10:23:45 | INFO     | core.security   | Access token created for subject: alice@company.com
2024-01-15 10:23:45 | INFO     | auth.router     | User registered successfully: id=1 email=alice@company.com
2024-01-15 10:24:00 | INFO     | auth.router     | Login attempt for email: alice@company.com
2024-01-15 10:24:00 | INFO     | auth.router     | Login successful: id=1 email=alice@company.com role=user
2024-01-15 10:24:05 | WARNING  | auth.router     | Failed login attempt for email: alice@company.com
2024-01-15 10:24:10 | WARNING  | core.security   | JWT decode failed: Signature verification failed
```

---

## Dependencies Installed

| Package | Version | Purpose |
|---|---|---|
| fastapi | latest | Web framework |
| uvicorn | latest | ASGI server that runs FastAPI |
| sqlalchemy | latest | ORM for SQLite |
| python-jose[cryptography] | latest | JWT encoding/decoding |
| passlib[bcrypt] | latest | Password hashing |
| bcrypt | 4.0.1 | bcrypt backend (pinned — passlib incompatible with 5.x) |
| python-multipart | latest | Required for form data parsing in FastAPI |
| python-dotenv | latest | Loads .env file |
| pydantic-settings | latest | Typed config from environment variables |
| pydantic[email] | latest | EmailStr validation |

> **Note:** `bcrypt` is pinned to `4.0.1` because `passlib` has not yet been
> updated to support the `bcrypt` 5.x API (missing `__about__.__version__`).

---

## Next Phase

**Phase 2 — Document Processing + FAISS Embedding Pipeline**

You will learn:
- What embeddings are and how text becomes a vector of numbers
- How to chunk long documents into overlapping pieces
- How FAISS stores and searches vectors in memory
- The full RAG (Retrieve → Augment → Generate) pattern

You will build:
- Parsers for PDF, DOCX, TXT/MD, and web URLs
- A chunking utility with configurable size and overlap
- An Ollama embedding pipeline that turns chunks into vectors
- A FAISS index per department, saved to disk
