"""The owner app's one big button. Whatever he says lands here.

Nemotron Nano reads it first, in well under a second, and pulls out what he wants
and which job he means:
  job_card -> he's telling us the work and the money: a draft invoice (jobcard.py)
  invoice  -> "do yesterday's invoice", "bill the Corolla": find that job in code
              and get its invoice ready to send
  find     -> "what did we do yesterday", "is the Hyundai paid": find and say it
  other    -> status updates, payments, parts orders, bookings, money: the
              back-office agent (Nemotron Super with tools)
Finding the job is plain code (joblookup.py), so it's quick and can't invent a job.
Each exchange is kept in the owner's conversation so a follow-up ("the Nissan
one") is read with what came before."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Any

from sqlmodel import Session, select

from .. import services as svc
from ..llm import get_llm
from ..models import Booking, Channel, Job, Message
from .backoffice import OWNER_CONVERSATION_ID, handle_owner_message
from .frontdesk import get_or_create_conversation
from .jobcard import draft_from_text
from .joblookup import describe, prepare_invoice, search_jobs, spoken_list

INTENT_PROMPT = """You read what a mechanic shop owner just said into his phone (speech recognition, so expect odd spelling, missing words and regos spelled out like "A B C one two three"). Today is {today}.
Work out what he wants and reply with JSON only:
{{"intent": "job_card" | "invoice" | "find" | "other",
 "when": "the day or period he means, in his words: 'yesterday', 'Friday', 'last week', 'this morning'; empty if none",
 "car": "words for the car: rego, make or model ('ABC123', 'Hyundai', 'the X-Trail'); empty if none",
 "customer": "customer name if said; empty if none",
 "status": "to_invoice" | "unpaid" | "paid" | "done" | "in_progress" | "waiting_parts" | ""}}
