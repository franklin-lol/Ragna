const API_BASE = "http://localhost:8000";

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
  created_at: string;
}

export interface SearchResult {
  chunk_id: string;
  document_id: string;
  filename: string;
  content: string;
  score: number;
  section?: string;
  tags: string[];
  language?: string;
}

class ApiError extends Error {
  constructor(
    public status: number,
    message: string
  ) {
    super(message);
  }
}

async function req<T>(
  path: string,
  opts: RequestInit = {},
  token?: string | null
): Promise<T> {
  const headers: Record<string, string> = {
    ...(opts.body && !(opts.body instanceof FormData)
      ? { "Content-Type": "application/json" }
      : {}),
    ...(token ? { "X-Session-Token": token } : {}),
  };

  const res = await fetch(`${API_BASE}${path}`, { ...opts, headers });

  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try {
      const j = await res.json();
      msg = j.detail ?? msg;
    } catch {}
    throw new ApiError(res.status, msg);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

class ApiClient {
  private token: string | null = null;
  private _vaultId: string | null = null;

  get sessionToken() { return this.token; }
  get activeVaultId() { return this._vaultId; }

  setSession(token: string, vaultId: string) {
    this.token = token;
    this._vaultId = vaultId;
  }

  clearSession() {
    this.token = null;
    this._vaultId = null;
  }

  isUnlocked() {
    return this.token !== null;
  }

  // ── Vaults ──────────────────────────────────────────────────────────────

  getVaults = () => req<Vault[]>("/vaults");

  createVault = (name: string, password: string) =>
    req<Vault>("/vaults", {
      method: "POST",
      body: JSON.stringify({ name, password }),
    });

  unlockVault = async (vaultId: string, password: string) => {
    const data = await req<{ session_token: string; vault_id: string; vault_name: string }>(
      `/vaults/${vaultId}/unlock`,
      { method: "POST", body: JSON.stringify({ password }) }
    );
    this.setSession(data.session_token, vaultId);
    return data;
  };

  lockVault = async (vaultId: string) => {
    await req<void>(`/vaults/${vaultId}/lock`, { method: "POST" }, this.token);
    this.clearSession();
  };

  deleteVault = (vaultId: string) =>
    req<void>(`/vaults/${vaultId}`, { method: "DELETE" });

  // ── Documents ────────────────────────────────────────────────────────────

  getDocuments = (vaultId: string) =>
    req<Document[]>(`/vaults/${vaultId}/documents`, {}, this.token);

  getDocument = (docId: string) =>
    req<Document>(`/documents/${docId}`, {}, this.token);

  deleteDocument = (docId: string) =>
    req<void>(`/documents/${docId}`, { method: "DELETE" }, this.token);

  // ── Ingest ───────────────────────────────────────────────────────────────

  ingestFile = (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return req<Document>("/ingest", { method: "POST", body: form }, this.token);
  };

  ingestFiles = async (files: File[]): Promise<Document[]> => {
    return Promise.all(files.map((f) => this.ingestFile(f)));
  };

  // ── Search ───────────────────────────────────────────────────────────────

  search = (query: string, topK = 10, threshold = 0.3) =>
    req<{ query: string; results: SearchResult[]; total: number }>(
      "/search",
      {
        method: "POST",
        body: JSON.stringify({ query, top_k: topK, threshold }),
      },
      this.token
    );
}

export const api = new ApiClient();
export { ApiError };
