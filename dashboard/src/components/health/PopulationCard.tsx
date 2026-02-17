import { TrendUp, TrendDown } from "@phosphor-icons/react";
import type { PopulationBalance } from "../../api/types";

interface Props {
  population: PopulationBalance;
}

export function PopulationCard({ population }: Props) {
  const isGrowing = population.net_growth >= 0;

  return (
    <div className="rounded-xl bg-base-100 border border-base-content/5 p-4">
      <div className="flex items-center gap-2 mb-2">
        {isGrowing ? (
          <TrendUp size={16} className="text-base-content/40" />
        ) : (
          <TrendDown size={16} className="text-base-content/40" />
        )}
        <span className="text-xs font-medium uppercase tracking-wider text-base-content/40">
          Population
        </span>
      </div>
      <p
        className={`text-2xl font-bold ${isGrowing ? "text-emerald-400" : "text-red-400"}`}
      >
        {isGrowing ? "+" : ""}
        {population.net_growth}
      </p>
      <p className="text-xs text-base-content/40 mt-1">
        +{population.stores} stored, -{population.deletes} deleted, -
        {population.decays} decayed (30d)
      </p>
    </div>
  );
}
