"""The owner app's memory: what he said earlier and what the shop knows about the
cars he mentions, put in front of the model every time he talks.

Two layers:
  short term  every turn (what he said, what we did, which job) in OwnerTurn, so
              "send it", "that one", "make it 380 all up" or "the CX-5 I did this
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
    Channel,
    Conversation,
    Customer,
    Invoice,
    InvoiceStatus,
    Job,
    JobStatus,
    Message,
    OwnerFact,
    OwnerTurn,
    Vehicle,
)
from . import knowhow

RECENT_TURNS = 10
RECENT_DAYS = 3
FOCUS_HOURS = 12  # "send it" refers to a job he talked about since this morning, not last week
HISTORY_VISITS = 3

# Short confirmations after "Send it?": the whole utterance, nothing more.
_SEND_IT = re.compile(
    r"^(?:(?:yes|yep|yeah|yup|ok|okay|sure|righto|sweet|perfect|correct|that's right|thats right|all good)[\s,.!]*)*"
    r"(?:(?:please\s+)?(?:send(?: it| that| that one| it off| it through| it to her| it to (?:the )?(?:wife|missus))?|go ahead|do it|go for it|approve it)[\s,.!]*(?:please|mate|thanks)?[\s,.!]*)?$",
    re.IGNORECASE,
)


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


def owner_conversation(s: Session) -> Conversation:
    """One back-office transcript per day, so yesterday's "the Corolla is done" never
    reads as today's. Earlier days reach the model through owner_context instead."""
    from .frontdesk import get_or_create_conversation

    conv = get_or_create_conversation(s, Channel.owner, f"owner-{svc.today().isoformat()}")
    conv.updated_at = datetime.utcnow()
    return conv


def _job_from(out: dict[str, Any]) -> int | None:
    job = out.get("job") or {}
    if job.get("job_id"):
        return int(job["job_id"])
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
    """Record what he said and what came of it. Drafts also go into today's back-office
    transcript, so a later "mark it paid" or "what did I just do" has them in view."""
    job_id = _job_from(out)
    job = s.get(Job, job_id) if job_id else None
    outcome = str(out.get("readback") or "")
    kind = str(out.get("kind") or "reply")
    ready = kind == "draft" and bool(out.get("ok")) and not out.get("warnings")
    t = OwnerTurn(said=said, kind=kind, outcome=outcome[:600], ready=ready, job_id=job.id if job else None, customer_id=job.customer_id if job else None)
    s.add(t)
    if t.kind != "reply":
        conv = owner_conversation(s)
        note = f" [job {job.id}]" if job else ""
        s.add(Message(conversation_id=conv.id, role="user", content=said))
        s.add(Message(conversation_id=conv.id, role="assistant", content=outcome + note))
    s.flush()
    return t


def recent_turns(s: Session, limit: int = RECENT_TURNS) -> list[OwnerTurn]:
    since = datetime.utcnow() - timedelta(days=RECENT_DAYS)
    rows = s.exec(select(OwnerTurn).where(OwnerTurn.created_at >= since).order_by(OwnerTurn.id.desc()).limit(limit)).all()  # type: ignore[attr-defined]
    return list(reversed(rows))


def focus_job(s: Session) -> Job | None:
    """The job he's been talking about most recently: what "it" and "that one" mean."""
    since = datetime.utcnow() - timedelta(hours=FOCUS_HOURS)
    t = s.exec(select(OwnerTurn).where(OwnerTurn.created_at >= since, OwnerTurn.job_id != None).order_by(OwnerTurn.id.desc())).first()  # type: ignore[attr-defined]  # noqa: E711
    return s.get(Job, t.job_id) if t and t.job_id else None


def is_send_it(text: str) -> bool:
    t = text.strip()
    return bool(t) and len(t) < 60 and bool(_SEND_IT.match(t)) and bool(re.search(r"[a-z]", t, re.I))


