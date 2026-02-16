import { useEffect, useState } from "react";
import {
  Database,
  TreeStructure,
  Lightning,
  Table,
  Cpu,
} from "@phosphor-icons/react";
import { api } from "../api/client";
import type { DomainStat, HealthCheck, Stats } from "../api/types";
import PageHeader from "../components/PageHeader";
import StatCard from "../components/StatCard";
import ServiceStatusCard from "../components/ServiceStatusCard";
import LoadingSpinner from "../components/LoadingSpinner";
import { useSSE } from "../hooks/useSSE";

const serviceIcons: Record<string, React.ReactNode> = {
  qdrant: <Database size={20} />,
  neo4j: <TreeStructure size={20} />,
  redis: <Lightning size={20} />,
  postgres: <Table size={20} />,
  ollama: <Cpu size={20} />,
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
      <h3 className="text-[11px] font-medium uppercase tracking-wider text-base-content/40 mb-3">
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
        <div className="rounded-xl bg-base-100 border border-base-content/5 p-5 mb-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-medium">LLM Infrastructure</h3>
            <span className="inline-flex items-center rounded-md bg-zinc-500/10 text-zinc-400 px-2 py-0.5 text-[11px] font-medium">
              Ollama {ollama.version}
            </span>
          </div>

          {/* Available models */}
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-base-content/5">
                  <th className="text-left py-2 text-[11px] font-medium uppercase tracking-wider text-base-content/40">
                    Model
                  </th>
                  <th className="text-left py-2 text-[11px] font-medium uppercase tracking-wider text-base-content/40">
                    Family
                  </th>
                  <th className="text-left py-2 text-[11px] font-medium uppercase tracking-wider text-base-content/40">
                    Parameters
                  </th>
                  <th className="text-left py-2 text-[11px] font-medium uppercase tracking-wider text-base-content/40">
                    Quantization
                  </th>
                  <th className="text-left py-2 text-[11px] font-medium uppercase tracking-wider text-base-content/40">
                    Size
                  </th>
                  <th className="text-left py-2 text-[11px] font-medium uppercase tracking-wider text-base-content/40">
                    Status
                  </th>
                </tr>
              </thead>
              <tbody>
                {ollama.models.map((m) => {
                  const running = ollama.running.find((r) => r.name === m.name);
                  return (
                    <tr
                      key={m.name}
                      className="border-b border-base-content/5 last:border-0"
                    >
                      <td className="py-2 font-mono text-sm">{m.name}</td>
                      <td className="py-2 text-xs text-base-content/60">
                        {m.family}
                      </td>
                      <td className="py-2 text-xs text-base-content/60">
                        {m.parameter_size}
                      </td>
                      <td className="py-2 text-xs text-base-content/60">
                        {m.quantization}
                      </td>
                      <td className="py-2 text-xs text-base-content/60">
                        {formatBytes(m.size_bytes)}
                      </td>
                      <td className="py-2">
                        {running ? (
                          <span className="inline-flex items-center rounded-md bg-emerald-500/10 text-emerald-400 px-2 py-0.5 text-[11px] font-medium">
                            Loaded
                          </span>
                        ) : (
                          <span className="inline-flex items-center rounded-md bg-zinc-500/10 text-zinc-400 px-2 py-0.5 text-[11px] font-medium">
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
            <div className="mt-4">
              <h4 className="text-[11px] font-medium uppercase tracking-wider text-base-content/40 mb-2">
                Active in Memory
              </h4>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {ollama.running.map((r) => (
                  <div
                    key={r.name}
                    className="rounded-lg bg-base-200 border border-base-content/5 p-3"
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-mono text-sm font-medium">
                        {r.name}
                      </span>
                      <span className="inline-flex items-center rounded-md bg-emerald-500/10 text-emerald-400 px-2 py-0.5 text-[11px] font-medium">
                        Running
                      </span>
                    </div>
                    <div className="grid grid-cols-3 gap-2 text-center">
                      <div>
                        <p className="text-[11px] font-medium uppercase tracking-wider text-base-content/40">
                          RAM
                        </p>
                        <p className="text-sm font-semibold tabular-nums">
                          {formatBytes(r.size_bytes)}
                        </p>
                      </div>
                      <div>
                        <p className="text-[11px] font-medium uppercase tracking-wider text-base-content/40">
                          VRAM
                        </p>
                        <p className="text-sm font-semibold tabular-nums">
                          {r.size_vram > 0 ? formatBytes(r.size_vram) : "CPU"}
                        </p>
                      </div>
                      <div>
                        <p className="text-[11px] font-medium uppercase tracking-wider text-base-content/40">
                          Context
                        </p>
                        <p className="text-sm font-semibold tabular-nums">
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
      )}

      {/* Domain breakdown */}
      {domains.length > 0 && (
        <div className="rounded-xl bg-base-100 border border-base-content/5 p-5">
          <h3 className="text-sm font-medium mb-4">Domain Breakdown</h3>
          <div className="space-y-3">
            {domains.map((d) => {
              const pct =
                totalDomainCount > 0 ? (d.count / totalDomainCount) * 100 : 0;
              return (
                <div key={d.domain}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-mono text-sm">{d.domain}</span>
                    <span className="text-xs text-base-content/40">
                      {d.count} memories &middot; avg imp{" "}
                      {d.avg_importance.toFixed(3)}
                    </span>
                  </div>
                  <div className="w-full bg-primary/10 rounded-full h-1.5">
                    <div
                      className="bg-primary rounded-full h-1.5 transition-all"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
