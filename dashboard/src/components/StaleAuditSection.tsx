import { useState, useEffect, useCallback } from "react";
import { Warning, CheckCircle, Trash, Eye } from "@phosphor-icons/react";
import { api } from "../api/client";
import type { StaleMemory, StaleMemoriesResponse } from "../api/types";
import { GlassCard } from "./common/GlassCard";
import { Button } from "./common/Button";
import {
  Table,
  TableHead,
  TableBody,
  TableRow,
  TableCell,
} from "./common/Table";
import { useToastContext } from "../context/ToastContext";
import { InfoTip } from "./health/InfoTip";

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

interface Props {
  onViewMemory?: (memoryId: string) => void;
}

export function StaleAuditSection({ onViewMemory }: Props) {
  const { addToast } = useToastContext();
  const [stale, setStale] = useState<StaleMemory[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchStale = useCallback(async () => {
    try {
      const data = await api<StaleMemoriesResponse>("/admin/stale");
      setStale(data.stale_memories || []);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to load stale memories";
      addToast(message, "error");
    } finally {
      setLoading(false);
    }
  }, [addToast]);

  useEffect(() => {
    fetchStale();
  }, [fetchStale]);

  const handleResolve = useCallback(
    async (id: string) => {
      try {
        await api(`/admin/stale/${id}/resolve`, "POST");
        setStale((prev) => prev.filter((m) => m.id !== id));
        addToast("Stale flag resolved", "success");
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Failed to resolve";
        addToast(message, "error");
      }
    },
    [addToast],
  );

  const handleDelete = useCallback(
    async (id: string) => {
      try {
        await api(`/memory/${id}`, "DELETE");
        setStale((prev) => prev.filter((m) => m.id !== id));
        addToast("Memory deleted", "success");
      } catch (err) {
        const message = err instanceof Error ? err.message : "Failed to delete";
        addToast(message, "error");
      }
    },
    [addToast],
  );

  if (loading) {
    return (
      <GlassCard className="p-6">
        <h3 className="text-sm font-semibold flex items-center gap-2 text-zinc-900 dark:text-zinc-100 mb-4">
          <Warning size={16} className="text-amber-400" />
          Stale Memories
        </h3>
        <p className="text-xs text-zinc-400 py-4 text-center animate-pulse">
          Loading...
        </p>
      </GlassCard>
    );
  }

  return (
    <GlassCard className="p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold flex items-center gap-2 text-zinc-900 dark:text-zinc-100">
          <Warning size={16} className="text-amber-400" />
          Stale Memories ({stale.length})
          <InfoTip text="Flagged when source code a memory references has changed (tracked via git commits). When a file edit invalidates a stored fact, it appears here so you can review, resolve, or delete it." />
        </h3>
      </div>

      {stale.length === 0 ? (
        <div className="py-4 text-center">
          <CheckCircle size={24} className="text-emerald-400 mx-auto mb-2" />
          <p className="text-xs text-zinc-400">No stale memories detected</p>
        </div>
      ) : (
        <Table>
          <TableHead>
            <TableCell header>Memory</TableCell>
            <TableCell header>Domain</TableCell>
            <TableCell header>Commit</TableCell>
            <TableCell header>Flagged</TableCell>
            <TableCell header>Reason</TableCell>
            <TableCell header>Actions</TableCell>
          </TableHead>
          <TableBody>
            {stale.map((m) => (
              <TableRow key={m.id}>
                <TableCell>
                  <code className="text-[10px] text-zinc-400 font-mono">
                    {m.id.slice(0, 8)}...
                  </code>
                </TableCell>
                <TableCell>
                  <span className="text-xs font-medium text-zinc-700 dark:text-zinc-300">
                    {m.domain || "—"}
                  </span>
                </TableCell>
                <TableCell>
                  <code className="text-[10px] text-violet-400 font-mono">
                    {m.invalidation_flag.commit_hash.slice(0, 7)}
                  </code>
                </TableCell>
                <TableCell>
                  <span className="text-xs text-zinc-500">
                    {relativeTime(m.invalidation_flag.flagged_at)}
                  </span>
                </TableCell>
                <TableCell>
                  <span className="text-xs text-zinc-500 dark:text-zinc-400 max-w-[200px] truncate block">
                    {m.invalidation_flag.reason}
                  </span>
                </TableCell>
                <TableCell>
                  <div className="flex items-center gap-1">
                    {onViewMemory && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => onViewMemory(m.id)}
                        title="View memory"
                      >
                        <Eye size={14} />
                      </Button>
                    )}
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleResolve(m.id)}
                      title="Mark as resolved"
                    >
                      <CheckCircle size={14} className="text-emerald-400" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleDelete(m.id)}
                      title="Delete memory"
                    >
                      <Trash size={14} className="text-red-400" />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </GlassCard>
  );
}
