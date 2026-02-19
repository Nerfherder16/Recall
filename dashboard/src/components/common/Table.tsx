import { cn } from "../../lib/utils";

interface Props {
  children: React.ReactNode;
  className?: string;
}

export function Table({ children, className }: Props) {
  return (
    <div className="overflow-x-auto">
      <table className={cn("w-full text-sm", className)}>{children}</table>
    </div>
  );
}

export function TableHead({ children, className }: Props) {
  return (
    <thead>
      <tr
        className={cn(
          "border-b border-zinc-200 dark:border-white/[0.06]",
          "text-xs font-mono uppercase tracking-wider text-zinc-400 dark:text-zinc-500",
          className,
        )}
      >
        {children}
      </tr>
    </thead>
  );
}

export function TableBody({ children, className }: Props) {
  return <tbody className={className}>{children}</tbody>;
}

interface RowProps extends Props {
  onClick?: () => void;
}

export function TableRow({ children, className, onClick }: RowProps) {
  return (
    <tr
      className={cn(
        "border-b border-zinc-100 dark:border-white/[0.03] last:border-0",
        "transition-colors hover:bg-zinc-50 dark:hover:bg-white/[0.02]",
        onClick && "cursor-pointer",
        className,
      )}
      onClick={onClick}
    >
      {children}
    </tr>
  );
}

interface CellProps extends Props {
  header?: boolean;
}

export function TableCell({ children, className, header }: CellProps) {
  const Tag = header ? "th" : "td";
  return (
    <Tag
      className={cn("px-4 py-3 text-left", header && "font-medium", className)}
    >
      {children}
    </Tag>
  );
}
