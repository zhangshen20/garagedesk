import { label } from "../format";

/** One consistent colour per status across bookings, jobs, invoices, POs and approvals. */
const TONES: Record<string, string> = {
  // bookings
  requested: "bg-slate-100 text-slate-700 ring-slate-200",
  confirmed: "bg-blue-50 text-blue-700 ring-blue-200",
  checked_in: "bg-amber-50 text-amber-800 ring-amber-200",
  completed: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  cancelled: "bg-slate-100 text-slate-500 ring-slate-200",
  no_show: "bg-slate-100 text-slate-500 ring-slate-200",
  // jobs
  quoted: "bg-slate-100 text-slate-700 ring-slate-200",
  approved: "bg-blue-50 text-blue-700 ring-blue-200",
  in_progress: "bg-amber-50 text-amber-800 ring-amber-200",
  waiting_parts: "bg-purple-50 text-purple-700 ring-purple-200",
  done: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  invoiced: "bg-teal-50 text-teal-700 ring-teal-200",
  paid: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  // invoices
  issued: "bg-blue-50 text-blue-700 ring-blue-200",
  overdue: "bg-red-50 text-red-700 ring-red-200",
  void: "bg-slate-100 text-slate-500 ring-slate-200",
  // approvals
  pending: "bg-amber-50 text-amber-800 ring-amber-200",
  rejected: "bg-slate-100 text-slate-500 ring-slate-200",
  // purchase orders
  draft: "bg-slate-100 text-slate-700 ring-slate-200",
  sent: "bg-blue-50 text-blue-700 ring-blue-200",
  received: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  // misc kinds
  purchase_order: "bg-purple-50 text-purple-700 ring-purple-200",
  quote: "bg-blue-50 text-blue-700 ring-blue-200",
  refund: "bg-red-50 text-red-700 ring-red-200",
  other: "bg-slate-100 text-slate-700 ring-slate-200",
  // intents
  booking: "bg-blue-50 text-blue-700 ring-blue-200",
  reschedule: "bg-amber-50 text-amber-800 ring-amber-200",
  cancel: "bg-slate-100 text-slate-600 ring-slate-200",
  status: "bg-teal-50 text-teal-700 ring-teal-200",
  question: "bg-slate-100 text-slate-700 ring-slate-200",
  quote_request: "bg-purple-50 text-purple-700 ring-purple-200",
};

const DOT: Record<string, string> = {
  checked_in: "bg-amber-500",
  in_progress: "bg-amber-500",
  waiting_parts: "bg-purple-500",
  pending: "bg-amber-500",
  overdue: "bg-red-500",
};

export default function StatusPill({ status, size = "sm", className = "" }: { status: string | null | undefined; size?: "xs" | "sm"; className?: string }) {
  if (!status) return null;
  const tone = TONES[status] ?? "bg-slate-100 text-slate-700 ring-slate-200";
  const dot = DOT[status];
  const sz = size === "xs" ? "text-[10px] px-1.5 py-px" : "text-xs px-2 py-0.5";
  return (
    <span className={`inline-flex items-center gap-1 rounded-full font-medium ring-1 ring-inset whitespace-nowrap ${sz} ${tone} ${className}`}>
      {dot && <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />}
      {label(status)}
    </span>
  );
}
