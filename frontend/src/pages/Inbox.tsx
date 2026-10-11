import { useEffect, useRef, useState } from "react";
import { Phone, MessageSquare, Globe, Send, Loader2, Bot, User, PhoneCall } from "lucide-react";
import { api, parseToolCalls, type ConversationDetail, type ConversationMessage } from "../api";
import { useLoad, useRefreshOnChange } from "../hooks";
import { relative, timeOf } from "../format";
import { Card, Spinner, Empty, ErrorNote, ChannelIcon, channelName } from "../components/ui";
import StatusPill from "../components/StatusPill";
import { ToolRow } from "../components/ToolSteps";
import { toast } from "../components/Toaster";

type SimChannel = "voice" | "sms" | "web";

const CHANNELS: { id: SimChannel; label: string; icon: typeof Phone }[] = [
  { id: "voice", label: "Phone", icon: Phone },
  { id: "sms", label: "SMS", icon: MessageSquare },
  { id: "web", label: "Web chat", icon: Globe },
];

/** Transcript: user / assistant bubbles, tool calls as collapsible rows. */
function Transcript({ conv }: { conv: ConversationDetail }) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [conv]);

  // Pair tool results with the assistant tool_calls that precede them.
  type ToolCallView = { name: string; args: Record<string, unknown>; result?: string; at: string };
  const out: ({ kind: "msg"; m: ConversationMessage } | { kind: "tools"; calls: ToolCallView[] })[] = [];
  const msgs = conv.messages;
  for (let i = 0; i < msgs.length; i++) {
    const m = msgs[i];
    if (m.role === "system") continue;
    if (m.role === "assistant" && m.tool_calls) {
      const calls = parseToolCalls(m.tool_calls);
      const results: string[] = [];
      let j = i + 1;
      while (j < msgs.length && msgs[j].role === "tool") {
        results.push(msgs[j].content);
        j++;
      }
      if (m.content.trim()) out.push({ kind: "msg", m });
      out.push({ kind: "tools", calls: calls.map((c, k) => ({ name: c.name, args: c.args, result: results[k], at: m.at })) });
      i = j - 1;
      continue;
    }
    if (m.role === "tool") {
      out.push({ kind: "tools", calls: [{ name: m.tool ?? "tool", args: {}, result: m.content, at: m.at }] });
      continue;
    }
    if (!m.content.trim()) continue;
    out.push({ kind: "msg", m });
  }

  function parseResult(s: string | undefined): unknown {
    if (s === undefined) return undefined;
    try {
      return JSON.parse(s);
    } catch {
      return s;
    }
  }

  return (
    <div className="flex flex-col gap-2.5 px-4 py-4">
      {out.length === 0 && <Empty title="No messages yet" />}
      {out.map((it, i) =>
        it.kind === "tools" ? (
          <div key={i} className="ml-9 mr-6 flex flex-col gap-1">
            {it.calls.map((c, k) => <ToolRow key={k} name={c.name} args={c.args} result={parseResult(c.result)} />)}
          </div>
        ) : it.m.role === "user" ? (
          <div key={i} className="flex items-end gap-2 justify-end">
            <div className="max-w-[78%]">
              <div className="rounded-2xl rounded-br-md bg-slate-800 text-white px-3.5 py-2 text-sm whitespace-pre-wrap">{it.m.content}</div>
              <div className="text-right text-[10px] text-slate-400 mt-0.5 pr-1">{timeOf(it.m.at)}</div>
            </div>
            <span className="grid h-7 w-7 place-items-center rounded-full bg-slate-200 text-slate-600 shrink-0 mb-4">
              <User size={14} />
            </span>
          </div>
        ) : (
          <div key={i} className="flex items-end gap-2">
            <span className="grid h-7 w-7 place-items-center rounded-full bg-brand-100 text-brand-700 shrink-0 mb-4">
              <Bot size={14} />
            </span>
            <div className="max-w-[78%]">
              <div className="rounded-2xl rounded-bl-md bg-white border border-slate-200 px-3.5 py-2 text-sm text-slate-800 whitespace-pre-wrap">{it.m.content}</div>
              <div className="text-[10px] text-slate-400 mt-0.5 pl-1">
                {timeOf(it.m.at)}
                {it.m.model && <span className="text-slate-300"> · {it.m.model.split("/").pop()}</span>}
              </div>
            </div>
          </div>
        ),
      )}
      <div ref={end} />
    </div>
  );
}

