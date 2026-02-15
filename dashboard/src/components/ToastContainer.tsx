import type { Toast as ToastData } from "../hooks/useToast";
import Toast from "./Toast";

interface Props {
  toasts: ToastData[];
  onDismiss: (id: number) => void;
}

export default function ToastContainer({ toasts, onDismiss }: Props) {
  if (toasts.length === 0) return null;
  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm">
      {toasts.map((t) => (
        <Toast key={t.id} toast={t} onDismiss={onDismiss} />
      ))}
    </div>
  );
}
