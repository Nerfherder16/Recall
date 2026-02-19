import { useState } from "react";
import { PushPin, Sparkle, Lock, ShieldCheck } from "@phosphor-icons/react";
import { api } from "../api/client";
import type { MemoryDetail } from "../api/types";
import Badge from "./Badge";
import { ForceProfile } from "./ForceProfile";
import { useToastContext } from "../context/ToastContext";
import { Modal } from "./common/Modal";
import { Button } from "./common/Button";
import { GlassCard } from "./common/GlassCard";
import { formatDate } from "../lib/utils";

function shouldSuggestPin(m: MemoryDetail): boolean {
  return !m.pinned && m.importance >= 0.7 && m.access_count >= 10;
}

interface Props {
  memory: MemoryDetail | null;
  onClose: () => void;
  onUpdate?: (updated: MemoryDetail) => void;
}

export default function MemoryDetailModal({
  memory,
  onClose,
  onUpdate,
}: Props) {
  const { addToast } = useToastContext();
  const [pinning, setPinning] = useState(false);

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
    <Modal open={!!memory} onClose={onClose} className="max-w-2xl">
      <div className="p-6">
        {/* Header */}
        <div className="flex items-center gap-2 mb-4 pr-8">
          <Badge text={memory.memory_type} />
          <span className="text-sm text-zinc-500 dark:text-zinc-400">
            {memory.domain}
          </span>
          {memory.pinned && (
            <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/10 text-amber-400 px-2 py-0.5 text-[10px] font-medium ring-1 ring-amber-500/20">
              <PushPin size={10} weight="fill" /> Pinned
            </span>
          )}
          {memory.durability === "permanent" && (
            <span className="inline-flex items-center gap-0.5 rounded-full bg-emerald-500/10 text-emerald-400 px-2 py-0.5 text-[10px] font-medium ring-1 ring-emerald-500/20">
              <Lock size={10} weight="fill" /> Permanent
            </span>
          )}
          {memory.durability === "durable" && (
            <span className="inline-flex items-center gap-0.5 rounded-full bg-cyan-500/10 text-cyan-400 px-2 py-0.5 text-[10px] font-medium ring-1 ring-cyan-500/20">
              <ShieldCheck size={10} weight="fill" /> Durable
            </span>
          )}
          <button
            className={`ml-auto rounded-lg p-1.5 transition-colors ${
              memory.pinned
                ? "text-amber-400 hover:bg-amber-500/10"
                : "text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800"
            }`}
            onClick={togglePin}
            disabled={pinning}
            title={
              memory.pinned ? "Unpin memory" : "Pin memory (immune to decay)"
            }
          >
            <PushPin size={16} weight={memory.pinned ? "fill" : "regular"} />
          </button>
        </div>

        <p className="font-mono text-xs text-zinc-400 dark:text-zinc-500 mb-3">
          ID: {memory.id}
        </p>

        {/* Pin suggestion banner */}
        {shouldSuggestPin(memory) && (
          <div className="flex items-center gap-2 rounded-xl border border-violet-500/30 bg-violet-500/5 p-3 mb-4">
            <Sparkle
              size={16}
              weight="fill"
              className="text-violet-400 shrink-0"
            />
            <p className="text-xs text-violet-400 flex-1">
              This memory has high importance ({memory.importance.toFixed(2)})
              and {memory.access_count} accesses — consider pinning it.
            </p>
            <Button
              variant="primary"
              size="sm"
              onClick={togglePin}
              disabled={pinning}
            >
              Pin now
            </Button>
          </div>
        )}

        {/* Content */}
        <div className="bg-zinc-100 dark:bg-zinc-800/60 rounded-xl p-4 text-sm whitespace-pre-wrap mb-4 border border-zinc-200 dark:border-white/[0.06] font-mono text-zinc-800 dark:text-zinc-200">
          {memory.content}
        </div>

        {/* Tags */}
        {memory.tags.length > 0 && (
          <div className="flex flex-wrap gap-1 mb-4">
            {memory.tags.map((t) => (
              <span
                key={t}
                className="inline-flex items-center rounded-full bg-zinc-100 dark:bg-zinc-800 text-zinc-500 dark:text-zinc-400 px-2.5 py-0.5 text-[11px] font-medium ring-1 ring-zinc-200 dark:ring-zinc-700"
              >
                {t}
              </span>
            ))}
          </div>
        )}

        {/* Metrics bento grid */}
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
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
                  : "\u2014",
            },
          ].map((item) => (
            <GlassCard key={item.label} className="p-3 text-center">
              <p className="font-mono text-[10px] font-medium uppercase tracking-[0.15em] text-zinc-400 dark:text-zinc-500">
                {item.label}
              </p>
              <p className="font-display font-semibold text-lg tabular-nums text-zinc-900 dark:text-zinc-100 mt-0.5">
                {item.val}
              </p>
            </GlassCard>
          ))}
        </div>

        {/* Metadata footer */}
        <div className="flex flex-wrap gap-4 mt-4 text-xs text-zinc-400 dark:text-zinc-500 font-mono">
          <span>Source: {memory.source}</span>
          {memory.stored_by && <span>Stored by: {memory.stored_by}</span>}
          <span>Created: {formatDate(memory.created_at)}</span>
          <span>Last access: {formatDate(memory.last_accessed)}</span>
        </div>

        <ForceProfile memoryId={memory.id} />
      </div>
    </Modal>
  );
}
