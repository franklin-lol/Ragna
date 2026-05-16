"""
AI Knowledge Compiler — FastAPI backend.
"""
import asyncio, hashlib, logging, os, secrets, shutil, time, uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, List, Optional

from fastapi import BackgroundTasks, Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy import func, select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import ChunkDB, DocumentDB, EntityDB, SessionLocal, VaultDB, WatcherDB, get_db, init_db
from models import (
    DocumentResponse, EntityResponse, SearchRequest, SearchResponse, SearchResult,
    UnlockResponse, VaultCreate, VaultRename, VaultResponse, VaultUnlock,
    WatcherCreate, WatcherResponse,
)
from modules.encryption import derive_key, generate_salt
from modules.ingestion import run_pipeline
from modules.vector_store import delete_from_index, delete_vault_index
from modules.watcher import watcher_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Rate limiter ──────────────────────────────────────────────────────────────

limiter = Limiter(key_func=get_remote_address)

async def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(status_code=429,
        content={"detail": "Too many unlock attempts. Please wait before retrying."})

# ── Session store ─────────────────────────────────────────────────────────────
# Single-worker only. See config.py comment for multi-worker caveats.

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

def _purge_expired() -> None:
    now = time.time()
    for t in [t for t, s in list(_sessions.items()) if now - s["created_at"] > settings.SESSION_TTL]:
        del _sessions[t]

async def require_session(x_session_token: Annotated[str | None, Header()] = None) -> dict:
    if not x_session_token:
        raise HTTPException(401, "Missing X-Session-Token header")
    session = _get_session(x_session_token)
    if not session:
        raise HTTPException(401, "Invalid or expired session")
    return session

# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await watcher_manager.start()          # ← Watch Mode
    asyncio.create_task(_warm_model())
    logger.info(
        f"Ragna — {settings.HOST}:{settings.PORT} | "
        f"ttl={settings.SESSION_TTL}s | limit={settings.UNLOCK_RATE_LIMIT}"
    )
    yield
    await watcher_manager.stop()           # ← clean shutdown

async def _warm_model():
    try:
        from modules.embeddings import get_model
        await asyncio.to_thread(get_model)
        logger.info("Embedding model ready.")
    except Exception as e:
        logger.warning(f"Model pre-warm failed: {e}")

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title=settings.APP_NAME, version=settings.VERSION, lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)
app.add_middleware(CORSMiddleware, allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "version": settings.VERSION}

# ── Vaults ────────────────────────────────────────────────────────────────────

@app.post("/vaults", response_model=VaultResponse, status_code=201)
async def create_vault(vault: VaultCreate, db: AsyncSession = Depends(get_db)):
    if (await db.execute(select(VaultDB).where(VaultDB.name == vault.name))).scalar_one_or_none():
        raise HTTPException(400, "Vault name already exists")
    v = VaultDB(name=vault.name.strip(), argon2_salt=generate_salt())
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
        doc_c   = (await db.execute(select(func.count(DocumentDB.id)).where(DocumentDB.vault_id == v.id))).scalar()
        chunk_c = (await db.execute(select(func.count(ChunkDB.id)).where(ChunkDB.vault_id == v.id))).scalar()
        result.append(VaultResponse(id=v.id, name=v.name, created_at=v.created_at,
                                    document_count=doc_c or 0, chunk_count=chunk_c or 0))
    return result


@app.post("/vaults/{vault_id}/unlock", response_model=UnlockResponse)
@limiter.limit(settings.UNLOCK_RATE_LIMIT)
async def unlock_vault(request: Request, vault_id: str, data: VaultUnlock,
                       db: AsyncSession = Depends(get_db)):
    vault = (await db.execute(select(VaultDB).where(VaultDB.id == vault_id))).scalar_one_or_none()
    if not vault:
        raise HTTPException(404, "Vault not found")
    key = await asyncio.to_thread(derive_key, data.password, vault.argon2_salt)
    token = _create_session(vault_id, key)

    # Resume persisted watchers
    db_watchers = (await db.execute(
        select(WatcherDB).where(WatcherDB.vault_id == vault_id, WatcherDB.is_active == True)
    )).scalars().all()
    if db_watchers:
        rows = [{"id": w.id, "folder_path": w.folder_path, "recursive": w.recursive}
                for w in db_watchers]
        asyncio.create_task(watcher_manager.resume_vault_watchers(vault_id, key, rows))

    return UnlockResponse(session_token=token, vault_id=vault_id, vault_name=vault.name)


