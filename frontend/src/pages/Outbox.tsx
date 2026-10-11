import { Info, CheckCircle2, Clock, Send } from "lucide-react";
import { api } from "../api";
import { useLoad, useRefreshOnChange } from "../hooks";
import { dateTime } from "../format";
import { Card, PageHeader, Spinner, Empty, ErrorNote, ChannelIcon, channelName } from "../components/ui";

export default function Outbox() {
  const { data, loading, error, refresh } = useLoad(() => api.outbox(), [], 15000);
  useRefreshOnChange(refresh);
  const ov = useLoad(() => api.overview(), []);
  const mock = !ov.data?.llm.twilio;
  const items = data?.outbox ?? [];

  return (
    <div className="space-y-4">
      <PageHeader title="Sent messages" subtitle="Every SMS, email and call the system sends: confirmations, reminders, supplier orders, invoices." />

      {mock && (
        <div className="flex items-start gap-2 rounded-lg border border-blue-200 bg-blue-50 px-3.5 py-2.5 text-sm text-blue-800">
          <Info size={16} className="mt-0.5 shrink-0" />
          <span>In demo mode messages are delivered here instead of to a phone. Add Twilio credentials and the same messages go out for real.</span>
        </div>
      )}

      <Card>
        {loading && !data && <Spinner />}
        {error && !data && <div className="p-3"><ErrorNote error={error} /></div>}
        {data && items.length === 0 && <Empty title="Nothing sent yet" hint="Book a car through the Inbox simulator and the confirmation text will show up here." icon={<Send size={28} />} />}
        {items.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px]">
              <thead className="bg-slate-50/80 border-b border-slate-200">
                <tr>
                  <th className="th">Channel</th>
                  <th className="th">To</th>
                  <th className="th">Message</th>
                  <th className="th">Delivered</th>
                  <th className="th">Time</th>
                </tr>
              </thead>
              <tbody>
                {items.map((o) => (
                  <tr key={o.id} className="border-b border-slate-100 hover:bg-slate-50/60 align-top">
                    <td className="td">
                      <span className="inline-flex items-center gap-1.5 text-slate-700">
                        <span className="grid h-6 w-6 place-items-center rounded-full bg-slate-100 text-slate-600"><ChannelIcon channel={o.channel} size={12} /></span>
                        {channelName(o.channel)}
                      </span>
                    </td>
                    <td className="td font-mono text-xs text-slate-700 whitespace-nowrap">{o.to}</td>
                    <td className="td max-w-xl">
                      {o.subject && <div className="font-medium text-slate-800">{o.subject}</div>}
                      <div className="text-slate-600 whitespace-pre-wrap">{o.body}</div>
                    </td>
                    <td className="td whitespace-nowrap">
                      {o.delivered ? (
                        <span className="inline-flex items-center gap-1 text-emerald-700 text-xs font-medium"><CheckCircle2 size={13} /> Delivered{o.provider_ref ? ` · ${o.provider_ref}` : ""}</span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-slate-500 text-xs"><Clock size={13} /> Queued</span>
                      )}
                    </td>
                    <td className="td text-xs text-slate-500 whitespace-nowrap">{dateTime(o.at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
