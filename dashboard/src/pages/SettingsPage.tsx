import { useCallback, useEffect, useState } from "react";
import {
  Sun,
  Moon,
  ArrowsClockwise,
  Timer,
  Scales,
  Export,
  Brain,
  Lightning,
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

interface MLModelStatus {
  status: string;
  trained_at?: string;
  n_samples?: number;
  binary_cv_score?: number;
  type_cv_score?: number;
  cv_score?: number;
  vocab_size?: number;
  type_classes?: string[];
  features?: string[];
  class_distribution?: Record<string, number>;
  type_distribution?: Record<string, number>;
}

export default function SettingsPage() {
  const { apiKey, setApiKey } = useAuth();
  const { theme, toggle: toggleTheme } = useThemeContext();
  const { addToast } = useToastContext();
  const [health, setHealth] = useState<HealthCheck | null>(null);
  const [keyInput, setKeyInput] = useState(apiKey === "none" ? "" : apiKey);
  const [opLoading, setOpLoading] = useState<string | null>(null);
  const [classifierStatus, setClassifierStatus] =
    useState<MLModelStatus | null>(null);
  const [rerankerStatus, setRerankerStatus] = useState<MLModelStatus | null>(
    null,
  );

  const loadMLStatus = useCallback(() => {
    api<MLModelStatus>("/admin/ml/signal-classifier-status", "GET")
      .then(setClassifierStatus)
      .catch(() => setClassifierStatus(null));
    api<MLModelStatus>("/admin/ml/reranker-status", "GET")
      .then(setRerankerStatus)
      .catch(() => setRerankerStatus(null));
  }, []);

  useEffect(() => {
    api<HealthCheck>("/health")
      .then(setHealth)
      .catch(() => {});
    loadMLStatus();
  }, [loadMLStatus]);

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

      {/* ML Models */}
      <GlassCard className="p-6 mb-4">
        <h3 className="text-sm font-semibold mb-3 text-zinc-900 dark:text-zinc-100">
          ML Models
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Signal Classifier */}
          <div className="rounded-lg border border-zinc-200 dark:border-zinc-700 p-4">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <Brain size={16} className="text-violet-500" />
                <span className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
                  Signal Classifier
                </span>
              </div>
              <span
                className={`text-xs px-2 py-0.5 rounded-full ${
                  classifierStatus?.status === "trained"
                    ? "bg-emerald-500/10 text-emerald-400"
                    : "bg-zinc-500/10 text-zinc-400"
                }`}
              >
                {classifierStatus?.status || "unknown"}
              </span>
            </div>
            {classifierStatus?.status === "trained" && (
              <div className="text-xs space-y-1 text-zinc-500 dark:text-zinc-400 mb-3">
                <p>
                  Samples: {classifierStatus.n_samples} | Vocab:{" "}
                  {classifierStatus.vocab_size}
                </p>
                <p>
                  Binary F1:{" "}
                  {((classifierStatus.binary_cv_score || 0) * 100).toFixed(1)}%
                  | Type Acc:{" "}
                  {((classifierStatus.type_cv_score || 0) * 100).toFixed(1)}%
                </p>
                <p className="font-mono text-[10px]">
                  Trained:{" "}
                  {classifierStatus.trained_at
                    ? new Date(classifierStatus.trained_at).toLocaleString()
                    : "unknown"}
                </p>
              </div>
            )}
            <Button
              variant="secondary"
              size="sm"
              onClick={async () => {
                setOpLoading("retrain-classifier");
                try {
                  await api("/admin/ml/retrain-signal-classifier", "POST");
                  addToast("Signal classifier retrained", "success");
                  loadMLStatus();
                } catch (e) {
                  addToast(
                    `Retrain failed: ${e instanceof Error ? e.message : "unknown"}`,
                    "error",
                  );
                } finally {
                  setOpLoading(null);
                }
              }}
              disabled={!!opLoading}
              loading={opLoading === "retrain-classifier"}
            >
              <Lightning size={14} />
              Retrain
            </Button>
          </div>

          {/* Reranker */}
          <div className="rounded-lg border border-zinc-200 dark:border-zinc-700 p-4">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <Brain size={16} className="text-blue-500" />
                <span className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
                  ML Reranker
                </span>
              </div>
              <span
                className={`text-xs px-2 py-0.5 rounded-full ${
                  rerankerStatus?.status === "trained"
                    ? "bg-emerald-500/10 text-emerald-400"
                    : "bg-zinc-500/10 text-zinc-400"
                }`}
              >
                {rerankerStatus?.status || "unknown"}
              </span>
            </div>
            {rerankerStatus?.status === "trained" && (
              <div className="text-xs space-y-1 text-zinc-500 dark:text-zinc-400 mb-3">
                <p>
                  Samples: {rerankerStatus.n_samples} | CV Score:{" "}
                  {((rerankerStatus.cv_score || 0) * 100).toFixed(1)}%
                </p>
                <p>
                  Features: {rerankerStatus.features?.length || 0} |{" "}
                  {rerankerStatus.class_distribution
                    ? `Useful: ${rerankerStatus.class_distribution.useful}, Not: ${rerankerStatus.class_distribution.not_useful}`
                    : ""}
                </p>
                <p className="font-mono text-[10px]">
                  Trained:{" "}
                  {rerankerStatus.trained_at
                    ? new Date(rerankerStatus.trained_at).toLocaleString()
                    : "unknown"}
                </p>
              </div>
            )}
            <Button
              variant="secondary"
              size="sm"
              onClick={async () => {
                setOpLoading("retrain-reranker");
                try {
                  await api("/admin/ml/retrain-ranker", "POST");
                  addToast("Reranker retrained", "success");
                  loadMLStatus();
                } catch (e) {
                  addToast(
                    `Retrain failed: ${e instanceof Error ? e.message : "unknown"}`,
                    "error",
                  );
                } finally {
                  setOpLoading(null);
                }
              }}
              disabled={!!opLoading}
              loading={opLoading === "retrain-reranker"}
            >
              <Lightning size={14} />
              Retrain
            </Button>
          </div>
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
