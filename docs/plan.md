# Enterprise AI Chatbot — Master Project Plan

## Project Vision

Build a mobile-first enterprise chatbot where employees chat with an AI that
intelligently routes their queries to the right department agent (HR, IT, Finance,
Legal, Admin). Each agent answers questions grounded in that department's uploaded
policy documents via RAG (Retrieval-Augmented Generation).

Approach: **Learning mode** — each phase teaches a concept before building it.

---

## Architecture

```
React Native App (Mobile)
        │  HTTP/REST + JWT
        ▼
FastAPI Backend  ──── SQLite (users, docs, chunks, sessions, messages)
        │
   Primary Router Agent (Ollama LLM — JSON mode)
   Classifies user message → department
        │
   ┌────┴──────────────────────────────┐
   HR     IT    Finance   Legal   Admin
   Agent  Agent  Agent   Agent   Agent
     │      │      │       │       │
   FAISS  FAISS  FAISS   FAISS   FAISS   (one index per department)
```

## Technology Stack

| Layer | Technology | Why |
|---|---|---|
| Backend API | Python 3.11 + FastAPI | Async, typed, auto-docs |
| Database | SQLite via SQLAlchemy | Zero-config, file-based, perfect for development |
| Vector Store | FAISS (faiss-cpu) | Fast nearest-neighbour search, one index per dept |
| Embeddings | sentence-transformers (all-MiniLM-L6-v2) | 90 MB, runs on CPU, 384-dim vectors |
| LLM / Chat | Ollama (gpt-oss:120b-cloud) | OpenAI-compatible API, local server |
| Auth | JWT (python-jose + passlib/bcrypt) | Stateless, mobile-friendly |
| Doc Parsing | pdfplumber, python-docx, beautifulsoup4 | PDF, DOCX, TXT/MD, URL |
| Mobile | React Native (Expo) | Cross-platform iOS/Android |

## Departments
HR, IT, Finance, Legal, Admin

## Key Decisions Made
- **Embeddings:** sentence-transformers (not Ollama) — cloud Ollama model requires auth for /api/embed
- **LLM:** gpt-oss:120b-cloud via local Ollama server
- **DB:** SQLite (single file, zero config, great for learning)
- **Routing:** LLM-based (JSON mode) — flexible, handles ambiguous queries naturally
- **Admin panel:** In-app document upload per department (triggers auto-indexing)
- **Document formats:** PDF, DOCX, TXT/MD, Web URLs

---

## Project Folder Structure (Final)

