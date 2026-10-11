import { useEffect, useState } from "react";
import { CheckCircle2, AlertCircle } from "lucide-react";

interface ToastItem {
  id: number;
  text: string;
  tone: "ok" | "err";
}

type Listener = (t: ToastItem) => void;
const listeners = new Set<Listener>();
let seq = 1;

/** Fire a toast from anywhere (pages, panels). */
export function toast(text: string, tone: "ok" | "err" = "ok") {
  const t = { id: seq++, text, tone };
  listeners.forEach((l) => l(t));
}

export default function Toaster() {
  const [items, setItems] = useState<ToastItem[]>([]);
  useEffect(() => {
    const l: Listener = (t) => {
      setItems((xs) => [...xs, t]);
      setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== t.id)), 3800);
    };
    listeners.add(l);
    return () => {
      listeners.delete(l);
    };
  }, []);
  if (!items.length) return null;
  return (
    <div className="fixed bottom-20 md:bottom-6 left-1/2 -translate-x-1/2 z-[60] flex flex-col gap-2 items-center pointer-events-none">
      {items.map((t) => (
        <div
          key={t.id}
          className={`fade-up pointer-events-auto flex items-center gap-2 rounded-lg px-3.5 py-2 text-sm shadow-float border ${
            t.tone === "ok" ? "bg-slate-900 text-white border-slate-800" : "bg-red-600 text-white border-red-700"
          }`}
        >
          {t.tone === "ok" ? <CheckCircle2 size={16} className="text-emerald-300" /> : <AlertCircle size={16} />}
          <span>{t.text}</span>
        </div>
      ))}
    </div>
  );
}
