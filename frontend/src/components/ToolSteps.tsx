import { Settings2 } from "lucide-react";
import type { ChatStep } from "../api";
import { argsInline } from "../api";

function short(v: unknown, max = 160): string {
  let s: string;
  if (typeof v === "string") s = v;
  else {
    try {
      s = JSON.stringify(v);
    } catch {
      s = String(v);
    }
  }
  return s.length > max ? s.slice(0, max - 1) + "…" : s;
}

/** A compact, collapsible row: ⚙ tool_name(args) → result */
export function ToolRow({ name, args, result, open = false }: { name: string; args: Record<string, unknown>; result?: unknown; open?: boolean }) {
  const full = result === undefined ? "" : typeof result === "string" ? result : JSON.stringify(result, null, 2);
  return (
    <details className="group rounded-md border border-slate-200 bg-slate-50/80 text-xs" open={open}>
      <summary className="cursor-pointer select-none list-none px-2 py-1 flex items-start gap-1.5 text-slate-600 hover:text-slate-800">
        <Settings2 size={12} className="mt-0.5 shrink-0 text-slate-400" />
        <span className="font-mono break-all">
          <span className="text-slate-800 font-medium">{name}</span>
          <span className="text-slate-500">({argsInline(args)})</span>
          {result !== undefined && (
            <>
              <span className="text-slate-400"> → </span>
              <span className="text-slate-600 group-open:hidden">{short(result, 90)}</span>
            </>
          )}
        </span>
      </summary>
      {result !== undefined && (
        <pre className="mx-2 mb-2 mt-0.5 max-h-56 overflow-auto rounded bg-white border border-slate-200 p-2 font-mono text-[11px] leading-snug text-slate-700 whitespace-pre-wrap break-all">{full}</pre>
      )}
    </details>
  );
}

export default function ToolSteps({ steps }: { steps: ChatStep[] | undefined }) {
  if (!steps?.length) return null;
  return (
    <div className="mt-1.5 flex flex-col gap-1">
      {steps.map((s, i) => <ToolRow key={i} name={s.tool} args={s.args ?? {}} result={s.result} />)}
    </div>
  );
}
