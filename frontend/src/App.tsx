import { useState, useEffect, useCallback, useRef } from "react";
import {
  Search, Upload, Database, Lock, Unlock, FileText, Plus,
  ShieldCheck, Loader2, AlertCircle, X, CheckCircle2,
  Clock, XCircle, ChevronRight, Cpu, FolderOpen, Zap, Trash2,
} from "lucide-react";
import { cn } from "./lib/utils";
import { api, Vault, Document, SearchResult, ApiError } from "./lib/api";
import "./App.css";

// ─── Types ────────────────────────────────────────────────────────────────────

type View = "search" | "upload" | "vault";

// ─── Sub-components ───────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: Document["status"] }) {
  const map = {
    pending:    { icon: Clock,        color: "text-yellow-500", bg: "bg-yellow-500/10", label: "Pending" },
    processing: { icon: Loader2,      color: "text-blue-400",   bg: "bg-blue-500/10",   label: "Processing" },
    indexed:    { icon: CheckCircle2, color: "text-emerald-400",bg: "bg-emerald-500/10",label: "Indexed" },
    failed:     { icon: XCircle,      color: "text-red-400",    bg: "bg-red-500/10",    label: "Failed" },
  } as const;
  const { icon: Icon, color, bg, label } = map[status];
  return (
    <span className={cn("inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-[11px] font-semibold", bg, color)}>
      <Icon size={11} className={status === "processing" ? "animate-spin" : ""} />
      {label}
    </span>
  );
}

function FileTypeIcon({ type }: { type: string }) {
  const colors: Record<string, string> = {
    pdf: "text-red-400", docx: "text-blue-400", md: "text-purple-400",
    txt: "text-zinc-400", json: "text-yellow-400", csv: "text-green-400",
    html: "text-orange-400", png: "text-pink-400", jpg: "text-pink-400",
  };
  return (
    <span className={cn("text-[10px] font-bold uppercase", colors[type] ?? "text-zinc-500")}>
      {type}
    </span>
  );
}

// ─── Vault Create Modal ───────────────────────────────────────────────────────

function VaultCreateModal({
  onClose, onCreated,
}: { onClose: () => void; onCreated: (v: Vault) => void }) {
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (password !== confirm) { setError("Passwords do not match"); return; }
    if (password.length < 6) { setError("Password must be at least 6 characters"); return; }
    setLoading(true); setError(null);
    try {
      const vault = await api.createVault(name.trim(), password);
      onCreated(vault);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create vault");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="w-full max-w-md bg-[#111111] border border-zinc-800 rounded-2xl p-8 shadow-2xl">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-bold text-white">New Vault</h2>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-200 transition-colors">
            <X size={20} />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-zinc-400 mb-1.5 uppercase tracking-wider">Vault Name</label>
            <input
              value={name} onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Research 2025"
              required
              className="w-full bg-zinc-900 border border-zinc-800 rounded-xl px-4 py-2.5 text-sm outline-none focus:border-indigo-500/60 transition-all placeholder:text-zinc-600"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-zinc-400 mb-1.5 uppercase tracking-wider">Encryption Password</label>
            <input
              type="password" value={password} onChange={(e) => setPassword(e.target.value)}
              placeholder="Strong passphrase..."
              required
              className="w-full bg-zinc-900 border border-zinc-800 rounded-xl px-4 py-2.5 text-sm outline-none focus:border-indigo-500/60 transition-all placeholder:text-zinc-600"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-zinc-400 mb-1.5 uppercase tracking-wider">Confirm Password</label>
            <input
              type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)}
              placeholder="Repeat passphrase..."
              required
              className="w-full bg-zinc-900 border border-zinc-800 rounded-xl px-4 py-2.5 text-sm outline-none focus:border-indigo-500/60 transition-all placeholder:text-zinc-600"
            />
          </div>
          {error && (
            <div className="flex items-center gap-2 text-red-400 text-xs bg-red-400/10 p-3 rounded-lg border border-red-400/20">
              <AlertCircle size={13} /> {error}
            </div>
          )}
          <div className="flex items-center gap-2 text-xs text-zinc-500 bg-zinc-900/50 p-3 rounded-lg border border-zinc-800/50">
            <ShieldCheck size={13} className="text-emerald-500 shrink-0" />
            AES-256-GCM encryption · Argon2id key derivation
          </div>
          <button
            type="submit" disabled={loading || !name.trim() || !password}
            className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold py-2.5 rounded-xl transition-all text-sm flex items-center justify-center gap-2"
          >
            {loading ? <Loader2 size={16} className="animate-spin" /> : "Create Vault"}
          </button>
        </form>
      </div>
    </div>
  );
}

