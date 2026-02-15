import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { DomainStat, HealthCheck, Stats } from "../api/types";
import PageHeader from "../components/PageHeader";
import StatCard from "../components/StatCard";
import ServiceStatusCard from "../components/ServiceStatusCard";
import LoadingSpinner from "../components/LoadingSpinner";
import { useSSE } from "../hooks/useSSE";

const serviceIcons: Record<string, string> = {
  qdrant:
    "M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4",
  neo4j:
    "M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1",
  redis:
    "M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01",
  postgres:
    "M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4",
  ollama:
    "M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z",
};

interface OllamaModel {
  name: string;
  parameter_size: string;
  quantization: string;
  family: string;
  size_bytes: number;
}

interface OllamaRunning {
  name: string;
  size_bytes: number;
  size_vram: number;
  context_length: number;
  expires_at: string;
}

interface OllamaInfo {
  version: string;
  models: OllamaModel[];
  running: OllamaRunning[];
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const gb = bytes / (1024 * 1024 * 1024);
  if (gb >= 1) return `${gb.toFixed(1)} GB`;
  const mb = bytes / (1024 * 1024);
  return `${mb.toFixed(0)} MB`;
}

export default function DashboardPage() {
  const [health, setHealth] = useState<HealthCheck | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [domains, setDomains] = useState<DomainStat[]>([]);
  const [ollama, setOllama] = useState<OllamaInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const sse = useSSE();

  useEffect(() => {
    Promise.all([
      api<HealthCheck>("/health")
        .then(setHealth)
        .catch(() => {}),
      api<Stats>("/stats")
        .then(setStats)
        .catch(() => {}),
      api<{ domains: DomainStat[] }>("/stats/domains")
        .then((d) => setDomains(d.domains))
        .catch(() => {}),
      api<OllamaInfo>("/admin/ollama")
        .then(setOllama)
        .catch(() => {}),
    ]).finally(() => setLoading(false));
  }, []);

  if (loading) return <LoadingSpinner />;

  const memCount = sse?.memory_count ?? stats?.memories.total ?? 0;
  const factCount = sse?.fact_count ?? 0;
  const graphNodes = sse?.graph_nodes ?? stats?.memories.graph_nodes ?? 0;
  const relationships =
    sse?.relationships ?? stats?.memories.relationships ?? 0;
  const sessions = sse?.active_sessions ?? stats?.sessions.active ?? 0;
  const auditCount = sse?.audit_count ?? 0;

  const svcStatus = (key: string): "ok" | "error" => {
    const sseVal = sse?.[key as keyof typeof sse];
    if (typeof sseVal === "string" && sseVal.startsWith("ok")) return "ok";
    if (health?.checks[key]?.startsWith("ok")) return "ok";
    return "error";
  };

  const svcDetail = (key: string): string => {
    const sseVal = sse?.[key as keyof typeof sse];
    if (typeof sseVal === "string") return sseVal;
    return health?.checks[key] ?? "unknown";
  };

  const totalDomainCount = domains.reduce((s, d) => s + d.count, 0);

  return (
    <div>
      <PageHeader title="Dashboard" subtitle="System overview and health" />

      {/* Stat cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <StatCard
          title="Memories"
          value={memCount}
          status={svcStatus("qdrant")}
        />
        <StatCard title="Facts" value={factCount} subtitle="Sub-embeddings" />
        <StatCard
          title="Graph Nodes"
          value={graphNodes}
          status={svcStatus("neo4j")}
        />
        <StatCard title="Relationships" value={relationships} />
        <StatCard
          title="Active Sessions"
          value={sessions}
          status={svcStatus("redis")}
        />
        <StatCard
          title="Audit Entries"
          value={auditCount}
          status={svcStatus("postgres")}
        />
        <StatCard title="Domains" value={domains.length} />
        <StatCard
          title="Status"
          value={health?.status === "healthy" ? "Healthy" : "Degraded"}
          status={health?.status === "healthy" ? "ok" : "error"}
        />
      </div>

      {/* Service status panels */}
      <h3 className="text-sm font-semibold uppercase text-base-content/50 mb-3">
        Services
      </h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3 mb-6">
        {["qdrant", "neo4j", "redis", "postgres", "ollama"].map((svc) => (
          <ServiceStatusCard
            key={svc}
            name={svc.charAt(0).toUpperCase() + svc.slice(1)}
            status={svcDetail(svc)}
            icon={serviceIcons[svc]}
          />
        ))}
      </div>

      {/* Ollama / LLM Info */}
      {ollama && (
        <div className="card bg-base-100 shadow-sm mb-6">
          <div className="card-body">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-semibold text-sm">LLM Infrastructure</h3>
              <span className="badge badge-sm badge-ghost">
                Ollama {ollama.version}
              </span>
            </div>

            {/* Available models */}
            <div className="overflow-x-auto">
              <table className="table table-sm">
                <thead>
                  <tr>
                    <th>Model</th>
                    <th>Family</th>
                    <th>Parameters</th>
                    <th>Quantization</th>
                    <th>Size</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {ollama.models.map((m) => {
                    const running = ollama.running.find(
                      (r) => r.name === m.name,
                    );
                    return (
                      <tr key={m.name}>
                        <td className="font-mono text-sm">{m.name}</td>
                        <td className="text-xs">{m.family}</td>
                        <td className="text-xs">{m.parameter_size}</td>
                        <td className="text-xs">{m.quantization}</td>
                        <td className="text-xs">{formatBytes(m.size_bytes)}</td>
                        <td>
                          {running ? (
                            <span className="badge badge-sm badge-success">
                              Loaded
                            </span>
                          ) : (
                            <span className="badge badge-sm badge-ghost">
                              Idle
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Running models with VRAM */}
            {ollama.running.length > 0 && (
              <div className="mt-3">
                <h4 className="text-xs font-semibold uppercase text-base-content/50 mb-2">
                  Active in Memory
                </h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  {ollama.running.map((r) => (
                    <div key={r.name} className="bg-base-200 rounded-lg p-3">
                      <div className="flex items-center justify-between mb-2">
                        <span className="font-mono text-sm font-semibold">
                          {r.name}
                        </span>
                        <span className="badge badge-sm badge-success">
                          Running
                        </span>
                      </div>
                      <div className="grid grid-cols-3 gap-2 text-center">
                        <div>
                          <p className="text-xs text-base-content/50">RAM</p>
                          <p className="text-sm font-bold">
                            {formatBytes(r.size_bytes)}
                          </p>
                        </div>
                        <div>
                          <p className="text-xs text-base-content/50">VRAM</p>
                          <p className="text-sm font-bold">
                            {r.size_vram > 0 ? formatBytes(r.size_vram) : "CPU"}
                          </p>
                        </div>
                        <div>
                          <p className="text-xs text-base-content/50">
                            Context
                          </p>
                          <p className="text-sm font-bold">
                            {r.context_length.toLocaleString()}
                          </p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Domain breakdown */}
      {domains.length > 0 && (
        <div className="card bg-base-100 shadow-sm">
          <div className="card-body">
            <h3 className="font-semibold text-sm mb-3">Domain Breakdown</h3>
            <div className="space-y-3">
              {domains.map((d) => {
                const pct =
                  totalDomainCount > 0 ? (d.count / totalDomainCount) * 100 : 0;
                return (
                  <div key={d.domain}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-mono text-sm">{d.domain}</span>
                      <span className="text-xs text-base-content/50">
                        {d.count} memories &middot; avg imp{" "}
                        {d.avg_importance.toFixed(3)}
                      </span>
                    </div>
                    <div className="w-full bg-base-300 rounded-full h-2">
                      <div
                        className="bg-primary rounded-full h-2 transition-all"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
