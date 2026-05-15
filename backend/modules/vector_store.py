"""
FAISS vector index per vault.
Uses IndexIDMap2(IndexFlatIP) + L2-normalized embeddings = cosine similarity.
IndexIDMap2 supports selective deletion by explicit ID — no full rebuild needed.
IDs are monotonically increasing ints, persisted in a per-vault meta JSON.

[CACHE] Each loaded index is kept in _index_cache after first disk read.
        Subsequent operations (search, add, delete) skip disk I/O entirely.
        Cache entries are invalidated only when the vault is deleted.
        Thread safety: existing per-vault threading.Lock covers cache access
        (all cache reads/writes happen inside the vault lock).
"""
import json
import logging
import threading
from pathlib import Path

import faiss
import numpy as np

from config import settings

logger = logging.getLogger(__name__)

# ─── Per-vault locks ──────────────────────────────────────────────────────────

_locks: dict[str, threading.Lock] = {}
_lock_guard = threading.Lock()


def _get_lock(vault_id: str) -> threading.Lock:
    with _lock_guard:
        if vault_id not in _locks:
            _locks[vault_id] = threading.Lock()
        return _locks[vault_id]


# ─── In-memory index cache ────────────────────────────────────────────────────
# Eliminates repeated faiss.read_index() calls (disk I/O) on every operation.
# Protected by the per-vault lock — no separate lock needed.

_index_cache: dict[str, faiss.IndexIDMap2] = {}


# ─── Paths ───────────────────────────────────────────────────────────────────

def _vault_dir() -> Path:
    p = settings.DATA_DIR / "vaults"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _index_path(vault_id: str) -> Path:
    return _vault_dir() / f"{vault_id}.index"


def _meta_path(vault_id: str) -> Path:
    return _vault_dir() / f"{vault_id}.meta.json"


# ─── Meta helpers ─────────────────────────────────────────────────────────────

def _read_meta(vault_id: str) -> dict:
    p = _meta_path(vault_id)
    if p.exists():
        return json.loads(p.read_text())
    return {"next_id": 0}


def _write_meta(vault_id: str, meta: dict) -> None:
    _meta_path(vault_id).write_text(json.dumps(meta))


# ─── Index lifecycle ─────────────────────────────────────────────────────────

def _create_index() -> faiss.IndexIDMap2:
    inner = faiss.IndexFlatIP(settings.EMBEDDING_DIM)
    return faiss.IndexIDMap2(inner)


def _load_index(vault_id: str) -> faiss.IndexIDMap2:
    """Return cached index if available, otherwise load from disk and cache."""
    if vault_id in _index_cache:
        return _index_cache[vault_id]
    p = _index_path(vault_id)
    if p.exists():
        idx = faiss.read_index(str(p))
        logger.debug(f"[FAISS] Cache miss — loaded vault {vault_id[:8]} from disk ({idx.ntotal} vectors)")
    else:
        idx = _create_index()
        logger.debug(f"[FAISS] New index created for vault {vault_id[:8]}")
    _index_cache[vault_id] = idx
    return idx


def _save_index(vault_id: str, index: faiss.IndexIDMap2) -> None:
    """Persist to disk and update cache."""
    faiss.write_index(index, str(_index_path(vault_id)))
    _index_cache[vault_id] = index


# ─── Public API ───────────────────────────────────────────────────────────────

def add_to_index(vault_id: str, embeddings: np.ndarray) -> list[int]:
    """
    Normalize + add vectors to the index with auto-assigned monotonic IDs.
    Returns list of assigned IDs (store in ChunkDB.faiss_index).
    Thread-safe. Cache-backed — no disk read on subsequent calls.
    """
    with _get_lock(vault_id):
        index = _load_index(vault_id)
        meta = _read_meta(vault_id)

        start_id = meta["next_id"]
        ids = list(range(start_id, start_id + len(embeddings)))
        meta["next_id"] = start_id + len(embeddings)

        vecs = embeddings.astype("float32").copy()
        faiss.normalize_L2(vecs)

        index.add_with_ids(vecs, np.array(ids, dtype="int64"))
        _save_index(vault_id, index)
        _write_meta(vault_id, meta)

        return ids


def delete_from_index(vault_id: str, faiss_ids: list[int]) -> None:
    """Delete specific vectors by their IDs. O(log n) per deletion."""
    if not faiss_ids:
        return
    with _get_lock(vault_id):
        index = _load_index(vault_id)
        selector = faiss.IDSelectorBatch(np.array(faiss_ids, dtype="int64"))
        index.remove_ids(selector)
        _save_index(vault_id, index)


def search_index(
    vault_id: str,
    query_embedding: np.ndarray,
    top_k: int = 10,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Returns (scores, faiss_ids).
    Scores are cosine similarities in [-1, 1] (higher = more similar).
    Cache-backed — typically zero disk I/O after first call per vault.
    """
    with _get_lock(vault_id):
        index = _load_index(vault_id)
        if index.ntotal == 0:
            return np.array([], dtype="float32"), np.array([], dtype="int64")

        k = min(top_k, index.ntotal)
        q = query_embedding.astype("float32").reshape(1, -1).copy()
        faiss.normalize_L2(q)
        scores, ids = index.search(q, k)
        return scores[0], ids[0]


def get_vault_index_size(vault_id: str) -> int:
    p = _index_path(vault_id)
    if not p.exists():
        return 0
    with _get_lock(vault_id):
        return _load_index(vault_id).ntotal


def delete_vault_index(vault_id: str) -> None:
    """Remove index from disk and evict from in-memory cache."""
    with _get_lock(vault_id):
        # Evict cache entry first
        _index_cache.pop(vault_id, None)
        for p in [_index_path(vault_id), _meta_path(vault_id)]:
            if p.exists():
                p.unlink()
    # Clean up the lock entry to avoid unbounded dict growth
    with _lock_guard:
        _locks.pop(vault_id, None)
