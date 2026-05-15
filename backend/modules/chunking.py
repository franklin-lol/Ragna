"""
Hierarchical context-preserving semantic chunking.

Architecture:
  Document
  └── Section  (title, raw text)
       └── Paragraphs  (double-newline splits)
            └── Chunks  (sentence-boundary splits, token budget)

Key upgrade over flat chunking:
  Each chunk carries embed_content = "[Section]: chunk text"
  This is used ONLY for embedding generation — NOT stored in the DB.
  The stored/encrypted content is always the clean chunk text.

  Effect: the embedding vector encodes both TOPIC (section) and CONTENT (chunk),
  significantly improving cosine recall for structured documents
  (technical docs, research papers, reports with distinct sections).

  Inspired by Anthropic's "Contextual Retrieval" approach but without LLM cost.

Chunk dict keys:
  content        — clean text, stored encrypted
  embed_content  — section-prefixed text, used for embedding ONLY
  section        — section title (or None)
  paragraph_idx  — paragraph position within section (0-indexed)
  length         — word count of content
"""
import logging
import re
from typing import Any

from config import settings

logger = logging.getLogger(__name__)


# ─── NLTK bootstrap ───────────────────────────────────────────────────────────

def _ensure_nltk() -> None:
    import nltk
    for resource in ("punkt", "punkt_tab"):
        try:
            nltk.data.find(f"tokenizers/{resource}")
            return
        except LookupError:
            pass
    try:
        nltk.download("punkt", quiet=True)
        nltk.download("punkt_tab", quiet=True)
    except Exception as e:
        logger.warning(f"NLTK download warning: {e}")


def _sent_tokenize(text: str) -> list[str]:
    _ensure_nltk()
    try:
        import nltk
        return nltk.sent_tokenize(text)
    except Exception:
        return [s.strip() for s in text.split(". ") if s.strip()]


# ─── Paragraph splitter ───────────────────────────────────────────────────────

_PARA_BREAK = re.compile(r"\n{2,}")


def _split_paragraphs(text: str) -> list[str]:
    """
    Split on double newlines. Single newlines preserved within paragraphs.
    Min paragraph length: 40 chars — shorter ones merged into neighbours.
    """
    raw = _PARA_BREAK.split(text)
    paras: list[str] = []
    pending = ""
    for p in raw:
        p = p.strip()
        if not p:
            continue
        if len(p) < 40 and paras:
            # Too short — append to previous paragraph
            paras[-1] = paras[-1] + " " + p
        elif pending:
            combined = pending + " " + p
            paras.append(combined)
            pending = ""
        else:
            paras.append(p)
    if pending:
        paras.append(pending)
    return paras if paras else [text]


# ─── Single-paragraph chunker ─────────────────────────────────────────────────

def _chunk_paragraph(
    text: str,
    section: str | None,
    para_idx: int,
    max_tokens: int,
    overlap: int,
) -> list[dict[str, Any]]:
    """
    Split one paragraph into token-budgeted chunks at sentence boundaries.
    Returns list of chunk dicts (content, embed_content, section, paragraph_idx, length).
    """
    sentences = _sent_tokenize(text)
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        return []

    # Build context prefix for embedding (section context injection)
    prefix = f"[{section}]: " if section else ""

    chunks: list[dict[str, Any]] = []
    buf: list[str] = []
    buf_tokens = 0

    def _flush(buf: list[str]) -> None:
        if not buf:
            return
        content = " ".join(buf)
        chunks.append({
            "content": content,
            "embed_content": prefix + content,
            "section": section,
            "paragraph_idx": para_idx,
            "length": len(content.split()),
        })

    for sentence in sentences:
        s_tokens = len(sentence.split())

        # Sentence alone exceeds budget → emit as its own chunk
        if s_tokens > max_tokens:
            if buf:
                _flush(buf)
                buf = buf[-overlap:] if overlap else []
                buf_tokens = sum(len(s.split()) for s in buf)
            _flush([sentence])
            continue

        if buf_tokens + s_tokens > max_tokens and buf:
            _flush(buf)
            buf = buf[-overlap:] if overlap else []
            buf_tokens = sum(len(s.split()) for s in buf)

        buf.append(sentence)
        buf_tokens += s_tokens

    _flush(buf)
    return chunks


# ─── Public API ───────────────────────────────────────────────────────────────

def chunk_document(sections: list[tuple[str | None, str]]) -> list[dict[str, Any]]:
    """
    Hierarchical chunking entry point.

    Input:  list of (section_title, raw_text)  — from extraction layer
    Output: list of chunk dicts with keys:
              content, embed_content, section, paragraph_idx, length

    Hierarchy:
      section → paragraphs → sentence-budgeted chunks

    The embed_content field carries the section context prefix for improved
    embedding quality. It is used in ingestion.py and discarded after embedding.
    """
    all_chunks: list[dict[str, Any]] = []
    max_tokens = settings.CHUNK_MAX_TOKENS
    overlap = settings.CHUNK_OVERLAP_SENTENCES

    for section_title, text in sections:
        if not text.strip():
            continue

        paragraphs = _split_paragraphs(text)

        for para_idx, para_text in enumerate(paragraphs):
            if not para_text.strip():
                continue
            new_chunks = _chunk_paragraph(
                para_text, section_title, para_idx, max_tokens, overlap
            )
            all_chunks.extend(new_chunks)

    # Deduplicate exact-duplicate content (can happen with OCR fallback)
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for chunk in all_chunks:
        key = chunk["content"][:200]
        if key not in seen:
            seen.add(key)
            deduped.append(chunk)

    if len(deduped) < len(all_chunks):
        logger.debug(f"Chunking: removed {len(all_chunks) - len(deduped)} duplicate chunks")

    return deduped
