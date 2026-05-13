from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
import uuid


def new_id() -> str:
    return str(uuid.uuid4())


# ─── Vault ───────────────────────────────────────────────────────────────────

class VaultCreate(BaseModel):
    name: str
    password: str

class VaultUnlock(BaseModel):
    password: str

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
    created_at: datetime

# ─── Search ───────────────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str
    top_k: int = Field(default=10, ge=1, le=50)
    threshold: float = Field(default=0.3, ge=0.0, le=1.0)

class SearchResult(BaseModel):
    chunk_id: str
    document_id: str
    filename: str
    content: str
    score: float
    section: Optional[str]
    tags: list[str]
    language: Optional[str]

class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
    total: int

# ─── Stats ────────────────────────────────────────────────────────────────────

class VaultStats(BaseModel):
    vault_id: str
    vault_name: str
    document_count: int
    chunk_count: int
    indexed_count: int
    processing_count: int
    failed_count: int