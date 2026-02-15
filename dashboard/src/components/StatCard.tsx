interface Props {
  title: string;
  value: string | number;
  subtitle?: string;
  status?: "ok" | "error" | "unknown";
}

export default function StatCard({ title, value, subtitle, status }: Props) {
  const borderColor =
    status === "ok"
      ? "border-success"
      : status === "error"
        ? "border-error"
        : "border-base-300";

  return (
    <div className={`card bg-base-100 shadow-sm border-l-4 ${borderColor}`}>
      <div className="card-body p-4">
        <h3 className="text-xs uppercase text-base-content/50">{title}</h3>
        <p className="text-2xl font-bold">{value}</p>
        {subtitle && (
          <p className="text-xs text-base-content/60">{subtitle}</p>
        )}
      </div>
    </div>
  );
}
