"""
Embedding generation — sentence-transformers.
Thread-safe singleton model loader.
All calls here are synchronous (run via asyncio.to_thread in callers).
"""
import logging
import threading

import numpy as np
from sentence_transformers import SentenceTransformer

from config import settings

logger = logging.getLogger(__name__)

_model: SentenceTransformer | None = None
_model_lock = threading.Lock()


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                logger.info(f"Loading embedding model: {settings.EMBEDDING_MODEL}")
                _model = SentenceTransformer(settings.EMBEDDING_MODEL)
                logger.info("Embedding model ready.")
    return _model


def generate_embeddings(texts: list[str]) -> np.ndarray:
    """
    Batch embed list of strings.
    Returns float32 ndarray (N, EMBEDDING_DIM).
    NOTE: Do NOT call from async context directly — wrap with asyncio.to_thread.
    """
    if not texts:
        return np.empty((0, settings.EMBEDDING_DIM), dtype="float32")
    return get_model().encode(
        texts,
        batch_size=settings.EMBEDDING_BATCH_SIZE,
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=False,  # normalization done in vector_store
    )


def generate_query_embedding(query: str) -> np.ndarray:
    """Single query embedding. Shape: (EMBEDDING_DIM,)"""
    return get_model().encode(query, convert_to_numpy=True, normalize_embeddings=False)