def follow_up(s: Session, text: str) -> dict[str, Any] | None:
    """Handle "yep, send it" straight after a draft read-back without another model call.
    Only when the job he's on is a finished draft with lines that hasn't gone yet."""
    if not is_send_it(text):
        return None
    job = focus_job(s)
    last = recent_turns(s, 1)
    if not job or not last or last[-1].job_id != job.id or not last[-1].ready:
        return None
    view = svc.job_view(s, job)
    if job.status != JobStatus.done or not view["lines"]:
        return None
    r = svc.request_invoice_approval(s, job)
    first = (view["customer"] or "the customer").split()[0]
    who = get_settings().approver_name or "the books"
    if r.get("status") == "awaiting_approval":
        say = f"Sent {first}'s invoice to {who} to approve."
    elif r.get("status") == "sent":
        say = f"Invoice sent to {first}."
    else:
        say = f"{first}'s invoice has already gone."
    return {"kind": "follow_up", "ok": True, "readback": say, "job": svc.job_view(s, job), "send": r, "model": "memory"}


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


def car_story(s: Session, c: Customer, v: Vehicle | None) -> str:
    """What the shop's records say about this customer and car, for the model to lean on."""
    car = f"{v.year or ''} {v.make} {v.model} {v.rego}".strip() if v else "car not on file"
    head = f"{c.name}, {car}" + (f", {v.odometer_km:,} km last time" if v and v.odometer_km else "")
    q = select(Job).where(Job.customer_id == c.id)
    if v:
        q = q.where(Job.vehicle_id == v.id)
    jobs = s.exec(q.order_by(Job.updated_at.desc())).all()  # type: ignore[attr-defined]
    lines = [head + "."]
    current = [j for j in jobs if j.status not in (JobStatus.invoiced, JobStatus.paid)]
    done = [j for j in jobs if j.status in (JobStatus.invoiced, JobStatus.paid)]
    for j in current[:2]:
        view = svc.job_view(s, j)
        lines.append(f"  In the shop now: job {j.id} '{j.title}', {j.status.value.replace('_', ' ')}; {_lines_said(view)}; total {_dollars(view['total_cents'])} inc GST.")
    for j in done[:HISTORY_VISITS]:
        view = svc.job_view(s, j)
        paid = "paid" if j.status == JobStatus.paid else "invoiced, not paid yet"
        lines.append(f"  Visit {_visit_day(s, j)}: job {j.id} '{j.title}': {_lines_said(view)}; total {_dollars(view['total_cents'])} inc GST ({paid}).")
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


# --- the block every owner-facing prompt gets ---------------------------------------------


def owner_context(s: Session, text: str) -> str:
    today = svc.today()
    yday = today - timedelta(days=1)
    parts = [f"Today is {today.strftime('%A %d %B %Y')}; yesterday was {yday.strftime('%A %d %B')}."]

    turns = recent_turns(s)
    if turns:
        rows = []
        for t in turns:
            said = t.said if len(t.said) <= 160 else t.said[:157] + "..."
            got = t.outcome if len(t.outcome) <= 180 else t.outcome[:177] + "..."
            rows.append(f"- {_when(t.created_at)} he said \"{said}\" -> you: \"{got}\"" + (f" (job {t.job_id})" if t.job_id else ""))
        parts.append("What he said to you lately, oldest first:\n" + "\n".join(rows))

    focus = focus_job(s)
    if focus:
        view = svc.job_view(s, focus)
        parts.append(
            f"The job he is on now (what \"it\", \"that one\" or \"send it\" mean): job {focus.id}, {view['customer']}'s {view['vehicle']}, "
            f"{focus.status.value.replace('_', ' ')}; {_lines_said(view)}; total {_dollars(view['total_cents'])} inc GST."
        )

    cars = mentioned(s, text)
    if focus and not cars and re.search(r"\b(it|that|this|same|again|her|his|him|them|one)\b", text, re.I):
        c = s.get(Customer, focus.customer_id)
        v = s.get(Vehicle, focus.vehicle_id) if focus.vehicle_id else None
        if c:
            cars = [(c, v)]
    if cars:
        parts.append("Shop records for the customers and cars he mentioned:\n" + "\n".join(car_story(s, c, v) for c, v in cars))

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
        "Otherwise prices come only from what he says now. Never invent a customer, car, rego or amount that is not in his words or these records."
    )
    return "\n\n".join(parts)
