"""
ingestion/vector_store.py
-------------------------
PURPOSE:
    Manages one FAISS vector index per department.
    Handles creating, loading, saving, adding vectors to, and searching
    each department's index. This is the core of the retrieval step in RAG.

CONCEPT — FAISS (Facebook AI Similarity Search)
    FAISS stores vectors as a matrix in RAM and answers nearest-neighbour
    queries (find the k vectors most similar to this query vector) very fast.

    Index type used: `IndexFlatIP` (Inner Product / cosine similarity)
      - "Flat" means no approximation — every stored vector is compared exactly.
      - For document collections of a few thousand chunks (typical enterprise use),
        exact search is fast enough and gives perfect recall.
      - Cosine similarity: vectors are L2-normalised before storage so that
        dot product (inner product) equals cosine similarity.

CONCEPT — Index Lifecycle
    create  → faiss.IndexFlatIP(dim)          empty index in RAM
    add     → index.add(vectors)             bulk-add embeddings
    search  → index.search(query, k)         find k nearest neighbours
    save    → faiss.write_index(index, path) persist to disk
    load    → faiss.read_index(path)         restore from disk on restart

CONCEPT — Parallel Storage (FAISS + SQLite)
    FAISS stores vectors and knows their integer IDs (0, 1, 2, …).
    SQLite stores chunk text and maps each FAISS ID to the text it came from.
    To answer a query: FAISS returns IDs → SQLite returns the matching texts.

DEPARTMENT INDEXES:
    Each department gets its own subdirectory:
      vector_store/hr/index.faiss
      vector_store/it/index.faiss
      vector_store/finance/index.faiss
      vector_store/legal/index.faiss
      vector_store/admin/index.faiss

USAGE:
    from ingestion.vector_store import VectorStore
    vs = VectorStore("hr")
    vs.add_vectors(embeddings_array)          # shape (n, 384)
    results = vs.search(query_embedding, k=5) # returns [(faiss_id, score), ...]
    vs.save()
    vs.load()
"""

import os
import numpy as np
from pathlib import Path
from core.logging_config import get_logger
from ingestion.embedder import EMBEDDING_DIM

logger = get_logger(__name__)

# Root directory for all FAISS index files (relative to where uvicorn is started).
VECTOR_STORE_ROOT = Path("vector_store")