/** Simulate a customer contacting the shop on a channel. */
function Simulate({ onDone }: { onDone: (externalId: string) => Promise<void> }) {
  const [channel, setChannel] = useState<SimChannel>("voice");
  const [phone, setPhone] = useState("+61 412 345 678");
  const [webId] = useState(() => `web-sim-${Math.random().toString(36).slice(2, 8)}`);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [reply, setReply] = useState<{ text: string; model: string; steps: number } | null>(null);

  const sessionId = channel === "web" ? webId : phone.replace(/\s+/g, "");

  async function send() {
    const t = text.trim();
    if (!t || busy) return;
    setBusy(true);
    setReply(null);
    try {
      const r = await api.chatCustomer(t, sessionId, channel);
      setReply({ text: r.reply, model: r.model, steps: r.steps.length });
      setText("");
      await onDone(sessionId);
      window.dispatchEvent(new CustomEvent("garagedesk:changed"));
    } catch (e) {
      toast(e instanceof Error ? e.message : "Failed to send", "err");
    } finally {
      setBusy(false);
    }
  }

  const examples: Record<SimChannel, string> = {
    voice: "Hi, I'd like to book a logbook service for my Corolla, rego ABC123, sometime tomorrow morning.",
    sms: "Can I move my booking to Thursday afternoon?",
    web: "What are your opening hours and do you do roadworthy certificates?",
  };

  return (
    <Card title={<span className="inline-flex items-center gap-1.5"><PhoneCall size={14} className="text-brand-600" /> Simulate a customer</span>} dense>
      <div className="p-3 space-y-2.5">
        <div className="grid grid-cols-3 gap-1 rounded-lg bg-slate-100 p-1">
          {CHANNELS.map((c) => (
            <button
              key={c.id}
              onClick={() => setChannel(c.id)}
              className={`inline-flex items-center justify-center gap-1.5 rounded-md px-2 py-1.5 text-xs font-medium transition-colors ${
                channel === c.id ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-800"
              }`}
            >
              <c.icon size={13} /> {c.label}
            </button>
          ))}
        </div>
        {channel === "web" ? (
          <div className="text-xs text-slate-500">
            Session <span className="font-mono text-slate-700">{webId}</span>
          </div>
        ) : (
          <input value={phone} onChange={(e) => setPhone(e.target.value)} className="input font-mono" placeholder="Customer phone number" />
        )}
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send();
            }
          }}
          rows={3}
          className="input resize-none"
          placeholder={channel === "voice" ? "What the caller says…" : "Message from the customer…"}
        />
        <div className="flex items-center justify-between gap-2">
          <button type="button" className="text-xs text-brand-700 hover:underline" onClick={() => setText(examples[channel])}>
            Use an example
          </button>
          <button className="btn-primary" onClick={() => void send()} disabled={busy || !text.trim()}>
            {busy ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
            {channel === "voice" ? "Speak" : "Send"}
          </button>
        </div>
        {reply && (
          <div className="rounded-lg border border-brand-200 bg-brand-50 px-3 py-2 text-sm text-slate-800 fade-up">
            <div className="flex items-center gap-1.5 text-[11px] font-medium text-brand-800 mb-1">
              <Bot size={12} /> Front desk replied
              {reply.steps > 0 && <span className="text-brand-600/80">· {reply.steps} tool {reply.steps === 1 ? "call" : "calls"}</span>}
            </div>
            <p className="whitespace-pre-wrap">{reply.text}</p>
            <div className="text-[10px] text-slate-400 mt-1">{reply.model}</div>
          </div>
        )}
      </div>
    </Card>
  );
}

