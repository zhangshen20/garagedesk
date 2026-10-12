"""The tool-calling loop shared by the front-desk and back-office agents.

Transcript persistence is per Conversation so a customer can text back an hour
later and the agent still knows what was said."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from sqlmodel import Session, select

from ..llm import get_llm
from ..models import Conversation, Message
from .tools import run_tool, schemas_for

log = logging.getLogger(__name__)

MAX_STEPS = 8
HISTORY_LIMIT = 30


@dataclass
class AgentResult:
    reply: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    model: str = ""


def load_history(s: Session, conv: Conversation) -> list[dict[str, Any]]:
    msgs = s.exec(select(Message).where(Message.conversation_id == conv.id).order_by(Message.created_at, Message.id)).all()
    out: list[dict[str, Any]] = []
    for m in msgs[-HISTORY_LIMIT:]:
        if m.role == "tool":
            out.append({"role": "tool", "tool_call_id": m.tool_call_id, "name": m.tool_name, "content": m.content})
        elif m.role == "assistant" and m.tool_calls_json:
            out.append({"role": "assistant", "content": m.content or "", "tool_calls": json.loads(m.tool_calls_json)})
        else:
            out.append({"role": m.role, "content": m.content})
    # a transcript can't start with a dangling tool result
    while out and out[0]["role"] == "tool":
        out.pop(0)
    return out


def run_agent(
    s: Session,
    *,
    conv: Conversation,
    system_prompt: str,
    user_text: str,
    tool_names: list[str],
    tier: str = "main",
    tool_context: dict[str, Any] | None = None,
    stop_after: set[str] | None = None,
) -> AgentResult:
    """stop_after: tools whose successful result ends the turn (the caller shows it),
    saving a model round trip."""
    llm = get_llm()
    tools = schemas_for(tool_names)
    history = load_history(s, conv)
    s.add(Message(conversation_id=conv.id, role="user", content=user_text))
    s.flush()
    messages = [{"role": "system", "content": system_prompt}, *history, {"role": "user", "content": user_text}]
    steps: list[dict[str, Any]] = []
    model = ""
    for _ in range(MAX_STEPS):
        reply = llm.chat(messages, tier=tier, tools=tools)
        model = reply.model
        if not reply.tool_calls:
            text = (reply.content or "").strip() or "Sorry, I didn't catch that. Could you say it again?"
            s.add(Message(conversation_id=conv.id, role="assistant", content=text, model=model))
            s.flush()
            return AgentResult(reply=text, steps=steps, model=model)
        assistant_msg = reply.as_message()
        messages.append(assistant_msg)
        s.add(Message(conversation_id=conv.id, role="assistant", content=reply.content or "", tool_calls_json=json.dumps(assistant_msg["tool_calls"]), model=model))
        for tc in reply.tool_calls:
            args = dict(tc.arguments)
            if tool_context and tc.name in ("create_booking",):
                args.update(tool_context)
            result = run_tool(s, tc.name, args)
            s.flush()
            content = json.dumps(result, default=str)
            steps.append({"tool": tc.name, "args": tc.arguments, "result": result})
            log.info("tool %s(%s) -> %s", tc.name, tc.arguments, content[:200])
            messages.append({"role": "tool", "tool_call_id": tc.id, "name": tc.name, "content": content})
            s.add(Message(conversation_id=conv.id, role="tool", content=content, tool_name=tc.name, tool_call_id=tc.id))
        s.flush()
        last = steps[-1] if steps else None
        if stop_after and last and last["tool"] in stop_after and last["result"].get("ok"):
            text = str(last["result"].get("readback") or "Done.")
            s.add(Message(conversation_id=conv.id, role="assistant", content=text, model=model))
            s.flush()
            return AgentResult(reply=text, steps=steps, model=model)
    text = "I've done what I can for now; the owner will follow up with you shortly."
    s.add(Message(conversation_id=conv.id, role="assistant", content=text, model=model))
    return AgentResult(reply=text, steps=steps, model=model)
