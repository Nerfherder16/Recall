import { Graph } from "@phosphor-icons/react";
import type { GraphCohesion } from "../../api/types";

interface Props {
  graph: GraphCohesion;
}

export function GraphCohesionCard({ graph }: Props) {
  return (
    <div className="rounded-xl bg-base-100 border border-base-content/5 p-4">
      <div className="flex items-center gap-2 mb-2">
        <Graph size={16} className="text-base-content/40" />
        <span className="text-xs font-medium uppercase tracking-wider text-base-content/40">
          Graph Cohesion
        </span>
      </div>
      <p className="text-2xl font-bold text-cyan-400">
        {graph.avg_edge_strength.toFixed(3)}
      </p>
      <p className="text-xs text-base-content/40 mt-1">
        Avg edge strength across {graph.edge_count} edges
      </p>
    </div>
  );
}
