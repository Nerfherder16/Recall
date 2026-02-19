import type { ReactNode } from "react";

interface Props {
  name: string;
  status: string;
  icon: ReactNode;
}

export default function ServiceStatusCard({ name, status, icon }: Props) {
  const isOk = status.startsWith("ok");
  return (
    <div className="rounded-2xl border border-zinc-200/80 dark:border-white/[0.06] bg-white/60 dark:bg-zinc-800/40 backdrop-blur-xl p-3 hover:border-zinc-300 dark:hover:border-white/[0.1] transition-all duration-200">
      <div className="flex items-center gap-3">
        <div className="text-zinc-400 dark:text-zinc-500">{icon}</div>
        <div className="flex-1 min-w-0">
          <h4 className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
            {name}
          </h4>
          <p className="text-xs text-zinc-500 dark:text-zinc-400 truncate">
            {status}
          </p>
        </div>
        <span
          className={`h-2.5 w-2.5 rounded-full shrink-0 ${
            isOk ? "bg-emerald-400 animate-pulse-dot" : "bg-red-400"
          }`}
        />
      </div>
    </div>
  );
}
