# 05 — Testing Guide

This project has three testing layers:
1. **Backend integration tests** — Python scripts that test each phase end-to-end
2. **TypeScript type checking** — catches type errors in the mobile codebase
3. **Manual QA checklist** — human verification of the full user journey

---

## Layer 1 — Backend Integration Tests

All test scripts live in `backend/`. They test against a running Ollama server and
write output to both the console and `temp/<script>.log`.

### Prerequisites
- Ollama is running: `ollama serve`
- Backend virtual environment is available: `RAG_VENV/`
- Run from the **project root** (not inside `backend/`) so relative paths work

### Running the tests

```bash
# Windows — run from e:\Claude_Work\PythonCode\
cd backend

# Phase 2 — Document ingestion + FAISS pipeline
..\RAG_VENV\Scripts\python test_ingestion.py

# Phase 3 — RAG query engine (requires at least one document ingested)
..\RAG_VENV\Scripts\python test_query_engine.py

# Phase 4 — Router agent (LLM-based department classification)
..\RAG_VENV\Scripts\python test_router_agent.py

# Phase 5 — Admin document management API
..\RAG_VENV\Scripts\python test_admin.py
```

```bash
# Mac / Linux
cd backend

../RAG_VENV/bin/python test_ingestion.py
../RAG_VENV/bin/python test_query_engine.py
../RAG_VENV/bin/python test_router_agent.py
../RAG_VENV/bin/python test_admin.py
```

### What each test covers

#### `test_ingestion.py` (Phase 2)
- Creates a sample text document in memory
- Runs the parse → chunk → embed → FAISS pipeline
- Verifies the expected number of chunks in SQLite
- Verifies vector count in the FAISS index
- Queries the index and confirms the most relevant chunk is returned

**Expected output:**
```
[PASS] Document ingested: 4 chunks created
[PASS] FAISS index contains 4 vectors
[PASS] Nearest-neighbour search returned relevant chunk
```

#### `test_query_engine.py` (Phase 3)
- Requires at least one document to be indexed (run test_ingestion first)
- Sends a test question to the HR department QueryEngine
- Streams the response and verifies tokens arrive
- Verifies the session and messages are saved to SQLite

**Expected output:**
```
[PASS] Stream started — tokens received
[PASS] Session created in DB
[PASS] User + assistant messages saved
```

#### `test_router_agent.py` (Phase 4)
- Sends 6 test messages with known correct departments
- Verifies the router classifies each to the right department
- Verifies the clarification path triggers for an ambiguous message
- Tests context-aware routing (follow-up question)

**Expected output:**
```
[PASS] "What is the leave policy?" → HR (confidence 0.97)
[PASS] "My laptop won't connect to VPN" → IT (confidence 0.95)
[PASS] "Expense reimbursement process?" → Finance (confidence 0.93)
[PASS] "NDA review needed" → Legal (confidence 0.91)
[PASS] "Book a meeting room" → Admin (confidence 0.88)
[PASS] "I have a question" → CLARIFICATION_NEEDED
[PASS] 6/6 routing decisions correct
```

#### `test_admin.py` (Phase 5)
- Uploads a test document via the pipeline
- Verifies it appears in the document list
- Deletes the document and verifies cascade deletion of chunks
- Rebuilds the FAISS index and verifies correctness

**Expected output:**
```
[PASS] test_ingest_document: chunk_count=4, faiss_vectors=4
[PASS] test_list_and_delete: listed 1 doc, deleted, 0 chunks remain
[PASS] test_rebuild_faiss_index: 3 vectors, faiss_ids consistent, searchable
```

### Log files
Each test writes a dedicated log to `temp/`:
```
backend/temp/test_ingestion.log
backend/temp/test_query_engine.log
backend/temp/test_router_agent.log
backend/temp/test_admin.log
```

---

## Layer 2 — TypeScript Type Check

Run the TypeScript compiler in check-only mode (no output files generated):

```bash
cd mobile
npx tsc --noEmit
```

**Expected:** No output = 0 errors. Any errors are printed to the terminal.

### Running on save (watch mode)

```bash
npx tsc --noEmit --watch
# Re-checks after every file save
```

### What this catches
- Missing or wrong props on components
- Type mismatches between screens and navigation params
- Missing fields in API response types
- Incorrect imports

---

## Layer 3 — Manual QA Checklist

Run this checklist before every release build or after significant changes.

### Setup
- [ ] Backend running: `http://localhost:8000/health` → `{"status":"ok"}`
- [ ] Ollama running: `ollama list` shows the model
- [ ] Expo dev server running: `npx expo start`
- [ ] At least one document uploaded to HR (for RAG tests to work)
- [ ] Two test accounts exist: one `role=user`, one `role=admin`

---

### Auth Flows

**Login:**
- [ ] Valid credentials → lands on Home screen
- [ ] Wrong password → error alert with `401` message
- [ ] Empty fields → validation prevents submit

