import { useState, useEffect, useCallback } from "react";
import { Plus, Trash, Warning } from "@phosphor-icons/react";
import { api } from "../api/client";
import type { AntiPattern, DomainStat } from "../api/types";
import PageHeader from "../components/PageHeader";
import LoadingSpinner from "../components/LoadingSpinner";
import EmptyState from "../components/EmptyState";
import ConfirmDialog from "../components/ConfirmDialog";
import { useToastContext } from "../context/ToastContext";

export default function AntiPatternsPage() {
  const { addToast } = useToastContext();
  const [patterns, setPatterns] = useState<AntiPattern[]>([]);
  const [loading, setLoading] = useState(true);
  const [domainFilter, setDomainFilter] = useState("");
  const [domains, setDomains] = useState<string[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [deleteId, setDeleteId] = useState<string | null>(null);

  // Create form state
  const [form, setForm] = useState({
    pattern: "",
    warning: "",
    alternative: "",
    severity: "warning",
    domain: "general",
    tags: "",
  });

  useEffect(() => {
    api<{ domains: DomainStat[] }>("/stats/domains")
      .then((d) => setDomains(d.domains.map((x) => x.domain)))
      .catch(() => {});
  }, []);

  const loadPatterns = useCallback(async () => {
    setLoading(true);
    try {
      const url = domainFilter
        ? `/memory/anti-patterns?domain=${encodeURIComponent(domainFilter)}`
        : "/memory/anti-patterns";
      const res = await api<{ anti_patterns: AntiPattern[]; total: number }>(
        url,
      );
      setPatterns(res.anti_patterns || []);
    } catch {
      setPatterns([]);
    } finally {
      setLoading(false);
    }
  }, [domainFilter]);

  useEffect(() => {
    loadPatterns();
  }, [loadPatterns]);

  async function handleCreate() {
    try {
      const tags = form.tags
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);
      await api("/memory/anti-pattern", "POST", {
        pattern: form.pattern,
        warning: form.warning,
        alternative: form.alternative || null,
        severity: form.severity,
        domain: form.domain,
        tags,
      });
      addToast("Anti-pattern created", "success");
      setShowCreate(false);
      setForm({
        pattern: "",
        warning: "",
        alternative: "",
        severity: "warning",
        domain: "general",
        tags: "",
      });
      loadPatterns();
    } catch {
      addToast("Failed to create anti-pattern", "error");
    }
  }

  async function handleDelete() {
    if (!deleteId) return;
    try {
      await api(`/memory/anti-pattern/${deleteId}`, "DELETE");
      setPatterns((prev) => prev.filter((p) => p.id !== deleteId));
      addToast("Anti-pattern deleted", "success");
    } catch {
      addToast("Failed to delete", "error");
    } finally {
      setDeleteId(null);
    }
  }

  const severityColor: Record<string, string> = {
    error: "bg-red-500/10 text-red-400 ring-red-500/20",
    warning: "bg-amber-500/10 text-amber-400 ring-amber-500/20",
    info: "bg-blue-500/10 text-blue-400 ring-blue-500/20",
  };

  return (
    <div>
      <PageHeader
        title="Anti-Patterns"
        subtitle="Danger memories — things to avoid"
      >
        <button
          className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-content hover:bg-primary/90 transition-colors flex items-center gap-1.5"
          onClick={() => setShowCreate(true)}
        >
          <Plus size={16} /> New
        </button>
      </PageHeader>

      {/* Filters */}
      <div className="flex gap-2 mb-4">
        <select
          className="rounded-lg border border-base-content/10 bg-base-200 px-3 py-2 text-sm focus:border-primary/50 focus:outline-none w-44"
          value={domainFilter}
          onChange={(e) => setDomainFilter(e.target.value)}
        >
          <option value="">All domains</option>
          {domains.map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
        </select>
      </div>

      {loading && <LoadingSpinner />}
      {!loading && patterns.length === 0 && (
        <EmptyState message="No anti-patterns found" />
      )}

      {!loading && patterns.length > 0 && (
        <div className="flex flex-col gap-3">
          {patterns.map((ap) => (
            <div
              key={ap.id}
              className="rounded-xl bg-base-100 border border-base-content/5 p-4 hover:border-base-content/10 transition-colors"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-2">
                    <Warning size={16} className="text-amber-400 shrink-0" />
                    <span
                      className={`inline-flex items-center text-[11px] font-medium px-2 py-0.5 rounded-full ring-1 ${
                        severityColor[ap.severity] || severityColor.warning
                      }`}
                    >
                      {ap.severity}
                    </span>
                    <span className="text-xs text-base-content/40">
                      {ap.domain}
                    </span>
                    {ap.times_triggered > 0 && (
                      <span className="text-xs text-base-content/30">
                        triggered {ap.times_triggered}x
                      </span>
                    )}
                  </div>
                  <p className="text-sm font-medium mb-1">{ap.pattern}</p>
                  <p className="text-sm text-base-content/60">{ap.warning}</p>
                  {ap.alternative && (
                    <p className="text-sm text-emerald-400 mt-1">
                      Instead: {ap.alternative}
                    </p>
                  )}
                  {ap.tags.length > 0 && (
                    <div className="flex gap-1 mt-2">
                      {ap.tags.map((t) => (
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
                <button
                  className="rounded-lg p-1.5 text-base-content/30 hover:text-error hover:bg-error/10 transition-colors shrink-0"
                  onClick={() => setDeleteId(ap.id)}
                  title="Delete"
                >
                  <Trash size={16} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Create dialog */}
      {showCreate && (
        <dialog
          className="modal modal-open"
          onClick={(e) => e.target === e.currentTarget && setShowCreate(false)}
        >
          <div className="rounded-2xl bg-base-100 border border-base-content/5 p-6 max-w-lg w-full">
            <h3 className="text-lg font-semibold mb-4">New Anti-Pattern</h3>
            <div className="flex flex-col gap-3">
              <input
                className="w-full rounded-lg border border-base-content/10 bg-base-200 px-3 py-2 text-sm focus:border-primary/50 focus:outline-none"
                placeholder="Pattern — what to watch for"
                value={form.pattern}
                onChange={(e) => setForm({ ...form, pattern: e.target.value })}
              />
              <textarea
                className="w-full rounded-lg border border-base-content/10 bg-base-200 px-3 py-2 text-sm focus:border-primary/50 focus:outline-none min-h-20"
                placeholder="Warning — what to tell the user"
                value={form.warning}
                onChange={(e) => setForm({ ...form, warning: e.target.value })}
              />
              <input
                className="w-full rounded-lg border border-base-content/10 bg-base-200 px-3 py-2 text-sm focus:border-primary/50 focus:outline-none"
                placeholder="Alternative — better approach (optional)"
                value={form.alternative}
                onChange={(e) =>
                  setForm({ ...form, alternative: e.target.value })
                }
              />
              <div className="flex gap-2">
                <select
                  className="rounded-lg border border-base-content/10 bg-base-200 px-3 py-2 text-sm focus:border-primary/50 focus:outline-none flex-1"
                  value={form.severity}
                  onChange={(e) =>
                    setForm({ ...form, severity: e.target.value })
                  }
                >
                  <option value="info">Info</option>
                  <option value="warning">Warning</option>
                  <option value="error">Error</option>
                </select>
                <input
                  className="rounded-lg border border-base-content/10 bg-base-200 px-3 py-2 text-sm focus:border-primary/50 focus:outline-none flex-1"
                  placeholder="Domain"
                  value={form.domain}
                  onChange={(e) => setForm({ ...form, domain: e.target.value })}
                />
              </div>
              <input
                className="w-full rounded-lg border border-base-content/10 bg-base-200 px-3 py-2 text-sm focus:border-primary/50 focus:outline-none"
                placeholder="Tags (comma-separated)"
                value={form.tags}
                onChange={(e) => setForm({ ...form, tags: e.target.value })}
              />
            </div>
            <div className="flex justify-end gap-2 mt-4">
              <button
                className="rounded-lg px-4 py-2 text-sm text-base-content/60 hover:bg-base-200 transition-colors"
                onClick={() => setShowCreate(false)}
              >
                Cancel
              </button>
              <button
                className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-content hover:bg-primary/90 transition-colors"
                onClick={handleCreate}
                disabled={!form.pattern || !form.warning}
              >
                Create
              </button>
            </div>
          </div>
        </dialog>
      )}

      {/* Delete confirm */}
      <ConfirmDialog
        open={!!deleteId}
        title="Delete Anti-Pattern"
        message="Are you sure you want to delete this anti-pattern?"
        confirmLabel="Delete"
        confirmClass="btn-error"
        onConfirm={handleDelete}
        onCancel={() => setDeleteId(null)}
      />
    </div>
  );
}
