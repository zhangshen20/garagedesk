import { useEffect, useRef, useState } from "react";
import { Car, Send, Loader2, MapPin, Clock, Phone } from "lucide-react";
import { api } from "../api";

interface Turn {
  role: "user" | "assistant";
  text: string;
  error?: boolean;
}

const GREETING = "Hi! I'm the front desk at Sunshine North Mechanic. Book a service, check on your car, or ask about hours.";
const QUICK = ["Book a logbook service", "Do you do roadworthy certificates?", "What are your hours?", "Is my car ready?"];

function sessionId(): string {
  const KEY = "garagedesk.web_session";
  try {
    const existing = localStorage.getItem(KEY);
    if (existing) return existing;
    const id = `web-${Math.random().toString(36).slice(2, 10)}`;
    localStorage.setItem(KEY, id);
    return id;
  } catch {
    return `web-${Math.random().toString(36).slice(2, 10)}`;
  }
}

export default function PublicChat() {
  const [sid] = useState(sessionId);
  const [turns, setTurns] = useState<Turn[]>([{ role: "assistant", text: GREETING }]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [shop, setShop] = useState<{ hours: string; address: string } | null>(null);
  const scroller = useRef<HTMLDivElement>(null);

  useEffect(() => {
    document.title = "Sunshine North Mechanic · Chat";
    api.overview().then((o) => setShop({ hours: o.shop.hours, address: o.shop.address })).catch(() => undefined);
  }, []);

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [turns, busy]);

  async function send(msg?: string) {
    const t = (msg ?? text).trim();
    if (!t || busy) return;
    setText("");
    setTurns((xs) => [...xs, { role: "user", text: t }]);
    setBusy(true);
    try {
      const r = await api.chatCustomer(t, sid, "web");
      setTurns((xs) => [...xs, { role: "assistant", text: r.reply }]);
    } catch (e) {
      setTurns((xs) => [...xs, { role: "assistant", text: "Sorry, something went wrong on our end. Please try again or give us a call.", error: true }]);
      void e;
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-100 flex flex-col">
      <header className="bg-slate-900 text-white">
        <div className="mx-auto max-w-2xl px-4 py-4 flex items-center gap-3">
          <span className="grid h-11 w-11 place-items-center rounded-xl bg-brand-500 text-white shadow-sm">
            <Car size={24} />
          </span>
          <div className="leading-tight">
            <div className="font-semibold text-lg">Sunshine North Mechanic</div>
            <div className="text-xs text-slate-300">Sunshine North, Melbourne · Logbook servicing, repairs, roadworthy</div>
          </div>
        </div>
        {shop && (
          <div className="border-t border-slate-800">
            <div className="mx-auto max-w-2xl px-4 py-2 flex flex-wrap gap-x-5 gap-y-1 text-xs text-slate-300">
              <span className="inline-flex items-center gap-1.5"><Clock size={12} className="text-brand-300" /> {shop.hours}</span>
              <span className="inline-flex items-center gap-1.5"><MapPin size={12} className="text-brand-300" /> {shop.address}</span>
              <span className="inline-flex items-center gap-1.5"><Phone size={12} className="text-brand-300" /> Or call the workshop</span>
            </div>
          </div>
        )}
      </header>

      <main className="flex-1 flex flex-col mx-auto w-full max-w-2xl px-3 sm:px-4 py-4">
        <div className="card flex-1 flex flex-col overflow-hidden min-h-[60vh]">
          <div className="px-4 py-2.5 border-b border-slate-100 flex items-center gap-2 text-sm">
            <span className="relative flex h-2.5 w-2.5">
              <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60 animate-ping" />
              <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-500" />
            </span>
            <span className="font-medium text-slate-800">Front desk</span>
            <span className="text-slate-400">· usually replies in seconds</span>
          </div>

          <div ref={scroller} className="flex-1 overflow-y-auto px-4 py-4 space-y-3 bg-slate-50/60">
            {turns.map((t, i) =>
              t.role === "user" ? (
                <div key={i} className="flex justify-end">
                  <div className="max-w-[82%] rounded-2xl rounded-br-md bg-brand-600 text-white px-4 py-2.5 text-[15px] whitespace-pre-wrap">{t.text}</div>
                </div>
              ) : (
                <div key={i} className="flex items-end gap-2">
                  <span className="grid h-7 w-7 place-items-center rounded-full bg-slate-900 text-brand-300 shrink-0">
                    <Car size={14} />
                  </span>
                  <div className={`max-w-[82%] rounded-2xl rounded-bl-md px-4 py-2.5 text-[15px] whitespace-pre-wrap border ${t.error ? "bg-red-50 border-red-200 text-red-800" : "bg-white border-slate-200 text-slate-800"}`}>{t.text}</div>
                </div>
              ),
            )}
            {busy && (
              <div className="flex items-end gap-2">
                <span className="grid h-7 w-7 place-items-center rounded-full bg-slate-900 text-brand-300 shrink-0">
                  <Car size={14} />
                </span>
                <div className="rounded-2xl rounded-bl-md bg-white border border-slate-200 px-4 py-3 inline-flex gap-1">
                  <span className="h-1.5 w-1.5 rounded-full bg-slate-400 animate-bounce [animation-delay:-0.2s]" />
                  <span className="h-1.5 w-1.5 rounded-full bg-slate-400 animate-bounce [animation-delay:-0.1s]" />
                  <span className="h-1.5 w-1.5 rounded-full bg-slate-400 animate-bounce" />
                </div>
              </div>
            )}
          </div>

          {turns.length <= 1 && (
            <div className="flex gap-1.5 overflow-x-auto px-3 pt-2.5 pb-1 bg-white border-t border-slate-100 [scrollbar-width:none]">
              {QUICK.map((q) => (
                <button key={q} onClick={() => void send(q)} className="chip shrink-0 border-slate-300 bg-white text-slate-700 hover:border-brand-400 hover:text-brand-700">
                  {q}
                </button>
              ))}
            </div>
          )}

          <form
            className="flex items-center gap-2 px-3 py-3 bg-white border-t border-slate-100"
            onSubmit={(e) => {
              e.preventDefault();
              void send();
            }}
          >
            <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Type a message…" className="input !py-2.5 !text-[15px]" disabled={busy} autoFocus />
            <button type="submit" className="btn-primary !rounded-full !p-2.5" disabled={busy || !text.trim()} aria-label="Send">
              {busy ? <Loader2 size={18} className="animate-spin" /> : <Send size={18} />}
            </button>
          </form>
        </div>
        <p className="text-center text-[11px] text-slate-400 mt-3">
          Chat is handled by our AI front desk and a human checks every booking. Session <span className="font-mono">{sid}</span>
        </p>
      </main>
    </div>
  );
}
