import { useState } from "react";
import { Check, X, Loader2, ShieldCheck, Send } from "lucide-react";
import { api, type Approval } from "../api";
import { useLoad, useRefreshOnChange } from "../hooks";
import { dateTime, relative } from "../format";
import { Card, PageHeader, Spinner, Empty, ErrorNote } from "../components/ui";
import StatusPill from "../components/StatusPill";
import { toast } from "../components/Toaster";

export default function Approvals() {
  const { data, loading, error, refresh } = useLoad(() => api.approvals(), [], 15000);
  useRefreshOnChange(refresh);
  const [busy, setBusy] = useState<number | null>(null);
  const [results, setResults] = useState<Record<number, string>>({});

  async function decide(a: Approval, approve: boolean) {
    setBusy(a.id);
    try {
      const r = await api.decide(a.id, approve);
      const msg = approve ? (r.sent_via ? `Approved · sent via ${r.sent_via}` : "Approved") : "Rejected";
      setResults((x) => ({ ...x, [a.id]: msg }));
      toast(`${a.title}: ${msg}`);
      await refresh();
      window.dispatchEvent(new CustomEvent("garagedesk:changed"));
    } catch (e) {
      toast(e instanceof Error ? e.message : "Failed", "err");
    } finally {
      setBusy(null);
    }
  }

  const all = data?.approvals ?? [];
  const pending = all.filter((a) => a.status === "pending");
  const history = all.filter((a) => a.status !== "pending");

  return (
    <div className="space-y-5">
      <PageHeader title="Approvals" subtitle="Things the agents want to do but won't without your say-so: supplier orders, big quotes, refunds." />

      {loading && !data && <Spinner />}
      {error && !data && <ErrorNote error={error} />}

      {data && (
        <>
          <Card title={<span>Waiting on you {pending.length > 0 && <span className="ml-1 rounded-full bg-amber-100 text-amber-800 px-1.5 py-px text-[11px]">{pending.length}</span>}</span>}>
            {pending.length === 0 ? (
              <Empty title="Nothing to approve" hint="You're all caught up. New requests from the back-office agent land here." icon={<ShieldCheck size={28} />} />
            ) : (
              <ul className="divide-y divide-slate-100">
                {pending.map((a) => (
                  <li key={a.id} className="px-5 py-4 flex flex-col md:flex-row md:items-start gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <StatusPill status={a.kind} />
                        <span className="font-medium text-slate-900">{a.title}</span>
                        <span className="text-xs text-slate-400">{relative(a.created_at)}</span>
                      </div>
                      <p className="mt-1 text-sm text-slate-600 whitespace-pre-wrap">{a.detail}</p>
                      {results[a.id] && <div className="mt-1.5 inline-flex items-center gap-1 text-xs font-medium text-emerald-700"><Send size={12} /> {results[a.id]}</div>}
                    </div>
                    <div className="flex gap-2 shrink-0">
                      <button className="btn-primary" disabled={busy === a.id} onClick={() => void decide(a, true)}>
                        {busy === a.id ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />} Approve
                      </button>
                      <button className="btn-danger" disabled={busy === a.id} onClick={() => void decide(a, false)}>
                        <X size={14} /> Reject
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="History" action={<span className="text-xs text-slate-500">{history.length} decided</span>}>
            {history.length === 0 ? (
              <Empty title="No decisions yet" />
            ) : (
              <ul className="divide-y divide-slate-100">
                {history.map((a) => (
                  <li key={a.id} className="px-5 py-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
                    <StatusPill status={a.status} />
                    <StatusPill status={a.kind} size="xs" />
                    <span className="font-medium text-slate-800">{a.title}</span>
                    <span className="text-slate-500 truncate flex-1 min-w-[200px]">{a.detail}</span>
                    <span className="text-xs text-slate-400 ml-auto">{dateTime(a.created_at)}</span>
                    {results[a.id] && <span className="text-xs text-emerald-700 w-full md:w-auto">{results[a.id]}</span>}
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
