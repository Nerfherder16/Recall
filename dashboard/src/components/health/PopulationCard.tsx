import { TrendUp, TrendDown } from "@phosphor-icons/react";
import type { PopulationBalance } from "../../api/types";
import { InfoTip } from "./InfoTip";

interface Props {
  population: PopulationBalance;
}

export function PopulationCard({ population }: Props) {
  const isGrowing = population.net_growth >= 0;

  return (
    <div className="rounded-2xl border border-zinc-200/80 dark:border-white/[0.06] bg-white/60 dark:bg-zinc-800/40 backdrop-blur-xl p-6">
      <div className="flex items-center gap-2 mb-2">
        {isGrowing ? (
          <TrendUp size={16} className="text-zinc-400 dark:text-zinc-500" />
        ) : (
          <TrendDown size={16} className="text-zinc-400 dark:text-zinc-500" />
        )}
        <span className="font-mono text-[10px] font-medium uppercase tracking-[0.2em] text-zinc-400 dark:text-zinc-500">
          Population
        </span>
        <InfoTip text="Net memory growth over 30 days. Growing = healthy (new memories outpace decay). Mild shrinkage is normal — decay prunes low-value memories. If rapidly shrinking, pin important memories or check decay settings." />
      </div>
      <p
        className={`font-display text-3xl font-bold ${isGrowing ? "text-emerald-400" : "text-red-400"}`}
      >
        {isGrowing ? "+" : ""}
        {population.net_growth}
      </p>
      <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
        +{population.stores} stored, -{population.deletes} deleted, -
        {population.decays} decayed (30d)
      </p>
    </div>
  );
}
