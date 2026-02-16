import { useState } from "react";
import { CaretDown } from "@phosphor-icons/react";
import { api } from "../api/client";
import type { SessionEntry, Turn } from "../api/types";
import { useRecallAPI } from "../hooks/useRecallAPI";
import EmptyState from "../components/EmptyState";
import PageHeader from "../components/PageHeader";
import LoadingSpinner from "../components/LoadingSpinner";

function timeAgo(iso: string): string {
  try {
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    const days = Math.floor(hrs / 24);
    return `${days}d ago`;
  } catch {
    return iso;
  }
}

function formatDuration(start: string, end: string | null): string {
  if (!end) return "ongoing";
  try {
    const ms = new Date(end).getTime() - new Date(start).getTime();
    const mins = Math.floor(ms / 60000);
    if (mins < 60) return `${mins}m`;
    const hrs = Math.floor(mins / 60);
    const remMins = mins % 60;
    return `${hrs}h ${remMins}m`;
  } catch {
    return "?";
  }
}

export default function SessionsPage() {
  const { data, loading } = useRecallAPI<{ sessions: SessionEntry[] }>(
    "/admin/sessions",
  );
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [turnsLoading, setTurnsLoading] = useState(false);
  const [turnsError, setTurnsError] = useState<string | null>(null);

  async function toggleExpand(sessionId: string) {
    if (expandedId === sessionId) {
      setExpandedId(null);
      setTurns([]);
      return;
    }
    setExpandedId(sessionId);
    setTurnsLoading(true);
    setTurnsError(null);
    try {
      const res = await api<{ turns: Turn[] }>(`/ingest/${sessionId}/turns`);
      setTurns(res.turns || []);
    } catch {
      setTurns([]);
      setTurnsError("Turns not available (session may be archived)");
    } finally {
      setTurnsLoading(false);
    }
  }

  return (
    <div>
      <PageHeader title="Sessions" subtitle="Active and archived sessions" />

      {loading && <LoadingSpinner />}

      {!loading && (!data?.sessions || data.sessions.length === 0) && (
        <EmptyState message="No sessions found" />
      )}

      {data?.sessions && data.sessions.length > 0 && (
        <div className="flex flex-col gap-3">
          {data.sessions.map((s) => {
            const isActive = !s.ended_at;
            const isExpanded = expandedId === s.session_id;
            return (
              <div
                key={s.session_id}
                className="rounded-xl bg-base-100 border border-base-content/5 hover:border-base-content/10 transition-colors"
              >
                <div
                  className="p-4 cursor-pointer"
                  onClick={() => toggleExpand(s.session_id)}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="font-mono text-sm">
                          {s.session_id.slice(0, 12)}...
                        </span>
                        {isActive ? (
                          <span className="inline-flex items-center rounded-md bg-emerald-500/10 text-emerald-400 px-2 py-0.5 text-[11px] font-medium">
                            Active
                          </span>
                        ) : (
                          <span className="inline-flex items-center rounded-md bg-zinc-500/10 text-zinc-400 px-2 py-0.5 text-[11px] font-medium">
                            Completed
                          </span>
                        )}
                      </div>
                      {s.current_task && (
                        <p className="text-sm text-base-content/60 truncate mb-1">
                          {s.current_task}
                        </p>
                      )}
                      <div className="flex gap-4 text-xs text-base-content/40">
                        <span>Started: {timeAgo(s.started_at)}</span>
                        <span>
                          Duration: {formatDuration(s.started_at, s.ended_at)}
                        </span>
                      </div>
                    </div>
                    <div className="flex gap-4 text-center shrink-0">
                      <div>
                        <p className="text-lg font-semibold tabular-nums">
                          {s.memories_created}
                        </p>
                        <p className="text-[11px] text-base-content/40">
                          memories
                        </p>
                      </div>
                      <div>
                        <p className="text-lg font-semibold tabular-nums">
                          {s.signals_detected}
                        </p>
                        <p className="text-[11px] text-base-content/40">
                          signals
                        </p>
                      </div>
                      <div>
                        <p className="text-lg font-semibold tabular-nums">
                          {s.turns_count}
                        </p>
                        <p className="text-[11px] text-base-content/40">
                          turns
                        </p>
                      </div>
                    </div>
                    <div className="ml-3">
                      <CaretDown
                        size={18}
                        className={`text-base-content/30 transition-transform ${isExpanded ? "rotate-180" : ""}`}
                      />
                    </div>
                  </div>
                </div>

                {/* Expanded: turn timeline */}
                {isExpanded && (
                  <div className="border-t border-base-content/5 px-4 py-3">
                    {turnsLoading && <LoadingSpinner size="sm" />}
                    {turnsError && (
                      <p className="text-sm text-base-content/40 italic py-2">
                        {turnsError}
                      </p>
                    )}
                    {!turnsLoading && !turnsError && turns.length === 0 && (
                      <p className="text-sm text-base-content/40 italic py-2">
                        No turns recorded
                      </p>
                    )}
                    {!turnsLoading && turns.length > 0 && (
                      <div className="relative pl-8 timeline-line space-y-4 py-2">
                        {turns.map((t, i) => (
                          <div key={i} className="relative">
                            {/* Timeline dot */}
                            <div
                              className={`absolute left-[-1.25rem] top-1 w-3 h-3 rounded-full border-2 ${
                                t.role === "user"
                                  ? "bg-primary border-primary"
                                  : "bg-secondary border-secondary"
                              }`}
                            />
                            <div>
                              <div className="flex items-center gap-2 mb-0.5">
                                <span
                                  className={`text-xs font-medium ${
                                    t.role === "user"
                                      ? "text-primary"
                                      : "text-secondary"
                                  }`}
                                >
                                  {t.role === "user" ? "User" : "Assistant"}
                                </span>
                                {t.timestamp && (
                                  <span className="text-xs text-base-content/30">
                                    {timeAgo(t.timestamp)}
                                  </span>
                                )}
                              </div>
                              <p className="text-sm text-base-content/70 line-clamp-4 whitespace-pre-wrap">
                                {t.content}
                              </p>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
