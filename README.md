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

---

## Usage

1. **Create Vault** — click "New Vault", set name + encryption password
2. **Unlock** — click vault → enter password (derives AES key via Argon2id)
3. **Ingest** — drop files into Upload zone (PDF, DOCX, XLSX, EPUB, MD, TXT, HTML, CSV, JSON, PNG, JPG, WEBP)
   - Processing is async — status updates automatically
4. **Search** — semantic query, finds conceptually related chunks even without exact keywords
5. **Manage** — delete individual documents or entire vaults directly from the GUI

---

## Developer

Developed by **Franklin System**.  
Portfolio: [franklin-sys.vercel.app](https://franklin-sys.vercel.app/)

---

## Roadmap

- [x] **Management:** Full CRUD for documents and vaults (DELETE/RENAME).
- [x] **Formats:** Support for XLSX, EPUB, JSON, CSV, and OCR for images.
- [x] **Local AI:** Integrated extractive summarization and Ollama support.
- [x] **Entities:** Automated entity extraction (NER) and tagging.
- [ ] **Knowledge Graph:** Visualizing relationships between concepts (Next Priority).
- [ ] **Voice Ingestion:** Whisper transcription for audio files.
- [ ] **Watch Mode:** Real-time folder synchronization.
- [ ] **Advanced RAG:** Multi-hop retrieval and context reranking.
- [ ] **Agent Memory:** API for autonomous agent integration.
