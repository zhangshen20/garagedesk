import { useState } from "react";
import { ChevronRight, FileText, Wrench } from "lucide-react";
import { api, type Job } from "../api";
import { useLoad, useRefreshOnChange } from "../hooks";
import { money, label } from "../format";
import { Card, PageHeader, Spinner, Empty, ErrorNote } from "../components/ui";
import StatusPill from "../components/StatusPill";

const STATUSES = ["quoted", "approved", "in_progress", "waiting_parts", "done", "invoiced", "paid"];

function JobDetail({ j }: { j: Job }) {
  return (
    <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_260px] px-4 py-3 bg-slate-50/70 border-t border-slate-100">
      <div>
        {j.lines.length === 0 ? (
          <div className="text-sm text-slate-500 py-2">No lines on this job card yet.</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr>
                <th className="th">Kind</th>
                <th className="th">Description</th>
                <th className="th text-right">Qty</th>
                <th className="th text-right">Unit</th>
                <th className="th text-right">Amount</th>
              </tr>
            </thead>
            <tbody>
              {j.lines.map((l, i) => (
                <tr key={i} className="border-t border-slate-100">
                  <td className="td">
                    <span className={`rounded-md px-1.5 py-0.5 text-[11px] font-medium ${l.kind === "labour" ? "bg-blue-50 text-blue-700" : l.kind === "part" ? "bg-purple-50 text-purple-700" : "bg-slate-100 text-slate-600"}`}>{label(l.kind)}</span>
                  </td>
                  <td className="td">{l.description}</td>
                  <td className="td text-right tnum">{l.qty}</td>
                  <td className="td text-right tnum">{money(l.unit_cents)}</td>
                  <td className="td text-right tnum font-medium">{money(Math.round(l.qty * l.unit_cents))}</td>
                </tr>
              ))}
            </tbody>
            <tfoot className="text-sm">
              <tr className="border-t border-slate-200">
                <td colSpan={4} className="td text-right text-slate-500">Subtotal (ex GST)</td>
                <td className="td text-right tnum">{money(j.subtotal_cents)}</td>
              </tr>
              <tr>
                <td colSpan={4} className="td text-right text-slate-500 !py-1">GST 10%</td>
                <td className="td text-right tnum !py-1">{money(j.gst_cents)}</td>
              </tr>
              <tr>
                <td colSpan={4} className="td text-right font-semibold text-slate-800">Total</td>
                <td className="td text-right tnum font-semibold text-slate-900">{money(j.total_cents)}</td>
              </tr>
            </tfoot>
          </table>
        )}
      </div>
      <div className="space-y-3 text-sm">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">Mechanic notes</div>
          <div className="rounded-lg bg-white border border-slate-200 px-3 py-2 text-slate-700 whitespace-pre-wrap min-h-[44px]">{j.mechanic_notes || <span className="text-slate-400">No notes yet</span>}</div>
        </div>
        <div>
          <div className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">Invoice</div>
          {j.invoice_number ? (
            <a href={`/api/invoices/${j.invoice_number}/pdf`} target="_blank" rel="noreferrer" className="btn-secondary">
              <FileText size={14} /> {j.invoice_number} <span className="text-slate-400 text-xs">PDF</span>
            </a>
          ) : (
            <div className="text-slate-400">Not invoiced yet</div>
          )}
        </div>
        <div className="text-xs text-slate-500">
          {j.phone && <div>Customer phone: <span className="font-mono text-slate-700">{j.phone}</span></div>}
          {j.booking_id && <div>From booking #{j.booking_id}</div>}
        </div>
      </div>
    </div>
  );
}

export default function Jobs() {
  const [filter, setFilter] = useState<string | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  const { data, loading, error, refresh } = useLoad(() => api.jobs(), [], 20000);
  useRefreshOnChange(refresh);

  const all = data?.jobs ?? [];
  const counts = new Map<string, number>();
  for (const j of all) counts.set(j.status, (counts.get(j.status) ?? 0) + 1);
  const jobs = filter ? all.filter((j) => j.status === filter) : all;

  return (
    <div>
      <PageHeader title="Jobs" subtitle="Job cards: the work actually done on each car, with parts, labour and the invoice." />

      <div className="flex flex-wrap gap-1.5 mb-4">
        <button onClick={() => setFilter(null)} className={`chip ${filter === null ? "bg-slate-800 text-white border-slate-800" : "bg-white border-slate-300 text-slate-600 hover:border-slate-400"}`}>
          All <span className="ml-1 opacity-60">{all.length}</span>
        </button>
        {STATUSES.map((s) => (
          <button key={s} onClick={() => setFilter(filter === s ? null : s)} className={`chip ${filter === s ? "bg-slate-800 text-white border-slate-800" : "bg-white border-slate-300 text-slate-600 hover:border-slate-400"}`}>
            {label(s)} <span className="ml-1 opacity-60">{counts.get(s) ?? 0}</span>
          </button>
        ))}
      </div>

      <Card>
        {loading && !data && <Spinner />}
        {error && !data && <div className="p-3"><ErrorNote error={error} /></div>}
        {data && jobs.length === 0 && <Empty title={filter ? `No ${label(filter).toLowerCase()} jobs` : "No jobs yet"} hint="Checking a car in from the bay board opens a job card." icon={<Wrench size={28} />} />}
        {jobs.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px]">
              <thead className="bg-slate-50/80 border-b border-slate-200">
                <tr>
                  <th className="th w-8"></th>
                  <th className="th">Job</th>
                  <th className="th">Customer</th>
                  <th className="th">Vehicle</th>
                  <th className="th">Status</th>
                  <th className="th text-right">Lines</th>
                  <th className="th text-right">Total</th>
                  <th className="th">Invoice</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((j) => {
                  const isOpen = open === j.job_id;
                  return (
                    <JobRows key={j.job_id} j={j} isOpen={isOpen} toggle={() => setOpen(isOpen ? null : j.job_id)} />
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}

function JobRows({ j, isOpen, toggle }: { j: Job; isOpen: boolean; toggle: () => void }) {
  return (
    <>
      <tr onClick={toggle} className={`cursor-pointer border-b border-slate-100 hover:bg-slate-50 ${isOpen ? "bg-slate-50" : ""}`}>
        <td className="td text-slate-400">
          <ChevronRight size={16} className={`transition-transform ${isOpen ? "rotate-90" : ""}`} />
        </td>
        <td className="td">
          <div className="font-medium text-slate-900">{j.title}</div>
          <div className="text-xs text-slate-400">Job #{j.job_id}</div>
        </td>
        <td className="td">{j.customer}</td>
        <td className="td">
          <div className="text-slate-700">{j.vehicle.replace(j.rego, "").trim() || "—"}</div>
          {j.rego && <div className="font-mono text-xs text-slate-500">{j.rego}</div>}
        </td>
        <td className="td"><StatusPill status={j.status} /></td>
        <td className="td text-right tnum">{j.lines.length}</td>
        <td className="td text-right tnum font-medium">{money(j.total_cents)}</td>
        <td className="td">
          {j.invoice_number ? (
            <a href={`/api/invoices/${j.invoice_number}/pdf`} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()} className="inline-flex items-center gap-1 text-brand-700 hover:underline text-sm">
              <FileText size={13} /> {j.invoice_number}
            </a>
          ) : (
            <span className="text-slate-300">—</span>
          )}
        </td>
      </tr>
      {isOpen && (
        <tr className="border-b border-slate-100">
          <td colSpan={8} className="p-0">
            <JobDetail j={j} />
          </td>
        </tr>
      )}
    </>
  );
}
