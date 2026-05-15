"""
Semantic search.
Cosine similarity via IndexIDMap2(IndexFlatIP) + normalized vectors.
Score ∈ [0, 1] for sentence-transformers embeddings (practically ~0.2–1.0).
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
) -> list[dict[str, Any]]:
    query_emb = await asyncio.to_thread(generate_query_embedding, query)
    scores, faiss_ids = await asyncio.to_thread(search_index, vault_id, query_emb, top_k)

    if len(faiss_ids) == 0:
        return []

    valid = []
    for s, fid in zip(scores, faiss_ids):
        if fid == -1:
            continue
        
        score = float(s)
        # BUG PROTECTION: If we see scores > 1.0, the index is likely using L2 metric instead of IP.
        # We'll log a warning and skip to avoid garbage results.
        if score > 1.1:
            logger.error(f"STRICT SEARCH WARNING: Detected suspicious FAISS score {score:.2f}. "
                         f"Your index might be using L2 distance instead of Cosine Similarity. "
                         f"Please delete the vault and re-index your documents.")
            continue
            
        if score >= threshold:
            valid.append((score, int(fid)))

    if not valid:
        return []

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

    results: list[dict] = []
    for score, fid in valid:
        if fid not in chunk_map:
            continue
        chunk_db, filename = chunk_map[fid]

        try:
            content = decrypt_bytes(key, chunk_db.nonce, chunk_db.content_encrypted).decode("utf-8")
        except Exception:
            logger.warning(f"Decryption failed chunk {chunk_db.id}")
            content = "[DECRYPTION FAILED]"

        try:
            tags = json.loads(chunk_db.tags) if chunk_db.tags else []
        except (json.JSONDecodeError, TypeError):
            tags = []

        results.append({
            "chunk_id": chunk_db.id,
            "document_id": chunk_db.document_id,
            "filename": filename,
            "content": content,
            "score": round(score, 4),
            "relevance_label": _relevance_label(score),
            "section": chunk_db.section,
            "tags": tags,
            "language": chunk_db.language,
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results
