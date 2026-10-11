import { NavLink, Outlet } from "react-router-dom";
import { CalendarDays, MessageCircle, Wrench, Wallet, Package, ShieldCheck, FileText, Send, Car, ExternalLink, Cpu } from "lucide-react";
import { api } from "../api";
import { useLoad } from "../hooks";
import DeskAssistant from "./DeskAssistant";
import Toaster from "./Toaster";

const NAV = [
  { to: "/", label: "Today", icon: CalendarDays, end: true },
  { to: "/inbox", label: "Inbox", icon: MessageCircle },
  { to: "/jobs", label: "Jobs", icon: Wrench },
  { to: "/money", label: "Money", icon: Wallet },
  { to: "/parts", label: "Parts", icon: Package },
  { to: "/approvals", label: "Approvals", icon: ShieldCheck },
  { to: "/report", label: "Report", icon: FileText },
  { to: "/outbox", label: "Sent", icon: Send },
];

const MOBILE_NAV = NAV.filter((n) => ["/", "/inbox", "/jobs", "/money", "/approvals"].includes(n.to));

function shortModel(m: string | undefined): string {
  if (!m) return "";
  return m.split("/").pop() ?? m;
}

export default function Layout() {
  // Sidebar footer + badges: light poll of the overview.
  const { data: ov } = useLoad(() => api.overview(), [], 15000);
  const pending = ov?.approvals_pending.length ?? 0;
  const mock = ov?.llm.mode === "mock";

  return (
    <div className="min-h-screen md:flex">
      {/* Sidebar (desktop) */}
      <aside className="hidden md:flex md:flex-col w-60 shrink-0 border-r border-slate-200 bg-white sticky top-0 h-screen">
        <div className="px-4 pt-5 pb-4 flex items-center gap-3">
          <span className="grid h-9 w-9 place-items-center rounded-xl bg-brand-600 text-white shadow-sm">
            <Car size={20} />
          </span>
          <div className="leading-tight">
            <div className="font-semibold text-slate-900">GarageDesk</div>
            <div className="text-[11px] text-slate-500 truncate max-w-[150px]">{ov?.shop.trading_name ?? "Sunshine North Mechanic"}</div>
          </div>
        </div>
        <nav className="flex-1 px-2 space-y-0.5">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  isActive ? "bg-brand-50 text-brand-800" : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                }`
              }
            >
              {({ isActive }) => (
                <>
                  <Icon size={17} className={isActive ? "text-brand-600" : "text-slate-400"} />
                  <span className="flex-1">{label}</span>
                  {to === "/approvals" && pending > 0 && <span className="rounded-full bg-amber-100 text-amber-800 text-[11px] font-semibold px-1.5 py-px">{pending}</span>}
                </>
              )}
            </NavLink>
          ))}
          <a
            href="/chat"
            target="_blank"
            rel="noreferrer"
            className="mt-2 flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100 hover:text-slate-900"
          >
            <ExternalLink size={17} className="text-slate-400" />
            <span className="flex-1">Customer chat page</span>
          </a>
        </nav>
        <footer className="px-4 py-4 border-t border-slate-100 text-[11px] text-slate-500 leading-snug">
          <div className="flex items-center gap-1.5 text-slate-600 font-medium">
            <Cpu size={13} className="text-emerald-600" /> Powered by NVIDIA Nemotron
          </div>
          <div className="mt-0.5">on Nebius Token Factory</div>
          {ov && (
            <dl className="mt-2 space-y-0.5 font-mono text-[10px] text-slate-500">
              <div className="flex gap-1.5"><dt className="text-slate-400 w-7">main</dt><dd className="truncate" title={ov.llm.main}>{shortModel(ov.llm.main)}</dd></div>
              <div className="flex gap-1.5"><dt className="text-slate-400 w-7">fast</dt><dd className="truncate" title={ov.llm.fast}>{shortModel(ov.llm.fast)}</dd></div>
              <div className="flex gap-1.5"><dt className="text-slate-400 w-7">deep</dt><dd className="truncate" title={ov.llm.deep}>{shortModel(ov.llm.deep)}</dd></div>
            </dl>
          )}
          {mock && <span className="mt-2 inline-block rounded-md bg-slate-100 text-slate-500 px-1.5 py-0.5 text-[10px] font-medium">demo mode (no API key)</span>}
        </footer>
      </aside>

      {/* Mobile top bar */}
      <header className="md:hidden sticky top-0 z-30 flex items-center gap-2.5 bg-white border-b border-slate-200 px-4 py-2.5">
        <span className="grid h-8 w-8 place-items-center rounded-lg bg-brand-600 text-white">
          <Car size={18} />
        </span>
        <div className="leading-tight">
          <div className="font-semibold text-slate-900 text-sm">GarageDesk</div>
          <div className="text-[11px] text-slate-500">{ov?.shop.trading_name ?? "Sunshine North Mechanic"}</div>
        </div>
        {mock && <span className="ml-auto rounded-md bg-slate-100 text-slate-500 px-1.5 py-0.5 text-[10px] font-medium">demo</span>}
      </header>

      {/* Content */}
      <main className="flex-1 min-w-0 px-4 py-5 md:px-8 md:py-7 pb-24 md:pb-10">
        <div className="mx-auto max-w-[1280px]">
          <Outlet />
        </div>
      </main>

      {/* Mobile bottom tabs */}
      <nav className="md:hidden fixed bottom-0 inset-x-0 z-30 bg-white border-t border-slate-200 grid grid-cols-5">
        {MOBILE_NAV.map(({ to, label, icon: Icon, end }) => (
          <NavLink key={to} to={to} end={end} className={({ isActive }) => `flex flex-col items-center gap-0.5 py-2 text-[10px] font-medium ${isActive ? "text-brand-700" : "text-slate-500"}`}>
            <Icon size={18} />
            {label}
          </NavLink>
        ))}
      </nav>

      <DeskAssistant model={ov?.llm.main} />
      <Toaster />
    </div>
  );
}
