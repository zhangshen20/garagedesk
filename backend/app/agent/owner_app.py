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
from ..models import Booking, Channel, Job, JobStatus, Message
from . import memory
from .backoffice import OWNER_CONVERSATION_ID, handle_owner_message
from .frontdesk import get_or_create_conversation
from .jobcard import draft_from_extracted, extract, readback
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
    r"\b((?:\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight)\s*(?:hours?|hrs?|bucks|dollars)|hour and a half|half an hour|an hour|all up|labour\s+\$?\d+|\$\s*\d+|fitted|replaced|changed the)\b",
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


_QUESTION = re.compile(r"^\s*(?:and\s+|so\s+)?(what|what's|whats|when|where|who|which|how|why|did|does|has|have|is|are|was|were)\b(?!\s+(?:the|a|an)\s+\w+\s+(?:on|for)\b)", re.I)
_WAITING = re.compile(r"\bwaiting (?:on|for)\b", re.I)

# booking a car in is diary work, never a write-up, even when it names a service
_BOOKING = re.compile(r"\bbook(?:ed)?\s+(?:[\w']+\s+){0,3}in\b|\bbook (?:him|her|them|a|an|the)\b|\b(?:make|take) a booking\b|\b(?:pencil|squeeze)\s+(?:[\w']+\s+){0,3}in\b|\b(?:reschedule|move|cancel)\b[^.?]*\bbooking\b", re.I)
# "same as last time": last visit's work and figures, written up as today's job
_SAME_AGAIN = re.compile(r"\bsame (?:as|again|thing|job|work)\b|\bsame as (?:last|before|usual)\b|\bthe usual\b", re.I)

_DAY_WORDS = re.compile(r"\b(yesterday|yday|today|morning|arvo|afternoon|tonight|tomorrow|week|month|days?|ago|monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|tues|wed|thu|thurs|fri|sat|sun|\d{1,2}(?:st|nd|rd|th)?|\d{1,2}/\d{1,2}|january|february|march|april|may|june|july|august|september|october|november|december|recently|lately)\b", re.I)


def _said(when: str, text: str, context: list[dict[str, str]] | None) -> bool:
    """The day words came from him (or the conversation), not from the model."""
    heard = (text + " " + " ".join(m["content"] for m in context or [] if m["role"] == "user")).lower()
    words = _DAY_WORDS.findall(when.lower())
    return bool(words) and any(re.search(rf"\b{re.escape(w.lower())}", heard) for w in words)


def _status_from(text: str) -> str:
    t = text.lower()
    if re.search(r"(\bnot|n't|\bnever|yet to be|still to be|need(?:s)? to be|to be)(?: been| got| gotten| had)? (?:invoiced|billed)\b|\buninvoiced\b|\bno invoice\b|\bstill to (?:invoice|bill)\b|\bneeds? (?:an )?invoic", t):
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
    # a question ("what did we charge her", "what did that come to") never writes up an
    # invoice, and a car waiting on parts is a status, not work to bill
    if intent in ("job_card", "invoice") and not _WORK.search(text):
        if _QUESTION.match(text):
            intent = "find"
        elif _WAITING.search(text):
            intent = "other"
    if _BOOKING.search(text) and not _WORK.search(text):
        intent = "other"
    elif _SAME_AGAIN.search(text) and not _QUESTION.match(text):
        intent = "job_card"
    when = str(out.get("when") or "").strip()
    # a small model sometimes fills in a day he never said
    if when and not _said(when, text, context):
        when = ""
    # what he plainly said beats the model's guess
    status = _status_from(text) or str(out.get("status") or "").strip()
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


# Questions the job search can't answer from a list (bookings, what was charged, a
# car's history, "what did that come to"): the agent answers these with its memory.
_ASK_AGENT = re.compile(r"\b(booked|booking|bookings|charged?|come to|came to|cost|how much|last time|last in|usually|remember|notes?|take|took|takings|make|made|earn|earned|gst|bas|spent|expenses?|tomorrow|coming in|arriving)\b", re.I)


