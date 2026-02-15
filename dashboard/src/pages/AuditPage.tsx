import { useState } from "react";
import { api } from "../api/client";
import Badge from "../components/Badge";
import EmptyState from "../components/EmptyState";

interface AuditEntry {
  id: number;
  timestamp: string;
  action: string;
  memory_id: string;
  actor: string;
  session_id: string | null;
  details: Record<string, unknown>;
}

export default function AuditPage() {
  const [action, setAction] = useState("");
  const [memoryId, setMemoryId] = useState("");
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(false);

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
      <h2 className="text-2xl font-bold mb-4">Audit Log</h2>

      <div className="flex gap-2 mb-4">
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
          className="input input-bordered flex-1"
          placeholder="Memory ID filter"
          value={memoryId}
          onChange={(e) => setMemoryId(e.target.value)}
        />
        <button className="btn btn-primary" onClick={loadAudit}>
          Load
        </button>
      </div>

      {loading && <span className="loading loading-spinner" />}

      {!loading && entries.length === 0 && (
        <EmptyState message="Click Load to view audit entries" />
      )}

      {entries.length > 0 && (
        <div className="overflow-x-auto">
          <table className="table table-xs">
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
                  <td className="text-xs whitespace-nowrap">{e.timestamp}</td>
                  <td>
                    <Badge text={e.action} />
                  </td>
                  <td className="font-mono text-xs">
                    {e.memory_id?.slice(0, 8)}...
                  </td>
                  <td>
                    <Badge text={e.actor} />
                  </td>
                  <td className="text-xs max-w-xs truncate">
                    {JSON.stringify(e.details)}
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
