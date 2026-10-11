import type { ReactNode } from "react";

/** Tiny markdown renderer: headings, bold/italic/code, bullet & numbered lists, paragraphs,
 * horizontal rules, simple pipe tables. Enough for agent replies and the daily report. */

function inline(text: string, key = 0): ReactNode[] {
  const out: ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*\n]+\*|_[^_\n]+_)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const tok = m[0];
    if (tok.startsWith("**")) out.push(<strong key={`${key}-${i++}`} className="font-semibold text-slate-900">{tok.slice(2, -2)}</strong>);
    else if (tok.startsWith("`")) out.push(<code key={`${key}-${i++}`} className="rounded bg-slate-100 px-1 py-px text-[0.9em] font-mono text-slate-800">{tok.slice(1, -1)}</code>);
    else out.push(<em key={`${key}-${i++}`}>{tok.slice(1, -1)}</em>);
    last = m.index + tok.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

export default function Markdown({ text, className = "" }: { text: string; className?: string }) {
  const lines = (text ?? "").replace(/\r\n/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let i = 0;
  let k = 0;

  while (i < lines.length) {
    const line = lines[i];
    const t = line.trim();
    if (!t) {
      i++;
      continue;
    }
    // heading
    const h = /^(#{1,4})\s+(.*)$/.exec(t);
    if (h) {
      const lvl = h[1].length;
      const cls = lvl === 1 ? "text-lg font-semibold mt-3 mb-1.5" : lvl === 2 ? "text-base font-semibold mt-3 mb-1" : "text-sm font-semibold mt-2.5 mb-1";
      blocks.push(<div key={k++} className={`${cls} text-slate-900`}>{inline(h[2], k)}</div>);
      i++;
      continue;
    }
    if (/^(-{3,}|\*{3,})$/.test(t)) {
      blocks.push(<hr key={k++} className="my-3 border-slate-200" />);
      i++;
      continue;
    }
    // table
    if (t.startsWith("|") && i + 1 < lines.length && /^\|?\s*:?-{2,}/.test(lines[i + 1].trim())) {
      const header = t.split("|").slice(1, -1).map((c) => c.trim());
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && lines[i].trim().startsWith("|")) {
        rows.push(lines[i].trim().split("|").slice(1, -1).map((c) => c.trim()));
        i++;
      }
      blocks.push(
        <div key={k++} className="my-2 overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr>{header.map((c, j) => <th key={j} className="text-left font-semibold text-slate-600 border-b border-slate-200 px-2 py-1">{inline(c, k)}</th>)}</tr>
            </thead>
            <tbody>
              {rows.map((r, ri) => (
                <tr key={ri} className="border-b border-slate-100">{r.map((c, j) => <td key={j} className="px-2 py-1 text-slate-700">{inline(c, k)}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }
    // bullet list
    if (/^[-*•]\s+/.test(t)) {
      const items: string[] = [];
      while (i < lines.length && /^[-*•]\s+/.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(/^[-*•]\s+/, ""));
        i++;
      }
      blocks.push(
        <ul key={k++} className="my-1.5 space-y-0.5 pl-4 list-disc marker:text-slate-400">
          {items.map((it, j) => <li key={j}>{inline(it, k * 100 + j)}</li>)}
        </ul>,
      );
      continue;
    }
    // numbered list
    if (/^\d+[.)]\s+/.test(t)) {
      const items: string[] = [];
      while (i < lines.length && /^\d+[.)]\s+/.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(/^\d+[.)]\s+/, ""));
        i++;
      }
      blocks.push(
        <ol key={k++} className="my-1.5 space-y-0.5 pl-5 list-decimal marker:text-slate-400">
          {items.map((it, j) => <li key={j}>{inline(it, k * 100 + j)}</li>)}
        </ol>,
      );
      continue;
    }
    // paragraph: collect until blank or structural line
    const para: string[] = [];
    while (i < lines.length) {
      const l = lines[i].trim();
      if (!l || /^(#{1,4})\s/.test(l) || /^[-*•]\s+/.test(l) || /^\d+[.)]\s+/.test(l) || l.startsWith("|") || /^(-{3,}|\*{3,})$/.test(l)) break;
      para.push(l);
      i++;
    }
    blocks.push(<p key={k++} className="my-1.5 leading-relaxed">{inline(para.join(" "), k)}</p>);
  }

  return <div className={`text-sm text-slate-700 ${className}`}>{blocks}</div>;
}
