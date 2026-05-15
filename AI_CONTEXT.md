# AI CONTEXT: RAGNA (AI KNOWLEDGE COMPILER)

This document provides a comprehensive technical overview of the Ragna project for LLMs and developers.

## 1. PROJECT VISION
Ragna is a **local-first, privacy-focused semantic memory system**. It is designed to ingest, encrypt, index, and retrieve multi-format data without ever sending raw content to the cloud. It transforms a "flat" collection of files into a structured "semantic brain."

## 2. CORE ARCHITECTURE

### High-Level Flow
`File Ingestion → Extraction → OCR (if needed) → Cleaning → Semantic Chunking → Embedding (Local) → AES-256 Encryption → FAISS Indexing + SQLite Storage`

### Backend (Python/FastAPI)
*   **API:** FastAPI with asynchronous endpoints.
*   **Security:** 
    *   **KDF:** Argon2id for password derivation.
    *   **Encryption:** AES-256-GCM (Authenticated Encryption) applied per-chunk.
    *   **Session:** Memory-only tokens with TTL.
    *   **Rate Limiting:** Brute-force protection on `/unlock` (via `slowapi`).
*   **Vector Store:** FAISS (`IndexIDMap2` with `IndexFlatIP`). 
    *   **Performance:** In-memory caching for indices to eliminate disk I/O on searches.
*   **Database:** SQLite (via `aiosqlite`) with cascading deletes for data integrity.
*   **Models:** 
    *   **Embeddings:** `sentence-transformers/all-MiniLM-L6-v2` (Local).
    *   **NER:** Rule-based + NLTK for entity extraction.
    *   **Summarization:** Extractive (Offline) or Local LLM (Ollama).

### Frontend (Tauri/React)
*   **Framework:** Tauri 2 (Rust bridge) + React 19 + TypeScript.
*   **Styling:** Modern dark UI.
*   **State:** Local React state + `localStorage` for persistent settings.
*   **Features:** Custom modals (Tauri-safe), settings view with sliders, help documentation.

## 3. REPOSITORY STRUCTURE
```text
/Ragna
├── backend/
│   ├── main.py              # Entry point, FastAPI routes, rate limiting
│   ├── database.py          # SQLAlchemy models (Vault, Document, Chunk, Entity)
│   ├── models.py            # Pydantic schemas (Request/Response)
│   ├── config.py            # Global settings (CORS, Paths, Rate limits)
│   ├── data/                # Local storage (SQLite DB, FAISS indexes, uploads)
│   └── modules/
│       ├── ingestion.py     # Main background pipeline logic
│       ├── extraction.py    # Multi-format extractors (PDF, XLSX, EPUB, etc.)
│       ├── chunking.py      # Section-aware semantic text splitting
│       ├── embeddings.py    # Vector generation (sentence-transformers)
│       ├── encryption.py    # AES-GCM and Argon2 implementation
│       ├── search.py        # Semantic search pipeline + score protection
│       ├── ocr.py           # Tesseract wrapper with OpenCV preprocessing
│       └── vector_store.py  # FAISS management with in-memory caching
├── frontend/
│   ├── src/
│   │   ├── App.tsx          # Main UI logic (Views: Search, Ingest, Knowledge, Settings)
│   │   └── lib/
│   │       ├── api.ts       # Typed API client
│   └── package.json         # Node.js dependencies
└── README.md                # User-facing documentation
```

## 4. KEY TECHNICAL DETAILS

### Data Management (CRUD)
*   **Cascading Deletes:** Deleting a Vault removes its SQLite records, FAISS index files, and all associated document chunks.
*   **Windows Compatibility:** Truncates long filenames to avoid `MAX_PATH` errors and locates Tesseract in default Program Files locations.

### Retrieval Logic
*   **Metric:** Cosine Similarity (normalized Inner Product).
*   **Thresholding:** Dynamic UI slider (0.0 to 1.0). Scores > 1.1 trigger an "Invalid Metric" warning (protection against L2 index corruption).
*   **Relevance Labels:** 
    *   `>= 0.75`: Strong
    *   `>= 0.60`: Good
    *   `>= 0.45`: Weak
    *   `< 0.45`: Marginal

### Supported Formats
*   **Documents:** PDF, DOCX, XLSX, EPUB, Markdown, TXT, CSV, JSON.
*   **Images (OCR):** PNG, JPG, JPEG, WEBP (Supports Tesseract + OpenCV preprocessing).

## 5. ROADMAP
1.  **Knowledge Graph:** Visualizing `EntityDB` relationships in a graph UI.
2.  **Voice Ingestion:** Whisper-based audio transcription.
3.  **Watch Mode:** Auto-sync folders via watchdog.
4.  **Advanced RAG:** Cross-encoder re-ranking and hierarchical chunking.

---
*Generated for AI analysis and context loading.*
