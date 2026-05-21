# Phase 2 — Document Processing + FAISS Embedding Pipeline

## Overview

**Goal:** Build the pipeline that converts uploaded documents into searchable vector
indexes. This is the "R" (Retrieval) in RAG — without this phase, the agents have no
knowledge of your company's policies.

**What you built:**
- Parsers for PDF, DOCX, TXT/Markdown, and web URLs
- A text chunker that splits long documents into overlapping segments
- An embedder using `sentence-transformers` (`all-MiniLM-L6-v2`) to convert text to vectors
- A FAISS vector store — one index per department — with disk persistence
- `Document` and `Chunk` database tables to track what's been ingested
- An end-to-end test script that verifies the whole pipeline

---

## Concepts Covered

### 1. Embeddings — Text as Numbers

An embedding converts text into a list of numbers (a **vector**) that captures its meaning:

```
"What is the leave policy?" → [0.12, -0.45, 0.88, 0.03, ...] (384 numbers)
"Annual leave entitlement"  → [0.11, -0.41, 0.85, 0.07, ...] (384 numbers, very similar!)
"Company car allowance"     → [-0.55, 0.22, -0.13, 0.91, ...] (very different)
```

**Key insight:** Texts with similar meaning produce vectors that are close together in
384-dimensional space, even if they use completely different words. This is semantic
search — far more powerful than keyword matching.

**Model used:** `all-MiniLM-L6-v2`
- 90 MB, runs on CPU, 384 dimensions
- Downloaded once to `~/.cache/huggingface/` and cached forever
- ~1000 sentences/second on a modern CPU

### 2. Chunking — Splitting Documents

A policy document can have thousands of tokens. The embedding model's limit is 512 tokens.
We split documents into overlapping chunks:

```
chunk_size = 500 tokens = ~2000 characters
overlap    =  50 tokens = ~200 characters

Document: [=====chunk0=====][==overlap==][=====chunk1=====][==overlap==][=====chunk2=====]
```

The **overlap** prevents important context from being lost at boundaries:

```
WITHOUT overlap:
  chunk0: "...employees must provide 14 days notice for"  ← sentence cut off!
  chunk1: "leave requests exceeding 5 days..."            ← context lost

WITH overlap:
  chunk0: "...employees must provide 14 days notice for leave requests..."
  chunk1: "...notice for leave requests exceeding 5 days..."  ← repeated for context
```

### 3. FAISS — Vector Similarity Search

FAISS stores vectors as a matrix in RAM and answers: *"which stored vectors are most
similar to this query vector?"*

**Index type used:** `IndexFlatIP` (Flat Inner Product)
- "Flat" = exact search (no approximation), best accuracy
- "Inner Product" = measures cosine similarity (with normalised vectors)
- Good for millions of vectors; for enterprise docs (thousands of chunks) it's instant

**Search flow:**
```
User query: "How many sick days do I get?"
    ↓ embed_text()
query_vector: [0.22, -0.11, 0.77, ...]
    ↓ faiss.search(query_vector, k=5)
top 5 FAISS IDs: [12, 7, 3, 18, 1]  with scores: [0.94, 0.91, 0.87, 0.83, 0.79]
    ↓ lookup SQLite: WHERE faiss_id IN (12, 7, 3, 18, 1)
chunk texts: ["Sick leave entitlement is 14 days...", ...]
    ↓ inject into LLM prompt
Answer: "You are entitled to 14 days of paid sick leave per year."
```

### 4. RAG Pattern — Retrieve → Augment → Generate

```
┌─────────────────────────────────────────────────────┐
│ INDEXING TIME (done when documents are uploaded)    │
│                                                     │
│  Document → Parse → Chunk → Embed → FAISS + SQLite │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ QUERY TIME (done on every user message)             │
│                                                     │
│  User question → Embed → FAISS search               │
│  → Retrieve top-k chunk texts from SQLite           │
│  → Build prompt: system + context + question        │
│  → LLM generates answer grounded in context         │
└─────────────────────────────────────────────────────┘
```

