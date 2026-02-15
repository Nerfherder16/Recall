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
  confirmClass = "btn-error",
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

  return (
    <dialog ref={ref} className="modal" onClose={onCancel}>
      <div className="modal-box">
        <h3 className="font-bold text-lg">{title}</h3>
        <p className="py-4 text-sm text-base-content/70">{message}</p>
        <div className="modal-action">
          <button className="btn btn-ghost" onClick={onCancel}>
            Cancel
          </button>
          <button className={`btn ${confirmClass}`} onClick={onConfirm}>
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
