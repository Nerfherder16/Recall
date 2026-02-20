interface Range {
  max: number;
  label: string;
  color: string;
}

interface Props {
  value: number;
  ranges: Range[];
}

export function HealthScale({ value, ranges }: Props) {
  // Find which range the value falls into
  const activeIndex = ranges.findIndex((r) => value <= r.max);
  const clampedIndex = activeIndex === -1 ? ranges.length - 1 : activeIndex;

  // Compute marker position (0-100%)
  const totalMax = ranges[ranges.length - 1].max;
  const pct = Math.min(100, Math.max(0, (value / totalMax) * 100));

  return (
    <div className="mt-3">
      {/* Segmented bar */}
      <div className="flex gap-0.5 h-1.5 rounded-full overflow-hidden">
        {ranges.map((r, i) => {
          const prevMax = i > 0 ? ranges[i - 1].max : 0;
          const width = ((r.max - prevMax) / totalMax) * 100;
          return (
            <div
              key={r.label}
              className={`${r.color} ${i === clampedIndex ? "opacity-100" : "opacity-25"}`}
              style={{ width: `${width}%` }}
            />
          );
        })}
      </div>

      {/* Marker */}
      <div className="relative h-0">
        <div
          className="absolute -top-1 w-0.5 h-2.5 bg-white rounded-full"
          style={{ left: `${pct}%`, transform: "translateX(-50%)" }}
        />
      </div>

      {/* Labels */}
      <div className="flex justify-between mt-1.5">
        {ranges.map((r, i) => (
          <span
            key={r.label}
            className={`text-[9px] font-mono ${
              i === clampedIndex ? "text-zinc-300" : "text-zinc-600"
            }`}
          >
            {r.label}
          </span>
        ))}
      </div>
    </div>
  );
}