```
enterprise-chatbot/
├── .gitignore
├── docs/                          ← All documentation
│   ├── plan.md                    ← This file (master plan)
│   ├── phase1.md                  ← Auth foundations
│   ├── phase2.md                  ← Document ingestion + FAISS
│   ├── phase3.md                  ← RAG query engine
│   ├── phase4.md                  ← Multi-agent routing
│   ├── phase5.md                  ← Admin document management API
│   ├── phase6.md                  ← React Native setup + auth screens
│   ├── phase7.md                  ← Chat UI
│   ├── phase8.md                  ← Admin panel UI
│   └── phase9.md                  ← Polish + production hardening
│
├── temp/                          ← Test log output (not committed)
│   ├── app.log                    ← Rolling server log
│   ├── test_ingestion.log         ← Phase 2 test output
│   ├── test_query_engine.log      ← Phase 3 test output
│   └── test_router_agent.log      ← Phase 4 test output
│
├── backend/
│   ├── main.py                    ← FastAPI entry point
│   ├── .env                       ← Secrets + config (not committed)
│   │
│   ├── core/
│   │   ├── config.py              ← Typed settings from .env
│   │   ├── security.py            ← bcrypt, JWT, FastAPI dependencies
│   │   └── logging_config.py      ← Centralised logger + file output
│   │
│   ├── db/
│   │   ├── database.py            ← SQLAlchemy engine + get_db()
│   │   └── models.py              ← All ORM tables (User, Document, Chunk, Session, Message)
│   │
│   ├── auth/
│   │   ├── schemas.py             ← Pydantic models for auth endpoints
│   │   └── router.py              ← POST /auth/register, /login  GET /auth/me
│   │
│   ├── ingestion/
│   │   ├── parsers.py             ← PDF / DOCX / TXT / URL → plain text
│   │   ├── chunker.py             ← Overlapping fixed-size chunking
│   │   ├── embedder.py            ← sentence-transformers singleton
│   │   ├── vector_store.py        ← FAISS index per department
│   │   └── pipeline.py            ← (Phase 5) Orchestrates full ingest
│   │
│   ├── agents/
│   │   ├── prompts.py             ← Department system prompts
│   │   ├── query_engine.py        ← RAG: retrieve → augment → stream
│   │   └── router_agent.py        ← (Phase 4) LLM-based dept classifier
│   │
│   ├── chat/
│   │   ├── schemas.py             ← Pydantic models for chat endpoints
│   │   └── router.py              ← POST /chat/query /chat/message  GET /chat/history
│   │
│   ├── admin/
│   │   └── router.py              ← (Phase 5) POST /admin/documents/upload etc.
│   │
│   ├── vector_store/              ← FAISS .faiss files (not committed)
│   │   ├── hr/index.faiss
│   │   ├── it/index.faiss
│   │   ├── finance/index.faiss
│   │   ├── legal/index.faiss
│   │   └── admin/index.faiss
│   │
│   ├── test_ingestion.py          ← Phase 2 pipeline test
│   ├── test_query_engine.py       ← Phase 3 RAG test
│   └── test_router_agent.py       ← Phase 4 routing test
│
└── mobile/                        ← React Native (Expo) app — Phase 6+
    ├── App.tsx
    ├── context/
    │   └── AuthContext.tsx
    ├── screens/
    │   ├── LoginScreen.tsx
    │   ├── RegisterScreen.tsx
    │   ├── HomeScreen.tsx
    │   ├── ChatScreen.tsx
    │   └── admin/
    │       ├── AdminHomeScreen.tsx
    │       ├── DocumentListScreen.tsx
    │       └── UploadDocumentScreen.tsx
    ├── components/
    │   └── MessageBubble.tsx
    └── services/
        ├── api.ts
        └── chatService.ts
```

---

## Phases

### Phase 1 — Backend Foundation + JWT Authentication ✅ DONE
**Concept:** REST APIs, FastAPI, SQLite/SQLAlchemy ORM, JWT tokens, bcrypt hashing, Pydantic

**Built:**
- FastAPI project scaffold
- `users` SQLite table
- `POST /auth/register`, `POST /auth/login`, `GET /auth/me`
- Centralised logging with file output to `temp/`

**Doc:** [docs/phase1.md](phase1.md)

---

### Phase 2 — Document Processing + FAISS Embedding Pipeline ✅ DONE
**Concept:** Embeddings, text chunking with overlap, FAISS vector search, RAG pattern overview

**Built:**
- Parsers for PDF, DOCX, TXT/MD, URL
- Overlapping chunker (500 tokens, 50 overlap)
- sentence-transformers embedder (all-MiniLM-L6-v2, 384-dim)
- FAISS index per department with disk persistence
- `documents` and `chunks` SQLite tables

**Doc:** [docs/phase2.md](phase2.md)

---

### Phase 3 — RAG Query Engine (Per-Department) ✅ DONE
**Concept:** Semantic search, prompt engineering, Ollama chat API, SSE streaming

**Built:**
- Department system prompts with grounding constraints
- `QueryEngine` class: embed → FAISS → retrieve → LLM stream
- `sessions` and `messages` SQLite tables
- `POST /chat/query` — streaming SSE endpoint
- `GET /chat/history/{session_id}` — restore past conversations

**Doc:** [docs/phase3.md](phase3.md)

---

### Phase 4 — Primary Router Agent (Multi-Agent Orchestration) ✅ DONE
**Concept:** LLM-as-classifier, JSON structured output, agent design pattern, confidence thresholds

