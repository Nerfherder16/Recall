import { useEffect, useState } from "react";
import {
  Sun,
  Moon,
  ArrowsClockwise,
  Timer,
  Scales,
  Export,
} from "@phosphor-icons/react";
import { api } from "../api/client";
import type { HealthCheck } from "../api/types";
import { useAuth } from "../hooks/useAuth";
import { useThemeContext } from "../context/ThemeContext";
import { useToastContext } from "../context/ToastContext";
import PageHeader from "../components/PageHeader";
import StatCard from "../components/StatCard";
import { GlassCard } from "../components/common/GlassCard";
import { Button } from "../components/common/Button";
import { Input } from "../components/common/Input";

export default function SettingsPage() {
  const { apiKey, setApiKey } = useAuth();
  const { theme, toggle: toggleTheme } = useThemeContext();
  const { addToast } = useToastContext();
  const [health, setHealth] = useState<HealthCheck | null>(null);
  const [keyInput, setKeyInput] = useState(apiKey === "none" ? "" : apiKey);
  const [opLoading, setOpLoading] = useState<string | null>(null);

  useEffect(() => {
    api<HealthCheck>("/health")
      .then(setHealth)
      .catch(() => {});
  }, []);

  async function runOp(name: string, endpoint: string, method = "POST") {
    setOpLoading(name);
    try {
      const res = await api<Record<string, unknown>>(endpoint, method);
      addToast(`${name}: ${JSON.stringify(res).slice(0, 80)}`, "success");
    } catch (e) {
      addToast(
        `${name} failed: ${e instanceof Error ? e.message : "unknown error"}`,
        "error",
      );
    } finally {
      setOpLoading(null);
    }
  }

  const opButtons = [
    {
      name: "Consolidation",
      endpoint: "/admin/consolidation/run",
      icon: <ArrowsClockwise size={14} />,
    },
    {
      name: "Decay",
      endpoint: "/admin/decay/run",
      icon: <Timer size={14} />,
    },
    {
      name: "Reconcile",
      endpoint: "/admin/reconcile?dry_run=true",
      method: "GET",
      icon: <Scales size={14} />,
    },
    {
      name: "Export",
      endpoint: "/admin/export",
      method: "GET",
      icon: <Export size={14} />,
    },
  ];

  return (
    <div>
      <PageHeader title="Settings" subtitle="Configuration and maintenance" />

      {/* API Key */}
      <GlassCard className="p-6 mb-4">
        <h3 className="text-sm font-semibold mb-3 text-zinc-900 dark:text-zinc-100">
          API Key
        </h3>
        <div className="flex gap-2">
          <Input
            type="password"
            value={keyInput}
            onChange={(e) => setKeyInput(e.target.value)}
            placeholder="API Key"
            containerClass="flex-1"
          />
          <Button
            onClick={() => {
              setApiKey(keyInput || "none");
              addToast("API key saved", "success");
            }}
          >
            Save
          </Button>
          <Button
            variant="ghost"
            onClick={() => {
              setApiKey("");
              setKeyInput("");
              addToast("API key cleared", "info");
            }}
          >
            Clear
          </Button>
        </div>
      </GlassCard>

      {/* Theme */}
      <GlassCard className="p-6 mb-4">
        <h3 className="text-sm font-semibold mb-3 text-zinc-900 dark:text-zinc-100">
          Appearance
        </h3>
        <div className="flex items-center gap-3">
          <span className="text-sm text-zinc-500 dark:text-zinc-400">
            Theme:
          </span>
          <Button variant="ghost" size="sm" onClick={toggleTheme}>
            {theme === "dark" ? (
              <>
                <Sun size={16} />
                Switch to Light
              </>
            ) : (
              <>
                <Moon size={16} />
                Switch to Dark
              </>
            )}
          </Button>
        </div>
      </GlassCard>

      {/* Maintenance */}
      <GlassCard className="p-6 mb-4">
        <h3 className="text-sm font-semibold mb-3 text-zinc-900 dark:text-zinc-100">
          Maintenance Operations
        </h3>
        <div className="flex flex-wrap gap-2">
          {opButtons.map((op) => (
            <Button
              key={op.name}
              variant="secondary"
              size="sm"
              onClick={() => runOp(op.name, op.endpoint, op.method || "POST")}
              disabled={!!opLoading}
              loading={opLoading === op.name}
            >
              {opLoading !== op.name && op.icon}
              {op.name}
            </Button>
          ))}
        </div>
      </GlassCard>

      {/* Connection Status */}
      {health && (
        <GlassCard className="p-6 mb-4">
          <h3 className="text-sm font-semibold mb-3 text-zinc-900 dark:text-zinc-100">
            Connection Status
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {Object.entries(health.checks).map(([name, val]) => (
              <StatCard
                key={name}
                title={name}
                value={String(val).startsWith("ok") ? "Connected" : "Error"}
                subtitle={String(val)}
                status={String(val).startsWith("ok") ? "ok" : "error"}
              />
            ))}
          </div>
        </GlassCard>
      )}

      {/* System Info */}
      <GlassCard className="p-6">
        <h3 className="text-sm font-semibold mb-3 text-zinc-900 dark:text-zinc-100">
          System Info
        </h3>
        <div className="text-sm space-y-1.5">
          <p>
            <span className="text-zinc-400 dark:text-zinc-500">Status:</span>{" "}
            <span className="text-zinc-700 dark:text-zinc-300">
              {health?.status || "unknown"}
            </span>
          </p>
          <p>
            <span className="text-zinc-400 dark:text-zinc-500">Timestamp:</span>{" "}
            <span className="font-mono text-zinc-700 dark:text-zinc-300">
              {health?.timestamp || "unknown"}
            </span>
          </p>
          <p>
            <span className="text-zinc-400 dark:text-zinc-500">Dashboard:</span>{" "}
            <span className="text-zinc-700 dark:text-zinc-300">
              Recall v0.3.0
            </span>
          </p>
        </div>
      </GlassCard>
    </div>
  );
}
