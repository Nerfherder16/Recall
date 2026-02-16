import type { ReactNode } from "react";

interface Props {
  name: string;
  status: string;
  icon: ReactNode;
}

export default function ServiceStatusCard({ name, status, icon }: Props) {
  const isOk = status.startsWith("ok");
  return (
    <div className="rounded-xl bg-base-100 border border-base-content/5 p-3 hover:border-base-content/10 transition-colors">
      <div className="flex items-center gap-3">
        <div className="text-base-content/40">{icon}</div>
        <div className="flex-1 min-w-0">
          <h4 className="text-sm font-medium">{name}</h4>
          <p className="text-xs text-base-content/40 truncate">{status}</p>
        </div>
        <span
          className={`h-2.5 w-2.5 rounded-full shrink-0 ${
            isOk ? "bg-success" : "bg-error"
          }`}
        />
      </div>
    </div>
  );
}
