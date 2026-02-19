import { StatCardSkeleton } from "./common/Skeleton";

interface Props {
  title: string;
  value: string | number;
  subtitle?: string;
  status?: "ok" | "error" | "unknown";
  icon?: React.ReactNode;
  loading?: boolean;
}

export default function StatCard({
  title,
  value,
  subtitle,
  status,
  icon,
  loading,
}: Props) {
  if (loading) return <StatCardSkeleton />;

  const statusDot =
    status === "ok"
      ? "bg-emerald-400"
      : status === "error"
        ? "bg-red-400"
        : null;

  return (
    <div className="rounded-2xl border border-zinc-200/80 dark:border-white/[0.06] bg-white/60 dark:bg-zinc-800/40 backdrop-blur-xl p-6 hover:border-zinc-300 dark:hover:border-white/[0.1] transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg">
      <div className="flex items-center gap-2">
        {icon}
        <h3 className="font-mono text-[10px] font-medium uppercase tracking-[0.2em] text-zinc-400 dark:text-zinc-500">
          {title}
        </h3>
        {statusDot && (
          <span
            className={`ml-auto h-2 w-2 rounded-full ${statusDot} ${status === "ok" ? "animate-pulse-dot" : ""}`}
          />
        )}
      </div>
      <p className="font-display text-3xl font-bold mt-2 text-zinc-900 dark:text-zinc-50">
        {value}
      </p>
      {subtitle && (
        <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
          {subtitle}
        </p>
      )}
    </div>
  );
}
