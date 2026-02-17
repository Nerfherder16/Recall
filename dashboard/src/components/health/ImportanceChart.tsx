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

interface Props {
  bands: ImportanceBand[];
}

export function ImportanceChart({ bands }: Props) {
  return (
    <div className="rounded-xl bg-base-100 border border-base-content/5 p-4">
      <h3 className="text-sm font-semibold mb-3">Importance Distribution</h3>
      {bands.length === 0 ? (
        <p className="text-xs text-base-content/40">No data available</p>
      ) : (
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={bands}>
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="oklch(var(--bc) / 0.1)"
            />
            <XAxis
              dataKey="range"
              tick={{ fontSize: 11, fill: "oklch(var(--bc) / 0.4)" }}
            />
            <YAxis tick={{ fontSize: 11, fill: "oklch(var(--bc) / 0.4)" }} />
            <Tooltip
              contentStyle={{
                background: "oklch(var(--b1))",
                border: "1px solid oklch(var(--bc) / 0.1)",
                borderRadius: "8px",
                fontSize: "12px",
              }}
            />
            <Bar dataKey="count" fill="#3b82f6" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
