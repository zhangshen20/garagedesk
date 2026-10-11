import { Package, Truck, AlertTriangle, Mail, MessageSquare } from "lucide-react";
import { api } from "../api";
import { useLoad, useRefreshOnChange } from "../hooks";
import { money, date, plural } from "../format";
import { Card, PageHeader, Spinner, Empty, ErrorNote, Collapsible } from "../components/ui";
import StatusPill from "../components/StatusPill";

export default function Parts() {
  const { data, loading, error, refresh } = useLoad(() => api.parts(), [], 30000);
  useRefreshOnChange(refresh);

  if (loading && !data) return <Spinner />;
  if (error && !data) return <ErrorNote error={error} />;
  if (!data) return null;

  const low = data.parts.filter((p) => p.low).length;
  const parts = [...data.parts].sort((a, b) => Number(b.low) - Number(a.low) || a.name.localeCompare(b.name));

  return (
    <div className="space-y-5">
      <PageHeader title="Parts & suppliers" subtitle={`${plural(data.parts.length, "part")} in the price list · ${plural(data.suppliers.length, "supplier")} · ${plural(data.purchase_orders.length, "purchase order")}`} />

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <Card title="Parts" action={low > 0 ? <span className="inline-flex items-center gap-1 text-xs font-medium text-red-600"><AlertTriangle size={13} /> {plural(low, "part")} low on stock</span> : <span className="text-xs text-slate-500">Stock healthy</span>}>
          {parts.length === 0 ? (
            <Empty title="No parts yet" icon={<Package size={28} />} />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[620px]">
                <thead className="bg-slate-50/80 border-b border-slate-200">
                  <tr>
                    <th className="th">Part</th>
                    <th className="th">Supplier</th>
                    <th className="th text-right">Cost</th>
                    <th className="th text-right">Sell</th>
                    <th className="th text-right">Margin</th>
                    <th className="th text-right">Stock</th>
                  </tr>
                </thead>
                <tbody>
                  {parts.map((p) => {
                    const margin = p.sell_cents > 0 ? Math.round(((p.sell_cents - p.cost_cents) / p.sell_cents) * 100) : 0;
                    return (
                      <tr key={p.id} className="border-b border-slate-100 hover:bg-slate-50/60">
                        <td className="td">
                          <div className="font-medium text-slate-800">{p.name}</div>
                          {p.sku && <div className="font-mono text-xs text-slate-400">{p.sku}</div>}
                        </td>
                        <td className="td text-slate-600">{p.supplier ?? <span className="text-slate-300">—</span>}</td>
                        <td className="td text-right tnum">{money(p.cost_cents)}</td>
                        <td className="td text-right tnum">{money(p.sell_cents)}</td>
                        <td className="td text-right tnum text-slate-500">{margin}%</td>
                        <td className="td text-right">
                          <div className="inline-flex items-center gap-2">
                            {p.low && <span className="rounded-full bg-red-50 text-red-700 ring-1 ring-inset ring-red-200 px-2 py-0.5 text-[11px] font-medium whitespace-nowrap">Low stock</span>}
                            <span className={`tnum font-medium ${p.low ? "text-red-700" : "text-slate-800"}`}>{p.stock}</span>
                            {p.reorder_level > 0 && <span className="text-[11px] text-slate-400">/ min {p.reorder_level}</span>}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <Card title="Suppliers">
          {data.suppliers.length === 0 ? (
            <Empty title="No suppliers" icon={<Truck size={28} />} />
          ) : (
            <ul className="divide-y divide-slate-100">
              {data.suppliers.map((s) => (
                <li key={s.id} className="px-4 py-3">
                  <div className="flex items-center justify-between gap-2">
                    <div className="font-medium text-slate-800">{s.name}</div>
                    <span className="inline-flex items-center gap-1 text-[11px] text-slate-500 rounded-md bg-slate-100 px-1.5 py-0.5 whitespace-nowrap shrink-0">
                      {s.channel === "sms" ? <MessageSquare size={11} /> : <Mail size={11} />} orders by {s.channel}
                    </span>
                  </div>
                  <div className="text-xs text-slate-500 mt-0.5">
                    {s.contact && <span>{s.contact} · </span>}
                    {s.channel === "sms" ? s.phone : s.email}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <Card title="Purchase orders" action={<span className="text-xs text-slate-500">Newest first</span>}>
        {data.purchase_orders.length === 0 ? (
          <Empty title="No purchase orders yet" hint='Ask the desk assistant to "Order brake pads for job 3"; the order waits for your approval before it is sent.' icon={<Truck size={28} />} />
        ) : (
          <ul className="divide-y divide-slate-100">
            {data.purchase_orders.map((po) => (
              <li key={po.po_id} className="px-5 py-3.5">
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                  <span className="font-mono text-sm font-medium text-slate-800">PO-{po.po_id}</span>
                  <StatusPill status={po.status} />
                  <span className="text-sm text-slate-700">{po.supplier}</span>
                  {po.job_id && <span className="text-xs text-slate-400">for job #{po.job_id}</span>}
                  <span className="ml-auto text-sm font-medium tnum">{money(po.total_cents)}</span>
                  <span className="text-xs text-slate-500 w-full sm:w-auto">{po.expected_date ? `Expected ${date(po.expected_date)}` : po.status === "draft" ? "Awaiting approval" : ""}</span>
                </div>
                <ul className="mt-2 text-sm text-slate-600 space-y-0.5">
                  {po.lines.map((l, i) => (
                    <li key={i} className="flex justify-between gap-3">
                      <span>{l.qty} × {l.description}</span>
                      <span className="tnum text-slate-500">{money(l.qty * l.unit_cost_cents)}</span>
                    </li>
                  ))}
                </ul>
                {po.message && (
                  <div className="mt-2">
                    <Collapsible summary={`Order message (sent by ${po.supplier_channel})`}>
                      <pre className="whitespace-pre-wrap rounded-lg bg-slate-50 border border-slate-200 px-3 py-2 text-xs text-slate-700 font-sans">{po.message}</pre>
                    </Collapsible>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
