"""The owner app's memory: what he said earlier and what the shop knows about the
cars he mentions, put in front of the model every time he talks.

Two layers:
  short term  every turn (what he said, what we did, which job) in OwnerTurn, so
              "that one", "make it 380 all up" or "the CX-5 I did this
              morning" resolve to a job.
  long term   the shop's own records for each car he names: past visits with their
              lines and totals, notes left on jobs, and facts he asked us to keep
              (OwnerFact). These are records, never guesses, so a "same as last time"
              invoice uses last time's real figures.

owner_context(s, text) builds the block the router, the extractor and the back-office
agent all read; remember_turn(s, text, out) records each turn afterwards."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlmodel import Session, select

from .. import services as svc
from ..config import get_settings
from ..models import (
    Booking,
    BookingStatus,
    Customer,
    Invoice,
    InvoiceStatus,
    Job,
    JobLine,
    JobStatus,
    LineKind,
    OwnerFact,
    OwnerTurn,
    Vehicle,
)
from . import knowhow

RECENT_TURNS = 10
RECENT_DAYS = 3
FOCUS_HOURS = 12  # "that one" means to a job he talked about since this morning, not last week
HISTORY_VISITS = 3

# --- time -------------------------------------------------------------------------------


def _tz() -> ZoneInfo:
    return ZoneInfo(get_settings().shop_timezone)


def _local(dt: datetime) -> datetime:
    """Stored times are naive UTC."""
    return dt.replace(tzinfo=ZoneInfo("UTC")).astimezone(_tz())


def _when(dt: datetime) -> str:
    d = _local(dt)
    days = (svc.today() - d.date()).days
    day = "today" if days == 0 else "yesterday" if days == 1 else d.strftime("%a %d %b")
    return f"{day} {d.strftime('%H:%M')}"


def _dollars(cents: int) -> str:
    return f"${cents / 100:,.2f}"


# --- short term: turns and the job he's on -------------------------------------------------


def _job_from(out: dict[str, Any]) -> int | None:
    job = out.get("job") or {}
    if job.get("job_id"):
        return int(job["job_id"])
    jobs = out.get("jobs") or []
    if len(jobs) == 1 and jobs[0].get("job_id"):
        return int(jobs[0]["job_id"])
    for st in reversed(out.get("steps") or []):
        r = st.get("result") or {}
        if isinstance(r, dict) and r.get("job_id"):
            return int(r["job_id"])
        args = st.get("args") or {}
        if isinstance(args, dict) and args.get("job_id"):
            try:
                return int(args["job_id"])
            except (TypeError, ValueError):
                continue
    return None


def remember_turn(s: Session, said: str, out: dict[str, Any]) -> OwnerTurn:
    """Record what he said and what came of it, and which job it was about."""
    job_id = _job_from(out)
    job = s.get(Job, job_id) if job_id else None
    outcome = str(out.get("readback") or "")
    kind = str(out.get("kind") or "reply")
    ready = kind == "draft" and bool(out.get("ok")) and not out.get("warnings")
    described = ""
    if kind == "draft":
        # his own description when he gave one; for an invoice got ready from a job already
        # on file ("the Corolla"), the job as it stands, so "add wipers" keeps the rest
        described = str(out.get("described") or (job_in_words(s, job) if job else said))
    t = OwnerTurn(said=said, kind=kind, outcome=outcome[:600], ready=ready, described=described[:1000], job_id=job.id if job else None, customer_id=job.customer_id if job else None)
    s.add(t)
    s.flush()
    return t


def job_in_words(s: Session, job: Job) -> str:
    """The job as he'd say it on the phone: car, then each line with what it costs inc
    GST (labour by the hour when it's at the shop rate), then the total if he set one."""
    view = svc.job_view(s, job)
    gst = 1 + get_settings().gst_rate
    rate = get_settings().labour_rate_cents
    bits = []
    for l in view["lines"]:
        if l["kind"] == "labour" and l["unit_cents"] == rate:
            bits.append(f"{l['description']}, {l['qty']:g} hours labour")
        elif l["kind"] == "labour":
            bits.append(f"{l['description']}, labour {l['qty'] * l['unit_cents'] * gst / 100:.2f}")
        else:
            qty = f"{l['qty']:g} x " if l["qty"] != 1 else ""
            bits.append(f"{qty}{l['description']} {l['qty'] * l['unit_cents'] * gst / 100:.2f}")
    words = f"{view['customer']}'s {view['vehicle']}: " + "; ".join(bits)
    if job.stated_total_cents:
        words += f"; {job.stated_total_cents / 100:.2f} all up"
    return words


def recent_turns(s: Session, limit: int = RECENT_TURNS) -> list[OwnerTurn]:
    since = datetime.utcnow() - timedelta(days=RECENT_DAYS)
    rows = s.exec(select(OwnerTurn).where(OwnerTurn.created_at >= since).order_by(OwnerTurn.id.desc()).limit(limit)).all()  # type: ignore[attr-defined]
    return list(reversed(rows))


def focus_job(s: Session) -> Job | None:
    """The job he's been talking about most recently: what "it" and "that one" mean."""
    since = datetime.utcnow() - timedelta(hours=FOCUS_HOURS)
    t = s.exec(select(OwnerTurn).where(OwnerTurn.created_at >= since, OwnerTurn.job_id != None).order_by(OwnerTurn.id.desc())).first()  # type: ignore[attr-defined]  # noqa: E711
    return s.get(Job, t.job_id) if t and t.job_id else None


_AMEND = re.compile(r"^\s*(?:(?:actually|no|nah|sorry|oh|and|also|plus|wait|hang on|mate)[\s,.!]+)*(?:make it|make that|change|add|put|take off|take out|remove|drop|forget|it was|labour was|that was|charge (?:her|him|them|it))\b", re.I)


_FILLS_IN = re.compile(r"\b(rego|registration|plate|customer|name is|owner is)\b", re.I)

# the app asked him something it needs before it can act: which car, which job, what price
_ASKED = re.compile(r"\?|\b(which (?:car|one|job)|say the rego|tell me the car|couldn't match|could you let me know)\b", re.I)
# a fresh request or question rather than an answer to one
_NEW_ASK = re.compile(r"\b(done|finished|ready|invoice|send|sent|paid|pay|order|book|booked|add|change|make|remove|cancel|waiting|remember|what|what's|when|how|who|why|is|has|did|does|can|yes|yep|yeah|no|nah|nope)\b", re.I)
ASK_MINUTES = 10


def is_answer(s: Session, text: str) -> bool:
    """A few words naming a car, a customer, a job or a price: "the CX-5", "Maria's",
    "the pads one", "45"."""
    if len(text.split()) > 6 or _NEW_ASK.search(text):
        return False
    return bool(mentioned(s, text) or knowhow.cars_in(text) or knowhow.services_in(text) or re.search(r"\d", text)
                or _ORDINAL.search(text) or _DAY.search(text))


_ORDINAL = re.compile(r"\b(first|1st|top|second|2nd|third|3rd|fourth|4th|last|bottom)\b", re.I)
_ORDINAL_AT = {"first": 0, "1st": 0, "top": 0, "second": 1, "2nd": 1, "third": 2, "3rd": 2, "fourth": 3, "4th": 3, "last": -1, "bottom": -1}
_DAY = re.compile(r"\b(today|yesterday|this morning|last week|the other day|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.I)
_FILLER = {"the", "one", "a", "that", "for", "from", "on", "it", "its", "it's", "s", "mate", "please", "um", "uh", "oh"}


def _listed(outcome: str) -> list[str]:
    """The jobs a "which one?" reply read out: "3 jobs to invoice: A; B; C. Which one?"."""
    m = re.search(r":\s*(.+?)\.\s*(?:Which one\?|Say which one\.)", outcome, re.S)
    return [x.strip() for x in m.group(1).split("; ")] if m else []


def pick_listed(outcome: str, text: str) -> str | None:
    """Which of the jobs just read out he means: "the first one", "yesterday's", "the
    Corolla". None unless exactly one fits."""
    items = _listed(outcome)
    if not items:
        return None
    o = _ORDINAL.search(text)
    if o:
        i = _ORDINAL_AT[o.group(1).lower()]
        return items[i] if -len(items) <= i < len(items) else None
    words = [w for w in re.findall(r"[a-z0-9-]+", text.lower().replace("'s", "")) if w not in _FILLER]
    if not words:
        return None
    fits = [x for x in items if all(_compact(w) in _compact(x) for w in words)]
    return fits[0] if len(fits) == 1 else None


_NO_PRICE = re.compile(r"I don't have a price for (.+?)\.", re.I)


def unpriced_draft(s: Session) -> tuple[Job, list[str]] | None:
    """The draft he's just been asked to price, and what's missing a price, while it's fresh."""
    turns = recent_turns(s, 2)
    draft = next((t for t in reversed(turns) if t.kind == "draft"), None)
    if not turns or not draft or not draft.job_id or draft.ready or not draft.described \
            or datetime.utcnow() - turns[-1].created_at > timedelta(minutes=ASK_MINUTES):
        return None
    missing = _NO_PRICE.findall(turns[-1].outcome)
    job = s.get(Job, draft.job_id)
    return (job, missing) if job and missing else None


def fill_price(s: Session, text: str) -> Job | None:
    """"25" or "filter was 30 bucks" after "what do you charge for the oil filter?": put his
    price (inc GST) on that line and leave everything else on the job as it is."""
    held = unpriced_draft(s)
    amounts = re.findall(r"\d+(?:\.\d{1,2})?", text)
    if not held or len(held[1]) != 1 or len(amounts) != 1 or len(text.split()) > 8 or held[0].stated_total_cents:
        return None
    job = held[0]
    unpriced = [l for l in s.exec(select(JobLine).where(JobLine.job_id == job.id)).all() if l.unit_cents == 0 and l.kind != LineKind.labour]
    if len(unpriced) != 1:
        return None
    line = unpriced[0]
    total = round(float(amounts[0]) * 100 / max(line.qty, 1))
    line.unit_cents = total - svc.gst_in(total)
    s.add(line)
    job.updated_at = datetime.utcnow()
    s.add(job)
    s.flush()
    return job


def waiting_on_yes(s: Session) -> dict[str, Any] | None:
    """A clean draft he was just asked to send, from the turns kept in the database."""
    last = recent_turns(s, 1)
    if last and last[-1].kind == "draft" and last[-1].ready and last[-1].job_id \
            and datetime.utcnow() - last[-1].created_at < timedelta(minutes=15):
        return {"action": "send", "job_id": last[-1].job_id}
    return None


def answer_text(s: Session, text: str) -> str | None:
    """"The CX-5" straight after "which car?": what he asked for in the first place, with his
    answer, so the request carries on instead of starting over. None when the app didn't
    just ask him something or this isn't an answer. (A draft that couldn't find the car is
    finished by amend_text; a ready draft's "Send it?" is answered by yes/no or a correction.)"""
    last = recent_turns(s, 1)
    if not last or last[-1].kind == "draft" or datetime.utcnow() - last[-1].created_at > timedelta(minutes=ASK_MINUTES):
        return None
    if not _ASKED.search(last[-1].outcome) or _NO_PRICE.search(last[-1].outcome) or not is_answer(s, text):
        return None
    # "the first one" after a list: the job itself, as it was read out
    # (by whose car it is: the work words would read as a new job to write up)
    picked = pick_listed(last[-1].outcome, text)
    return f"{last[-1].said.rstrip(' .?!')}: {picked.split(',')[0] if picked else text}"


def amend_text(s: Session, text: str) -> str | None:
    """"Make it 380 all up" or "add wipers to that" straight after a draft: his earlier
    description plus the change, so nothing he already said is lost when the job's lines
    are rewritten. None when it isn't a correction to the job he's on."""
    last = recent_turns(s, 1)
    # "rego's GLF222, customer Ben Hall" after "I couldn't find the Golf": the same job, now findable
    if last and last[-1].kind == "draft" and not last[-1].job_id and last[-1].described and (_FILLS_IN.search(text) or is_answer(s, text)) \
            and datetime.utcnow() - last[-1].created_at < timedelta(minutes=15):
        return f"{last[-1].described}\nThen he added: {text}"
    # a price for more than one unpriced line: say it all again with his prices
    if unpriced_draft(s) and re.search(r"\d", text) and len(text.split()) <= 12:
        draft = next(x for x in reversed(recent_turns(s, 2)) if x.kind == "draft")
        return f"{draft.described}\nThen he gave the price: {text}"
    # "45 for the pads" straight after the read-back: a new figure for the job on screen
    # (a whole new description naming the car again replaces it instead)
    new_figure = bool(re.search(r"\d", text)) and len(text.split()) <= 8 and not _NEW_ASK.search(text) \
        and not mentioned(s, text) and not knowhow.cars_in(text)
    if not (_AMEND.search(text) or new_figure):
        return None
    focus = focus_job(s)
    if not last or not focus or last[-1].kind != "draft" or last[-1].job_id != focus.id or not last[-1].described:
        return None
    others = [v for _, v in mentioned(s, text) if v and v.id != focus.vehicle_id]
    fv = s.get(Vehicle, focus.vehicle_id) if focus.vehicle_id else None
    other_cars = [c for c in knowhow.cars_in(text) if not fv or _compact(fv.model) not in _compact(c)]
    if others or other_cars or "waiting" in text.lower():
        return None
    return f"{last[-1].described}\nThen he corrected it: {text}"


# --- long term: the cars he mentions -------------------------------------------------------


def _compact(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def mentioned(s: Session, text: str, limit: int = 3) -> list[tuple[Customer, Vehicle | None]]:
    """Customers and cars he named, by rego (even spelled out), model or name."""
    words = set(re.findall(r"[a-z']+", (text or "").lower()))
    flat = _compact(text)
    heard_cars = {_compact(c.split(" ", 1)[-1]) for c in knowhow.cars_in(text)}  # "high lux" -> "hilux"
    hits: list[tuple[int, Customer, Vehicle | None]] = []
    for v in s.exec(select(Vehicle)).all():
        c = s.get(Customer, v.customer_id)
        if not c:
            continue
        score = 0
        if len(v.rego) >= 4 and _compact(v.rego) in flat:
            score = 10
        model = _compact(v.model)
        if len(model) >= 3 and (model in flat or model in heard_cars):
            score = max(score, 3)
        names = [n.lower().strip("'") for n in c.name.split() if len(n) > 2]
        if names and (names[0] in words or names[0] + "'s" in words):
            score += 2
        if score:
            hits.append((score, c, v))
    hits.sort(key=lambda h: -h[0])
    if hits and hits[0][0] >= 10:
        hits = [h for h in hits if h[0] >= 10]
    return [(c, v) for _, c, v in hits[:limit]]


def _lines_said(view: dict[str, Any]) -> str:
    gst = 1 + get_settings().gst_rate
    out = []
    for l in view["lines"]:
        amount = l["qty"] * l["unit_cents"] * gst
        what = l["description"]
        if l["kind"] == "labour" and l["qty"] != 1:
            what += f" {l['qty']:g} hrs"
        out.append(f"{what} {_dollars(int(round(amount)))}")
    return ", ".join(out) or "no items yet"


def _visit_day(s: Session, j: Job) -> str:
    inv = s.exec(select(Invoice).where(Invoice.job_id == j.id, Invoice.status != InvoiceStatus.void)).first()
    when = inv.issued_at if inv else j.updated_at
    return _local(when).strftime("%d %b %Y")


def car_story(s: Session, c: Customer, v: Vehicle | None, *, current_amounts: bool = True) -> str:
    """What the shop's records say about this customer and car, for the model to lean on.
    current_amounts=False leaves the open job's lines out (the extractor would copy them)."""
    car = f"{v.year or ''} {v.make} {v.model} {v.rego}".strip() if v else "car not on file"
    head = f"{c.name}, {car}" + (f", {v.odometer_km:,} km last time" if v and v.odometer_km else "")
    q = select(Job).where(Job.customer_id == c.id)
    if v:
        q = q.where(Job.vehicle_id == v.id)
    jobs = s.exec(q.order_by(Job.updated_at.desc())).all()  # type: ignore[attr-defined]
    lines = [head + "."]
    current = [j for j in jobs if j.status not in (JobStatus.invoiced, JobStatus.paid)]
    done = [j for j in jobs if j.status in (JobStatus.invoiced, JobStatus.paid)]
    bq = select(Booking).where(Booking.customer_id == c.id, Booking.day >= svc.today(), Booking.status.in_([BookingStatus.requested, BookingStatus.confirmed, BookingStatus.checked_in]))  # type: ignore[attr-defined]
    for b in s.exec(bq.order_by(Booking.day, Booking.start)).all()[:2]:
        days = (b.day - svc.today()).days
        day = "today" if days == 0 else "tomorrow" if days == 1 else b.day.strftime("%A %d %B")
        lines.append(f"  Booked in {day} at {b.start.strftime('%H:%M')}: {b.service} ({b.status.value.replace('_', ' ')}).")
    for j in current[:2]:
        view = svc.job_view(s, j)
        now = f"  In the shop now: job {j.id} '{j.title}', {j.status.value.replace('_', ' ')}"
        lines.append(now + (f"; {_lines_said(view)}; total {_dollars(view['total_cents'])} inc GST." if current_amounts else "."))
    for i, j in enumerate(done[:HISTORY_VISITS]):
        view = svc.job_view(s, j)
        paid = "paid" if j.status == JobStatus.paid else "invoiced, not paid yet"
        # newest first; naming the latest stops "same as last time" picking an older visit
        label = "LAST TIME (latest visit)" if i == 0 else "Earlier visit"
        lines.append(f"  {label} {_visit_day(s, j)}: job {j.id} '{j.title}': {_lines_said(view)}; total {_dollars(view['total_cents'])} inc GST ({paid}).")
    if len(done) >= 2:
        lines.append(f"  A regular: {len(done)} visits on file.")
    notes = [j.mechanic_notes.strip() for j in jobs if j.mechanic_notes and j.mechanic_notes.strip()]
    if notes:
        lines.append("  His notes: " + " | ".join(notes[:3]))
    facts = s.exec(select(OwnerFact).where(OwnerFact.customer_id == c.id).order_by(OwnerFact.id.desc())).all()  # type: ignore[attr-defined]
    if facts:
        lines.append("  He told you to remember: " + " | ".join(f.fact for f in facts[:4]))
    return "\n".join(lines)


def remember_fact(s: Session, about: str, fact: str) -> dict[str, Any]:
    hits = mentioned(s, about, limit=1)
    c, v = hits[0] if hits else (None, None)
    f = OwnerFact(fact=fact.strip(), customer_id=c.id if c else None, vehicle_id=v.id if v else None)
    s.add(f)
    s.flush()
    svc.log_event(s, "owner", "remembered", fact[:120], "customer" if c else None, c.id if c else None)
    return {"ok": True, "about": c.name if c else "the shop", "fact": f.fact}


def recall(s: Session, about: str) -> dict[str, Any]:
    hits = mentioned(s, about)
    shop = [f.fact for f in s.exec(select(OwnerFact).where(OwnerFact.customer_id == None).order_by(OwnerFact.id.desc())).all()[:5]]  # noqa: E711
    if not hits:
        return {"found": False, "shop_notes": shop}
    return {"found": True, "records": [car_story(s, c, v) for c, v in hits], "shop_notes": shop}


def route_context(s: Session) -> str:
    """Just the last exchange, for the quick intent router (a long prompt slows it and
    pulls it towards whatever the context talks about)."""
    last = recent_turns(s, 1)
    if not last:
        return ""
    t = last[-1]
    return f"Just before this he said \"{t.said[:160]}\" and you replied \"{t.outcome[:160]}\"."


_BACK = re.compile(r"\b(it|that|this|same|again|she|he|her|his|him|they|them|their|one)\b", re.I)


_WRAP = re.compile(r"\nThen he (?:added|corrected it|gave the price):", re.I)


def refers_back(text: str) -> bool:
    """"it", "that one", "same again": he means something already in the conversation.
    (Only his own words count, not the "Then he added:" joining a follow-up to them.)"""
    return bool(_BACK.search(_WRAP.sub("\n", text)))


def latest_car(s: Session, text: str) -> tuple[Customer, Vehicle | None] | None:
    """The car he named most recently: in "...\nThen he added: the Corolla", the Corolla."""
    for part in reversed(_WRAP.split(text)):
        found = mentioned(s, part, limit=1)
        if found:
            return found[0]
    return None


def names_a_car(s: Session, text: str) -> bool:
    """His words say which car or customer: a rego, a model or a name we know."""
    return bool(mentioned(s, text) or knowhow.cars_in(text) or re.search(r"\b(?!\d+w\d+\b)(?=[a-z]*\d)(?=\d*[a-z])[a-z0-9]{5,7}\b", text, re.I))


def ground_car(s: Session, ex: dict[str, Any], words: str) -> dict[str, Any]:
    """New work with no car in his words ("front pads, hour and a half, 350 all up") is not
    the job we talked about earlier unless he says "it" or "that one": drop the car the model
    took from memory so we ask which car instead of billing the wrong customer."""
    if not ex:
        return ex
    named = latest_car(s, words)
    if named and named[1]:
        # he said which car: that one, even if the model leaned on the job talked about before
        c, v = named
        rego = _compact(str(ex.get("rego") or ""))
        said_rego = bool(rego) and rego in _compact(_WRAP.split(words)[-1])  # a rego he said wins
        if not said_rego and _compact(v.rego) != rego:
            return {**ex, "car": f"{v.make} {v.model}", "rego": v.rego, "customer_name": c.name}
        return ex
    if names_a_car(s, words) or refers_back(words):
        return ex
    return {**ex, "car": "", "rego": "", "customer_name": ""}


# --- the block every owner-facing prompt gets ---------------------------------------------


def owner_context(s: Session, text: str, *, for_extract: bool = False) -> str:
    """for_extract: the version for turning his words into invoice lines. It carries his
    own words but not our read-backs or the open job's amounts, which the model would
    otherwise copy as if he had said them; past visits keep their amounts for
    "same as last time"."""
    today = svc.today()
    yday = today - timedelta(days=1)
    parts = [f"Today is {today.strftime('%A %d %B %Y')}; yesterday was {yday.strftime('%A %d %B')}."]

    turns = recent_turns(s)
    if turns:
        rows = []
        for t in turns:
            said = t.said if len(t.said) <= 160 else t.said[:157] + "..."
            got = t.outcome if len(t.outcome) <= 180 else t.outcome[:177] + "..."
            reply = "" if for_extract else f" -> you: \"{got}\""
            rows.append(f"- {_when(t.created_at)} he said \"{said}\"{reply}" + (f" (job {t.job_id})" if t.job_id else ""))
        parts.append("What he said to you lately, oldest first:\n" + "\n".join(rows))

    focus = focus_job(s)
    # for new work, the job he was on only matters if he points back at it
    if focus and not (for_extract and not refers_back(text)):
        view = svc.job_view(s, focus)
        parts.append(
            f"The job he is on now (what \"it\" or \"that one\" mean): job {focus.id}, {view['customer']}'s {view['vehicle']}, "
            f"{focus.status.value.replace('_', ' ')}"
            + ("." if for_extract else f"; {_lines_said(view)}; total {_dollars(view['total_cents'])} inc GST.")
        )

    cars = mentioned(s, text)
    pronoun = refers_back(text)
    if not cars and pronoun and turns:
        # "and what's he driving" right after "how does Jack usually pay"
        cars = mentioned(s, f"{turns[-1].said} {turns[-1].outcome}", limit=1)
    if focus and not cars and pronoun:
        c = s.get(Customer, focus.customer_id)
        v = s.get(Vehicle, focus.vehicle_id) if focus.vehicle_id else None
        if c:
            cars = [(c, v)]
    if cars:
        parts.append("Shop records for the customers and cars he mentioned:\n" + "\n".join(car_story(s, c, v, current_amounts=not for_extract) for c, v in cars))

    shop_notes = s.exec(select(OwnerFact).where(OwnerFact.customer_id == None).order_by(OwnerFact.id.desc())).all()[:5]  # noqa: E711
    if shop_notes:
        parts.append("Shop notes he asked you to keep: " + " | ".join(f.fact for f in shop_notes))

    kh = knowhow.knowhow_for(text)
    if kh:
        parts.append("Know-how that may help (typical, not prices):\n" + kh)

    parts.append(
        "How to use this: resolve \"it\", \"that one\", \"same again\" and half-said cars from the lines above. "
        "If he corrects or adds to the job he is on, repeat that job as he first described it (his earlier words above) with his change applied, so nothing he said before is lost. "
        "If he says \"same as last time\", use that visit's items and amounts exactly as listed. "
        "Amounts in your read-backs and the records are not things he said: never copy them into labour or total figures unless he asks for last time's job again. "
        "Otherwise prices come only from what he says now. Never invent a customer, car, rego or amount that is not in his words or these records."
    )
    return "\n\n".join(parts)
