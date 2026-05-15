import { useState, useEffect, useCallback, useRef } from "react";
import {
  Search, Upload, Database, Lock, Unlock, FileText, Plus,
  ShieldCheck, Loader2, AlertCircle, X, CheckCircle2, Clock,
  XCircle, Cpu, Zap, Settings, Trash2, Edit3, BookOpen,
  Globe, ChevronDown, ChevronRight, SlidersHorizontal, HelpCircle,
} from "lucide-react";
import { cn } from "./lib/utils";
import {
  api, Vault, Document, Entity, SearchResult,
  AppSettings, DEFAULT_SETTINGS, ApiError,
} from "./lib/api";
import "./App.css";

type View = "search" | "upload" | "knowledge" | "settings";

// ─── Settings hook ────────────────────────────────────────────────────────────

function useSettings(): [AppSettings, (s: Partial<AppSettings>) => void] {
  const [settings, setSettingsState] = useState<AppSettings>(() => {
    try {
      const stored = localStorage.getItem("ragna_settings");
      return stored ? { ...DEFAULT_SETTINGS, ...JSON.parse(stored) } : DEFAULT_SETTINGS;
    } catch { return DEFAULT_SETTINGS; }
  });

  const updateSettings = useCallback((patch: Partial<AppSettings>) => {
    setSettingsState(prev => {
      const next = { ...prev, ...patch };
      localStorage.setItem("ragna_settings", JSON.stringify(next));
      return next;
    });
  }, []);

  useEffect(() => { api.setBaseUrl(settings.backendUrl); }, [settings.backendUrl]);

  return [settings, updateSettings];
}

// ─── UI atoms ─────────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: Document["status"] }) {
  const map = {
    pending:    { icon: Clock,        color: "text-yellow-500", bg: "bg-yellow-500/10",  label: "Pending" },
    processing: { icon: Loader2,      color: "text-blue-400",   bg: "bg-blue-500/10",    label: "Processing" },
    indexed:    { icon: CheckCircle2, color: "text-emerald-400",bg: "bg-emerald-500/10", label: "Indexed" },
    failed:     { icon: XCircle,      color: "text-red-400",    bg: "bg-red-500/10",     label: "Failed" },
  } as const;
  const { icon: Icon, color, bg, label } = map[status];
  return (
    <span className={cn("inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-[11px] font-semibold", bg, color)}>
      <Icon size={11} className={status === "processing" ? "animate-spin" : ""} />
      {label}
    </span>
  );
}

const FILE_COLORS: Record<string, string> = {
  pdf: "text-red-400", docx: "text-blue-400", md: "text-purple-400", txt: "text-zinc-400",
  json: "text-yellow-400", csv: "text-green-400", html: "text-orange-400",
  png: "text-pink-400", jpg: "text-pink-400", webp: "text-pink-400",
  xlsx: "text-emerald-400", epub: "text-cyan-400",
};

function FileBadge({ type }: { type: string }) {
  return <span className={cn("text-[10px] font-bold uppercase tracking-wide", FILE_COLORS[type] ?? "text-zinc-500")}>{type}</span>;
}

const ENTITY_COLORS: Record<string, string> = {
  TECH: "bg-indigo-500/15 text-indigo-400 border-indigo-500/25",
  LANG: "bg-blue-500/15 text-blue-400 border-blue-500/25",
  FRAMEWORK: "bg-purple-500/15 text-purple-400 border-purple-500/25",
  DATABASE: "bg-green-500/15 text-green-400 border-green-500/25",
  INFRA: "bg-orange-500/15 text-orange-400 border-orange-500/25",
  CLOUD: "bg-cyan-500/15 text-cyan-400 border-cyan-500/25",
  AI: "bg-pink-500/15 text-pink-400 border-pink-500/25",
  PERSON: "bg-yellow-500/15 text-yellow-400 border-yellow-500/25",
  ORGANIZATION: "bg-amber-500/15 text-amber-400 border-amber-500/25",
  GPE: "bg-teal-500/15 text-teal-400 border-teal-500/25",
  PROTOCOL: "bg-rose-500/15 text-rose-400 border-rose-500/25",
};

function EntityChip({ entity }: { entity: Entity }) {
  const cls = ENTITY_COLORS[entity.subtype ?? entity.entity_type] ?? ENTITY_COLORS[entity.entity_type] ?? "bg-zinc-800 text-zinc-400 border-zinc-700";
  return (
    <span className={cn("inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-semibold border", cls)}>
      {entity.text}
      {entity.frequency > 1 && <span className="opacity-50">×{entity.frequency}</span>}
    </span>
  );
}

// ─── Modals ───────────────────────────────────────────────────────────────────

function ConfirmModal({
  title, message, onConfirm, onCancel, danger = false,
}: { title: string; message: string; onConfirm: () => void; onCancel: () => void; danger?: boolean }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="w-full max-w-sm bg-[#111] border border-zinc-800 rounded-2xl p-6 shadow-2xl">
        <h3 className="text-base font-bold mb-2">{title}</h3>
        <p className="text-sm text-zinc-400 mb-6">{message}</p>
        <div className="flex gap-3 justify-end">
          <button onClick={onCancel}
            className="px-4 py-2 rounded-xl text-sm font-semibold text-zinc-400 hover:text-white bg-zinc-900 hover:bg-zinc-800 transition-all border border-zinc-800">
            Cancel
          </button>
          <button onClick={onConfirm}
            className={cn("px-4 py-2 rounded-xl text-sm font-semibold text-white transition-all",
              danger ? "bg-red-600 hover:bg-red-500" : "bg-indigo-600 hover:bg-indigo-500")}>
            {danger ? "Delete" : "Confirm"}
          </button>
        </div>
      </div>
    </div>
  );
}

