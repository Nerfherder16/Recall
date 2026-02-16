import { SquaresFour, List } from "@phosphor-icons/react";

interface Props {
  view: "grid" | "list";
  onChange: (v: "grid" | "list") => void;
}

export default function ViewToggle({ view, onChange }: Props) {
  return (
    <div className="flex rounded-lg border border-base-content/10 overflow-hidden">
      <button
        className={`px-2.5 py-1.5 transition-colors ${
          view === "grid"
            ? "bg-base-content/10 text-base-content"
            : "text-base-content/40 hover:text-base-content"
        }`}
        onClick={() => onChange("grid")}
        title="Grid view"
      >
        <SquaresFour size={16} />
      </button>
      <button
        className={`px-2.5 py-1.5 transition-colors ${
          view === "list"
            ? "bg-base-content/10 text-base-content"
            : "text-base-content/40 hover:text-base-content"
        }`}
        onClick={() => onChange("list")}
        title="List view"
      >
        <List size={16} />
      </button>
    </div>
  );
}