def _booking_today(s: Session, hint: str) -> dict[str, Any] | None:
    """A car booked in today that has no job yet."""
    if not hint:
        return None
    from .joblookup import _close, _words, spoken_key

    for b in s.exec(select(Booking).where(Booking.day == svc.today())).all():
        if s.exec(select(Job).where(Job.booking_id == b.id)).first():
            continue
        v = svc.booking_view(s, b)
        plate = v["vehicle"].split()[-1] if v["vehicle"] else ""
        have = _words(f"{v['vehicle']} {v['customer']}")
        if (plate and plate.upper() in spoken_key(hint)) or any(_close(w, h) for w in _words(hint) for h in have):
            return v
    return None


def _booked_today(s: Session, hint: str) -> str:
    """A car booked in today that has no job yet, e.g. "Liam's Ford Ranger"."""
    v = _booking_today(s, hint)
    return f"{(v['customer'] or 'The customer').split()[0]}'s {' '.join(v['vehicle'].split()[:-1])}" if v else ""


# changing a job that's already written up: "take the labour off the Nissan",
# "change the labour on the Corolla to two hours", "add wipers to Jack's car, 45"
_EDIT = re.compile(r"\b(?:take|knock)\b[^.?]*\b(?:off|out)\b|\b(?:remove|delete)\b|\bdrop\b[^.?]*\b(?:off|from)\b|\bchange\b[^.?]*\bto\b|\b(?:add|put)\b[^.?]*\b(?:to|on|onto)\b[^.?]*\b(?:invoice|job|car|bill)\b|\b(?:add|put)\b[^.?]*\b(?:to|on|onto) (?:the|his|her|\w+'s)\b", re.I)
_DID = re.compile(r"\b(replaced|fitted|did|done|finished|serviced|repaired|fixed|machined)\b", re.I)
_EDITABLE = [JobStatus.quoted, JobStatus.approved, JobStatus.in_progress, JobStatus.waiting_parts, JobStatus.done]


def named_job(s: Session, text: str) -> Job | None:
    """The one open job whose car or customer he named: make, model, rego or first name."""
    from .joblookup import _close, spoken_key

    words = set(re.findall(r"[a-z0-9]+", text.lower().replace("'s ", " ")))
    flat = spoken_key(text)
    best: list[tuple[int, Job]] = []
    for j in s.exec(select(Job).where(Job.status.in_(_EDITABLE)).order_by(Job.updated_at.desc())).all():  # type: ignore[attr-defined]
        v = svc.job_view(s, j)
        score = 0
        if v["rego"] and len(v["rego"]) >= 4 and v["rego"].upper() in flat:
            score = 100
        parts = v["vehicle"].split()
        car = [re.sub(r"[^a-z0-9]", "", w.lower()) for w in parts[:-1]] if len(parts) > 1 else []
        compact = re.sub(r"[^a-z0-9]", "", text.lower())
        score += sum(10 for c in car if len(c) >= 3 and (c in compact or any(_close(c, w) for w in words)))
        first = (v["customer"] or "").split()[0].lower() if v["customer"] else ""
        if first and first in words:
            score += 10
        if score:
            best.append((score, j))
    if not best:
        return None
    top = max(sc for sc, _ in best)
    hits = [j for sc, j in best if sc == top]
    return hits[0] if len(hits) == 1 else None


def edit_for(s: Session, text: str) -> dict[str, Any] | None:
    """A change to a job already written up. None when it isn't one."""
    if not _EDIT.search(text) or _BOOKING.search(text) or _DID.search(text):
        return None
    job = named_job(s, text)
    if not job:
        focus = memory.focus_job(s)
        # "take the labour off it": the job he's on, as long as he didn't name another car
        if focus and focus.status in _EDITABLE and not memory.mentioned(s, text):
            job = focus
    if not job:
        return None
    from .jobcard import edit_job

    d = edit_job(s, job, text, context=memory.owner_context(s, text, for_extract=True))
    # the job as it now stands, so a further "make it 300 all up" keeps the rest
    return {"kind": "draft", **d.as_dict(), "described": memory.job_in_words(s, job)}


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
    # booked in today with nothing written up yet beats last year's paid visits
    booked = "" if r["when"] else _booked_today(s, " ".join(x for x in (r["car"], r["customer"]) if x))
    if booked:
        return _reply(text, f"{booked} is booked in today but there's nothing on it yet. Tell me what you did and what to charge.", r["model"], jobs=[])
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
    # "what's the Civic in for": today's booking, not the job it had in September
    if not r["when"] and not r["status"] and (r["car"] or r["customer"]) and not any(j["day"] == svc.today().isoformat() for j in found["jobs"]):
        b = _booking_today(s, " ".join(x for x in (r["car"], r["customer"]) if x))
        if b:
            start = datetime.strptime(b["start"], "%H:%M").strftime("%-I:%M %p").replace(":00", "").lower()
            who = f"{(b['customer'] or 'The customer').split()[0]}'s {' '.join(b['vehicle'].split()[:-1])}"
            return _reply(text, f"{who} is booked in today at {start} for {b['service'].lower()}. Nothing written up on it yet.", r["model"], jobs=[])
    if len(found["jobs"]) == 1 and found["jobs"][0].get("has_lines"):
        # one job: say what it comes to as well
        j = found["jobs"][0]
        return _reply(text, spoken_list(found).rstrip(".") + f", ${j['total_cents'] / 100:,.2f}.", r["model"], jobs=found["jobs"])
    if not found["jobs"] and r["status"] and (r["car"] or r["customer"]):
        # "is the Hyundai paid": tell him where that car is at, whatever its state
        found = search_jobs(s, when=r["when"], car=r["car"], customer=r["customer"])
    return _reply(text, spoken_list(found), r["model"], jobs=found["jobs"], nearest=found.get("nearest", []))


