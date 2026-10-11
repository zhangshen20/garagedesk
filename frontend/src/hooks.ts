import { useCallback, useEffect, useRef, useState } from "react";

export interface Loadable<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

/** Fetch once (and optionally on an interval). `refresh` re-fetches without flashing the loader. */
export function useLoad<T>(fn: () => Promise<T>, deps: unknown[] = [], intervalMs?: number): Loadable<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  const refresh = useCallback(async () => {
    try {
      const d = await fnRef.current();
      setData(d);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    setLoading(true);
    void refresh();
    if (!intervalMs) return;
    const id = setInterval(() => {
      if (document.visibilityState === "visible") void refresh();
    }, intervalMs);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refresh, intervalMs, ...deps]);

  return { data, loading, error, refresh };
}

/** Re-run `refresh` whenever the desk assistant (or any panel) reports a data change. */
export function useRefreshOnChange(refresh: () => Promise<void> | void) {
  useEffect(() => {
    const h = () => void refresh();
    window.addEventListener("garagedesk:changed", h);
    return () => window.removeEventListener("garagedesk:changed", h);
  }, [refresh]);
}

/** Small toast queue. */
export interface Toast {
  id: number;
  text: string;
  tone: "ok" | "err";
}

let toastSeq = 1;
export function useToasts() {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((text: string, tone: Toast["tone"] = "ok") => {
    const id = toastSeq++;
    setToasts((t) => [...t, { id, text, tone }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 3500);
  }, []);
  return { toasts, push };
}