export default function Inbox() {
  const list = useLoad(() => api.conversations(), [], 15000);
  const [selected, setSelected] = useState<number | null>(null);
  const detail = useLoad(() => (selected ? api.conversation(selected) : Promise.resolve(null)), [selected]);

  useRefreshOnChange(list.refresh);

  // Default to the newest conversation.
  useEffect(() => {
    if (selected === null && list.data?.conversations.length) setSelected(list.data.conversations[0].id);
  }, [list.data, selected]);

  async function afterSimulate(externalId: string) {
    await list.refresh();
    const fresh = await api.conversations();
    const hit = fresh.conversations.find((c) => c.external_id === externalId);
    if (hit) {
      if (hit.id === selected) await detail.refresh();
      else setSelected(hit.id);
    }
  }

  const convs = list.data?.conversations ?? [];
  const current = convs.find((c) => c.id === selected);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl md:text-2xl font-semibold tracking-tight text-slate-900">Inbox</h1>
          <p className="text-sm text-slate-500 mt-0.5">Every phone call, text and web chat the front-desk agent has handled.</p>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[300px_minmax(0,1fr)_320px]">
        {/* Conversation list */}
        <Card className="overflow-hidden lg:h-[calc(100vh-11rem)] flex flex-col" title="Conversations" action={<span className="text-xs text-slate-500">{convs.length}</span>} dense>
          <div className="flex-1 overflow-y-auto">
            {list.loading && !list.data && <Spinner />}
            {list.error && !list.data && <div className="p-3"><ErrorNote error={list.error} /></div>}
            {list.data && convs.length === 0 && <Empty title="No conversations yet" hint="Use the simulator to have a customer call in." />}
            <ul className="divide-y divide-slate-100">
              {convs.map((c) => (
                <li key={c.id}>
                  <button
                    onClick={() => setSelected(c.id)}
                    className={`w-full text-left px-3.5 py-2.5 hover:bg-slate-50 transition-colors ${selected === c.id ? "bg-brand-50/70 border-l-2 border-brand-500" : "border-l-2 border-transparent"}`}
                  >
                    <div className="flex items-center gap-2">
                      <span className="grid h-7 w-7 place-items-center rounded-full bg-slate-100 text-slate-600 shrink-0">
                        <ChannelIcon channel={c.channel} size={13} />
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-sm font-medium text-slate-800 truncate">{c.customer ?? (c.channel === "owner" ? "Owner · desk assistant" : c.external_id)}</span>
                          <span className="text-[10px] text-slate-400 shrink-0">{relative(c.updated_at)}</span>
                        </div>
                        <div className="flex items-center gap-1.5 mt-0.5">
                          {c.intent && <StatusPill status={c.intent} size="xs" />}
                          <span className="text-xs text-slate-500 truncate">{c.last || c.summary || channelName(c.channel)}</span>
                        </div>
                      </div>
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </Card>

        {/* Transcript */}
        <Card
          className="overflow-hidden lg:h-[calc(100vh-11rem)] flex flex-col bg-slate-50/50"
          dense
          title={
            current ? (
              <span className="inline-flex items-center gap-2">
                <ChannelIcon channel={current.channel} size={14} className="text-slate-500" />
                {current.customer ?? (current.channel === "owner" ? "Owner · desk assistant" : current.external_id)}
                <span className="text-xs font-normal text-slate-400">{channelName(current.channel)} · {current.external_id}</span>
              </span>
            ) : (
              "Transcript"
            )
          }
          action={current?.intent ? <StatusPill status={current.intent} /> : undefined}
        >
          <div className="flex-1 overflow-y-auto">
            {!selected && <Empty title="Pick a conversation" hint="Select a conversation on the left to read the transcript and the tools the agent used." />}
            {selected && detail.loading && !detail.data && <Spinner />}
            {selected && detail.error && <div className="p-3"><ErrorNote error={detail.error} /></div>}
            {selected && detail.data && <Transcript conv={detail.data} />}
          </div>
        </Card>

        {/* Simulator */}
        <div className="space-y-3">
          <Simulate onDone={afterSimulate} />
          <p className="text-xs text-slate-500 px-1">
            Live calls arrive via Twilio at <span className="font-mono">/twilio/voice</span>; here you can play the customer and watch the agent book, reschedule and answer in real time.
          </p>
        </div>
      </div>
    </div>
  );
}
