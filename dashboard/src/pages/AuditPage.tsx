import { useState, useEffect } from "react";
import { api } from "../api/client";
import Badge from "../components/Badge";
import EmptyState from "../components/EmptyState";
import PageHeader from "../components/PageHeader";
import LoadingSpinner from "../components/LoadingSpinner";

interface AuditEntry {
  id: number;
  timestamp: string;
  action: string;
  memory_id: string;
  actor: string;
  session_id: string | null;
  details: Record<string, unknown>;
}

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

function DetailBadges({
  details,
}: {
  details: Record<string, unknown> | null;
}) {
  if (!details) return <span className="text-xs text-base-content/40">-</span>;
  const entries = Object.entries(details).filter(
    ([, v]) => v !== null && v !== undefined && v !== "",
  );
  if (entries.length === 0)
    return <span className="text-xs text-base-content/40">-</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {entries.slice(0, 4).map(([k, v]) => (
        <span key={k} className="badge badge-sm badge-ghost">
          {k}: {typeof v === "object" ? JSON.stringify(v) : String(v)}
        </span>
      ))}
      {entries.length > 4 && (
        <span className="badge badge-sm badge-ghost">
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

  // Auto-load on mount
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
        <select
          className="select select-bordered w-40"
          value={action}
          onChange={(e) => setAction(e.target.value)}
        >
          <option value="">All actions</option>
          <option value="create">Create</option>
          <option value="delete">Delete</option>
          <option value="update">Update</option>
          <option value="consolidation">Consolidation</option>
          <option value="decay">Decay</option>
        </select>
        <input
          className="input input-bordered flex-1 min-w-48"
          placeholder="Memory ID filter"
          value={memoryId}
          onChange={(e) => setMemoryId(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && loadAudit()}
        />
        <button className="btn btn-primary" onClick={loadAudit}>
          Filter
        </button>
      </div>

      {loading && <LoadingSpinner />}

      {!loading && entries.length === 0 && (
        <EmptyState message="No audit entries found" />
      )}

      {!loading && entries.length > 0 && (
        <div className="overflow-x-auto">
          <table className="table table-sm">
            <thead>
              <tr>
                <th>Time</th>
                <th>Action</th>
                <th>Memory</th>
                <th>Actor</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => (
                <tr key={e.id}>
                  <td className="text-xs whitespace-nowrap" title={e.timestamp}>
                    {timeAgo(e.timestamp)}
                  </td>
                  <td>
                    <Badge text={e.action} />
                  </td>
                  <td className="font-mono text-xs">
                    {e.memory_id ? `${e.memory_id.slice(0, 8)}...` : "-"}
                  </td>
                  <td>
                    <Badge text={e.actor} />
                  </td>
                  <td>
                    <DetailBadges details={e.details} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