@app.post("/vaults/{vault_id}/lock", status_code=204)
async def lock_vault(vault_id: str, session: dict = Depends(require_session)):
    for t in [t for t, s in list(_sessions.items()) if s["vault_id"] == vault_id]:
        del _sessions[t]
    watcher_manager.clear_vault_key(vault_id)  # ← pause watchers on lock


@app.patch("/vaults/{vault_id}", response_model=VaultResponse)
async def rename_vault(vault_id: str, data: VaultRename,
                       session: dict = Depends(require_session), db: AsyncSession = Depends(get_db)):
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
    doc_c   = (await db.execute(select(func.count(DocumentDB.id)).where(DocumentDB.vault_id == vault_id))).scalar()
    chunk_c = (await db.execute(select(func.count(ChunkDB.id)).where(ChunkDB.vault_id == vault_id))).scalar()
    return VaultResponse(id=vault.id, name=vault.name, created_at=vault.created_at,
                         document_count=doc_c or 0, chunk_count=chunk_c or 0)


@app.delete("/vaults/{vault_id}", status_code=204)
async def delete_vault(vault_id: str, session: dict = Depends(require_session),
                       db: AsyncSession = Depends(get_db)):
    if session["vault_id"] != vault_id:
        raise HTTPException(403, "Token does not belong to this vault")
    for tbl, col in [
        (WatcherDB, WatcherDB.vault_id), (EntityDB, EntityDB.vault_id),
        (ChunkDB, ChunkDB.vault_id),     (DocumentDB, DocumentDB.vault_id),
    ]:
        await db.execute(delete(tbl).where(col == vault_id))
    await db.execute(delete(VaultDB).where(VaultDB.id == vault_id))
    await db.commit()
    delete_vault_index(vault_id)
    watcher_manager.remove_vault_watchers(vault_id)
    for t in [t for t, s in list(_sessions.items()) if s["vault_id"] == vault_id]:
        del _sessions[t]

# ── Documents ─────────────────────────────────────────────────────────────────

def _doc_resp(d: DocumentDB) -> DocumentResponse:
    return DocumentResponse(id=d.id, vault_id=d.vault_id, filename=d.filename,
        file_type=d.file_type, chunk_count=d.chunk_count, status=d.status,
        error=d.error, summary=d.summary, created_at=d.created_at)


@app.get("/vaults/{vault_id}/documents", response_model=List[DocumentResponse])
async def list_documents(vault_id: str, session: dict = Depends(require_session),
                         db: AsyncSession = Depends(get_db)):
    if session["vault_id"] != vault_id:
        raise HTTPException(403, "Access denied")
    docs = (await db.execute(select(DocumentDB).where(DocumentDB.vault_id == vault_id)
        .order_by(DocumentDB.created_at.desc()))).scalars().all()
    return [_doc_resp(d) for d in docs]


@app.get("/documents/{doc_id}", response_model=DocumentResponse)
async def get_document(doc_id: str, session: dict = Depends(require_session),
                       db: AsyncSession = Depends(get_db)):
    doc = (await db.execute(select(DocumentDB).where(DocumentDB.id == doc_id))).scalar_one_or_none()
    if not doc: raise HTTPException(404, "Not found")
    if doc.vault_id != session["vault_id"]: raise HTTPException(403, "Access denied")
    return _doc_resp(doc)


