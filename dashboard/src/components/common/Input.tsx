import { cn } from "../../lib/utils";

const baseInput = [
  "w-full rounded-xl border bg-white dark:bg-zinc-900/80",
  "border-zinc-200 dark:border-white/[0.06]",
  "px-3 py-2 text-sm",
  "text-zinc-900 dark:text-zinc-100",
  "placeholder-zinc-400 dark:placeholder-zinc-500",
  "focus:border-violet-500/50 focus:outline-none focus:ring-2 focus:ring-violet-500/20",
  "transition-colors duration-200",
].join(" ");

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  containerClass?: string;
}

export function Input({ className, containerClass, ...rest }: InputProps) {
  return (
    <div className={containerClass}>
      <input className={cn(baseInput, className)} {...rest} />
    </div>
  );
}

interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  containerClass?: string;
}

export function Select({
  className,
  containerClass,
  children,
  ...rest
}: SelectProps) {
  return (
    <div className={containerClass}>
      <select className={cn(baseInput, "cursor-pointer", className)} {...rest}>
        {children}
      </select>
    </div>
  );
}

interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  containerClass?: string;
}

export function Textarea({
  className,
  containerClass,
  ...rest
}: TextareaProps) {
  return (
    <div className={containerClass}>
      <textarea
        className={cn(baseInput, "resize-y min-h-[80px]", className)}
        {...rest}
      />
    </div>
  );
}
