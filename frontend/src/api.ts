/** Typed fetch helpers for the GarageDesk FastAPI backend. All URLs are relative so
 * the same code works behind the Vite dev proxy and when FastAPI serves the build. */

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body?.detail === "string" ? body.detail : JSON.stringify(body?.detail ?? body);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail || `HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}

const get = <T>(url: string) => request<T>(url);
const post = <T>(url: string, body?: unknown) =>
  request<T>(url, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
const patch = <T>(url: string, body: unknown) => request<T>(url, { method: "PATCH", body: JSON.stringify(body) });

// --- shapes --------------------------------------------------------------------------

export type BookingStatus = "requested" | "confirmed" | "checked_in" | "completed" | "cancelled" | "no_show";
export type JobStatus = "quoted" | "approved" | "in_progress" | "waiting_parts" | "done" | "invoiced" | "paid";
export type Channel = "web" | "sms" | "voice" | "email" | "owner";
export type Source = "phone" | "sms" | "web" | "desk" | string;

export interface Booking {
  booking_id: number;
  reference: string;
  day: string;
  start: string; // "HH:MM"
  bay: number;
  service: string;
  status: BookingStatus;
  customer: string;
  phone: string;
  vehicle: string;
  source: Source;
}

export interface JobLine {
  kind: "labour" | "part" | "fee";
  description: string;
  qty: number;
  unit_cents: number;
}

export interface Job {
  job_id: number;
  title: string;
  status: JobStatus;
  customer: string;
  phone: string;
  vehicle: string;
  rego: string;
  lines: JobLine[];
  subtotal_cents: number;
  gst_cents: number;
  total_cents: number;
  invoice_number: string | null;
  mechanic_notes: string | null;
  booking_id: number | null;
}

export interface Approval {
  id: number;
  kind: string;
  title: string;
  detail: string;
  status: "pending" | "approved" | "rejected";
  created_at: string;
  ref_table: string | null;
  ref_id: number | null;
}

export interface ApprovalDecision extends Approval {
  approval_id?: number;
  sent_via?: string;
}

export interface EventItem {
  at: string;
  actor: string;
  action: string;
  detail: string | null;
}

export interface Overview {
  shop: { name: string; trading_name: string; address: string; hours: string; bays: number; owner: string };
  llm: { mode: string; fast: string; main: string; deep: string; tavily: boolean; twilio: boolean };
  today: string;
  bookings_today: Booking[];
  jobs_open: Job[];
  approvals_pending: Approval[];
  unpaid: { count: number; total_cents: number };
  cash_in_cents: number;
  cash_out_cents: number;
  bookings_tomorrow: number;
  events: EventItem[];
}

export interface Invoice {
  number: string;
  customer: string;
  job_id: number;
  subtotal_cents: number;
  gst_cents: number;
  total_cents: number;
  status: "issued" | "paid" | "void";
  issued_at: string;
  due: string | null;
  pdf: string;
  receipt: string | null;
}

export interface UnpaidInvoice {
  number: string;
  customer: string;
  total_cents: number;
  due: string | null;
  days_overdue: number;
}

export interface MoneySummary {
  from: string;
  to: string;
  cash_in_cents: number;
  cash_out_cents: number;
  gst_collected_cents: number;
  gst_paid_cents: number;
  invoices_issued: number;
}

export interface Money {
  summary: MoneySummary;
  series: { day: string; in: number; out: number }[];
  unpaid: UnpaidInvoice[];
}

export interface Part {
  id: number;
  sku: string | null;
  name: string;
  supplier: string | null;
  cost_cents: number;
  sell_cents: number;
  stock: number;
  reorder_level: number;
  low: boolean;
}

export interface Supplier {
  id: number;
  name: string;
  contact: string | null;
  channel: string;
  email: string | null;
  phone: string | null;
}

export interface PurchaseOrder {
  po_id: number;
  supplier: string;
  supplier_channel: string;
  status: "draft" | "sent" | "received" | "cancelled";
  job_id: number | null;
  lines: { description: string; qty: number; unit_cost_cents: number }[];
  total_cents: number;
  message: string | null;
  expected_date: string | null;
}

export interface PartsResponse {
  parts: Part[];
  suppliers: Supplier[];
  purchase_orders: PurchaseOrder[];
}

export interface ConversationSummary {
  id: number;
  channel: Channel;
  external_id: string;
  customer: string | null;
  intent: string | null;
  summary: string | null;
  last: string;
  updated_at: string;
}

export interface ConversationMessage {
  role: "user" | "assistant" | "tool" | "system";
  content: string;
  tool: string | null;
  tool_calls: string | null; // JSON string of OpenAI-style tool calls
  model: string | null;
  at: string;
}

export interface ConversationDetail {
  id: number;
  channel: Channel;
  external_id: string;
  messages: ConversationMessage[];
}

export interface OutboxItem {
  id: number;
  channel: Channel;
  to: string;
  subject: string | null;
  body: string;
  delivered: boolean;
  provider_ref: string | null;
  at: string;
}

export interface Report {
  day: string;
  content_md: string;
  model: string;
  created_at?: string;
}

export interface ChatStep {
  tool: string;
  args: Record<string, unknown>;
  result: unknown;
}

export interface ChatReply {
  reply: string;
  steps: ChatStep[];
  model: string;
}

// --- endpoints -----------------------------------------------------------------------

// --- owner app ------------------------------------------------------------------------

export interface OwnerJob extends Job {
  approval: { id: number; status: "pending" | "approved" | "rejected" } | null;
}

export interface OwnerResult {
  kind: "draft" | "reply";
  ok?: boolean;
  job?: Job | null;
  readback: string;
  warnings?: string[];
  transcript?: string;
  paid_method?: string;
  model?: string;
}

export interface OwnerToday {
  shop: string;
  owner: string;
  approver: string;
  jobs: OwnerJob[];
  arriving: Booking[];
}

export interface SendResult {
  status: "awaiting_approval" | "sent" | "already_invoiced";
  approval_id?: number;
  approver?: string;
  invoice_number?: string;
  total_cents?: number;
}

export interface ApproveView extends Approval {
  approver: string;
  shop: string;
  job?: Job | null;
}

export const api = {
  overview: () => get<Overview>("/api/overview"),

  bookings: (day = "today", days = 7) =>
    get<{ from: string; bookings: Booking[]; availability: unknown[] }>(`/api/bookings?day=${day}&days=${days}`),
  patchBooking: (id: number, body: { status?: BookingStatus; day?: string; start?: string }) =>
    patch<Booking>(`/api/bookings/${id}`, body),

  jobs: (status?: string) => get<{ jobs: Job[] }>(`/api/jobs${status ? `?status=${status}` : ""}`),
  job: (id: number) => get<Job>(`/api/jobs/${id}`),

  invoices: () => get<{ invoices: Invoice[] }>("/api/invoices"),
  recordPayment: (number: string, amount_cents: number, method = "card") =>
    post<{ number: string; status: string }>(`/api/invoices/${number}/payments`, { amount_cents, method }),
  money: (days = 30) => get<Money>(`/api/money?days=${days}`),

  parts: () => get<PartsResponse>("/api/parts"),

  approvals: () => get<{ approvals: Approval[] }>("/api/approvals"),
  decide: (id: number, approve: boolean) => post<ApprovalDecision>(`/api/approvals/${id}`, { approve }),

  conversations: () => get<{ conversations: ConversationSummary[] }>("/api/conversations"),
  conversation: (id: number) => get<ConversationDetail>(`/api/conversations/${id}`),

  outbox: () => get<{ outbox: OutboxItem[] }>("/api/outbox"),

  reports: () => get<{ reports: Report[] }>("/api/reports"),
  generateReport: () => post<Report>("/api/reports/generate"),

  chatCustomer: (text: string, session_id: string, channel: "web" | "sms" | "voice") =>
    post<ChatReply>("/api/chat/customer", { text, session_id, channel }),
  chatOwner: (text: string) => post<ChatReply>("/api/chat/owner", { text }),

  resetDemo: () => post<{ ok: boolean; today: string }>("/api/demo/reset"),

  ownerVoice: (text: string) => post<OwnerResult>("/api/owner/voice", { text }),
  ownerPhoto: (image_b64: string, mime = "image/jpeg") => post<OwnerResult>("/api/owner/photo", { image_b64, mime }),
  ownerToday: () => get<OwnerToday>("/api/owner/today"),
  ownerSend: (jobId: number) => post<SendResult>(`/api/owner/jobs/${jobId}/send`),
  ownerPaid: (jobId: number, method = "eftpos") => post<{ number: string; status: string }>(`/api/owner/jobs/${jobId}/paid`, { method }),

  approveView: (id: number, t: string) => get<ApproveView>(`/api/approve/${id}?t=${encodeURIComponent(t)}`),
  approveDecide: (id: number, t: string, approve: boolean, note?: string) =>
    post<ApproveView & { invoice_number?: string }>(`/api/approve/${id}`, { t, approve, note }),
};

/** Parse the OpenAI-style tool_calls JSON stored on assistant messages. */
export interface ParsedToolCall {
  id?: string;
  name: string;
  args: Record<string, unknown>;
}

export function parseToolCalls(json: string | null | undefined): ParsedToolCall[] {
  if (!json) return [];
  try {
    const raw = JSON.parse(json);
    if (!Array.isArray(raw)) return [];
    return raw.map((tc: Record<string, unknown>) => {
      const fn = (tc.function ?? {}) as { name?: string; arguments?: unknown };
      const name = (fn.name ?? (tc.name as string) ?? "tool") as string;
      let args: Record<string, unknown> = {};
      const a = fn.arguments ?? tc.arguments;
      if (typeof a === "string") {
        try {
          args = JSON.parse(a);
        } catch {
          args = { _raw: a };
        }
      } else if (a && typeof a === "object") {
        args = a as Record<string, unknown>;
      }
      return { id: tc.id as string | undefined, name, args };
    });
  } catch {
    return [];
  }
}

/** Pretty-print tool args as `key=value, key2=value2`. */
export function argsInline(args: Record<string, unknown>): string {
  return Object.entries(args)
    .map(([k, v]) => `${k}=${typeof v === "string" ? JSON.stringify(v) : JSON.stringify(v)}`)
    .join(", ");
}