**Built:**
- `RouterAgent` class — Ollama JSON mode → `RoutingResult(department, confidence, reason)`
- `POST /chat/message` — primary endpoint; router picks department automatically
- Confidence threshold (0.50): low confidence → `clarify` SSE event → user picks department
- SSE event types: `routing`, `metadata`, `token`, `done`, `clarify`
- Context-aware routing: last 4 history messages injected for follow-up questions
- 6/6 routing tests passed; clarification path verified; full flow integration tested

**Doc:** [docs/phase4.md](phase4.md)

---

### Phase 5 — Admin Document Management API ✅ DONE
**Concept:** File upload in FastAPI, BackgroundTasks, FAISS persistence, RBAC

**Built:**
- `ingestion/pipeline.py` — full orchestration (parse → chunk → embed → FAISS → SQLite)
- `POST /admin/documents/upload` — multipart upload (file or URL), 202 Accepted + background ingest
- `GET  /admin/documents` — list with optional department filter
- `GET  /admin/documents/{id}` — single document (poll for chunk_count after async ingest)
- `DELETE /admin/documents/{id}` — delete + cascade chunks + background FAISS rebuild
- `rebuild_faiss_index(department, db)` — re-embeds all remaining chunks, updates faiss_ids
- 3/3 tests passed: ingest, list/delete/cascade, index rebuild

**Doc:** [docs/phase5.md](phase5.md)

---

### Phase 6 — React Native App Setup + Auth Screens ✅ DONE
**Concept:** Expo managed workflow, React Navigation, AsyncStorage, Axios, React Context

**Built:**
- Expo blank-typescript scaffold + navigation/storage/HTTP dependencies
- `theme.ts` — central design tokens (Colors, Typography, Shadow, Spacing)
- `services/api.ts` — Axios singleton with JWT request interceptor
- `context/AuthContext.tsx` — global auth state; auto-restores session from AsyncStorage
- `screens/LoginScreen.tsx` — controlled inputs, KeyboardAvoidingView, error alerts
- `screens/RegisterScreen.tsx` — registration with department chip selector
- `screens/ForgotPasswordScreen.tsx` — email input → step-tracker success state
- `screens/HomeScreen.tsx` — 5 department cards + recent conversations
- `App.tsx` — AuthStack ↔ MainStack auth-guard switching, TypeScript param lists
- Zero TypeScript compile errors

**Doc:** [docs/phase6.md](phase6.md)

---

### Phase 7 — Chat UI (Home + Chat Screens) ✅ DONE
**Concept:** FlatList for chat, SSE streaming in React Native, KeyboardAvoidingView, optimistic UI

**Built:**
- `ChatScreen` — message list, text input, typing indicator, agent badge, clarify flow
- `MessageBubble` — user/assistant bubbles, routing pill, streaming cursor, React.memo optimisation
- `TypingIndicator` — 3-dot Animated bounce with native driver at 60fps
- `chatService.ts` — XHR-based SSE streaming, byte-offset buffering, full event dispatch
- App.tsx updated: ChatScreen registered in MainNavigator
- Zero TypeScript compile errors

**Doc:** [docs/phase7.md](phase7.md)

---

### Phase 8 — Admin Panel UI ✅ DONE
**Concept:** expo-document-picker, FormData multipart upload, role-based navigation

**Built:**
- Admin tab (visible only for `role=admin`) via `BottomTabNavigator`
- `AdminHomeScreen` — all departments with document counts, pull-to-refresh
- `DocumentListScreen` — list + delete (Alert confirmation + optimistic removal)
- `UploadDocumentScreen` — native file picker + FormData + progress bar + 202 flow
- `adminApi` functions added to `services/api.ts`
- App.tsx updated: nested navigators, role-based root (`ChatNavigator` vs `AdminTabNavigator`)
- Zero TypeScript compile errors

**Doc:** [docs/phase8.md](phase8.md)

---

### Phase 9 — Polish + Production Hardening ✅ DONE
**Concept:** Global error handling, rate limiting, FAISS persistence, enhanced health check

