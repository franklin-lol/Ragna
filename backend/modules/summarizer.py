"""
Document summarization.
Mode A: Extractive (default, zero extra deps).
Mode B: Ollama (local LLM — requires Ollama running).
Mode C: OpenAI/compatible API.
"""
import asyncio
import logging
from typing import Literal

import httpx

logger = logging.getLogger(__name__)

SummaryMode = Literal["extractive", "ollama", "openai", "disabled"]


# ─── Extractive (always available) ───────────────────────────────────────────

def _ensure_nltk():
    import nltk
    for res, path in [
        ("punkt", "tokenizers/punkt"),
        ("punkt_tab", "tokenizers/punkt_tab"),
        ("stopwords", "corpora/stopwords"),
    ]:
        try:
            nltk.data.find(path)
        except LookupError:
            nltk.download(res, quiet=True)


def extractive_summary(text: str, n_sentences: int = 3, max_chars: int = 600) -> str:
    """
    Picks top-N sentences by TF-weighted score, preserving original order.
    Works on any language — stopword filtering is best-effort.
    """
    _ensure_nltk()
    from collections import Counter

    try:
        from nltk.tokenize import sent_tokenize, word_tokenize
    except Exception:
        # Hard fallback
        sents = [s.strip() for s in text.split(". ") if len(s.strip()) > 20]
        return " ".join(sents[:n_sentences])[:max_chars]

    sentences = [s.strip() for s in sent_tokenize(text) if len(s.strip()) > 20]
    if not sentences:
        return text[:max_chars]
    if len(sentences) <= n_sentences:
        return " ".join(sentences)[:max_chars]

    # Stopwords (fail silently)
    stop_words: set[str] = set()
    try:
        from nltk.corpus import stopwords
        stop_words = set(stopwords.words("english"))
    except Exception:
        pass

    tokens = word_tokenize(text.lower())
    freq = Counter(w for w in tokens if w.isalpha() and w not in stop_words and len(w) > 2)
    if not freq:
        return " ".join(sentences[:n_sentences])[:max_chars]

    max_freq = max(freq.values())
    norm_freq = {w: f / max_freq for w, f in freq.items()}

    scored: list[tuple[float, int, str]] = []
    for i, sent in enumerate(sentences):
        words = word_tokenize(sent.lower())
        score = sum(norm_freq.get(w, 0) for w in words if w.isalpha())
        score /= max(len(words), 1)  # Normalize by length
        if i < 3:
            score *= 1.4  # Position bonus
        scored.append((score, i, sent))

    top = sorted(scored, reverse=True)[:n_sentences]
    top.sort(key=lambda x: x[1])  # Restore order
    result = " ".join(s for _, _, s in top)
    return result[:max_chars]


# ─── Ollama (local LLM) ───────────────────────────────────────────────────────

async def ollama_summary(
    text: str,
    model: str = "llama3.2:3b",
    url: str = "http://localhost:11434",
    timeout: int = 30,
) -> str:
    prompt = (
        "You are a document summarizer. Write a concise 2-3 sentence summary "
        "of the following text. Focus on the main topic and key points. "
        "Be specific, not generic.\n\nText:\n"
        + text[:3000]
        + "\n\nSummary:"
    )
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{url}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
            )
            resp.raise_for_status()
            return resp.json().get("response", "").strip()
    except Exception as e:
        logger.warning(f"Ollama summary failed ({model}@{url}): {e}")
        return ""


# ─── Unified interface ────────────────────────────────────────────────────────

async def generate_summary(
    text: str,
    mode: SummaryMode = "extractive",
    ollama_url: str = "http://localhost:11434",
    ollama_model: str = "llama3.2:3b",
) -> str:
    """
    Generate document summary. Falls back to extractive if remote fails.
    Called from async context; extractive runs in to_thread.
    """
    if mode == "disabled" or not text.strip():
        return ""

    if mode == "ollama":
        result = await ollama_summary(text, model=ollama_model, url=ollama_url)
        if result:
            return result
        # Fallback
        logger.info("Ollama unavailable, falling back to extractive summary")

    # Extractive (default + fallback)
    return await asyncio.to_thread(extractive_summary, text)
