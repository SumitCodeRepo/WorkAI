# Phase 3 — RAG Query Engine (Per-Department)

## Overview

**Goal:** Connect the retrieval pipeline (Phase 2) to the LLM to produce grounded,
streaming answers. After this phase, you can POST a question to a department endpoint
and receive a real AI answer drawn from uploaded policy documents.

**What you built:**
- Department-specific system prompts with grounding constraints
- `QueryEngine` class: embed → FAISS search → chunk retrieval → LLM streaming
- `Session` and `Message` database tables for chat history
- `POST /chat/query` streaming endpoint (Server-Sent Events)
- `GET /chat/history/{session_id}` to restore past conversations
- `POST /chat/session` to create a session explicitly

---

## Concepts Covered

### 1. Semantic Search vs Keyword Search

| | Keyword Search | Semantic Search (our approach) |
|---|---|---|
| Matches | Exact word | Meaning / intent |
| "sick days" query | Only finds "sick days" | Also finds "medical leave", "illness entitlement" |
| Implementation | `LIKE '%sick%'` SQL | FAISS vector similarity |
| Accuracy | Brittle | Robust to paraphrasing |

Semantic search works because the embedding model was trained to place
semantically similar sentences close together in vector space.

### 2. Prompt Engineering

A well-structured prompt has four layers:

```
┌──────────────────────────────────────────────┐
│ SYSTEM PROMPT                                │
│ "You are the HR assistant. Answer ONLY       │
│  from the provided context..."               │
├──────────────────────────────────────────────┤
│ CONTEXT BLOCK (retrieved chunks)             │
│ [1] Sick leave entitlement is 14 days...     │
│ [2] Medical certificate required for 3+...  │
├──────────────────────────────────────────────┤
│ CHAT HISTORY (last 4 turns)                  │
│ user: How many annual leave days?            │
│ assistant: 21 days for full-time...          │
├──────────────────────────────────────────────┤
│ CURRENT QUESTION                             │
│ user: What about sick leave?                 │
└──────────────────────────────────────────────┘
```

**Grounding:** The phrase "Answer ONLY using the provided context" is critical.
Without it, the LLM invents plausible-sounding but wrong policy details.

**Per-department prompts:** Each department has its own system prompt tuned to
its domain. The Finance prompt reminds employees to keep receipts; the Legal
prompt clarifies that answers aren't legal advice.

### 3. Ollama Chat API

OpenAI-compatible format. We send a POST request with a messages array:

```python
requests.post("http://localhost:11434/api/chat", json={
    "model": "gpt-oss:120b-cloud",
    "messages": [
        {"role": "system",    "content": "You are the HR assistant..."},
        {"role": "user",      "content": "--- CONTEXT ---\n[1] ...\n\nQuestion: ..."}
    ],
    "stream": True,
    "think": False    # suppresses the reasoning <think> block from output
})
```

With `stream=True`, Ollama sends one JSON object per line as tokens are generated:
```
{"message": {"role": "assistant", "content": "You"}, "done": false}
{"message": {"role": "assistant", "content": " are"}, "done": false}
{"message": {"role": "assistant", "content": " entitled"}, "done": false}
...
{"message": {"role": "assistant", "content": "."}, "done": true}
```

### 4. Server-Sent Events (SSE) Streaming

SSE is a simple HTTP protocol for one-way server→client streaming:

```
HTTP/1.1 200 OK
Content-Type: text/event-stream

event: metadata
data: {"session_id": 3, "department": "hr"}

event: token
data: You

event: token
data:  are entitled to

event: token
data:  14 days

event: done
data: {}
```

The client (React Native) reads these events and appends each token to the
chat bubble as it arrives — no polling, no websocket needed.

### 5. Session and Chat History

Sessions group messages for one conversation thread:

```
Session 5 (HR, user_id=1)
  Message 1: role=user    "How many sick days do I get?"
  Message 2: role=assistant "You are entitled to 14 days..."
  Message 3: role=user    "What about hospitalisation?"
  Message 4: role=assistant "Additionally, 60 days of..."
```

The `QueryEngine` loads the last 4 turns (8 messages) and injects them into
the prompt so the LLM understands "What about hospitalisation?" refers to sick leave.

---

## File Map

```
backend/
├── agents/
│   ├── prompts.py          Department system prompts + context block builder
│   └── query_engine.py     RAG engine: retrieve → augment → generate
│
├── chat/
│   ├── schemas.py          Pydantic models for chat request/response
│   └── router.py           POST /chat/query, GET /chat/history, POST /chat/session
│
├── db/models.py            Updated: Session + Message tables added
├── core/config.py          Updated: OLLAMA_MODEL setting added
├── .env                    Updated: OLLAMA_MODEL=gpt-oss:120b-cloud
├── main.py                 Updated: chat router mounted
└── test_query_engine.py    End-to-end RAG test
```

---

## File-by-File Purpose

### `agents/prompts.py`
**Purpose:** All system prompt strings and the context block formatter.