class VectorStore:
    """
    Manages the FAISS index for one department.

    Each instance owns one index. Call load() at startup and save() after
    every document ingestion to persist changes across server restarts.

    Attributes:
        department: Department name (e.g. 'hr', 'it').
        index_path: Path to the .faiss file on disk.
        index:      The live FAISS index object (None until created or loaded).
        count:      Number of vectors currently stored in the index.
    """

    def __init__(self, department: str) -> None:
        """
        Initialise the store for a department. Does NOT load from disk yet.
        Call load() explicitly, or add_vectors() to start a fresh index.

        Args:
            department: Lowercase department name matching db/models.py Department enum.
        """
        self.department = department.lower()
        self.index_dir = VECTOR_STORE_ROOT / self.department
        self.index_path = self.index_dir / "index.faiss"
        self.index = None

        self.index_dir.mkdir(parents=True, exist_ok=True)
        logger.debug("VectorStore initialised for department: %s", self.department)

    @property
    def count(self) -> int:
        """Number of vectors currently in the index (0 if not yet created)."""
        return self.index.ntotal if self.index is not None else 0

    # ── Create / Load ─────────────────────────────────────────────────────────

    def _create_empty_index(self):
        """
        Create a new empty FAISS IndexFlatIP.

        Vectors are L2-normalised before being added so that inner product
        equals cosine similarity. This means we normalise in add_vectors()
        and in search().
        """
        import faiss
        self.index = faiss.IndexFlatIP(EMBEDDING_DIM)
        logger.info("Created new FAISS index for '%s' (dim=%d)", self.department, EMBEDDING_DIM)

    def load(self) -> bool:
        """
        Load the FAISS index from disk if it exists.

        Returns:
            True if loaded from disk, False if no saved index was found
            (a fresh empty index is created in that case).
        """
        import faiss

        if self.index_path.exists():
            logger.info("Loading FAISS index from %s", self.index_path)
            self.index = faiss.read_index(str(self.index_path))
            logger.info(
                "FAISS index loaded for '%s': %d vectors",
                self.department, self.count,
            )
            return True
        else:
            logger.info("No saved index for '%s' — starting fresh", self.department)
            self._create_empty_index()
            return False

    # ── Save ──────────────────────────────────────────────────────────────────

    def save(self) -> None:
        """
        Persist the current FAISS index to disk.

        Call this after every document ingestion. The file is written
        atomically via a temp file to avoid corruption if the process
        crashes mid-write.
        """
        import faiss

        if self.index is None:
            logger.warning("save() called on uninitialised index for '%s' — skipping", self.department)
            return

        tmp_path = self.index_path.with_suffix(".faiss.tmp")
        faiss.write_index(self.index, str(tmp_path))
        tmp_path.replace(self.index_path)  # atomic rename

        logger.info(
            "FAISS index saved for '%s': %d vectors -> %s",
            self.department, self.count, self.index_path,
        )

    # ── Add vectors ───────────────────────────────────────────────────────────

    def add_vectors(self, vectors: np.ndarray) -> list[int]:
        """
        Add a batch of embedding vectors to the index.

        Vectors are L2-normalised before adding so that IndexFlatIP (inner
        product) behaves as cosine similarity search.

        Args:
            vectors: float32 numpy array of shape (n, EMBEDDING_DIM).

        Returns:
            List of FAISS IDs assigned to the added vectors.
            IDs are sequential integers starting from the current count.
            Store these IDs in SQLite (chunks.faiss_id) to retrieve text later.
        """
        import faiss

        if self.index is None:
            self._create_empty_index()

        vectors = vectors.astype(np.float32)

        # L2-normalise: divide each vector by its magnitude.
        # After normalisation, all vectors lie on the unit sphere,
        # so inner product == cosine similarity.
        faiss.normalize_L2(vectors)

        start_id = self.count
        self.index.add(vectors)
        end_id = self.count

        assigned_ids = list(range(start_id, end_id))
        logger.info(
            "Added %d vectors to '%s' index (total now: %d)",
            len(assigned_ids), self.department, self.count,
        )
        return assigned_ids

    # ── Search ────────────────────────────────────────────────────────────────

    def search(self, query_vector: np.ndarray, k: int = 5) -> list[tuple[int, float]]:
        """
        Find the k most similar vectors to `query_vector`.

        Args:
            query_vector: 1-D float32 numpy array of shape (EMBEDDING_DIM,).
            k:            Number of nearest neighbours to return.
                          Clamped to the number of stored vectors automatically.

        Returns:
            List of (faiss_id, similarity_score) tuples, sorted best-first.
            Pass faiss_ids to SQLite to retrieve the original chunk texts.

        Raises:
            RuntimeError if the index is empty.
        """
        if self.index is None or self.count == 0:
            raise RuntimeError(
                f"FAISS index for '{self.department}' is empty. "
                "Ingest at least one document before searching."
            )

        # Reshape to 2D (1, dim) as FAISS expects a matrix.
        q = query_vector.astype(np.float32).reshape(1, -1)
        import faiss
        faiss.normalize_L2(q)  # normalise query the same way as stored vectors

        # Clamp k to available vectors to prevent FAISS errors.
        k = min(k, self.count)

        scores, ids = self.index.search(q, k)

        # FAISS returns 2D arrays; flatten to 1D since we searched one query.
        results = [(int(ids[0][i]), float(scores[0][i])) for i in range(k)]

        logger.debug(
            "Search in '%s': top-%d results | scores=%s",
            self.department, k, [f"{s:.3f}" for _, s in results],
        )
        return results

    # ── Reset ─────────────────────────────────────────────────────────────────

    def reset(self) -> None:
        """
        Destroy the current index and remove the saved file.

        Called when all documents for a department are deleted and the index
        must be rebuilt from scratch.
        """
        logger.warning("Resetting FAISS index for department: %s", self.department)
        self._create_empty_index()

        if self.index_path.exists():
            self.index_path.unlink()
            logger.info("Deleted saved FAISS index file: %s", self.index_path)


# ── Global registry ───────────────────────────────────────────────────────────
# Keeps one VectorStore instance per department loaded in memory.
# Avoids re-reading the .faiss file on every query.

_stores: dict[str, VectorStore] = {}


def get_vector_store(department: str) -> VectorStore:
    """
    Return the loaded VectorStore for a department, loading it if necessary.

    This is the preferred way to access vector stores — it ensures the index
    is loaded from disk before use and keeps only one instance per department.

    Args:
        department: Lowercase department name (e.g. 'hr', 'it').

    Returns:
        VectorStore instance with its FAISS index loaded and ready.
    """
    dept = department.lower()
    if dept not in _stores:
        store = VectorStore(dept)
        store.load()
        _stores[dept] = store
    return _stores[dept]


def load_all_stores() -> None:
    """
    Pre-load FAISS indexes for all departments on server startup.

    Called from main.py startup event so the first query to any department
    is fast (no disk read on first user request).
    """
    departments = ["hr", "it", "finance", "legal", "admin"]
    logger.info("Pre-loading FAISS indexes for all departments...")
    for dept in departments:
        get_vector_store(dept)
    logger.info("All FAISS indexes loaded")


def save_all_stores() -> None:
    """
    Persist all in-memory FAISS indexes to disk.

    Called from main.py shutdown lifespan event so any vectors added during
    the server session survive a restart. Only saves indexes that are loaded
    and have at least one vector.
    """
    logger.info("Saving FAISS indexes for all departments...")
    for dept, store in _stores.items():
        if store.index is not None and store.index.ntotal > 0:
            try:
                store.save()
            except Exception as exc:
                logger.error("Failed to save FAISS index for '%s': %s", dept, exc)
    logger.info("All FAISS indexes saved")
