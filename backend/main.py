"""
AI Knowledge Compiler — FastAPI backend.
"""
import asyncio
import hashlib
import logging
import os
import secrets
import shutil
import time
import uuid
from contextlib import asynccontextmanager
from typing import Annotated, List, Optional

from fastapi import (
    BackgroundTasks, Depends, FastAPI, File, Header,
    HTTPException, UploadFile, status,
)
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import ChunkDB, DocumentDB, EntityDB, SessionLocal, VaultDB, get_db, init_db
from models import (
    DocumentResponse, EntityResponse, SearchRequest, SearchResponse,
    SearchResult, UnlockResponse, VaultCreate, VaultRename, VaultResponse, VaultUnlock,
)
from modules.encryption import derive_key, generate_salt
from modules.ingestion import run_pipeline
from modules.vector_store import delete_from_index, delete_vault_index, get_vault_index_size

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ─── Session store ────────────────────────────────────────────────────────────

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
    for t in [t for t, s in list(_sessions.items()) if now - s["created_at"] > settings.SESSION_TTL]:
        del _sessions[t]


# ─── Auth dependency ──────────────────────────────────────────────────────────

async def require_session(x_session_token: Annotated[str | None, Header()] = None) -> dict:
    if not x_session_token:
        raise HTTPException(401, "Missing X-Session-Token header")
    session = _get_session(x_session_token)
    if not session:
        raise HTTPException(401, "Invalid or expired session")
    return session


# ─── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    asyncio.create_task(_warm_model())
    yield


async def _warm_model():
    try:
        from modules.embeddings import get_model
        await asyncio.to_thread(get_model)
        logger.info("Embedding model ready.")
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
    if (await db.execute(select(VaultDB).where(VaultDB.name == vault.name))).scalar_one_or_none():
        raise HTTPException(400, "Vault name already exists")
    salt = generate_salt()
    v = VaultDB(name=vault.name.strip(), argon2_salt=salt)
    db.add(v)
    await db.commit()
    await db.refresh(v)
    return VaultResponse(id=v.id, name=v.name, created_at=v.created_at)


@app.get("/vaults", response_model=List[VaultResponse])
async def list_vaults(db: AsyncSession = Depends(get_db)):
    vaults = (await db.execute(select(VaultDB))).scalars().all()
    _purge_expired()
    result = []
    for v in vaults:
        doc_c = (await db.execute(select(func.count(DocumentDB.id)).where(DocumentDB.vault_id == v.id))).scalar()
        chunk_c = (await db.execute(select(func.count(ChunkDB.id)).where(ChunkDB.vault_id == v.id))).scalar()
        result.append(VaultResponse(id=v.id, name=v.name, created_at=v.created_at,
                                    document_count=doc_c or 0, chunk_count=chunk_c or 0))
    return result


@app.post("/vaults/{vault_id}/unlock", response_model=UnlockResponse)
async def unlock_vault(vault_id: str, data: VaultUnlock, db: AsyncSession = Depends(get_db)):
    vault = (await db.execute(select(VaultDB).where(VaultDB.id == vault_id))).scalar_one_or_none()
    if not vault:
        raise HTTPException(404, "Vault not found")
    key = await asyncio.to_thread(derive_key, data.password, vault.argon2_salt)
    token = _create_session(vault_id, key)
    return UnlockResponse(session_token=token, vault_id=vault_id, vault_name=vault.name)


@app.post("/vaults/{vault_id}/lock", status_code=204)
async def lock_vault(vault_id: str, session: dict = Depends(require_session)):
    for t in [t for t, s in list(_sessions.items()) if s["vault_id"] == vault_id]:
        del _sessions[t]


