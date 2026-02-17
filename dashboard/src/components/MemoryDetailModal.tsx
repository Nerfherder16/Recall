import { useRef, useEffect, useState } from "react";
import { X, PushPin, Sparkle, Lock, ShieldCheck } from "@phosphor-icons/react";
import { api } from "../api/client";
import type { MemoryDetail } from "../api/types";
import Badge from "./Badge";
import { ForceProfile } from "./ForceProfile";
import { useToastContext } from "../context/ToastContext";

function shouldSuggestPin(m: MemoryDetail): boolean {
  return !m.pinned && m.importance >= 0.7 && m.access_count >= 10;
}

interface Props {
  memory: MemoryDetail | null;
  onClose: () => void;
  onUpdate?: (updated: MemoryDetail) => void;
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export default function MemoryDetailModal({
  memory,
  onClose,
  onUpdate,
}: Props) {
  const ref = useRef<HTMLDialogElement>(null);
  const { addToast } = useToastContext();
  const [pinning, setPinning] = useState(false);

  useEffect(() => {
    if (memory) {
      ref.current?.showModal();
    } else {
      ref.current?.close();
    }
  }, [memory]);

  if (!memory) return null;

  async function togglePin() {
    if (!memory || pinning) return;
    setPinning(true);
    try {
      if (memory.pinned) {
        await api(`/memory/${memory.id}/pin`, "DELETE");
        memory.pinned = false;
        addToast("Memory unpinned", "success");
      } else {
        await api(`/memory/${memory.id}/pin`, "POST");
        memory.pinned = true;
        addToast("Memory pinned", "success");
      }
      if (onUpdate) onUpdate({ ...memory });
    } catch {
      addToast("Failed to update pin status", "error");
    } finally {
      setPinning(false);
    }
  }

  return (
    <dialog ref={ref} className="modal" onClose={onClose}>
      <div className="rounded-2xl bg-base-100 border border-base-content/5 p-6 max-w-2xl w-full">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Badge text={memory.memory_type} />
            <span className="text-sm text-base-content/40">
              {memory.domain}
            </span>
            {memory.pinned && (
              <span className="inline-flex items-center gap-1 rounded-md bg-amber-500/10 text-amber-400 px-1.5 py-0.5 text-[10px] font-medium">
                <PushPin size={10} weight="fill" /> Pinned
              </span>
            )}
            {memory.durability === "permanent" && (
              <span className="inline-flex items-center gap-0.5 rounded-md bg-emerald-500/10 text-emerald-400 px-1.5 py-0.5 text-[10px] font-medium">
                <Lock size={10} weight="fill" /> Permanent
              </span>
            )}
            {memory.durability === "durable" && (
              <span className="inline-flex items-center gap-0.5 rounded-md bg-cyan-500/10 text-cyan-400 px-1.5 py-0.5 text-[10px] font-medium">
                <ShieldCheck size={10} weight="fill" /> Durable
              </span>
            )}
          </div>
          <div className="flex items-center gap-1">
            <button
              className={`rounded-lg p-1.5 transition-colors ${
                memory.pinned
                  ? "text-amber-400 hover:bg-amber-500/10"
                  : "text-base-content/30 hover:bg-base-content/5"
              }`}
              onClick={togglePin}
              disabled={pinning}
              title={
                memory.pinned ? "Unpin memory" : "Pin memory (immune to decay)"
              }
            >
              <PushPin size={16} weight={memory.pinned ? "fill" : "regular"} />
            </button>
            <button
              className="rounded-lg p-1.5 hover:bg-base-content/5 transition-colors"
              onClick={onClose}
            >
              <X size={16} />
            </button>
          </div>
        </div>

        <p className="font-mono text-xs text-base-content/30 mb-3">
          ID: {memory.id}
        </p>

        {shouldSuggestPin(memory) && (
          <div className="flex items-center gap-2 rounded-lg border border-violet-500/30 bg-violet-500/5 p-3 mb-4">
            <Sparkle
              size={16}
              weight="fill"
              className="text-violet-400 shrink-0"
            />
            <p className="text-xs text-violet-300 flex-1">
              This memory has high importance ({memory.importance.toFixed(2)})
              and {memory.access_count} accesses — consider pinning it to
              prevent decay.
            </p>
            <button
              className="rounded-lg bg-violet-600 px-3 py-1 text-xs font-medium text-white hover:bg-violet-500 transition-colors shrink-0"
              onClick={togglePin}
              disabled={pinning}
            >
              Pin now
            </button>
          </div>
        )}

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
            { label: "Durability", val: memory.durability || "ephemeral" },
            {
              label: "Initial Imp.",
              val:
                memory.initial_importance != null
                  ? memory.initial_importance.toFixed(3)
                  : "—",
            },
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

        <ForceProfile memoryId={memory.id} />
      </div>
      <form method="dialog" className="modal-backdrop">
        <button>close</button>
      </form>
    </dialog>
  );
}
