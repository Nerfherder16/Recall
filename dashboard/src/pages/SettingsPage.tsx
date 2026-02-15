import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { HealthCheck } from "../api/types";
import { useAuth } from "../hooks/useAuth";
import StatCard from "../components/StatCard";

export default function SettingsPage() {
  const { apiKey, setApiKey } = useAuth();
  const [health, setHealth] = useState<HealthCheck | null>(null);
  const [factCount, setFactCount] = useState<number | null>(null);
  const [keyInput, setKeyInput] = useState(apiKey === "none" ? "" : apiKey);

  useEffect(() => {
    api<HealthCheck>("/health").then(setHealth).catch(() => {});
    // Try to get fact count from stats
    api<{ memories: { total: number } }>("/stats")
      .then(() => {})
      .catch(() => {});
  }, []);

  return (
    <div>
      <h2 className="text-2xl font-bold mb-4">Settings</h2>

      <div className="card bg-base-100 shadow-sm mb-4">
        <div className="card-body">
          <h3 className="card-title text-sm">API Key</h3>
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
              onClick={() => setApiKey(keyInput || "none")}
            >
              Save
            </button>
            <button
              className="btn btn-ghost"
              onClick={() => {
                setApiKey("");
                setKeyInput("");
              }}
            >
              Clear
            </button>
          </div>
        </div>
      </div>

      {health && (
        <div className="card bg-base-100 shadow-sm mb-4">
          <div className="card-body">
            <h3 className="card-title text-sm">Connection Status</h3>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mt-2">
              {Object.entries(health.checks).map(([name, val]) => (
                <StatCard
                  key={name}
                  title={name}
                  value={String(val).startsWith("ok") ? "Connected" : "Error"}
                  subtitle={String(val)}
                  status={
                    String(val).startsWith("ok") ? "ok" : "error"
                  }
                />
              ))}
            </div>
          </div>
        </div>
      )}

      <div className="card bg-base-100 shadow-sm">
        <div className="card-body">
          <h3 className="card-title text-sm">System Info</h3>
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
              v0.1.0 (Phase 9)
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