**Key exports:**
- `DEPARTMENT_PROMPTS` — dict mapping dept → system prompt string
- `build_context_block(chunks)` → formatted `--- RELEVANT CONTEXT ---` block
- `get_system_prompt(department)` → returns prompt for dept, falls back to 'general'

**Design decision:** Prompts live in one file so the company can tune them
without touching engine logic. A non-developer could edit prompts safely.

---

### `agents/query_engine.py`
**Purpose:** The RAG pipeline in a single class. Stateless between queries.

**`QueryEngine(department)`** — constructor, sets department and model name.

**`stream_answer(question, db, session_id)` → generator**

Internal steps:
1. `_retrieve_chunks()` — embed question, FAISS search, SQLite lookup
2. `_load_history()` — fetch last `HISTORY_TURNS * 2` messages from session
3. `_build_messages()` — assemble [system, ...history, user+context] list
4. Calls Ollama `/api/chat` with `stream=True`
5. Yields each token string from the SSE stream

**Tuning constants** (top of file):
```python
HISTORY_TURNS = 4   # number of prior Q&A pairs injected into prompt
TOP_K_CHUNKS  = 5   # number of FAISS nearest neighbours to retrieve
```

---

### `chat/router.py`
**Purpose:** HTTP endpoints the mobile app calls.

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `/chat/query` | POST | JWT | Stream AI answer (SSE) |
| `/chat/history/{session_id}` | GET | JWT | Fetch past messages |
| `/chat/session` | POST | JWT | Create session explicitly |

**`POST /chat/query` flow:**
1. Authenticate user
2. Get/create session
3. Emit `metadata` SSE event with session_id
4. Iterate `engine.stream_answer()` → emit `token` SSE events
5. After stream: save user message + full response to SQLite
6. Emit `done` SSE event

**Session ownership check:** The endpoint verifies `session.user_id == current_user.id`
before allowing access — users cannot access other users' chat history.

---

### `db/models.py` — New Models

#### `Session`
| Column | Type | Purpose |
|---|---|---|
| `id` | Integer PK | Auto-increment |
| `user_id` | FK → User | Owner of this conversation |
| `department` | String | Which agent this session is with |
| `created_at` | DateTime | When the session started |

#### `Message`
| Column | Type | Purpose |
|---|---|---|
| `id` | Integer PK | Auto-increment |
| `session_id` | FK → Session | Parent session |
| `role` | String | `'user'` or `'assistant'` |
| `content` | Text | Full message text |
| `created_at` | DateTime | Ordering timestamps |

---

## API Reference

### POST `/chat/query`

**Header:** `Authorization: Bearer <token>`

**Request body:**
```json
{
  "department": "hr",
  "message": "How many sick days do I get?",
  "session_id": null
}
```

**Response:** `text/event-stream`
```
event: metadata
data: {"session_id": 3, "department": "hr"}

event: token
data: You are entitled to

event: token
data:  14 days of paid sick leave per year.

event: done
data: {}
```

On follow-up questions, send the returned `session_id`:
```json
{
  "department": "hr",
  "message": "What about hospitalisation?",
  "session_id": 3
}
```

---

### GET `/chat/history/{session_id}`

**Header:** `Authorization: Bearer <token>`

**Response:**
```json
[
  {"id": 1, "role": "user",      "content": "How many sick days...", "created_at": "2024-..."},
  {"id": 2, "role": "assistant", "content": "You are entitled to 14 days...", "created_at": "2024-..."}
]
```

---

## Testing with curl

```bash
# 1. Login and get token
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@company.com","password":"secret123"}' \
  | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)

# 2. Stream a chat response (watch tokens arrive)
curl -s -X POST http://localhost:8000/chat/query \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"department":"hr","message":"How many sick days do I get?"}' \
  --no-buffer

# 3. Fetch chat history (note the session_id from the metadata event)
curl -s http://localhost:8000/chat/history/1 \
  -H "Authorization: Bearer $TOKEN"
```

---

## Configuration

| Setting | Default | Location |
|---|---|---|
| `OLLAMA_MODEL` | `gpt-oss:120b-cloud` | `.env` / `core/config.py` |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | `.env` / `core/config.py` |
| `TOP_K_CHUNKS` | `5` | `agents/query_engine.py` |
| `HISTORY_TURNS` | `4` | `agents/query_engine.py` |

To switch to a different Ollama model, update `OLLAMA_MODEL` in `.env`.

---

## Next Phase

**Phase 4 — Primary Router Agent (Multi-Agent Orchestration)**

You will learn:
- LLM-as-classifier: using the model's own reasoning to route queries
- Structured output: forcing the LLM to respond with valid JSON
- Agent design pattern: perceive → reason → act
- Confidence thresholds and fallback handling

You will build:
- `RouterAgent` class — sends user message to LLM → returns `{department, confidence, reason}`
- `POST /chat/message` — the primary endpoint the mobile app calls (no department needed)
- Fallback: if confidence is low, ask the user to clarify
