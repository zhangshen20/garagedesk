"""Talk-to-Invoice: turn what the owner says (or a photo of his paper job card) into
a priced job card ready to invoice.

The owner can't type. He holds a button and says "Corolla ABC123 done, front pads,
machined the rotors, hour and a half", or photographs the card he already wrote.
  photo -> vision model transcribes the handwriting
  words -> Nemotron Super pulls out the car and line items as JSON
  code  -> finds the job, prices parts from the catalogue and labour from the
           shop's rate, and writes the lines. No prices are invented by the model.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlmodel import Session, select

from .. import services as svc
from ..config import get_settings
from ..llm import get_llm
from ..models import Booking, BookingStatus, Job, JobLine, JobStatus, LineKind, Part

EXTRACT_PROMPT = """You turn a mechanic's spoken or handwritten job notes into a job card. The notes are in Australian workshop slang and may come from speech recognition, so expect odd spelling ("break pads" = brake pads, "five W thirty" = 5W-30, "hour and a half" = 1.5 hours).
Reply with JSON only:
{"car": "words that identify the car or customer, e.g. 'Corolla ABC123' or 'Maria's Corolla'",
 "rego": "registration plate if said, letters and digits only, else empty",
 "customer_name": "customer name if said, else empty",
 "labour_hours": number or null,
 "labour_description": "short description of the work done, e.g. 'Replace front pads, machine rotors'",
 "parts": [{"name": "part name as a parts shop would write it", "qty": number, "price_dollars": number or null}],
 "fees": [{"name": "...", "price_dollars": number}],
 "paid_method": "eftpos" | "cash" | "transfer" | "" ,
 "notes": "anything else worth keeping, e.g. 'rear pads 30%, tell customer next time'"}
