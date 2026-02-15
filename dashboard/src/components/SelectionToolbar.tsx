interface Props {
  count: number;
  onDelete: () => void;
  onClear: () => void;
}

export default function SelectionToolbar({ count, onDelete, onClear }: Props) {
  if (count === 0) return null;
  return (
    <div className="fixed bottom-16 left-1/2 -translate-x-1/2 z-40 bg-base-300 shadow-xl rounded-box px-4 py-2 flex items-center gap-3 animate-slide-in">
      <span className="text-sm font-semibold">{count} selected</span>
      <button className="btn btn-error btn-sm" onClick={onDelete}>
        Delete
      </button>
      <button className="btn btn-ghost btn-sm" onClick={onClear}>
        Clear
      </button>
    </div>
  );
}
