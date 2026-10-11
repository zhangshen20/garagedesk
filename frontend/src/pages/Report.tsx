import { useState } from "react";
import { Sparkles, Loader2, FileText, Cpu } from "lucide-react";
import { api, type Report as ReportT } from "../api";
import { useLoad } from "../hooks";
import { date, dateLong, dateTime } from "../format";
import { Card, PageHeader, Spinner, Empty, ErrorNote } from "../components/ui";
import Markdown from "../components/Markdown";
import { toast } from "../components/Toaster";

export default function Report() {
  const { data, loading, error, refresh } = useLoad(() => api.reports(), []);
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);

  async function generate() {
    setBusy(true);
    try {
      const r = await api.generateReport();
      toast(`Report for ${date(r.day)} generated`);
      await refresh();
      setSelected(r.day);
    } catch (e) {
      toast(e instanceof Error ? e.message : "Failed to generate", "err");
    } finally {
      setBusy(false);
    }
  }

  const reports = data?.reports ?? [];
  const current: ReportT | undefined = reports.find((r) => r.day === selected) ?? reports[0];

  return (
    <div className="space-y-5">
      <PageHeader
        title="Daily report"
        subtitle="End-of-day summary written by the deep model: cash, cars, parts, what needs you tomorrow."
        action={
          <button className="btn-primary" onClick={() => void generate()} disabled={busy}>
            {busy ? <Loader2 size={15} className="animate-spin" /> : <Sparkles size={15} />}
            {busy ? "Writing…" : "Generate today's report"}
          </button>
        }
      />

      {loading && !data && <Spinner />}
      {error && !data && <ErrorNote error={error} />}

      {data && (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
          <Card
            title={current ? dateLong(current.day) : "Report"}
            action={current ? <span className="inline-flex items-center gap-1 text-[11px] text-slate-500 font-mono"><Cpu size={12} className="text-emerald-600" /> {current.model}</span> : undefined}
          >
            {!current ? (
              <Empty title="No report yet" hint="Generate one now, or wait for the 5:45pm scheduled run." icon={<FileText size={28} />} />
            ) : (
              <div className="px-6 py-5 max-w-3xl">
                <Markdown text={current.content_md} className="[&_p]:text-[15px] [&_li]:text-[15px]" />
                <div className="mt-5 pt-3 border-t border-slate-100 text-xs text-slate-400">
                  Written by <span className="font-mono text-slate-500">{current.model}</span>
                  {current.created_at && <> · {dateTime(current.created_at)}</>}
                </div>
              </div>
            )}
          </Card>

          <Card title="Previous reports" dense>
            {reports.length === 0 ? (
              <Empty title="Nothing yet" />
            ) : (
              <ul className="divide-y divide-slate-100">
                {reports.map((r) => (
                  <li key={r.day}>
                    <button
                      onClick={() => setSelected(r.day)}
                      className={`w-full text-left px-4 py-2.5 text-sm hover:bg-slate-50 ${current?.day === r.day ? "bg-brand-50/70 border-l-2 border-brand-500" : "border-l-2 border-transparent"}`}
                    >
                      <div className="font-medium text-slate-800">{date(r.day)}</div>
                      <div className="text-xs text-slate-400 truncate">{r.model.split("/").pop()}</div>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