**Built:**
- `core/rate_limit.py` — shared Limiter singleton (avoids circular imports)
- `@limiter.limit(settings.RATE_LIMIT_CHAT)` on `POST /chat/message` (20/min default)
- FastAPI lifespan: startup loads FAISS, shutdown saves all indexes to disk
- Global exception handler: logs full traceback, returns safe 500 JSON to client
- `RequestValidationError` handler: consistent 422 shape
- Enhanced `/health`: checks DB (SELECT 1) + Ollama (/api/tags) — returns "degraded" vs "ok"
- Fixed missing `DEPARTMENT_DESCRIPTIONS` import in `chat/router.py`
- `RATE_LIMIT_CHAT` setting added to `core/config.py`
- Import check verified clean

**Doc:** [docs/phase9.md](phase9.md)

---

## Backend Endpoints — Complete Map

| Method | Path | Auth | Phase | Description |
|---|---|---|---|---|
| GET | /health | No | 1 | Server health check |
| POST | /auth/register | No | 1 | Create user account |
| POST | /auth/login | No | 1 | Login, get JWT |
| GET | /auth/me | JWT | 1 | Current user profile |
| POST | /chat/query | JWT | 3 | Direct dept chat (streaming SSE) |
| GET | /chat/history/{id} | JWT | 3 | Fetch session message history |
| POST | /chat/session | JWT | 3 | Create session explicitly |
| POST | /chat/message | JWT | 4 | Primary chat (router decides dept) |
| POST | /admin/documents/upload | JWT+Admin | 5 | Upload + auto-index document |
| GET | /admin/documents | JWT+Admin | 5 | List documents (dept filter) |
| DELETE | /admin/documents/{id} | JWT+Admin | 5 | Delete document + rebuild index |

## SQLite Tables — Complete Map

| Table | Phase | Purpose |
|---|---|---|
| users | 1 | Registered accounts (email, hashed_password, role, department) |
| documents | 2 | Uploaded policy files (filename, department, chunk_count) |
| chunks | 2 | Text segments from documents (chunk_text, faiss_id) |
| sessions | 3 | Chat conversation threads (user_id, department) |
| messages | 3 | Individual chat turns (role, content, session_id) |

## Dependencies — Complete List

**Backend (Python):**
```
fastapi uvicorn sqlalchemy
python-jose[cryptography] passlib[bcrypt] bcrypt==4.0.1
python-multipart python-dotenv pydantic-settings pydantic[email]
sentence-transformers faiss-cpu numpy
pdfplumber python-docx beautifulsoup4 requests
slowapi                     ← Phase 9
```

**Mobile (Node/Expo):**
```
expo react-navigation
axios @react-native-async-storage/async-storage
expo-document-picker        ← Phase 8
```

## Running the Server

```bash
cd backend/
..\RAG_VENV\Scripts\python -m uvicorn main:app --reload --port 8000
```

- Swagger UI:  http://localhost:8000/docs
- ReDoc:       http://localhost:8000/redoc
- Health:      http://localhost:8000/health
- Server log:  temp/app.log

## Running Tests

```bash
cd backend/
..\RAG_VENV\Scripts\python test_ingestion.py      # Phase 2
..\RAG_VENV\Scripts\python test_query_engine.py   # Phase 3
..\RAG_VENV\Scripts\python test_router_agent.py   # Phase 4
```

Logs are written to `temp/<test_name>.log` in addition to the console.

## Known Issues / Notes

- `bcrypt` pinned to 4.0.1 — passlib incompatible with bcrypt 5.x API
- Windows console (cp1252) can't display some Unicode chars from LLM output;
  test scripts use `errors="replace"` encoding and logging_config uses `reconfigure`
- Ollama cloud model (`gpt-oss:120b-cloud`) returns "unauthorized" for `/api/embed`,
  so sentence-transformers is used for embeddings instead
- The HuggingFace cache does not use symlinks on Windows without Developer Mode;
  this is a cosmetic warning only — caching still works