Rules: only include prices the notes actually state; never guess a price. Prices said by the mechanic are what the customer pays including GST unless he says "plus GST". Work items without a part (machining, inspection, top-ups) belong in labour_description, not parts. qty counts items as a parts shop sells them: "both wiper blades" is one pair, "oil and filter" is one oil and one filter."""

VISION_PROMPT = "Transcribe this handwritten mechanic's job card exactly as written, line by line. Keep numbers, prices and the registration plate exactly. Plain text only."


@dataclass
class Draft:
    ok: bool
    job: dict[str, Any] | None = None
    readback: str = ""
    warnings: list[str] = field(default_factory=list)
    transcript: str = ""
    extracted: dict[str, Any] = field(default_factory=dict)
    paid_method: str = ""
    model: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "job": self.job,
            "readback": self.readback,
            "warnings": self.warnings,
            "transcript": self.transcript,
            "extracted": self.extracted,
            "paid_method": self.paid_method,
            "model": self.model,
        }


def transcribe_photo(image_b64: str, mime: str = "image/jpeg") -> tuple[str, str]:
    """Read a photo of a paper job card. Returns (text, model)."""
    llm = get_llm()
    r = llm.vision(VISION_PROMPT, image_b64, mime=mime)
    return (r.content or "").strip(), r.model


def extract(text: str) -> tuple[dict[str, Any], str]:
    llm = get_llm()
    r = llm.chat(
        [{"role": "system", "content": EXTRACT_PROMPT}, {"role": "user", "content": text}],
        tier="main",
        json_mode=True,
        max_tokens=2000,
        temperature=0,
    )
    return _parse_json(r.content or ""), r.model


def _parse_json(s: str) -> dict[str, Any]:
    s = s.strip()
    m = re.search(r"\{.*\}", s, flags=re.DOTALL)
    if m:
        s = m.group(0)
    try:
        v = json.loads(s)
        return v if isinstance(v, dict) else {}
    except json.JSONDecodeError:
        return {}


# --- matching the car to a job ---------------------------------------------------------

_OPEN = [JobStatus.quoted, JobStatus.approved, JobStatus.in_progress, JobStatus.waiting_parts, JobStatus.done]


def _words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (s or "").lower()) if len(w) > 1}


def _rego_key(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def match_open_job(s: Session, hint: str, rego: str = "", statuses: list[JobStatus] | None = None) -> Job | None:
    """Find the job the owner means from loose words: rego, make, model or customer name."""
    statuses = statuses or _OPEN
    jobs = s.exec(select(Job).where(Job.status.in_(statuses)).order_by(Job.updated_at.desc())).all()  # type: ignore[attr-defined]
    rk = _rego_key(rego)
    hint_words = _words(hint) | _words(rego)
    best, best_score = None, 0
    for j in jobs:
        v = svc.job_view(s, j)
        if rk and _rego_key(v["rego"]) == rk:
            return j
        hay = _words(f"{v['vehicle']} {v['customer']} {j.title}")
        # a rego said with a space ("ABC 123") arrives as two words
        if v["rego"] and _rego_key(v["rego"]) in _rego_key(hint):
            return j
        score = len(hint_words & hay)
        if score > best_score:
            best, best_score = j, score
    return best


def _job_from_todays_booking(s: Session, hint: str, rego: str) -> Job | None:
    """A car booked in today with no job card yet: open one."""
    bookings = s.exec(select(Booking).where(Booking.day == svc.today(), Booking.status.in_([BookingStatus.confirmed, BookingStatus.checked_in, BookingStatus.requested]))).all()  # type: ignore[attr-defined]
    rk, hint_words = _rego_key(rego), _words(hint) | _words(rego)
    best, best_score = None, 0
    for b in bookings:
        if s.exec(select(Job).where(Job.booking_id == b.id)).first():
            continue
        v = svc.booking_view(s, b)
        plate = v["vehicle"].split()[-1] if v["vehicle"] else ""
        if rk and _rego_key(plate) == rk:
            best = b
            break
        score = len(hint_words & _words(f"{v['vehicle']} {v['customer']}"))
        if score > best_score:
            best, best_score = b, score
    if not best:
        return None
    best.status = BookingStatus.checked_in
    j = Job(booking_id=best.id, customer_id=best.customer_id, vehicle_id=best.vehicle_id, title=best.service, status=JobStatus.in_progress)
    s.add(j)
    s.flush()
    svc.log_event(s, "owner", "job_opened", f"from booking {svc.booking_reference(best)}", "job", j.id)
    return j


def find_or_open_job(s: Session, ex: dict[str, Any]) -> Job | None:
    hint = " ".join(str(ex.get(k) or "") for k in ("car", "customer_name"))
    rego = str(ex.get("rego") or "")
    job = match_open_job(s, hint, rego)
    if job:
        return job
    job = _job_from_todays_booking(s, hint, rego)
    if job:
        return job
    if rego and ex.get("customer_name"):
        # a walk-in nobody booked: new customer, car and job
        c, v = svc.find_or_create_customer(s, name=str(ex["customer_name"]), phone="", rego=rego, vehicle=str(ex.get("car") or ""))
        j = Job(customer_id=c.id, vehicle_id=v.id if v else None, title=str(ex.get("labour_description") or "Workshop job"), status=JobStatus.in_progress)
        s.add(j)
        s.flush()
        svc.log_event(s, "owner", "job_opened", f"walk-in {c.name} {rego}", "job", j.id)
        return j
    return None


# --- pricing ---------------------------------------------------------------------------


def match_part(s: Session, name: str, vehicle: str = "") -> Part | None:
    want = _words(name)
    if not want:
        return None
    want |= {w.rstrip("s") for w in want}
    car = _words(vehicle)
    best, best_score = None, 0.0
    for p in s.exec(select(Part)).all():
        have = _words(p.name)
        have |= {w.rstrip("s") for w in have}
        overlap = len(want & have)
        # one shared word ("front") is not a match, unless the owner said one word
        if overlap < min(2, len(_words(name))):
            continue
        # prefer the part for this car, and an exact-ish name over a loose one
        score = overlap + 0.5 * len(car & have) - 0.01 * len(have)
        if score > best_score:
            best, best_score = p, score
    return best


def _ex_gst(dollars: float) -> int:
    return int(round(dollars * 100 / (1 + get_settings().gst_rate)))


def apply_to_job(s: Session, job: Job, ex: dict[str, Any]) -> list[str]:
    """Replace the job's lines with what the owner described. Returns warnings to read back."""
    warnings: list[str] = []
    settings = get_settings()
    v = svc.job_view(s, job)
    for line in s.exec(select(JobLine).where(JobLine.job_id == job.id)).all():
        s.delete(line)
    s.flush()

    hours = ex.get("labour_hours")
    desc = str(ex.get("labour_description") or job.title or "Labour").strip()
    if hours:
        s.add(JobLine(job_id=job.id, kind=LineKind.labour, description=desc[:1].upper() + desc[1:], qty=float(hours), unit_cents=settings.labour_rate_cents))
    else:
        warnings.append("I didn't hear the labour time.")

    for p in ex.get("parts") or []:
        name = str(p.get("name") or "").strip()
        if not name:
            continue
        qty = float(p.get("qty") or 1)
        price = p.get("price_dollars")
        part = match_part(s, name, v["vehicle"])
        if price not in (None, ""):
            unit = _ex_gst(float(price) / qty) if qty else _ex_gst(float(price))
            s.add(JobLine(job_id=job.id, kind=LineKind.part, description=part.name if part else name, qty=qty, unit_cents=unit, part_id=part.id if part else None))
        elif part:
            s.add(JobLine(job_id=job.id, kind=LineKind.part, description=part.name, qty=qty, unit_cents=part.sell_cents, part_id=part.id))
        else:
            s.add(JobLine(job_id=job.id, kind=LineKind.part, description=name, qty=qty, unit_cents=0))
            warnings.append(f"I don't have a price for {name}.")

    for f in ex.get("fees") or []:
        if f.get("name") and f.get("price_dollars") not in (None, ""):
            s.add(JobLine(job_id=job.id, kind=LineKind.fee, description=str(f["name"]), qty=1, unit_cents=_ex_gst(float(f["price_dollars"]))))

    if ex.get("notes"):
        job.mechanic_notes = ((job.mechanic_notes or "") + "\n" + str(ex["notes"])).strip()
    job.status = JobStatus.done
    job.updated_at = datetime.utcnow()
    s.flush()
    svc.log_event(s, "owner", "job_card_spoken", f"job {job.id}: {desc}", "job", job.id)
    return warnings


