import { Trash, X } from "@phosphor-icons/react";

interface Props {
  count: number;
  onDelete: () => void;
  onClear: () => void;
}

export default function SelectionToolbar({ count, onDelete, onClear }: Props) {
  if (count === 0) return null;
  return (
    <div className="fixed bottom-16 left-1/2 -translate-x-1/2 z-40 rounded-xl bg-base-300 border border-base-content/10 px-4 py-2.5 flex items-center gap-3 animate-slide-in shadow-lg">
      <span className="text-sm font-medium">{count} selected</span>
      <button
        className="flex items-center gap-1.5 rounded-lg bg-error px-3 py-1.5 text-sm font-medium text-error-content hover:bg-error/90 transition-colors"
        onClick={onDelete}
      >
        <Trash size={14} />
        Delete
      </button>
      <button
        className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm hover:bg-base-content/5 transition-colors"
        onClick={onClear}
      >
        <X size={14} />
        Clear
      </button>
    </div>
  );
}