Without RAG, the LLM can only answer from its training data (which doesn't include your
company's policies). With RAG, the LLM answers from the actual documents.

### 5. Cosine Similarity + L2 Normalisation

We use `IndexFlatIP` (inner product) instead of `IndexFlatL2` (Euclidean distance) because:
- Inner product of two **unit vectors** equals their **cosine similarity**
- Cosine similarity measures *direction* (meaning), not magnitude (length)
- A 10-word chunk and a 500-word chunk can have the same cosine similarity to a query

Before adding to FAISS, we normalise with `faiss.normalize_L2(vectors)` — this divides
each vector by its length, placing it on the unit sphere. All vectors are then comparable.

---

## File Map

```
backend/
├── ingestion/
│   ├── __init__.py         Package marker
│   ├── parsers.py          Format-specific text extractors (PDF, DOCX, TXT, URL)
│   ├── chunker.py          Overlapping fixed-size text chunker
│   ├── embedder.py         sentence-transformers wrapper + singleton
│   └── vector_store.py     FAISS index management (one per department)
│
├── db/
│   └── models.py           Updated: Document + Chunk ORM models added
│
├── test_ingestion.py       End-to-end pipeline test (run directly)
│
└── vector_store/           Created at runtime
    ├── hr/index.faiss
    ├── it/index.faiss
    ├── finance/index.faiss
    ├── legal/index.faiss
    └── admin/index.faiss
```

---

## File-by-File Purpose

### `ingestion/parsers.py`
**Purpose:** Extract plain text from documents regardless of their format.

| Format | Library | Notes |
|---|---|---|
| PDF | `pdfplumber` | Handles columns, rotated text; skips image-only pages |
| DOCX | `python-docx` | Reads paragraph objects; tables not extracted in Phase 2 |
| TXT / MD | built-in | UTF-8 read; no library needed |
| URL | `requests` + `BeautifulSoup` | Fetches HTML, strips script/style/nav tags |

**Key function:** `parse_document(source)` — auto-detects format and dispatches.

---

### `ingestion/chunker.py`
**Purpose:** Split long text into overlapping fixed-size segments for embedding.

**Key function:** `chunk_text(text, chunk_size=500, overlap=50)`

**Algorithm:**
1. Clean whitespace (collapse blank lines, tabs)
2. Convert token counts to character counts (1 token ≈ 4 chars)
3. Slide a window across the text, stepping by `chunk_size - overlap`
4. At each boundary, find the nearest sentence end (`. ` or `\n`) to avoid mid-sentence cuts
5. Return list of non-empty strings

**Configuration:**
| Parameter | Default | Effect |
|---|---|---|
| `chunk_size` | 500 tokens | Larger = more context per chunk, fewer chunks |
| `overlap` | 50 tokens | Larger = less information loss at boundaries, more storage |

---

### `ingestion/embedder.py`
**Purpose:** Convert text strings into 384-dimensional float32 vectors.

**Key class:** `Embedder`
- `embed_text(text)` → shape `(384,)` — for query-time embedding
- `embed_batch(texts)` → shape `(n, 384)` — for bulk document ingestion

**Key function:** `get_embedder()` — returns the shared singleton instance.

**First-run behaviour:** Downloads `all-MiniLM-L6-v2` (~90 MB) from Hugging Face.
Cached at `~/.cache/huggingface/` — subsequent runs are instant.

---

### `ingestion/vector_store.py`
**Purpose:** One FAISS index per department — add, search, save, load, reset.

**Key class:** `VectorStore`

| Method | What it does |
|---|---|
| `load()` | Load index from `.faiss` file, or create empty one |
| `add_vectors(vectors)` | L2-normalise and add to index; returns FAISS IDs |
| `search(query_vector, k)` | Return top-k `(faiss_id, score)` tuples |
| `save()` | Write index to disk atomically (via temp file) |
| `reset()` | Destroy index and delete file (used when all docs deleted) |

**Key function:** `get_vector_store(department)` — singleton per department.

**Key function:** `load_all_stores()` — called by `main.py` on startup to pre-warm indexes.

**Disk layout:** `vector_store/{department}/index.faiss`

---

### `db/models.py` — New Models

#### `Document`
| Column | Type | Purpose |
|---|---|---|
| `id` | Integer PK | Auto-increment |
| `department` | String | Which FAISS index this belongs to |
| `filename` | String | Original filename or URL |
| `source_type` | String | `pdf`, `docx`, `txt`, `md`, `url` |
| `chunk_count` | Integer | How many Chunk rows were created |
| `uploaded_at` | DateTime | UTC ingestion timestamp |

#### `Chunk`
| Column | Type | Purpose |
|---|---|---|
| `id` | Integer PK | Auto-increment |
| `document_id` | FK → Document | Parent document |
| `department` | String | Denormalised for fast lookup without JOIN |
| `chunk_index` | Integer | 0-based position within the document |
| `chunk_text` | Text | The raw text sent to the LLM as context |
| `faiss_id` | Integer | Index in the FAISS array for this department |

**Relationship:** `Document.chunks` → list of all `Chunk` rows. Deleting a `Document`
cascades and deletes all its `Chunk` rows automatically.

---

## Data Flow Diagram

```
Upload: policy.pdf (HR department)
    │
    ▼
parsers.parse_document("policy.pdf")
    → "ANNUAL LEAVE POLICY\n\n1. ENTITLEMENT\nAll employees..."
    │
    ▼
chunker.chunk_text(text, chunk_size=500, overlap=50)
    → ["ANNUAL LEAVE POLICY...entitlement is 21 days...",
       "...21 days...carry-over rules...",
       "...carry-over...application process..."]
    │
    ▼
embedder.embed_batch(chunks)
    → array shape (3, 384)  ← 3 chunks × 384 dimensions
    │
    ▼
vector_store.add_vectors(vectors)           vector_store.save()
    → faiss_ids = [0, 1, 2]                → vector_store/hr/index.faiss
    │
    ▼
SQLite: INSERT INTO documents (department='hr', filename='policy.pdf', chunk_count=3)
        INSERT INTO chunks (document_id=1, faiss_id=0, chunk_text="ANNUAL LEAVE...")
        INSERT INTO chunks (document_id=1, faiss_id=1, chunk_text="...21 days...")
        INSERT INTO chunks (document_id=1, faiss_id=2, chunk_text="...carry-over...")
```

---

## API Reference (Test Script)

Run the end-to-end pipeline test:

```bash
cd backend/
..\RAG_VENV\Scripts\python test_ingestion.py
```

**Expected output:**
```
TEST 1: Chunker
  Produced 5 chunks
  PASSED

TEST 2: Embedder (downloads ~90MB on first run)
  Single embed shape: (384,)  PASSED
  Batch embed shape: (5, 384)  PASSED

TEST 3: VectorStore (FAISS)
  Indexed 5 vectors | IDs: [0, 1, 2, 3, 4]
  Query: 'leave encashment'
  Rank 1 | score=0.8432 | chunk[4]: ENCASHMENT Annual leave encashment is permitted...
  PASSED
  Save/Load roundtrip PASSED

TEST 4: Database models (Document + Chunk)
  Document created: id=1, chunk_count=5
  5 Chunk rows created
  Chunk retrieved by faiss_id=0
  PASSED

ALL TESTS PASSED
```

---

## Dependencies Installed

| Package | Purpose |
|---|---|
| `sentence-transformers` | Downloads and runs `all-MiniLM-L6-v2` locally |
| `torch` | PyTorch backend for the transformer model |
| `faiss-cpu` | Facebook AI Similarity Search (CPU build) |
| `numpy` | Array operations; FAISS works with numpy arrays |
| `pdfplumber` | PDF text extraction |
| `python-docx` | DOCX paragraph extraction |
| `beautifulsoup4` | HTML tag stripping for URL parsing |
| `requests` | HTTP fetching for URL parsing |

---

## Configuration Tips

**Chunk size tuning:**
- Too small (< 200 tokens) → chunks lose context, answers are incomplete
- Too large (> 800 tokens) → few chunks, poor precision in retrieval
- Sweet spot: 400–600 tokens for policy documents

**Top-k tuning:**
- `k=3` → fast, focused context, may miss details
- `k=5` → balanced (recommended for Phase 3)
- `k=10` → comprehensive, uses more of the LLM's context window

---

## Next Phase

**Phase 3 — RAG Query Engine (Per-Department)**

You will learn:
- Semantic search vs keyword search
- Prompt engineering: system prompt, context injection, conversation history
- Ollama chat API — OpenAI-compatible format
- Streaming responses for real-time UX

You will build:
- `QueryEngine` class: embed query → FAISS search → retrieve chunks → call LLM
- Department-specific system prompts
- `POST /chat/query` endpoint with streaming support
- `sessions` and `messages` tables for chat history
