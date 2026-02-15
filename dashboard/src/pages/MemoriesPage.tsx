import { useState } from "react";
import { api } from "../api/client";
import type { BrowseResult, MemoryDetail } from "../api/types";
import Badge from "../components/Badge";
import EmptyState from "../components/EmptyState";

export default function MemoriesPage() {
  const [query, setQuery] = useState("");
  const [domain, setDomain] = useState("");
  const [memType, setMemType] = useState("");
  const [results, setResults] = useState<BrowseResult[]>([]);
  const [expanded, setExpanded] = useState<Record<string, MemoryDetail>>({});
  const [loading, setLoading] = useState(false);

  async function search() {
    if (!query.trim()) return;
    setLoading(true);
    try {
      const body: Record<string, unknown> = { query, limit: 20 };
      if (domain) body.domains = [domain];
      if (memType) body.memory_types = [memType];
      const res = await api<{ results: BrowseResult[] }>(
        "/search/browse",
        "POST",
        body,
      );
      setResults(res.results);
    } catch {
      setResults([]);
    } finally {
      setLoading(false);
    }
  }

  async function toggleExpand(id: string) {
    if (expanded[id]) {
      const next = { ...expanded };
      delete next[id];
      setExpanded(next);
      return;
    }
    try {
      const detail = await api<MemoryDetail>(`/memory/${id}`);
      setExpanded({ ...expanded, [id]: detail });
    } catch {}
  }

  async function deleteMemory(id: string) {
    if (!confirm("Delete this memory?")) return;
    try {
      await api(`/memory/${id}`, "DELETE");
      setResults(results.filter((r) => r.id !== id));
      const next = { ...expanded };
      delete next[id];
      setExpanded(next);
    } catch {}
  }

  return (
    <div>
      <h2 className="text-2xl font-bold mb-4">Memories</h2>

      <div className="flex gap-2 mb-4">
        <input
          className="input input-bordered flex-1"
          placeholder="Search memories..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && search()}
        />
        <input
          className="input input-bordered w-32"
          placeholder="Domain"
          value={domain}
          onChange={(e) => setDomain(e.target.value)}
        />
        <select
          className="select select-bordered w-40"
          value={memType}
          onChange={(e) => setMemType(e.target.value)}
        >
          <option value="">All types</option>
          <option value="semantic">Semantic</option>
          <option value="episodic">Episodic</option>
          <option value="procedural">Procedural</option>
        </select>
        <button
          className={`btn btn-primary ${loading ? "loading" : ""}`}
          onClick={search}
        >
          Search
        </button>
      </div>

      {results.length === 0 && !loading && (
        <EmptyState message="Search for memories above" />
      )}

      <div className="flex flex-col gap-2">
        {results.map((r) => (
          <div key={r.id} className="card bg-base-100 shadow-sm">
            <div className="card-body p-4">
              <div className="flex items-start justify-between">
                <div
                  className="flex-1 cursor-pointer"
                  onClick={() => toggleExpand(r.id)}
                >
                  <div className="flex gap-2 items-center mb-1">
                    <Badge text={r.memory_type} />
                    <span className="text-xs text-base-content/50">
                      {r.domain}
                    </span>
                    <span className="text-xs text-base-content/40">
                      {(r.similarity * 100).toFixed(1)}%
                    </span>
                    <span className="text-xs text-base-content/40">
                      imp: {r.importance.toFixed(2)}
                    </span>
                  </div>
                  <p className="text-sm">{r.summary}</p>
                  {r.tags.length > 0 && (
                    <div className="flex gap-1 mt-1">
                      {r.tags.slice(0, 5).map((t) => (
                        <span key={t} className="badge badge-xs badge-ghost">
                          {t}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                <button
                  className="btn btn-ghost btn-xs text-error"
                  onClick={() => deleteMemory(r.id)}
                >
                  Del
                </button>
              </div>

              {expanded[r.id] && (
                <div className="mt-3 p-3 bg-base-200 rounded text-sm whitespace-pre-wrap">
                  <p className="font-mono text-xs text-base-content/40 mb-2">
                    ID: {r.id}
                  </p>
                  {expanded[r.id].content}
                  <div className="flex gap-4 mt-2 text-xs text-base-content/50">
                    <span>
                      Stability: {expanded[r.id].stability.toFixed(2)}
                    </span>
                    <span>
                      Confidence: {expanded[r.id].confidence.toFixed(2)}
                    </span>
                    <span>Accesses: {expanded[r.id].access_count}</span>
                    <span>Created: {expanded[r.id].created_at}</span>
                  </div>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
