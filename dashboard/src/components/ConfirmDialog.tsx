import { useRef, useEffect } from "react";

interface Props {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  confirmClass?: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = "Confirm",
  confirmClass,
  onConfirm,
  onCancel,
}: Props) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    if (open) {
      ref.current?.showModal();
    } else {
      ref.current?.close();
    }
  }, [open]);

  const btnColor =
    confirmClass === "btn-error"
      ? "bg-error text-error-content hover:bg-error/90"
      : "bg-primary text-primary-content hover:bg-primary/90";

  return (
    <dialog ref={ref} className="modal" onClose={onCancel}>
      <div className="rounded-2xl bg-base-100 border border-base-content/5 p-6 max-w-sm w-full">
        <h3 className="font-semibold text-lg">{title}</h3>
        <p className="py-4 text-sm text-base-content/60">{message}</p>
        <div className="flex justify-end gap-2">
          <button
            className="rounded-lg px-4 py-2 text-sm hover:bg-base-content/5 transition-colors"
            onClick={onCancel}
          >
            Cancel
          </button>
          <button
            className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors ${btnColor}`}
            onClick={onConfirm}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
      <form method="dialog" className="modal-backdrop">
        <button>close</button>
      </form>
    </dialog>
  );
}