function HelpModal({ onClose }: { onClose: () => void }) {
  const sections = [
    {
      title: "What is Ragna?",
      content: "Ragna is a local-first encrypted knowledge base. Documents are chunked, embedded into vector space, and stored with AES-256-GCM encryption. Everything runs locally on your machine.",
    },
    {
      title: "Vaults & Security",
      content: "A Vault is an encrypted container. Passphrases derive AES keys via Argon2id. Without your password, data is mathematically unreadable. Minimum password length: 8 characters.",
    },
    {
      title: "Supported Formats",
      content: "PDF, DOCX, XLSX, EPUB, MD, TXT, HTML, CSV, JSON, and common image formats (via OCR).",
    },
    {
      title: "Semantic Search",
      content: "Natural language search using cosine similarity. Use the Threshold slider in Settings to control how 'strict' the matching is.",
    },
    {
      title: "AI Summaries",
      content: "Supports extractive offline summarization or Ollama (local LLM) integration. Configure this in Settings.",
    },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="w-full max-w-xl bg-[#111] border border-zinc-800 rounded-2xl shadow-2xl overflow-hidden">
        <div className="flex items-center justify-between px-6 py-5 border-b border-zinc-800/80">
          <h2 className="text-sm font-bold">Documentation & Help</h2>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-200"><X size={18}/></button>
        </div>
        <div className="overflow-y-auto max-h-[60vh] px-6 py-5 space-y-5">
          {sections.map(s => (
            <div key={s.title}>
              <p className="text-[10px] font-bold text-indigo-400 uppercase tracking-widest mb-1.5">{s.title}</p>
              <p className="text-xs text-zinc-400 leading-relaxed">{s.content}</p>
            </div>
          ))}
        </div>
        <div className="px-6 py-4 border-t border-zinc-800/80 flex items-center justify-between bg-zinc-950/40">
          <span className="text-[10px] text-zinc-500 uppercase font-bold tracking-widest">Built by Franklin</span>
          <a href="https://franklin-sys.vercel.app/" target="_blank" rel="noreferrer" className="text-xs text-indigo-400 hover:text-indigo-300">franklin-sys.vercel.app</a>
        </div>
      </div>
    </div>
  );
}

function VaultCreateModal({ onClose, onCreated }: { onClose: () => void; onCreated: (v: Vault) => void }) {
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (password !== confirm) { setError("Passwords do not match"); return; }
    if (password.length < 8)  { setError("Minimum 8 characters"); return; }
    setLoading(true); setError(null);
    try {
      const v = await api.createVault(name.trim(), password);
      onCreated(v);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create vault");
    } finally { setLoading(false); }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="w-full max-w-md bg-[#111] border border-zinc-800 rounded-2xl p-8 shadow-2xl">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-bold">New Vault</h2>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-200 transition-colors"><X size={20}/></button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          {[
            { label: "Vault Name", type: "text", value: name, set: setName, placeholder: "e.g. Research 2025" },
            { label: "Password", type: "password", value: password, set: setPassword, placeholder: "Strong passphrase…" },
            { label: "Confirm Password", type: "password", value: confirm, set: setConfirm, placeholder: "Repeat passphrase…" },
          ].map(({ label, type, value, set, placeholder }) => (
            <div key={label}>
              <label className="block text-[10px] font-bold text-zinc-500 uppercase tracking-widest mb-1.5">{label}</label>
              <input type={type} value={value} onChange={e => set(e.target.value)} placeholder={placeholder} required
                className="w-full bg-zinc-900 border border-zinc-800 rounded-xl px-4 py-2.5 text-sm outline-none focus:border-indigo-500/60 transition-all placeholder:text-zinc-600"/>
            </div>
          ))}
          {error && (
            <div className="flex items-center gap-2 text-red-400 text-xs bg-red-400/10 p-3 rounded-lg border border-red-400/20">
              <AlertCircle size={13}/>{error}
            </div>
          )}
          <div className="flex items-center gap-2 text-xs text-zinc-600 bg-zinc-900/50 p-3 rounded-lg border border-zinc-800/50">
            <ShieldCheck size={13} className="text-emerald-500 shrink-0"/>
            AES-256-GCM encryption · Argon2id key derivation
          </div>
          <button type="submit" disabled={loading || !name.trim() || !password}
            className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold py-2.5 rounded-xl transition-all text-sm flex items-center justify-center gap-2">
            {loading ? <Loader2 size={15} className="animate-spin"/> : "Create Vault"}
          </button>
        </form>
      </div>
    </div>
  );
}

function UnlockModal({ vault, onClose, onUnlocked }: { vault: Vault; onClose: () => void; onUnlocked: () => void }) {
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleUnlock(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true); setError(null);
    try {
      await api.unlockVault(vault.id, password);
      onUnlocked();
    } catch {
      setError("Incorrect password");
    } finally { setLoading(false); }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="w-full max-w-sm bg-[#111] border border-zinc-800 rounded-2xl p-8 shadow-2xl">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 bg-orange-500/10 rounded-xl flex items-center justify-center">
              <Lock size={17} className="text-orange-400"/>
            </div>
            <div>
              <p className="text-[10px] text-zinc-500 uppercase font-bold tracking-widest">Unlock</p>
              <p className="text-sm font-bold">{vault.name}</p>
            </div>
          </div>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-200 transition-colors"><X size={18}/></button>
        </div>
        <form onSubmit={handleUnlock} className="space-y-3">
          <input type="password" value={password} onChange={e => setPassword(e.target.value)}
            placeholder="Vault password…" autoFocus required
            className="w-full bg-zinc-900 border border-zinc-800 rounded-xl px-4 py-2.5 text-sm outline-none focus:border-indigo-500/60 transition-all placeholder:text-zinc-600"/>
          {error && (
            <div className="flex items-center gap-2 text-red-400 text-xs bg-red-400/10 p-3 rounded-lg border border-red-400/20">
              <AlertCircle size={13}/>{error}
            </div>
          )}
          <button type="submit" disabled={loading || !password}
            className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-semibold py-2.5 rounded-xl transition-all text-sm flex items-center justify-center gap-2">
            {loading ? <Loader2 size={15} className="animate-spin"/> : "Decrypt & Enter"}
          </button>
        </form>
      </div>
    </div>
  );
}

// ─── Knowledge View ───────────────────────────────────────────────────────────

