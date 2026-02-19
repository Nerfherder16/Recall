import { SquaresFour, List } from "@phosphor-icons/react";
import { cn } from "../lib/utils";

interface Props {
  view: "grid" | "list";
  onChange: (v: "grid" | "list") => void;
}

export default function ViewToggle({ view, onChange }: Props) {
  return (
    <div className="flex rounded-full border border-zinc-200 dark:border-white/[0.06] overflow-hidden bg-zinc-100 dark:bg-zinc-800/50 p-0.5">
      <button
        className={cn(
          "px-2.5 py-1.5 rounded-full transition-all duration-200",
          view === "grid"
            ? "bg-white dark:bg-zinc-700 text-zinc-900 dark:text-zinc-100 shadow-sm"
            : "text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200",
        )}
        onClick={() => onChange("grid")}
        title="Grid view"
      >
        <SquaresFour size={16} />
      </button>
      <button
        className={cn(
          "px-2.5 py-1.5 rounded-full transition-all duration-200",
          view === "list"
            ? "bg-white dark:bg-zinc-700 text-zinc-900 dark:text-zinc-100 shadow-sm"
            : "text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200",
        )}
        onClick={() => onChange("list")}
        title="List view"
      >
        <List size={16} />
      </button>
    </div>
  );
}
