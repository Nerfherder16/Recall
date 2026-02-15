import { createContext, useContext } from "react";
import { useToast, type Toast, type ToastType } from "../hooks/useToast";
import ToastContainer from "../components/ToastContainer";

interface ToastCtx {
  toasts: Toast[];
  addToast: (message: string, type?: ToastType) => void;
  removeToast: (id: number) => void;
}

const Ctx = createContext<ToastCtx>({
  toasts: [],
  addToast: () => {},
  removeToast: () => {},
});

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const value = useToast();
  return (
    <Ctx.Provider value={value}>
      {children}
      <ToastContainer toasts={value.toasts} onDismiss={value.removeToast} />
    </Ctx.Provider>
  );
}

export function useToastContext() {
  return useContext(Ctx);
}
