import { useState, useEffect } from "react";
import { Check } from "@phosphor-icons/react";
import { api } from "../api/client";
import type { SessionEntry } from "../api/types";
import Badge from "../components/Badge";
import EmptyState from "../components/EmptyState";
import PageHeader from "../components/PageHeader";
import LoadingSpinner from "../components/LoadingSpinner";
import { useToastContext } from "../context/ToastContext";

interface Signal {
  signal_type: string;
  content: string;
  confidence: number;
  domain: string;
  tags: string[];
}

export default function SignalsPage() {
  const { addToast } = useToastContext();
  const [sessions, setSessions] = useState<SessionEntry[]>([]);
  const [sessionId, setSessionId] = useState("");
  const [signals, setSignals] = useState<Signal[]>([]);
  const [loading, setLoading] = useState(false);

  // Load recent sessions for dropdown
  useEffect(() => {
    api<{ sessions: SessionEntry[] }>("/admin/sessions")
      .then((d) => setSessions(d.sessions || []))
      .catch(() => {});
  }, []);

  // Auto-load signals when session changes
  useEffect(() => {
    if (!sessionId) {
      setSignals([]);
      return;
    }
    loadSignals();
  }, [sessionId]);

  async function loadSignals() {
    if (!sessionId.trim()) return;
    setLoading(true);
    try {
      const res = await api<{ signals: Signal[] }>(
        `/ingest/${sessionId}/signals`,
      );
      setSignals(res.signals || []);
    } catch {
      setSignals([]);
    } finally {
      setLoading(false);
    }
  }

  async function approveAll() {
    if (!sessionId.trim()) return;
    try {
      await api(`/ingest/${sessionId}/signals/approve`, "POST");
      setSignals([]);
      addToast("All signals approved", "success");
    } catch {
      addToast("Failed to approve signals", "error");
    }
  }

  return (
    <div>
      <PageHeader
        title="Pending Signals"
        subtitle="Review and approve detected signals"
      />

      <div className="flex flex-wrap gap-2 mb-4">
        <select
          className="flex-1 min-w-48 rounded-lg border border-base-content/10 bg-base-200 px-3 py-2 text-sm focus:border-primary/50 focus:outline-none"
          value={sessionId}
          onChange={(e) => setSessionId(e.target.value)}
        >
          <option value="">Select a session...</option>
          {sessions.map((s) => (
            <option key={s.session_id} value={s.session_id}>
              {s.session_id.slice(0, 12)}...{" "}
              {s.current_task ? `— ${s.current_task.slice(0, 40)}` : ""}{" "}
              {!s.ended_at ? "(active)" : ""}
            </option>
          ))}
        </select>
        {signals.length > 0 && (
          <button
            className="flex items-center gap-1.5 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-content hover:bg-accent/90 transition-colors"
            onClick={approveAll}
          >
            <Check size={16} weight="bold" />
            Approve All ({signals.length})
          </button>
        )}
      </div>

      {loading && <LoadingSpinner />}

      {!loading && sessionId && signals.length === 0 && (
        <EmptyState message="No pending signals for this session" />
      )}

      {!loading && !sessionId && (
        <EmptyState message="Select a session to view pending signals" />
      )}

      <div className="flex flex-col gap-2">
        {signals.map((s, i) => (
          <div
            key={i}
            className="rounded-xl bg-base-100 border border-base-content/5 p-4 hover:border-base-content/10 transition-colors"
          >
            <div className="flex gap-2 items-center mb-1">
              <Badge text={s.signal_type} />
              <span className="text-xs text-base-content/40">{s.domain}</span>
              <div className="flex-1" />
              <span className="text-xs text-base-content/40 tabular-nums">
                Confidence: {(s.confidence * 100).toFixed(0)}%
              </span>
            </div>
            <p className="text-sm">{s.content}</p>
            {s.tags.length > 0 && (
              <div className="flex gap-1 mt-1">
                {s.tags.map((t) => (
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
        ))}
      </div>
    </div>
  );
}
