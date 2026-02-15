import type { Toast as ToastData } from "../hooks/useToast";

const alertClass: Record<string, string> = {
  success: "alert-success",
  error: "alert-error",
  info: "alert-info",
};

interface Props {
  toast: ToastData;
  onDismiss: (id: number) => void;
}

export default function Toast({ toast, onDismiss }: Props) {
  return (
    <div
      className={`alert ${alertClass[toast.type]} shadow-lg text-sm py-2 px-4 animate-slide-in cursor-pointer`}
      onClick={() => onDismiss(toast.id)}
    >
      <span>{toast.message}</span>
    </div>
  );
}
