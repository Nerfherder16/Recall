import { motion, AnimatePresence } from "framer-motion";
import { Trash, X } from "@phosphor-icons/react";
import { Button } from "./common/Button";

interface Props {
  count: number;
  onDelete: () => void;
  onClear: () => void;
}

export default function SelectionToolbar({ count, onDelete, onClear }: Props) {
  return (
    <AnimatePresence>
      {count > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 20 }}
          className="fixed bottom-16 left-1/2 -translate-x-1/2 z-40 rounded-2xl bg-white/80 dark:bg-zinc-800/80 backdrop-blur-xl border border-zinc-200 dark:border-white/[0.06] px-4 py-2.5 flex items-center gap-3 shadow-2xl"
        >
          <span className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
            {count} selected
          </span>
          <Button variant="danger" size="sm" onClick={onDelete}>
            <Trash size={14} />
            Delete
          </Button>
          <Button variant="ghost" size="sm" onClick={onClear}>
            <X size={14} />
            Clear
          </Button>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
