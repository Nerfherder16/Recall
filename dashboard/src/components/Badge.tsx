const typeColors: Record<string, string> = {
  semantic: "bg-blue-500/10 text-blue-400",
  episodic: "bg-amber-500/10 text-amber-400",
  procedural: "bg-emerald-500/10 text-emerald-400",
  working: "bg-violet-500/10 text-violet-400",
  create: "bg-emerald-500/10 text-emerald-400",
  delete: "bg-red-500/10 text-red-400",
  update: "bg-amber-500/10 text-amber-400",
  consolidation: "bg-blue-500/10 text-blue-400",
  decay: "bg-zinc-500/10 text-zinc-400",
  user: "bg-violet-500/10 text-violet-400",
  signal: "bg-sky-500/10 text-sky-400",
  observer: "bg-teal-500/10 text-teal-400",
};

interface Props {
  text: string;
}

export default function Badge({ text }: Props) {
  const color = typeColors[text] || "bg-zinc-500/10 text-zinc-400";
  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-0.5 text-[11px] font-medium ${color}`}
    >
      {text}
    </span>
  );
}
