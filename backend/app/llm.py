"""Thin client over Nebius Token Factory's OpenAI-compatible API.

Three tiers of NVIDIA Nemotron are used on purpose:
  fast  -> Nemotron 3 Nano   : intent classification, cheap single-turn extraction
  main  -> Nemotron 3 Super  : the tool-calling front-desk and back-office agents
  deep  -> Nemotron 3 Ultra  : the end-of-day owner report (reasons over the whole day)

When no NEBIUS_API_KEY is set the module falls back to a deterministic mock so the
test-suite, CI and a keyless demo all still exercise the full tool loop."""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from .config import get_settings

log = logging.getLogger(__name__)

Tier = str  # "fast" | "main" | "deep"


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMReply:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    model: str = ""
    usage: dict[str, int] = field(default_factory=dict)

    def as_message(self) -> dict[str, Any]:
        msg: dict[str, Any] = {"role": "assistant", "content": self.content or ""}
        if self.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                }
                for tc in self.tool_calls
            ]
        return msg


def model_for(tier: Tier) -> str:
    s = get_settings()
    return {"fast": s.model_fast, "main": s.model_main, "deep": s.model_deep}[tier]


# --------------------------------------------------------------------------------------
# Real client
# --------------------------------------------------------------------------------------


class NebiusLLM:
    def __init__(self) -> None:
        from openai import OpenAI

        s = get_settings()
        self.client = OpenAI(api_key=s.nebius_api_key, base_url=s.nebius_base_url)

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tier: Tier = "main",
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1200,
        json_mode: bool = False,
    ) -> LLMReply:
        model = model_for(tier)
        kwargs: dict[str, Any] = dict(
            model=model, messages=messages, temperature=temperature, max_tokens=max_tokens
        )
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        if tier == "fast":
            # Nano's hidden reasoning otherwise eats the token budget on one-shot
            # extraction jobs and returns an empty or truncated answer.
            kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
        resp = self.client.chat.completions.create(**kwargs)
        choice = resp.choices[0].message
        calls: list[ToolCall] = []
        for tc in choice.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {"_raw": tc.function.arguments}
            calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))
        usage = {}
        if resp.usage:
            usage = {
                "prompt_tokens": resp.usage.prompt_tokens,
                "completion_tokens": resp.usage.completion_tokens,
            }
        # Nemotron reasoning models may wrap thinking in <think> tags; strip for display.
        content = _strip_think(choice.content)
        return LLMReply(content=content, tool_calls=calls, model=model, usage=usage)


def _strip_think(text: str | None) -> str | None:
    if not text:
        return text
    return re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL).strip()


# --------------------------------------------------------------------------------------
# Mock client: a small rule-based "agent" that calls the same tools the real model
# would, so the whole product can be exercised without a key.
# --------------------------------------------------------------------------------------


