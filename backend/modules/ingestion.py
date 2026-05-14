"""
Ingestion pipeline — background task.
Runs: extract → OCR fallback → clean → chunk → embed → encrypt → store → index.
All blocking (CPU-bound) ops wrapped in asyncio.to_thread.
"""
import asyncio
import hashlib
import json
import logging
import os

from sqlalchemy import select

from database import ChunkDB, DocumentDB, SessionLocal
from modules.chunking import chunk_document
from modules.cleaning import clean_text
from modules.embeddings import generate_embeddings
from modules.encryption import encrypt_bytes
from modules.extraction import extract, is_image_type
from modules.ocr import run_ocr
from modules.vector_store import add_to_index

logger = logging.getLogger(__name__)

# ─── Language detection (optional) ──────────────────────────────────────────

def _detect_language(text: str) -> str | None:
    try:
        from langdetect import detect
        return detect(text[:2000])
    except Exception:
        return None


# ─── Auto-tags (lightweight keyword extraction) ──────────────────────────────

_TECH_KEYWORDS = {
    "python", "javascript", "typescript", "rust", "golang", "java", "c++",
    "docker", "kubernetes", "redis", "postgres", "sqlite", "mongodb",
    "fastapi", "django", "react", "vue", "tailwind", "graphql", "rest",
    "api", "llm", "ai", "ml", "rag", "embedding", "vector", "database",
    "encryption", "security", "authentication", "jwt", "oauth",
    "async", "concurrency", "microservice", "devops", "ci/cd",
}

def _extract_tags(text: str) -> list[str]:
    lower = text.lower()
    return sorted({kw for kw in _TECH_KEYWORDS if kw in lower})[:10]


# ─── Background pipeline entry point ─────────────────────────────────────────

async def run_pipeline(
    doc_id: str,
    vault_id: str,
    key: bytes,
    file_path: str,
    filename: str,
    file_type: str,
) -> None:
    """
    Top-level coroutine called by BackgroundTasks.
    Opens its own DB session (request session is already closed).
    """
    async with SessionLocal() as db:
        # Mark as processing
        doc = (await db.execute(select(DocumentDB).where(DocumentDB.id == doc_id))).scalar_one()
        doc.status = "processing"
        await db.commit()

        try:
            await _run(db, doc, vault_id, key, file_path, filename, file_type)
        except Exception as exc:
            logger.exception(f"Pipeline failed for {filename}")
            doc.status = "failed"
            doc.error = str(exc)[:500]
            await db.commit()
        finally:
            # Always clean up temp file
            try:
                os.unlink(file_path)
            except OSError:
                pass


async def _run(db, doc, vault_id, key, file_path, filename, file_type):
    # ── 1. Extract ───────────────────────────────────────────────────────────
    if is_image_type(file_type):
        # Pure image → go straight to OCR
        ocr_text = await asyncio.to_thread(run_ocr, file_path)
        sections = [("OCR", ocr_text)] if ocr_text.strip() else []
    else:
        sections = await asyncio.to_thread(extract, file_path, file_type)

        # Low-text PDF/scan → fallback OCR
        total_text = " ".join(s[1] for s in sections)
        if len(total_text.strip()) < 100 and file_type.lower() in ("pdf",):
            logger.info(f"Low text for {filename}, running OCR fallback")
            ocr_text = await asyncio.to_thread(run_ocr, file_path)
            if ocr_text.strip():
                sections.append(("OCR Fallback", ocr_text))

    if not sections:
        doc.status = "indexed"
        doc.chunk_count = 0
        await db.commit()
        return

    # ── 2. Clean ─────────────────────────────────────────────────────────────
    sections = [(title, await asyncio.to_thread(clean_text, text)) for title, text in sections]
    sections = [(t, txt) for t, txt in sections if txt.strip()]

    # ── 3. Language detection (on combined sample) ───────────────────────────
    combined_sample = " ".join(s[1] for s in sections)[:3000]
    language = await asyncio.to_thread(_detect_language, combined_sample)

    # ── 4. Chunk ─────────────────────────────────────────────────────────────
    chunks = await asyncio.to_thread(chunk_document, sections)

    if not chunks:
        doc.status = "indexed"
        doc.chunk_count = 0
        await db.commit()
        return

    # ── 5. Embed ─────────────────────────────────────────────────────────────
    texts = [c["content"] for c in chunks]
    embeddings = await asyncio.to_thread(generate_embeddings, texts)

    # ── 6. FAISS index ───────────────────────────────────────────────────────
    faiss_positions = await asyncio.to_thread(add_to_index, vault_id, embeddings)

    # ── 7. Encrypt + persist chunks ──────────────────────────────────────────
    for i, (chunk, pos) in enumerate(zip(chunks, faiss_positions)):
        content_bytes = chunk["content"].encode("utf-8")
        content_hash = hashlib.sha256(content_bytes).hexdigest()
        nonce, encrypted_content = encrypt_bytes(key, content_bytes)
        tags = _extract_tags(chunk["content"])

        chunk_db = ChunkDB(
            vault_id=vault_id,
            document_id=doc.id,
            content_encrypted=encrypted_content,
            nonce=nonce,
            content_hash=content_hash,
            section=chunk.get("section"),
            tags=json.dumps(tags),
            language=language,
            chunk_index=i,
            faiss_index=pos,
        )
        db.add(chunk_db)

    doc.status = "indexed"
    doc.chunk_count = len(chunks)
    await db.commit()
    logger.info(f"Indexed {filename}: {len(chunks)} chunks, lang={language}")
