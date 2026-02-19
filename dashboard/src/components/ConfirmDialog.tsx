import { Modal } from "./common/Modal";
import { Button } from "./common/Button";

interface Props {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = "Confirm",
  danger = true,
  onConfirm,
  onCancel,
}: Props) {
  return (
    <Modal
      open={open}
      onClose={onCancel}
      className="max-w-sm"
      showClose={false}
    >
      <div className="p-6">
        <h3 className="font-display font-semibold text-lg text-zinc-900 dark:text-zinc-50">
          {title}
        </h3>
        <p className="py-4 text-sm text-zinc-500 dark:text-zinc-400">
          {message}
        </p>
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
          <Button variant={danger ? "danger" : "primary"} onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
