import { useState, useEffect } from "react";
import { 
  Search, 
  Upload, 
  Database, 
  Settings, 
  Lock, 
  Unlock, 
  FileText, 
  Plus, 
  ChevronRight,
  Activity,
  ShieldCheck,
  Loader2,
  AlertCircle
} from "lucide-react";
import { cn } from "./lib/utils";
import { api, Vault, SearchResult } from "./lib/api";
import "./App.css";

type View = "search" | "upload" | "vaults" | "settings";

function App() {
  const [activeView, setActiveView] = useState<View>("search");
  const [isLocked, setIsLocked] = useState(true);
  const [password, setPassword] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [vaults, setVaults] = useState<Vault[]>([]);
  const [activeVault, setActiveVault] = useState<Vault | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load vaults on start
  useEffect(() => {
    refreshVaults();
  }, []);

  const refreshVaults = async () => {
    try {
      const data = await api.getVaults();
      setVaults(data);
    } catch (err) {
      console.error(err);
    }
  };

  const handleUnlock = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeVault) return;
    setIsLoading(true);
    setError(null);
    try {
      await api.unlockVault(activeVault.id, password);
      setIsLocked(false);
      setPassword("");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isLocked) return;
    setIsLoading(true);
    try {
      const data = await api.search(searchQuery);
      setResults(data);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || isLocked) return;
    setIsLoading(true);
    try {
      await api.ingestFile(file);
      await refreshVaults();
      alert("File indexed successfully!");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex h-screen w-screen bg-[#0a0a0a] text-zinc-100 overflow-hidden font-sans">
      
      {/* --- Sidebar --- */}
      <aside className="w-64 bg-[#111111] border-r border-zinc-800 flex flex-col">
        <div className="p-6 flex items-center gap-2 mb-4">
          <div className="w-8 h-8 bg-indigo-600 rounded-lg flex items-center justify-center shadow-lg shadow-indigo-500/20">
            <Activity size={18} className="text-white" />
          </div>
          <span className="font-bold text-lg tracking-tight">AKC Memory</span>
        </div>

        <nav className="flex-1 px-3 space-y-1">
          <button 
            onClick={() => setActiveView("search")}
            disabled={isLocked}
            className={cn(
              "w-full flex items-center gap-3 px-3 py-2 rounded-md transition-all disabled:opacity-30",
              activeView === "search" ? "bg-zinc-800 text-white shadow-sm" : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900"
            )}
          >
            <Search size={18} />
            <span className="text-sm font-medium">Search</span>
          </button>
          
          <button 
            onClick={() => setActiveView("upload")}
            disabled={isLocked}
            className={cn(
              "w-full flex items-center gap-3 px-3 py-2 rounded-md transition-all disabled:opacity-30",
              activeView === "upload" ? "bg-zinc-800 text-white shadow-sm" : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900"
            )}
          >
            <Upload size={18} />
            <span className="text-sm font-medium">Ingest</span>
          </button>

          <div className="pt-6 pb-2 px-3">
            <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Vaults</span>
          </div>

          {vaults.map(v => (
            <button 
              key={v.id}
              onClick={() => {
                setActiveVault(v);
                setActiveView("vaults");
              }}
              className={cn(
                "w-full flex items-center justify-between px-3 py-2 rounded-md transition-all text-sm group",
                activeVault?.id === v.id && activeView === "vaults" ? "bg-zinc-800 text-white" : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900"
              )}
            >
              <div className="flex items-center gap-3">
                <Database size={16} />
                <span>{v.name}</span>
              </div>
              {isLocked ? (
                <Lock size={12} className="text-orange-500/50" />
              ) : (
                <Unlock size={12} className="text-emerald-500/50" />
              )}
            </button>
          ))}
          
          <button 
            onClick={async () => {
              const name = prompt("Enter vault name:");
              const pass = prompt("Enter password:");
              if (name && pass) {
                await api.createVault(name, pass);
                refreshVaults();
              }
            }}
            className="w-full flex items-center gap-3 px-3 py-2 rounded-md text-zinc-500 hover:text-indigo-400 hover:bg-zinc-900 transition-all text-sm mt-2"
          >
            <Plus size={16} />
            <span>New Vault</span>
          </button>
        </nav>

        <div className="p-4 border-t border-zinc-800">
          <button 
            onClick={() => setActiveView("settings")}
            className={cn(
              "w-full flex items-center gap-3 px-3 py-2 rounded-md transition-all text-sm",
              activeView === "settings" ? "bg-zinc-800 text-white" : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900"
            )}
          >
            <Settings size={18} />
            <span>Settings</span>
          </button>
          <div className="mt-4 px-3 py-2 bg-zinc-900/50 rounded-lg flex items-center justify-between border border-zinc-800/50">
            <div className="flex items-center gap-2">
              <ShieldCheck size={14} className={isLocked ? "text-orange-500" : "text-emerald-500"} />
              <span className="text-[10px] text-zinc-400 font-medium uppercase">{isLocked ? "Locked" : "Decrypted"}</span>
            </div>
          </div>
        </div>
      </aside>

      {/* --- Main Content --- */}
      <main className="flex-1 flex flex-col min-w-0 bg-[#0a0a0a]">
        
        <header className="h-16 border-b border-zinc-800/50 flex items-center px-8 justify-between bg-[#0a0a0a]/80 backdrop-blur-md sticky top-0 z-10">
          <div className="flex items-center gap-4">
            <h2 className="text-sm font-semibold text-zinc-400 capitalize">{activeView}</h2>
          </div>
          {isLoading && <Loader2 size={16} className="animate-spin text-indigo-500" />}
        </header>

        <div className="flex-1 overflow-y-auto p-8 max-w-5xl mx-auto w-full">
          
          {isLocked && activeVault && activeView === "vaults" ? (
            <div className="max-w-md mx-auto mt-20 p-8 bg-[#111111] border border-zinc-800 rounded-3xl space-y-6">
              <div className="text-center space-y-2">
                <div className="w-12 h-12 bg-orange-500/10 rounded-2xl flex items-center justify-center mx-auto mb-4">
                  <Lock className="text-orange-500" size={24} />
                </div>
                <h2 className="text-2xl font-bold text-white">Unlock Vault</h2>
                <p className="text-zinc-500">Enter password for "{activeVault.name}"</p>
              </div>

              <form onSubmit={handleUnlock} className="space-y-4">
                <input 
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Encryption key..."
                  className="w-full bg-zinc-900 border border-zinc-800 rounded-xl px-4 py-3 outline-none focus:border-indigo-500/50 transition-all"
                  autoFocus
                />
                {error && (
                  <div className="flex items-center gap-2 text-red-400 text-xs bg-red-400/10 p-3 rounded-lg border border-red-400/20">
                    <AlertCircle size={14} />
                    <span>{error}</span>
                  </div>
                )}
                <button 
                  type="submit"
                  disabled={isLoading}
                  className="w-full bg-indigo-600 hover:bg-indigo-500 text-white font-bold py-3 rounded-xl transition-all shadow-lg shadow-indigo-600/20 flex items-center justify-center gap-2"
                >
                  {isLoading ? <Loader2 size={18} className="animate-spin" /> : "Decrypt & Access"}
                </button>
              </form>
            </div>
          ) : !isLocked ? (
            <>
              {activeView === "search" && (
                <div className="space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-500">
                  <div className="text-center space-y-2 mb-12">
                    <h1 className="text-4xl font-bold tracking-tight text-white">Semantic Search</h1>
                    <p className="text-zinc-500 text-lg">Query your encrypted knowledge in <b>{activeVault?.name}</b></p>
                  </div>

                  <form onSubmit={handleSearch} className="relative group max-w-3xl mx-auto">
                    <div className="absolute inset-0 bg-indigo-500/20 blur-xl rounded-2xl opacity-0 group-focus-within:opacity-100 transition-opacity duration-700" />
                    <div className="relative flex items-center bg-zinc-900 border border-zinc-800 rounded-2xl p-2 shadow-2xl focus-within:border-indigo-500/50 transition-all duration-300">
                      <Search className="ml-4 text-zinc-500" size={20} />
                      <input 
                        type="text"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        placeholder="Search for concepts, entities, or facts..."
                        className="flex-1 bg-transparent border-none outline-none px-4 py-3 text-lg text-white placeholder:text-zinc-600"
                      />
                      <button 
                        type="submit"
                        className="bg-indigo-600 hover:bg-indigo-500 text-white px-6 py-3 rounded-xl font-semibold transition-all shadow-lg shadow-indigo-600/20"
                      >
                        Query
                      </button>
                    </div>
                  </form>

                  <div className="grid gap-6 mt-12">
                    {results.length === 0 && !isLoading && searchQuery && (
                      <p className="text-center text-zinc-600">No results found for your query.</p>
                    )}
                    {results.map(res => (
                      <div key={res.chunk_id} className="bg-[#111111] border border-zinc-800/50 rounded-2xl p-6 hover:border-zinc-700 transition-all group">
                        <div className="flex items-center justify-between mb-4">
                          <div className="flex items-center gap-2">
                            <div className="p-1.5 bg-zinc-900 rounded-md">
                              <FileText size={14} className="text-indigo-400" />
                            </div>
                            <span className="text-xs font-bold text-zinc-400 uppercase tracking-tight">{res.filename}</span>
                          </div>
                          <div className="px-2 py-1 bg-indigo-500/10 text-indigo-400 rounded text-[10px] font-bold">
                            SCORE: {(res.score * 100).toFixed(0)}%
                          </div>
                        </div>
                        <p className="text-zinc-300 leading-relaxed">
                          {res.content}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {activeView === "upload" && (
                <div className="max-w-2xl mx-auto space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-500">
                  <div className="text-center space-y-2 mb-8">
                    <h1 className="text-3xl font-bold tracking-tight text-white">Ingest Knowledge</h1>
                    <p className="text-zinc-500">Add documents to <b>{activeVault?.name}</b></p>
                  </div>

                  <label className="border-2 border-dashed border-zinc-800 rounded-3xl p-16 flex flex-col items-center justify-center space-y-4 bg-zinc-900/20 hover:bg-zinc-900/40 hover:border-indigo-500/40 transition-all cursor-pointer group">
                    <input type="file" className="hidden" onChange={handleFileUpload} disabled={isLoading} />
                    <div className="w-16 h-16 bg-zinc-900 rounded-2xl flex items-center justify-center border border-zinc-800 group-hover:scale-110 group-hover:border-indigo-500/50 transition-all duration-300">
                      <Upload className="text-zinc-500 group-hover:text-indigo-400" size={32} />
                    </div>
                    <div className="text-center">
                      <p className="text-lg font-medium text-zinc-200">Click to browse or drop files</p>
                      <p className="text-sm text-zinc-500 mt-1">PDF, DOCX, Images, Markdown, etc.</p>
                    </div>
                  </label>
                </div>
              )}

              {activeView === "vaults" && (
                <div className="animate-in fade-in slide-in-from-bottom-2 duration-500">
                  <div className="flex items-center justify-between mb-8">
                    <div>
                      <h1 className="text-3xl font-bold text-white">{activeVault?.name}</h1>
                      <p className="text-zinc-500 mt-1">Manage and explore documents in this vault</p>
                    </div>
                    <button 
                      onClick={() => setIsLocked(true)}
                      className="bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 px-4 py-2 rounded-lg flex items-center gap-2 text-sm font-medium transition-all"
                    >
                      <Lock size={16} className="text-orange-400" />
                      Lock Vault
                    </button>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                    <div className="bg-[#111111] border border-zinc-800 p-6 rounded-2xl space-y-2">
                      <span className="text-[10px] font-bold text-zinc-500 uppercase">Documents</span>
                      <p className="text-3xl font-bold text-white">{activeVault?.document_count || 0}</p>
                    </div>
                    <div className="bg-[#111111] border border-zinc-800 p-6 rounded-2xl space-y-2">
                      <span className="text-[10px] font-bold text-zinc-500 uppercase">Semantic Chunks</span>
                      <p className="text-3xl font-bold text-white">{activeVault?.chunk_count || 0}</p>
                    </div>
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="flex flex-col items-center justify-center mt-20 text-zinc-600">
              <Database size={48} className="mb-4 opacity-20" />
              <p>Select and unlock a vault from the sidebar to start.</p>
            </div>
          )}

        </div>
      </main>
    </div>
  );
}

export default App;
