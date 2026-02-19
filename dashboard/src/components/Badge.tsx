import { cn } from "../lib/utils";

const typeColors: Record<string, string> = {
  semantic: "bg-blue-500/10 text-blue-400 ring-blue-500/20",
  episodic: "bg-amber-500/10 text-amber-400 ring-amber-500/20",
  procedural: "bg-emerald-500/10 text-emerald-400 ring-emerald-500/20",
  working: "bg-violet-500/10 text-violet-400 ring-violet-500/20",
  create: "bg-emerald-500/10 text-emerald-400 ring-emerald-500/20",
  delete: "bg-red-500/10 text-red-400 ring-red-500/20",
  update: "bg-amber-500/10 text-amber-400 ring-amber-500/20",
  consolidation: "bg-blue-500/10 text-blue-400 ring-blue-500/20",
  decay: "bg-zinc-500/10 text-zinc-400 ring-zinc-500/20",
  user: "bg-violet-500/10 text-violet-400 ring-violet-500/20",
  signal: "bg-sky-500/10 text-sky-400 ring-sky-500/20",
  observer: "bg-teal-500/10 text-teal-400 ring-teal-500/20",
};

interface Props {
  text: string;
  className?: string;
}

export default function Badge({ text, className }: Props) {
  const color =
    typeColors[text] || "bg-zinc-500/10 text-zinc-400 ring-zinc-500/20";
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-medium ring-1",
        color,
        className,
      )}
    >
      {text}
    </span>
  );
}
