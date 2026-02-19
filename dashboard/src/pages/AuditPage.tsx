import { useState, useEffect } from "react";
import { Funnel } from "@phosphor-icons/react";
import { api } from "../api/client";
import Badge from "../components/Badge";
import EmptyState from "../components/EmptyState";
import PageHeader from "../components/PageHeader";
import LoadingSpinner from "../components/LoadingSpinner";
import { GlassCard } from "../components/common/GlassCard";
import { Button } from "../components/common/Button";
import { Input, Select } from "../components/common/Input";
import { timeAgo } from "../lib/utils";

interface AuditEntry {
  id: number;
  timestamp: string;
  action: string;
  memory_id: string;
  actor: string;
  session_id: string | null;
  details: Record<string, unknown>;
}

function DetailBadges({
  details,
}: {
  details: Record<string, unknown> | null;
}) {
  if (!details)
    return <span className="text-xs text-zinc-400 dark:text-zinc-600">-</span>;
  const entries = Object.entries(details).filter(
    ([, v]) => v !== null && v !== undefined && v !== "",
  );
  if (entries.length === 0)
    return <span className="text-xs text-zinc-400 dark:text-zinc-600">-</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {entries.slice(0, 4).map(([k, v]) => (
        <span
          key={k}
          className="inline-flex items-center rounded-full bg-zinc-500/10 text-zinc-400 px-1.5 py-0.5 text-[10px] font-medium ring-1 ring-zinc-500/20"
        >
          {k}: {typeof v === "object" ? JSON.stringify(v) : String(v)}
        </span>
      ))}
      {entries.length > 4 && (
        <span className="inline-flex items-center rounded-full bg-zinc-500/10 text-zinc-400 px-1.5 py-0.5 text-[10px] font-medium ring-1 ring-zinc-500/20">
          +{entries.length - 4}
        </span>
      )}
    </div>
  );
}

export default function AuditPage() {
  const [action, setAction] = useState("");
  const [memoryId, setMemoryId] = useState("");
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    loadAudit();
  }, []);

  async function loadAudit() {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (action) params.set("action", action);
      if (memoryId) params.set("memory_id", memoryId);
      params.set("limit", "100");
      const res = await api<{ entries: AuditEntry[] }>(
        `/admin/audit?${params}`,
      );
      setEntries(res.entries || []);
    } catch {
      setEntries([]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <PageHeader title="Audit Log" subtitle="Memory mutation history" />

      <div className="flex flex-wrap gap-2 mb-4">
        <Select
          containerClass="w-40"
          value={action}
          onChange={(e) => setAction(e.target.value)}
        >
          <option value="">All actions</option>
          <option value="create">Create</option>
          <option value="delete">Delete</option>
          <option value="update">Update</option>
          <option value="consolidation">Consolidation</option>
          <option value="decay">Decay</option>
        </Select>
        <Input
          containerClass="flex-1 min-w-48"
          placeholder="Memory ID filter"
          value={memoryId}
          onChange={(e) => setMemoryId(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && loadAudit()}
        />
        <Button onClick={loadAudit}>
          <Funnel size={16} />
          Filter
        </Button>
      </div>

      {loading && <LoadingSpinner />}

      {!loading && entries.length === 0 && (
        <EmptyState message="No audit entries found" />
      )}

      {!loading && entries.length > 0 && (
        <GlassCard className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-200 dark:border-white/[0.06]">
                  {["Time", "Action", "Memory", "Actor", "Details"].map((h) => (
                    <th
                      key={h}
                      className="text-left px-4 py-2.5 font-mono text-[10px] font-medium uppercase tracking-[0.15em] text-zinc-400 dark:text-zinc-500"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {entries.map((e) => (
                  <tr
                    key={e.id}
                    className="border-b border-zinc-100 dark:border-white/[0.03] last:border-0"
                  >
                    <td
                      className="px-4 py-2.5 text-xs whitespace-nowrap text-zinc-500 dark:text-zinc-400"
                      title={e.timestamp}
                    >
                      {timeAgo(e.timestamp)}
                    </td>
                    <td className="px-4 py-2.5">
                      <Badge text={e.action} />
                    </td>
                    <td className="px-4 py-2.5 font-mono text-xs text-zinc-500 dark:text-zinc-400">
                      {e.memory_id ? `${e.memory_id.slice(0, 8)}...` : "-"}
                    </td>
                    <td className="px-4 py-2.5">
                      <Badge text={e.actor} />
                    </td>
                    <td className="px-4 py-2.5">
                      <DetailBadges details={e.details} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </GlassCard>
      )}
    </div>
  );
}
