import { useState, useEffect, useCallback } from "react";
import { MagnifyingGlass, Trash, PushPin } from "@phosphor-icons/react";
import { api } from "../api/client";
import type {
  BrowseResult,
  MemoryDetail,
  DomainStat,
  UserInfo,
} from "../api/types";
import Badge from "../components/Badge";
import EmptyState from "../components/EmptyState";
import PageHeader from "../components/PageHeader";
import LoadingSpinner from "../components/LoadingSpinner";
import ViewToggle from "../components/ViewToggle";
import SelectionToolbar from "../components/SelectionToolbar";
import ConfirmDialog from "../components/ConfirmDialog";
import MemoryDetailModal from "../components/MemoryDetailModal";
import { useLocalStorage } from "../hooks/useLocalStorage";
import { useToastContext } from "../context/ToastContext";

export default function MemoriesPage() {
  const { addToast } = useToastContext();
  const [query, setQuery] = useState("");
  const [domain, setDomain] = useState("");
  const [memType, setMemType] = useState("");
  const [userFilter, setUserFilter] = useState("");
  const [results, setResults] = useState<BrowseResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [view, setView] = useLocalStorage<"grid" | "list">(
    "recall_mem_view",
    "list",
  );
  const [domains, setDomains] = useState<string[]>([]);
  const [users, setUsers] = useState<UserInfo[]>([]);

  // Selection state
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [confirmDelete, setConfirmDelete] = useState(false);

  // Detail modal
  const [detailMem, setDetailMem] = useState<MemoryDetail | null>(null);

  // Load domains and users for filter dropdowns
  useEffect(() => {
    api<{ domains: DomainStat[] }>("/stats/domains")
      .then((d) => setDomains(d.domains.map((x) => x.domain)))
      .catch(() => {});
    api<UserInfo[]>("/admin/users")
      .then((u) => setUsers(u))
      .catch(() => {});
  }, []);

  // Auto-browse on mount (timeline, no query needed)
  useEffect(() => {
    loadTimeline();
  }, []);

  async function loadTimeline() {
    setLoading(true);
    try {
      const res = await api<{ entries: BrowseResult[] }>(
        "/search/timeline",
        "POST",
        { limit: 30 },
      );
      setResults(
        (res.entries || []).map((e) => ({
          ...e,
          tags: e.tags || [],
          similarity: e.similarity || 0,
          pinned: e.pinned ?? false,
        })),
      );
    } catch {
      setResults([]);
    } finally {
      setLoading(false);
    }
  }

  async function search() {
    if (!query.trim()) {
      loadTimeline();
      return;
    }
    setLoading(true);
    setSelected(new Set());
    try {
      const body: Record<string, unknown> = { query, limit: 30 };
      if (domain) body.domains = [domain];
      if (memType) body.memory_types = [memType];
      if (userFilter) body.user = userFilter;
      const res = await api<{ results: BrowseResult[] }>(
        "/search/browse",
        "POST",
        body,
      );
      setResults(res.results || []);
    } catch {
      setResults([]);
    } finally {
      setLoading(false);
    }
  }

  const toggleSelect = useCallback((id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  async function openDetail(id: string) {
    try {
      const detail = await api<MemoryDetail>(`/memory/${id}`);
      setDetailMem(detail);
    } catch {
      addToast("Failed to load memory detail", "error");
    }
  }

  async function deleteSingle(id: string) {
    try {
      await api(`/memory/${id}`, "DELETE");
      setResults((prev) => prev.filter((r) => r.id !== id));
      setSelected((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
      addToast("Memory deleted", "success");
    } catch {
      addToast("Failed to delete memory", "error");
    }
  }

  async function togglePin(id: string, currentlyPinned: boolean) {
    try {
      if (currentlyPinned) {
        await api(`/memory/${id}/pin`, "DELETE");
      } else {
        await api(`/memory/${id}/pin`, "POST");
      }
      setResults((prev) =>
        prev.map((r) => (r.id === id ? { ...r, pinned: !currentlyPinned } : r)),
      );
      if (detailMem && detailMem.id === id) {
        setDetailMem({ ...detailMem, pinned: !currentlyPinned });
      }
      addToast(
        currentlyPinned ? "Memory unpinned" : "Memory pinned",
        "success",
      );
    } catch {
      addToast("Failed to update pin status", "error");
    }
  }

  async function bulkDelete() {
    setConfirmDelete(false);
    const ids = Array.from(selected);
    try {
      await api("/memory/batch/delete", "POST", { ids });
      setResults((prev) => prev.filter((r) => !selected.has(r.id)));
      addToast(`Deleted ${ids.length} memories`, "success");
      setSelected(new Set());
    } catch {
      addToast("Bulk delete failed", "error");
    }
  }

  return (
    <div>
      <PageHeader title="Memories" subtitle="Browse and manage stored memories">
        <ViewToggle view={view} onChange={setView} />
      </PageHeader>

      {/* Search bar */}
      <div className="flex flex-wrap gap-2 mb-4">
        <div className="flex-1 min-w-48 relative">
          <MagnifyingGlass
            size={16}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-base-content/30"
          />
          <input
            className="w-full rounded-lg border border-base-content/10 bg-base-200 pl-9 pr-3 py-2 text-sm focus:border-primary/50 focus:outline-none"
            placeholder="Search memories (or leave empty for recent)..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && search()}
          />
        </div>
        <select
          className="rounded-lg border border-base-content/10 bg-base-200 px-3 py-2 text-sm focus:border-primary/50 focus:outline-none w-36"
          value={domain}
          onChange={(e) => setDomain(e.target.value)}
        >
          <option value="">All domains</option>
          {domains.map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
        </select>
        <select
          className="rounded-lg border border-base-content/10 bg-base-200 px-3 py-2 text-sm focus:border-primary/50 focus:outline-none w-36"
          value={memType}
          onChange={(e) => setMemType(e.target.value)}
        >
          <option value="">All types</option>
          <option value="semantic">Semantic</option>
          <option value="episodic">Episodic</option>
          <option value="procedural">Procedural</option>
        </select>
        <select
          className="rounded-lg border border-base-content/10 bg-base-200 px-3 py-2 text-sm focus:border-primary/50 focus:outline-none w-36"
          value={userFilter}
          onChange={(e) => setUserFilter(e.target.value)}
        >
          <option value="">All users</option>
          <option value="system">system</option>
          {users.map((u) => (
            <option key={u.id} value={u.username}>
              {u.display_name || u.username}
            </option>
          ))}
        </select>
        <button
          className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-content hover:bg-primary/90 transition-colors"
          onClick={search}
        >
          Search
        </button>
      </div>

      {loading && <LoadingSpinner />}

      {!loading && results.length === 0 && (
        <EmptyState message="No memories found" />
      )}

      {/* Grid view */}
      {!loading && results.length > 0 && view === "grid" && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {results.map((r) => (
            <div
              key={r.id}
              className="rounded-xl bg-base-100 border border-base-content/5 p-4 hover:border-base-content/10 transition-colors"
            >
              <div className="flex items-start gap-2">
                <input
                  type="checkbox"
                  className="checkbox checkbox-sm mt-1"
                  checked={selected.has(r.id)}
                  onChange={() => toggleSelect(r.id)}
                />
                <div className="flex-1 min-w-0">
                  <div className="flex gap-2 items-center mb-1">
                    <Badge text={r.memory_type} />
                    <span className="text-xs text-base-content/40">
                      {r.domain}
                    </span>
                    {r.stored_by && (
                      <span className="inline-flex items-center rounded-md bg-blue-500/10 text-blue-400 px-1.5 py-0.5 text-[10px] font-medium">
                        {r.stored_by}
                      </span>
                    )}
                    {r.pinned && (
                      <span className="inline-flex items-center gap-0.5 rounded-md bg-amber-500/10 text-amber-400 px-1.5 py-0.5 text-[10px] font-medium">
                        <PushPin size={10} weight="fill" /> Pinned
                      </span>
                    )}
                  </div>
                  <p
                    className="text-sm cursor-pointer hover:text-primary transition-colors line-clamp-3"
                    onClick={() => openDetail(r.id)}
                  >
                    {r.summary}
                  </p>
                  <div className="flex items-center justify-between mt-2">
                    <div className="flex gap-1">
                      {r.tags.slice(0, 3).map((t) => (
                        <span
                          key={t}
                          className="inline-flex items-center rounded-md bg-zinc-500/10 text-zinc-400 px-1.5 py-0.5 text-[10px] font-medium"
                        >
                          {t}
                        </span>
                      ))}
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        className={`rounded-lg p-1.5 transition-colors shrink-0 ${r.pinned ? "text-amber-400 hover:text-amber-300 hover:bg-amber-500/10" : "text-base-content/30 hover:text-amber-400 hover:bg-amber-500/10"}`}
                        onClick={() => togglePin(r.id, r.pinned)}
                        title={r.pinned ? "Unpin" : "Pin"}
                      >
                        <PushPin
                          size={14}
                          weight={r.pinned ? "fill" : "regular"}
                        />
                      </button>
                      <span className="text-xs text-base-content/30 tabular-nums">
                        imp: {r.importance.toFixed(2)}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* List view */}
      {!loading && results.length > 0 && view === "list" && (
        <div className="flex flex-col gap-2">
          {results.map((r) => (
            <div
              key={r.id}
              className="rounded-xl bg-base-100 border border-base-content/5 p-4 hover:border-base-content/10 transition-colors"
            >
              <div className="flex items-start gap-3">
                <input
                  type="checkbox"
                  className="checkbox checkbox-sm mt-1"
                  checked={selected.has(r.id)}
                  onChange={() => toggleSelect(r.id)}
                />
                <div
                  className="flex-1 cursor-pointer min-w-0"
                  onClick={() => openDetail(r.id)}
                >
                  <div className="flex gap-2 items-center mb-1">
                    <Badge text={r.memory_type} />
                    <span className="text-xs text-base-content/40">
                      {r.domain}
                    </span>
                    {r.stored_by && (
                      <span className="inline-flex items-center rounded-md bg-blue-500/10 text-blue-400 px-1.5 py-0.5 text-[10px] font-medium">
                        {r.stored_by}
                      </span>
                    )}
                    {r.pinned && (
                      <span className="inline-flex items-center gap-0.5 rounded-md bg-amber-500/10 text-amber-400 px-1.5 py-0.5 text-[10px] font-medium">
                        <PushPin size={10} weight="fill" /> Pinned
                      </span>
                    )}
                    {r.similarity > 0 && (
                      <span className="text-xs text-base-content/30 tabular-nums">
                        {(r.similarity * 100).toFixed(1)}%
                      </span>
                    )}
                    <span className="text-xs text-base-content/30 tabular-nums">
                      imp: {r.importance.toFixed(2)}
                    </span>
                  </div>
                  <p className="text-sm">{r.summary}</p>
                  {r.tags.length > 0 && (
                    <div className="flex gap-1 mt-1">
                      {r.tags.slice(0, 5).map((t) => (
                        <span
                          key={t}
                          className="inline-flex items-center rounded-md bg-zinc-500/10 text-zinc-400 px-1.5 py-0.5 text-[10px] font-medium"
                        >
                          {t}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                <div className="flex flex-col gap-1 shrink-0">
                  <button
                    className={`rounded-lg p-1.5 transition-colors ${r.pinned ? "text-amber-400 hover:text-amber-300 hover:bg-amber-500/10" : "text-base-content/30 hover:text-amber-400 hover:bg-amber-500/10"}`}
                    onClick={() => togglePin(r.id, r.pinned)}
                    title={r.pinned ? "Unpin" : "Pin"}
                  >
                    <PushPin size={16} weight={r.pinned ? "fill" : "regular"} />
                  </button>
                  <button
                    className="rounded-lg p-1.5 text-base-content/30 hover:text-error hover:bg-error/10 transition-colors"
                    onClick={() => deleteSingle(r.id)}
                    title="Delete"
                  >
                    <Trash size={16} />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Bulk selection toolbar */}
      <SelectionToolbar
        count={selected.size}
        onDelete={() => setConfirmDelete(true)}
        onClear={() => setSelected(new Set())}
      />

      {/* Confirm bulk delete dialog */}
      <ConfirmDialog
        open={confirmDelete}
        title="Delete Memories"
        message={`Are you sure you want to delete ${selected.size} selected memories? This cannot be undone.`}
        confirmLabel="Delete"
        confirmClass="btn-error"
        onConfirm={bulkDelete}
        onCancel={() => setConfirmDelete(false)}
      />

      {/* Detail modal */}
      <MemoryDetailModal
        memory={detailMem}
        onClose={() => setDetailMem(null)}
      />
    </div>
  );
}
