"""
AI Knowledge Compiler — FastAPI backend.
"""
import asyncio
import logging
import os
import secrets
import shutil
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, List

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Header,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import ChunkDB, DocumentDB, SessionLocal, VaultDB, get_db, init_db
from models import (
    DocumentResponse,
    SearchRequest,
    SearchResponse,
    SearchResult,
    UnlockResponse,
    VaultCreate,
    VaultResponse,
    VaultUnlock,
)
from modules.encryption import derive_key, generate_salt
from modules.ingestion import run_pipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── Session store ─────────────────────────────────────────────────────────────
# { token: { vault_id, key, created_at } }
_sessions: dict[str, dict] = {}

def _create_session(vault_id: str, key: bytes) -> str:
    token = secrets.token_urlsafe(32)
    _sessions[token] = {"vault_id": vault_id, "key": key, "created_at": time.time()}
    return token

def _get_session(token: str) -> dict | None:
    s = _sessions.get(token)
    if s is None:
        return None
    if time.time() - s["created_at"] > settings.SESSION_TTL:
        del _sessions[token]
        return None
    return s

def _purge_expired():
    now = time.time()
    expired = [t for t, s in _sessions.items() if now - s["created_at"] > settings.SESSION_TTL]
    for t in expired:
        del _sessions[t]


# ─── Auth dependency ─────────────────────────────────────────────────────────

async def require_session(
    x_session_token: Annotated[str | None, Header()] = None
) -> dict:
    """
    Reads X-Session-Token header.
    Returns session dict {vault_id, key}.
    """
    if not x_session_token:
        raise HTTPException(status_code=401, detail="Missing X-Session-Token header")
    session = _get_session(x_session_token)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return session


# ─── Lifespan ────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # Pre-warm embedding model in background
    asyncio.create_task(_warm_model())
    yield


async def _warm_model():
    """Pre-load sentence-transformer model on startup to avoid cold start on first search."""
    try:
        from modules.embeddings import get_model
        await asyncio.to_thread(get_model)
        logger.info("Embedding model loaded.")
    except Exception as e:
        logger.warning(f"Model pre-warm failed: {e}")


# ─── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(title=settings.APP_NAME, version=settings.VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Health ───────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "version": settings.VERSION}


# ─── Vaults ───────────────────────────────────────────────────────────────────

@app.post("/vaults", response_model=VaultResponse, status_code=201)
async def create_vault(vault: VaultCreate, db: AsyncSession = Depends(get_db)):
    stmt = select(VaultDB).where(VaultDB.name == vault.name)
    if (await db.execute(stmt)).scalar_one_or_none():
        raise HTTPException(400, "Vault with this name already exists")

    salt = generate_salt()
    new_vault = VaultDB(name=vault.name, argon2_salt=salt)
    db.add(new_vault)
    await db.commit()
    await db.refresh(new_vault)

    return VaultResponse(
        id=new_vault.id,
        name=new_vault.name,
        created_at=new_vault.created_at,
    )


@app.get("/vaults", response_model=List[VaultResponse])
async def list_vaults(db: AsyncSession = Depends(get_db)):
    vaults = (await db.execute(select(VaultDB))).scalars().all()
    _purge_expired()

    result = []
    for v in vaults:
        doc_count = (
            await db.execute(
                select(func.count(DocumentDB.id)).where(DocumentDB.vault_id == v.id)
            )
        ).scalar()
        chunk_count = (
            await db.execute(
                select(func.count(ChunkDB.id)).where(ChunkDB.vault_id == v.id)
            )
        ).scalar()
        result.append(
            VaultResponse(
                id=v.id,
                name=v.name,
                created_at=v.created_at,
                document_count=doc_count or 0,
                chunk_count=chunk_count or 0,
            )
        )
    return result


@app.post("/vaults/{vault_id}/unlock", response_model=UnlockResponse)
async def unlock_vault(
    vault_id: str, data: VaultUnlock, db: AsyncSession = Depends(get_db)
):
    vault = (
        await db.execute(select(VaultDB).where(VaultDB.id == vault_id))
    ).scalar_one_or_none()

    if not vault:
        raise HTTPException(404, "Vault not found")

    key = await asyncio.to_thread(derive_key, data.password, vault.argon2_salt)
    token = _create_session(vault_id, key)

    return UnlockResponse(session_token=token, vault_id=vault_id, vault_name=vault.name)


@app.post("/vaults/{vault_id}/lock", status_code=204)
async def lock_vault(
    vault_id: str,
    session: dict = Depends(require_session),
):
    """Invalidate the current session token."""
    # We can't easily get the token from the dependency, so we purge by vault_id
    to_delete = [t for t, s in _sessions.items() if s["vault_id"] == vault_id]
    for t in to_delete:
        del _sessions[t]


@app.delete("/vaults/{vault_id}", status_code=204)
async def delete_vault(
    vault_id: str,
    db: AsyncSession = Depends(get_db),
):
    from modules.vector_store import delete_vault_index

    vault = (
        await db.execute(select(VaultDB).where(VaultDB.id == vault_id))
    ).scalar_one_or_none()

    if not vault:
        raise HTTPException(404, "Vault not found")

    # Invalidate sessions
    to_delete = [t for t, s in _sessions.items() if s["vault_id"] == vault_id]
    for t in to_delete:
        del _sessions[t]

    # Delete from DB (cascades to documents and chunks)
    await db.delete(vault)
    await db.commit()

    # Delete FAISS index
    await asyncio.to_thread(delete_vault_index, vault_id)


