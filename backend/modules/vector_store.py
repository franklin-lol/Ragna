"""
Vector storage using FAISS.
Each vault has its own index file.
"""
import faiss
import numpy as np
import os
from pathlib import Path
from typing import List
from config import settings

def get_index_path(vault_id: str) -> Path:
    return settings.DATA_DIR / "vaults" / f"{vault_id}.index"

def create_index(vault_id: str):
    """Initialize a new FAISS index for a vault."""
    dimension = settings.EMBEDDING_DIM
    index = faiss.IndexFlatL2(dimension)
    
    path = get_index_path(vault_id)
    faiss.write_index(index, str(path))
    return index

def load_index(vault_id: str):
    """Load an existing FAISS index."""
    path = get_index_path(vault_id)
    if not path.exists():
        return create_index(vault_id)
    return faiss.read_index(str(path))

def save_index(vault_id: str, index):
    """Save the index to disk."""
    path = get_index_path(vault_id)
    faiss.write_index(index, str(path))

def add_to_index(vault_id: str, embeddings: np.ndarray) -> List[int]:
    """
    Add embeddings to the index and return their positions.
    """
    index = load_index(vault_id)
    start_pos = index.ntotal
    index.add(embeddings.astype('float32'))
    save_index(vault_id, index)
    
    return list(range(start_pos, index.ntotal))

def search_index(vault_id: str, query_embedding: np.ndarray, top_k: int = 10):
    """
    Search the index.
    Returns (distances, positions).
    """
    index = load_index(vault_id)
    if index.ntotal == 0:
        return np.array([]), np.array([])
        
    distances, positions = index.search(
        query_embedding.reshape(1, -1).astype('float32'), 
        top_k
    )
    return distances[0], positions[0]