@app.patch("/vaults/{vault_id}", response_model=VaultResponse)
async def rename_vault(
    vault_id: str, data: VaultRename,
    session: dict = Depends(require_session),
    db: AsyncSession = Depends(get_db),
):
    if session["vault_id"] != vault_id:
        raise HTTPException(403, "Token does not belong to this vault")
    vault = (await db.execute(select(VaultDB).where(VaultDB.id == vault_id))).scalar_one_or_none()
    if not vault:
        raise HTTPException(404, "Vault not found")
    existing = (await db.execute(select(VaultDB).where(VaultDB.name == data.name.strip()))).scalar_one_or_none()
    if existing and existing.id != vault_id:
        raise HTTPException(400, "Name already taken")
    vault.name = data.name.strip()
    await db.commit()
    await db.refresh(vault)
    doc_c = (await db.execute(select(func.count(DocumentDB.id)).where(DocumentDB.vault_id == vault_id))).scalar()
    chunk_c = (await db.execute(select(func.count(ChunkDB.id)).where(ChunkDB.vault_id == vault_id))).scalar()
    return VaultResponse(id=vault.id, name=vault.name, created_at=vault.created_at,
                         document_count=doc_c or 0, chunk_count=chunk_c or 0)


@app.delete("/vaults/{vault_id}", status_code=204)
async def delete_vault(
    vault_id: str,
    session: dict = Depends(require_session),
    db: AsyncSession = Depends(get_db),
):
    if session["vault_id"] != vault_id:
        raise HTTPException(403, "Token does not belong to this vault")
    # Delete all data
    await db.execute(delete(EntityDB).where(EntityDB.vault_id == vault_id))
    await db.execute(delete(ChunkDB).where(ChunkDB.vault_id == vault_id))
    await db.execute(delete(DocumentDB).where(DocumentDB.vault_id == vault_id))
    await db.execute(delete(VaultDB).where(VaultDB.id == vault_id))
    await db.commit()
    delete_vault_index(vault_id)
    for t in [t for t, s in list(_sessions.items()) if s["vault_id"] == vault_id]:
        del _sessions[t]


# ─── Documents ────────────────────────────────────────────────────────────────

def _doc_response(d: DocumentDB) -> DocumentResponse:
    return DocumentResponse(
        id=d.id, vault_id=d.vault_id, filename=d.filename,
        file_type=d.file_type, chunk_count=d.chunk_count,
        status=d.status, error=d.error, summary=d.summary,
        created_at=d.created_at,
    )


@app.get("/vaults/{vault_id}/documents", response_model=List[DocumentResponse])
async def list_documents(
    vault_id: str,
    session: dict = Depends(require_session),
    db: AsyncSession = Depends(get_db),
):
    if session["vault_id"] != vault_id:
        raise HTTPException(403, "Access denied")
    docs = (
        await db.execute(
            select(DocumentDB).where(DocumentDB.vault_id == vault_id)
            .order_by(DocumentDB.created_at.desc())
        )
    ).scalars().all()
    return [_doc_response(d) for d in docs]


@app.get("/documents/{doc_id}", response_model=DocumentResponse)
async def get_document(doc_id: str, session: dict = Depends(require_session), db: AsyncSession = Depends(get_db)):
    doc = (await db.execute(select(DocumentDB).where(DocumentDB.id == doc_id))).scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Not found")
    if doc.vault_id != session["vault_id"]:
        raise HTTPException(403, "Access denied")
    return _doc_response(doc)


@app.delete("/documents/{doc_id}", status_code=204)
async def delete_document(
    doc_id: str,
    session: dict = Depends(require_session),
    db: AsyncSession = Depends(get_db),
):
    doc = (await db.execute(select(DocumentDB).where(DocumentDB.id == doc_id))).scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Not found")
    if doc.vault_id != session["vault_id"]:
        raise HTTPException(403, "Access denied")

    # Collect FAISS IDs for deletion
    chunks = (
        await db.execute(select(ChunkDB).where(ChunkDB.document_id == doc_id))
    ).scalars().all()
    faiss_ids = [c.faiss_index for c in chunks if c.faiss_index is not None]

    # DB cleanup
    await db.execute(delete(EntityDB).where(EntityDB.document_id == doc_id))
    await db.execute(delete(ChunkDB).where(ChunkDB.document_id == doc_id))
    await db.execute(delete(DocumentDB).where(DocumentDB.id == doc_id))
    await db.commit()

    # Remove from FAISS index (no rebuild needed — IndexIDMap2)
    if faiss_ids:
        await asyncio.to_thread(delete_from_index, doc.vault_id, faiss_ids)


# ─── Ingest ───────────────────────────────────────────────────────────────────

