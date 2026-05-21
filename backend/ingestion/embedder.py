"""
ingestion/embedder.py
---------------------
PURPOSE:
    Converts text strings into dense numerical vectors (embeddings) using a
    locally-running sentence-transformers model.

    This is the bridge between raw text and FAISS: FAISS stores and searches
    vectors, so everything must be embedded before it can be indexed or queried.

CONCEPT — sentence-transformers
    The `sentence-transformers` library wraps Hugging Face transformer models
    and exposes a simple `.encode(text)` API. The model `all-MiniLM-L6-v2`:
      - Size: ~90 MB (downloaded once to ~/.cache/huggingface/)
      - Output: 384-dimensional float32 vectors
      - Speed: ~1000 sentences/second on CPU
      - Quality: very good for semantic similarity tasks

CONCEPT — Embedding Dimension
    Every vector from this model has exactly 384 numbers. When we store vectors
    in FAISS, the index is initialised with dimension=384. All queries must also
    produce 384-dimensional vectors. Mixing models with different dimensions
    corrupts the index.

CONCEPT — Batching
    Encoding one text at a time is slow because the model starts and stops for
    each call. Batching sends many texts through the model in one forward pass,
    which is much faster on both CPU and GPU.

SINGLETON PATTERN:
    The model is loaded once when this module is first imported and reused for
    every subsequent call. Loading a transformer model takes ~1-3 seconds;
    we don't want that delay on every embedding request.

USAGE:
    from ingestion.embedder import get_embedder
    embedder = get_embedder()
    vector = embedder.embed_text("What is the leave policy?")
    vectors = embedder.embed_batch(["chunk 1 text", "chunk 2 text", ...])
"""

import numpy as np
from core.logging_config import get_logger

logger = get_logger(__name__)

# Model identifier on Hugging Face Hub.
# Downloaded automatically on first use to ~/.cache/huggingface/
MODEL_NAME = "all-MiniLM-L6-v2"

# Embedding dimension produced by this model.
# FAISS indexes created with this module must use this exact dimension.
EMBEDDING_DIM = 384


class Embedder:
    """
    Wraps a sentence-transformers model with logging and batch support.

    Attributes:
        model_name: Hugging Face model identifier used for this embedder.
        dim:        Dimension of produced embedding vectors.
    """

    def __init__(self, model_name: str = MODEL_NAME) -> None:
        """
        Load the embedding model.

        The first call downloads the model weights (~90 MB).
        Subsequent calls load from the local Hugging Face cache (fast).

        Args:
            model_name: Sentence-transformers model to load.
        """
        from sentence_transformers import SentenceTransformer

        logger.info("Loading embedding model: %s", model_name)
        self._model = SentenceTransformer(model_name)
        self.model_name = model_name
        self.dim = self._model.get_embedding_dimension()
        logger.info("Embedding model ready | dimension=%d", self.dim)

    def embed_text(self, text: str) -> np.ndarray:
        """
        Embed a single text string.

        Args:
            text: The text to embed (e.g. a user query at search time).

        Returns:
            1-D float32 numpy array of shape (dim,).
        """
        if not text or not text.strip():
            raise ValueError("Cannot embed empty text")

        logger.debug("Embedding single text (%d chars)", len(text))
        vector = self._model.encode(text, convert_to_numpy=True)
        return vector.astype(np.float32)

    def embed_batch(self, texts: list[str], batch_size: int = 64) -> np.ndarray:
        """
        Embed a list of text strings in batches.

        Batching is significantly faster than calling embed_text() in a loop
        because the transformer processes multiple texts in one forward pass.

        Args:
            texts:      List of non-empty text strings to embed.
            batch_size: How many texts to process per model forward pass.
                        Reduce if you run out of RAM on large documents.

        Returns:
            2-D float32 numpy array of shape (len(texts), dim).
        """
        if not texts:
            raise ValueError("Cannot embed an empty list")

        logger.info("Embedding batch of %d texts (batch_size=%d)", len(texts), batch_size)
        vectors = self._model.encode(
            texts,
            batch_size=batch_size,
            convert_to_numpy=True,
            show_progress_bar=len(texts) > 100,  # show progress bar for large batches
        )
        logger.info("Batch embedding complete | shape=%s", vectors.shape)
        return vectors.astype(np.float32)


# ── Module-level singleton ────────────────────────────────────────────────────
# Loaded once on first call to get_embedder(), then reused.
_embedder_instance: Embedder | None = None


def get_embedder() -> Embedder:
    """
    Return the shared Embedder instance, loading the model if needed.

    Using a singleton avoids reloading the model weights (~1-3s) on every
    document ingestion or query. Call this function everywhere instead of
    instantiating Embedder directly.
    """
    global _embedder_instance
    if _embedder_instance is None:
        logger.info("Initialising embedder singleton")
        _embedder_instance = Embedder()
    return _embedder_instance
