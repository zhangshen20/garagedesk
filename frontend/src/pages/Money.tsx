import { useState } from "react";
import { ArrowDownToLine, ArrowUpFromLine, Landmark, Receipt, FileText, CreditCard, Loader2 } from "lucide-react";
import { api, type Invoice } from "../api";
import { useLoad, useRefreshOnChange } from "../hooks";
import { money, date, plural } from "../format";
import { Card, PageHeader, KpiTile, Spinner, Empty, ErrorNote } from "../components/ui";
import StatusPill from "../components/StatusPill";
import CashChart from "../components/CashChart";
import { toast } from "../components/Toaster";

function daysOverdue(inv: Invoice): number {
  if (inv.status !== "issued" || !inv.due) return 0;
  const [y, m, d] = inv.due.split("-").map((x) => parseInt(x, 10));
  const due = new Date(y, m - 1, d);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.max(0, Math.round((today.getTime() - due.getTime()) / 86400000));
}

export default function Money() {
  const m = useLoad(() => api.money(30), [], 30000);
  const inv = useLoad(() => api.invoices(), [], 30000);
  const [paying, setPaying] = useState<string | null>(null);

  const refreshAll = async () => {
    await Promise.all([m.refresh(), inv.refresh()]);
  };
  useRefreshOnChange(refreshAll);

  async function pay(i: Invoice) {
    setPaying(i.number);
    try {
      await api.recordPayment(i.number, i.total_cents, "card");
      toast(`${i.number} paid · ${money(i.total_cents)}`);
      await refreshAll();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Payment failed", "err");
    } finally {
      setPaying(null);
    }
  }

  const s = m.data?.summary;
  const invoices = inv.data?.invoices ?? [];
  const unpaidCount = invoices.filter((i) => i.status === "issued").length;

  return (
    <div className="space-y-5">
      <PageHeader title="Money" subtitle={s ? `Last 30 days · ${date(s.from)} to ${date(s.to)} · ${plural(s.invoices_issued, "invoice")} issued` : "Cash in, cash out and GST over the last 30 days"} />

      {m.error && !m.data && <ErrorNote error={m.error} />}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiTile label="Cash in (30 days)" value={s ? money(s.cash_in_cents) : "—"} tone="good" icon={<ArrowDownToLine size={16} />} hint="Payments received" />
        <KpiTile label="Cash out (30 days)" value={s ? money(s.cash_out_cents) : "—"} tone="bad" icon={<ArrowUpFromLine size={16} />} hint="Expenses and parts" />
        <KpiTile label="GST collected" value={s ? money(s.gst_collected_cents) : "—"} icon={<Landmark size={16} />} hint="On invoices issued" />
        <KpiTile label="GST paid" value={s ? money(s.gst_paid_cents) : "—"} icon={<Receipt size={16} />} hint={s ? `Net GST ${money(s.gst_collected_cents - s.gst_paid_cents)}` : undefined} />
      </div>

      <Card title="Cash in vs cash out, per day" action={<span className="text-xs text-slate-500">Last 30 days</span>}>
        {m.loading && !m.data ? <Spinner /> : m.data ? <CashChart series={m.data.series} /> : null}
      </Card>

      <Card title="Invoices" action={<span className="text-xs text-slate-500">{unpaidCount ? `${plural(unpaidCount, "invoice")} unpaid` : "All paid"}</span>}>
        {inv.loading && !inv.data && <Spinner />}
        {inv.error && !inv.data && <div className="p-3"><ErrorNote error={inv.error} /></div>}
        {inv.data && invoices.length === 0 && <Empty title="No invoices yet" hint='Ask the desk assistant to "Invoice job 4" and it will appear here with a PDF.' icon={<FileText size={28} />} />}
        {invoices.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px]">
              <thead className="bg-slate-50/80 border-b border-slate-200">
                <tr>
                  <th className="th">Number</th>
                  <th className="th">Customer</th>
                  <th className="th text-right">Total</th>
                  <th className="th">Status</th>
                  <th className="th">Issued</th>
                  <th className="th">Due</th>
                  <th className="th">Documents</th>
                  <th className="th text-right"></th>
                </tr>
              </thead>
              <tbody>
                {invoices.map((i) => {
                  const od = daysOverdue(i);
                  return (
                    <tr key={i.number} className="border-b border-slate-100 hover:bg-slate-50/60">
                      <td className="td font-mono text-slate-800">{i.number}</td>
                      <td className="td">
                        <div>{i.customer}</div>
                        <div className="text-xs text-slate-400">Job #{i.job_id}</div>
                      </td>
                      <td className="td text-right tnum font-medium">
                        {money(i.total_cents)}
                        <div className="text-[11px] text-slate-400 font-normal">incl. GST {money(i.gst_cents)}</div>
                      </td>
                      <td className="td"><StatusPill status={od > 0 ? "overdue" : i.status} /></td>
                      <td className="td text-slate-600">{date(i.issued_at)}</td>
                      <td className="td">
                        <div className="text-slate-600">{i.due ? date(i.due) : "—"}</div>
                        {od > 0 && <div className="text-xs font-medium text-red-600">{plural(od, "day")} overdue</div>}
                      </td>
                      <td className="td">
                        <div className="flex items-center gap-2">
                          <a href={i.pdf} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-brand-700 hover:underline text-sm">
                            <FileText size={13} /> PDF
                          </a>
                          {i.receipt && (
                            <a href={i.receipt} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-emerald-700 hover:underline text-sm">
                              <Receipt size={13} /> Receipt
                            </a>
                          )}
                        </div>
                      </td>
                      <td className="td text-right">
                        {i.status === "issued" && (
                          <button className="btn-secondary !py-1 text-xs" disabled={paying === i.number} onClick={() => void pay(i)}>
                            {paying === i.number ? <Loader2 size={13} className="animate-spin" /> : <CreditCard size={13} />} Record payment
                          </button>
                        )}
                      </td>
                    </tr>
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
