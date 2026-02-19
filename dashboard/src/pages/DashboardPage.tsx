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
import { GlassCard } from "../components/common/GlassCard";
import { useSSE } from "../hooks/useSSE";
import { formatBytes } from "../lib/utils";

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

      {/* Stat cards — bento grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
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

      {/* Service status strip */}
      <h3 className="font-mono text-[10px] font-medium uppercase tracking-[0.2em] text-zinc-400 dark:text-zinc-500 mb-3">
        Services
      </h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3 mb-8">
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
        <GlassCard className="p-6 mb-8">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
              LLM Infrastructure
            </h3>
            <span className="inline-flex items-center rounded-full bg-zinc-100 dark:bg-zinc-800 text-zinc-500 dark:text-zinc-400 px-2.5 py-0.5 text-[11px] font-medium ring-1 ring-zinc-200 dark:ring-zinc-700">
              Ollama {ollama.version}
            </span>
          </div>

          {/* Available models */}
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-200 dark:border-white/[0.06]">
                  {[
                    "Model",
                    "Family",
                    "Parameters",
                    "Quantization",
                    "Size",
                    "Status",
                  ].map((h) => (
                    <th
                      key={h}
                      className="text-left py-2 font-mono text-[10px] font-medium uppercase tracking-[0.15em] text-zinc-400 dark:text-zinc-500"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {ollama.models.map((m) => {
                  const running = ollama.running.find((r) => r.name === m.name);
                  return (
                    <tr
                      key={m.name}
                      className="border-b border-zinc-100 dark:border-white/[0.03] last:border-0"
                    >
                      <td className="py-2 font-mono text-sm text-zinc-900 dark:text-zinc-100">
                        {m.name}
                      </td>
                      <td className="py-2 text-xs text-zinc-500 dark:text-zinc-400">
                        {m.family}
                      </td>
                      <td className="py-2 text-xs text-zinc-500 dark:text-zinc-400">
                        {m.parameter_size}
                      </td>
                      <td className="py-2 text-xs text-zinc-500 dark:text-zinc-400">
                        {m.quantization}
                      </td>
                      <td className="py-2 text-xs text-zinc-500 dark:text-zinc-400">
                        {formatBytes(m.size_bytes)}
                      </td>
                      <td className="py-2">
                        {running ? (
                          <span className="inline-flex items-center rounded-full bg-emerald-500/10 text-emerald-400 px-2 py-0.5 text-[11px] font-medium ring-1 ring-emerald-500/20">
                            Loaded
                          </span>
                        ) : (
                          <span className="inline-flex items-center rounded-full bg-zinc-500/10 text-zinc-400 px-2 py-0.5 text-[11px] font-medium ring-1 ring-zinc-500/20">
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
              <h4 className="font-mono text-[10px] font-medium uppercase tracking-[0.2em] text-zinc-400 dark:text-zinc-500 mb-2">
                Active in Memory
              </h4>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {ollama.running.map((r) => (
                  <GlassCard key={r.name} className="p-4">
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-mono text-sm font-medium text-zinc-900 dark:text-zinc-100">
                        {r.name}
                      </span>
                      <span className="inline-flex items-center rounded-full bg-emerald-500/10 text-emerald-400 px-2 py-0.5 text-[11px] font-medium ring-1 ring-emerald-500/20">
                        Running
                      </span>
                    </div>
                    <div className="grid grid-cols-3 gap-2 text-center">
                      {[
                        { label: "RAM", val: formatBytes(r.size_bytes) },
                        {
                          label: "VRAM",
                          val:
                            r.size_vram > 0 ? formatBytes(r.size_vram) : "CPU",
                        },
                        {
                          label: "Context",
                          val: r.context_length.toLocaleString(),
                        },
                      ].map((item) => (
                        <div key={item.label}>
                          <p className="font-mono text-[10px] font-medium uppercase tracking-[0.15em] text-zinc-400 dark:text-zinc-500">
                            {item.label}
                          </p>
                          <p className="text-sm font-semibold tabular-nums text-zinc-900 dark:text-zinc-100">
                            {item.val}
                          </p>
                        </div>
                      ))}
                    </div>
                  </GlassCard>
                ))}
              </div>
            </div>
          )}
        </GlassCard>
      )}

      {/* Domain breakdown */}
      {domains.length > 0 && (
        <GlassCard className="p-6">
          <h3 className="text-sm font-semibold mb-4 text-zinc-900 dark:text-zinc-100">
            Domain Breakdown
          </h3>
          <div className="space-y-3">
            {domains.map((d) => {
              const pct =
                totalDomainCount > 0 ? (d.count / totalDomainCount) * 100 : 0;
              return (
                <div key={d.domain}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-mono text-sm text-zinc-900 dark:text-zinc-100">
                      {d.domain}
                    </span>
                    <span className="text-xs text-zinc-400 dark:text-zinc-500">
                      {d.count} memories &middot; avg imp{" "}
                      {d.avg_importance.toFixed(3)}
                    </span>
                  </div>
                  <div className="w-full bg-violet-500/10 rounded-full h-1.5">
                    <div
                      className="bg-gradient-to-r from-violet-500 to-violet-400 rounded-full h-1.5 transition-all"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </GlassCard>
      )}
    </div>
  );
}
