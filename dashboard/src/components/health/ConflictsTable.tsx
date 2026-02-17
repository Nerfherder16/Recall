import { useState } from "react";
import { Warning, Info } from "@phosphor-icons/react";
import type { Conflict } from "../../api/types";

interface Props {
  conflicts: Conflict[];
}

const SEVERITY_STYLES: Record<string, string> = {
  warning: "bg-amber-500/10 text-amber-400 ring-1 ring-amber-500/20",
  info: "bg-blue-500/10 text-blue-400 ring-1 ring-blue-500/20",
  critical: "bg-red-500/10 text-red-400 ring-1 ring-red-500/20",
};

const TYPE_LABELS: Record<string, string> = {
  noisy: "Noisy",
  feedback_starved: "No Feedback",
  orphan_hub: "Orphan Hub",
  decay_vs_feedback: "Decay vs Feedback",
  stale_anti_pattern: "Stale Anti-Pattern",
};

export function ConflictsTable({ conflicts }: Props) {
  const [typeFilter, setTypeFilter] = useState<string>("");

  const types = [...new Set(conflicts.map((c) => c.type))];
  const filtered = typeFilter
    ? conflicts.filter((c) => c.type === typeFilter)
    : conflicts;

  return (
    <div className="rounded-xl bg-base-100 border border-base-content/5 p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold flex items-center gap-2">
          <Warning size={16} className="text-amber-400" />
          Conflicts ({conflicts.length})
        </h3>
        {types.length > 1 && (
          <select
            className="rounded-lg border border-base-content/10 bg-base-200 px-2 py-1 text-xs focus:border-primary/50 focus:outline-none"
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
          >
            <option value="">All types</option>
            {types.map((t) => (
              <option key={t} value={t}>
                {TYPE_LABELS[t] || t}
              </option>
            ))}
          </select>
        )}
      </div>

      {filtered.length === 0 ? (
        <p className="text-xs text-base-content/40 py-4 text-center">
          No conflicts detected
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="table table-sm w-full">
            <thead>
              <tr className="text-xs text-base-content/40">
                <th>Type</th>
                <th>Severity</th>
                <th>Memory</th>
                <th>Description</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((c, i) => (
                <tr key={i} className="hover:bg-base-200/50">
                  <td>
                    <span className="text-xs font-medium">
                      {TYPE_LABELS[c.type] || c.type}
                    </span>
                  </td>
                  <td>
                    <span
                      className={`inline-flex items-center gap-1 text-[10px] font-medium px-2 py-0.5 rounded-full ${SEVERITY_STYLES[c.severity] || SEVERITY_STYLES.info}`}
                    >
                      {c.severity === "warning" ? (
                        <Warning size={10} weight="fill" />
                      ) : (
                        <Info size={10} weight="fill" />
                      )}
                      {c.severity}
                    </span>
                  </td>
                  <td>
                    <code className="text-[10px] text-base-content/50 font-mono">
                      {c.memory_id.slice(0, 8)}...
                    </code>
                  </td>
                  <td className="text-xs text-base-content/60">
                    {c.description}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
