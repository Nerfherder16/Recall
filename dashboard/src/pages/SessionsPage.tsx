import { useRecallAPI } from "../hooks/useRecallAPI";
import EmptyState from "../components/EmptyState";

interface SessionRow {
  session_id: string;
  started_at: string;
  ended_at: string | null;
  current_task: string | null;
  memories_created: number;
  signals_detected: number;
}

export default function SessionsPage() {
  const { data, loading } = useRecallAPI<{ sessions: SessionRow[] }>(
    "/admin/sessions",
  );

  return (
    <div>
      <h2 className="text-2xl font-bold mb-4">Sessions</h2>

      {loading && <span className="loading loading-spinner" />}

      {!loading && (!data?.sessions || data.sessions.length === 0) && (
        <EmptyState message="No sessions found" />
      )}

      {data?.sessions && data.sessions.length > 0 && (
        <div className="overflow-x-auto">
          <table className="table table-sm">
            <thead>
              <tr>
                <th>Session ID</th>
                <th>Started</th>
                <th>Ended</th>
                <th>Task</th>
                <th>Memories</th>
                <th>Signals</th>
              </tr>
            </thead>
            <tbody>
              {data.sessions.map((s) => (
                <tr key={s.session_id}>
                  <td className="font-mono text-xs">{s.session_id.slice(0, 8)}...</td>
                  <td className="text-xs">{s.started_at}</td>
                  <td className="text-xs">{s.ended_at || "active"}</td>
                  <td className="text-sm max-w-xs truncate">
                    {s.current_task || "-"}
                  </td>
                  <td>{s.memories_created}</td>
                  <td>{s.signals_detected}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
