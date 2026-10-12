/** The owner app: one big button for a mechanic who doesn't type.
 *
 * Tap to talk, tap when done ("Corolla ABC123, front pads, hour and a half, 350 all
 * up"), the way he'd tell the office on the phone. If the iPhone won't listen (Siri
 * dictation off, mic blocked, Home Screen app) it falls back to the keyboard's own
 * microphone. The draft invoice is read back out loud; one tap sends it to
 * whoever does the books for approval. Built for an iPhone on the workshop bench:
 * big targets, no menus, no login. */

import { useCallback, useEffect, useRef, useState } from "react";
import { Camera, Check, CircleDollarSign, Clock, Loader2, Mic, RotateCcw, Send, Square, Volume2, Wrench } from "lucide-react";
import { api, type OwnerJob, type OwnerResult, type OwnerToday } from "../api";
import { money } from "../format";

// --- speech in and out -----------------------------------------------------------------

type Recognition = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onresult: ((e: { resultIndex: number; results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }> }) => void) | null;
  onend: (() => void) | null;
  onstart: (() => void) | null;
  onerror: ((e: { error: string }) => void) | null;
};

function makeRecognition(): Recognition | null {
  const w = window as unknown as { SpeechRecognition?: new () => Recognition; webkitSpeechRecognition?: new () => Recognition };
  const Ctor = w.SpeechRecognition ?? w.webkitSpeechRecognition;
  if (!Ctor || !window.isSecureContext) return null;
  const r = new Ctor();
  r.lang = "en-AU";
  r.continuous = true;
  r.interimResults = true;
  return r;
}

/** Tell the server what the phone's microphone did. Fire and forget. */
function diag(event: string, detail: Record<string, unknown> = {}) {
  try {
    void fetch("/api/owner/diag", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ event, detail }),
      keepalive: true,
    }).catch(() => undefined);
  } catch {
    /* never let reporting break the page */
  }
}

function standalone(): boolean {
  const n = navigator as Navigator & { standalone?: boolean };
  return Boolean(n.standalone) || window.matchMedia?.("(display-mode: standalone)").matches;
}

