import { PushPin, Warning } from "@phosphor-icons/react";
import type { PinRatio } from "../../api/types";

interface Props {
  pins: PinRatio;
}

export function PinRatioCard({ pins }: Props) {
  const pct = (pins.ratio * 100).toFixed(1);

  return (
    <div className="rounded-xl bg-base-100 border border-base-content/5 p-4">
      <div className="flex items-center gap-2 mb-2">
        <PushPin size={16} className="text-base-content/40" />
        <span className="text-xs font-medium uppercase tracking-wider text-base-content/40">
          Pin Ratio
        </span>
        {pins.warning && (
          <Warning size={14} className="text-amber-400" weight="fill" />
        )}
      </div>
      <p
        className={`text-2xl font-bold ${pins.warning ? "text-amber-400" : "text-base-content"}`}
      >
        {pct}%
      </p>
      <p className="text-xs text-base-content/40 mt-1">
        {pins.pinned} pinned / {pins.total} total
        {pins.warning && " (high — consider unpinning some)"}
      </p>
    </div>
  );
}
