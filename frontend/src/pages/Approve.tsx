/** The page behind the link texted to whoever does the books. She checks the
 * invoice the owner spoke and taps Approve, or sends it back with a note. */

import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { Check, Loader2, Undo2, Wrench } from "lucide-react";
import { api, type ApproveView } from "../api";
import { money } from "../format";

export default function Approve() {
  const { id } = useParams();
  const [params] = useSearchParams();
  const token = params.get("t") ?? "";
  const [view, setView] = useState<ApproveView | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [fixing, setFixing] = useState(false);
  const [note, setNote] = useState("");
  const [done, setDone] = useState("");

  useEffect(() => {
    document.title = "Approve invoice";
    api
      .approveView(Number(id), token)
      .then(setView)
      .catch(() => setError("This link has expired or is not valid."));
  }, [id, token]);

  async function decide(approve: boolean) {
    setBusy(true);
    try {
      const r = await api.approveDecide(Number(id), token, approve, approve ? undefined : note);
      setView(r);
      setDone(approve ? `Approved. Invoice ${r.invoice_number ?? ""} has gone to the customer.` : "Sent back. He'll fix it and send it again.");
    } catch {
      setError("Something went wrong. Try again.");
    } finally {
      setBusy(false);
    }
  }

  const job = view?.job;
  return (
    <div className="min-h-[100dvh] bg-slate-50">
      <div className="mx-auto max-w-md px-4 pb-12 pt-[max(1.25rem,env(safe-area-inset-top))]">
        <header className="flex items-center gap-2">
          <span className="grid h-9 w-9 place-items-center rounded-xl bg-brand-600 text-white">
            <Wrench size={18} />
          </span>
          <div className="text-sm font-semibold text-slate-700">{view?.shop ?? "GarageDesk"}</div>
        </header>

        {error && <p className="mt-10 text-center text-lg text-slate-600">{error}</p>}
        {!view && !error && (
          <p className="mt-10 flex justify-center text-slate-500">
            <Loader2 className="animate-spin" />
          </p>
        )}

        {view && (
          <section className="mt-6 rounded-3xl bg-white p-5 shadow-card">
            <h1 className="text-xl font-bold text-slate-900">{view.title}</h1>
            {job ? (
              <>
                <div className="mt-1 text-sm text-slate-500">
                  {job.vehicle} · {job.phone}
                </div>
                <ul className="mt-4 space-y-2">
                  {job.lines.map((l, i) => (
                    <li key={i} className="flex justify-between gap-3 text-base text-slate-800">
                      <span>
                        {l.description}
                        {l.qty !== 1 && <span className="text-slate-500"> × {l.qty}</span>}
                      </span>
                      <span className="shrink-0 tabular-nums">{money(Math.round(l.qty * l.unit_cents))}</span>
                    </li>
                  ))}
                </ul>
                <div className="mt-4 space-y-1 border-t border-slate-200 pt-3 text-sm text-slate-600">
                  <div className="flex justify-between">
                    <span>Subtotal ex GST</span>
                    <span className="tabular-nums">{money(job.subtotal_cents)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>GST</span>
                    <span className="tabular-nums">{money(job.gst_cents)}</span>
                  </div>
                  <div className="flex justify-between pt-1 text-xl font-bold text-slate-900">
                    <span>Total</span>
                    <span className="tabular-nums">{money(job.total_cents)}</span>
                  </div>
                </div>
                {job.mechanic_notes && <p className="mt-3 rounded-xl bg-amber-50 p-3 text-sm text-amber-900">{job.mechanic_notes}</p>}
              </>
            ) : (
              <p className="mt-2 text-slate-600">{view.detail}</p>
            )}

            {done ? (
              <p className="mt-6 rounded-2xl bg-emerald-50 p-4 text-center text-base font-semibold text-emerald-800">{done}</p>
            ) : view.status !== "pending" ? (
              <p className="mt-6 rounded-2xl bg-slate-100 p-4 text-center text-base text-slate-700">Already {view.status}.</p>
            ) : fixing ? (
              <div className="mt-6">
                <textarea
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  rows={2}
                  placeholder="What needs fixing? e.g. labour is 2 hours"
                  className="w-full rounded-2xl border border-slate-300 p-3 text-base focus:border-brand-500 focus:outline-none"
                />
                <div className="mt-3 grid grid-cols-2 gap-3">
                  <button type="button" onClick={() => setFixing(false)} className="h-14 rounded-2xl bg-slate-100 text-base font-semibold text-slate-700">
                    Cancel
                  </button>
                  <button type="button" onClick={() => decide(false)} disabled={busy} className="h-14 rounded-2xl bg-slate-800 text-base font-semibold text-white disabled:opacity-50">
                    Send back
                  </button>
                </div>
              </div>
            ) : (
              <div className="mt-6 grid grid-cols-[1fr_auto] gap-3">
                <button
                  type="button"
                  onClick={() => decide(true)}
                  disabled={busy}
                  className="flex h-16 items-center justify-center gap-2 rounded-2xl bg-emerald-600 text-lg font-semibold text-white active:bg-emerald-700 disabled:opacity-50"
                >
                  {busy ? <Loader2 className="animate-spin" /> : <Check />} Approve and send
                </button>
                <button type="button" onClick={() => setFixing(true)} className="flex h-16 items-center gap-1.5 rounded-2xl bg-slate-100 px-4 font-semibold text-slate-700">
                  <Undo2 size={18} /> Fix
                </button>
              </div>
            )}
          </section>
        )}
      </div>
    </div>
  );
}
