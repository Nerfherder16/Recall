import { useState, useEffect, useCallback } from "react";
import {
  MagnifyingGlass,
  Trash,
  PushPin,
  Sparkle,
  Lock,
  ShieldCheck,
} from "@phosphor-icons/react";
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
import { GlassCard } from "../components/common/GlassCard";
import { Button } from "../components/common/Button";
import { Select } from "../components/common/Input";
import { Checkbox } from "../components/common/Checkbox";
import { useLocalStorage } from "../hooks/useLocalStorage";
import { useToastContext } from "../context/ToastContext";

function shouldSuggestPin(r: BrowseResult): boolean {
  return !r.pinned && r.importance >= 0.7 && r.access_count >= 10;
}

function DurabilityBadge({ durability }: { durability: string | null }) {
  if (!durability || durability === "ephemeral") return null;
  if (durability === "permanent") {
    return (
      <span className="inline-flex items-center gap-0.5 rounded-full bg-emerald-500/10 text-emerald-400 px-2 py-0.5 text-[10px] font-medium ring-1 ring-emerald-500/20">
        <Lock size={10} weight="fill" /> Permanent
      </span>
    );
  }
  if (durability === "durable") {
    return (
      <span className="inline-flex items-center gap-0.5 rounded-full bg-cyan-500/10 text-cyan-400 px-2 py-0.5 text-[10px] font-medium ring-1 ring-cyan-500/20">
        <ShieldCheck size={10} weight="fill" /> Durable
      </span>
    );
  }
  return null;
}

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
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [detailMem, setDetailMem] = useState<MemoryDetail | null>(null);

  useEffect(() => {
    api<{ domains: DomainStat[] }>("/stats/domains")
      .then((d) => setDomains(d.domains.map((x) => x.domain)))
      .catch(() => {});
    api<UserInfo[]>("/admin/users")
      .then((u) => setUsers(u))
      .catch(() => {});
  }, []);

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
          access_count: e.access_count ?? 0,
          durability: e.durability ?? null,
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
      <GlassCard className="p-4 mb-6">
        <div className="flex flex-wrap gap-2">
          <div className="flex-1 min-w-48 relative">
            <MagnifyingGlass
              size={16}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400"
            />
            <input
              className="w-full rounded-xl border border-zinc-200 dark:border-white/[0.06] bg-white dark:bg-zinc-900/80 pl-9 pr-3 py-2 text-sm text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 focus:border-violet-500/50 focus:outline-none focus:ring-2 focus:ring-violet-500/20 transition-colors"
              placeholder="Search memories (or leave empty for recent)..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && search()}
            />
          </div>
          <Select
            className="w-36"
            value={domain}
            onChange={(e) => setDomain(e.target.value)}
          >
            <option value="">All domains</option>
            {domains.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </Select>
          <Select
            className="w-36"
            value={memType}
            onChange={(e) => setMemType(e.target.value)}
          >
            <option value="">All types</option>
            <option value="semantic">Semantic</option>
            <option value="episodic">Episodic</option>
            <option value="procedural">Procedural</option>
          </Select>
          <Select
            className="w-36"
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
          </Select>
          <Button onClick={search}>Search</Button>
        </div>
      </GlassCard>

      {loading && <LoadingSpinner />}
      {!loading && results.length === 0 && (
        <EmptyState message="No memories found" />
      )}

      {/* Grid view */}
      {!loading && results.length > 0 && view === "grid" && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {results.map((r) => (
            <GlassCard key={r.id} hover className="p-4">
              <div className="flex items-start gap-2">
                <Checkbox
                  checked={selected.has(r.id)}
                  onChange={() => toggleSelect(r.id)}
                  className="mt-1"
                />
                <div className="flex-1 min-w-0">
                  <div className="flex gap-1.5 items-center flex-wrap mb-1">
                    <Badge text={r.memory_type} />
                    <span className="text-xs text-zinc-400 dark:text-zinc-500">
                      {r.domain}
                    </span>
                    {r.stored_by && (
                      <span className="inline-flex items-center rounded-full bg-blue-500/10 text-blue-400 px-2 py-0.5 text-[10px] font-medium ring-1 ring-blue-500/20">
                        {r.stored_by}
                      </span>
                    )}
                    {r.pinned && (
                      <span className="inline-flex items-center gap-0.5 rounded-full bg-amber-500/10 text-amber-400 px-2 py-0.5 text-[10px] font-medium ring-1 ring-amber-500/20">
                        <PushPin size={10} weight="fill" /> Pinned
                      </span>
                    )}
                    {shouldSuggestPin(r) && (
                      <button
                        className="inline-flex items-center gap-0.5 rounded-full bg-violet-500/10 text-violet-400 px-2 py-0.5 text-[10px] font-medium ring-1 ring-violet-500/20 hover:bg-violet-500/20 transition-colors"
                        onClick={(e) => {
                          e.stopPropagation();
                          togglePin(r.id, false);
                        }}
                      >
                        <Sparkle size={10} weight="fill" /> Pin?
                      </button>
                    )}
                    <DurabilityBadge durability={r.durability} />
                  </div>
                  <p
                    className="text-sm cursor-pointer text-zinc-700 dark:text-zinc-300 hover:text-violet-500 dark:hover:text-violet-400 transition-colors line-clamp-3"
                    onClick={() => openDetail(r.id)}
                  >
                    {r.summary}
                  </p>
                  <div className="flex items-center justify-between mt-2">
                    <div className="flex gap-1">
                      {r.tags.slice(0, 3).map((t) => (
                        <span
                          key={t}
                          className="inline-flex items-center rounded-full bg-zinc-100 dark:bg-zinc-800 text-zinc-400 px-2 py-0.5 text-[10px] font-medium ring-1 ring-zinc-200 dark:ring-zinc-700"
                        >
                          {t}
                        </span>
                      ))}
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        className={`rounded-lg p-1.5 transition-colors shrink-0 ${r.pinned ? "text-amber-400 hover:bg-amber-500/10" : "text-zinc-400 hover:text-amber-400 hover:bg-amber-500/10"}`}
                        onClick={() => togglePin(r.id, r.pinned)}
                        title={r.pinned ? "Unpin" : "Pin"}
                      >
                        <PushPin
                          size={14}
                          weight={r.pinned ? "fill" : "regular"}
                        />
                      </button>
                      <span className="font-mono text-xs text-zinc-400 tabular-nums">
                        {r.importance.toFixed(2)}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </GlassCard>
          ))}
        </div>
      )}

      {/* List view */}
      {!loading && results.length > 0 && view === "list" && (
        <div className="flex flex-col gap-2">
          {results.map((r) => (
            <GlassCard key={r.id} hover className="p-4">
              <div className="flex items-start gap-3">
                <Checkbox
                  checked={selected.has(r.id)}
                  onChange={() => toggleSelect(r.id)}
                  className="mt-1"
                />
                <div
                  className="flex-1 cursor-pointer min-w-0"
                  onClick={() => openDetail(r.id)}
                >
                  <div className="flex gap-1.5 items-center flex-wrap mb-1">
                    <Badge text={r.memory_type} />
                    <span className="text-xs text-zinc-400 dark:text-zinc-500">
                      {r.domain}
                    </span>
                    {r.stored_by && (
                      <span className="inline-flex items-center rounded-full bg-blue-500/10 text-blue-400 px-2 py-0.5 text-[10px] font-medium ring-1 ring-blue-500/20">
                        {r.stored_by}
                      </span>
                    )}
                    {r.pinned && (
                      <span className="inline-flex items-center gap-0.5 rounded-full bg-amber-500/10 text-amber-400 px-2 py-0.5 text-[10px] font-medium ring-1 ring-amber-500/20">
                        <PushPin size={10} weight="fill" /> Pinned
                      </span>
                    )}
                    {shouldSuggestPin(r) && (
                      <button
                        className="inline-flex items-center gap-0.5 rounded-full bg-violet-500/10 text-violet-400 px-2 py-0.5 text-[10px] font-medium ring-1 ring-violet-500/20 hover:bg-violet-500/20 transition-colors"
                        onClick={(e) => {
                          e.stopPropagation();
                          togglePin(r.id, false);
                        }}
                      >
                        <Sparkle size={10} weight="fill" /> Pin?
                      </button>
                    )}
                    <DurabilityBadge durability={r.durability} />
                    {r.similarity > 0 && (
                      <span className="font-mono text-xs text-zinc-400 tabular-nums">
                        {(r.similarity * 100).toFixed(1)}%
                      </span>
                    )}
                    <span className="font-mono text-xs text-zinc-400 tabular-nums">
                      imp: {r.importance.toFixed(2)}
                    </span>
                  </div>
                  <p className="text-sm text-zinc-700 dark:text-zinc-300">
                    {r.summary}
                  </p>
                  {r.tags.length > 0 && (
                    <div className="flex gap-1 mt-1">
                      {r.tags.slice(0, 5).map((t) => (
                        <span
                          key={t}
                          className="inline-flex items-center rounded-full bg-zinc-100 dark:bg-zinc-800 text-zinc-400 px-2 py-0.5 text-[10px] font-medium ring-1 ring-zinc-200 dark:ring-zinc-700"
                        >
                          {t}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                <div className="flex flex-col gap-1 shrink-0">
                  <button
                    className={`rounded-lg p-1.5 transition-colors ${r.pinned ? "text-amber-400 hover:bg-amber-500/10" : "text-zinc-400 hover:text-amber-400 hover:bg-amber-500/10"}`}
                    onClick={() => togglePin(r.id, r.pinned)}
                    title={r.pinned ? "Unpin" : "Pin"}
                  >
                    <PushPin size={16} weight={r.pinned ? "fill" : "regular"} />
                  </button>
                  <button
                    className="rounded-lg p-1.5 text-zinc-400 hover:text-red-400 hover:bg-red-500/10 transition-colors"
                    onClick={() => deleteSingle(r.id)}
                    title="Delete"
                  >
                    <Trash size={16} />
                  </button>
                </div>
              </div>
            </GlassCard>
          ))}
        </div>
      )}

      <SelectionToolbar
        count={selected.size}
        onDelete={() => setConfirmDelete(true)}
        onClear={() => setSelected(new Set())}
      />

      <ConfirmDialog
        open={confirmDelete}
        title="Delete Memories"
        message={`Are you sure you want to delete ${selected.size} selected memories? This cannot be undone.`}
        confirmLabel="Delete"
        onConfirm={bulkDelete}
        onCancel={() => setConfirmDelete(false)}
      />

      <MemoryDetailModal
        memory={detailMem}
        onClose={() => setDetailMem(null)}
      />
    </div>
  );
}
