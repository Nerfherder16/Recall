import { useState } from "react";
import { CaretDown } from "@phosphor-icons/react";
import { api } from "../api/client";
import type { SessionEntry, Turn } from "../api/types";
import { useRecallAPI } from "../hooks/useRecallAPI";
import EmptyState from "../components/EmptyState";
import PageHeader from "../components/PageHeader";
import LoadingSpinner from "../components/LoadingSpinner";
import { GlassCard } from "../components/common/GlassCard";
import { timeAgo } from "../lib/utils";

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
              <GlassCard key={s.session_id} hover>
                <div
                  className="p-4 cursor-pointer"
                  onClick={() => toggleExpand(s.session_id)}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="font-mono text-sm text-zinc-900 dark:text-zinc-100">
                          {s.session_id.slice(0, 12)}...
                        </span>
                        {isActive ? (
                          <span className="inline-flex items-center rounded-full bg-emerald-500/10 text-emerald-400 px-2 py-0.5 text-[11px] font-medium ring-1 ring-emerald-500/20">
                            Active
                          </span>
                        ) : (
                          <span className="inline-flex items-center rounded-full bg-zinc-500/10 text-zinc-400 px-2 py-0.5 text-[11px] font-medium ring-1 ring-zinc-500/20">
                            Completed
                          </span>
                        )}
                      </div>
                      {s.current_task && (
                        <p className="text-sm text-zinc-500 dark:text-zinc-400 truncate mb-1">
                          {s.current_task}
                        </p>
                      )}
                      <div className="flex gap-4 text-xs text-zinc-400 dark:text-zinc-500">
                        <span>Started: {timeAgo(s.started_at)}</span>
                        <span>
                          Duration: {formatDuration(s.started_at, s.ended_at)}
                        </span>
                      </div>
                    </div>
                    <div className="flex gap-4 text-center shrink-0">
                      <div>
                        <p className="font-display text-lg font-semibold tabular-nums text-zinc-900 dark:text-zinc-100">
                          {s.memories_created}
                        </p>
                        <p className="font-mono text-[10px] uppercase tracking-[0.15em] text-zinc-400 dark:text-zinc-500">
                          memories
                        </p>
                      </div>
                      <div>
                        <p className="font-display text-lg font-semibold tabular-nums text-zinc-900 dark:text-zinc-100">
                          {s.signals_detected}
                        </p>
                        <p className="font-mono text-[10px] uppercase tracking-[0.15em] text-zinc-400 dark:text-zinc-500">
                          signals
                        </p>
                      </div>
                      <div>
                        <p className="font-display text-lg font-semibold tabular-nums text-zinc-900 dark:text-zinc-100">
                          {s.turns_count}
                        </p>
                        <p className="font-mono text-[10px] uppercase tracking-[0.15em] text-zinc-400 dark:text-zinc-500">
                          turns
                        </p>
                      </div>
                    </div>
                    <div className="ml-3">
                      <CaretDown
                        size={18}
                        className={`text-zinc-400 dark:text-zinc-500 transition-transform ${isExpanded ? "rotate-180" : ""}`}
                      />
                    </div>
                  </div>
                </div>

                {/* Expanded: turn timeline */}
                {isExpanded && (
                  <div className="border-t border-zinc-200 dark:border-white/[0.06] px-4 py-3">
                    {turnsLoading && <LoadingSpinner size="sm" />}
                    {turnsError && (
                      <p className="text-sm text-zinc-400 dark:text-zinc-500 italic py-2">
                        {turnsError}
                      </p>
                    )}
                    {!turnsLoading && !turnsError && turns.length === 0 && (
                      <p className="text-sm text-zinc-400 dark:text-zinc-500 italic py-2">
                        No turns recorded
                      </p>
                    )}
                    {!turnsLoading && turns.length > 0 && (
                      <div className="relative pl-8 timeline-line space-y-4 py-2">
                        {turns.map((t, i) => (
                          <div key={i} className="relative">
                            <div
                              className={`absolute left-[-1.25rem] top-1 w-3 h-3 rounded-full border-2 ${
                                t.role === "user"
                                  ? "bg-violet-500 border-violet-500"
                                  : "bg-zinc-400 dark:bg-zinc-500 border-zinc-400 dark:border-zinc-500"
                              }`}
                            />
                            <div>
                              <div className="flex items-center gap-2 mb-0.5">
                                <span
                                  className={`text-xs font-medium ${
                                    t.role === "user"
                                      ? "text-violet-600 dark:text-violet-400"
                                      : "text-zinc-500 dark:text-zinc-400"
                                  }`}
                                >
                                  {t.role === "user" ? "User" : "Assistant"}
                                </span>
                                {t.timestamp && (
                                  <span className="text-xs text-zinc-400 dark:text-zinc-600">
                                    {timeAgo(t.timestamp)}
                                  </span>
                                )}
                              </div>
                              <p className="text-sm text-zinc-600 dark:text-zinc-300 line-clamp-4 whitespace-pre-wrap">
                                {t.content}
                              </p>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </GlassCard>
            );
          })}
        </div>
      )}
    </div>
  );
}
