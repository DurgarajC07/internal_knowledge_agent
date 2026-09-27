"""Splits cleaned text into ~500-800 token chunks with 10-15% overlap
(Plan.md SS7). Chunk size is measured in words as a token proxy (~0.75
words/token for English prose) to avoid pulling in a tokenizer dependency —
documented approximation, not a precision requirement at MVP scale.
"""

from __future__ import annotations

DEFAULT_CHUNK_SIZE_TOKENS = 650
DEFAULT_OVERLAP_RATIO = 0.125
_WORDS_PER_TOKEN = 0.75


def chunk_text(
    text: str,
    *,
    chunk_size_tokens: int = DEFAULT_CHUNK_SIZE_TOKENS,
    overlap_ratio: float = DEFAULT_OVERLAP_RATIO,
) -> list[str]:
    words = text.split()
    if not words:
        return []

    chunk_size_words = max(1, int(chunk_size_tokens * _WORDS_PER_TOKEN))
    overlap_words = int(chunk_size_words * overlap_ratio)
    stride = max(1, chunk_size_words - overlap_words)

    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size_words, len(words))
        chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start += stride
    return chunks
