"""
Cross-encoder reranker for passage retrieval quality improvement.

Model: cross-encoder/ms-marco-MiniLM-L-6-v2
  ~80 MB, CPU-friendly, SOTA on MS MARCO passage reranking.
  Auto-downloads on first use (same pattern as embeddings).

Architecture:
  Bi-encoder (FAISS)  — fast ANN recall, O(1) lookup
  Cross-encoder (here) — slow but precise pairwise scoring, O(N) per query

Usage pattern (search.py):
  1. FAISS: fetch top_k * RERANK_FACTOR candidates (expanded recall)
  2. Cross-encoder: score all candidates against query
  3. Sort by reranker score, slice top_k
  4. Apply final threshold

Score range: logits in ~[-12, 12] → sigmoid → [0, 1]
Interpretation after sigmoid:
  > 0.85 — highly relevant
  > 0.65 — relevant
  > 0.40 — marginal
  < 0.40 — not relevant
"""
import logging
import math
import threading
from typing import Optional

logger = logging.getLogger(__name__)

# Factor by which to expand FAISS recall before reranking.
# FAISS fetches top_k * RERANK_FACTOR candidates, reranker scores them,
# final top_k is returned. Higher = better recall, higher latency.
RERANK_FACTOR = 4

# Minimum sigmoid score to include a result after reranking.
# More permissive than cosine threshold — reranker precision compensates.
RERANK_THRESHOLD = 0.30

_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"

_reranker = None
_reranker_lock = threading.Lock()
_reranker_failed = False  # Sticky flag — don't retry after permanent failure


def get_reranker():
    """Lazy singleton. Thread-safe double-checked locking."""
    global _reranker, _reranker_failed
    if _reranker_failed:
        return None
    if _reranker is not None:
        return _reranker
    with _reranker_lock:
        if _reranker is not None:
            return _reranker
        if _reranker_failed:
            return None
        try:
            from sentence_transformers import CrossEncoder
            logger.info(f"Loading reranker: {_MODEL_NAME}")
            _reranker = CrossEncoder(_MODEL_NAME, max_length=512)
            logger.info("Reranker ready.")
        except Exception as e:
            logger.warning(f"Reranker unavailable ({e}). Search will use cosine scores only.")
            _reranker_failed = True
            return None
    return _reranker


def rerank(
    query: str,
    passages: list[str],
) -> list[float]:
    """
    Score each passage against the query using the cross-encoder.
    Returns list of sigmoid-normalized scores in [0, 1], same length as passages.
    On failure: returns list of 0.5 (neutral — preserves original order upstream).
    Must be called from a thread (not async context). Use asyncio.to_thread in callers.
    """
    model = get_reranker()
    if model is None or not passages:
        return [0.5] * len(passages)

    try:
        pairs = [[query, p] for p in passages]
        logits: list[float] = model.predict(pairs, show_progress_bar=False).tolist()
        # Sigmoid normalization: score → [0, 1]
        return [1.0 / (1.0 + math.exp(-logit)) for logit in logits]
    except Exception as e:
        logger.warning(f"Reranker inference failed: {e}")
        return [0.5] * len(passages)


def is_available() -> bool:
    """Returns True if reranker loaded successfully."""
    return get_reranker() is not None