@app.post("/ingest", response_model=DocumentResponse, status_code=202)
async def ingest_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    summary_mode: str = "extractive",
    ollama_url: str = "http://localhost:11434",
    ollama_model: str = "llama3.2:3b",
    session: dict = Depends(require_session),
    db: AsyncSession = Depends(get_db),
):
    vault_id = session["vault_id"]
    key = session["key"]
    ext = os.path.splitext(file.filename or "file.bin")[1].lstrip(".").lower() or "bin"

    # Create uploads directory if missing
    uploads_dir = settings.DATA_DIR / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    # Truncate filename if it's too long (Windows MAX_PATH safety)
    safe_filename = file.filename or "file.bin"
    if len(safe_filename) > 100:
        base, ext = os.path.splitext(safe_filename)
        safe_filename = base[:90] + "..." + ext

    temp_path = uploads_dir / f"{uuid.uuid4()}_{safe_filename}"
    
    try:
        with open(temp_path, "wb") as buf:
            shutil.copyfileobj(file.file, buf)
    except Exception as e:
        logger.error(f"Failed to save temp file: {e}")
        raise HTTPException(500, f"Failed to save upload: {e}")

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
            **{k: getattr(existing, k) for k in
               ("id", "vault_id", "filename", "file_type", "chunk_count", "status", "summary", "created_at")},
            error="Duplicate — already indexed",
        )

    doc = DocumentDB(
        vault_id=vault_id, filename=file.filename or "unknown",
        file_type=ext, file_hash=file_hash, status="pending",
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    background_tasks.add_task(
        run_pipeline,
        doc_id=doc.id, vault_id=vault_id, key=key,
        file_path=str(temp_path), filename=file.filename or "unknown",
        file_type=ext, summary_mode=summary_mode,
        ollama_url=ollama_url, ollama_model=ollama_model,
    )

    return DocumentResponse(
        id=doc.id, vault_id=doc.vault_id, filename=doc.filename,
        file_type=doc.file_type, chunk_count=0, status="pending",
        created_at=doc.created_at,
    )


# ─── Entities ─────────────────────────────────────────────────────────────────

@app.get("/vaults/{vault_id}/entities", response_model=List[EntityResponse])
async def get_vault_entities(
    vault_id: str,
    entity_type: Optional[str] = None,
    limit: int = 50,
    session: dict = Depends(require_session),
    db: AsyncSession = Depends(get_db),
):
    if session["vault_id"] != vault_id:
        raise HTTPException(403, "Access denied")
    q = select(EntityDB).where(EntityDB.vault_id == vault_id)
    if entity_type:
        q = q.where(EntityDB.entity_type == entity_type.upper())
    q = q.order_by(EntityDB.frequency.desc()).limit(limit)
    entities = (await db.execute(q)).scalars().all()
    return [
        EntityResponse(
            id=e.id, document_id=e.document_id, text=e.text,
            entity_type=e.entity_type, subtype=e.subtype, frequency=e.frequency,
        )
        for e in entities
    ]


@app.get("/documents/{doc_id}/entities", response_model=List[EntityResponse])
async def get_document_entities(
    doc_id: str,
    session: dict = Depends(require_session),
    db: AsyncSession = Depends(get_db),
):
    doc = (await db.execute(select(DocumentDB).where(DocumentDB.id == doc_id))).scalar_one_or_none()
    if not doc or doc.vault_id != session["vault_id"]:
        raise HTTPException(403, "Access denied")
    entities = (
        await db.execute(
            select(EntityDB).where(EntityDB.document_id == doc_id)
            .order_by(EntityDB.frequency.desc())
        )
    ).scalars().all()
    return [
        EntityResponse(
            id=e.id, document_id=e.document_id, text=e.text,
            entity_type=e.entity_type, subtype=e.subtype, frequency=e.frequency,
        )
        for e in entities
    ]


# ─── Search ───────────────────────────────────────────────────────────────────

@app.post("/search", response_model=SearchResponse)
async def search(
    request: SearchRequest,
    session: dict = Depends(require_session),
    db: AsyncSession = Depends(get_db),
):
    from modules.search import perform_search
    results = await perform_search(
        db, session["vault_id"], session["key"],
        request.query, request.top_k, request.threshold,
    )
    return SearchResponse(
        query=request.query,
        results=[SearchResult(**r) for r in results],
        total=len(results),
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=True)
