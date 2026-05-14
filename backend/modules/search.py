"""
Semantic search pipeline:
1. Embed query
2. FAISS cosine search
3. Load + decrypt matching chunks from DB
4. Filter by threshold, sort by score
"""
import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import ChunkDB, DocumentDB
from modules.embeddings import generate_query_embedding
from modules.encryption import decrypt_bytes
from modules.vector_store import search_index
import asyncio

logger = logging.getLogger(__name__)


async def perform_search(
    db: AsyncSession,
    vault_id: str,
    key: bytes,
    query: str,
    top_k: int = 10,
    threshold: float = 0.3,
) -> list[dict[str, Any]]:
    """
    Returns list of result dicts, sorted by cosine similarity (descending).
    Threshold applies to cosine similarity score in [0, 1].
    """
    # Embed query (blocking → thread)
    query_emb = await asyncio.to_thread(generate_query_embedding, query)

    # FAISS search (blocking → thread)
    scores, positions = await asyncio.to_thread(search_index, vault_id, query_emb, top_k)

    if len(positions) == 0:
        return []

    # Valid positions only (FAISS returns -1 for padding)
    valid = [(float(s), int(p)) for s, p in zip(scores, positions) if p != -1]
    if not valid:
        return []

    valid_positions = [p for _, p in valid]

    # Fetch matching chunks + filenames from DB
    rows = (
        await db.execute(
            select(ChunkDB, DocumentDB.filename)
            .join(DocumentDB, ChunkDB.document_id == DocumentDB.id)
            .where(ChunkDB.vault_id == vault_id)
            .where(ChunkDB.faiss_index.in_(valid_positions))
        )
    ).all()

    # Build position → (chunk, filename) map
    chunk_map: dict[int, tuple[ChunkDB, str]] = {
        row.ChunkDB.faiss_index: (row.ChunkDB, row.filename) for row in rows
    }

    results = []
    for score, pos in valid:
        # Cosine sim in [-1,1]; after normalization semantic embeddings typically [0,1]
        if score < threshold:
            continue
        if pos not in chunk_map:
            continue

        chunk_db, filename = chunk_map[pos]

        # Decrypt
        try:
            content = decrypt_bytes(key, chunk_db.nonce, chunk_db.content_encrypted).decode("utf-8")
        except Exception:
            logger.warning(f"Decryption failed for chunk {chunk_db.id}")
            content = "[DECRYPTION FAILED]"

        # Tags stored as JSON array
        try:
            tags = json.loads(chunk_db.tags) if chunk_db.tags else []
        except (json.JSONDecodeError, TypeError):
            tags = []

        results.append(
            {
                "chunk_id": chunk_db.id,
                "document_id": chunk_db.document_id,
                "filename": filename,
                "content": content,
                "score": round(score, 4),
                "section": chunk_db.section,
                "tags": tags,
                "language": chunk_db.language,
            }
        )

    results.sort(key=lambda x: x["score"], reverse=True)
    return results