class MockLLM:
    """Deterministic stand-in. It inspects the latest user turn plus any tool results
    already in the transcript and decides the next tool call or final answer."""

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tier: Tier = "main",
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1200,
        json_mode: bool = False,
    ) -> LLMReply:
        model = f"mock/{model_for(tier).split('/')[-1]}"
        tool_names = {t["function"]["name"] for t in tools or []}
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        last_user = next((m for m in reversed(messages) if m["role"] == "user"), None)
        text = (last_user["content"] if last_user else "").lower()
        done = [m["name"] for m in messages if m["role"] == "tool"]
        results = {m["name"]: _safe_json(m["content"]) for m in messages if m["role"] == "tool"}

        def call(tool_name: str, **args: Any) -> LLMReply:
            return LLMReply(
                content=None,
                tool_calls=[ToolCall(id=f"call_{uuid.uuid4().hex[:8]}", name=tool_name, arguments=args)],
                model=model,
            )

        def say(s: str) -> LLMReply:
            return LLMReply(content=s, model=model)

        # ---- cheap single-turn jobs (tier fast) ----------------------------------------
        if json_mode and "classify" in system.lower():
            intent = "booking"
            if any(k in text for k in ("invoice", "receipt", "how much", "owe", "pay")):
                intent = "billing"
            elif any(k in text for k in ("ready", "status", "finished", "done yet")):
                intent = "job_status"
            elif any(k in text for k in ("hours", "open", "where", "address")):
                intent = "info"
            elif any(k in text for k in ("cancel", "reschedule", "move")):
                intent = "change_booking"
            return say(json.dumps({"intent": intent, "urgency": "normal"}))

        if "daily report" in system.lower() or tier == "deep":
            return say(_mock_report(messages))

        # ---- owner back-office agent ---------------------------------------------------
        if "back-office" in system.lower():
            if "order" in text and "order_parts" in tool_names:
                if "lookup_part_price" in tool_names and "lookup_part_price" not in done:
                    part = _extract_after(text, "order") or "brake pads"
                    return call("lookup_part_price", query=part)
                if "order_parts" not in done:
                    part = _extract_after(text, "order") or "brake pads"
                    price = results.get("lookup_part_price", {})
                    return call(
                        "order_parts",
                        supplier_name=price.get("best_supplier", "Burson Auto Parts"),
                        items=[{"description": part, "qty": 1, "unit_cost_cents": price.get("best_price_cents", 8900)}],
                        job_id=_extract_int(text, "job"),
                    )
                po = results.get("order_parts", {})
                return say(
                    f"Drafted purchase order #{po.get('po_id')} with {po.get('supplier')} and queued it for your approval. "
                    "Nothing is sent until you tap approve."
                )
            if "invoice" in text and "issue_invoice" in tool_names:
                if "issue_invoice" not in done:
                    return call("issue_invoice", job_id=_extract_int(text, "job") or 1)
                inv = results.get("issue_invoice", {})
                return say(
                    f"Tax invoice {inv.get('number')} issued for ${inv.get('total_cents', 0) / 100:.2f} inc GST and sent to the customer."
                )
            if ("today" in text or "schedule" in text or "bays" in text) and "list_bookings" in tool_names:
                if "list_bookings" not in done:
                    return call("list_bookings", day="today")
                bl = results.get("list_bookings", {}).get("bookings", [])
                lines = [f"- {b['start']} bay {b['bay']}: {b['customer']} ({b['vehicle']}) {b['service']}" for b in bl]
                return say("Today's board:\n" + ("\n".join(lines) if lines else "No bookings."))
            if ("owe" in text or "outstanding" in text or "unpaid" in text) and "list_unpaid_invoices" in tool_names:
                if "list_unpaid_invoices" not in done:
                    return call("list_unpaid_invoices")
                u = results.get("list_unpaid_invoices", {})
                return say(f"${u.get('total_cents', 0) / 100:.2f} outstanding across {len(u.get('invoices', []))} invoices.")
            if "expense" in text and "add_expense" in tool_names:
                if "add_expense" not in done:
                    m = re.search(r"\$\s*(\d+(?:\.\d{1,2})?)", text)
                    cents = int(round(float(m.group(1)) * 100)) if m else 0
                    desc = re.sub(r"^.*?expense[:,]?\s*", "", text).strip() or "expense"
                    desc = re.sub(r"\$\s*\d+(?:\.\d{1,2})?\s*", "", desc).strip(" ,.") or "expense"
                    return call("add_expense", description=desc, amount_cents=cents, category="consumables")
                e = results.get("add_expense", {})
                return say(f"Logged that expense (#{e.get('expense_id')}), GST portion ${e.get('gst_cents', 0) / 100:.2f}.")
            return say("Done. Anything else you want cleared off the desk?")

        # ---- customer front desk -------------------------------------------------------
        if any(k in text for k in ("hours", "open", "address", "where are you")):
            return say(
                "We're at Whitehill Ave, Sunshine North, open Mon-Sat 8am-5:30pm. Want me to book you in?"
            )
        if any(k in text for k in ("ready", "status", "done yet", "finished")) and "get_job_status" in tool_names:
            if "get_job_status" not in done:
                return call("get_job_status", rego=_extract_rego(text) or "")
            js = results.get("get_job_status", {})
            if js.get("found"):
                return say(f"Your {js['vehicle']} is {js['status_text']}. {js.get('next', '')}".strip())
            return say("I couldn't find a job under that rego. Can you double-check the plate?")
        if any(k in text for k in ("cancel", "reschedule", "move")) and "cancel_booking" in tool_names:
            if "find_booking" not in done:
                return call("find_booking", phone="", rego=_extract_rego(text) or "")
            fb = results.get("find_booking", {})
            if fb.get("found") and "cancel" in text and "cancel_booking" not in done:
                return call("cancel_booking", booking_id=fb["booking_id"])
            if "cancel_booking" in done:
                return say("No worries, that booking is cancelled. Call back any time to rebook.")
            return say("I found your booking. Which day would you like to move it to?")
        # default: booking flow
        if "find_or_create_customer" not in done:
            return call(
                "find_or_create_customer",
                name=_extract_name(text) or "",
                phone="",
                rego=_extract_rego(text) or "",
                vehicle=_extract_vehicle(text) or "",
            )
        if "list_availability" not in done:
            return call("list_availability", from_day="tomorrow", days=3)
        if "create_booking" not in done:
            slots = results.get("list_availability", {}).get("slots", [])
            if not slots:
                return say("We're fully booked for the next few days; can I take your number and call you back?")
            first = slots[0]
            return call(
                "create_booking",
                day=first["day"],
                start=first["start"],
                service=_extract_service(text) or "general service",
                customer_id=results.get("find_or_create_customer", {}).get("customer_id"),
                vehicle_id=results.get("find_or_create_customer", {}).get("vehicle_id"),
            )
        bk = results.get("create_booking", {})
        return say(
            f"You're booked in for {bk.get('day')} at {bk.get('start')} for a {bk.get('service')}. "
            f"Your reference is {bk.get('reference')}. We'll text you a reminder the day before."
        )


