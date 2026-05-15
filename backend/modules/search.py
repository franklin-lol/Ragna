"""
Semantic search pipeline.

Two modes:

A) Cosine-only (rerank=False, default):
   query → embedding → FAISS top_k → threshold filter → decrypt → return

B) Reranked (rerank=True):
   query → embedding → FAISS top_k * RERANK_FACTOR candidates
         → threshold pre-filter (loose: 0.10)
         → decrypt all candidates
         → cross-encoder rerank
         → sigmoid score threshold (RERANK_THRESHOLD)
         → slice top_k → return

Mode B significantly improves precision for ambiguous or short queries.
Latency overhead: ~50–200ms on CPU for 40 candidates (cross-encoder batch).
Falls back to mode A silently if reranker model unavailable.

Scores:
  Cosine-only  — IndexFlatIP cosine in [0, 1]
  Reranked     — cross-encoder sigmoid in [0, 1] (replaces cosine score in output)
"""
import asyncio
import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import ChunkDB, DocumentDB
from modules.embeddings import generate_query_embedding
from modules.encryption import decrypt_bytes
from modules.reranker import RERANK_FACTOR, RERANK_THRESHOLD, is_available, rerank
from modules.vector_store import search_index

logger = logging.getLogger(__name__)


def _relevance_label(score: float) -> str:
    if score >= 0.75:
        return "Strong"
    elif score >= 0.60:
        return "Good"
    elif score >= 0.45:
        return "Weak"
    else:
        return "Marginal"


async def perform_search(
    db: AsyncSession,
    vault_id: str,
    key: bytes,
    query: str,
    top_k: int = 10,
    threshold: float = 0.45,
    rerank_results: bool = False,
) -> list[dict[str, Any]]:
    """
    Unified search entry point.

    Args:
        rerank_results: if True and reranker available, run cross-encoder reranking.
                        Falls back to cosine-only if reranker unavailable.
    """
    use_rerank = rerank_results and is_available()

    # ── Step 1: FAISS ANN retrieval ──────────────────────────────────────────
    query_emb = await asyncio.to_thread(generate_query_embedding, query)

    # When reranking, fetch more candidates to improve recall before scoring.
    faiss_k = (top_k * RERANK_FACTOR) if use_rerank else top_k
    scores, faiss_ids = await asyncio.to_thread(search_index, vault_id, query_emb, faiss_k)

    if len(faiss_ids) == 0:
        return []

    # ── Step 2: Pre-filter ────────────────────────────────────────────────────
    # For reranking: use loose threshold (0.10) — cast a wide net, cross-encoder
    # will separate signal from noise precisely.
    # For cosine-only: use the user-configured threshold directly.
    pre_threshold = 0.10 if use_rerank else threshold

    valid: list[tuple[float, int]] = []
    for s, fid in zip(scores, faiss_ids):
        if fid == -1:
            continue
        score = float(s)
        if score > 1.1:
            logger.error(
                f"Suspicious FAISS score {score:.2f} — index may be using L2 instead of cosine. "
                f"Delete vault and re-index."
            )
            continue
        if score >= pre_threshold:
            valid.append((score, int(fid)))

    if not valid:
        return []

    # ── Step 3: DB fetch + decrypt ────────────────────────────────────────────
    valid_ids = [fid for _, fid in valid]
    rows = (
        await db.execute(
            select(ChunkDB, DocumentDB.filename)
            .join(DocumentDB, ChunkDB.document_id == DocumentDB.id)
            .where(ChunkDB.vault_id == vault_id)
            .where(ChunkDB.faiss_index.in_(valid_ids))
        )
    ).all()

    chunk_map: dict[int, tuple[ChunkDB, str]] = {
        row.ChunkDB.faiss_index: (row.ChunkDB, row.filename)
        for row in rows
    }

    # Assemble candidates with decrypted content
    candidates: list[dict[str, Any]] = []
    for cosine_score, fid in valid:
        if fid not in chunk_map:
            continue
        chunk_db, filename = chunk_map[fid]

        try:
            content = decrypt_bytes(
                key, chunk_db.nonce, chunk_db.content_encrypted
            ).decode("utf-8")
        except Exception:
            logger.warning(f"Decryption failed: chunk {chunk_db.id}")
            continue

        try:
            tags = json.loads(chunk_db.tags) if chunk_db.tags else []
        except (json.JSONDecodeError, TypeError):
            tags = []

        candidates.append({
            "chunk_id": chunk_db.id,
            "document_id": chunk_db.document_id,
            "filename": filename,
            "content": content,
            "score": round(cosine_score, 4),
            "section": chunk_db.section,
            "tags": tags,
            "language": chunk_db.language,
        })

    if not candidates:
        return []

    # ── Step 4: Reranking (if enabled) ────────────────────────────────────────
    if use_rerank:
        passages = [c["content"] for c in candidates]
        rerank_scores = await asyncio.to_thread(rerank, query, passages)

        for candidate, rs in zip(candidates, rerank_scores):
            candidate["score"] = round(rs, 4)
            candidate["cosine_score"] = candidate["score"]  # keep for debug

        # Filter by reranker threshold, then slice to top_k
        candidates = [c for c in candidates if c["score"] >= RERANK_THRESHOLD]
        candidates.sort(key=lambda x: x["score"], reverse=True)
        candidates = candidates[:top_k]

    else:
        # Cosine-only: apply user threshold, sort, slice
        candidates = [c for c in candidates if c["score"] >= threshold]
        candidates.sort(key=lambda x: x["score"], reverse=True)
        candidates = candidates[:top_k]

    # ── Step 5: Annotate relevance labels ─────────────────────────────────────
    for c in candidates:
        c["relevance_label"] = _relevance_label(c["score"])

    return candidates