// ─── Unlock Modal ─────────────────────────────────────────────────────────────

function UnlockModal({
  vault, onClose, onUnlocked,
}: { vault: Vault; onClose: () => void; onUnlocked: () => void }) {
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
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="w-full max-w-sm bg-[#111111] border border-zinc-800 rounded-2xl p-8 shadow-2xl">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 bg-orange-500/10 rounded-xl flex items-center justify-center">
              <Lock size={18} className="text-orange-400" />
            </div>
            <div>
              <p className="text-[10px] text-zinc-500 uppercase font-semibold tracking-widest">Unlock</p>
              <p className="text-sm font-bold text-white">{vault.name}</p>
            </div>
          </div>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-200 transition-colors">
            <X size={18} />
          </button>
        </div>
        <form onSubmit={handleUnlock} className="space-y-3">
          <input
            type="password" value={password} onChange={(e) => setPassword(e.target.value)}
            placeholder="Vault password..."
            autoFocus required
            className="w-full bg-zinc-900 border border-zinc-800 rounded-xl px-4 py-2.5 text-sm outline-none focus:border-indigo-500/60 transition-all placeholder:text-zinc-600"
          />
          {error && (
            <div className="flex items-center gap-2 text-red-400 text-xs bg-red-400/10 p-3 rounded-lg border border-red-400/20">
              <AlertCircle size={13} /> {error}
            </div>
          )}
          <button
            type="submit" disabled={loading || !password}
            className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white font-semibold py-2.5 rounded-xl transition-all text-sm flex items-center justify-center gap-2"
          >
            {loading ? <Loader2 size={16} className="animate-spin" /> : "Decrypt & Enter"}
          </button>
        </form>
      </div>
    </div>
  );
}

// ─── Upload View ──────────────────────────────────────────────────────────────

