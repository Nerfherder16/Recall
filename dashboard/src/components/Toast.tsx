import { motion } from "framer-motion";
import type { Toast as ToastData } from "../hooks/useToast";

const typeStyles: Record<string, string> = {
  success:
    "bg-emerald-500/10 text-emerald-400 border-emerald-500/20 dark:bg-emerald-500/10",
  error: "bg-red-500/10 text-red-400 border-red-500/20 dark:bg-red-500/10",
  info: "bg-blue-500/10 text-blue-400 border-blue-500/20 dark:bg-blue-500/10",
};

interface Props {
  toast: ToastData;
  onDismiss: (id: number) => void;
}

export default function Toast({ toast, onDismiss }: Props) {
  return (
    <motion.div
      initial={{ opacity: 0, x: 80, scale: 0.95 }}
      animate={{ opacity: 1, x: 0, scale: 1 }}
      exit={{ opacity: 0, x: 80, scale: 0.95 }}
      transition={{ duration: 0.2 }}
      className={`rounded-xl border px-4 py-2.5 text-sm cursor-pointer backdrop-blur-xl ${typeStyles[toast.type] || typeStyles.info}`}
      onClick={() => onDismiss(toast.id)}
    >
      <span>{toast.message}</span>
    </motion.div>
  );
}
