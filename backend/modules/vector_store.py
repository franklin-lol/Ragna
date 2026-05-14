"""
FAISS vector index per vault.
Uses IndexFlatIP + L2-normalized embeddings = cosine similarity.
Scores in [0, 1] range (for typical semantic embeddings).
Thread-safe via per-vault locks.
"""
import threading
import logging
import numpy as np
import faiss
from pathlib import Path
from typing import List

from config import settings

logger = logging.getLogger(__name__)

# Per-vault threading locks
_locks: dict[str, threading.Lock] = {}
_lock_guard = threading.Lock()


def _get_lock(vault_id: str) -> threading.Lock:
    with _lock_guard:
        if vault_id not in _locks:
            _locks[vault_id] = threading.Lock()
        return _locks[vault_id]


def _index_path(vault_id: str) -> Path:
    return settings.DATA_DIR / "vaults" / f"{vault_id}.index"


def _create_index() -> faiss.IndexFlatIP:
    """IndexFlatIP: inner-product search. Cosine sim after L2 normalization."""
    return faiss.IndexFlatIP(settings.EMBEDDING_DIM)


def _load_index(vault_id: str) -> faiss.IndexFlatIP:
    path = _index_path(vault_id)
    if path.exists():
        idx = faiss.read_index(str(path))
        logger.debug(f"Loaded FAISS index for vault {vault_id}: {idx.ntotal} vectors")
        return idx
    return _create_index()


def _save_index(vault_id: str, index: faiss.IndexFlatIP) -> None:
    faiss.write_index(index, str(_index_path(vault_id)))


def add_to_index(vault_id: str, embeddings: np.ndarray) -> List[int]:
    """
    Normalize embeddings to unit length, then add to IndexFlatIP.
    Returns list of assigned positions (contiguous ints from ntotal before add).
    """
    with _get_lock(vault_id):
        index = _load_index(vault_id)
        vecs = embeddings.astype("float32").copy()
        faiss.normalize_L2(vecs)  # in-place L2 normalization → cosine sim
        start = index.ntotal
        index.add(vecs)
        _save_index(vault_id, index)
        return list(range(start, index.ntotal))


def search_index(
    vault_id: str,
    query_embedding: np.ndarray,
    top_k: int = 10,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Returns (scores, positions).
    scores: cosine similarities in [-1, 1], higher = more similar.
    positions: FAISS integer IDs.
    """
    with _get_lock(vault_id):
        index = _load_index(vault_id)
        if index.ntotal == 0:
            return np.array([]), np.array([])

        k = min(top_k, index.ntotal)
        q = query_embedding.astype("float32").reshape(1, -1).copy()
        faiss.normalize_L2(q)
        scores, positions = index.search(q, k)
        return scores[0], positions[0]


def delete_vault_index(vault_id: str) -> None:
    path = _index_path(vault_id)
    if path.exists():
        path.unlink()