**Register:**
- [ ] All fields filled → account created → navigates to Login
- [ ] Password < 8 chars → validation error shown
- [ ] Passwords don't match → validation error shown
- [ ] Duplicate email → error alert from server

**Forgot password:**
- [ ] Enter email → tap Send → success screen appears
- [ ] Success screen shows the entered email address
- [ ] Back button works

**Logout:**
- [ ] Tap avatar on Home → logged out → Login screen appears

---

### Chat Flows (Regular User)

**Home screen:**
- [ ] All 5 department cards visible (HR, IT, Finance, Legal, Admin)
- [ ] No "Admin" tab visible (regular user)
- [ ] Tapping a card navigates to the department's Chat screen

**Sending a message:**
- [ ] User message appears immediately (optimistic UI)
- [ ] Typing indicator (3 animated dots + "Routing…" pill) appears
- [ ] Typing indicator disappears when first token arrives
- [ ] Tokens stream into the assistant bubble one by one
- [ ] Routing pill shows department name + confidence % on the assistant bubble
- [ ] Send button is disabled while streaming
- [ ] After stream ends, send button is re-enabled

**Follow-up messages:**
- [ ] Second message in the same session reuses the `session_id`
- [ ] The assistant has context from previous turns

**Clarification flow:**
- [ ] Send an ambiguous message ("I have a question about something")
- [ ] Clarification chips appear above the input bar
- [ ] Tapping a chip navigates to a fresh chat for that department

**Error handling:**
- [ ] Stop the backend → send a message → error bubble appears with "Network error"
- [ ] Restart backend → new message works correctly

**Keyboard:**
- [ ] Input bar moves up when keyboard appears
- [ ] Input bar moves back down when keyboard dismisses
- [ ] Return key sends the message

---

### Admin Flows (Admin User)

**Navigation:**
- [ ] Login as admin → bottom tab bar visible with "Chats" and "Admin" tabs
- [ ] "Chats" tab → same Home + Chat flow as regular users
- [ ] "Admin" tab → Admin Home screen with 5 department cards

**Document list:**
- [ ] Department card shows correct document count
- [ ] Tapping a card → document list for that department
- [ ] Pull down to refresh updates the list
- [ ] Each document shows filename, type emoji, chunk count, upload date

**Upload flow:**
- [ ] Tap "+" → Upload screen opens
- [ ] Tap the drop zone → native file picker opens
- [ ] Pick a PDF → file name and size appear in the drop zone
- [ ] Tap "Upload & Index" → progress bar fills
- [ ] Success screen appears with file name and instructions
- [ ] "Back to Document List" button returns to the list
- [ ] After pulling to refresh, the new document appears with chunk count > 0
- [ ] Unsupported file type (e.g. `.xlsx`) → the picker filters it out

**Delete flow:**
- [ ] Tap the delete icon (🗑️) → confirmation dialog appears
- [ ] Cancel → document remains
- [ ] Confirm → loading spinner on the row → document disappears from list
- [ ] After deletion, querying that department in Chat no longer uses the deleted document

---

### Rate Limiting (Phase 9)

```bash
# Send 21 rapid requests (21st should get 429)
for i in $(seq 1 21); do
  curl -s -o /dev/null -w "%{http_code}\n" \
    -X POST http://localhost:8000/chat/message \
    -H "Authorization: Bearer <token>" \
    -H "Content-Type: application/json" \
    -d '{"message":"test"}'
done
```

Expected: first 20 return `200`, the 21st returns `429`.

---

### API Tests (via Swagger UI)

Open http://localhost:8000/docs and manually test:

| Endpoint | Test | Expected |
|---|---|---|
| `GET /health` | No auth | `{"status":"ok","db":"ok","ollama":"ok"}` |
| `POST /auth/register` | New email | `201` with user object |
| `POST /auth/login` | Valid creds | `200` with `access_token` |
| `GET /auth/me` | With token | `200` with user profile |
| `POST /chat/message` | Authenticated | `200` streaming SSE events |
| `POST /admin/documents/upload` | Admin token + PDF | `202 Accepted` |
| `GET /admin/documents` | Admin token | List of documents |
| `DELETE /admin/documents/{id}` | Admin token | `200` with rebuild message |
| `GET /chat/history/{id}` | User token | List of messages |

---

## Automated Testing (Future)

To add automated tests in the future:

### Backend — pytest
```bash
RAG_VENV/bin/pip install pytest httpx

# Example test file: backend/tests/test_auth.py
# Uses FastAPI TestClient for HTTP tests without a running server
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] in ("ok", "degraded")
```

### Mobile — Jest + React Native Testing Library
```bash
npm install --save-dev jest @testing-library/react-native

# Run tests
npx jest
```

### End-to-End — Detox (React Native)
```bash
npm install --save-dev detox
```

Detox drives the app on a real simulator and is the gold standard for full
flow testing (login → chat → stream → admin upload).
