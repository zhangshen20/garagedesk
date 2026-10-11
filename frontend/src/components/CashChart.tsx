import { useMemo, useState } from "react";
import { money, date, dayShort } from "../format";

/** 30-day cash in / cash out grouped columns. Follows the dataviz method:
 * two categorical slots (blue = in, orange = out, validated), thin columns with
 * 4px rounded caps, hairline gridlines, legend for two series, hover tooltip,
 * selective direct labels (largest value per series only), and a table view. */

const SERIES = {
  in: { label: "Cash in", color: "#2a78d6" },
  out: { label: "Cash out", color: "#eb6834" },
};

interface Point {
  day: string;
  in: number;
  out: number;
}

function niceMax(v: number): number {
  if (v <= 0) return 100_00;
  const pow = Math.pow(10, Math.floor(Math.log10(v)));
  const n = v / pow;
  const step = n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10;
  return step * pow;
}

function tick(cents: number): string {
  if (cents === 0) return "0";
  const d = cents / 100;
  if (d >= 1000) return `$${(d / 1000).toFixed(d % 1000 === 0 ? 0 : 1)}k`;
  return `$${d.toFixed(0)}`;
}

export default function CashChart({ series }: { series: Point[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const [view, setView] = useState<"chart" | "table">("chart");

  const W = 760;
  const H = 240;
  const padL = 44;
  const padR = 12;
  const padT = 14;
  const padB = 28;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;

  const maxV = useMemo(() => niceMax(Math.max(0, ...series.map((p) => Math.max(p.in, p.out)))), [series]);
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * maxV);
  const n = Math.max(series.length, 1);
  const band = plotW / n;
  const gap = 2; // surface gap between the two columns
  const barW = Math.min(24, Math.max(3, (band - 6 - gap) / 2));
  const y = (v: number) => padT + plotH - (v / maxV) * plotH;

  const maxIn = Math.max(...series.map((p) => p.in));
  const maxOut = Math.max(...series.map((p) => p.out));
  const totalIn = series.reduce((a, p) => a + p.in, 0);
  const totalOut = series.reduce((a, p) => a + p.out, 0);
  const anyData = totalIn + totalOut > 0;

  function column(x: number, v: number, color: string, key: string) {
    if (v <= 0) return null;
    const top = y(v);
    const h = Math.max(0, padT + plotH - top);
    const r = Math.min(4, barW / 2, h);
    // Rounded top, square baseline.
    const d = `M${x},${padT + plotH} V${top + r} Q${x},${top} ${x + r},${top} H${x + barW - r} Q${x + barW},${top} ${x + barW},${top + r} V${padT + plotH} Z`;
    return <path key={key} d={d} fill={color} />;
  }

  const labelEvery = Math.max(1, Math.ceil(n / 6));

  return (
    <div className="viz-root" style={{ color: "#52514e" }}>
      <div className="flex flex-wrap items-center justify-between gap-2 px-5 pt-3">
        <div className="flex items-center gap-4 text-xs text-slate-600">
          {(["in", "out"] as const).map((k) => (
            <span key={k} className="inline-flex items-center gap-1.5">
              <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: SERIES[k].color }} />
              {SERIES[k].label}
              <span className="text-slate-400 tnum">{money(k === "in" ? totalIn : totalOut)}</span>
            </span>
          ))}
        </div>
        <div className="inline-flex rounded-md border border-slate-200 text-xs overflow-hidden">
          {(["chart", "table"] as const).map((v) => (
            <button key={v} onClick={() => setView(v)} className={`px-2.5 py-1 capitalize ${view === v ? "bg-slate-100 text-slate-900 font-medium" : "text-slate-500 hover:bg-slate-50"}`}>
              {v}
            </button>
          ))}
        </div>
      </div>

      {view === "table" ? (
        <div className="max-h-72 overflow-auto px-5 pb-4 pt-2">
          <table className="min-w-full text-sm">
            <thead className="sticky top-0 bg-white">
              <tr>
                <th className="th">Day</th>
                <th className="th text-right">Cash in</th>
                <th className="th text-right">Cash out</th>
                <th className="th text-right">Net</th>
              </tr>
            </thead>
            <tbody>
              {series.map((p) => (
                <tr key={p.day} className="border-t border-slate-100">
                  <td className="td">{date(p.day)}</td>
                  <td className="td text-right tnum">{money(p.in)}</td>
                  <td className="td text-right tnum">{money(p.out)}</td>
                  <td className={`td text-right tnum ${p.in - p.out < 0 ? "text-red-700" : ""}`}>{money(p.in - p.out)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="relative px-2 pb-2">
          {!anyData && <div className="absolute inset-0 grid place-items-center text-sm text-slate-400">No cash movement in this period</div>}
          <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto block" role="img" aria-label="Cash in and cash out per day, last 30 days" onMouseLeave={() => setHover(null)}>
            {ticks.map((t, i) => (
              <g key={i}>
                <line x1={padL} x2={W - padR} y1={y(t)} y2={y(t)} stroke={i === 0 ? "#c3c2b7" : "#e9e8e3"} strokeWidth={1} />
                <text x={padL - 8} y={y(t) + 3.5} textAnchor="end" fontSize={10} fill="#898781" style={{ fontVariantNumeric: "tabular-nums" }}>
                  {tick(t)}
                </text>
              </g>
            ))}
            {series.map((p, i) => {
              const x0 = padL + i * band;
              const cx = x0 + band / 2;
              const xIn = cx - barW - gap / 2;
              const xOut = cx + gap / 2;
              const isHover = hover === i;
              return (
                <g key={p.day}>
                  {isHover && <rect x={x0} y={padT} width={band} height={plotH} fill="#0b0b0b" opacity={0.04} />}
                  {column(xIn, p.in, SERIES.in.color, "in")}
                  {column(xOut, p.out, SERIES.out.color, "out")}
                  {p.in > 0 && p.in === maxIn && !isHover && (
                    <text x={xIn + barW / 2} y={y(p.in) - 4} textAnchor="middle" fontSize={10} fill="#52514e" fontWeight={500}>
                      {money(p.in)}
                    </text>
                  )}
                  {p.out > 0 && p.out === maxOut && !isHover && p.out !== maxIn && (
                    <text x={xOut + barW / 2} y={y(p.out) - 4} textAnchor="middle" fontSize={10} fill="#52514e" fontWeight={500}>
                      {money(p.out)}
                    </text>
                  )}
                  {i % labelEvery === 0 && (
                    <text x={cx} y={H - 10} textAnchor="middle" fontSize={10} fill="#898781">
                      {dayShort(p.day)}
                    </text>
                  )}
                  <rect x={x0} y={padT} width={band} height={plotH} fill="transparent" onMouseEnter={() => setHover(i)} />
                </g>
              );
            })}
          </svg>
          {hover !== null && series[hover] && (
            <div
              className="pointer-events-none absolute top-3 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs shadow-float"
              style={{ left: `${Math.min(88, Math.max(6, ((padL + (hover + 0.5) * band) / W) * 100))}%`, transform: "translateX(-50%)" }}
            >
              <div className="font-medium text-slate-800 mb-1">{date(series[hover].day)}</div>
              <div className="flex items-center gap-1.5 tnum">
                <span className="h-2 w-2 rounded-sm" style={{ background: SERIES.in.color }} /> In <span className="ml-auto pl-3 text-slate-800">{money(series[hover].in)}</span>
              </div>
              <div className="flex items-center gap-1.5 tnum">
                <span className="h-2 w-2 rounded-sm" style={{ background: SERIES.out.color }} /> Out <span className="ml-auto pl-3 text-slate-800">{money(series[hover].out)}</span>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
