import { Graph } from "@phosphor-icons/react";
import type { GraphCohesion } from "../../api/types";
import { HealthScale } from "./HealthScale";

interface Props {
  graph: GraphCohesion;
}

export function GraphCohesionCard({ graph }: Props) {
  return (
    <div className="rounded-2xl border border-zinc-200/80 dark:border-white/[0.06] bg-white/60 dark:bg-zinc-800/40 backdrop-blur-xl p-6">
      <div className="flex items-center gap-2 mb-2">
        <Graph size={16} className="text-zinc-400 dark:text-zinc-500" />
        <span className="font-mono text-[10px] font-medium uppercase tracking-[0.2em] text-zinc-400 dark:text-zinc-500">
          Graph Cohesion
        </span>
      </div>
      <p className="font-display text-3xl font-bold text-cyan-400">
        {graph.avg_edge_strength.toFixed(3)}
      </p>
      <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
        Avg edge strength across {graph.edge_count} edges
      </p>
      <HealthScale
        value={graph.avg_edge_strength}
        ranges={[
          { max: 0.3, label: "<0.3 weak", color: "bg-red-400" },
          { max: 0.6, label: "0.3–0.6", color: "bg-amber-400" },
          { max: 1.0, label: ">0.6 strong", color: "bg-emerald-400" },
        ]}
      />
    </div>
  );
}
