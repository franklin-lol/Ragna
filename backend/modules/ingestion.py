"""
Ingestion pipeline — background task.
extract → OCR fallback → clean → chunk → embed → entities → summarize → encrypt → store → index
"""
import asyncio
import hashlib
import json
import logging

import numpy as np
from sqlalchemy import select

from config import settings
from database import ChunkDB, DocumentDB, EntityDB, SessionLocal
from modules.chunking import chunk_document
from modules.cleaning import clean_text
from modules.embeddings import generate_embeddings
from modules.encryption import encrypt_bytes
from modules.entities import extract_entities
from modules.extraction import extract, is_image_type
from modules.ocr import run_ocr
from modules.summarizer import generate_summary
from modules.vector_store import add_to_index

logger = logging.getLogger(__name__)


async def run_pipeline(
    doc_id: str,
    vault_id: str,
    key: bytes,
    file_path: str,
    filename: str,
    file_type: str,
    summary_mode: str = "extractive",
    ollama_url: str = "http://localhost:11434",
    ollama_model: str = "llama3.2:3b",
) -> None:
    async with SessionLocal() as db:
        doc = (await db.execute(select(DocumentDB).where(DocumentDB.id == doc_id))).scalar_one()
        doc.status = "processing"
        await db.commit()
        try:
            await _run(db, doc, vault_id, key, file_path, filename, file_type,
                       summary_mode, ollama_url, ollama_model)
        except Exception as exc:
            logger.exception(f"Pipeline failed: {filename}")
            doc.status = "failed"
            doc.error = str(exc)[:500]
            await db.commit()
        finally:
            import os
            try:
                os.unlink(file_path)
            except OSError:
                pass


async def _run(db, doc, vault_id, key, file_path, filename, file_type,
               summary_mode, ollama_url, ollama_model):
    # ── 1. Extract ──────────────────────────────────────────────────────────
    if is_image_type(file_type):
        ocr_text = await asyncio.to_thread(run_ocr, file_path)
        sections = [("OCR", ocr_text)] if ocr_text.strip() else []
    else:
        sections = await asyncio.to_thread(extract, file_path, file_type)
        total_text = " ".join(s[1] for s in sections)
        if len(total_text.strip()) < 100 and file_type.lower() == "pdf":
            logger.info(f"Low-text PDF {filename} — OCR fallback")
            ocr = await asyncio.to_thread(run_ocr, file_path)
            if ocr.strip():
                sections.append(("OCR Fallback", ocr))

    if not sections:
        doc.status = "indexed"
        doc.chunk_count = 0
        await db.commit()
        return

    # ── 2. Clean ─────────────────────────────────────────────────────────────
    sections = [(t, await asyncio.to_thread(clean_text, txt)) for t, txt in sections]
    sections = [(t, txt) for t, txt in sections if txt.strip()]

    full_text = "\n\n".join(txt for _, txt in sections)

    # ── 3. Summarize (async — may call Ollama) ───────────────────────────────
    summary = await generate_summary(
        full_text[:6000],
        mode=summary_mode,
        ollama_url=ollama_url,
        ollama_model=ollama_model,
    )

    # ── 4. Language detection ────────────────────────────────────────────────
    language: str | None = None
    try:
        from langdetect import detect
        language = await asyncio.to_thread(detect, full_text[:2000])
    except Exception:
        pass

    # ── 5. Entity extraction ─────────────────────────────────────────────────
    raw_entities = await asyncio.to_thread(extract_entities, full_text[:10000])

    # ── 6. Chunk (hierarchical) ───────────────────────────────────────────────
    chunks = await asyncio.to_thread(chunk_document, sections)
    if not chunks:
        doc.status = "indexed"
        doc.chunk_count = 0
        doc.summary = summary or None
        await db.commit()
        return

    # ── 7. Embed ─────────────────────────────────────────────────────────────
    # CHANGED: use embed_content (section-prefixed) for embedding generation.
    # embed_content = "[Section Title]: chunk text" — encodes topic + content.
    # Stored/encrypted content is always the clean chunk text (no prefix).
    embed_texts = [c.get("embed_content", c["content"]) for c in chunks]
    embeddings: np.ndarray = await asyncio.to_thread(generate_embeddings, embed_texts)

    # ── 8. FAISS index ───────────────────────────────────────────────────────
    faiss_ids = await asyncio.to_thread(add_to_index, vault_id, embeddings)

    # ── 9. Persist chunks (encrypted) ────────────────────────────────────────
    import re
    _TECH_KW = {
        "python", "javascript", "typescript", "rust", "go", "java", "docker",
        "kubernetes", "redis", "postgres", "sqlite", "mongodb", "fastapi",
        "django", "react", "vue", "llm", "ai", "ml", "rag", "embedding", "vector",
        "api", "rest", "grpc", "jwt", "auth", "encryption", "security",
    }

    for i, (chunk, pos, emb) in enumerate(zip(chunks, faiss_ids, embeddings)):
        # Store clean content only — NOT embed_content (no prefix in DB)
        content_bytes = chunk["content"].encode("utf-8")
        content_hash = hashlib.sha256(content_bytes).hexdigest()
        nonce, encrypted = encrypt_bytes(key, content_bytes)

        lower = chunk["content"].lower()
        tags = sorted({kw for kw in _TECH_KW if kw in lower})[:8]

        chunk_db = ChunkDB(
            vault_id=vault_id,
            document_id=doc.id,
            content_encrypted=encrypted,
            nonce=nonce,
            content_hash=content_hash,
            embedding_blob=emb.astype("float32").tobytes(),
            section=chunk.get("section"),
            tags=json.dumps(tags),
            language=language,
            chunk_index=i,
            faiss_index=pos,
        )
        db.add(chunk_db)

    # ── 10. Persist entities ──────────────────────────────────────────────────
    for ent in raw_entities:
        db.add(EntityDB(
            vault_id=vault_id,
            document_id=doc.id,
            text=ent["text"],
            entity_type=ent["type"],
            subtype=ent.get("subtype"),
            frequency=ent["frequency"],
        ))

    # ── 11. Finalise document ─────────────────────────────────────────────────
    doc.status = "indexed"
    doc.chunk_count = len(chunks)
    doc.summary = summary or None
    await db.commit()

    logger.info(
        f"Indexed '{filename}': {len(chunks)} chunks, "
        f"{len(raw_entities)} entities, lang={language}, "
        f"summary_mode={summary_mode}"
    )
