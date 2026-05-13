from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
import os
import shutil
import uuid
from typing import List
from contextlib import asynccontextmanager

from config import settings
from database import get_db, init_db, VaultDB, DocumentDB, ChunkDB
from models import (
    VaultCreate, VaultResponse, VaultUnlock, UnlockResponse,
    DocumentResponse, SearchRequest, SearchResponse, SearchResult
)
from modules.encryption import generate_salt, derive_key
from modules.ingestion import process_file
from modules.search import perform_search

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    await init_db()
    yield
    # Shutdown logic (if any)

app = FastAPI(title=settings.APP_NAME, version=settings.VERSION, lifespan=lifespan)

# In-memory session storage (In production, use Redis)
# session_token -> {"vault_id": str, "key": bytes}
sessions = {}

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Vault Management ─────────────────────────────────────────────────────────

@app.post("/vaults", response_model=VaultResponse)
async def create_vault(vault: VaultCreate, db: AsyncSession = Depends(get_db)):
    # Check if name exists
    stmt = select(VaultDB).where(VaultDB.name == vault.name)
    existing = await db.execute(stmt)
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Vault already exists")

    salt = generate_salt()
    # Note: We don't store the password, only the salt.
    # Key is derived on unlock.
    
    new_vault = VaultDB(
        name=vault.name,
        argon2_salt=salt
    )
    db.add(new_vault)
    await db.commit()
    await db.refresh(new_vault)
    
    return VaultResponse(
        id=new_vault.id,
        name=new_vault.name,
        created_at=new_vault.created_at
    )

@app.get("/vaults", response_model=List[VaultResponse])
async def list_vaults(db: AsyncSession = Depends(get_db)):
    stmt = select(VaultDB)
    result = await db.execute(stmt)
    vaults = result.scalars().all()
    
    res = []
    for v in vaults:
        # Get counts
        doc_stmt = select(func.count(DocumentDB.id)).where(DocumentDB.vault_id == v.id)
        chunk_stmt = select(func.count(ChunkDB.id)).where(ChunkDB.vault_id == v.id)
        
        doc_count = await db.execute(doc_stmt)
        chunk_count = await db.execute(chunk_stmt)
        
        res.append(VaultResponse(
            id=v.id,
            name=v.name,
            created_at=v.created_at,
            document_count=doc_count.scalar(),
            chunk_count=chunk_count.scalar()
        ))
    return res

@app.post("/vaults/{vault_id}/unlock", response_model=UnlockResponse)
async def unlock_vault(vault_id: str, data: VaultUnlock, db: AsyncSession = Depends(get_db)):
    stmt = select(VaultDB).where(VaultDB.id == vault_id)
    result = await db.execute(stmt)
    vault = result.scalar_one_or_none()
    
    if not vault:
        raise HTTPException(status_code=404, detail="Vault not found")
        
    # Derive key
    key = derive_key(data.password, vault.argon2_salt)
    
    # Create session
    token = str(uuid.uuid4())
    sessions[token] = {"vault_id": vault_id, "key": key}
    
    return UnlockResponse(
        session_token=token,
        vault_id=vault_id,
        vault_name=vault.name
    )

# ─── Ingestion ────────────────────────────────────────────────────────────────

@app.post("/ingest", response_model=DocumentResponse)
async def ingest_file(
    token: str, 
    file: UploadFile = File(...), 
    db: AsyncSession = Depends(get_db)
):
    if token not in sessions:
        raise HTTPException(status_code=401, detail="Invalid session")
        
    session = sessions[token]
    vault_id = session["vault_id"]
    key = session["key"]
    
    # Save temp file
    temp_path = settings.DATA_DIR / "uploads" / f"{uuid.uuid4()}_{file.filename}"
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    try:
        doc_id = await process_file(
            db, 
            vault_id, 
            key, 
            str(temp_path), 
            file.filename, 
            os.path.splitext(file.filename)[1]
        )
        
        # Fetch updated doc
        stmt = select(DocumentDB).where(DocumentDB.id == doc_id)
        result = await db.execute(stmt)
        doc = result.scalar_one()
        
        return DocumentResponse(
            id=doc.id,
            vault_id=doc.vault_id,
            filename=doc.filename,
            file_type=doc.file_type,
            chunk_count=doc.chunk_count,
            status=doc.status,
            created_at=doc.created_at
        )
    finally:
        if temp_path.exists():
            os.remove(temp_path)

# ─── Search ───────────────────────────────────────────────────────────────────

@app.post("/search", response_model=SearchResponse)
async def search(
    token: str, 
    request: SearchRequest, 
    db: AsyncSession = Depends(get_db)
):
    if token not in sessions:
        raise HTTPException(status_code=401, detail="Invalid session")
        
    session = sessions[token]
    vault_id = session["vault_id"]
    key = session["key"]
    
    results = await perform_search(
        db, 
        vault_id, 
        key, 
        request.query, 
        request.top_k, 
        request.threshold
    )
    
    return SearchResponse(
        query=request.query,
        results=[SearchResult(**r) for r in results],
        total=len(results)
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)
