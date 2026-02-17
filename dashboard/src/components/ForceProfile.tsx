import { useState, useCallback, useEffect } from "react";
import { CaretDown, CaretUp, Lightning } from "@phosphor-icons/react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Cell,
} from "recharts";
import { api } from "../api/client";
import type { ForceProfileResponse } from "../api/types";

interface Props {
  memoryId: string;
}

const FORCE_LABELS: Record<string, string> = {
  decay_pressure: "Decay Pressure",
  retrieval_lift: "Retrieval Lift",
  feedback_signal: "Feedback Signal",
  co_retrieval_gravity: "Co-retrieval",
  pin_status: "Pin Status",
  durability_shield: "Durability Shield",
};

export function ForceProfile({ memoryId }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [data, setData] = useState<ForceProfileResponse | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchForces = useCallback(async () => {
    if (data || loading) return;
    setLoading(true);
    try {
      const result = await api<ForceProfileResponse>(
        `/memory/${memoryId}/forces`,
      );
      setData(result);
    } catch {
      // Silent fail — force profile is supplementary
    } finally {
      setLoading(false);
    }
  }, [memoryId, data, loading]);

  useEffect(() => {
    if (expanded && !data) {
      fetchForces();
    }
  }, [expanded, data, fetchForces]);

  const chartData = data
    ? Object.entries(data.forces).map(([key, value]) => ({
        name: FORCE_LABELS[key] || key,
        value: value as number,
      }))
    : [];

  return (
    <div className="mt-4 border border-base-content/5 rounded-lg">
      <button
        className="flex items-center gap-2 w-full px-4 py-2.5 text-sm text-base-content/60 hover:text-base-content transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <Lightning size={14} className="text-violet-400" />
        <span className="font-medium">Force Profile</span>
        {expanded ? <CaretUp size={12} /> : <CaretDown size={12} />}
      </button>

      {expanded && (
        <div className="px-4 pb-4">
          {loading && (
            <p className="text-xs text-base-content/40 py-2">Loading...</p>
          )}
          {data && (
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={chartData} layout="vertical">
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke="oklch(var(--bc) / 0.1)"
                />
                <XAxis
                  type="number"
                  tick={{ fontSize: 10, fill: "oklch(var(--bc) / 0.4)" }}
                />
                <YAxis
                  type="category"
                  dataKey="name"
                  width={110}
                  tick={{ fontSize: 10, fill: "oklch(var(--bc) / 0.4)" }}
                />
                <Tooltip
                  contentStyle={{
                    background: "oklch(var(--b1))",
                    border: "1px solid oklch(var(--bc) / 0.1)",
                    borderRadius: "8px",
                    fontSize: "11px",
                  }}
                  formatter={(v: number | undefined) => (v ?? 0).toFixed(4)}
                />
                <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                  {chartData.map((entry, index) => (
                    <Cell
                      key={index}
                      fill={entry.value >= 0 ? "#10b981" : "#ef4444"}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      )}
    </div>
  );
}
