import { useRef, useEffect } from "react";
import type { MemoryDetail } from "../api/types";
import Badge from "./Badge";

interface Props {
  memory: MemoryDetail | null;
  onClose: () => void;
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export default function MemoryDetailModal({ memory, onClose }: Props) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    if (memory) {
      ref.current?.showModal();
    } else {
      ref.current?.close();
    }
  }, [memory]);

  if (!memory) return null;

  return (
    <dialog ref={ref} className="modal" onClose={onClose}>
      <div className="modal-box max-w-2xl">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Badge text={memory.memory_type} />
            <span className="text-sm text-base-content/50">
              {memory.domain}
            </span>
          </div>
          <button className="btn btn-sm btn-ghost" onClick={onClose}>
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-4 w-4"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>

        <p className="font-mono text-xs text-base-content/40 mb-3">
          ID: {memory.id}
        </p>

        <div className="bg-base-200 rounded-lg p-4 text-sm whitespace-pre-wrap mb-4">
          {memory.content}
        </div>

        {memory.tags.length > 0 && (
          <div className="flex flex-wrap gap-1 mb-4">
            {memory.tags.map((t) => (
              <span key={t} className="badge badge-sm badge-ghost">
                {t}
              </span>
            ))}
          </div>
        )}

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div className="bg-base-200 rounded-lg p-2 text-center">
            <p className="text-xs text-base-content/50">Importance</p>
            <p className="font-bold">{memory.importance.toFixed(3)}</p>
          </div>
          <div className="bg-base-200 rounded-lg p-2 text-center">
            <p className="text-xs text-base-content/50">Stability</p>
            <p className="font-bold">{memory.stability.toFixed(3)}</p>
          </div>
          <div className="bg-base-200 rounded-lg p-2 text-center">
            <p className="text-xs text-base-content/50">Confidence</p>
            <p className="font-bold">{memory.confidence.toFixed(3)}</p>
          </div>
          <div className="bg-base-200 rounded-lg p-2 text-center">
            <p className="text-xs text-base-content/50">Accesses</p>
            <p className="font-bold">{memory.access_count}</p>
          </div>
        </div>

        <div className="flex gap-4 mt-4 text-xs text-base-content/50">
          <span>Source: {memory.source}</span>
          <span>Created: {formatDate(memory.created_at)}</span>
          <span>Last access: {formatDate(memory.last_accessed)}</span>
        </div>
      </div>
      <form method="dialog" className="modal-backdrop">
        <button>close</button>
      </form>
    </dialog>
  );
}
