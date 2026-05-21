"""
ingestion/chunker.py
--------------------
PURPOSE:
    Splits a long text string into overlapping fixed-size chunks suitable
    for embedding and storage in the FAISS vector index.

CONCEPT — Why Chunk?
    Embedding models have a token limit (e.g. 512 tokens for MiniLM).
    A 50-page policy document has tens of thousands of tokens — it must be
    split before embedding. Each chunk becomes one searchable unit in FAISS.

CONCEPT — Overlap
    If we split strictly at 500-token boundaries, a sentence starting at
    token 499 gets cut off mid-thought. With a 50-token overlap, the end of
    one chunk is repeated at the start of the next. This ensures no important
    context is lost at a boundary.

    Example (chunk_size=10, overlap=3, tokens=[a,b,c,d,e,f,g,h,i,j,k]):
        chunk 0: [a,b,c,d,e,f,g,h,i,j]
        chunk 1: [h,i,j,k]              ← 'h,i,j' repeated from chunk 0

CONCEPT — Token vs Character Chunking
    True token counting requires running the tokeniser (slow). We approximate
    with characters: 1 token ≈ 4 characters on average for English text.
    This is fast and accurate enough for retrieval — slight over/under-chunking
    has no meaningful impact on answer quality.

USAGE:
    from ingestion.chunker import chunk_text
    chunks = chunk_text("very long policy document text...", chunk_size=500, overlap=50)
    # Returns: ["chunk 1 text", "chunk 2 text", ...]
"""

import re
from core.logging_config import get_logger

logger = get_logger(__name__)

# 1 token ≈ 4 characters for English prose.
# Used to convert token-based config values to character counts.
CHARS_PER_TOKEN = 4


def _clean_text(text: str) -> str:
    """
    Normalise whitespace before chunking.

    Consecutive blank lines and runs of spaces create misleading chunk
    boundaries and waste tokens. We collapse them here once so the chunker
    works on clean input.
    """
    # Collapse 3+ consecutive newlines to a paragraph break (2 newlines).
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Collapse horizontal runs of whitespace (tabs, multiple spaces) to a single space.
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def chunk_text(
    text: str,
    chunk_size: int = 500,
    overlap: int = 50,
) -> list[str]:
    """
    Split `text` into overlapping chunks of approximately `chunk_size` tokens.

    Strategy:
      1. Clean the text (normalise whitespace).
      2. Convert token sizes to character counts.
      3. Slide a window of `chunk_chars` across the text, stepping by
         `step_chars` (= chunk_chars - overlap_chars) each iteration.
      4. At each position, find the nearest sentence boundary (`. ` or `\n`)
         within a tolerance window to avoid cutting mid-sentence.
      5. Strip and deduplicate empty chunks.

    Args:
        text:       The full document text to split.
        chunk_size: Target chunk size in tokens (default 500).
        overlap:    Number of tokens to repeat between adjacent chunks (default 50).

    Returns:
        List of non-empty text strings, each approximately `chunk_size` tokens.
    """
    text = _clean_text(text)

    if not text:
        logger.warning("chunk_text received empty text — returning empty list")
        return []

    chunk_chars = chunk_size * CHARS_PER_TOKEN    # e.g. 500 tokens → 2000 chars
    overlap_chars = overlap * CHARS_PER_TOKEN     # e.g.  50 tokens →  200 chars
    step_chars = chunk_chars - overlap_chars      # advance this far each iteration

    chunks = []
    start = 0
    text_len = len(text)

    logger.debug(
        "Chunking %d chars | chunk=%d tokens (%d chars) | overlap=%d tokens (%d chars)",
        text_len, chunk_size, chunk_chars, overlap, overlap_chars,
    )

    while start < text_len:
        end = min(start + chunk_chars, text_len)

        # Try to break at a sentence boundary within the last 20% of the window
        # to avoid cutting mid-sentence. Skip boundary search on the final chunk.
        if end < text_len:
            boundary_search_start = end - chunk_chars // 5  # last 20% of chunk
            # Look for '. ', '.\n', or '\n\n' in the boundary search zone.
            best_boundary = -1
            for pattern in (". ", ".\n", "\n\n", "\n"):
                pos = text.rfind(pattern, boundary_search_start, end)
                if pos != -1 and pos > best_boundary:
                    best_boundary = pos + len(pattern)  # include the delimiter

            if best_boundary != -1:
                end = best_boundary

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        start += step_chars

        # Safety: if step is 0 or negative (shouldn't happen), break to avoid loop.
        if step_chars <= 0:
            logger.error("step_chars <= 0 — chunking aborted to prevent infinite loop")
            break

    logger.info(
        "Chunking complete: %d chunks from %d characters (avg %.0f chars/chunk)",
        len(chunks), text_len, (text_len / len(chunks)) if chunks else 0,
    )
    return chunks
