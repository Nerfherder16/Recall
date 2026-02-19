import { cn } from "../../lib/utils";

interface Props {
  children: React.ReactNode;
  className?: string;
  hover?: boolean;
  glow?: boolean;
  onClick?: () => void;
}

export function GlassCard({
  children,
  className,
  hover = false,
  glow = false,
  onClick,
}: Props) {
  return (
    <div
      className={cn(
        "rounded-2xl border border-white/[0.06] dark:border-white/[0.06] border-zinc-200/80",
        "bg-white/60 dark:bg-zinc-800/40",
        "backdrop-blur-xl",
        hover &&
          "transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg hover:border-white/[0.1] dark:hover:border-white/[0.1] hover:border-zinc-300",
        glow && "shadow-glow",
        onClick && "cursor-pointer",
        className,
      )}
      onClick={onClick}
    >
      {children}
    </div>
  );
}
