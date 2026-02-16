import type { Toast as ToastData } from "../hooks/useToast";

const typeStyles: Record<string, string> = {
  success: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  error: "bg-red-500/10 text-red-400 border-red-500/20",
  info: "bg-blue-500/10 text-blue-400 border-blue-500/20",
};

interface Props {
  toast: ToastData;
  onDismiss: (id: number) => void;
}

export default function Toast({ toast, onDismiss }: Props) {
  return (
    <div
      className={`rounded-lg border px-4 py-2.5 text-sm animate-slide-in cursor-pointer ${typeStyles[toast.type] || typeStyles.info}`}
      onClick={() => onDismiss(toast.id)}
    >
      <span>{toast.message}</span>
    </div>
  );
}
