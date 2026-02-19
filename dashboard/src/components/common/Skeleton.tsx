import { cn } from "../../lib/utils";

interface Props {
  className?: string;
}

export function Skeleton({ className }: Props) {
  return <div className={cn("animate-shimmer rounded-lg", className)} />;
}

export function StatCardSkeleton() {
  return (
    <div className="rounded-2xl border border-white/[0.06] dark:border-white/[0.06] border-zinc-200/80 bg-white/60 dark:bg-zinc-800/40 backdrop-blur-xl p-6 space-y-3">
      <Skeleton className="h-3 w-20" />
      <Skeleton className="h-8 w-16" />
      <Skeleton className="h-3 w-32" />
    </div>
  );
}

export function CardSkeleton() {
  return (
    <div className="rounded-2xl border border-white/[0.06] dark:border-white/[0.06] border-zinc-200/80 bg-white/60 dark:bg-zinc-800/40 backdrop-blur-xl p-6 space-y-4">
      <Skeleton className="h-4 w-3/4" />
      <Skeleton className="h-3 w-full" />
      <Skeleton className="h-3 w-2/3" />
    </div>
  );
}
