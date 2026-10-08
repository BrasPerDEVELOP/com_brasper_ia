"use client";
import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";

// Notificaciones no bloqueantes (reemplazan alert()).
type Kind = "ok" | "err" | "warn" | "info";
interface Toast { id: number; kind: Kind; text: string }
interface Ctx { toast: (text: string, kind?: Kind) => void }

const ToastCtx = createContext<Ctx>({ toast: () => {} });
export const useToast = () => useContext(ToastCtx);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const seq = useRef(0);
  const dismiss = useCallback((id: number) => setItems(l => l.filter(t => t.id !== id)), []);
  const toast = useCallback((text: string, kind: Kind = "info") => {
    const id = ++seq.current;
    setItems(l => [...l.slice(-3), { id, kind, text }]);
    window.setTimeout(() => dismiss(id), kind === "err" ? 7000 : 3500);
  }, [dismiss]);
  const value = useMemo(() => ({ toast }), [toast]);
  return (
    <ToastCtx.Provider value={value}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {items.map(t => (
          <div key={t.id} className={`toast ${t.kind}`}>
            <span>{t.text}</span>
            <button onClick={() => dismiss(t.id)} aria-label="Cerrar">×</button>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}
