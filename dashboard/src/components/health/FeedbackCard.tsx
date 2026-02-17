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
    <div className="rounded-xl bg-base-100 border border-base-content/5 p-4">
      <div className="flex items-center gap-2 mb-2">
        <ThumbsUp size={16} className="text-base-content/40" />
        <span className="text-xs font-medium uppercase tracking-wider text-base-content/40">
          Feedback
        </span>
      </div>
      <p className={`text-2xl font-bold ${color}`}>{rate}%</p>
      <p className="text-xs text-base-content/40 mt-1">
        {feedback.total_positive} positive / {total} total (30d)
      </p>
    </div>
  );
}
