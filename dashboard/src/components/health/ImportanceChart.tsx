import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import type { ImportanceBand } from "../../api/types";
import { InfoTip } from "./InfoTip";

interface Props {
  bands: ImportanceBand[];
}

export function ImportanceChart({ bands }: Props) {
  return (
    <div className="rounded-2xl border border-zinc-200/80 dark:border-white/[0.06] bg-white/60 dark:bg-zinc-800/40 backdrop-blur-xl p-6">
      <h3 className="text-sm font-semibold mb-3 text-zinc-900 dark:text-zinc-100 flex items-center gap-2">
        Importance Distribution
        <InfoTip text="How memories spread across importance (0–1). Healthy = bell curve around 0.3–0.6. Too many at 0.0–0.2 = aggressive decay. Spike at 0.8+ = importance inflation. Decay pushes unused memories left; retrieval and feedback push useful ones right." />
      </h3>
      {bands.length === 0 ? (
        <p className="text-xs text-zinc-400">No data available</p>
      ) : (
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={bands}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
            <XAxis
              dataKey="range"
              tick={{ fontSize: 11, fill: "var(--chart-text)" }}
            />
            <YAxis tick={{ fontSize: 11, fill: "var(--chart-text)" }} />
            <Tooltip
              contentStyle={{
                background: "var(--chart-tooltip-bg)",
                border: "1px solid var(--chart-tooltip-border)",
                borderRadius: "8px",
                fontSize: "12px",
                color: "var(--content-primary)",
              }}
            />
            <Bar dataKey="count" fill="#3b82f6" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
