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
  const statusDot =
    status === "ok" ? "bg-success" : status === "error" ? "bg-error" : null;

  return (
    <div className="rounded-xl bg-base-100 border border-base-content/5 p-4 hover:border-base-content/10 transition-colors">
      {loading ? (
        <div className="animate-pulse space-y-2">
          <div className="h-3 bg-base-300 rounded w-20" />
          <div className="h-6 bg-base-300 rounded w-16" />
        </div>
      ) : (
        <>
          <div className="flex items-center gap-2">
            {icon}
            <h3 className="text-[11px] font-medium uppercase tracking-wider text-base-content/40">
              {title}
            </h3>
            {statusDot && (
              <span className={`ml-auto h-2 w-2 rounded-full ${statusDot}`} />
            )}
          </div>
          <p className="text-2xl font-semibold tabular-nums mt-1">{value}</p>
          {subtitle && (
            <p className="text-xs text-base-content/50 mt-0.5">{subtitle}</p>
          )}
        </>
      )}
    </div>
  );
}
