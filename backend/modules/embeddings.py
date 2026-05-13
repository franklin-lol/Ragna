"""
Embedding generation using sentence-transformers.
Supports local models and batch processing.
"""
from sentence_transformers import SentenceTransformer
import numpy as np
from typing import List
from config import settings

_model = None

def get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer(settings.EMBEDDING_MODEL)
    return _model

def generate_embeddings(texts: List[str]) -> np.ndarray:
    """
    Generate embeddings for a list of strings.
    Returns a numpy array of shape (len(texts), embedding_dim).
    """
    model = get_model()
    embeddings = model.encode(
        texts, 
        batch_size=settings.EMBEDDING_BATCH_SIZE,
        show_progress_bar=False,
        convert_to_numpy=True
    )
    return embeddings

def generate_query_embedding(query: str) -> np.ndarray:
    """Generate embedding for a single search query."""
    model = get_model()
    return model.encode(query, convert_to_numpy=True)
