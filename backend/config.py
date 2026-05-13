from pydantic_settings import BaseSettings
from pathlib import Path
import os


class Settings(BaseSettings):
    APP_NAME: str = "AI Knowledge Compiler"
    VERSION: str = "0.1.0-mvp"

    # Storage
    DATA_DIR: Path = Path(os.getenv("DATA_DIR", "./data"))

    # Embeddings
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    EMBEDDING_DIM: int = 384
    EMBEDDING_BATCH_SIZE: int = 32

    # Chunking
    CHUNK_MAX_TOKENS: int = 400
    CHUNK_OVERLAP_SENTENCES: int = 1

    # Encryption — Argon2id params
    ARGON2_TIME_COST: int = 3
    ARGON2_MEMORY_COST: int = 65536  # 64 MB
    ARGON2_PARALLELISM: int = 4
    ARGON2_HASH_LEN: int = 32
    ARGON2_SALT_LEN: int = 32

    # Session TTL (seconds)
    SESSION_TTL: int = 3600

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    ]

    class Config:
        env_file = ".env"


settings = Settings()

# Ensure dirs exist at import
for d in [
    settings.DATA_DIR,
    settings.DATA_DIR / "vaults",
    settings.DATA_DIR / "uploads",
]:
    d.mkdir(parents=True, exist_ok=True)