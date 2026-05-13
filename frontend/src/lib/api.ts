const API_BASE_URL = "http://localhost:8000";

export interface Vault {
  id: string;
  name: string;
  created_at: string;
  document_count: number;
  chunk_count: number;
}

export interface SearchResult {
  chunk_id: string;
  document_id: string;
  filename: string;
  content: string;
  score: number;
  section?: string;
}

class ApiClient {
  private token: string | null = null;

  setToken(token: string) {
    this.token = token;
  }

  async getVaults(): Promise<Vault[]> {
    const res = await fetch(`${API_BASE_URL}/vaults`);
    if (!res.ok) throw new Error("Failed to fetch vaults");
    return res.json();
  }

  async createVault(name: string, password: string): Promise<Vault> {
    const res = await fetch(`${API_BASE_URL}/vaults`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, password }),
    });
    if (!res.ok) throw new Error("Failed to create vault");
    return res.json();
  }

  async unlockVault(vaultId: string, password: string) {
    const res = await fetch(`${API_BASE_URL}/vaults/${vaultId}/unlock`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    });
    if (!res.ok) throw new Error("Invalid password or vault not found");
    const data = await res.json();
    this.token = data.session_token;
    return data;
  }

  async search(query: string, topK: number = 10): Promise<SearchResult[]> {
    if (!this.token) throw new Error("Vault is locked");
    const res = await fetch(`${API_BASE_URL}/search?token=${this.token}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, top_k: topK }),
    });
    if (!res.ok) throw new Error("Search failed");
    const data = await res.json();
    return data.results;
  }

  async ingestFile(file: File): Promise<any> {
    if (!this.token) throw new Error("Vault is locked");
    const formData = new FormData();
    formData.append("file", file);

    const res = await fetch(`${API_BASE_URL}/ingest?token=${this.token}`, {
      method: "POST",
      body: formData,
    });
    if (!res.ok) throw new Error("Upload failed");
    return res.json();
  }
}

export const api = new ApiClient();