Intents:
"job_card": he says what was done on a car and/or what to charge (parts fitted, labour time, prices, "350 all up"). This wins even if he also says "invoice".
"invoice": he wants the invoice made or sent for work already in the system, without giving new work or prices: "do yesterday's invoices", "invoice the Corolla", "bill Priya", "prepare the invoice for the Nissan", "find yesterday's job and do the invoice".
"find": he asks about jobs or cars: "what did we do yesterday", "which cars aren't invoiced", "is the Hyundai paid", "find Maria's job", "what's Tom's car in for".
"other": anything else: a car's progress ("Hilux is done", "waiting on parts"), a payment ("Corolla paid on EFTPOS"), ordering parts, expenses, bookings and today's schedule, money totals, questions.
status: "to_invoice" for not invoiced yet or ready to bill, "unpaid" for owing money, otherwise what he said, else empty.
If his words only make sense as an answer to your last message (e.g. "the Nissan one", "yes, that one", "the first one"), use that message to fill intent, when and car."""

_WORK = re.compile(
    r"\b(\d+(?:\.\d+)?\s*(?:hours?|hrs?|bucks|dollars)|hour and a half|half an hour|an hour|all up|labour\s+\$?\d+|\$\s*\d+|fitted|replaced|changed the)\b",
    re.I,
)


_JOB_WORDS = re.compile(
    r"\b(pads?|rotors?|discs?|oil|filters?|battery|tyres?|tires?|wipers?|globes?|bulbs?|belts?|hoses?|plugs?|coolant|fluid|alignment|service|serviced|rwc|roadworthy|labour|replaced|fitted|changed|machined|flushed|scanned|cleared|repaired|fixed|swapped|diagnos\w*|\d+)\b",
    re.I,
)

_WANTS_INVOICE = re.compile(
    r"\b(prepare|prep|do|make|send|get|write|raise|create|generate|draft|sort|finish)\b[^.?]*\b(invoices?|bills?)\b|\binvoice (?:the|him|her|them|it|for)\b|\bbill (?:the|him|her|them)\b",
    re.I,
)


_DAY_WORDS = re.compile(r"\b(yesterday|yday|today|morning|arvo|afternoon|tonight|tomorrow|week|month|days?|ago|monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|tues|wed|thu|thurs|fri|sat|sun|\d{1,2}(?:st|nd|rd|th)?|\d{1,2}/\d{1,2}|january|february|march|april|may|june|july|august|september|october|november|december|recently|lately)\b", re.I)


def _said(when: str, text: str, context: list[dict[str, str]] | None) -> bool:
    """The day words came from him (or the conversation), not from the model."""
    heard = (text + " " + " ".join(m["content"] for m in context or [] if m["role"] == "user")).lower()
    words = _DAY_WORDS.findall(when.lower())
    return bool(words) and any(re.search(rf"\b{re.escape(w.lower())}", heard) for w in words)


def _status_from(text: str) -> str:
    t = text.lower()
    if re.search(r"(\bnot|n't|\bnever|yet to be|still to be|need(?:s)? to be|to be) invoiced\b|\bnot (?:been )?billed\b|\bstill to (?:invoice|bill)\b|\bneeds? (?:an )?invoic", t):
        return "to_invoice"
    if re.search(r"\b(owes?|owing|unpaid|outstanding|not paid|n't paid|hasn't paid|haven't paid)\b", t):
        return "unpaid"
    return ""


def route(text: str, context: list[dict[str, str]] | None = None) -> dict[str, Any]:
    prompt = INTENT_PROMPT.format(today=svc.today().strftime("%A %d %B %Y"))
    msgs = [{"role": "system", "content": prompt}, *(context or []), {"role": "user", "content": text}]
    r = get_llm().chat(msgs, tier="fast", json_mode=True, max_tokens=200, temperature=0)
    try:
        m = re.search(r"\{.*\}", r.content or "", flags=re.DOTALL)
        out = json.loads(m.group(0) if m else "{}")
    except json.JSONDecodeError:
        out = {}
    if not isinstance(out, dict):
        out = {}
    intent = str(out.get("intent") or "other")
    if intent not in ("job_card", "invoice", "find", "other"):
        intent = "job_card" if "job_card" in (r.content or "") else "other"
    # "find yesterday's job and do the invoice": he wants the invoice, not a list
    if intent == "find" and _WANTS_INVOICE.search(text):
        intent = "invoice"
    # he gave the work or the money, so it's a job card whatever else he said
    if intent == "invoice" and _WORK.search(text):
        intent = "job_card"
    # no work and no money in it ("the Nissan one"): there's nothing to write up, so
    # it's about a job we already have
    if intent == "job_card" and not (_WORK.search(text) or _JOB_WORDS.search(text)):
        intent = "invoice"
    when = str(out.get("when") or "").strip()
    # a small model sometimes fills in a day he never said
    if when and not _said(when, text, context):
        when = ""
    status = str(out.get("status") or "").strip()
    if not status:
        status = _status_from(text)
    return {
        "intent": intent,
        "when": when,
        "car": str(out.get("car") or "").strip(),
        "customer": str(out.get("customer") or "").strip(),
        "status": status,
        "model": r.model,
    }


# --- the owner's running conversation ------------------------------------------------


def _conversation(s: Session):
    conv = get_or_create_conversation(s, Channel.owner, OWNER_CONVERSATION_ID)
    conv.updated_at = datetime.utcnow()
    return conv


def recent_context(s: Session, turns: int = 2, within_minutes: int = 30) -> list[dict[str, str]]:
    """His last exchange or two, if recent, so "the Nissan one" makes sense."""
    conv = _conversation(s)
    since = datetime.utcnow() - timedelta(minutes=within_minutes)
    msgs = s.exec(
        select(Message)
        .where(Message.conversation_id == conv.id, Message.role.in_(["user", "assistant"]), Message.created_at >= since)  # type: ignore[attr-defined]
        .order_by(Message.created_at.desc(), Message.id.desc())  # type: ignore[attr-defined]
    ).all()
    out = [{"role": m.role, "content": m.content} for m in msgs if m.content][: turns * 2]
    return list(reversed(out))


def remember(s: Session, text: str, reply: str, model: str = "") -> None:
    conv = _conversation(s)
    s.add(Message(conversation_id=conv.id, role="user", content=text))
    s.add(Message(conversation_id=conv.id, role="assistant", content=reply, model=model))
    s.flush()


# --- the four paths ------------------------------------------------------------------


def _draft(text: str, d: dict[str, Any], model: str) -> dict[str, Any]:
    return {"kind": "draft", "ok": d["ok"], "job": d.get("job"), "readback": d["readback"], "warnings": d.get("warnings", []), "transcript": text, "extracted": {}, "paid_method": "", "model": model}


def _reply(text: str, readback: str, model: str, **extra: Any) -> dict[str, Any]:
    return {"kind": "reply", "readback": readback, "steps": extra.pop("steps", []), "model": model, **extra}


def _booked_today(s: Session, hint: str) -> str:
    """A car booked in today that has no job yet, e.g. "Liam's Ford Ranger"."""
    if not hint:
        return ""
    from .joblookup import _close, _words, spoken_key

    for b in s.exec(select(Booking).where(Booking.day == svc.today())).all():
        if s.exec(select(Job).where(Job.booking_id == b.id)).first():
            continue
        v = svc.booking_view(s, b)
        plate = v["vehicle"].split()[-1] if v["vehicle"] else ""
        have = _words(f"{v['vehicle']} {v['customer']}")
        if (plate and plate.upper() in spoken_key(hint)) or any(_close(w, h) for w in _words(hint) for h in have):
            return f"{(v['customer'] or 'The customer').split()[0]}'s {' '.join(v['vehicle'].split()[:-1])}"
    return ""


def invoice_for(s: Session, text: str, r: dict[str, Any]) -> dict[str, Any]:
    # whatever state he called it, the jobs worth invoicing are the ones not invoiced yet
    found = search_jobs(s, when=r["when"], car=r["car"], customer=r["customer"], status="to_invoice")
    jobs = found["jobs"]
    if len(jobs) == 1:
        job = s.get(Job, jobs[0]["job_id"])
        assert job
        d = prepare_invoice(s, job)
        if d["ok"]:
            return _draft(text, d, r["model"])
        return _reply(text, d["readback"], r["model"], jobs=jobs)
    if len(jobs) > 1:
        return _reply(text, f"{len(jobs)} jobs to invoice: " + "; ".join(describe(j) for j in jobs) + ". Which one?", r["model"], jobs=jobs)
    # nothing left to invoice: say why (already invoiced?) or what's close
    anyway = search_jobs(s, when=r["when"], car=r["car"], customer=r["customer"])
    if anyway["jobs"]:
        return _reply(text, f"Nothing left to invoice for {anyway['searched']}. " + "; ".join(describe(j) for j in anyway["jobs"]) + ".", r["model"], jobs=anyway["jobs"])
    booked = _booked_today(s, " ".join(x for x in (r["car"], r["customer"]) if x))
    if booked:
        return _reply(text, f"{booked} is booked in today but there's nothing on it yet. Tell me what you did and what to charge.", r["model"], jobs=[])
    near = [j for j in anyway.get("nearest", []) if j["status"] not in ("invoiced", "paid")] or anyway.get("nearest", [])
    readback = f"I couldn't find a job for {anyway['searched']}."
    if near:
        readback += " Closest I have: " + "; ".join(describe(j) for j in near) + ". Say which one."
    return _reply(text, readback, r["model"], jobs=[], nearest=near)


def find_for(s: Session, text: str, r: dict[str, Any]) -> dict[str, Any]:
    found = search_jobs(s, when=r["when"], car=r["car"], customer=r["customer"], status=r["status"])
    if not found["jobs"] and r["status"] and (r["car"] or r["customer"]):
        # "is the Hyundai paid": tell him where that car is at, whatever its state
        found = search_jobs(s, when=r["when"], car=r["car"], customer=r["customer"])
    return _reply(text, spoken_list(found), r["model"], jobs=found["jobs"], nearest=found.get("nearest", []))


def handle_voice(s: Session, text: str) -> dict[str, Any]:
    r = route(text, recent_context(s))
    if r["intent"] == "job_card":
        out = {"kind": "draft", **draft_from_text(s, text).as_dict()}
        out["model"] = " + ".join(m for m in (r["model"], out.get("model")) if m)
        remember(s, text, out["readback"], out["model"])
        return out
    if r["intent"] == "invoice":
        out = invoice_for(s, text, r)
        remember(s, text, out["readback"], r["model"])
        return out
    if r["intent"] == "find":
        out = find_for(s, text, r)
        remember(s, text, out["readback"], r["model"])
        return out
    res = handle_owner_message(s, text, owner_app=True)
    model = " + ".join(m for m in (r["model"], res.model) if m)
    # the agent got an invoice ready: show it with the Send button
    for st in reversed(res.steps):
        if st["tool"] == "prepare_invoice" and st["result"].get("ok"):
            return _draft(text, {**st["result"], "readback": st["result"]["readback"]}, model)
    return _reply(text, res.reply, model, steps=res.steps)
