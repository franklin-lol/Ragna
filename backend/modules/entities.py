"""
Entity extraction module.
Tier-1: Rule-based tech/concept extraction (no deps — always works).
Tier-2: NLTK NE chunker for PERSON / ORGANIZATION (requires chunker data).
Tier-3: spaCy en_core_web_sm if installed (best quality).
"""
import logging
import re
from collections import defaultdict

logger = logging.getLogger(__name__)

# ─── Tech entity vocabulary ───────────────────────────────────────────────────

TECH_VOCAB: dict[str, str] = {
    # Languages
    **{k: "LANG" for k in [
        "python", "javascript", "typescript", "rust", "golang", "go",
        "java", "kotlin", "swift", "c++", "cpp", "c#", "csharp",
        "ruby", "php", "scala", "elixir", "haskell", "lua", "r",
        "bash", "shell", "sql", "graphql",
    ]},
    # Frameworks / Libraries
    **{k: "FRAMEWORK" for k in [
        "react", "vue", "angular", "svelte", "nextjs", "nuxt", "remix",
        "fastapi", "django", "flask", "starlette", "express", "nestjs",
        "pytorch", "tensorflow", "keras", "jax", "sklearn", "scikit-learn",
        "pandas", "numpy", "scipy", "langchain", "llamaindex", "haystack",
        "tailwind", "bootstrap", "shadcn",
    ]},
    # Databases / Storage
    **{k: "DATABASE" for k in [
        "postgresql", "postgres", "mysql", "sqlite", "mariadb",
        "mongodb", "redis", "elasticsearch", "opensearch", "cassandra",
        "neo4j", "faiss", "qdrant", "pinecone", "chromadb", "weaviate",
        "milvus", "pgvector", "clickhouse", "duckdb",
    ]},
    # Cloud / Infra
    **{k: "INFRA" for k in [
        "docker", "kubernetes", "k8s", "helm", "terraform", "ansible",
        "nginx", "traefik", "caddy", "kafka", "rabbitmq", "celery",
        "airflow", "prefect", "dagster", "prometheus", "grafana",
    ]},
    # Cloud providers
    **{k: "CLOUD" for k in [
        "aws", "gcp", "azure", "cloudflare", "vercel", "netlify",
        "heroku", "fly.io", "railway",
    ]},
    # AI / ML concepts
    **{k: "AI" for k in [
        "llm", "rag", "embedding", "transformer", "attention", "bert",
        "gpt", "llama", "mistral", "claude", "gemini", "openai", "anthropic",
        "ollama", "huggingface", "langchain", "vector", "faiss",
        "fine-tuning", "lora", "rlhf", "sft", "inference", "tokenizer",
    ]},
    # Protocols / Standards
    **{k: "PROTOCOL" for k in [
        "rest", "grpc", "websocket", "http", "https", "tcp", "udp",
        "oauth", "jwt", "tls", "ssl", "ssh", "s3", "smtp",
    ]},
}


def extract_entities(text: str) -> list[dict]:
    """
    Returns list of entity dicts:
    { text, type, subtype, frequency }
    Sorted by frequency desc, max 40 entries.
    """
    found: dict[str, dict] = {}

    # ── Tier 1: Rule-based tech extraction ──────────────────────────────────
    lower = text.lower()
    for keyword, subtype in TECH_VOCAB.items():
        pattern = r"(?<![a-zA-Z0-9_])" + re.escape(keyword) + r"(?![a-zA-Z0-9_])"
        matches = re.findall(pattern, lower)
        if matches:
            key = keyword
            if key in found:
                found[key]["frequency"] += len(matches)
            else:
                found[key] = {
                    "text": keyword,
                    "type": "TECH",
                    "subtype": subtype,
                    "frequency": len(matches),
                }

    # ── Tier 2: NLTK NER (PERSON / ORGANIZATION) ────────────────────────────
    _nltk_ner(text, found)

    # ── Tier 3: spaCy (if available — best quality) ──────────────────────────
    _spacy_ner(text, found)

    return sorted(found.values(), key=lambda x: -x["frequency"])[:40]


def _nltk_ner(text: str, found: dict) -> None:
    try:
        import nltk
        from nltk import ne_chunk, pos_tag, word_tokenize
        from nltk.tree import Tree

        # Ensure required data
        for res in ("punkt", "maxent_ne_chunker", "words", "averaged_perceptron_tagger"):
            try:
                nltk.data.find(f"taggers/{res}" if "tagger" in res else
                               f"chunkers/{res}" if "chunker" in res else
                               f"corpora/{res}" if res == "words" else
                               f"tokenizers/{res}")
            except LookupError:
                nltk.download(res, quiet=True)

        sample = text[:4000]
        tokens = word_tokenize(sample)
        tagged = pos_tag(tokens)
        tree = ne_chunk(tagged)

        for subtree in tree:
            if isinstance(subtree, Tree):
                label = subtree.label()  # PERSON / ORGANIZATION / GPE
                entity_text = " ".join(w for w, _ in subtree.leaves()).strip()
                if len(entity_text) < 2 or len(entity_text) > 60:
                    continue
                key = entity_text.lower()
                if key not in found:
                    found[key] = {
                        "text": entity_text,
                        "type": label,
                        "subtype": None,
                        "frequency": 1,
                    }
                else:
                    found[key]["frequency"] += 1

    except Exception as e:
        logger.debug(f"NLTK NER skipped: {e}")


def _spacy_ner(text: str, found: dict) -> None:
    try:
        import spacy
        nlp = spacy.load("en_core_web_sm")
        doc = nlp(text[:5000])
        for ent in doc.ents:
            if ent.label_ not in ("PERSON", "ORG", "GPE", "PRODUCT", "WORK_OF_ART"):
                continue
            entity_text = ent.text.strip()
            if len(entity_text) < 2 or len(entity_text) > 80:
                continue
            key = entity_text.lower()
            if key not in found:
                found[key] = {
                    "text": entity_text,
                    "type": ent.label_,
                    "subtype": None,
                    "frequency": 1,
                }
            else:
                found[key]["frequency"] += 1
    except Exception:
        pass  # spaCy not installed — silent skip