def handle_voice(s: Session, text: str) -> dict[str, Any]:
    from ..voice import offers
    from ..voice.flow import reply_to_offer, with_voice

    # "yes" / "nah" answers the step the app just offered (send it, mark it paid)
    short = reply_to_offer(s, text)
    if short is not None:
        memory.remember_turn(s, text, short)
        return short
    # "the CX-5" after "which car?": carry on with what he asked for, now with the car
    asked = memory.answer_text(s, text)
    out = _handle(s, asked or text)
    if asked:
        out["transcript"] = text
    turn = memory.remember_turn(s, asked or text, out)  # what he said and which job it was about
    out = with_voice(out)
    offers.anchor(turn.id)  # a new offer made just now belongs to this turn
    return out


# "what's on today", "what have I got tomorrow", "who's coming in Friday": the diary, from code
_SCHEDULE = re.compile(r"\b(what'?s on|what is on|what (?:have|do) (?:i|we) (?:got|have)|what'?ve (?:i|we) got|who'?s (?:coming|booked|in)|who is (?:coming|booked|in)|how many (?:cars|bookings|jobs)|what cars|which cars are (?:coming|booked)|(?:today'?s|tomorrow'?s) (?:cars|bookings|jobs|list))\b", re.I)
_SCHEDULE_DAY = re.compile(r"\b(today|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.I)


def schedule_for(s: Session, text: str) -> dict[str, Any] | None:
    if not _SCHEDULE.search(text) or _WORK.search(text) or _status_from(text):
        return None
    m = _SCHEDULE_DAY.search(text)
    # "what's on the Nissan invoice" is about a car, not the diary
    if not m and not re.fullmatch(r"\W*(?:so\s+|and\s+|ok\s+)?(?:what'?s on|what is on|what (?:have|do) (?:i|we) (?:got|have)(?: on)?|what'?ve (?:i|we) got(?: on)?)\W*", text, re.I):
        return None
    if named_job(s, text):
        return None
    word = m.group(1).lower() if m else "today"
    day = svc.parse_day(word)
    from .joblookup import say_day

    said = "today" if day == svc.today() else "tomorrow" if word == "tomorrow" else f"on {say_day(day) if day < svc.today() else day.strftime('%A')}"
    bookings = s.exec(select(Booking).where(Booking.day == day).order_by(Booking.start)).all()  # type: ignore[arg-type]
    state = {"in_progress": "on the hoist", "waiting_parts": "waiting on parts", "done": "done, not invoiced", "invoiced": "invoiced", "paid": "paid"}
    items = []
    for b in bookings:
        if b.status.value in ("cancelled", "no_show"):
            continue
        v = svc.booking_view(s, b)
        job = s.exec(select(Job).where(Job.booking_id == b.id)).first()
        car = " ".join(v["vehicle"].split()[1:-1]) or "car"
        when = datetime.strptime(v["start"], "%H:%M").strftime("%-I:%M%p").replace(":00", "").lower()
        bit = f"{when} {(v['customer'] or 'someone').split()[0]}'s {car}, {v['service'].lower()}"
        if job and job.status.value in state:
            bit += f", {state[job.status.value]}"
        items.append(bit)
    n = len(items)
    if not n:
        return _reply(text, f"Nothing booked {said}.", "")
    head = f"{'One car' if n == 1 else f'{n} cars'} {said}"
    return _reply(text, f"{head}: " + "; ".join(items) + ".", "")


def _known_words(s: Session) -> dict[str, str]:
    """Every make, model, rego and customer first name the shop has, as he'd say them."""
    from ..models import Customer, Vehicle

    out: dict[str, str] = {}
    for v in s.exec(select(Vehicle)).all():
        for w in (v.make, v.model, v.rego):
            if w and len(w) >= 3:
                out[re.sub(r"[^a-z0-9]", "", w.lower())] = "car"
    for c in s.exec(select(Customer)).all():
        first = (c.name or "").split()[0].lower() if c.name else ""
        if len(first) >= 3:
            out[first] = "customer"
    return out


def _ground(s: Session, text: str, r: dict[str, Any]) -> dict[str, Any]:
    """The router fills the car and customer from his words or, for "that one", from the
    last exchange. When he did name a car or a person, it has to be the one he named:
    "is the Hyundai paid" right after talking about Jack's CX-5 is about the Hyundai."""
    known = _known_words(s)
    flat = re.sub(r"[^a-z0-9 ]", " ", text.lower().replace("'s ", " "))
    said = [w for w in flat.split() if w in known] + [k for k in known if len(k) >= 4 and k in flat.replace(" ", "") and k not in flat.split()]
    if not said:
        return r
    def his(value: str) -> str:
        # keep the model's words only where he said them ("Jack Thompson" when he said "Jack")
        words = re.sub(r"[^a-z0-9 ]", " ", (value or "").lower()).split()
        return " ".join(w for w in words if w in flat.split() or (len(w) >= 4 and w in flat.replace(" ", "")))

    cars = [w for w in said if known[w] == "car"]
    people = [w for w in flat.split() if known.get(w) == "customer"]
    return {**r, "car": his(r.get("car", "")) or " ".join(dict.fromkeys(cars)), "customer": his(r.get("customer", "")) or " ".join(dict.fromkeys(people))}


# "what did we take yesterday", "how much did I make this week", "how much GST this quarter"
_MONEY_Q = re.compile(r"\b(?:what|how much)\b[^?]*\b(?:take|took|taken|make|made|earn|earned|takings|bring in|brought in|come in|came in|in the till)\b|\b(?:gst|bas)\b", re.I)
_PERIOD = re.compile(r"\b(today|yesterday|(?:this|last) (?:week|month|quarter|year))\b", re.I)


def money_for(s: Session, text: str) -> dict[str, Any] | None:
    if not _MONEY_Q.search(text) or _WORK.search(text) or named_job(s, text):
        return None
    gst = bool(re.search(r"\b(?:gst|bas)\b", text, re.I))
    m = _PERIOD.search(text)
    period = m.group(1).lower() if m else ("this quarter" if gst else "today")
    from .tools import REGISTRY

    _, fn = REGISTRY["money_summary"]
    r = fn(s, period=period)
    d = lambda c: f"${c / 100:,.2f}"  # noqa: E731
    if gst:
        owe = r["gst_collected_cents"] - r["gst_paid_cents"]
        say = f"GST {period}: {d(r['gst_collected_cents'])} collected on invoices, {d(r['gst_paid_cents'])} paid on expenses, so " + (f"about {d(owe)} to pay." if owe >= 0 else f"about {d(-owe)} back.")
    else:
        say = f"{period[:1].upper()}{period[1:]} you took {d(r['cash_in_cents'])} and spent {d(r['cash_out_cents'])}."
        if r["invoices_issued"]:
            say += f" {r['invoices_issued']} invoice{'s' if r['invoices_issued'] != 1 else ''} went out."
    return _reply(text, say, "", steps=[{"tool": "money_summary", "args": {"period": period}, "result": r}])


_FILLER = re.compile(r"^[\s,.!?]*(?:(?:um+|uh+|er+|ah+|hmm+|mm+|oh|okay|ok|so|and|the|a|like|yeah|hello|hey|hi|test(?:ing)?|one two|mate)[\s,.!?]*)*$", re.I)


def _handle(s: Session, text: str) -> dict[str, Any]:
    if not text.strip() or _FILLER.match(text):
        out = _reply(text, "Sorry, I didn't catch that. Hold the button and tell me the car and what you need.", "")
        remember(s, text, out["readback"], "")
        return out
    # "25" when he was just asked what to charge for the one unpriced part
    priced = memory.fill_price(s, text)
    if priced:
        view = svc.job_view(s, priced)
        out = _draft(text, {"ok": True, "job": view, "readback": readback(view, [])}, "")
        remember(s, text, out["readback"], "")
        return out
    # "make it 380 all up" straight after a draft: his earlier words plus the change
    amended = memory.amend_text(s, text)
    if not amended:
        diary = schedule_for(s, text) or money_for(s, text)
        if diary:
            remember(s, text, diary["readback"], "")
            return diary
        edited = edit_for(s, text)
        if edited:
            remember(s, text, edited["readback"], edited.get("model", ""))
            return edited
    r = {"intent": "job_card", "model": ""} if amended else _ground(s, text, route(text, recent_context(s)))

    if r["intent"] == "job_card":
        words = amended or text
        ctx = memory.owner_context(s, words, for_extract=True)
        ex, ex_model = extract(words, ctx)
        ex = memory.ground_car(s, ex, words)
        out = {"kind": "draft", **draft_from_extracted(s, ex, words, ex_model).as_dict(), "transcript": text, "described": words}
        out["model"] = " + ".join(m for m in (r["model"], out.get("model")) if m)
        remember(s, text, out["readback"], out["model"])
        return out
    if r["intent"] == "invoice":
        out = invoice_for(s, text, r)
        remember(s, text, out["readback"], r["model"])
        return out
    if r["intent"] == "find" and not _ASK_AGENT.search(text):
        out = find_for(s, text, r)
        remember(s, text, out["readback"], r["model"])
        return out
    res = handle_owner_message(s, text, owner_app=True, context=memory.owner_context(s, text))
    model = " + ".join(m for m in (r["model"], res.model) if m)
    # the agent got an invoice ready: show it with the Send button
    for st in reversed(res.steps):
        if st["tool"] == "prepare_invoice" and st["result"].get("ok"):
            return _draft(text, {**st["result"], "readback": st["result"]["readback"]}, model)
    # "the CX-5 is done": the customer's been told, and if the work is already written up
    # the next thing he wants is its invoice, so have it ready to send
    for st in reversed(res.steps):
        if st["tool"] == "update_car_status" and st["result"].get("status") == "done" and st["result"].get("job_id"):
            job = s.get(Job, st["result"]["job_id"])
            d = prepare_invoice(s, job) if job else {"ok": False}
            if d["ok"]:
                told = f"Done, and {(st['result'].get('customer') or 'the customer').split()[0]}'s been told. "
                out = _draft(text, {**d, "readback": told + d["readback"]}, model)
                out["steps"] = res.steps
                return out
    # a parts order waits for a yes from him, here, not on a dashboard he never opens
    for st in reversed(res.steps):
        if st["tool"] == "order_parts" and st["result"].get("approval_id"):
            return _order_offer(s, text, st["result"], model, res.steps)
    return _reply(text, res.reply, model, steps=res.steps)


def _order_offer(s: Session, text: str, placed: dict[str, Any], model: str, steps: list[dict[str, Any]]) -> dict[str, Any]:
    from ..models import PurchaseOrder
    from ..voice import offers

    po = s.get(PurchaseOrder, placed.get("po_id") or 0)
    view = svc.po_view(s, po) if po else {"lines": [], "supplier": placed.get("supplier", ""), "total_cents": placed.get("total_cents", 0)}
    def short(d: str) -> str:
        # "FRONT Brake Pads for KIA CERATO 1.8 (YD) 2013-2020 – Ceramic, EP2240" -> "front brake pads for kia cerato 1.8"
        return " ".join(re.split(r"\s[–-]\s|[(,;]", d)[0].split()[:7]).lower()

    items = " and ".join(f"{l['qty']:g} x {short(l['description'])}" if l["qty"] != 1 else short(l["description"]) for l in view["lines"]) or "the parts"
    items = items[:1].upper() + items[1:]
    say = f"{items} from {view['supplier']}, ${view['total_cents'] / 100:,.2f} plus GST. Send the order?"
    out = _reply(text, say, model, steps=steps)
    out["offer"] = offers.put("order", say, approval_id=placed["approval_id"])
    return out
