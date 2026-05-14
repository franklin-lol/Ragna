# Ragna — AI Memory Compiler

Local-first semantic knowledge system. Encrypts, indexes, and semantically searches your documents.

## Stack

| Layer | Tech |
|---|---|
| Desktop | Tauri 2 + React 19 + TypeScript |
| Backend | FastAPI + SQLite + FAISS |
| Embeddings | sentence-transformers (all-MiniLM-L6-v2, ~90MB, auto-download) |
| Encryption | AES-256-GCM · Argon2id KDF |
| OCR | Tesseract (optional) |

---

## Prerequisites

- Python 3.11+
- Node.js 18+ + pnpm (`npm i -g pnpm`)
- Rust + Cargo (for Tauri: https://tauri.app/start/prerequisites/)
- *(Optional)* Tesseract OCR:
  - Ubuntu/Debian: `sudo apt install tesseract-ocr`
  - macOS: `brew install tesseract`
  - Windows: [UB Mannheim installer](https://github.com/UB-Mannheim/tesseract/wiki)

---

## Setup & Run

### 1. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Download NLTK punkt tokenizer
python -c "import nltk; nltk.download('punkt'); nltk.download('punkt_tab')"

# Start server (embedding model downloads ~90MB on first request)
uvicorn main:app --reload --port 8000
```

Backend runs at: `http://localhost:8000`  
API docs: `http://localhost:8000/docs`

### 2. Frontend (Tauri desktop app)

```bash
cd frontend
pnpm install
pnpm tauri dev
```

Or for web-only (no Tauri):
```bash
pnpm dev
# → http://localhost:1420
```

---

## Usage

1. **Create Vault** — click "New Vault", set name + encryption password
2. **Unlock** — click vault → enter password (derives AES key via Argon2id)
3. **Ingest** — drop files into Upload zone (PDF, DOCX, XLSX, MD, TXT, HTML, CSV, JSON, PNG, JPG)
   - Processing is async — status updates automatically
4. **Search** — semantic query, finds conceptually related chunks even without exact keywords
5. **Manage** — delete individual documents or entire vaults directly from the GUI

---

## Developer

Developed by **Franklin System**.  
Portfolio: [franklin-sys.vercel.app](https://franklin-sys.vercel.app/)

---

## Architecture

```
File Upload → Extraction → OCR Fallback → Cleaning → Chunking
           → Embeddings (sentence-transformers) → FAISS (cosine sim)
           → AES-256-GCM Encrypt → SQLite
```

- Each vault has unique Argon2id salt → 32-byte AES key
- Chunk content encrypted individually (unique 12-byte GCM nonce per chunk)
- FAISS index stored per vault; uses `IndexFlatIP` + L2-normalized vectors = cosine similarity
- Background processing via FastAPI `BackgroundTasks` + `asyncio.to_thread` (non-blocking)

---

## Roadmap (not in MVP)

- [ ] Voice/audio ingestion (Whisper transcription)
- [ ] Knowledge graph (networkx / neo4j)
- [ ] Auto-tagging + entity extraction (spaCy)
- [ ] Folder watch mode
- [ ] Multi-user server mode
- [ ] SaaS / cloud sync
- [ ] Agent memory integration
