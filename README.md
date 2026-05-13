# AI Knowledge Compiler (AKC)

## Overview
AI Knowledge Compiler is a local-first semantic memory system designed to ingest, process, and index multi-format data for AI agents and RAG pipelines. It transforms raw documents into an encrypted, searchable, and AI-ready knowledge base using local embeddings and vector storage.

## Core Features
- **Local-first & Privacy-first**: All data stays local and is encrypted using AES-256-GCM.
- **Multi-modal Ingestion**: Supports PDF, DOCX, TXT, MD, HTML, CSV, and JSON.
- **Integrated OCR**: Automatic text extraction from images and scanned PDFs using Tesseract.
- **Semantic Chunking**: Intelligent document splitting that preserves context.
- **Vector Search**: Ultra-fast semantic retrieval powered by FAISS and Sentence-Transformers.

## Project Structure
- `backend/`: Python core handling logic, encryption, and AI processing.
- `backend/modules/`: Specialized modules for extraction, chunking, embeddings, and search.
- `frontend/`: Tauri + React + TypeScript desktop application.
- `data/`: Local storage for SQLite database, encrypted chunks, and FAISS indexes (auto-generated).

## Installation & Setup

### Prerequisites
- **Python 3.10+**
- **Rust & Cargo** (for Tauri)
- **Node.js & pnpm**
- **Tesseract OCR** (optional, for image support)

### Backend Setup
1. Install Python dependencies:
   ```bash
   pip install -r backend/requirements.txt
   ```
2. Start the FastAPI server:
   ```bash
   cd backend
   python main.py
   ```

### Frontend Setup
1. Install Node dependencies:
   ```bash
   cd frontend
   pnpm install
   ```
2. Run in development mode:
   ```bash
   pnpm tauri dev
   ```

## API Usage
The backend runs on `http://localhost:8000` by default.
- `POST /vaults`: Create a new encrypted knowledge vault.
- `POST /vaults/{id}/unlock`: Unlock a vault and receive a session token.
- `POST /ingest`: Upload and index a file.
- `POST /search`: Perform semantic search across indexed documents.

## Roadmap

### Phase 1: Core Backend & MVP
- [x] Basic file ingestion (PDF, DOCX, Text).
- [x] AES-256 encryption layer.
- [x] Local embedding generation.
- [x] FAISS vector indexing.
- [x] FastAPI backend implementation.
- [x] Basic OCR integration.

### Phase 2: Desktop GUI Implementation
- [x] Tauri + React integration and setup.
- [x] Modern Dark-themed UI with Tailwind CSS.
- [ ] Vault management interface (Logic).
- [ ] Real-time search integration with backend.
- [ ] Drag & Drop ingestion logic.
- [ ] Live indexing status and progress bars.

### Phase 3: Enhanced Ingestion & Processing
- [ ] Watch mode: Monitor folders for automatic indexing.
- [ ] Advanced deduplication (semantic and hash-based).
- [ ] Table extraction improvements for PDF and DOCX.
- [ ] Expanded format support (EPUB, XLSX, PPTX).

### Phase 4: Semantic Analysis & Graphs
- [ ] Automated topic detection and tagging.
- [ ] Relationship extraction between entities.
- [ ] Knowledge graph visualization.
- [ ] Document clustering based on semantic similarity.

### Phase 5: Advanced AI Integration
- [ ] Local LLM integration for summarization.
- [ ] Context optimization for long-context models.
- [ ] Multi-agent memory support.

### Phase 6: Server & Scale
- [ ] Multi-user support and permissions.
- [ ] Background workers (Celery/Redis).
- [ ] Cloud sync with end-to-end encryption.

## License
Private / Proprietary
