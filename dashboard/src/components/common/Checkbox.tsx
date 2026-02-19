import { cn } from "../../lib/utils";

interface Props extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
}

export function Checkbox({ className, label, id, ...rest }: Props) {
  return (
    <label
      htmlFor={id}
      className={cn("inline-flex items-center gap-2 cursor-pointer", className)}
    >
      <input
        type="checkbox"
        id={id}
        className={cn(
          "h-4 w-4 rounded border-zinc-300 dark:border-zinc-600",
          "bg-white dark:bg-zinc-800",
          "text-violet-600 focus:ring-violet-500/50 focus:ring-2 focus:ring-offset-0",
          "cursor-pointer accent-violet-600",
        )}
        {...rest}
      />
      {label && (
        <span className="text-sm text-zinc-700 dark:text-zinc-300 select-none">
          {label}
        </span>
      )}
    </label>
  );
}