function plain(text: string): string {
  return text.replace(/[*_`#>]/g, "").replace(/\s+/g, " ").trim();
}

function speak(text: string) {
  try {
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(plain(text));
    u.lang = "en-AU";
    u.rate = 1;
    window.speechSynthesis.speak(u);
  } catch {
    /* no speech synthesis: the text is on screen */
  }
}

/** Why the iPhone wouldn't listen, in words he can act on. */
function micProblem(code: string): string {
  if (code === "no-speech") return "I didn't hear anything. Tap the button and talk again.";
  if (code === "not-allowed" || code === "service-not-allowed")
    return "This iPhone isn't letting the page listen. Use the keyboard microphone for now: tap the box, then the microphone key. To fix it: open this link in Safari (not from the Home Screen), allow the microphone when asked, and make sure Settings, General, Keyboard, Enable Dictation is on.";
  if (code === "audio-capture") return "Another app is using the microphone. Close it and tap again, or use the keyboard microphone.";
  if (code === "network") return "No internet for the voice. Check the signal, or use the keyboard microphone.";
  return "The voice didn't start. Use the keyboard microphone instead.";
}

const TYPE_KEY = "garagedesk.owner.type";
// Some iPhones only start the microphone on a finished tap, not on a press.
const PRESS_KEY = "garagedesk.owner.pressfails";

function flag(key: string): boolean {
  try {
    return localStorage.getItem(key) === "1";
  } catch {
    return false;
  }
}

function setFlag(key: string, on: boolean) {
  try {
    if (on) localStorage.setItem(key, "1");
    else localStorage.removeItem(key);
  } catch {
    /* private mode: just this visit */
  }
}

const prefersTyping = () => flag(TYPE_KEY);
const rememberTyping = (on: boolean) => setFlag(TYPE_KEY, on);

/** iOS only lets a page speak after a tap; say nothing once inside the first tap. */
function unlockSpeech() {
  try {
    const u = new SpeechSynthesisUtterance("");
    window.speechSynthesis.speak(u);
  } catch {
    /* ignore */
  }
}

async function shrinkPhoto(file: File): Promise<string> {
  const url = URL.createObjectURL(file);
  try {
    const img = await new Promise<HTMLImageElement>((resolve, reject) => {
      const i = new Image();
      i.onload = () => resolve(i);
      i.onerror = reject;
      i.src = url;
    });
    const scale = Math.min(1, 1600 / Math.max(img.width, img.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(img.width * scale);
    canvas.height = Math.round(img.height * scale);
    canvas.getContext("2d")!.drawImage(img, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL("image/jpeg", 0.82).split(",")[1];
  } finally {
    URL.revokeObjectURL(url);
  }
}

// --- page ------------------------------------------------------------------------------

type Phase = "idle" | "listening" | "thinking";

export default function OwnerApp() {
  const [today, setToday] = useState<OwnerToday | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [heard, setHeard] = useState("");
  const [result, setResult] = useState<OwnerResult | null>(null);
  const [typed, setTyped] = useState("");
  const [busyJob, setBusyJob] = useState<number | null>(null);
  const [toast, setToast] = useState("");
  const recRef = useRef<Recognition | null>(null);
  const finalRef = useRef("");
  const photoRef = useRef<HTMLInputElement>(null);
  const receiptJob = useRef<number | null>(null);
  const canListen = useRef<boolean>(makeRecognition() !== null);
  const [typing, setTyping] = useState<boolean>(() => !canListen.current || prefersTyping());
  const [micNote, setMicNote] = useState("");
  const errRef = useRef("");
  const [pressing, setPressing] = useState(false);
  const phaseRef = useRef<Phase>("idle");
  phaseRef.current = phase;
  const pressAt = useRef(0);
  const startedBy = useRef<"press" | "tap">("tap");
  const startedOk = useRef(false);
  const stopOnTap = useRef(false);
  const pressFails = useRef(flag(PRESS_KEY));

  const refresh = useCallback(() => {
    api.ownerToday().then(setToday).catch(() => undefined);
  }, []);

  useEffect(() => {
    document.title = "GarageDesk · Owner";
    const w = window as unknown as Record<string, unknown>;
    const report = (mic: string) =>
      diag("open", {
        speech: Boolean(w.SpeechRecognition),
        webkitSpeech: Boolean(w.webkitSpeechRecognition),
        secure: window.isSecureContext,
        standalone: standalone(),
        mic,
        pressFails: pressFails.current,
        typing: prefersTyping(),
        build: document.querySelector<HTMLScriptElement>("script[src*='assets/']")?.src.split("/").pop() ?? "",
      });
    const perms = (navigator as Navigator & { permissions?: { query: (d: { name: string }) => Promise<{ state: string }> } }).permissions;
    if (perms) perms.query({ name: "microphone" }).then((p) => report(p.state), () => report("unknown"));
    else report("no-permissions-api");
    refresh();
    const t = setInterval(refresh, 10000);
    return () => clearInterval(t);
  }, [refresh]);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(""), 4000);
    return () => clearTimeout(t);
  }, [toast]);

  async function submitText(text: string) {
    const t = text.trim();
    if (!t) {
      setPhase("idle");
      return;
    }
    setPhase("thinking");
    setHeard(t);
    try {
      const r = await api.ownerVoice(t);
      setResult(r);
      speak(r.readback);
      refresh();
    } catch (e) {
      setResult({ kind: "reply", readback: "Sorry, something went wrong. Try again." });
      void e;
    } finally {
      setPhase("idle");
    }
  }

  function startListening(by: "press" | "tap") {
    window.speechSynthesis?.cancel();
    const rec = makeRecognition();
    if (!rec) {
      diag("no-speech-api");
      setTyping(true);
      return;
    }
    finalRef.current = "";
    errRef.current = "";
    startedBy.current = by;
    startedOk.current = false;
    setHeard("");
    setMicNote("");
    setResult(null);
    rec.onstart = () => {
      startedOk.current = true;
      diag("started", { by });
    };
    rec.onresult = (e) => {
      let interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i];
        if (r.isFinal) finalRef.current += r[0].transcript + " ";
        else interim += r[0].transcript;
      }
      setHeard((finalRef.current + interim).trim());
    };
    rec.onerror = (e) => {
      errRef.current = e.error;
      diag("error", { code: e.error, by, started: startedOk.current });
    };
    rec.onend = () => {
      recRef.current = null;
      const said = finalRef.current.trim();
      const err = errRef.current;
      diag("end", { by, words: said.split(/\s+/).filter(Boolean).length, err, started: startedOk.current });
      if (said) {
        void submitText(said);
        return;
      }
      setPhase("idle");
      const blocked = err === "not-allowed" || err === "service-not-allowed";
      if (blocked && by === "press") {
        // this phone wants a finished tap: from now on start on the tap
        pressFails.current = true;
        setFlag(PRESS_KEY, true);
        setMicNote("Tap the button once, then talk. Tap again when you're done.");
      } else if (err && err !== "aborted") {
        setMicNote(micProblem(err));
        if (err !== "no-speech") {
          setTyping(true);
          rememberTyping(true);
        }
      } else {
        setMicNote(micProblem("no-speech"));
      }
    };
    recRef.current = rec;
    setPhase("listening");
    try {
      rec.start();
      diag("start", { by });
    } catch (err) {
      recRef.current = null;
      setPhase("idle");
      diag("start-threw", { by, message: String(err) });
      if (by === "press") {
        pressFails.current = true;
        setFlag(PRESS_KEY, true);
      } else {
        setMicNote(micProblem(""));
        setTyping(true);
      }
    }
  }

  function stopListening() {
    unlockSpeech();
    const rec = recRef.current;
    // let the last words land before ending
    if (rec) setTimeout(() => rec.stop(), 300);
  }

  // Hold to talk and tap to talk both work. A press starts listening straight
  // away where the phone allows it; letting go after a real hold sends it. A
  // quick tap keeps listening until the next tap. Phones that only allow the
  // microphone on a finished tap start on the tap instead.
  function onPressStart(e: React.PointerEvent) {
    e.preventDefault();
    if (phaseRef.current === "listening") {
      stopOnTap.current = true;
      return;
    }
    if (phaseRef.current !== "idle") return;
    pressAt.current = Date.now();
    setPressing(true);
    if (!pressFails.current) startListening("press");
  }

  function onPressEnd() {
    setPressing(false);
    const held = Date.now() - pressAt.current;
    if (recRef.current && startedBy.current === "press" && held > 700 && !stopOnTap.current) {
      pressAt.current = 0;
      stopListening();
    }
  }

  function onTap() {
    if (stopOnTap.current) {
      stopOnTap.current = false;
      stopListening();
      return;
    }
    if (phaseRef.current === "idle" && !recRef.current) startListening("tap");
  }

  async function onPhoto(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    e.target.value = "";
    const jobId = receiptJob.current;
    if (!f || jobId === null) return;
    unlockSpeech();
    setHeard("Reading the receipt…");
    setPhase("thinking");
    try {
      const b64 = await shrinkPhoto(f);
      const r = await api.ownerReceipt(jobId, b64);
      setResult(r);
      setHeard(r.transcript ? `Receipt says: ${r.transcript.replace(/\n/g, " · ")}` : "");
      speak(r.readback);
      refresh();
    } catch {
      setResult({ kind: "draft", ok: false, readback: "I couldn't read that receipt. Try again with the whole receipt in view." });
    } finally {
      setPhase("idle");
    }
  }

  async function send(jobId: number) {
    setBusyJob(jobId);
    try {
      const r = await api.ownerSend(jobId);
      const who = today?.approver ?? "the office";
      const msg = r.status === "sent" ? `Invoice ${r.invoice_number} sent to the customer.` : r.status === "already_invoiced" ? "Already invoiced." : `Sent to ${who} to approve.`;
      setToast(msg);
      speak(msg);
      setResult(null);
      refresh();
    } catch (e) {
      setToast(String((e as Error).message || e));
    } finally {
      setBusyJob(null);
    }
  }

  async function paid(jobId: number) {
    setBusyJob(jobId);
    try {
      const r = await api.ownerPaid(jobId, "eftpos");
      const msg = `Paid on EFTPOS. Receipt sent for ${r.number}.`;
      setToast(msg);
      speak("Paid. Receipt sent.");
      refresh();
    } catch (e) {
      setToast(String((e as Error).message || e));
    } finally {
      setBusyJob(null);
    }
  }

  const draft = result?.kind === "draft" && result.ok && result.job ? result.job : null;

  return (
    <div className="min-h-[100dvh] bg-slate-900 text-white">
      <div className="mx-auto max-w-md px-4 pb-16 pt-[max(1rem,env(safe-area-inset-top))]">
        <header className="flex items-center justify-between py-2">
          <div className="flex items-center gap-2">
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-brand-600">
              <Wrench size={18} />
            </span>
            <div className="leading-tight">
              <div className="text-sm font-semibold">{today?.shop ?? "GarageDesk"}</div>
              <div className="text-xs text-slate-400">Owner</div>
            </div>
          </div>
        </header>

        {/* the big button */}
        <section className="mt-6 flex flex-col items-center">
          {!typing ? (
            <button
              type="button"
              aria-label={phase === "listening" ? "Stop and send" : "Tap to talk"}
              onPointerDown={onPressStart}
              onPointerUp={onPressEnd}
              onClick={onTap}
              onContextMenu={(e) => e.preventDefault()}
              disabled={phase === "thinking"}
              className={`relative grid h-56 w-56 touch-none select-none place-items-center rounded-full text-white shadow-float transition [-webkit-tap-highlight-color:transparent] [-webkit-touch-callout:none] [-webkit-user-select:none] ${
                phase === "listening" ? "scale-105 bg-red-600" : phase === "thinking" ? "bg-slate-700" : pressing ? "scale-95 bg-brand-700" : "bg-brand-600"
              }`}
            >
              {phase === "listening" && <span className="absolute inset-0 animate-ping rounded-full bg-red-500/40" />}
              <span className="relative flex flex-col items-center gap-2">
                {phase === "thinking" ? <Loader2 size={64} className="animate-spin" /> : phase === "listening" ? <Square size={56} fill="currentColor" /> : <Mic size={72} />}
                <span className="px-6 text-center text-lg font-semibold leading-tight">
                  {phase === "listening" ? "Listening… talk now" : phase === "thinking" ? "Working…" : pressing ? "Let go, then talk" : "Tap to talk"}
                </span>
                {phase === "listening" && <span className="text-sm text-red-100">Tap or let go when done</span>}
              </span>
            </button>
          ) : (
            <form
              className="w-full"
              onSubmit={(e) => {
                e.preventDefault();
                unlockSpeech();
                void submitText(typed);
                setTyped("");
              }}
            >
              <label className="mb-2 block text-center text-sm text-slate-300">Tap the box, then the microphone on your keyboard. Say the car, what you did, and what to charge.</label>
              <textarea
                value={typed}
                onChange={(e) => setTyped(e.target.value)}
                rows={3}
                placeholder="Corolla ABC123 done, front pads, hour and a half, 350 all up"
                className="w-full rounded-2xl border border-slate-700 bg-slate-800 p-4 text-lg text-white placeholder:text-slate-500 focus:border-brand-500 focus:outline-none"
              />
              <button type="submit" disabled={phase === "thinking" || !typed.trim()} className="mt-3 flex h-16 w-full items-center justify-center gap-2 rounded-2xl bg-brand-600 text-lg font-semibold disabled:opacity-50">
                {phase === "thinking" ? <Loader2 className="animate-spin" /> : <Send />} Go
              </button>
            </form>
          )}

          {micNote && <p role="status" className="mt-4 rounded-2xl bg-amber-100 p-3 text-center text-base text-amber-950">{micNote}</p>}
          {!typing && phase !== "listening" && <p className="mt-5 text-center text-base text-slate-300">Tap, then say it like you'd tell the office: the car, what you did, and what to charge.</p>}
          {canListen.current && (
            <button
              type="button"
              onClick={() => {
                const next = !typing;
                setTyping(next);
                rememberTyping(next);
                setMicNote("");
              }}
              className="mt-3 text-sm text-slate-400 underline underline-offset-4"
            >
              {typing ? "Use the talk button" : "Talk button not working? Use the keyboard microphone"}
            </button>
          )}
          <input ref={photoRef} type="file" accept="image/*" capture="environment" className="hidden" onChange={onPhoto} />
        </section>

        {heard && <p className="mt-6 text-center text-base italic text-slate-300">“{heard}”</p>}

        {/* what came back */}
        {result && (
          <section className="mt-4 rounded-3xl bg-white p-5 text-slate-900 shadow-float">
            <div className="flex items-start gap-3">
              <button type="button" aria-label="Read it again" onClick={() => speak(result.readback)} className="mt-0.5 shrink-0 rounded-full bg-slate-100 p-2 text-slate-600">
                <Volume2 size={20} />
              </button>
              <p className="text-lg font-medium leading-snug">{plain(result.readback)}</p>
            </div>
            {draft && (
              <>
                <div className="mt-4 rounded-2xl bg-slate-50 p-4">
                  <div className="text-sm font-semibold text-slate-500">
                    {draft.customer} · {draft.vehicle}
                  </div>
                  <ul className="mt-2 space-y-1.5">
                    {draft.lines.map((l, i) => (
                      <li key={i} className="flex justify-between gap-3 text-base">
                        <span className={l.unit_cents === 0 ? "font-semibold text-red-600" : ""}>
                          {l.description}
                          {l.qty !== 1 && <span className="text-slate-500"> × {l.qty}</span>}
                        </span>
                        <span className="shrink-0 tabular-nums">{l.unit_cents === 0 ? "no price" : money(Math.round(l.qty * l.unit_cents * 1.1))}</span>
                      </li>
                    ))}
                  </ul>
                  <div className="mt-3 flex justify-between border-t border-slate-200 pt-3 text-xl font-bold">
                    <span>Total inc GST</span>
                    <span className="tabular-nums">{money(draft.total_cents)}</span>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    receiptJob.current = draft.job_id;
                    photoRef.current?.click();
                  }}
                  disabled={phase !== "idle"}
                  className="mt-4 flex h-12 w-full items-center justify-center gap-2 rounded-2xl border border-slate-300 text-base font-semibold text-slate-700 active:bg-slate-100 disabled:opacity-50"
                >
                  <Camera size={20} /> Add parts from a receipt photo
                </button>
                <div className="mt-3 grid grid-cols-[1fr_auto] gap-3">
                  <button
                    type="button"
                    onClick={() => send(draft.job_id)}
                    disabled={busyJob === draft.job_id || (result.warnings?.length ?? 0) > 0}
                    className="flex h-16 items-center justify-center gap-2 rounded-2xl bg-emerald-600 text-lg font-semibold text-white active:bg-emerald-700 disabled:opacity-40"
                  >
                    {busyJob === draft.job_id ? <Loader2 className="animate-spin" /> : <Send />} Send
                  </button>
                  <button type="button" onClick={() => setResult(null)} aria-label="Say it again" className="flex h-16 w-16 items-center justify-center rounded-2xl bg-slate-200 text-slate-700">
                    <RotateCcw />
                  </button>
                </div>
                <p className="mt-2 text-center text-sm text-slate-500">Goes to {today?.approver ?? "the office"} to check, then to the customer.</p>
              </>
            )}
          </section>
        )}

        {toast && <div className="fixed inset-x-4 bottom-6 z-10 mx-auto max-w-md rounded-2xl bg-emerald-600 px-4 py-3 text-center text-base font-semibold shadow-float">{toast}</div>}

        {/* today's cars */}
        <section className="mt-10">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">Cars in the shop</h2>
          <div className="space-y-3">
            {today?.jobs.map((j) => (
              <CarRow key={j.job_id} job={j} approver={today.approver} busy={busyJob === j.job_id} onSend={() => send(j.job_id)} onPaid={() => paid(j.job_id)} />
            ))}
            {today?.arriving.map((b) => (
              <div key={b.booking_id} className="flex items-center justify-between rounded-2xl bg-slate-800/60 px-4 py-3 text-slate-300">
                <div>
                  <div className="font-semibold">{b.vehicle.split(" ").slice(0, 2).join(" ")}</div>
                  <div className="text-sm text-slate-400">
                    {b.customer} · {b.service}
                  </div>
                </div>
                <span className="flex items-center gap-1 text-sm">
                  <Clock size={14} /> {b.start}
                </span>
              </div>
            ))}
            {today && today.jobs.length === 0 && today.arriving.length === 0 && <p className="text-slate-400">No cars yet today.</p>}
          </div>
        </section>
      </div>
    </div>
  );
}

function CarRow({ job, approver, busy, onSend, onPaid }: { job: OwnerJob; approver: string; busy: boolean; onSend: () => void; onPaid: () => void }) {
  const car = job.vehicle.split(" ").slice(0, 2).join(" ") || job.title;
  const pending = job.approval?.status === "pending";
  const sentBack = job.approval?.status === "rejected" && job.status === "done";
  let state: React.ReactNode = <span className="text-slate-400">In the workshop</span>;
  let action: React.ReactNode = null;
  if (job.status === "waiting_parts") state = <span className="text-amber-300">Waiting on parts</span>;
  if (job.status === "done" && job.lines.length > 0) {
    state = <span className="text-sky-300">Ready to invoice · {money(job.total_cents)}</span>;
    action = (
      <button type="button" onClick={onSend} disabled={busy} className="flex h-12 items-center gap-1.5 rounded-xl bg-emerald-600 px-4 font-semibold disabled:opacity-50">
        {busy ? <Loader2 size={18} className="animate-spin" /> : <Send size={18} />} Send
      </button>
    );
  }
  if (pending) {
    state = <span className="text-amber-300">Waiting for {approver} · {money(job.total_cents)}</span>;
    action = null;
  }
  if (sentBack) state = <span className="text-red-300">Sent back by {approver}. Say it again.</span>;
  if (job.status === "invoiced") {
    state = <span className="text-emerald-300">Invoiced · {money(job.total_cents)} to pay</span>;
    action = (
      <button type="button" onClick={onPaid} disabled={busy} className="flex h-12 items-center gap-1.5 rounded-xl bg-white px-4 font-semibold text-slate-900 disabled:opacity-50">
        {busy ? <Loader2 size={18} className="animate-spin" /> : <CircleDollarSign size={18} />} Paid EFTPOS
      </button>
    );
  }
  return (
    <div className="rounded-2xl bg-slate-800 px-4 py-3">
      <div className="flex items-baseline gap-2">
        {job.status === "invoiced" && <Check size={18} className="shrink-0 self-center text-emerald-400" />}
        <span className="truncate text-lg font-semibold">{car}</span>
        <span className="shrink-0 text-sm text-slate-400">{job.rego}</span>
      </div>
      <div className="text-sm">
        {job.customer} · {state}
      </div>
      {action && <div className="mt-3 [&>button]:w-full [&>button]:justify-center">{action}</div>}
    </div>
  );
}
