import { ThumbsUp } from "@phosphor-icons/react";
import type { FeedbackMetrics } from "../../api/types";

interface Props {
  feedback: FeedbackMetrics;
}

export function FeedbackCard({ feedback }: Props) {
  const rate = (feedback.positive_rate * 100).toFixed(1);
  const total = feedback.total_positive + feedback.total_negative;
  const color =
    feedback.positive_rate >= 0.7
      ? "text-emerald-400"
      : feedback.positive_rate >= 0.4
        ? "text-amber-400"
        : "text-red-400";

  return (
    <div className="rounded-2xl border border-zinc-200/80 dark:border-white/[0.06] bg-white/60 dark:bg-zinc-800/40 backdrop-blur-xl p-6">
      <div className="flex items-center gap-2 mb-2">
        <ThumbsUp size={16} className="text-zinc-400 dark:text-zinc-500" />
        <span className="font-mono text-[10px] font-medium uppercase tracking-[0.2em] text-zinc-400 dark:text-zinc-500">
          Feedback
        </span>
      </div>
      <p className={`font-display text-3xl font-bold ${color}`}>{rate}%</p>
      <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
        {feedback.total_positive} positive / {total} total (30d)
      </p>
    </div>
  );
}
