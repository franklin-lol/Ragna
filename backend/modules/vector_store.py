"""
FAISS vector index per vault.
Uses IndexIDMap2(IndexFlatIP) + L2-normalized embeddings = cosine similarity.
IndexIDMap2 supports selective deletion by explicit ID — no full rebuild needed.
IDs are monotonically increasing ints, persisted in a per-vault meta JSON.
"""
import json
import logging
import threading
from pathlib import Path

import faiss
import numpy as np

from config import settings

logger = logging.getLogger(__name__)

_locks: dict[str, threading.Lock] = {}
_lock_guard = threading.Lock()


def _get_lock(vault_id: str) -> threading.Lock:
    with _lock_guard:
        if vault_id not in _locks:
            _locks[vault_id] = threading.Lock()
        return _locks[vault_id]


def _vault_dir() -> Path:
    p = settings.DATA_DIR / "vaults"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _index_path(vault_id: str) -> Path:
    return _vault_dir() / f"{vault_id}.index"


def _meta_path(vault_id: str) -> Path:
    return _vault_dir() / f"{vault_id}.meta.json"


def _read_meta(vault_id: str) -> dict:
    p = _meta_path(vault_id)
    if p.exists():
        return json.loads(p.read_text())
    return {"next_id": 0}


def _write_meta(vault_id: str, meta: dict) -> None:
    _meta_path(vault_id).write_text(json.dumps(meta))


def _create_index() -> faiss.IndexIDMap2:
    inner = faiss.IndexFlatIP(settings.EMBEDDING_DIM)
    return faiss.IndexIDMap2(inner)


def _load_index(vault_id: str) -> faiss.IndexIDMap2:
    p = _index_path(vault_id)
    if p.exists():
        return faiss.read_index(str(p))
    return _create_index()


def _save_index(vault_id: str, index) -> None:
    faiss.write_index(index, str(_index_path(vault_id)))


# ─── Public API ──────────────────────────────────────────────────────────────

def add_to_index(vault_id: str, embeddings: np.ndarray) -> list[int]:
    """
    Normalize + add vectors to the index with auto-assigned monotonic IDs.
    Returns list of assigned IDs (store in ChunkDB.faiss_index).
    Thread-safe.
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
    faiss_ids are the IDs passed to add_with_ids (stored in ChunkDB.faiss_index).
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
    for p in [_index_path(vault_id), _meta_path(vault_id)]:
        if p.exists():
            p.unlink()
