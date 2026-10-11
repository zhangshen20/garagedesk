import type { ReactNode } from "react";
import { Phone, MessageSquare, Globe, Monitor, Mail, UserCog, Bot, Loader2, Inbox } from "lucide-react";

export function Card({ children, className = "", title, action, dense }: { children: ReactNode; className?: string; title?: ReactNode; action?: ReactNode; dense?: boolean }) {
  return (
    <section className={`card ${className}`}>
      {(title || action) && (
        <header className={`flex items-center justify-between gap-3 border-b border-slate-100 ${dense ? "px-4 py-2.5" : "px-5 py-3.5"}`}>
          <h2 className="text-sm font-semibold text-slate-800">{title}</h2>
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

export function PageHeader({ title, subtitle, action }: { title: ReactNode; subtitle?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3 mb-5">
      <div>
        <h1 className="text-xl md:text-2xl font-semibold tracking-tight text-slate-900">{title}</h1>
        {subtitle && <p className="text-sm text-slate-500 mt-0.5">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

export function KpiTile({ label, value, hint, tone = "default", icon }: { label: string; value: ReactNode; hint?: ReactNode; tone?: "default" | "good" | "bad" | "warn" | "accent"; icon?: ReactNode }) {
  const valueTone = {
    default: "text-slate-900",
    good: "text-emerald-700",
    bad: "text-red-700",
    warn: "text-amber-700",
    accent: "text-brand-700",
  }[tone];
  return (
    <div className="card px-4 py-3.5 flex flex-col gap-1 min-w-0">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium text-slate-500">{label}</span>
        {icon && <span className="text-slate-400">{icon}</span>}
      </div>
      <div className={`text-2xl font-semibold tracking-tight truncate ${valueTone}`}>{value}</div>
      {hint && <div className="text-xs text-slate-500 truncate">{hint}</div>}
    </div>
  );
}

export function Spinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-10 text-sm text-slate-500">
      <Loader2 size={16} className="animate-spin" /> {label}
    </div>
  );
}

export function Empty({ title, hint, icon }: { title: string; hint?: string; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-1.5 py-10 text-center">
      <div className="text-slate-300">{icon ?? <Inbox size={28} />}</div>
      <div className="text-sm font-medium text-slate-600">{title}</div>
      {hint && <div className="text-xs text-slate-400 max-w-xs">{hint}</div>}
    </div>
  );
}

export function ErrorNote({ error }: { error: string }) {
  return <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">Couldn't load: {error}</div>;
}

/** Icon for a conversation channel or booking source. */
export function ChannelIcon({ channel, size = 14, className = "" }: { channel: string | null | undefined; size?: number; className?: string }) {
  const c = (channel ?? "").toLowerCase();
  const props = { size, className, strokeWidth: 2 };
  if (c === "voice" || c === "phone") return <Phone {...props} aria-label="Phone" />;
  if (c === "sms") return <MessageSquare {...props} aria-label="SMS" />;
  if (c === "web") return <Globe {...props} aria-label="Web" />;
  if (c === "email") return <Mail {...props} aria-label="Email" />;
  if (c === "owner") return <UserCog {...props} aria-label="Owner" />;
  return <Monitor {...props} aria-label="Desk" />;
}

export function channelName(channel: string | null | undefined): string {
  const c = (channel ?? "").toLowerCase();
  return { voice: "Phone call", phone: "Phone", sms: "SMS", web: "Web chat", email: "Email", owner: "Owner", desk: "Front desk" }[c] ?? c;
}

/** Badge naming which actor did something in the event feed. */
export function ActorBadge({ actor }: { actor: string }) {
  const map: Record<string, { cls: string; label: string; icon?: ReactNode }> = {
    frontdesk: { cls: "bg-blue-50 text-blue-700 ring-blue-200", label: "Front desk", icon: <Bot size={11} /> },
    backoffice: { cls: "bg-purple-50 text-purple-700 ring-purple-200", label: "Back office", icon: <Bot size={11} /> },
    owner: { cls: "bg-brand-50 text-brand-800 ring-brand-200", label: "Owner" },
    system: { cls: "bg-slate-100 text-slate-600 ring-slate-200", label: "System" },
  };
  const m = map[actor] ?? { cls: "bg-slate-100 text-slate-600 ring-slate-200", label: actor };
  return (
    <span className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-medium ring-1 ring-inset ${m.cls}`}>
      {m.icon}
      {m.label}
    </span>
  );
}

export function Collapsible({ summary, children, defaultOpen = false }: { summary: ReactNode; children: ReactNode; defaultOpen?: boolean }) {
  return (
    <details className="group" open={defaultOpen}>
      <summary className="cursor-pointer select-none list-none text-xs text-slate-500 hover:text-slate-700 inline-flex items-center gap-1">
        <span className="inline-block transition-transform group-open:rotate-90">▸</span>
        {summary}
      </summary>
      <div className="mt-1.5">{children}</div>
    </details>
  );
}
