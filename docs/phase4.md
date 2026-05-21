# Phase 4 — Primary Router Agent (Multi-Agent Orchestration)

## Concept to Learn

### 1. LLM as a Classifier

Traditional intent classification requires labelled training data, a model training pipeline,
and versioned artefacts. That works well at scale but is expensive to bootstrap.

An alternative: **ask the LLM itself**.

```
User message  →  [Routing prompt + message]  →  LLM  →  JSON  →  department
```

Because a large language model already understands natural language, it can classify
arbitrary queries to a fixed label set with zero labelled training data. The tradeoff:
it is slower than a dedicated classifier (one extra LLM call) and costs tokens, but for
an internal chatbot this is completely acceptable.

### 2. Structured JSON Output (Ollama `format: "json"`)

Normally an LLM responds in free-form prose, which is hard to parse reliably. Ollama
supports a `"format": "json"` field in the chat request that forces the model to output
**only valid JSON** and nothing else. No markdown fences, no preamble, no trailing text.

```python
payload = {
    "model": "...",
    "messages": [...],
    "stream": False,
    "format": "json",   # <-- constrains output to valid JSON
}
```

Combined with a prompt that specifies the exact schema:

```
Reply with ONLY a JSON object in this exact format:
{
  "department": "<one of: hr, it, finance, legal, admin>",
  "confidence": <float between 0.0 and 1.0>,
  "reason": "<one sentence explaining why>"
}
```

This makes the response trivially parseable with `json.loads()` and eliminates the most
common failure mode: the model wrapping the answer in markdown.

### 3. Confidence Thresholds

The model returns a **self-assessed confidence** score (0.0–1.0). This is not a
calibrated probability, but it reliably tracks the model's certainty:
- `confidence ≥ 0.90` → clear, single-department query
- `confidence 0.50–0.89` → plausible routing, act on it
- `confidence < 0.50` → ambiguous (greeting, multi-dept, too vague)

When confidence falls below the threshold, we return a special `CLARIFICATION_NEEDED`
sentinel instead of guessing. The HTTP endpoint then asks the user to pick a department
rather than silently routing to the wrong one.

### 4. Agent Design Pattern: Perceive → Reason → Act

This phase introduces the concept of an **agent** as a perceive-reason-act loop:

```
Perceive:  Read user message + recent conversation history
Reason:    LLM classifies message to a department with justification
Act:       Return routing decision; caller executes it (streams answer)
```

The `RouterAgent` is stateless — it holds no conversation state itself. The HTTP router
passes history in as a parameter, keeping the agent pure and testable.

### 5. Context-Aware Routing

A follow-up message like _"What about part-time employees?"_ contains no department signal
on its own. By injecting the last 4 messages from the conversation as context, the LLM
can resolve the reference and route correctly to the same department as the preceding turn.

```python
messages = [{"role": "system", "content": system_prompt}]
messages.extend(history[-4:])        # last 2 exchange turns
messages.append({"role": "user", "content": message})
```

### 6. SSE Event Types (Extended)

Phase 3 introduced `token`, `done`, `error`. Phase 4 adds two more:

| Event | Payload | Purpose |
|---|---|---|
| `routing` | `{department, confidence, reason}` | UI can show "Answering via HR Agent…" instantly |
| `metadata` | `{session_id, department}` | Client stores session ID |
| `token` | plain text fragment | Appended to chat bubble |
| `done` | `{}` | Stream complete, enable input |
| `clarify` | `{message, departments[]}` | Show department picker to user |

The `routing` event is emitted **before** any LLM generation begins, so the UI can
display the agent badge with zero perceived latency.

---

## What Was Built

### Files Created / Modified

| File | Status | Description |
|---|---|---|
| `backend/agents/router_agent.py` | **New** | RouterAgent class — LLM JSON classifier |
| `backend/chat/schemas.py` | Updated | Added `MessageRequest` (no dept field) |
| `backend/chat/router.py` | Updated | Added `POST /chat/message` primary endpoint |
| `backend/test_router_agent.py` | **New** | Three-test suite for Phase 4 |
| `docs/phase4.md` | **New** | This document |

---

## File Deep-Dives

### `backend/agents/router_agent.py`

```
RouterAgent
├── CONFIDENCE_THRESHOLD = 0.50
├── CLARIFICATION_NEEDED = "clarification_needed"   ← sentinel string
├── DEPARTMENT_DESCRIPTIONS                          ← dept → description dict
├── RoutingResult(dataclass)
│   ├── department: str
│   ├── confidence: float
│   └── reason: str
└── RouterAgent
    ├── __init__(model=None)   ← reads settings.OLLAMA_MODEL
    ├── _build_routing_prompt()  ← injects dept list + JSON schema
    └── route(message, history=None) → RoutingResult
```

