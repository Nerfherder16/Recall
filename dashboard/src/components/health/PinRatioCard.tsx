import { PushPin, Warning } from "@phosphor-icons/react";
import type { PinRatio } from "../../api/types";
import { HealthScale } from "./HealthScale";

interface Props {
  pins: PinRatio;
}

export function PinRatioCard({ pins }: Props) {
  const pct = (pins.ratio * 100).toFixed(1);

  return (
    <div className="rounded-2xl border border-zinc-200/80 dark:border-white/[0.06] bg-white/60 dark:bg-zinc-800/40 backdrop-blur-xl p-6">
      <div className="flex items-center gap-2 mb-2">
        <PushPin size={16} className="text-zinc-400 dark:text-zinc-500" />
        <span className="font-mono text-[10px] font-medium uppercase tracking-[0.2em] text-zinc-400 dark:text-zinc-500">
          Pin Ratio
        </span>
        {pins.warning && (
          <Warning size={14} className="text-amber-400" weight="fill" />
        )}
      </div>
      <p
        className={`font-display text-3xl font-bold ${pins.warning ? "text-amber-400" : "text-zinc-900 dark:text-zinc-100"}`}
      >
        {pct}%
      </p>
      <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
        {pins.pinned} pinned / {pins.total} total
        {pins.warning && " (high \u2014 consider unpinning some)"}
      </p>
      <HealthScale
        value={pins.ratio}
        ranges={[
          { max: 0.1, label: "<10% good", color: "bg-emerald-400" },
          { max: 0.3, label: "10–30%", color: "bg-amber-400" },
          { max: 1.0, label: ">30% high", color: "bg-red-400" },
        ]}
      />
    </div>
  );
}
