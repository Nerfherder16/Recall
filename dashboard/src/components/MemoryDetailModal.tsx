import { useRef, useEffect } from "react";
import { X } from "@phosphor-icons/react";
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
      <div className="rounded-2xl bg-base-100 border border-base-content/5 p-6 max-w-2xl w-full">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Badge text={memory.memory_type} />
            <span className="text-sm text-base-content/40">
              {memory.domain}
            </span>
          </div>
          <button
            className="rounded-lg p-1.5 hover:bg-base-content/5 transition-colors"
            onClick={onClose}
          >
            <X size={16} />
          </button>
        </div>

        <p className="font-mono text-xs text-base-content/30 mb-3">
          ID: {memory.id}
        </p>

        <div className="bg-base-200 rounded-lg p-4 text-sm whitespace-pre-wrap mb-4 border border-base-content/5">
          {memory.content}
        </div>

        {memory.tags.length > 0 && (
          <div className="flex flex-wrap gap-1 mb-4">
            {memory.tags.map((t) => (
              <span
                key={t}
                className="inline-flex items-center rounded-md bg-zinc-500/10 text-zinc-400 px-2 py-0.5 text-[11px] font-medium"
              >
                {t}
              </span>
            ))}
          </div>
        )}

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { label: "Importance", val: memory.importance.toFixed(3) },
            { label: "Stability", val: memory.stability.toFixed(3) },
            { label: "Confidence", val: memory.confidence.toFixed(3) },
            { label: "Accesses", val: memory.access_count },
          ].map((item) => (
            <div
              key={item.label}
              className="bg-base-200 rounded-lg p-2 text-center border border-base-content/5"
            >
              <p className="text-[11px] font-medium uppercase tracking-wider text-base-content/40">
                {item.label}
              </p>
              <p className="font-semibold tabular-nums">{item.val}</p>
            </div>
          ))}
        </div>

        <div className="flex flex-wrap gap-4 mt-4 text-xs text-base-content/40">
          <span>Source: {memory.source}</span>
          {memory.stored_by && <span>Stored by: {memory.stored_by}</span>}
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