**Key decisions:**
- `"format": "json"` + explicit schema in prompt → zero-boilerplate parsing
- `"think": False` → suppresses the gpt-oss model's reasoning token block
- `"stream": False` → routing is a single fast call, no streaming needed
- Unknown department returned by LLM → treated as `CLARIFICATION_NEEDED`
- Any exception (timeout, network, JSON parse) → safe fallback result

### `POST /chat/message` Flow

```
Client sends: { message: "How do I reset my VPN password?" }

1. RouterAgent.route(message, history=[...])
   → RoutingResult(department="it", confidence=0.98, ...)

2. Emit SSE: event: routing
   data: {"department": "it", "confidence": 0.98, "reason": "..."}

3. confidence >= 0.5, so route to QueryEngine("it")

4. _get_or_create_session(department="it", ...)
   Emit SSE: event: metadata
   data: {"session_id": 42, "department": "it"}

5. QueryEngine.stream_answer(message, db, session_id) → token stream
   Emit SSE: event: token
   data: <text fragment>
   ... (repeated for each token)

6. _save_messages(session_id, message, full_response, db)

7. Emit SSE: event: done
   data: {}
```

**Clarification path (confidence < 0.5):**

```
1. RouterAgent.route("Hello") → RoutingResult(department="clarification_needed", confidence=0.30)

2. Emit SSE: event: routing
   data: {"department": "clarification_needed", "confidence": 0.30, ...}

3. Emit SSE: event: clarify
   data: {"message": "...", "departments": ["hr", "it", "finance", "legal", "admin"]}

4. Generator returns — no QueryEngine call, no DB session created
```

---

## Test Results

```
Phase 4 RouterAgent — End-to-End Test

TEST 1: RouterAgent routing accuracy
  [PASS] 'How many days of annual leave do I get?...'           → hr     (conf=1.00)
  [PASS] 'I forgot my VPN password, how do I reset it?...'      → it     (conf=1.00)
  [PASS] 'How do I submit an expense claim for a client...'     → finance (conf=0.99)
  [PASS] 'We need to sign an NDA with a vendor...'              → legal  (conf=0.98)
  [PASS] 'How do I book a meeting room for next Monday?...'     → admin  (conf=0.99)
  [PASS] 'Hello...'                                             → clarification_needed (conf=0.30)
  Result: 6/6 passed   PASSED

TEST 2: Clarification path for vague messages
  'Hello'          → clarification_needed (conf=0.30)
  'I have a question' → clarification_needed (conf=0.20)
  'Can you help me?' → clarification_needed (conf=0.30)
  PASSED

TEST 3: Full /chat/message flow (route → answer → save)
  Routing result: dept=it  conf=0.98
  Answer length: 1388 chars   PASSED
  Message persistence verified   PASSED

ALL TESTS PASSED — Phase 4 multi-agent routing is working
```

---

## API Reference

### `POST /chat/message`

**Auth:** JWT required

**Request body:**
```json
{
  "message": "How do I reset my VPN password?",
  "session_id": null
}
```

**SSE event stream:**
```
event: routing
data: {"department": "it", "confidence": 0.98, "reason": "VPN password is IT support"}

event: metadata
data: {"session_id": 42, "department": "it"}

event: token
data: To reset your VPN password

event: token
data: , visit helpdesk.company.com

... (more tokens)

event: done
data: {}
```

**On low confidence:**
```
event: routing
data: {"department": "clarification_needed", "confidence": 0.30, "reason": "..."}

event: clarify
data: {"message": "...", "departments": ["hr", "it", "finance", "legal", "admin"]}
```

---

## Architecture After Phase 4

```
POST /chat/message
        │
        ▼
  RouterAgent.route()          ← Ollama (JSON mode, non-streaming)
  RoutingResult(dept, conf, reason)
        │
   conf >= 0.5?
        │
   Yes ─┤                No
        │                │
        ▼                ▼
  QueryEngine(dept)   emit: clarify
  stream_answer()
  emit: token stream
        │
        ▼
  _save_messages()
  emit: done
```

---

## Running the Test

```bash
cd backend/
..\RAG_VENV\Scripts\python test_router_agent.py
```

Log output: `temp/test_router_agent.log`

---

## Known Issues / Notes

- The `gpt-oss:120b-cloud` model consistently returns confidence ≥ 0.95 for clearly
  departmental questions and ≤ 0.30 for greetings. The threshold of 0.50 is well-calibrated
  for this model.
- `"think": False` is required — without it the cloud model prepends a reasoning token block
  before the JSON, which breaks `json.loads()`.
- The `routing` event fires before session creation. If routing returns `clarification_needed`,
  no session is created and no DB writes happen — the endpoint remains side-effect-free
  for unanswerable inputs.
