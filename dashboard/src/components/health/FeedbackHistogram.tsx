import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import type { SimilarityBucket } from "../../api/types";
import { InfoTip } from "./InfoTip";

interface Props {
  buckets: SimilarityBucket[];
}

export function FeedbackHistogram({ buckets }: Props) {
  const data = buckets.map((b) => ({
    range: `${b.range_start.toFixed(1)}-${b.range_end.toFixed(1)}`,
    count: b.count,
  }));

  return (
    <div className="rounded-2xl border border-zinc-200/80 dark:border-white/[0.06] bg-white/60 dark:bg-zinc-800/40 backdrop-blur-xl p-6">
      <h3 className="text-sm font-semibold mb-3 text-zinc-900 dark:text-zinc-100 flex items-center gap-2">
        Feedback Similarity Distribution
        <InfoTip text="How closely retrieved memories matched what you used. Bars at 0.7–1.0 = surfacing relevant content. Concentration at 0.0–0.3 = memories aren't matching needs. The 0.35 threshold separates 'useful' from 'not useful' in the feedback loop." />
      </h3>
      {data.length === 0 ? (
        <p className="text-xs text-zinc-400">No feedback data yet</p>
      ) : (
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={data}>
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
            <Bar dataKey="count" fill="#8b5cf6" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
