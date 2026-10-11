import { useState } from "react";
import { Car, ArrowDownToLine, ArrowUpFromLine, ReceiptText, ShieldAlert, LogIn, CheckCheck, XCircle, Loader2, Clock } from "lucide-react";
import { api, type Booking, type Overview } from "../api";
import { useLoad, useRefreshOnChange } from "../hooks";
import { money, time, dateLong, timeOf, label, plural } from "../format";
import { Card, KpiTile, Spinner, Empty, ErrorNote, ChannelIcon, ActorBadge, channelName } from "../components/ui";
import StatusPill from "../components/StatusPill";
import { toast } from "../components/Toaster";

function BookingCard({ b, onChange }: { b: Booking; onChange: () => Promise<void> }) {
  const [busy, setBusy] = useState<string | null>(null);

  async function set(status: "checked_in" | "completed" | "cancelled", verb: string) {
    setBusy(status);
    try {
      await api.patchBooking(b.booking_id, { status });
      toast(`${b.customer || "Booking"} ${verb}`);
      await onChange();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Failed", "err");
    } finally {
      setBusy(null);
    }
  }

  const terminal = b.status === "completed" || b.status === "cancelled" || b.status === "no_show";
  return (
    <div className={`rounded-lg border bg-white p-3 shadow-card ${terminal ? "border-slate-100 opacity-70" : "border-slate-200"}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-1.5 text-sm font-semibold text-slate-900 tnum">
          <Clock size={13} className="text-slate-400" />
          {time(b.start)}
        </div>
        <StatusPill status={b.status} size="xs" />
      </div>
      <div className="mt-1.5 text-sm font-medium text-slate-800 truncate">{b.customer || "Walk-in"}</div>
      <div className="text-xs text-slate-500 truncate">{b.vehicle || "Vehicle not recorded"}</div>
      <div className="mt-1.5 text-sm text-slate-700">{b.service}</div>
      <div className="mt-2 flex items-center justify-between gap-2">
        <span className="inline-flex items-center gap-1 text-[11px] text-slate-500" title={`Booked via ${channelName(b.source)}`}>
          <ChannelIcon channel={b.source} size={12} /> {channelName(b.source)}
          <span className="text-slate-300">·</span>
          <span className="font-mono">{b.reference}</span>
        </span>
      </div>
      {!terminal && (
        <div className="mt-2.5 flex flex-wrap gap-1.5">
          {b.status !== "checked_in" && (
            <button className="btn-primary !px-2.5 !py-1 text-xs" disabled={!!busy} onClick={() => void set("checked_in", "checked in")}>
              {busy === "checked_in" ? <Loader2 size={13} className="animate-spin" /> : <LogIn size={13} />} Check in
            </button>
          )}
          <button className="btn-secondary !px-2.5 !py-1 text-xs" disabled={!!busy} onClick={() => void set("completed", "marked completed")}>
            {busy === "completed" ? <Loader2 size={13} className="animate-spin" /> : <CheckCheck size={13} />} Completed
          </button>
          <button className="btn-ghost !px-2 !py-1 text-xs text-slate-500" disabled={!!busy} onClick={() => void set("cancelled", "cancelled")}>
            {busy === "cancelled" ? <Loader2 size={13} className="animate-spin" /> : <XCircle size={13} />} Cancel
          </button>
        </div>
      )}
    </div>
  );
}

function BayBoard({ ov, onChange }: { ov: Overview; onChange: () => Promise<void> }) {
  const bays = Array.from({ length: Math.max(1, ov.shop.bays) }, (_, i) => i + 1);
  const byBay = new Map<number, Booking[]>();
  for (const b of ov.bookings_today) {
    const k = bays.includes(b.bay) ? b.bay : bays[bays.length - 1];
    byBay.set(k, [...(byBay.get(k) ?? []), b]);
  }
  return (
    <div className="grid gap-3" style={{ gridTemplateColumns: `repeat(${bays.length}, minmax(0, 1fr))` }}>
      {bays.map((bay) => {
        const list = byBay.get(bay) ?? [];
        return (
          <div key={bay} className="rounded-xl bg-slate-100/80 border border-slate-200/70 p-2.5 min-h-[160px]">
            <div className="flex items-center justify-between px-1 pb-2">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-600">Bay {bay}</span>
              <span className="text-[11px] text-slate-500">{plural(list.length, "car")}</span>
            </div>
            <div className="space-y-2">
              {list.length === 0 && <div className="rounded-lg border border-dashed border-slate-300 py-6 text-center text-xs text-slate-400">Free</div>}
              {list.map((b) => <BookingCard key={b.booking_id} b={b} onChange={onChange} />)}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default function Today() {
  const { data: ov, loading, error, refresh } = useLoad(() => api.overview(), [], 10000);
  useRefreshOnChange(refresh);

  if (loading && !ov) return <Spinner />;
  if (error && !ov) return <ErrorNote error={error} />;
  if (!ov) return null;

  const cars = ov.bookings_today.length;
  const inShop = ov.bookings_today.filter((b) => b.status === "checked_in").length;
  const waiting = ov.jobs_open.filter((j) => j.status === "waiting_parts").length;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl md:text-2xl font-semibold tracking-tight text-slate-900">{ov.shop.name}</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {dateLong(ov.today)} · {ov.shop.hours} · {ov.shop.address}
          </p>
        </div>
        <div className="text-xs text-slate-500">
          {ov.bookings_tomorrow > 0 ? `${plural(ov.bookings_tomorrow, "booking")} tomorrow` : "Nothing booked tomorrow yet"}
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <KpiTile label="Cars today" value={cars} hint={inShop ? `${inShop} in the shop now` : waiting ? `${waiting} waiting on parts` : "Across all bays"} icon={<Car size={16} />} />
        <KpiTile label="Cash in today" value={money(ov.cash_in_cents)} tone="good" icon={<ArrowDownToLine size={16} />} hint="Payments received" />
        <KpiTile label="Cash out today" value={money(ov.cash_out_cents)} tone={ov.cash_out_cents > 0 ? "bad" : "default"} icon={<ArrowUpFromLine size={16} />} hint="Expenses logged" />
        <KpiTile label="Unpaid invoices" value={money(ov.unpaid.total_cents)} hint={plural(ov.unpaid.count, "invoice") + " outstanding"} tone={ov.unpaid.count ? "warn" : "default"} icon={<ReceiptText size={16} />} />
        <KpiTile label="Approvals pending" value={ov.approvals_pending.length} hint={ov.approvals_pending[0]?.title ?? "Nothing waiting on you"} tone={ov.approvals_pending.length ? "accent" : "default"} icon={<ShieldAlert size={16} />} />
      </div>

      <Card title="Bay board" action={<span className="text-xs text-slate-500">Live · refreshes every 10s</span>}>
        <div className="p-3 md:p-4 overflow-x-auto">
          {ov.bookings_today.length === 0 ? (
            <Empty title="No cars booked today" hint="Bookings made by the front-desk agent will show up here by bay." icon={<Car size={28} />} />
          ) : (
            <div className="min-w-[560px]">
              <BayBoard ov={ov} onChange={refresh} />
            </div>
          )}
        </div>
      </Card>

      <Card title="Agent activity" action={<span className="text-xs text-slate-500">Last {ov.events.length} actions</span>}>
        {ov.events.length === 0 ? (
          <Empty title="Quiet so far" hint="Every booking, order, invoice and message the agents handle is logged here." />
        ) : (
          <ul className="divide-y divide-slate-100">
            {ov.events.map((e, i) => (
              <li key={i} className="flex items-start gap-3 px-5 py-2.5 text-sm">
                <span className="w-16 shrink-0 text-xs text-slate-400 tnum pt-0.5">{timeOf(e.at)}</span>
                <ActorBadge actor={e.actor} />
                <span className="font-medium text-slate-800 shrink-0">{label(e.action)}</span>
                <span className="text-slate-500 truncate">{e.detail}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
