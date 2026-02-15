import { useEffect, useState } from "react";
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

  return (
    <div>
      <PageHeader title="Settings" subtitle="Configuration and maintenance" />

      {/* API Key */}
      <div className="card bg-base-100 shadow-sm mb-4">
        <div className="card-body">
          <h3 className="font-semibold text-sm mb-2">API Key</h3>
          <div className="flex gap-2">
            <input
              className="input input-bordered flex-1"
              type="password"
              value={keyInput}
              onChange={(e) => setKeyInput(e.target.value)}
              placeholder="API Key"
            />
            <button
              className="btn btn-primary"
              onClick={() => {
                setApiKey(keyInput || "none");
                addToast("API key saved", "success");
              }}
            >
              Save
            </button>
            <button
              className="btn btn-ghost"
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
      </div>

      {/* Theme */}
      <div className="card bg-base-100 shadow-sm mb-4">
        <div className="card-body">
          <h3 className="font-semibold text-sm mb-2">Appearance</h3>
          <div className="flex items-center gap-3">
            <span className="text-sm">Theme:</span>
            <button
              className="btn btn-sm btn-ghost gap-2"
              onClick={toggleTheme}
            >
              {theme === "dark" ? (
                <>
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    className="h-4 w-4"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z"
                    />
                  </svg>
                  Switch to Light
                </>
              ) : (
                <>
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    className="h-4 w-4"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"
                    />
                  </svg>
                  Switch to Dark
                </>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Maintenance */}
      <div className="card bg-base-100 shadow-sm mb-4">
        <div className="card-body">
          <h3 className="font-semibold text-sm mb-2">Maintenance Operations</h3>
          <div className="flex flex-wrap gap-2">
            <button
              className={`btn btn-sm ${opLoading === "Consolidation" ? "loading" : ""}`}
              onClick={() => runOp("Consolidation", "/admin/consolidation/run")}
              disabled={!!opLoading}
            >
              Run Consolidation
            </button>
            <button
              className={`btn btn-sm ${opLoading === "Decay" ? "loading" : ""}`}
              onClick={() => runOp("Decay", "/admin/decay/run")}
              disabled={!!opLoading}
            >
              Run Decay
            </button>
            <button
              className={`btn btn-sm ${opLoading === "Reconcile" ? "loading" : ""}`}
              onClick={() =>
                runOp("Reconcile", "/admin/reconcile?dry_run=true", "GET")
              }
              disabled={!!opLoading}
            >
              Reconcile (dry run)
            </button>
            <button
              className={`btn btn-sm ${opLoading === "Export" ? "loading" : ""}`}
              onClick={() => runOp("Export", "/admin/export", "GET")}
              disabled={!!opLoading}
            >
              Export
            </button>
          </div>
        </div>
      </div>

      {/* Connection Status */}
      {health && (
        <div className="card bg-base-100 shadow-sm mb-4">
          <div className="card-body">
            <h3 className="font-semibold text-sm mb-2">Connection Status</h3>
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
        </div>
      )}

      {/* System Info */}
      <div className="card bg-base-100 shadow-sm">
        <div className="card-body">
          <h3 className="font-semibold text-sm mb-2">System Info</h3>
          <div className="text-sm space-y-1">
            <p>
              <span className="text-base-content/50">Status:</span>{" "}
              {health?.status || "unknown"}
            </p>
            <p>
              <span className="text-base-content/50">Timestamp:</span>{" "}
              {health?.timestamp || "unknown"}
            </p>
            <p>
              <span className="text-base-content/50">Dashboard:</span> Recall
              v0.2.0 (Phase 10)
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
