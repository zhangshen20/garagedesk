import { useEffect, useRef, useState } from "react";
import { Bot, X, Send, Loader2, Sparkles } from "lucide-react";
import { api, type ChatStep } from "../api";
import Markdown from "./Markdown";
import ToolSteps from "./ToolSteps";

interface Turn {
  role: "user" | "assistant";
  text: string;
  steps?: ChatStep[];
  model?: string;
  error?: boolean;
}

const SUGGESTIONS = ["What's on today?", "Order brake pads for job 3", "Invoice job 4", "Who still owes us money?", "Add expense: $64 brake cleaner"];

/** Floating back-office chat available on every owner page. Fires `garagedesk:changed`
 * after each reply so the page underneath can refresh its data. */
export default function DeskAssistant({ model }: { model?: string }) {
  const [open, setOpen] = useState(false);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [turns, busy, open]);

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 50);
  }, [open]);

  async function send(msg?: string) {
    const t = (msg ?? text).trim();
    if (!t || busy) return;
    setText("");
    setTurns((xs) => [...xs, { role: "user", text: t }]);
    setBusy(true);
    try {
      const r = await api.chatOwner(t);
      setTurns((xs) => [...xs, { role: "assistant", text: r.reply, steps: r.steps, model: r.model }]);
      window.dispatchEvent(new CustomEvent("garagedesk:changed"));
    } catch (e) {
      setTurns((xs) => [...xs, { role: "assistant", text: `Something went wrong: ${e instanceof Error ? e.message : String(e)}`, error: true }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      {!open && (
        <button
          onClick={() => setOpen(true)}
          className="fixed bottom-[4.5rem] md:bottom-6 right-4 md:right-6 z-40 inline-flex items-center gap-2 rounded-full bg-slate-900 text-white pl-3.5 pr-4 py-2.5 text-sm font-medium shadow-float hover:bg-slate-800 transition-colors"
        >
          <Bot size={18} className="text-brand-300" />
          Ask the desk
        </button>
      )}

      {open && (
        <div className="fixed z-50 inset-x-2 bottom-2 md:inset-auto md:right-6 md:bottom-6 md:w-[420px] h-[min(620px,calc(100vh-1rem))] md:h-[min(620px,calc(100vh-3rem))] card shadow-float flex flex-col overflow-hidden fade-up">
          <header className="flex items-center justify-between gap-2 px-4 py-3 border-b border-slate-100 bg-slate-900 text-white">
            <div className="flex items-center gap-2.5">
              <span className="grid h-8 w-8 place-items-center rounded-lg bg-slate-800">
                <Bot size={18} className="text-brand-300" />
              </span>
              <div>
                <div className="text-sm font-semibold leading-tight">Desk assistant</div>
                <div className="text-[11px] text-slate-400 leading-tight truncate max-w-[260px]">{model ? `Back-office agent · ${model.split("/").pop()}` : "Back-office agent"}</div>
              </div>
            </div>
            <button onClick={() => setOpen(false)} className="rounded-md p-1.5 text-slate-300 hover:bg-slate-800 hover:text-white" aria-label="Close">
              <X size={16} />
            </button>
          </header>

          <div ref={scroller} className="flex-1 overflow-y-auto px-4 py-3 space-y-3 bg-slate-50/60">
            {turns.length === 0 && (
              <div className="pt-2">
                <div className="flex items-start gap-2 text-sm text-slate-700">
                  <Sparkles size={16} className="mt-0.5 text-brand-500 shrink-0" />
                  <p>
                    I'm the back office. I can read the board, order parts, raise invoices, record payments and log expenses. Try one of these:
                  </p>
                </div>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {SUGGESTIONS.map((s) => (
                    <button key={s} onClick={() => void send(s)} className="chip border-slate-300 bg-white text-slate-700 hover:border-brand-400 hover:text-brand-700">
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {turns.map((t, i) =>
              t.role === "user" ? (
                <div key={i} className="flex justify-end">
                  <div className="max-w-[85%] rounded-2xl rounded-br-md bg-brand-600 text-white px-3.5 py-2 text-sm whitespace-pre-wrap">{t.text}</div>
                </div>
              ) : (
                <div key={i} className="flex justify-start">
                  <div className={`max-w-[92%] rounded-2xl rounded-bl-md px-3.5 py-2 border ${t.error ? "bg-red-50 border-red-200" : "bg-white border-slate-200"}`}>
                    <Markdown text={t.text} />
                    <ToolSteps steps={t.steps} />
                  </div>
                </div>
              ),
            )}
            {busy && (
              <div className="flex items-center gap-2 text-xs text-slate-500 pl-1">
                <Loader2 size={13} className="animate-spin" /> Working…
              </div>
            )}
          </div>

          {turns.length > 0 && (
            <div className="flex gap-1.5 overflow-x-auto px-3 pt-2 pb-1 border-t border-slate-100 bg-white [scrollbar-width:none]">
              {SUGGESTIONS.map((s) => (
                <button key={s} onClick={() => void send(s)} disabled={busy} className="chip shrink-0 border-slate-200 bg-slate-50 text-slate-600 hover:border-brand-400 hover:text-brand-700">
                  {s}
                </button>
              ))}
            </div>
          )}

          <form
            className="flex items-center gap-2 px-3 py-2.5 bg-white border-t border-slate-100"
            onSubmit={(e) => {
              e.preventDefault();
              void send();
            }}
          >
            <input ref={inputRef} value={text} onChange={(e) => setText(e.target.value)} placeholder="Ask the back office…" className="input" disabled={busy} />
            <button type="submit" className="btn-primary !px-2.5 !py-2" disabled={busy || !text.trim()} aria-label="Send">
              <Send size={16} />
            </button>
          </form>
        </div>
      )}
    </>
  );
}