function UploadView({
  vault, documents, onFilesAdded, onDeleteDocument,
}: {
  vault: Vault;
  documents: Document[];
  onFilesAdded: () => void;
  onDeleteDocument: (id: string) => void;
}) {
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadErrors, setUploadErrors] = useState<string[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  async function handleFiles(files: FileList | File[]) {
    const arr = Array.from(files);
    if (!arr.length) return;
    setUploading(true);
    setUploadErrors([]);
    const errs: string[] = [];
    for (const file of arr) {
      try {
        await api.ingestFile(file);
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

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Ingest Knowledge</h1>
        <p className="text-zinc-500 text-sm mt-1">Add documents to <span className="text-indigo-400 font-medium">{vault.name}</span></p>
      </div>

      {/* Drop zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => !uploading && inputRef.current?.click()}
        className={cn(
          "border-2 border-dashed rounded-2xl p-12 flex flex-col items-center justify-center gap-4 cursor-pointer transition-all duration-200",
          dragging ? "border-indigo-500 bg-indigo-500/5" : "border-zinc-800 bg-zinc-900/20 hover:border-zinc-700 hover:bg-zinc-900/40",
          uploading && "opacity-60 cursor-not-allowed pointer-events-none"
        )}
      >
        <input
          ref={inputRef} type="file" multiple className="hidden"
          accept=".pdf,.docx,.txt,.md,.html,.csv,.json,.png,.jpg,.jpeg,.webp"
          onChange={(e) => e.target.files && handleFiles(e.target.files)}
        />
        <div className={cn("w-16 h-16 rounded-2xl flex items-center justify-center border transition-all duration-200",
          dragging ? "bg-indigo-500/20 border-indigo-500/40 scale-110" : "bg-zinc-900 border-zinc-800"
        )}>
          {uploading
            ? <Loader2 size={28} className="text-indigo-400 animate-spin" />
            : <Upload size={28} className={dragging ? "text-indigo-400" : "text-zinc-500"} />
          }
        </div>
        <div className="text-center">
          <p className="font-semibold text-zinc-200">{uploading ? "Uploading files…" : "Drop files here or click to browse"}</p>
          <p className="text-xs text-zinc-500 mt-1">PDF, DOCX, MD, TXT, HTML, CSV, JSON, PNG, JPG · Multiple files supported</p>
        </div>
      </div>

      {uploadErrors.length > 0 && (
        <div className="space-y-2">
          {uploadErrors.map((e, i) => (
            <div key={i} className="flex items-start gap-2 text-red-400 text-xs bg-red-400/10 p-3 rounded-lg border border-red-400/20">
              <AlertCircle size={13} className="mt-0.5 shrink-0" /> {e}
            </div>
          ))}
        </div>
      )}

      {/* Document list */}
      {documents.length > 0 && (
        <div>
          <h3 className="text-xs font-bold text-zinc-500 uppercase tracking-widest mb-3">
            Documents · {documents.length}
          </h3>
          <div className="space-y-2">
            {documents.map((doc) => (
              <div key={doc.id} className="flex items-center gap-4 bg-[#111111] border border-zinc-800/60 rounded-xl px-4 py-3 hover:border-zinc-700 transition-all">
                <div className="w-8 h-8 bg-zinc-900 rounded-lg flex items-center justify-center border border-zinc-800 shrink-0">
                  <FileText size={15} className="text-zinc-400" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-zinc-200 truncate">{doc.filename}</p>
                  <div className="flex items-center gap-2 mt-0.5">
                    <FileTypeIcon type={doc.file_type} />
                    {doc.chunk_count > 0 && (
                      <span className="text-[10px] text-zinc-600">{doc.chunk_count} chunks</span>
                    )}
                    {doc.error && doc.status !== "failed" && (
                      <span className="text-[10px] text-yellow-500 truncate">{doc.error}</span>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <StatusBadge status={doc.status} />
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      if (confirm("Delete this document?")) onDeleteDocument(doc.id);
                    }}
                    className="p-1 text-zinc-600 hover:text-red-400 transition-colors"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Search View ──────────────────────────────────────────────────────────────

function SearchView({ vault }: { vault: Vault }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    setLoading(true); setError(null);
    try {
      const data = await api.search(query);
      setResults(data.results);
      setSearched(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Search failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-white">Semantic Search</h1>
        <p className="text-zinc-500 text-sm mt-1">
          Query <span className="text-indigo-400 font-medium">{vault.name}</span> · {vault.chunk_count} chunks indexed
        </p>
      </div>

      <form onSubmit={handleSearch} className="relative group">
        <div className="absolute inset-0 bg-indigo-500/10 blur-xl rounded-2xl opacity-0 group-focus-within:opacity-100 transition-opacity duration-500" />
        <div className="relative flex items-center bg-zinc-900 border border-zinc-800 rounded-2xl p-2 focus-within:border-indigo-500/50 transition-all">
          <Search className="ml-3 text-zinc-500 shrink-0" size={18} />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search for concepts, entities, facts…"
            className="flex-1 bg-transparent outline-none px-4 py-2.5 text-sm text-white placeholder:text-zinc-600"
          />
          <button
            type="submit"
            disabled={loading || !query.trim()}
            className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white px-5 py-2 rounded-xl text-sm font-semibold transition-all flex items-center gap-2"
          >
            {loading ? <Loader2 size={14} className="animate-spin" /> : <Zap size={14} />}
            Query
          </button>
        </div>
      </form>

      {error && (
        <div className="flex items-center gap-2 text-red-400 text-sm bg-red-400/10 p-4 rounded-xl border border-red-400/20">
          <AlertCircle size={15} /> {error}
        </div>
      )}

      {searched && results.length === 0 && !loading && (
        <div className="text-center py-16 text-zinc-600">
          <Search size={36} className="mx-auto mb-3 opacity-30" />
          <p className="text-sm">No results found. Try a different query.</p>
        </div>
      )}

      <div className="space-y-4">
        {results.map((res) => (
          <div key={res.chunk_id} className="bg-[#111111] border border-zinc-800/60 rounded-2xl p-5 hover:border-zinc-700 transition-all">
            <div className="flex items-start justify-between gap-4 mb-3">
              <div className="flex items-center gap-2 min-w-0">
                <div className="w-7 h-7 bg-zinc-900 rounded-lg flex items-center justify-center border border-zinc-800 shrink-0">
                  <FileText size={13} className="text-indigo-400" />
                </div>
                <div className="min-w-0">
                  <span className="text-xs font-semibold text-zinc-300 truncate block">{res.filename}</span>
                  {res.section && (
                    <span className="text-[10px] text-zinc-600 truncate block">{res.section}</span>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {res.language && (
                  <span className="text-[10px] font-semibold text-zinc-500 uppercase bg-zinc-900 px-2 py-0.5 rounded">
                    {res.language}
                  </span>
                )}
                <div className={cn(
                  "px-2.5 py-1 rounded-lg text-[11px] font-bold",
                  res.score > 0.7 ? "bg-emerald-500/15 text-emerald-400" :
                  res.score > 0.5 ? "bg-blue-500/15 text-blue-400" :
                  "bg-zinc-800 text-zinc-400"
                )}>
                  {(res.score * 100).toFixed(0)}%
                </div>
              </div>
            </div>
            <p className="text-zinc-300 text-sm leading-relaxed line-clamp-5">{res.content}</p>
            {res.tags.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-3">
                {res.tags.map((tag) => (
                  <span key={tag} className="text-[10px] font-medium text-indigo-400/70 bg-indigo-500/10 px-2 py-0.5 rounded-md border border-indigo-500/20">
                    {tag}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Vault Stats View ─────────────────────────────────────────────────────────

function VaultView({ vault, documents }: { vault: Vault; documents: Document[] }) {
  const indexed = documents.filter((d) => d.status === "indexed").length;
  const processing = documents.filter((d) => d.status === "processing" || d.status === "pending").length;
  const failed = documents.filter((d) => d.status === "failed").length;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">{vault.name}</h1>
        <p className="text-zinc-500 text-sm mt-1">Vault overview & statistics</p>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: "Documents", value: vault.document_count, color: "text-white" },
          { label: "Indexed", value: indexed, color: "text-emerald-400" },
          { label: "Processing", value: processing, color: "text-blue-400" },
          { label: "Chunks", value: vault.chunk_count, color: "text-indigo-400" },
        ].map(({ label, value, color }) => (
          <div key={label} className="bg-[#111111] border border-zinc-800 rounded-2xl p-5">
            <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest mb-2">{label}</p>
            <p className={cn("text-3xl font-bold", color)}>{value}</p>
          </div>
        ))}
      </div>
      {failed > 0 && (
        <div className="bg-red-500/5 border border-red-500/20 rounded-xl p-4">
          <div className="flex items-center gap-2 text-red-400 text-sm font-semibold mb-2">
            <XCircle size={15} /> {failed} failed document{failed > 1 ? "s" : ""}
          </div>
          {documents.filter((d) => d.status === "failed").map((d) => (
            <div key={d.id} className="text-xs text-zinc-500 ml-5">
              {d.filename}: <span className="text-red-400/70">{d.error}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── App root ─────────────────────────────────────────────────────────────────

export default function App() {
  const [vaults, setVaults] = useState<Vault[]>([]);
  const [activeVault, setActiveVault] = useState<Vault | null>(null);
  const [isUnlocked, setIsUnlocked] = useState(false);
  const [view, setView] = useState<View>("upload");
  const [documents, setDocuments] = useState<Document[]>([]);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showUnlockModal, setShowUnlockModal] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── Load vaults ─────────────────────────────────────────────────────────
  const refreshVaults = useCallback(async () => {
    try {
      const data = await api.getVaults();
      setVaults(data);
      // Sync active vault stats
      if (activeVault) {
        const updated = data.find((v) => v.id === activeVault.id);
        if (updated) setActiveVault(updated);
      }
    } catch {}
  }, [activeVault]);

  useEffect(() => { refreshVaults(); }, []);

  // ── Load documents + polling ─────────────────────────────────────────────
  const refreshDocuments = useCallback(async () => {
    if (!activeVault || !isUnlocked) return;
    try {
      const docs = await api.getDocuments(activeVault.id);
      setDocuments(docs);
      // Refresh vault stats too
      await refreshVaults();
      // Stop polling if no active jobs
      const hasActive = docs.some((d) => d.status === "pending" || d.status === "processing");
      if (!hasActive && pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    } catch {}
  }, [activeVault, isUnlocked]);

  useEffect(() => {
    if (!isUnlocked || !activeVault) return;
    refreshDocuments();
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [isUnlocked, activeVault?.id]);

  function startPolling() {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(refreshDocuments, 2500);
  }

  // ── Handlers ─────────────────────────────────────────────────────────────
  async function handleVaultSelect(vault: Vault) {
    if (isUnlocked && vault.id === activeVault?.id) return;
    if (isUnlocked && activeVault) {
      // Lock previous vault
      try { await api.lockVault(activeVault.id); } catch {}
    }
    setIsUnlocked(false);
    setDocuments([]);
    setActiveVault(vault);
    setShowUnlockModal(true);
  }

  function handleUnlocked() {
    setIsUnlocked(true);
    setShowUnlockModal(false);
    setView("upload");
    refreshDocuments();
  }

  async function handleLock() {
    if (!activeVault) return;
    try { await api.lockVault(activeVault.id); } catch {}
    setIsUnlocked(false);
    setDocuments([]);
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  }

  function handleFilesAdded() {
    refreshDocuments();
    startPolling();
  }

  async function handleDocumentDelete(docId: string) {
    try {
      await api.deleteDocument(docId);
      refreshDocuments();
    } catch (err) {
      alert("Failed to delete document");
    }
  }

  async function handleVaultDelete(vaultId: string) {
    if (!confirm("Are you sure? This will delete all documents and the index for this vault forever.")) return;
    try {
      await api.deleteVault(vaultId);
      if (activeVault?.id === vaultId) {
        setIsUnlocked(false);
        setActiveVault(null);
      }
      refreshVaults();
    } catch (err) {
      alert("Failed to delete vault");
    }
  }

  const navItems: { id: View; label: string; icon: typeof Search }[] = [
    { id: "search", label: "Search", icon: Search },
    { id: "upload", label: "Ingest", icon: Upload },
    { id: "vault", label: "Overview", icon: Database },
  ];

  return (
    <div className="flex h-screen w-screen bg-[#0a0a0a] text-zinc-100 overflow-hidden font-sans">

      {/* ── Modals ── */}
      {showCreateModal && (
        <VaultCreateModal
          onClose={() => setShowCreateModal(false)}
          onCreated={(v) => {
            setShowCreateModal(false);
            refreshVaults();
          }}
        />
      )}
      {showUnlockModal && activeVault && (
        <UnlockModal
          vault={activeVault}
          onClose={() => setShowUnlockModal(false)}
          onUnlocked={handleUnlocked}
        />
      )}

      {/* ── Sidebar ── */}
      <aside className="w-60 bg-[#0e0e0e] border-r border-zinc-800/70 flex flex-col shrink-0">
        {/* Logo */}
        <div className="px-5 py-5 flex items-center gap-2.5">
          <div className="w-8 h-8 bg-indigo-600 rounded-lg flex items-center justify-center shadow-lg shadow-indigo-600/20">
            <Cpu size={15} className="text-white" />
          </div>
          <div>
            <span className="font-bold text-sm leading-none text-white tracking-tight">Ragna</span>
            <span className="block text-[9px] text-zinc-500 font-medium uppercase tracking-widest mt-0.5">Memory Compiler</span>
          </div>
        </div>

        {/* Nav */}
        {isUnlocked && (
          <nav className="px-3 space-y-0.5 mb-4">
            {navItems.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                onClick={() => setView(id)}
                className={cn(
                  "w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all",
                  view === id
                    ? "bg-zinc-800 text-white font-semibold"
                    : "text-zinc-500 hover:text-zinc-200 hover:bg-zinc-900"
                )}
              >
                <Icon size={15} />
                {label}
              </button>
            ))}
          </nav>
        )}

        {/* Vaults */}
        <div className="flex-1 px-3 overflow-y-auto">
          <div className="flex items-center justify-between px-2 mb-2">
            <span className="text-[10px] font-bold text-zinc-600 uppercase tracking-widest">Vaults</span>
          </div>
          <div className="space-y-0.5">
            {vaults.map((v) => {
              const active = activeVault?.id === v.id;
              const unlocked = active && isUnlocked;
              return (
                <button
                  key={v.id}
                  onClick={() => handleVaultSelect(v)}
                  className={cn(
                    "w-full flex items-center justify-between px-3 py-2.5 rounded-lg text-sm transition-all group",
                    active ? "bg-zinc-800 text-white" : "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-900"
                  )}
                >
                  <div className="flex items-center gap-2.5 min-w-0">
                    <Database size={13} className={unlocked ? "text-emerald-400" : ""} />
                    <span className="truncate font-medium">{v.name}</span>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {active ? (
                      unlocked ? <Unlock size={11} className="text-emerald-400" /> : <Lock size={11} className="text-zinc-600" />
                    ) : (
                      <Trash2
                        size={11}
                        className="text-zinc-700 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-all"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleVaultDelete(v.id);
                        }}
                      />
                    )}
                  </div>
                </button>
              );
            })}
          </div>
          <button
            onClick={() => setShowCreateModal(true)}
            className="w-full flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-xs text-zinc-600 hover:text-indigo-400 hover:bg-zinc-900 transition-all mt-2"
          >
            <Plus size={13} /> New Vault
          </button>
        </div>

        {/* Status bar */}
        <div className="p-3 border-t border-zinc-800/70">
          <div className="flex items-center justify-between px-2 py-1.5">
            <div className="flex items-center gap-2">
              <div className={cn("w-1.5 h-1.5 rounded-full", isUnlocked ? "bg-emerald-400 shadow-sm shadow-emerald-400/50" : "bg-zinc-600")} />
              <span className="text-[10px] font-semibold text-zinc-500 uppercase tracking-widest">
                {isUnlocked ? `${activeVault?.name}` : "Locked"}
              </span>
            </div>
            {isUnlocked && (
              <button
                onClick={handleLock}
                className="text-zinc-600 hover:text-orange-400 transition-colors"
                title="Lock vault"
              >
                <Lock size={12} />
              </button>
            )}
          </div>
        </div>
      </aside>

      {/* ── Main ── */}
      <main className="flex-1 flex flex-col min-w-0 bg-[#0a0a0a] overflow-hidden">
        <div className="flex-1 overflow-y-auto">
          <div className="max-w-4xl mx-auto p-8">
            {!activeVault ? (
              <div className="flex flex-col items-center justify-center mt-24 text-zinc-700 select-none">
                <Database size={52} className="mb-4 opacity-20" />
                <p className="text-sm font-medium">Select a vault from the sidebar</p>
                <p className="text-xs mt-1 text-zinc-800">or create a new one to get started</p>
              </div>
            ) : !isUnlocked ? (
              <div className="flex flex-col items-center justify-center mt-24 text-zinc-700 select-none">
                <Lock size={48} className="mb-4 opacity-20" />
                <p className="text-sm font-medium">Vault is locked</p>
                <button
                  onClick={() => setShowUnlockModal(true)}
                  className="mt-4 text-xs font-semibold text-indigo-400 hover:text-indigo-300 flex items-center gap-1 transition-colors"
                >
                  <Unlock size={12} /> Unlock vault
                </button>
              </div>
            ) : (
              <>
                {view === "search" && <SearchView vault={activeVault} />}
                {view === "upload" && (
                  <UploadView
                    vault={activeVault}
                    documents={documents}
                    onFilesAdded={handleFilesAdded}
                    onDeleteDocument={handleDocumentDelete}
                  />
                )}
                {view === "vault" && (
                  <VaultView vault={activeVault} documents={documents} />
                )}
              </>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
