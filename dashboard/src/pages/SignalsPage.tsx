import { useState, useEffect } from "react";
import { Check } from "@phosphor-icons/react";
import { api } from "../api/client";
import type { SessionEntry } from "../api/types";
import Badge from "../components/Badge";
import EmptyState from "../components/EmptyState";
import PageHeader from "../components/PageHeader";
import LoadingSpinner from "../components/LoadingSpinner";
import { useToastContext } from "../context/ToastContext";
import { GlassCard } from "../components/common/GlassCard";
import { Button } from "../components/common/Button";
import { Select } from "../components/common/Input";

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

  useEffect(() => {
    api<{ sessions: SessionEntry[] }>("/admin/sessions")
      .then((d) => setSessions(d.sessions || []))
      .catch(() => {});
  }, []);

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
        <Select
          containerClass="flex-1 min-w-48"
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
        </Select>
        {signals.length > 0 && (
          <Button onClick={approveAll}>
            <Check size={16} weight="bold" />
            Approve All ({signals.length})
          </Button>
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
          <GlassCard key={i} hover className="p-4">
            <div className="flex gap-2 items-center mb-1">
              <Badge text={s.signal_type} />
              <span className="text-xs text-zinc-400 dark:text-zinc-500">
                {s.domain}
              </span>
              <div className="flex-1" />
              <span className="text-xs text-zinc-400 dark:text-zinc-500 tabular-nums">
                Confidence: {(s.confidence * 100).toFixed(0)}%
              </span>
            </div>
            <p className="text-sm text-zinc-900 dark:text-zinc-100">
              {s.content}
            </p>
            {s.tags.length > 0 && (
              <div className="flex gap-1 mt-1">
                {s.tags.map((t) => (
                  <span
                    key={t}
                    className="inline-flex items-center rounded-full bg-zinc-500/10 text-zinc-400 px-1.5 py-0.5 text-[10px] font-medium ring-1 ring-zinc-500/20"
                  >
                    {t}
                  </span>
                ))}
              </div>
            )}
          </GlassCard>
        ))}
      </div>
    </div>
  );
}