def readback(view: dict[str, Any], warnings: list[str]) -> str:
    first = (view["customer"] or "the customer").split()[0]
    car = " ".join(view["vehicle"].split()[:2]) or "car"
    items = []
    for l in view["lines"]:
        if l["kind"] == "labour":
            h = l["qty"]
            items.append(f"{h:g} hour{'s' if h != 1 else ''} labour")
        else:
            items.append(l["description"].split(" - ")[0].lower())
    listed = ", ".join(items[:-1]) + (" and " if len(items) > 1 else "") + items[-1] if items else "no items"
    total = view["total_cents"] / 100
    text = f"Invoice for {first}'s {car}: {listed}. {total:,.2f} dollars including GST."
    if warnings:
        text += " " + " ".join(warnings) + " Say it again with that and I'll fix it."
    else:
        text += " Send it?"
    return text


def draft_from_text(s: Session, text: str, transcript_model: str = "") -> Draft:
    ex, model = extract(text)
    if not ex:
        return Draft(ok=False, readback="Sorry, I didn't get that. Try again: say the car, what you did, and how long it took.", transcript=text, model=model)
    job = find_or_open_job(s, ex)
    if not job:
        car = ex.get("car") or "that car"
        return Draft(ok=False, readback=f"I couldn't find {car} in today's jobs. Say the rego and the customer's name.", transcript=text, extracted=ex, model=model)
    if job.status in (JobStatus.invoiced, JobStatus.paid):
        return Draft(ok=False, readback="That job is already invoiced.", transcript=text, extracted=ex, model=model)
    warnings = apply_to_job(s, job, ex)
    view = svc.job_view(s, job)
    paid = str(ex.get("paid_method") or "").lower()
    return Draft(
        ok=True,
        job=view,
        readback=readback(view, warnings),
        warnings=warnings,
        transcript=text,
        extracted=ex,
        paid_method=paid if paid in ("eftpos", "cash", "transfer") else "",
        model=" + ".join(m for m in (transcript_model, model) if m),
    )
