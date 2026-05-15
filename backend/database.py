from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, Integer, LargeBinary, DateTime, Text, ForeignKey, func, text
from datetime import datetime
from typing import Optional, List
from config import settings
import uuid


DATABASE_URL = f"sqlite+aiosqlite:///{settings.DATA_DIR}/akc.db"

engine = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class VaultDB(Base):
    __tablename__ = "vaults"

    id:          Mapped[str]      = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name:        Mapped[str]      = mapped_column(String, nullable=False)
    argon2_salt: Mapped[bytes]    = mapped_column(LargeBinary, nullable=False)
    created_at:  Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    documents: Mapped[List["DocumentDB"]] = relationship(
        "DocumentDB", back_populates="vault", cascade="all, delete-orphan", lazy="noload"
    )
    chunks: Mapped[List["ChunkDB"]] = relationship(
        "ChunkDB", back_populates="vault", cascade="all, delete-orphan", lazy="noload"
    )
    entities: Mapped[List["EntityDB"]] = relationship(
        "EntityDB", back_populates="vault", cascade="all, delete-orphan", lazy="noload"
    )


class DocumentDB(Base):
    __tablename__ = "documents"

    id:          Mapped[str]           = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    vault_id:    Mapped[str]           = mapped_column(String, ForeignKey("vaults.id", ondelete="CASCADE"), nullable=False)
    filename:    Mapped[str]           = mapped_column(String, nullable=False)
    file_type:   Mapped[str]           = mapped_column(String, nullable=False)
    file_hash:   Mapped[str]           = mapped_column(String, nullable=False)
    chunk_count: Mapped[int]           = mapped_column(Integer, default=0)
    status:      Mapped[str]           = mapped_column(String, default="pending")
    error:       Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    summary:     Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at:  Mapped[datetime]      = mapped_column(DateTime, server_default=func.now())

    vault:    Mapped["VaultDB"]       = relationship("VaultDB", back_populates="documents")
    chunks:   Mapped[List["ChunkDB"]] = relationship(
        "ChunkDB", back_populates="document", cascade="all, delete-orphan", lazy="noload"
    )
    entities: Mapped[List["EntityDB"]] = relationship(
        "EntityDB", back_populates="document", cascade="all, delete-orphan", lazy="noload"
    )


class ChunkDB(Base):
    __tablename__ = "chunks"

    id:                Mapped[str]           = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    vault_id:          Mapped[str]           = mapped_column(String, ForeignKey("vaults.id", ondelete="CASCADE"), nullable=False)
    document_id:       Mapped[str]           = mapped_column(String, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    content_encrypted: Mapped[bytes]         = mapped_column(LargeBinary, nullable=False)
    nonce:             Mapped[bytes]         = mapped_column(LargeBinary, nullable=False)
    content_hash:      Mapped[str]           = mapped_column(String, nullable=False)
    embedding_blob:    Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)  # raw float32 — for index rebuild
    section:           Mapped[Optional[str]] = mapped_column(String, nullable=True)
    tags:              Mapped[Optional[str]] = mapped_column(Text, nullable=True)      # JSON array
    language:          Mapped[Optional[str]] = mapped_column(String, nullable=True)
    chunk_index:       Mapped[int]           = mapped_column(Integer, default=0)
    faiss_index:       Mapped[Optional[int]] = mapped_column(Integer, nullable=True)   # IndexIDMap2 ID

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    vault:    Mapped["VaultDB"]    = relationship("VaultDB", back_populates="chunks")
    document: Mapped["DocumentDB"] = relationship("DocumentDB", back_populates="chunks")


class EntityDB(Base):
    __tablename__ = "entities"

    id:          Mapped[str]           = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    vault_id:    Mapped[str]           = mapped_column(String, ForeignKey("vaults.id", ondelete="CASCADE"), nullable=False)
    document_id: Mapped[str]           = mapped_column(String, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    text:        Mapped[str]           = mapped_column(String, nullable=False)
    entity_type: Mapped[str]           = mapped_column(String, nullable=False)
    subtype:     Mapped[Optional[str]] = mapped_column(String, nullable=True)
    frequency:   Mapped[int]           = mapped_column(Integer, default=1)

    vault:    Mapped["VaultDB"]    = relationship("VaultDB", back_populates="entities")
    document: Mapped["DocumentDB"] = relationship("DocumentDB", back_populates="entities")


# ─── Init + safe migrations ───────────────────────────────────────────────────

async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Additive migrations for existing DBs (idempotent)
        for stmt in [
            "ALTER TABLE documents ADD COLUMN summary TEXT",
            "ALTER TABLE chunks ADD COLUMN embedding_blob BLOB",
        ]:
            try:
                await conn.execute(text(stmt))
            except Exception:
                pass  # column already exists — skip


async def get_db():
    async with SessionLocal() as session:
        yield session
