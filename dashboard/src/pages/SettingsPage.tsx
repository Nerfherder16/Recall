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
      <div className="rounded-xl bg-base-100 border border-base-content/5 p-5 mb-4">
        <h3 className="text-sm font-medium mb-3">API Key</h3>
        <div className="flex gap-2">
          <input
            className="flex-1 rounded-lg border border-base-content/10 bg-base-200 px-3 py-2 text-sm focus:border-primary/50 focus:outline-none"
            type="password"
            value={keyInput}
            onChange={(e) => setKeyInput(e.target.value)}
            placeholder="API Key"
          />
          <button
            className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-content hover:bg-primary/90 transition-colors"
            onClick={() => {
              setApiKey(keyInput || "none");
              addToast("API key saved", "success");
            }}
          >
            Save
          </button>
          <button
            className="rounded-lg px-4 py-2 text-sm hover:bg-base-content/5 transition-colors"
            onClick={() => {
              setApiKey("");
              setKeyInput("");
              addToast("API key cleared", "info");
            }}
          >
            Clear
          </button>
        </div>
      </div>

      {/* Theme */}
      <div className="rounded-xl bg-base-100 border border-base-content/5 p-5 mb-4">
        <h3 className="text-sm font-medium mb-3">Appearance</h3>
        <div className="flex items-center gap-3">
          <span className="text-sm text-base-content/60">Theme:</span>
          <button
            className="flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm hover:bg-base-content/5 transition-colors"
            onClick={toggleTheme}
          >
            {theme === "recall-dark" ? (
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
          </button>
        </div>
      </div>

      {/* Maintenance */}
      <div className="rounded-xl bg-base-100 border border-base-content/5 p-5 mb-4">
        <h3 className="text-sm font-medium mb-3">Maintenance Operations</h3>
        <div className="flex flex-wrap gap-2">
          {opButtons.map((op) => (
            <button
              key={op.name}
              className="flex items-center gap-1.5 rounded-lg border border-base-content/10 px-3 py-1.5 text-sm hover:bg-base-content/5 transition-colors disabled:opacity-50"
              onClick={() => runOp(op.name, op.endpoint, op.method || "POST")}
              disabled={!!opLoading}
            >
              {opLoading === op.name ? (
                <div className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-base-content/10 border-t-primary" />
              ) : (
                op.icon
              )}
              {op.name}
            </button>
          ))}
        </div>
      </div>

      {/* Connection Status */}
      {health && (
        <div className="rounded-xl bg-base-100 border border-base-content/5 p-5 mb-4">
          <h3 className="text-sm font-medium mb-3">Connection Status</h3>
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
        </div>
      )}

      {/* System Info */}
      <div className="rounded-xl bg-base-100 border border-base-content/5 p-5">
        <h3 className="text-sm font-medium mb-3">System Info</h3>
        <div className="text-sm space-y-1.5">
          <p>
            <span className="text-base-content/40">Status:</span>{" "}
            {health?.status || "unknown"}
          </p>
          <p>
            <span className="text-base-content/40">Timestamp:</span>{" "}
            {health?.timestamp || "unknown"}
          </p>
          <p>
            <span className="text-base-content/40">Dashboard:</span> Recall
            v0.3.0 (Phase 14)
          </p>
        </div>
      </div>
    </div>
  );
}
