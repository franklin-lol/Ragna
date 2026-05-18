from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


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

class EntityResponse(BaseModel):
    id: str
    document_id: str
    text: str
    entity_type: str
    subtype: Optional[str]
    frequency: int

class SearchRequest(BaseModel):
    query: str
    top_k: int = Field(default=10, ge=1, le=50)
    threshold: float = Field(default=0.45, ge=0.0, le=1.0)
    rerank: bool = Field(default=False)

class SearchResult(BaseModel):
    chunk_id: str
    document_id: str
    filename: str
    content: str
    score: float
    relevance_label: str
    section: Optional[str]
    tags: list[str]
    language: Optional[str]

class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
    total: int
    reranked: bool = False

class WatcherCreate(BaseModel):
    folder_path: str = Field(min_length=1)
    recursive: bool = Field(default=False)

class WatcherResponse(BaseModel):
    id: str
    vault_id: str
    folder_path: str
    recursive: bool
    is_active: bool
    is_running: bool = False
    created_at: datetime


# ── Entity Graph ──────────────────────────────────────────────────────────────

class GraphNode(BaseModel):
    """Single entity node in the knowledge graph."""
    id: str              # entity text (lowercase, canonical)
    label: str           # display text
    entity_type: str     # TECH / PERSON / ORG / DATABASE / FRAMEWORK / AI / etc.
    subtype: Optional[str]
    frequency: int       # occurrence count across vault

class GraphEdge(BaseModel):
    """Co-occurrence relationship between two entity nodes."""
    source: str          # entity_a id
    target: str          # entity_b id
    weight: int          # number of chunks where both appear together

class GraphResponse(BaseModel):
    vault_id: str
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    # Convenience stats for frontend rendering decisions
    node_count: int = 0
    edge_count: int = 0

    def model_post_init(self, __context):
        self.node_count = len(self.nodes)
        self.edge_count = len(self.edges)