@app.delete("/documents/{doc_id}", status_code=204)
async def delete_document(doc_id: str, session: dict = Depends(require_session),
                          db: AsyncSession = Depends(get_db)):
    doc = (await db.execute(select(DocumentDB).where(DocumentDB.id == doc_id))).scalar_one_or_none()
    if not doc: raise HTTPException(404, "Not found")
    if doc.vault_id != session["vault_id"]: raise HTTPException(403, "Access denied")
    chunks = (await db.execute(select(ChunkDB).where(ChunkDB.document_id == doc_id))).scalars().all()
    faiss_ids = [c.faiss_index for c in chunks if c.faiss_index is not None]
    await db.execute(delete(EntityDB).where(EntityDB.document_id == doc_id))
    await db.execute(delete(ChunkDB).where(ChunkDB.document_id == doc_id))
    await db.execute(delete(DocumentDB).where(DocumentDB.id == doc_id))
    await db.commit()
    if faiss_ids:
        await asyncio.to_thread(delete_from_index, doc.vault_id, faiss_ids)

# ── Ingest ────────────────────────────────────────────────────────────────────

@app.post("/ingest", response_model=DocumentResponse, status_code=202)
async def ingest_file(background_tasks: BackgroundTasks, file: UploadFile = File(...),
    summary_mode: str = "extractive", ollama_url: str = "http://localhost:11434",
    ollama_model: str = "llama3.2:3b", session: dict = Depends(require_session),
    db: AsyncSession = Depends(get_db)):
    vault_id, key = session["vault_id"], session["key"]
    ext = os.path.splitext(file.filename or "file.bin")[1].lstrip(".").lower() or "bin"
    uploads_dir = settings.DATA_DIR / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    safe_name = (file.filename or "file.bin")[:100]
    temp_path = uploads_dir / f"{uuid.uuid4()}_{safe_name}"
    try:
        with open(temp_path, "wb") as buf:
            shutil.copyfileobj(file.file, buf)
    except Exception as e:
        raise HTTPException(500, f"Failed to save upload: {e}")
    with open(temp_path, "rb") as f:
        file_hash = hashlib.sha256(f.read()).hexdigest()
    existing = (await db.execute(select(DocumentDB).where(
        DocumentDB.vault_id == vault_id, DocumentDB.file_hash == file_hash
    ))).scalar_one_or_none()
    if existing:
        temp_path.unlink(missing_ok=True)
        return DocumentResponse(**{k: getattr(existing, k) for k in
            ("id","vault_id","filename","file_type","chunk_count","status","summary","created_at")},
            error="Duplicate — already indexed")
    doc = DocumentDB(vault_id=vault_id, filename=file.filename or "unknown",
                     file_type=ext, file_hash=file_hash, status="pending")
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    background_tasks.add_task(run_pipeline, doc_id=doc.id, vault_id=vault_id, key=key,
        file_path=str(temp_path), filename=file.filename or "unknown",
        file_type=ext, summary_mode=summary_mode, ollama_url=ollama_url, ollama_model=ollama_model)
    return DocumentResponse(id=doc.id, vault_id=doc.vault_id, filename=doc.filename,
        file_type=doc.file_type, chunk_count=0, status="pending", created_at=doc.created_at)

# ── Entities ──────────────────────────────────────────────────────────────────

@app.get("/vaults/{vault_id}/entities", response_model=List[EntityResponse])
async def get_vault_entities(vault_id: str, entity_type: Optional[str] = None,
    limit: int = 50, session: dict = Depends(require_session), db: AsyncSession = Depends(get_db)):
    if session["vault_id"] != vault_id: raise HTTPException(403, "Access denied")
    q = select(EntityDB).where(EntityDB.vault_id == vault_id)
    if entity_type: q = q.where(EntityDB.entity_type == entity_type.upper())
    entities = (await db.execute(q.order_by(EntityDB.frequency.desc()).limit(limit))).scalars().all()
    return [EntityResponse(id=e.id, document_id=e.document_id, text=e.text,
        entity_type=e.entity_type, subtype=e.subtype, frequency=e.frequency) for e in entities]


