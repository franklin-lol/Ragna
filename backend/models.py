from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
import uuid


# ─── Vault ───────────────────────────────────────────────────────────────────

class VaultCreate(BaseModel):
    name: str
    password: str

class VaultUnlock(BaseModel):
    password: str

class VaultRename(BaseModel):
    name: str

class VaultResponse(BaseModel):
    id: str
    name: str
    created_at: datetime
    document_count: int = 0
    chunk_count: int = 0

class UnlockResponse(BaseModel):
    session_token: str
    vault_id: str
    vault_name: str


# ─── Document ─────────────────────────────────────────────────────────────────

class DocumentResponse(BaseModel):
    id: str
    vault_id: str
    filename: str
    file_type: str
    chunk_count: int
    status: str
    error: Optional[str] = None
    summary: Optional[str] = None
    created_at: datetime


# ─── Entity ───────────────────────────────────────────────────────────────────

class EntityResponse(BaseModel):
    id: str
    document_id: str
    text: str
    entity_type: str
    subtype: Optional[str]
    frequency: int


# ─── Search ───────────────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str
    top_k: int = Field(default=10, ge=1, le=50)
    threshold: float = Field(default=0.45, ge=0.0, le=1.0)

    # If True and cross-encoder model available:
    #   - FAISS fetches top_k * RERANK_FACTOR candidates (expanded recall)
    #   - Cross-encoder scores all candidates against query
    #   - Results re-sorted by cross-encoder score, top_k returned
    # Falls back to cosine-only silently if model unavailable.
    # Latency: +50–200ms on CPU for typical top_k. Worth it for precision.
    rerank: bool = Field(default=False)


class SearchResult(BaseModel):
    chunk_id: str
    document_id: str
    filename: str
    content: str
    score: float
    relevance_label: str  # Strong / Good / Weak / Marginal
    section: Optional[str]
    tags: list[str]
    language: Optional[str]


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
    total: int
    reranked: bool = False  # True if cross-encoder was applied
