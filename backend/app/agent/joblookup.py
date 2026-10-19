"""Finding the job he means when he asks about one ("yesterday's jobs", "the Hyundai
from Friday", "Priya's car", "what's not invoiced") and getting its invoice ready.

The search is plain code so it is fast and never makes things up. When nothing
matches, the answer says what was searched and offers the nearest jobs instead of
a flat "couldn't find it"."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
from typing import Any
from zoneinfo import ZoneInfo

from sqlmodel import Session, select

from .. import services as svc
from ..config import get_settings
from ..models import (
    Approval,
    ApprovalStatus,
    Booking,
    Invoice,
    InvoiceStatus,
    Job,
    JobLine,
    JobStatus,
)

# words that say nothing about which car he means
_STOP = {
    "the", "a", "an", "job", "jobs", "car", "cars", "one", "ones", "for", "from", "of", "on", "in", "s",
    "invoice", "invoices", "bill", "do", "make", "prepare", "get", "find", "me", "my", "his", "her",
    "their", "that", "this", "it", "yesterday", "today", "work", "done", "all", "any", "please",
}

# Which jobs a status word means. "to_invoice" is the useful one: work that's done
# (or still on the hoist) and has no invoice yet.
STATUS_GROUPS: dict[str, list[JobStatus]] = {
    "to_invoice": [JobStatus.done, JobStatus.in_progress, JobStatus.waiting_parts, JobStatus.approved],
    "open": [JobStatus.quoted, JobStatus.approved, JobStatus.in_progress, JobStatus.waiting_parts, JobStatus.done],
    "in_progress": [JobStatus.in_progress],
    "waiting_parts": [JobStatus.waiting_parts],
    "done": [JobStatus.done],
    "invoiced": [JobStatus.invoiced],
    "unpaid": [JobStatus.invoiced],
    "paid": [JobStatus.paid],
}


def job_day(s: Session, job: Job) -> date:
    """The day the work was on: its booking day, else the day the job was opened."""
    if job.booking_id:
        b = s.get(Booking, job.booking_id)
        if b:
            return b.day
    tz = ZoneInfo(get_settings().shop_timezone)
    return job.created_at.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz).date()


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower().replace("'s ", " ")) if w not in _STOP and len(w) > 1}


def _key(text: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (text or "").upper())


_DIGITS = {"zero": "0", "oh": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9"}


def spoken_key(text: str) -> str:
    """A rego as speech recognition writes it: "A B C one two three" -> "ABC123"."""
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return _key("".join(_DIGITS.get(w, w) for w in words))


def _close(a: str, b: str) -> bool:
    """Misheard model names: "carolla" ~ "corolla", "forrester" ~ "forester"."""
    if a == b:
        return True
    if len(a) < 4 or len(b) < 4:
        return False
    return SequenceMatcher(None, a, b).ratio() >= 0.8


def say_day(d: date) -> str:
    t = svc.today()
    if d == t:
        return "today"
    if d == t - timedelta(days=1):
        return "yesterday"
    if t - timedelta(days=6) <= d < t:
        return d.strftime("%A")
    return d.strftime("%A %-d %B")


def _match_score(s: Session, job: Job, hint: str) -> int:
    """How well his words fit this job: a rego is a sure thing, then name and car words."""
    v = svc.job_view(s, job)
    rk = _key(v["rego"])
    if rk and len(rk) >= 4 and (rk in _key(hint) or rk in spoken_key(hint)):
        return 100
    hw = _words(hint)
    if not hw:
        return 0
    have = _words(f"{v['vehicle']} {v['customer']} {job.title}")
    # "xtrail" for "X-Trail", "cx5" for "CX-5"
    have |= {_key(w).lower() for w in re.findall(r"[A-Za-z0-9]+-[A-Za-z0-9]+", v["vehicle"])}
    return sum(10 if w in have else 8 for w in hw if any(_close(w, h) for h in have))


def _view(s: Session, job: Job) -> dict[str, Any]:
    v = svc.job_view(s, job)
    d = job_day(s, job)
    inv = s.exec(select(Invoice).where(Invoice.job_id == job.id, Invoice.status != InvoiceStatus.void)).first()
    return {
        "job_id": job.id,
        "day": d.isoformat(),
        "when": say_day(d),
        "customer": v["customer"],
        "vehicle": v["vehicle"],
        "rego": v["rego"],
        "work": job.title,
        "status": job.status.value,
        "invoice": inv.number if inv else None,
        "invoice_status": inv.status.value if inv else None,
        "total_cents": v["total_cents"],
        "has_lines": bool(v["lines"]),
        # sent to whoever does the books and not approved yet
        "awaiting_approval": bool(s.exec(select(Approval).where(Approval.kind == "invoice", Approval.ref_id == job.id, Approval.status == ApprovalStatus.pending)).first()),
    }


def search_jobs(
    s: Session,
    *,
    when: str = "",
    car: str = "",
    customer: str = "",
    status: str = "",
) -> dict[str, Any]:
    """Jobs that fit what he said. Always returns what was searched; when nothing
    fits, `nearest` holds the closest jobs (same car any day, else the most recent)."""
    searched: list[str] = []
    day_from = day_to = None
    hint = " ".join(x for x in (customer, car) if x).strip()
    if hint:
        searched.append(hint)
    if when:
        try:
            day_from, day_to = svc.parse_period(when)
            if day_from == day_to:
                w = say_day(day_from)
                searched.append(w if w in ("today", "yesterday") else f"on {w}")
            else:
                searched.append(f"from {say_day(day_from)} to {say_day(day_to)}")
        except ValueError:
            searched.append(f"any day (I didn't catch '{when}')")
    group = STATUS_GROUPS.get((status or "").strip().lower())
    if group:
        searched.append({"to_invoice": "not invoiced yet", "unpaid": "still unpaid", "open": "still open"}.get(status, status.replace("_", " ")))
    jobs = s.exec(select(Job).order_by(Job.updated_at.desc())).all()  # type: ignore[attr-defined]
    scored: list[tuple[int, Job]] = []
    for j in jobs:
        if group and j.status not in group:
            continue
        if status == "unpaid":
            inv = s.exec(select(Invoice).where(Invoice.job_id == j.id, Invoice.status == InvoiceStatus.issued)).first()
            if not inv:
                continue
        if day_from and not (day_from <= job_day(s, j) <= day_to):  # type: ignore[operator]
            continue
        score = _match_score(s, j, hint) if hint else 1
        if hint and score == 0:
            continue
        scored.append((score, j))
    if scored:
        top = max(sc for sc, _ in scored)
        matches = [j for sc, j in scored if sc == top]
    else:
        matches = []
    out: dict[str, Any] = {"searched": " ".join(searched) or "any day", "jobs": [_view(s, j) for j in matches[:8]]}
    if not matches:
        near: list[Job] = []
        if hint:
            # the same car on another day, or in another state
            near = [j for j in jobs if _match_score(s, j, hint) > 0]
        if not near and day_from:
            # jobs close to the day he said
            near = sorted(jobs, key=lambda j: abs((job_day(s, j) - day_from).days))  # type: ignore[operator]
        if not near:
            near = list(jobs)
        out["nearest"] = [_view(s, j) for j in near[:3]]
    return out


def describe(j: dict[str, Any]) -> str:
    """One job, said the way he'd say it: "Dan's Nissan X-Trail, rear brake pads, yesterday"."""
    first = (j["customer"] or "someone").split()[0]
    car = " ".join(j["vehicle"].split()[:2]) or "car"
    state = {
        "invoiced": f"already invoiced{' (' + j['invoice'] + ')' if j.get('invoice') else ''}, not paid yet",
        "paid": "invoiced and paid",
        "done": "done, not invoiced yet",
        "in_progress": "still being worked on",
        "waiting_parts": "waiting on parts",
    }.get(j["status"], j["status"].replace("_", " "))
    if j.get("awaiting_approval") and j["status"] not in ("invoiced", "paid"):
        state = f"with {get_settings().approver_name} to approve"
    return f"{first}'s {car}, {j['work'].split(' - ')[0].lower()}, {j['when']}, {state}"


