"""
Ingestion pipeline — background task.
extract → OCR fallback → clean → chunk → embed → entities → summarize → encrypt → store → index

KEY FIX: Short-lived DB sessions.
  BEFORE: one session held open for entire pipeline duration (OCR + embed = 30-60s each)
          → QueuePool exhaustion on batch uploads
  AFTER:  session opened only for atomic DB writes (< 1ms each)
          Heavy CPU work (OCR, embeddings, FAISS) runs with NO open session
          Session lifecycle: open → write status → close → [heavy work] → open → write results → close
"""
import asyncio
import hashlib
import json
import logging
import os

import numpy as np

from config import settings
from database import ChunkDB, DocumentDB, EntityDB, EntityRelationDB, SessionLocal
from modules.chunking import chunk_document
from modules.cleaning import clean_text
from modules.embeddings import generate_embeddings
from modules.encryption import encrypt_bytes
from modules.entities import extract_entities
from modules.extraction import extract, is_image_type
from modules.ocr import run_ocr
from modules.summarizer import generate_summary
from modules.vector_store import add_to_index
from modules.entity_topology import build_cooccurrence_graph

logger = logging.getLogger(__name__)

_TECH_KW = frozenset({
    "python", "javascript", "typescript", "rust", "go", "java", "docker",
    "kubernetes", "redis", "postgres", "sqlite", "mongodb", "fastapi",
    "django", "react", "vue", "llm", "ai", "ml", "rag", "embedding", "vector",
    "api", "rest", "grpc", "jwt", "auth", "encryption", "security",
})


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
    # ── Session 1: mark processing (open → write → close immediately) ────────
    async with SessionLocal() as db:
        from sqlalchemy import select
        doc = (await db.execute(
            select(DocumentDB).where(DocumentDB.id == doc_id)
        )).scalar_one()
        doc.status = "processing"
        await db.commit()
        doc_id_str = doc.id  # capture before session closes

    # ── Heavy work — NO open DB session ──────────────────────────────────────
    error: str | None = None
    chunks_data: list = []
    entities_data: list = []
    summary: str | None = None
    language: str | None = None
    faiss_ids: list[int] = []
    embeddings_arr: np.ndarray | None = None

    try:
        chunks_data, entities_data, edges_data, summary, language, faiss_ids, embeddings_arr = \
            await _heavy_work(
                file_path, filename, file_type,
                vault_id, key,
                summary_mode, ollama_url, ollama_model,
            )
    except Exception as exc:
        logger.exception(f"Pipeline failed: {filename}")
        error = str(exc)[:500]
        edges_data = []
    finally:
        # Always clean up temp file — regardless of success/failure
        try:
            os.unlink(file_path)
        except OSError:
            pass

    # ── Session 2: persist results (open → bulk write → close) ───────────────
    async with SessionLocal() as db:
        from sqlalchemy import select
        doc = (await db.execute(
            select(DocumentDB).where(DocumentDB.id == doc_id_str)
        )).scalar_one()

        if error:
            doc.status = "failed"
            doc.error = error
            await db.commit()
            return

        if not chunks_data:
            # Extraction produced nothing (empty file, unsupported content)
            doc.status = "indexed"
            doc.chunk_count = 0
            doc.summary = summary
            await db.commit()
            return

        # Bulk-insert chunks
        for i, (chunk, faiss_id, emb) in enumerate(
            zip(chunks_data, faiss_ids, embeddings_arr)
        ):
            content_bytes = chunk["content"].encode("utf-8")
            nonce, encrypted = encrypt_bytes(key, content_bytes)
            lower = chunk["content"].lower()
            tags = sorted({kw for kw in _TECH_KW if kw in lower})[:8]

            db.add(ChunkDB(
                vault_id=vault_id,
                document_id=doc_id_str,
                content_encrypted=encrypted,
                nonce=nonce,
                content_hash=hashlib.sha256(content_bytes).hexdigest(),
                embedding_blob=emb.astype("float32").tobytes(),
                section=chunk.get("section"),
                tags=json.dumps(tags),
                language=language,
                chunk_index=i,
                faiss_index=faiss_id,
            ))

        # Bulk-insert entities
        for ent in entities_data:
            db.add(EntityDB(
                vault_id=vault_id,
                document_id=doc_id_str,
                text=ent["text"],
                entity_type=ent["type"],
                subtype=ent.get("subtype"),
                frequency=ent["frequency"],
            ))

        # Bulk-insert entity co-occurrence edges
        for entity_a, entity_b, weight in edges_data:
            db.add(EntityRelationDB(
                vault_id=vault_id,
                document_id=doc_id_str,
                entity_a=entity_a,
                entity_b=entity_b,
                weight=weight,
            ))

        doc.status = "indexed"
        doc.chunk_count = len(chunks_data)
        doc.summary = summary
        await db.commit()

    logger.info(
        f"Indexed '{filename}': {len(chunks_data)} chunks, "
        f"{len(entities_data)} entities, lang={language}, mode={summary_mode}"
    )


async def _heavy_work(
    file_path: str,
    filename: str,
    file_type: str,
    vault_id: str,
    key: bytes,
    summary_mode: str,
    ollama_url: str,
    ollama_model: str,
) -> tuple:
    """
    All CPU/IO-heavy work — runs with NO open DB session.
    Returns: (chunks, entities, edges, summary, language, faiss_ids, embeddings)
    """
    # ── 1. Extract ────────────────────────────────────────────────────────────
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
        return [], [], None, None, [], np.array([])

    # ── 2. Clean ──────────────────────────────────────────────────────────────
    sections = [(t, await asyncio.to_thread(clean_text, txt)) for t, txt in sections]
    sections = [(t, txt) for t, txt in sections if txt.strip()]
    if not sections:
        return [], [], None, None, [], np.array([])

    full_text = "\n\n".join(txt for _, txt in sections)

    # ── 3. Parallel: summarize + language detect + NER ────────────────────────
    # These are independent — run concurrently to cut total latency
    async def _detect_lang():
        try:
            from langdetect import detect
            return await asyncio.to_thread(detect, full_text[:2000])
        except Exception:
            return None

    summary_coro   = generate_summary(full_text[:6000], mode=summary_mode,
                                      ollama_url=ollama_url, ollama_model=ollama_model)
    lang_coro      = _detect_lang()
    entities_coro  = asyncio.to_thread(extract_entities, full_text[:10000])

    summary, language, raw_entities = await asyncio.gather(
        summary_coro, lang_coro, entities_coro
    )

    # ── 4. Chunk ──────────────────────────────────────────────────────────────
    chunks = await asyncio.to_thread(chunk_document, sections)
    if not chunks:
        return [], raw_entities, summary, language, [], np.array([])

    # ── 5. Embed ──────────────────────────────────────────────────────────────
    embed_texts = [c.get("embed_content", c["content"]) for c in chunks]
    embeddings: np.ndarray = await asyncio.to_thread(generate_embeddings, embed_texts)

    # ── 6. FAISS ──────────────────────────────────────────────────────────────
    faiss_ids = await asyncio.to_thread(add_to_index, vault_id, embeddings)

    # ── 7. Entity co-occurrence graph ──────────────────────────────────────────
    edges = build_cooccurrence_graph(chunks, raw_entities)

    return chunks, raw_entities, edges, summary, language, faiss_ids, embeddings
