import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { DomainStat, HealthCheck, Stats } from "../api/types";
import StatCard from "../components/StatCard";
import { useSSE } from "../hooks/useSSE";

export default function DashboardPage() {
  const [health, setHealth] = useState<HealthCheck | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [domains, setDomains] = useState<DomainStat[]>([]);
  const sse = useSSE();

  useEffect(() => {
    api<HealthCheck>("/health").then(setHealth).catch(() => {});
    api<Stats>("/stats").then(setStats).catch(() => {});
    api<{ domains: DomainStat[] }>("/stats/domains")
      .then((d) => setDomains(d.domains))
      .catch(() => {});
  }, []);

  const memCount = sse?.memory_count ?? stats?.memories.total ?? "...";
  const factCount = sse?.fact_count ?? 0;
  const graphNodes = sse?.graph_nodes ?? stats?.memories.graph_nodes ?? "...";
  const relationships =
    sse?.relationships ?? stats?.memories.relationships ?? "...";
  const sessions = sse?.active_sessions ?? stats?.sessions.active ?? "...";

  const svcStatus = (key: string) =>
    sse?.[key as keyof typeof sse] === "ok"
      ? "ok"
      : health?.checks[key]?.startsWith("ok")
        ? "ok"
        : "error";

  return (
    <div>
      <h2 className="text-2xl font-bold mb-4">Dashboard</h2>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <StatCard
          title="Memories"
          value={memCount}
          status={svcStatus("qdrant") as "ok" | "error"}
        />
        <StatCard title="Facts" value={factCount} subtitle="Sub-embeddings" />
        <StatCard
          title="Graph Nodes"
          value={graphNodes}
          status={svcStatus("neo4j") as "ok" | "error"}
        />
        <StatCard title="Relationships" value={relationships} />
        <StatCard
          title="Active Sessions"
          value={sessions}
          status={svcStatus("redis") as "ok" | "error"}
        />
        <StatCard
          title="Audit Entries"
          value={sse?.audit_count ?? "..."}
          status={svcStatus("postgres") as "ok" | "error"}
        />
      </div>

      <div className="card bg-base-100 shadow-sm">
        <div className="card-body">
          <h3 className="card-title text-sm">Service Status</h3>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-2 mt-2">
            {health &&
              Object.entries(health.checks).map(([name, val]) => (
                <div
                  key={name}
                  className={`badge badge-lg gap-1 ${String(val).startsWith("ok") ? "badge-success" : "badge-error"}`}
                >
                  {name}
                </div>
              ))}
          </div>
        </div>
      </div>

      {domains.length > 0 && (
        <div className="card bg-base-100 shadow-sm mt-4">
          <div className="card-body">
            <h3 className="card-title text-sm">Domains</h3>
            <div className="overflow-x-auto">
              <table className="table table-sm">
                <thead>
                  <tr>
                    <th>Domain</th>
                    <th>Count</th>
                    <th>Avg Importance</th>
                  </tr>
                </thead>
                <tbody>
                  {domains.map((d) => (
                    <tr key={d.domain}>
                      <td className="font-mono">{d.domain}</td>
                      <td>{d.count}</td>
                      <td>{d.avg_importance.toFixed(3)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
