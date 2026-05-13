"""
Ingestion orchestration.
Handles file upload -> extraction -> chunking -> embedding -> indexing.
"""
import hashlib
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from database import DocumentDB, ChunkDB
from modules.extraction import extract
from modules.ocr import run_ocr
from modules.chunking import chunk_document
from modules.embeddings import generate_embeddings
from modules.vector_store import add_to_index
from modules.encryption import encrypt_bytes
import logging

logger = logging.getLogger(__name__)

async def process_file(
    db: AsyncSession,
    vault_id: str,
    encryption_key: bytes,
    file_path: str,
    filename: str,
    file_type: str
) -> str:
    """
    Full pipeline for a single file.
    Returns the document ID.
    """
    # 1. Calculate file hash to prevent duplicates
    with open(file_path, "rb") as f:
        file_hash = hashlib.sha256(f.read()).hexdigest()
    
    # 2. Create document entry
    doc_db = DocumentDB(
        vault_id=vault_id,
        filename=filename,
        file_type=file_type,
        file_hash=file_hash,
        status="processing"
    )
    db.add(doc_db)
    await db.commit()
    await db.refresh(doc_db)
    
    try:
        # 3. Extract text
        sections = extract(file_path, file_type)
        
        # 4. If image/PDF and very little text, try OCR
        total_text = " ".join([s[1] for s in sections])
        if len(total_text.strip()) < 50 and file_type.lower() in ('.pdf', '.png', '.jpg', '.jpeg'):
            logger.info(f"Low text content for {filename}, running OCR...")
            ocr_text = run_ocr(file_path)
            if ocr_text:
                sections.append(("OCR Result", ocr_text))

        # 5. Chunking
        chunks = chunk_document(sections)
        doc_db.chunk_count = len(chunks)
        
        if not chunks:
            doc_db.status = "indexed"
            await db.commit()
            return doc_db.id

        # 6. Embeddings
        texts = [c["content"] for c in chunks]
        embeddings = generate_embeddings(texts)
        
        # 7. Add to FAISS Index
        faiss_positions = add_to_index(vault_id, embeddings)
        
        # 8. Encrypt and save chunks to DB
        for i, (chunk, pos) in enumerate(zip(chunks, faiss_positions)):
            content_bytes = chunk["content"].encode("utf-8")
            content_hash = hashlib.sha256(content_bytes).hexdigest()
            
            nonce, encrypted_content = encrypt_bytes(encryption_key, content_bytes)
            
            chunk_db = ChunkDB(
                vault_id=vault_id,
                document_id=doc_db.id,
                content_encrypted=encrypted_content,
                nonce=nonce,
                content_hash=content_hash,
                section=chunk["section"],
                chunk_index=i,
                faiss_index=pos
            )
            db.add(chunk_db)
            
        doc_db.status = "indexed"
        await db.commit()
        return doc_db.id
        
    except Exception as e:
        logger.exception(f"Failed to process {filename}")
        doc_db.status = "failed"
        doc_db.error = str(e)
        await db.commit()
        raise