function KnowledgeView({
  vault, documents, onDeleted, onRefresh,
}: { vault: Vault; documents: Document[]; onDeleted: () => void; onRefresh: () => void }) {
  const [expandedId, setExpandedId]   = useState<string | null>(null);
  const [entities, setEntities]       = useState<Record<string, Entity[]>>({});
  const [deletingId, setDeletingId]   = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<Document | null>(null);

  async function loadEntities(docId: string) {
    if (entities[docId] !== undefined) return;
    try {
      const data = await api.getDocumentEntities(docId);
      setEntities(prev => ({ ...prev, [docId]: data }));
    } catch {
      setEntities(prev => ({ ...prev, [docId]: [] }));
    }
  }

  function toggleExpand(docId: string) {
    if (expandedId === docId) {
      setExpandedId(null);
    } else {
      setExpandedId(docId);
      loadEntities(docId);
    }
  }

  async function handleDelete(doc: Document) {
    setDeletingId(doc.id);
    try {
      await api.deleteDocument(doc.id);
      setEntities(prev => { const n = { ...prev }; delete n[doc.id]; return n; });
      if (expandedId === doc.id) setExpandedId(null);
      onDeleted();
    } catch (e) {
      alert(e instanceof ApiError ? e.message : "Delete failed");
    } finally {
      setDeletingId(null);
      setConfirmDelete(null);
    }
  }

  const indexed = documents.filter(d => d.status === "indexed");
  const others  = documents.filter(d => d.status !== "indexed");

  return (
    <div className="space-y-6">
      {confirmDelete && (
        <ConfirmModal
          title="Delete Document"
          message={`Remove "${confirmDelete.filename}" and all its ${confirmDelete.chunk_count} chunks? This cannot be undone.`}
          danger
          onConfirm={() => handleDelete(confirmDelete)}
          onCancel={() => setConfirmDelete(null)}
        />
      )}

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Knowledge Base</h1>
          <p className="text-zinc-500 text-sm mt-1">{vault.document_count} documents · {vault.chunk_count} vectors</p>
        </div>
        <button onClick={onRefresh}
          className="text-xs text-zinc-500 hover:text-zinc-200 flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-zinc-900 hover:bg-zinc-800 transition-all border border-zinc-800">
          <Loader2 size={11}/>Refresh
        </button>
      </div>

      {/* Processing queue */}
      {others.length > 0 && (
        <div className="space-y-2">
          <p className="text-[10px] font-bold text-zinc-600 uppercase tracking-widest">Processing Queue</p>
          {others.map(doc => (
            <div key={doc.id} className="flex items-center gap-3 bg-zinc-900/40 border border-zinc-800/60 rounded-xl px-4 py-3">
              <FileText size={13} className="text-zinc-600 shrink-0"/>
              <span className="text-sm text-zinc-400 flex-1 truncate">{doc.filename}</span>
              <StatusBadge status={doc.status}/>
              {doc.error && <span className="text-[10px] text-red-400 truncate max-w-[180px]">{doc.error}</span>}
            </div>
          ))}
        </div>
      )}

      {indexed.length === 0 && others.length === 0 && (
        <div className="text-center py-20 text-zinc-700">
          <BookOpen size={40} className="mx-auto mb-3 opacity-20"/>
          <p className="text-sm">No documents yet. Upload files to get started.</p>
        </div>
      )}

      {/* Indexed documents */}
      {indexed.length > 0 && (
        <div className="space-y-2">
          <p className="text-[10px] font-bold text-zinc-600 uppercase tracking-widest">Indexed · {indexed.length}</p>
          {indexed.map(doc => (
            <div key={doc.id} className="bg-[#111] border border-zinc-800/60 rounded-2xl overflow-hidden hover:border-zinc-700/80 transition-all">
              <div className="flex items-center gap-3 px-4 py-3.5">
                <button onClick={() => toggleExpand(doc.id)}
                  className="text-zinc-600 hover:text-zinc-300 transition-colors shrink-0">
                  {expandedId === doc.id ? <ChevronDown size={14}/> : <ChevronRight size={14}/>}
                </button>
                <div className="w-8 h-8 bg-zinc-900 rounded-lg flex items-center justify-center border border-zinc-800 shrink-0">
                  <FileText size={13} className="text-zinc-500"/>
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-medium text-zinc-200 truncate">{doc.filename}</p>
                    <FileBadge type={doc.file_type}/>
                  </div>
                  {doc.summary && (
                    <p className="text-[11px] text-zinc-500 mt-0.5 line-clamp-1">{doc.summary}</p>
                  )}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className="text-[10px] text-zinc-600">{doc.chunk_count} chunks</span>
                  <StatusBadge status={doc.status}/>
                  <button
                    onClick={() => setConfirmDelete(doc)}
                    disabled={deletingId === doc.id}
                    className="w-7 h-7 flex items-center justify-center rounded-lg text-zinc-700 hover:text-red-400 hover:bg-red-500/10 transition-all disabled:opacity-40"
                    title="Delete document">
                    {deletingId === doc.id
                      ? <Loader2 size={12} className="animate-spin"/>
                      : <Trash2 size={12}/>}
                  </button>
                </div>
              </div>

              {expandedId === doc.id && (
                <div className="border-t border-zinc-800/60 px-5 py-4 space-y-4 bg-zinc-900/20">
                  {doc.summary && (
                    <div>
                      <p className="text-[10px] font-bold text-zinc-600 uppercase tracking-widest mb-1.5">Summary</p>
                      <p className="text-sm text-zinc-300 leading-relaxed">{doc.summary}</p>
                    </div>
                  )}
                  <div>
                    <p className="text-[10px] font-bold text-zinc-600 uppercase tracking-widest mb-2">Entities Detected</p>
                    {entities[doc.id] === undefined ? (
                      <div className="flex items-center gap-2 text-xs text-zinc-600">
                        <Loader2 size={11} className="animate-spin"/>Loading…
                      </div>
                    ) : entities[doc.id].length === 0 ? (
                      <span className="text-xs text-zinc-700">No entities detected</span>
                    ) : (
                      <div className="flex flex-wrap gap-1.5">
                        {entities[doc.id].slice(0, 40).map(e => (
                          <EntityChip key={e.id} entity={e}/>
                        ))}
                      </div>
                    )}
                  </div>
                  <p className="text-[10px] text-zinc-700">
                    Indexed {new Date(doc.created_at).toLocaleString()}
                  </p>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Upload View ──────────────────────────────────────────────────────────────

function UploadView({
  vault, documents, settings, onFilesAdded,
}: { vault: Vault; documents: Document[]; settings: AppSettings; onFilesAdded: () => void }) {
  const [dragging, setDragging]         = useState(false);
  const [uploading, setUploading]       = useState(false);
  const [uploadErrors, setUploadErrors] = useState<string[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  async function handleFiles(files: FileList | File[]) {
    const arr = Array.from(files);
    if (!arr.length) return;
    setUploading(true); setUploadErrors([]);
    const errs: string[] = [];
    for (const file of arr) {
      try {
        await api.ingestFile(file, settings.summaryMode, settings.ollamaUrl, settings.ollamaModel);
      } catch (e) {
        errs.push(`${file.name}: ${e instanceof ApiError ? e.message : "Upload failed"}`);
      }
    }
    setUploadErrors(errs);
    setUploading(false);
    onFilesAdded();
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault(); setDragging(false);
    handleFiles(e.dataTransfer.files);
  }

  const recent = documents.slice(0, 8);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Ingest Knowledge</h1>
        <p className="text-zinc-500 text-sm mt-1">
          Add documents to <span className="text-indigo-400 font-medium">{vault.name}</span>
          {settings.summaryMode !== "disabled" && (
            <span className="ml-2 text-[10px] text-zinc-600 bg-zinc-900 px-2 py-0.5 rounded border border-zinc-800">
              {settings.summaryMode === "ollama" ? `Ollama: ${settings.ollamaModel}` : "Extractive summary"}
            </span>
          )}
        </p>
      </div>

      {/* Drop zone */}
      <div
        onDragOver={e => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => !uploading && inputRef.current?.click()}
        className={cn(
          "border-2 border-dashed rounded-2xl p-12 flex flex-col items-center justify-center gap-4 cursor-pointer transition-all duration-200",
          dragging ? "border-indigo-500 bg-indigo-500/5" : "border-zinc-800 bg-zinc-900/20 hover:border-zinc-700 hover:bg-zinc-900/40",
          uploading && "opacity-60 cursor-not-allowed pointer-events-none",
        )}>
        <input ref={inputRef} type="file" multiple className="hidden"
          accept=".pdf,.docx,.txt,.md,.html,.csv,.json,.png,.jpg,.jpeg,.webp,.xlsx,.epub"
          onChange={e => e.target.files && handleFiles(e.target.files)}/>
        <div className={cn("w-14 h-14 rounded-2xl flex items-center justify-center border transition-all duration-200",
          dragging ? "bg-indigo-500/20 border-indigo-500/40 scale-110" : "bg-zinc-900 border-zinc-800")}>
          {uploading
            ? <Loader2 size={26} className="text-indigo-400 animate-spin"/>
            : <Upload size={26} className={dragging ? "text-indigo-400" : "text-zinc-600"}/>}
        </div>
        <div className="text-center">
          <p className="font-semibold text-zinc-300">
            {uploading ? "Uploading…" : "Drop files here or click to browse"}
          </p>
          <p className="text-xs text-zinc-600 mt-1">
            PDF · DOCX · MD · TXT · HTML · CSV · JSON · XLSX · EPUB · PNG · JPG · WEBP
          </p>
        </div>
      </div>

      {uploadErrors.length > 0 && (
        <div className="space-y-1.5">
          {uploadErrors.map((e, i) => (
            <div key={i} className="flex items-start gap-2 text-red-400 text-xs bg-red-400/10 p-3 rounded-lg border border-red-400/20">
              <AlertCircle size={12} className="mt-0.5 shrink-0"/>{e}
            </div>
          ))}
        </div>
      )}

      {/* Recent documents */}
      {recent.length > 0 && (
        <div>
          <p className="text-[10px] font-bold text-zinc-600 uppercase tracking-widest mb-2">Recent</p>
          <div className="space-y-1.5">
            {recent.map(doc => (
              <div key={doc.id} className="flex items-center gap-3 bg-[#111] border border-zinc-800/60 rounded-xl px-4 py-3 hover:border-zinc-700 transition-all">
                <FileText size={13} className="text-zinc-600 shrink-0"/>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-zinc-300 truncate">{doc.filename}</p>
                  <div className="flex items-center gap-2 mt-0.5">
                    <FileBadge type={doc.file_type}/>
                    {doc.chunk_count > 0 && <span className="text-[10px] text-zinc-700">{doc.chunk_count} chunks</span>}
                    {doc.status === "indexed" && doc.summary && (
                      <span className="text-[10px] text-zinc-600 truncate max-w-[200px]">{doc.summary}</span>
                    )}
                  </div>
                </div>
                <StatusBadge status={doc.status}/>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Search View ──────────────────────────────────────────────────────────────

function SearchView({ vault, settings }: { vault: Vault; settings: AppSettings }) {
  const [query, setQuery]           = useState("");
  const [results, setResults]       = useState<SearchResult[]>([]);
  const [loading, setLoading]       = useState(false);
  const [searched, setSearched]     = useState(false);
  const [error, setError]           = useState<string | null>(null);
  const [localThreshold, setLocalThreshold] = useState(settings.searchThreshold);

  useEffect(() => { setLocalThreshold(settings.searchThreshold); }, [settings.searchThreshold]);

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    setLoading(true); setError(null);
    try {
      const data = await api.search(query, settings.searchTopK, localThreshold);
      setResults(data.results);
      setSearched(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Search failed");
    } finally { setLoading(false); }
  }

  const RELEVANCE_STYLE = {
    Strong:   "bg-emerald-500/15 text-emerald-400 border-emerald-500/25",
    Good:     "bg-blue-500/15 text-blue-400 border-blue-500/25",
    Weak:     "bg-yellow-500/15 text-yellow-500 border-yellow-500/25",
    Marginal: "bg-zinc-800 text-zinc-500 border-zinc-700",
  } as const;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Semantic Search</h1>
        <p className="text-zinc-500 text-sm mt-1">
          {vault.chunk_count} chunks · <span className="text-indigo-400 font-medium">{vault.name}</span>
        </p>
      </div>

      {/* Threshold inline control */}
      <div className="flex items-center gap-4 bg-zinc-900/50 border border-zinc-800/60 rounded-xl px-4 py-2.5">
        <SlidersHorizontal size={13} className="text-zinc-600 shrink-0"/>
        <span className="text-[11px] text-zinc-500 font-semibold whitespace-nowrap">Relevance threshold</span>
        <input type="range" min="0.10" max="0.90" step="0.05"
          value={localThreshold}
          onChange={e => setLocalThreshold(parseFloat(e.target.value))}
          className="flex-1 h-1 accent-indigo-500"/>
        <span className="text-xs font-bold text-indigo-400 w-8 text-right">{(localThreshold * 100).toFixed(0)}%</span>
        <span className="text-[10px] text-zinc-600 border-l border-zinc-800 pl-3 w-16">
          {localThreshold >= 0.7 ? "Strict" : localThreshold >= 0.5 ? "Moderate" : localThreshold >= 0.35 ? "Loose" : "Very Loose"}
        </span>
      </div>

      <form onSubmit={handleSearch} className="relative group">
        <div className="absolute inset-0 bg-indigo-500/8 blur-xl rounded-2xl opacity-0 group-focus-within:opacity-100 transition-opacity duration-500"/>
        <div className="relative flex items-center bg-zinc-900 border border-zinc-800 rounded-2xl p-2 focus-within:border-indigo-500/50 transition-all">
          <Search className="ml-3 text-zinc-600 shrink-0" size={17}/>
          <input value={query} onChange={e => setQuery(e.target.value)}
            placeholder="Search by concept, entity, topic, code pattern…"
            className="flex-1 bg-transparent outline-none px-4 py-2.5 text-sm placeholder:text-zinc-700"/>
          <button type="submit" disabled={loading || !query.trim()}
            className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white px-5 py-2 rounded-xl text-sm font-semibold transition-all flex items-center gap-2">
            {loading ? <Loader2 size={13} className="animate-spin"/> : <Zap size={13}/>}Query
          </button>
        </div>
      </form>

      {error && (
        <div className="flex items-center gap-2 text-red-400 text-sm bg-red-500/10 p-4 rounded-xl border border-red-400/20">
          <AlertCircle size={14}/>{error}
        </div>
      )}

      {searched && results.length === 0 && !loading && (
        <div className="text-center py-16 text-zinc-700">
          <Search size={36} className="mx-auto mb-3 opacity-20"/>
          <p className="text-sm font-medium">No results above {(localThreshold * 100).toFixed(0)}% threshold</p>
          <p className="text-xs mt-1 text-zinc-800">Lower the threshold slider or try different wording</p>
        </div>
      )}

      <div className="space-y-3">
        {results.map(res => (
          <div key={res.chunk_id} className="bg-[#111] border border-zinc-800/60 rounded-2xl p-5 hover:border-zinc-700 transition-all">
            <div className="flex items-start justify-between gap-4 mb-3">
              <div className="flex items-center gap-2 min-w-0">
                <FileText size={12} className="text-indigo-400 shrink-0"/>
                <div className="min-w-0">
                  <span className="text-xs font-semibold text-zinc-300 truncate block">{res.filename}</span>
                  {res.section && <span className="text-[10px] text-zinc-600 truncate block">{res.section}</span>}
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {res.language && (
                  <span className="text-[10px] text-zinc-600 bg-zinc-900 px-2 py-0.5 rounded uppercase font-bold flex items-center gap-1">
                    <Globe size={9}/>{res.language}
                  </span>
                )}
                <span className={cn("px-2.5 py-0.5 rounded-lg text-[11px] font-bold border",
                  RELEVANCE_STYLE[res.relevance_label as keyof typeof RELEVANCE_STYLE] ?? RELEVANCE_STYLE.Marginal)}>
                  {res.relevance_label} · {(res.score * 100).toFixed(0)}%
                </span>
              </div>
            </div>
            <p className="text-zinc-300 text-sm leading-relaxed line-clamp-5">{res.content}</p>
            {res.tags.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-3">
                {res.tags.map(tag => (
                  <span key={tag} className="text-[10px] font-medium text-indigo-400/70 bg-indigo-500/10 px-2 py-0.5 rounded-md border border-indigo-500/20">{tag}</span>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Settings View ────────────────────────────────────────────────────────────

function SettingsView({
  vault, settings, onUpdate, onVaultRenamed, onVaultDeleted,
}: {
  vault: Vault | null;
  settings: AppSettings;
  onUpdate: (s: Partial<AppSettings>) => void;
  onVaultRenamed: (v: Vault) => void;
  onVaultDeleted: (id: string) => void;
}) {
  const [backendStatus,  setBackendStatus]  = useState<"idle" | "ok" | "error">("idle");
  const [ollamaStatus,   setOllamaStatus]   = useState<"idle" | "ok" | "error">("idle");
  const [renaming,       setRenaming]       = useState(false);
  const [newVaultName,   setNewVaultName]   = useState(vault?.name ?? "");
  const [renameError,    setRenameError]    = useState<string | null>(null);
  const [confirmVaultDelete, setConfirmVaultDelete] = useState(false);

  async function testBackend() {
    setBackendStatus("idle");
    try { api.setBaseUrl(settings.backendUrl); await api.checkHealth(); setBackendStatus("ok"); }
    catch { setBackendStatus("error"); }
  }

  async function testOllama() {
    setOllamaStatus("idle");
    try {
      const res = await fetch(`${settings.ollamaUrl}/api/tags`, { signal: AbortSignal.timeout(3000) });
      setOllamaStatus(res.ok ? "ok" : "error");
    } catch { setOllamaStatus("error"); }
  }

  async function handleRename() {
    if (!vault || !newVaultName.trim() || newVaultName.trim() === vault.name) {
      setRenaming(false); return;
    }
    setRenameError(null);
    try {
      const updated = await api.renameVault(vault.id, newVaultName.trim());
      setRenaming(false);
      onVaultRenamed(updated);  // ← propagate to App state, no page reload
    } catch (e) {
      setRenameError(e instanceof ApiError ? e.message : "Failed");
    }
  }

  async function handleVaultDelete() {
    if (!vault) return;
    try {
      await api.deleteVault(vault.id);
      onVaultDeleted(vault.id);
    } catch (e) {
      alert(e instanceof ApiError ? e.message : "Delete failed");
    } finally { setConfirmVaultDelete(false); }
  }

  function Dot({ status }: { status: "idle" | "ok" | "error" }) {
    return <span className={cn("inline-block w-2 h-2 rounded-full",
      status === "ok" ? "bg-emerald-400" : status === "error" ? "bg-red-400" : "bg-zinc-700")}/>;
  }

  function Section({ title, children }: { title: string; children: React.ReactNode }) {
    return (
      <div className="bg-[#111] border border-zinc-800/60 rounded-2xl overflow-hidden">
        <div className="px-5 py-3 border-b border-zinc-800/60 bg-zinc-900/30">
          <h3 className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">{title}</h3>
        </div>
        <div className="p-5 space-y-5">{children}</div>
      </div>
    );
  }

  function Row({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
    return (
      <div className="flex items-start justify-between gap-6">
        <div className="shrink-0">
          <p className="text-sm font-medium text-zinc-200">{label}</p>
          {hint && <p className="text-[11px] text-zinc-600 mt-0.5 max-w-[200px]">{hint}</p>}
        </div>
        <div className="shrink-0">{children}</div>
      </div>
    );
  }

  function Toggle({ value, onChange }: { value: boolean; onChange: (v: boolean) => void }) {
    return (
      <div onClick={() => onChange(!value)}
        className={cn("w-10 h-5 rounded-full transition-all relative cursor-pointer",
          value ? "bg-indigo-600" : "bg-zinc-700")}>
        <div className={cn("absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-all",
          value ? "left-5" : "left-0.5")}/>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {confirmVaultDelete && (
        <ConfirmModal
          title="Delete Vault"
          message={`Permanently delete "${vault?.name}" including all documents, chunks, and the FAISS index? Cannot be undone.`}
          danger
          onConfirm={handleVaultDelete}
          onCancel={() => setConfirmVaultDelete(false)}
        />
      )}

      <div>
        <h1 className="text-2xl font-bold">Settings</h1>
        <p className="text-zinc-500 text-sm mt-1">Configuration & preferences</p>
      </div>

      {/* Search */}
      <Section title="Search & Retrieval">
        <Row label="Relevance Threshold"
          hint={`Cosine similarity floor. Recommended: 45–65%`}>
          <div className="flex items-center gap-3">
            <input type="range" min="0.10" max="0.90" step="0.05"
              value={settings.searchThreshold}
              onChange={e => onUpdate({ searchThreshold: parseFloat(e.target.value) })}
              className="w-32 h-1 accent-indigo-500"/>
            <span className="text-sm font-bold text-indigo-400 w-8">{(settings.searchThreshold * 100).toFixed(0)}%</span>
          </div>
        </Row>
        <Row label="Max Results" hint="Results per query">
          <div className="flex items-center gap-3">
            <input type="range" min="1" max="50" step="1"
              value={settings.searchTopK}
              onChange={e => onUpdate({ searchTopK: parseInt(e.target.value) })}
              className="w-32 h-1 accent-indigo-500"/>
            <span className="text-sm font-bold text-indigo-400 w-6">{settings.searchTopK}</span>
          </div>
        </Row>
      </Section>

      {/* Summarization */}
      <Section title="AI Summarization">
        <Row label="Mode" hint="Applied to newly ingested files">
          <select value={settings.summaryMode}
            onChange={e => onUpdate({ summaryMode: e.target.value as AppSettings["summaryMode"] })}
            className="bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-1.5 text-sm outline-none focus:border-indigo-500/50">
            <option value="extractive">Extractive (offline · fast)</option>
            <option value="ollama">Ollama (local LLM)</option>
            <option value="disabled">Disabled</option>
          </select>
        </Row>
        {settings.summaryMode === "ollama" && (
          <>
            <Row label="Ollama URL">
              <div className="flex items-center gap-2">
                <input value={settings.ollamaUrl} onChange={e => onUpdate({ ollamaUrl: e.target.value })}
                  className="bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-1.5 text-sm w-48 outline-none focus:border-indigo-500/50"/>
                <button onClick={testOllama}
                  className="text-xs text-zinc-400 hover:text-white bg-zinc-900 border border-zinc-800 px-2.5 py-1.5 rounded-lg flex items-center gap-1.5 transition-all">
                  <Dot status={ollamaStatus}/> Test
                </button>
              </div>
            </Row>
            <Row label="Model" hint="e.g. llama3.2:3b, mistral:7b">
              <input value={settings.ollamaModel} onChange={e => onUpdate({ ollamaModel: e.target.value })}
                className="bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-1.5 text-sm w-40 outline-none focus:border-indigo-500/50"/>
            </Row>
          </>
        )}
      </Section>

      {/* Backend */}
      <Section title="Backend">
        <Row label="API URL">
          <div className="flex items-center gap-2">
            <input value={settings.backendUrl} onChange={e => onUpdate({ backendUrl: e.target.value })}
              className="bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-1.5 text-sm w-52 outline-none focus:border-indigo-500/50"/>
            <button onClick={testBackend}
              className="text-xs text-zinc-400 hover:text-white bg-zinc-900 border border-zinc-800 px-2.5 py-1.5 rounded-lg flex items-center gap-1.5 transition-all">
              <Dot status={backendStatus}/> Test
            </button>
          </div>
        </Row>
        <Row label="OCR" hint="Requires tesseract system install">
          <Toggle value={settings.ocrEnabled} onChange={v => onUpdate({ ocrEnabled: v })}/>
        </Row>
      </Section>

      {/* Vault management */}
      {vault && (
        <Section title={`Vault: ${vault.name}`}>
          <Row label="Rename">
            {renaming ? (
              <div className="flex items-center gap-2">
                <input value={newVaultName} onChange={e => setNewVaultName(e.target.value)}
                  onKeyDown={e => { if (e.key === "Enter") handleRename(); if (e.key === "Escape") { setRenaming(false); setNewVaultName(vault.name); } }}
                  autoFocus
                  className="bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-1.5 text-sm w-40 outline-none focus:border-indigo-500/50"/>
                <button onClick={handleRename}
                  className="text-xs bg-indigo-600 hover:bg-indigo-500 text-white px-3 py-1.5 rounded-lg transition-all">Save</button>
                <button onClick={() => { setRenaming(false); setNewVaultName(vault.name); }}
                  className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors">Cancel</button>
              </div>
            ) : (
              <button onClick={() => setRenaming(true)}
                className="flex items-center gap-1.5 text-xs text-zinc-400 hover:text-white bg-zinc-900 border border-zinc-800 px-3 py-1.5 rounded-lg transition-all">
                <Edit3 size={12}/> Rename
              </button>
            )}
          </Row>
          {renameError && <p className="text-xs text-red-400">{renameError}</p>}
          <Row label="Embedding model">
            <span className="text-xs text-zinc-500 font-mono bg-zinc-900 px-2.5 py-1 rounded-lg border border-zinc-800">
              all-MiniLM-L6-v2 · 384d
            </span>
          </Row>
          <Row label="Index size">
            <span className="text-xs text-zinc-500">{vault.chunk_count} vectors · FAISS IndexIDMap2</span>
          </Row>
          <Row label="Danger Zone">
            <button onClick={() => setConfirmVaultDelete(true)}
              className="flex items-center gap-1.5 text-xs text-red-400 hover:text-red-300 bg-red-500/10 hover:bg-red-500/15 border border-red-500/20 px-3 py-1.5 rounded-lg transition-all">
              <Trash2 size={12}/> Delete Vault
            </button>
          </Row>
        </Section>
      )}

      {/* About */}
      <Section title="About">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 bg-indigo-600 rounded-xl flex items-center justify-center shadow-lg shadow-indigo-600/20 shrink-0">
            <Cpu size={16} className="text-white"/>
          </div>
          <div>
            <p className="font-bold text-sm">Ragna — AI Memory Compiler</p>
            <p className="text-[11px] text-zinc-600">v0.2.0-mvp · Local-first · Privacy-first</p>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2 text-[11px]">
          {[
            ["Vector search",  "FAISS IndexIDMap2"],
            ["Similarity",     "Cosine (L2-norm)"],
            ["Encryption",     "AES-256-GCM / chunk"],
            ["KDF",            "Argon2id 64MB·3pass"],
            ["Summarization",  "Extractive / Ollama"],
            ["NER",            "Rule-based + NLTK"],
          ].map(([k, v]) => (
            <div key={k} className="bg-zinc-900/50 rounded-lg px-3 py-2 border border-zinc-800/50">
              <p className="text-zinc-600">{k}</p>
              <p className="text-zinc-400 font-medium mt-0.5">{v}</p>
            </div>
          ))}
        </div>
      </Section>
    </div>
  );
}

// ─── App root ─────────────────────────────────────────────────────────────────

export default function App() {
  const [settings, updateSettings] = useSettings();
  const [vaults, setVaults]               = useState<Vault[]>([]);
  const [activeVault, setActiveVault]     = useState<Vault | null>(null);
  const [isUnlocked, setIsUnlocked]       = useState(false);
  const [view, setView]                   = useState<View>("upload");
  const [documents, setDocuments]         = useState<Document[]>([]);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showUnlockModal, setShowUnlockModal] = useState(false);
  const [showHelp, setShowHelp]           = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── Data refresh ────────────────────────────────────────────────────────
  const refreshVaults = useCallback(async () => {
    try {
      const data = await api.getVaults();
      setVaults(data);
      if (activeVault) {
        const updated = data.find(v => v.id === activeVault.id);
        if (updated) setActiveVault(updated);
      }
    } catch {}
  }, [activeVault?.id]);

  const refreshDocuments = useCallback(async () => {
    if (!activeVault || !isUnlocked) return;
    try {
      const docs = await api.getDocuments(activeVault.id);
      setDocuments(docs);
      await refreshVaults();
      const hasActive = docs.some(d => d.status === "pending" || d.status === "processing");
      if (!hasActive && pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    } catch {}
  }, [activeVault?.id, isUnlocked]);

  useEffect(() => { refreshVaults(); }, []);

  useEffect(() => {
    if (!isUnlocked || !activeVault) return;
    refreshDocuments();
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [isUnlocked, activeVault?.id]);

  function startPolling() {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(refreshDocuments, 2500);
  }

  // ── Vault handlers ───────────────────────────────────────────────────────
  async function handleVaultSelect(vault: Vault) {
    if (isUnlocked && vault.id === activeVault?.id) return;
    if (isUnlocked && activeVault) {
      try { await api.lockVault(activeVault.id); } catch {}
    }
    setIsUnlocked(false); setDocuments([]);
    setActiveVault(vault); setShowUnlockModal(true);
  }

  function handleUnlocked() {
    setIsUnlocked(true); setShowUnlockModal(false);
    setView("upload"); refreshDocuments();
  }

  async function handleLock() {
    if (!activeVault) return;
    try { await api.lockVault(activeVault.id); } catch {}
    setIsUnlocked(false); setDocuments([]);
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  }

  function handleVaultRenamed(updated: Vault) {
    setVaults(prev => prev.map(v => v.id === updated.id ? updated : v));
    setActiveVault(updated);
  }

  function handleVaultDeleted(vaultId: string) {
    setVaults(prev => prev.filter(v => v.id !== vaultId));
    if (activeVault?.id === vaultId) {
      setActiveVault(null); setIsUnlocked(false); setDocuments([]);
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    }
  }

  function handleFilesAdded() { refreshDocuments(); startPolling(); }

  const navItems: { id: View; label: string; icon: typeof Search }[] = [
    { id: "search",    label: "Search",    icon: Search },
    { id: "upload",    label: "Ingest",    icon: Upload },
    { id: "knowledge", label: "Knowledge", icon: BookOpen },
    { id: "settings",  label: "Settings",  icon: Settings },
  ];

  return (
    <div className="flex h-screen w-screen bg-[#0a0a0a] text-zinc-100 overflow-hidden font-sans">

      {showCreateModal && (
        <VaultCreateModal
          onClose={() => setShowCreateModal(false)}
          onCreated={v => { setShowCreateModal(false); refreshVaults(); }}
        />
      )}
      {showUnlockModal && activeVault && (
        <UnlockModal vault={activeVault} onClose={() => setShowUnlockModal(false)} onUnlocked={handleUnlocked}/>
      )}
      {showHelp && <HelpModal onClose={() => setShowHelp(false)}/>}

      {/* ── Sidebar ── */}
      <aside className="w-56 bg-[#0e0e0e] border-r border-zinc-800/70 flex flex-col shrink-0">
        {/* Logo */}
        <div className="px-4 py-5 flex items-center gap-2.5">
          <div className="w-8 h-8 bg-indigo-600 rounded-lg flex items-center justify-center shadow-lg shadow-indigo-600/20">
            <Cpu size={14} className="text-white"/>
          </div>
          <div>
            <span className="font-bold text-sm tracking-tight">Ragna</span>
            <span className="block text-[9px] text-zinc-600 font-medium uppercase tracking-widest mt-0.5">Memory Compiler</span>
          </div>
        </div>

        {/* Nav */}
        <nav className="px-2 space-y-0.5 mb-2">
          {navItems
            .filter(item => isUnlocked || item.id === "settings")
            .map(({ id, label, icon: Icon }) => (
              <button key={id} onClick={() => setView(id)}
                className={cn("w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all",
                  view === id ? "bg-zinc-800 text-white font-semibold" : "text-zinc-500 hover:text-zinc-200 hover:bg-zinc-900")}>
                <Icon size={14}/>{label}
              </button>
            ))}
        </nav>

        {/* Vaults */}
        <div className="flex-1 px-2 overflow-y-auto">
          <div className="px-2 mb-1.5">
            <span className="text-[9px] font-bold text-zinc-700 uppercase tracking-widest">Vaults</span>
          </div>
          {vaults.map(v => {
            const active   = activeVault?.id === v.id;
            const unlocked = active && isUnlocked;
            return (
              <button key={v.id} onClick={() => handleVaultSelect(v)}
                className={cn("w-full flex items-center justify-between px-3 py-2.5 rounded-lg text-sm transition-all group",
                  active ? "bg-zinc-800 text-white" : "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-900")}>
                <div className="flex items-center gap-2 min-w-0">
                  <Database size={12} className={unlocked ? "text-emerald-400" : ""}/>
                  <span className="truncate font-medium text-xs">{v.name}</span>
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  {unlocked
                    ? <Unlock size={10} className="text-emerald-400"/>
                    : <Lock size={10} className="text-zinc-700"/>}
                </div>
              </button>
            );
          })}
          <button onClick={() => setShowCreateModal(true)}
            className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs text-zinc-700 hover:text-indigo-400 hover:bg-zinc-900 transition-all mt-1">
            <Plus size={12}/> New Vault
          </button>
        </div>

        {/* Status bar */}
        <div className="p-3 border-t border-zinc-800/60">
          <div className="flex items-center justify-between px-2 py-1">
            <div className="flex items-center gap-2">
              <div className={cn("w-1.5 h-1.5 rounded-full",
                isUnlocked ? "bg-emerald-400 shadow-sm shadow-emerald-400/50" : "bg-zinc-700")}/>
              <span className="text-[10px] font-semibold text-zinc-600 uppercase tracking-widest truncate max-w-[90px]">
                {isUnlocked ? activeVault?.name : "Locked"}
              </span>
            </div>
            <div className="flex items-center gap-1.5">
              <button onClick={() => setShowHelp(true)} className="text-zinc-700 hover:text-indigo-400 transition-colors" title="Help">
                <HelpCircle size={11}/>
              </button>
              {isUnlocked && (
                <button onClick={handleLock} className="text-zinc-700 hover:text-orange-400 transition-colors" title="Lock">
                  <Lock size={11}/>
                </button>
              )}
            </div>
          </div>
        </div>
      </aside>

      {/* ── Main ── */}
      <main className="flex-1 min-w-0 overflow-y-auto bg-[#0a0a0a]">
        <div className="max-w-4xl mx-auto p-8">
          {view === "settings" ? (
            <SettingsView
              vault={activeVault}
              settings={settings}
              onUpdate={updateSettings}
              onVaultRenamed={handleVaultRenamed}
              onVaultDeleted={handleVaultDeleted}
            />
          ) : !activeVault ? (
            <div className="flex flex-col items-center justify-center mt-24 text-zinc-700 select-none">
              <Database size={48} className="mb-4 opacity-15"/>
              <p className="text-sm font-medium">Select a vault to get started</p>
              <button onClick={() => setShowHelp(true)} className="mt-4 text-[10px] text-zinc-600 hover:text-indigo-400 flex items-center gap-1.5 uppercase font-bold tracking-widest transition-colors">
                <HelpCircle size={12}/> How it works
              </button>
            </div>
          ) : !isUnlocked ? (
            <div className="flex flex-col items-center justify-center mt-24 text-zinc-700 select-none">
              <Lock size={44} className="mb-4 opacity-15"/>
              <p className="text-sm font-medium">Vault is locked</p>
              <button onClick={() => setShowUnlockModal(true)}
                className="mt-4 text-xs font-semibold text-indigo-400 hover:text-indigo-300 flex items-center gap-1 transition-colors">
                <Unlock size={12}/> Unlock
              </button>
            </div>
          ) : (
            <>
              {view === "search"    && <SearchView vault={activeVault} settings={settings}/>}
              {view === "upload"    && (
                <UploadView vault={activeVault} documents={documents} settings={settings}
                  onFilesAdded={handleFilesAdded}/>
              )}
              {view === "knowledge" && (
                <KnowledgeView vault={activeVault} documents={documents}
                  onDeleted={() => { refreshDocuments(); refreshVaults(); }}
                  onRefresh={refreshDocuments}/>
              )}
            </>
          )}
        </div>
      </main>
    </div>
  );
}
