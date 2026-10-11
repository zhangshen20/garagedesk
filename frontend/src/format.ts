/** Formatting helpers: money from cents, Australian-style dates and times. */

const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** 123450 -> "$1,234.50"; negatives as "-$12.00". */
export function money(cents: number | null | undefined): string {
  const c = Math.round(cents ?? 0);
  const sign = c < 0 ? "-" : "";
  const abs = Math.abs(c);
  const dollars = Math.floor(abs / 100);
  const rem = (abs % 100).toString().padStart(2, "0");
  return `${sign}$${dollars.toLocaleString("en-AU")}.${rem}`;
}

/** Compact for tight tiles: 123450 -> "$1,234.50", 1234500 -> "$12.3k". */
export function moneyCompact(cents: number | null | undefined): string {
  const c = Math.round(cents ?? 0);
  if (Math.abs(c) >= 1_000_000) return `$${(c / 100_000).toFixed(1)}k`;
  return money(c);
}

/** "08:00" or "14:30:00" -> "8:00am" / "2:30pm". */
export function time(hhmm: string | null | undefined): string {
  if (!hhmm) return "";
  const [h, m] = hhmm.split(":").map((x) => parseInt(x, 10));
  if (Number.isNaN(h)) return hhmm;
  const suffix = h >= 12 ? "pm" : "am";
  const hour12 = h % 12 === 0 ? 12 : h % 12;
  return `${hour12}:${(m || 0).toString().padStart(2, "0")}${suffix}`;
}

function parseDate(iso: string): Date | null {
  if (!iso) return null;
  // Date-only strings are parsed as local dates; datetimes are UTC-naive from the server.
  if (/^\d{4}-\d{2}-\d{2}$/.test(iso)) {
    const [y, mo, d] = iso.split("-").map((x) => parseInt(x, 10));
    return new Date(y, mo - 1, d);
  }
  const d = new Date(iso.endsWith("Z") || /[+-]\d{2}:\d{2}$/.test(iso) ? iso : iso + "Z");
  return Number.isNaN(d.getTime()) ? null : d;
}

/** "2026-10-12" -> "Mon 12 Oct". */
export function date(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = parseDate(iso);
  if (!d) return iso;
  return `${DAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]}`;
}

/** "2026-10-12" -> "Monday 12 October 2026". */
export function dateLong(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = parseDate(iso);
  if (!d) return iso;
  return d.toLocaleDateString("en-AU", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
}

/** ISO datetime -> "8:05am". */
export function timeOf(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = parseDate(iso);
  if (!d) return "";
  return time(`${d.getHours()}:${d.getMinutes().toString().padStart(2, "0")}`);
}

/** ISO datetime -> "Mon 12 Oct, 8:05am". */
export function dateTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = parseDate(iso);
  if (!d) return "";
  return `${date(iso)}, ${timeOf(iso)}`;
}

/** ISO datetime -> "just now" / "4 min ago" / "2 h ago" / "Mon 12 Oct". */
export function relative(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = parseDate(iso);
  if (!d) return "";
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 45) return "just now";
  if (diff < 3600) return `${Math.round(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)} h ago`;
  return date(iso);
}

/** Day-of-week short label for chart axes: "2026-10-12" -> "12 Oct". */
export function dayShort(iso: string): string {
  const d = parseDate(iso);
  if (!d) return iso;
  return `${d.getDate()} ${MONTHS[d.getMonth()]}`;
}

/** Human label for enum-ish strings: "waiting_parts" -> "Waiting parts". */
export function label(s: string | null | undefined): string {
  if (!s) return "";
  const t = s.replace(/_/g, " ");
  return t.charAt(0).toUpperCase() + t.slice(1);
}

export function plural(n: number, one: string, many?: string): string {
  return `${n} ${n === 1 ? one : many ?? one + "s"}`;
}