def spoken_list(found: dict[str, Any], intro: str = "") -> str:
    jobs = found["jobs"]
    if not jobs:
        near = found.get("nearest") or []
        text = f"I couldn't find a job for {found['searched']}."
        if near:
            text += " Closest I have: " + "; ".join(describe(j) for j in near) + "."
        return text
    if len(jobs) == 1 and not intro:
        return describe(jobs[0])[:1].upper() + describe(jobs[0])[1:] + "."
    where = found["searched"]
    if where == "any day":
        where = ""
    elif not where.startswith(("not invoiced", "still ")):
        where = f"for {where}"
    head = intro or (f"{len(jobs)} jobs" + (f" {where}" if where else "") + ":")
    # read out loud, so a long list stops at four
    more = f"; and {len(jobs) - 4} more" if len(jobs) > 5 else ""
    return head + " " + "; ".join(describe(j) for j in jobs[: 4 if more else 5]) + more + "."


def prepare_invoice(s: Session, job: Job) -> dict[str, Any]:
    """Get an existing job's invoice ready for him to send (his wife still approves).
    Returns {ok, job, readback, warnings}, shaped like a Talk-to-Invoice draft."""
    from .jobcard import readback

    view = svc.job_view(s, job)
    first = (view["customer"] or "the customer").split()[0]
    car = " ".join(view["vehicle"].split()[:2]) or "car"
    if job.status == JobStatus.paid:
        return {"ok": False, "job": view, "readback": f"{first}'s {car} is already invoiced ({view['invoice_number']}) and paid.", "warnings": []}
    if job.status == JobStatus.invoiced:
        return {"ok": False, "job": view, "readback": f"{first}'s {car} is already invoiced ({view['invoice_number']}), waiting on payment. Say 'paid on EFTPOS' when they pay.", "warnings": []}
    has_lines = bool(s.exec(select(JobLine).where(JobLine.job_id == job.id)).first())
    if not has_lines:
        return {"ok": False, "job": view, "readback": f"I've got {first}'s {car} but nothing on it yet. Tell me what you did and what to charge.", "warnings": []}
    if job.status != JobStatus.done:
        job.status = JobStatus.done
        job.updated_at = datetime.utcnow()
        s.flush()
        view = svc.job_view(s, job)
    return {"ok": True, "job": view, "readback": readback(view, []), "warnings": []}
