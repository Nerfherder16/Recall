import { useState } from "react";
import { api } from "../api/client";
import Badge from "../components/Badge";
import EmptyState from "../components/EmptyState";

interface Signal {
  signal_type: string;
  content: string;
  confidence: number;
  domain: string;
  tags: string[];
}

export default function SignalsPage() {
  const [sessionId, setSessionId] = useState("");
  const [signals, setSignals] = useState<Signal[]>([]);
  const [loading, setLoading] = useState(false);

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
    } catch {}
  }

  return (
    <div>
      <h2 className="text-2xl font-bold mb-4">Pending Signals</h2>

      <div className="flex gap-2 mb-4">
        <input
          className="input input-bordered flex-1"
          placeholder="Session ID"
          value={sessionId}
          onChange={(e) => setSessionId(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && loadSignals()}
        />
        <button className="btn btn-primary" onClick={loadSignals}>
          Load
        </button>
        {signals.length > 0 && (
          <button className="btn btn-success" onClick={approveAll}>
            Approve All
          </button>
        )}
      </div>

      {signals.length === 0 && !loading && (
        <EmptyState message="Enter a session ID to view pending signals" />
      )}

      <div className="flex flex-col gap-2">
        {signals.map((s, i) => (
          <div key={i} className="card bg-base-100 shadow-sm">
            <div className="card-body p-4">
              <div className="flex gap-2 items-center mb-1">
                <Badge text={s.signal_type} />
                <span className="text-xs text-base-content/50">
                  {s.domain}
                </span>
                <div className="flex-1" />
                <span className="text-xs">
                  Confidence: {(s.confidence * 100).toFixed(0)}%
                </span>
              </div>
              <p className="text-sm">{s.content}</p>
              {s.tags.length > 0 && (
                <div className="flex gap-1 mt-1">
                  {s.tags.map((t) => (
                    <span key={t} className="badge badge-xs badge-ghost">
                      {t}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
