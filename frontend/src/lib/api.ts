const DEFAULT_BACKEND = "http://localhost:8000";

export interface Vault {
  id: string;
  name: string;
  created_at: string;
  document_count: number;
  chunk_count: number;
}

export interface Document {
  id: string;
  vault_id: string;
  filename: string;
  file_type: string;
  chunk_count: number;
  status: "pending" | "processing" | "indexed" | "failed";
  error?: string | null;
  summary?: string | null;
  created_at: string;
}

export interface Entity {
  id: string;
  document_id: string;
  text: string;
  entity_type: string;
  subtype?: string | null;
  frequency: number;
}

export interface SearchResult {
  chunk_id: string;
  document_id: string;
  filename: string;
  content: string;
  score: number;
  relevance_label: "Strong" | "Good" | "Weak" | "Marginal";
  section?: string;
  tags: string[];
  language?: string;
}

// ── Watcher ──────────────────────────────────────────────────────────────────

export interface Watcher {
  id: string;
  vault_id: string;
  folder_path: string;
  recursive: boolean;
  is_active: boolean;
  is_running: boolean;
  created_at: string;
}

// ── Settings ─────────────────────────────────────────────────────────────────

export interface AppSettings {
  searchThreshold: number;
  searchTopK: number;
  backendUrl: string;
  summaryMode: "extractive" | "ollama" | "disabled";
  ollamaUrl: string;
  ollamaModel: string;
  ocrEnabled: boolean;
}

export const DEFAULT_SETTINGS: AppSettings = {
  searchThreshold: 0.3,
  searchTopK: 10,
  backendUrl: DEFAULT_BACKEND,
  summaryMode: "extractive",
  ollamaUrl: "http://localhost:11434",
  ollamaModel: "llama3.2:3b",
  ocrEnabled: true,
};

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

class ApiClient {
  private token: string | null = null;
  private _vaultId: string | null = null;
  private _baseUrl: string = DEFAULT_BACKEND;

  get sessionToken() { return this.token; }
  get activeVaultId() { return this._vaultId; }

  setBaseUrl(url: string) { this._baseUrl = url.replace(/\/$/, ""); }
  setSession(token: string, vaultId: string) { this.token = token; this._vaultId = vaultId; }
  clearSession() { this.token = null; this._vaultId = null; }
  isUnlocked() { return this.token !== null; }

  private async req<T>(path: string, opts: RequestInit = {}): Promise<T> {
    const headers: Record<string, string> = {
      ...(opts.body && !(opts.body instanceof FormData)
        ? { "Content-Type": "application/json" } : {}),
      ...(this.token ? { "X-Session-Token": this.token } : {}),
    };
    const res = await fetch(`${this._baseUrl}${path}`, { ...opts, headers });
    if (!res.ok) {
      let msg = `HTTP ${res.status}`;
      try { msg = (await res.json()).detail ?? msg; } catch {}
      throw new ApiError(res.status, msg);
    }
    if (res.status === 204) return undefined as T;
    return res.json() as Promise<T>;
  }

  // ── Health ──────────────────────────────────────────────────────────────
  checkHealth = () => this.req<{ status: string; version: string }>("/health");

  // ── Vaults ──────────────────────────────────────────────────────────────
  getVaults = () => this.req<Vault[]>("/vaults");
  createVault = (name: string, password: string) =>
    this.req<Vault>("/vaults", { method: "POST", body: JSON.stringify({ name, password }) });

  unlockVault = async (vaultId: string, password: string) => {
    const data = await this.req<{ session_token: string; vault_id: string; vault_name: string }>(
      `/vaults/${vaultId}/unlock`, { method: "POST", body: JSON.stringify({ password }) });
    this.setSession(data.session_token, vaultId);
    return data;
  };

  lockVault = async (vaultId: string) => {
    await this.req<void>(`/vaults/${vaultId}/lock`, { method: "POST" });
    this.clearSession();
  };

  renameVault = (vaultId: string, name: string) =>
    this.req<Vault>(`/vaults/${vaultId}`, { method: "PATCH", body: JSON.stringify({ name }) });
  deleteVault = (vaultId: string) =>
    this.req<void>(`/vaults/${vaultId}`, { method: "DELETE" });

  // ── Documents ────────────────────────────────────────────────────────────
  getDocuments = (vaultId: string) => this.req<Document[]>(`/vaults/${vaultId}/documents`);
  getDocument  = (docId: string)   => this.req<Document>(`/documents/${docId}`);
  deleteDocument = (docId: string) => this.req<void>(`/documents/${docId}`, { method: "DELETE" });
  getDocumentEntities = (docId: string) => this.req<Entity[]>(`/documents/${docId}/entities`);

  // ── Ingest ───────────────────────────────────────────────────────────────
  ingestFile = (file: File, summaryMode = "extractive",
    ollamaUrl = "http://localhost:11434", ollamaModel = "llama3.2:3b") => {
    const form = new FormData();
    form.append("file", file);
    form.append("summary_mode", summaryMode);
    form.append("ollama_url", ollamaUrl);
    form.append("ollama_model", ollamaModel);
    return this.req<Document>("/ingest", { method: "POST", body: form });
  };

  // ── Entities ─────────────────────────────────────────────────────────────
  getVaultEntities = (vaultId: string, entityType?: string) => {
    const params = entityType ? `?entity_type=${entityType}` : "";
    return this.req<Entity[]>(`/vaults/${vaultId}/entities${params}`);
  };

  // ── Search ───────────────────────────────────────────────────────────────
  search = (query: string, topK = 10, threshold = 0.3, rerank = false) =>
    this.req<{ query: string; results: SearchResult[]; total: number; reranked: boolean }>(
      "/search", { method: "POST",
        body: JSON.stringify({ query, top_k: topK, threshold, rerank }) });

  // ── Watch Mode ───────────────────────────────────────────────────────────
  getWatchers = (vaultId: string) =>
    this.req<Watcher[]>(`/vaults/${vaultId}/watchers`);

  addWatcher = (vaultId: string, folderPath: string, recursive = false) =>
    this.req<Watcher>(`/vaults/${vaultId}/watchers`, {
      method: "POST",
      body: JSON.stringify({ folder_path: folderPath, recursive }),
    });

  removeWatcher = (watcherId: string) =>
    this.req<void>(`/watchers/${watcherId}`, { method: "DELETE" });
}

export const api = new ApiClient();