def _mock_report(messages: list[dict[str, Any]]) -> str:
    data = next((m["content"] for m in messages if m["role"] == "user"), "{}")
    d = _safe_json(data)
    return (
        "## End of day\n\n"
        f"**Cash in:** ${d.get('cash_in_cents', 0) / 100:,.2f}  ·  **Cash out:** ${d.get('cash_out_cents', 0) / 100:,.2f}  ·  "
        f"**Jobs completed:** {d.get('jobs_completed', 0)}\n\n"
        "### What needs you\n"
        + ("\n".join(f"- {a}" for a in d.get("pending_approvals", [])) or "Nothing waiting on you.") + "\n\n"
        "### Tomorrow\n"
        f"{d.get('bookings_tomorrow', 0)} cars booked. First drop-off 8:00am.\n\n"
        "*(mock report: set NEBIUS_API_KEY to have Nemotron 3 Ultra write this)*"
    )


def _safe_json(s: str) -> dict[str, Any]:
    try:
        v = json.loads(s)
        return v if isinstance(v, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _extract_rego(t: str) -> str | None:
    m = re.search(r"(?:rego|plate|registration)\s*(?:is\s*|number\s*)?([a-z0-9]{2,3}[- ]?[a-z0-9]{3})\b", t)
    if not m:
        # a 6-7 char token mixing letters and digits
        m = re.search(r"\b(?=[a-z0-9-]*\d)(?=[a-z0-9-]*[a-z])([a-z0-9]{2,3}[- ]?[a-z0-9]{3})\b", t)
    return m.group(1).upper().replace(" ", "").replace("-", "") if m else None


def _extract_name(t: str) -> str | None:
    m = re.search(r"(?:my name is|i'm|i am|this is|it's)\s+([a-z]+(?:\s[a-z]+)?)", t)
    return m.group(1).title() if m else None


def _extract_vehicle(t: str) -> str | None:
    m = re.search(
        r"\b(toyota|mazda|hyundai|kia|ford|holden|honda|nissan|subaru|vw|volkswagen|bmw|mercedes|tesla|mitsubishi|suzuki)\s+([a-z0-9-]+)",
        t,
    )
    return f"{m.group(1).title()} {m.group(2).title()}" if m else None


def _extract_service(t: str) -> str | None:
    for k in ("roadworthy", "rwc", "logbook", "brake", "tyre", "tire", "oil change", "service", "clutch", "battery"):
        if k in t:
            return {"rwc": "roadworthy inspection", "tire": "tyres", "roadworthy": "roadworthy inspection"}.get(k, k)
    return None


def _extract_after(t: str, word: str) -> str | None:
    m = re.search(word + r"\s+(?:some\s+|a\s+|the\s+)?([a-z0-9 \-]+?)(?:\s+for|\s+from|$|\.)", t)
    return m.group(1).strip() if m else None


def _extract_int(t: str, word: str) -> int | None:
    m = re.search(word + r"\s*#?\s*(\d+)", t)
    return int(m.group(1)) if m else None


# --------------------------------------------------------------------------------------

_client: NebiusLLM | MockLLM | None = None


def get_llm() -> NebiusLLM | MockLLM:
    global _client
    if _client is None:
        mode = get_settings().effective_llm_mode
        _client = NebiusLLM() if mode == "nebius" else MockLLM()
        log.info("LLM mode: %s", mode)
    return _client


def reset_llm() -> None:
    global _client
    _client = None
