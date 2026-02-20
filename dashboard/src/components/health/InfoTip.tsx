import { useState, useRef, useEffect } from "react";
import { Info } from "@phosphor-icons/react";

interface Props {
  text: string;
}

export function InfoTip({ text }: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    function handle(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, [open]);

  return (
    <div className="relative inline-flex" ref={ref}>
      <button
        type="button"
        className="text-zinc-400 hover:text-zinc-300 transition-colors"
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onClick={() => setOpen((v) => !v)}
        aria-label="More info"
      >
        <Info size={14} weight="fill" />
      </button>
      {open && (
        <div className="absolute z-50 bottom-full left-1/2 -translate-x-1/2 mb-2 w-64 px-3 py-2 rounded-lg bg-zinc-900 border border-white/10 shadow-xl">
          <p className="text-[11px] text-zinc-300 leading-relaxed">{text}</p>
          <div className="absolute top-full left-1/2 -translate-x-1/2 -mt-px w-2 h-2 rotate-45 bg-zinc-900 border-r border-b border-white/10" />
        </div>
      )}
    </div>
  );
}
