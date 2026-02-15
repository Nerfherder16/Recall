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
  const borderColor =
    status === "ok"
      ? "border-success"
      : status === "error"
        ? "border-error"
        : "border-base-300";

  return (
    <div className={`card bg-base-100 shadow-sm border-l-4 ${borderColor}`}>
      <div className="card-body p-4">
        {loading ? (
          <div className="animate-pulse space-y-2">
            <div className="h-3 bg-base-300 rounded w-20" />
            <div className="h-6 bg-base-300 rounded w-16" />
          </div>
        ) : (
          <>
            <div className="flex items-center gap-2">
              {icon}
              <h3 className="text-xs uppercase text-base-content/50">
                {title}
              </h3>
            </div>
            <p className="text-2xl font-bold">{value}</p>
            {subtitle && (
              <p className="text-xs text-base-content/60">{subtitle}</p>
            )}
          </>
        )}
      </div>
    </div>
  );
}