@app.get("/documents/{doc_id}/entities", response_model=List[EntityResponse])
async def get_document_entities(doc_id: str, session: dict = Depends(require_session),
                                db: AsyncSession = Depends(get_db)):
    doc = (await db.execute(select(DocumentDB).where(DocumentDB.id == doc_id))).scalar_one_or_none()
    if not doc or doc.vault_id != session["vault_id"]: raise HTTPException(403, "Access denied")
    entities = (await db.execute(select(EntityDB).where(EntityDB.document_id == doc_id)
        .order_by(EntityDB.frequency.desc()))).scalars().all()
    return [EntityResponse(id=e.id, document_id=e.document_id, text=e.text,
        entity_type=e.entity_type, subtype=e.subtype, frequency=e.frequency) for e in entities]

# ── Search ────────────────────────────────────────────────────────────────────

@app.post("/search", response_model=SearchResponse)
async def search(request: SearchRequest, session: dict = Depends(require_session),
                 db: AsyncSession = Depends(get_db)):
    from modules.reranker import is_available
    from modules.search import perform_search
    results = await perform_search(db, session["vault_id"], session["key"],
        request.query, request.top_k, request.threshold, rerank_results=request.rerank)
    return SearchResponse(query=request.query, results=[SearchResult(**r) for r in results],
        total=len(results), reranked=request.rerank and is_available())

# ── Watch Mode ────────────────────────────────────────────────────────────────

def _watcher_resp(w: WatcherDB, running: bool = False) -> WatcherResponse:
    return WatcherResponse(id=w.id, vault_id=w.vault_id, folder_path=w.folder_path,
        recursive=w.recursive, is_active=w.is_active, is_running=running,
        created_at=w.created_at)


@app.get("/vaults/{vault_id}/watchers", response_model=List[WatcherResponse])
async def list_watchers(vault_id: str, session: dict = Depends(require_session),
                        db: AsyncSession = Depends(get_db)):
    if session["vault_id"] != vault_id: raise HTTPException(403, "Access denied")
    watchers = (await db.execute(select(WatcherDB).where(WatcherDB.vault_id == vault_id))).scalars().all()
    running_ids = set(watcher_manager.get_vault_watcher_ids(vault_id))
    return [_watcher_resp(w, running=w.id in running_ids) for w in watchers]


@app.post("/vaults/{vault_id}/watchers", response_model=WatcherResponse, status_code=201)
async def add_watcher(vault_id: str, data: WatcherCreate,
                      session: dict = Depends(require_session), db: AsyncSession = Depends(get_db)):
    if session["vault_id"] != vault_id: raise HTTPException(403, "Token does not belong to this vault")
    folder = Path(data.folder_path).expanduser().resolve()
    if not folder.is_dir(): raise HTTPException(400, f"Not a directory: {folder}")
    existing = (await db.execute(select(WatcherDB).where(
        WatcherDB.vault_id == vault_id, WatcherDB.folder_path == str(folder)
    ))).scalar_one_or_none()
    if existing: raise HTTPException(400, "Watcher for this folder already exists")
    w = WatcherDB(vault_id=vault_id, folder_path=str(folder),
                  recursive=data.recursive, is_active=True)
    db.add(w)
    await db.commit()
    await db.refresh(w)
    is_running = False
    try:
        watcher_manager.add_watcher(vault_id=vault_id, folder_path=str(folder),
            key=session["key"], watcher_id=w.id, recursive=data.recursive)
        is_running = True
    except ValueError as e:
        logger.warning(f"Watcher DB-registered but OS start failed: {e}")
    return _watcher_resp(w, running=is_running)


@app.delete("/watchers/{watcher_id}", status_code=204)
async def remove_watcher(watcher_id: str, session: dict = Depends(require_session),
                         db: AsyncSession = Depends(get_db)):
    w = (await db.execute(select(WatcherDB).where(WatcherDB.id == watcher_id))).scalar_one_or_none()
    if not w: raise HTTPException(404, "Watcher not found")
    if w.vault_id != session["vault_id"]: raise HTTPException(403, "Access denied")
    watcher_manager.remove_watcher(watcher_id)
    await db.execute(delete(WatcherDB).where(WatcherDB.id == watcher_id))
    await db.commit()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT,
                reload=True, workers=1)