# ─── Documents ────────────────────────────────────────────────────────────────

@app.get("/vaults/{vault_id}/documents", response_model=List[DocumentResponse])
async def list_documents(
    vault_id: str,
    session: dict = Depends(require_session),
    db: AsyncSession = Depends(get_db),
):
    if session["vault_id"] != vault_id:
        raise HTTPException(403, "Token does not belong to this vault")

    docs = (
        await db.execute(
            select(DocumentDB)
            .where(DocumentDB.vault_id == vault_id)
            .order_by(DocumentDB.created_at.desc())
        )
    ).scalars().all()

    return [
        DocumentResponse(
            id=d.id,
            vault_id=d.vault_id,
            filename=d.filename,
            file_type=d.file_type,
            chunk_count=d.chunk_count,
            status=d.status,
            error=d.error,
            created_at=d.created_at,
        )
        for d in docs
    ]


@app.get("/documents/{doc_id}", response_model=DocumentResponse)
async def get_document(
    doc_id: str,
    session: dict = Depends(require_session),
    db: AsyncSession = Depends(get_db),
):
    doc = (
        await db.execute(select(DocumentDB).where(DocumentDB.id == doc_id))
    ).scalar_one_or_none()

    if not doc:
        raise HTTPException(404, "Document not found")
    if doc.vault_id != session["vault_id"]:
        raise HTTPException(403, "Access denied")

    return DocumentResponse(
        id=doc.id,
        vault_id=doc.vault_id,
        filename=doc.filename,
        file_type=doc.file_type,
        chunk_count=doc.chunk_count,
        status=doc.status,
        error=doc.error,
        created_at=doc.created_at,
    )


@app.delete("/documents/{doc_id}", status_code=204)
async def delete_document(
    doc_id: str,
    session: dict = Depends(require_session),
    db: AsyncSession = Depends(get_db),
):
    doc = (
        await db.execute(select(DocumentDB).where(DocumentDB.id == doc_id))
    ).scalar_one_or_none()

    if not doc:
        raise HTTPException(404, "Document not found")
    if doc.vault_id != session["vault_id"]:
        raise HTTPException(403, "Access denied")

    await db.delete(doc)
    await db.commit()


# ─── Ingest ───────────────────────────────────────────────────────────────────

@app.post("/ingest", response_model=DocumentResponse, status_code=202)
async def ingest_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    session: dict = Depends(require_session),
    db: AsyncSession = Depends(get_db),
):
    """
    Accepts upload, creates document record (status=pending), returns immediately.
    Processing runs in background via BackgroundTasks + asyncio.to_thread.
    """
    vault_id = session["vault_id"]
    key = session["key"]

    ext = os.path.splitext(file.filename or "file.bin")[1].lstrip(".").lower() or "bin"

    # Persist to temp location (survives beyond request lifetime)
    temp_path = settings.DATA_DIR / "uploads" / f"{uuid.uuid4()}_{file.filename}"
    with open(temp_path, "wb") as buf:
        shutil.copyfileobj(file.file, buf)

    # Dedup check: compute hash
    import hashlib
    with open(temp_path, "rb") as f:
        file_hash = hashlib.sha256(f.read()).hexdigest()

    existing = (
        await db.execute(
            select(DocumentDB).where(
                DocumentDB.vault_id == vault_id,
                DocumentDB.file_hash == file_hash,
            )
        )
    ).scalar_one_or_none()

    if existing:
        temp_path.unlink(missing_ok=True)
        return DocumentResponse(
            id=existing.id,
            vault_id=existing.vault_id,
            filename=existing.filename,
            file_type=existing.file_type,
            chunk_count=existing.chunk_count,
            status=existing.status,
            error="Duplicate file — already indexed",
            created_at=existing.created_at,
        )

    # Create document record
    doc = DocumentDB(
        vault_id=vault_id,
        filename=file.filename or "unknown",
        file_type=ext,
        file_hash=file_hash,
        status="pending",
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    doc_id = doc.id

    # Kick off background pipeline
    background_tasks.add_task(
        run_pipeline,
        doc_id=doc_id,
        vault_id=vault_id,
        key=key,
        file_path=str(temp_path),
        filename=file.filename or "unknown",
        file_type=ext,
    )

    return DocumentResponse(
        id=doc.id,
        vault_id=doc.vault_id,
        filename=doc.filename,
        file_type=doc.file_type,
        chunk_count=0,
        status="pending",
        created_at=doc.created_at,
    )


# ─── Search ───────────────────────────────────────────────────────────────────

@app.post("/search", response_model=SearchResponse)
async def search(
    request: SearchRequest,
    session: dict = Depends(require_session),
    db: AsyncSession = Depends(get_db),
):
    from modules.search import perform_search

    vault_id = session["vault_id"]
    key = session["key"]

    results = await perform_search(
        db, vault_id, key, request.query, request.top_k, request.threshold
    )

    return SearchResponse(
        query=request.query,
        results=[SearchResult(**r) for r in results],
        total=len(results),
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=True)
