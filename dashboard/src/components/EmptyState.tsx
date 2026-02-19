import { Archive } from "@phosphor-icons/react";

interface Props {
  message: string;
  action?: React.ReactNode;
}

export default function EmptyState({ message, action }: Props) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-zinc-400 dark:text-zinc-500">
      <Archive size={48} className="mb-4 opacity-50" />
      <p className="text-sm font-medium">{message}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
