"""
Section-aware semantic chunking.
Splits text at sentence boundaries respecting token budget.
Includes overlap to preserve cross-chunk context.
"""
import logging
from typing import Any

from config import settings

logger = logging.getLogger(__name__)


def _ensure_nltk():
    import nltk
    for resource in ("punkt", "punkt_tab"):
        try:
            nltk.data.find(f"tokenizers/{resource}")
            return  # found one, that's enough
        except LookupError:
            pass
    # Neither found — download punkt (works in all NLTK versions)
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
        # Hard fallback: split on ". "
        return [s.strip() for s in text.split(". ") if s.strip()]


def chunk_document(sections: list[tuple[str | None, str]]) -> list[dict[str, Any]]:
    """
    Input:  list of (section_title, raw_text)
    Output: list of chunk dicts with keys: content, section, length
    """
    all_chunks: list[dict[str, Any]] = []

    for section_title, text in sections:
        if not text.strip():
            continue

        sentences = _sent_tokenize(text)
        buf: list[str] = []
        buf_tokens = 0

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            s_tokens = len(sentence.split())

            # Single sentence exceeds budget → emit as its own chunk
            if s_tokens > settings.CHUNK_MAX_TOKENS:
                if buf:
                    all_chunks.append(_make_chunk(buf, section_title))
                    buf, buf_tokens = [], 0
                all_chunks.append(_make_chunk([sentence], section_title))
                continue

            if buf_tokens + s_tokens > settings.CHUNK_MAX_TOKENS and buf:
                all_chunks.append(_make_chunk(buf, section_title))
                # Keep overlap
                overlap = settings.CHUNK_OVERLAP_SENTENCES
                buf = buf[-overlap:] if overlap else []
                buf_tokens = sum(len(s.split()) for s in buf)

            buf.append(sentence)
            buf_tokens += s_tokens

        if buf:
            all_chunks.append(_make_chunk(buf, section_title))

    return all_chunks


def _make_chunk(sentences: list[str], section: str | None) -> dict[str, Any]:
    content = " ".join(sentences)
    return {
        "content": content,
        "section": section,
        "length": len(content.split()),
    }
