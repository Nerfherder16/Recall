const typeColors: Record<string, string> = {
  semantic: "badge-info",
  episodic: "badge-warning",
  procedural: "badge-success",
  working: "badge-accent",
  create: "badge-success",
  delete: "badge-error",
  update: "badge-warning",
  consolidation: "badge-info",
  decay: "badge-ghost",
  user: "badge-primary",
  signal: "badge-secondary",
  observer: "badge-accent",
};

interface Props {
  text: string;
}

export default function Badge({ text }: Props) {
  const color = typeColors[text] || "badge-ghost";
  return <span className={`badge badge-sm ${color}`}>{text}</span>;
}
