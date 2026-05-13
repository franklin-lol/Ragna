"""
Search orchestration.
Combines vector search with database retrieval and decryption.
"""
from typing import List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database import ChunkDB, DocumentDB
from modules.embeddings import generate_query_embedding
from modules.vector_store import search_index
from modules.encryption import decrypt_bytes
import numpy as np

async def perform_search(
    db: AsyncSession,
    vault_id: str,
    encryption_key: bytes,
    query: str,
    top_k: int = 10,
    threshold: float = 0.3
) -> List[dict]:
    """
    1. Generate embedding for query.
    2. Search FAISS index.
    3. Fetch chunks from DB.
    4. Decrypt content.
    5. Return formatted results.
    """
    query_emb = generate_query_embedding(query)
    distances, positions = search_index(vault_id, query_emb, top_k)
    
    if len(positions) == 0:
        return []

    # Map FAISS positions back to ChunkDB entries
    # In a real app, we might store a mapping table or use FAISS IDs.
    # Here we assume faiss_index column in ChunkDB matches.
    
    valid_positions = [int(p) for p in positions if p != -1]
    if not valid_positions:
        return []

    # Fetch chunks from DB that match the positions
    stmt = (
        select(ChunkDB, DocumentDB.filename)
        .join(DocumentDB, ChunkDB.document_id == DocumentDB.id)
        .where(ChunkDB.vault_id == vault_id)
        .where(ChunkDB.faiss_index.in_(valid_positions))
    )
    
    result = await db.execute(stmt)
    chunks_with_filenames = result.all()
    
    # Create a map for easy lookup by position
    chunks_map = {c.ChunkDB.faiss_index: (c.ChunkDB, c.filename) for c in chunks_with_filenames}
    
    search_results = []
    for dist, pos in zip(distances, positions):
        if pos == -1 or pos not in chunks_map:
            continue
            
        # FAISS IndexFlatL2 returns L2 distance. Smaller is better.
        # Simple similarity score: 1 / (1 + distance)
        score = 1.0 / (1.0 + float(dist))
        
        if score < threshold:
            continue
            
        chunk_db, filename = chunks_map[pos]
        
        # Decrypt content
        try:
            content = decrypt_bytes(
                encryption_key, 
                chunk_db.nonce, 
                chunk_db.content_encrypted
            ).decode("utf-8")
        except Exception:
            content = "[DECRYPTION FAILED]"

        search_results.append({
            "chunk_id": chunk_db.id,
            "document_id": chunk_db.document_id,
            "filename": filename,
            "content": content,
            "score": score,
            "section": chunk_db.section,
            "tags": chunk_db.tags.split(",") if chunk_db.tags else [],
            "language": chunk_db.language
        })

    # Sort by score descending
    search_results.sort(key=lambda x: x["score"], reverse=True)
    
    return search_results
