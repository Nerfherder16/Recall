interface Props {
  name: string;
  status: string; // "ok", "ok (123 items)", "error", etc.
  icon: string; // SVG path
}

export default function ServiceStatusCard({ name, status, icon }: Props) {
  const isOk = status.startsWith("ok");
  return (
    <div
      className={`card bg-base-100 shadow-sm border-l-4 ${isOk ? "border-success" : "border-error"}`}
    >
      <div className="card-body p-3 flex-row items-center gap-3">
        <div
          className={`p-2 rounded-lg ${isOk ? "bg-success/10 text-success" : "bg-error/10 text-error"}`}
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-5 w-5"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d={icon}
            />
          </svg>
        </div>
        <div className="flex-1 min-w-0">
          <h4 className="font-semibold text-sm">{name}</h4>
          <p className="text-xs text-base-content/50 truncate">{status}</p>
        </div>
        <div
          className={`badge badge-sm ${isOk ? "badge-success" : "badge-error"}`}
        >
          {isOk ? "OK" : "Error"}
        </div>
      </div>
    </div>
  );
}
