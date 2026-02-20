import { useState } from "react";
import { Warning, Info, CheckCircle } from "@phosphor-icons/react";
import type { Conflict } from "../../api/types";
import { GlassCard } from "../common/GlassCard";
import { Select } from "../common/Input";
import {
  Table,
  TableHead,
  TableBody,
  TableRow,
  TableCell,
} from "../common/Table";
import { InfoTip } from "./InfoTip";

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

const TYPE_TIPS: Record<string, string> = {
  noisy:
    "Retrieved often but rarely marked useful. Consider deleting or rewording.",
  feedback_starved:
    "High access count but zero feedback. Use the memory in a session so the feedback loop can score it.",
  orphan_hub:
    "Many graph edges but low importance — decay should eventually prune it, or delete manually.",
  decay_vs_feedback:
    "Decay is pushing importance down while feedback says it's useful. Pin it to protect from decay.",
  stale_anti_pattern:
    "An anti-pattern that hasn't triggered in a while. Review whether it's still relevant.",
};

export function ConflictsTable({ conflicts }: Props) {
  const [typeFilter, setTypeFilter] = useState<string>("");

  const types = [...new Set(conflicts.map((c) => c.type))];
  const filtered = typeFilter
    ? conflicts.filter((c) => c.type === typeFilter)
    : conflicts;

  return (
    <GlassCard className="p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold flex items-center gap-2 text-zinc-900 dark:text-zinc-100">
          <Warning size={16} className="text-amber-400" />
          Conflicts ({conflicts.length})
          <InfoTip text="Memories where competing forces disagree — e.g. decay pulling importance down while feedback says it's useful, or a memory retrieved often but never marked helpful. Zero conflicts means the system's forces are balanced." />
        </h3>
        {types.length > 1 && (
          <Select
            className="w-auto text-xs"
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
          >
            <option value="">All types</option>
            {types.map((t) => (
              <option key={t} value={t}>
                {TYPE_LABELS[t] || t}
              </option>
            ))}
          </Select>
        )}
      </div>

      {filtered.length === 0 ? (
        <div className="py-4 text-center">
          <CheckCircle size={24} className="text-emerald-400 mx-auto mb-2" />
          <p className="text-xs text-zinc-400">No conflicts detected</p>
        </div>
      ) : (
        <Table>
          <TableHead>
            <TableCell header>Type</TableCell>
            <TableCell header>Severity</TableCell>
            <TableCell header>Memory</TableCell>
            <TableCell header>Description</TableCell>
          </TableHead>
          <TableBody>
            {filtered.map((c, i) => (
              <TableRow key={i}>
                <TableCell>
                  <span className="text-xs font-medium text-zinc-700 dark:text-zinc-300 inline-flex items-center gap-1">
                    {TYPE_LABELS[c.type] || c.type}
                    {TYPE_TIPS[c.type] && <InfoTip text={TYPE_TIPS[c.type]} />}
                  </span>
                </TableCell>
                <TableCell>
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
                </TableCell>
                <TableCell>
                  <code className="text-[10px] text-zinc-400 font-mono">
                    {c.memory_id.slice(0, 8)}...
                  </code>
                </TableCell>
                <TableCell>
                  <span className="text-xs text-zinc-500 dark:text-zinc-400">
                    {c.description}
                  </span>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </GlassCard>
  );
}
