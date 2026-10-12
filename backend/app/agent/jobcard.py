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

EXTRACT_PROMPT = """You turn what a mechanic says about a finished job into a job card, the way he would tell his wife over the phone so she can make the tax invoice. The notes are in Australian workshop slang and may come from speech recognition, so expect odd spelling ("break pads" = brake pads, "five W thirty" = 5W-30, "hour and a half" = 1.5 hours).
Reply with JSON only:
{"car": "words that identify the car or customer, e.g. 'Corolla ABC123' or 'Maria's Corolla'",
 "rego": "registration plate if said, letters and digits only, else empty",
 "customer_name": "customer name if said, else empty",
 "labour_hours": number or null,
 "labour_description": "short description of the work done, e.g. 'Replace front pads, machine rotors'",
 "labour_dollars": number or null,
 "total_dollars": number or null,
 "parts": [{"name": "part name as a parts shop would write it", "qty": number, "price_dollars": number or null}],
 "fees": [{"name": "...", "price_dollars": number}],
 "paid_method": "eftpos" | "cash" | "transfer" | "" ,
 "notes": "anything else worth keeping, e.g. 'rear pads 30%, tell customer next time'"}
He works the money out on a calculator and says it: per item ("pads 120"), for labour ("labour 180"), or for the whole job ("350 all up", "charge her 350"). Put each figure exactly where he said it: item prices in parts[].price_dollars, a labour amount in labour_dollars, a whole-job amount in total_dollars.
Rules: only include prices he actually states; never guess a price. Prices said by the mechanic are what the customer pays including GST unless he says "plus GST". Work items without a part (machining, inspection, top-ups) belong in labour_description, not parts. A part he names is a parts item even when it is also the job: "front pads" is labour "Replace front pads" plus the part "Brake pads front"; "did the battery" is labour plus the part "Battery". qty counts items as a parts shop sells them: "both wiper blades" is one pair, "oil and filter" is one oil and one filter."""

RECEIPT_VISION_PROMPT = "Transcribe this supplier receipt or parts invoice exactly, line by line: supplier name, each item with quantity and price, GST and the total. Plain text only."

RECEIPT_PROMPT = """You read a car parts supplier receipt (already transcribed to text) for a mechanic shop.
Reply with JSON only:
{"supplier": "supplier name or empty",
 "parts": [{"name": "item as written, tidied", "qty": number, "line_total_dollars": number}],
 "total_dollars": number or null,
 "gst_dollars": number or null}
Rules: copy prices exactly as printed; line_total_dollars is what that line costs including GST; skip freight, rounding and payment lines."""

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


def extract(text: str, context: str = "") -> tuple[dict[str, Any], str]:
    """context: what the agent remembers (memory.owner_context), so "same again for
    the Corolla" or "make it 380" can be filled in from earlier turns and records."""
    llm = get_llm()
    system = EXTRACT_PROMPT + (f"\n\nContext:\n{context}" if context else "")
    r = llm.chat(
        [{"role": "system", "content": system}, {"role": "user", "content": text}],
        tier="main",
        json_mode=True,
        max_tokens=2000,
        temperature=0,
        think=False,
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
    # a rego that matches nothing is a different car: never guess from a shared name or model
    return None if rk else best


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
        if rk:
            continue
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


def _vehicle_words(car: str, name: str, rego: str) -> str:
    """'Ben Lee's Toyota Hilux BEN001' -> 'Toyota Hilux'."""
    drop = _words(name) | {rego.lower(), "rego", "walk", "in", "the", "his", "her", "new", "customer"}
    words = [w for w in re.findall(r"[A-Za-z0-9-]+", car.replace("'s", "")) if w.lower() not in drop and _rego_key(w) != _rego_key(rego)]
    return " ".join(words)


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
        c, v = svc.find_or_create_customer(s, name=str(ex["customer_name"]), phone="", rego=rego, vehicle=_vehicle_words(str(ex.get("car") or ""), str(ex["customer_name"]), rego))
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
        # a part catalogued for another car ("... - Toyota Corolla" on a Mazda) doesn't fit
        fits_for = _words(p.name.split(" - ", 1)[1]) if " - " in p.name else set()
        if fits_for and car and not (fits_for & car):
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

    hours = _num(ex.get("labour_hours"))
    labour_dollars = _num(ex.get("labour_dollars"))
    total_dollars = _num(ex.get("total_dollars"))
    desc = str(ex.get("labour_description") or job.title or "Labour").strip()
    desc = desc[:1].upper() + desc[1:]
    labour: JobLine | None = None
    if labour_dollars is not None:
        # his figure for the labour, whatever the hours
        labour = JobLine(job_id=job.id, kind=LineKind.labour, description=desc + (f" ({hours:g} hrs)" if hours else ""), qty=1, unit_cents=_ex_gst(labour_dollars))
    elif hours:
        labour = JobLine(job_id=job.id, kind=LineKind.labour, description=desc, qty=hours, unit_cents=settings.labour_rate_cents)
    elif total_dollars is None:
        warnings.append("I didn't hear the labour time.")
    if labour:
        s.add(labour)

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

    s.flush()
    if total_dollars is not None:
        warnings += _hit_total(s, job, labour, desc, hours, total_dollars, labour_fixed=labour_dollars is not None)

    if ex.get("notes"):
        job.mechanic_notes = ((job.mechanic_notes or "") + "\n" + str(ex["notes"])).strip()
    job.status = JobStatus.done
    job.updated_at = datetime.utcnow()
    s.flush()
    svc.log_event(s, "owner", "job_card_spoken", f"job {job.id}: {desc}", "job", job.id)
    return warnings


def _num(v: Any) -> float | None:
    try:
        return None if v in (None, "") else float(v)
    except (TypeError, ValueError):
        return None


def _subtotal_for(total_cents: int) -> int:
    """Ex-GST subtotal whose GST-inclusive total comes out to exactly total_cents."""
    rate = get_settings().gst_rate
    base = int(round(total_cents / (1 + rate)))
    for sub in (base, base - 1, base + 1):
        if sub + svc.gst_on(sub) == total_cents:
            return sub
    return base


def _hit_total(s: Session, job: Job, labour: JobLine | None, desc: str, hours: float | None, total_dollars: float, *, labour_fixed: bool) -> list[str]:
    """He said what the whole job costs. Make the invoice add up to exactly that: the
    labour line takes the balance after the parts, as his wife would have done."""
    target = _subtotal_for(int(round(total_dollars * 100)))
    lines = s.exec(select(JobLine).where(JobLine.job_id == job.id)).all()
    others = sum(int(round(l.qty * l.unit_cents)) for l in lines if l is not labour)
    if labour_fixed:
        current = sum(int(round(l.qty * l.unit_cents)) for l in lines)
        if current == target:
            return []
        return [f"Your items add up to {(current * 1.1) / 100:,.2f}, not {total_dollars:,.2f}."]
    balance = target - others
    if balance < 0:
        return [f"The parts alone come to more than {total_dollars:,.2f}."]
    if labour is None:
        labour = JobLine(job_id=job.id, kind=LineKind.labour, description=desc, qty=1, unit_cents=0)
        s.add(labour)
    labour.qty = 1
    labour.unit_cents = balance
    labour.description = desc + (f" ({hours:g} hrs)" if hours else "")
    s.flush()
    return []


def readback(view: dict[str, Any], warnings: list[str]) -> str:
    first = (view["customer"] or "the customer").split()[0]
    car = " ".join(view["vehicle"].split()[:2]) or "car"
    gst = 1 + get_settings().gst_rate
    items = []
    for l in view["lines"]:
        amount = l["qty"] * l["unit_cents"] * gst / 100
        if l["kind"] == "labour":
            h = l["qty"]
            what = "labour" if h == 1 else f"{h:g} hours labour"
        else:
            what = l["description"].split(" - ")[0].lower()
        items.append(f"{what} {amount:,.2f}" if l["unit_cents"] else what)
    listed = ", ".join(items[:-1]) + (" and " if len(items) > 1 else "") + items[-1] if items else "no items"
    total = view["total_cents"] / 100
    text = f"Invoice for {first}'s {car}: {listed}. {total:,.2f} dollars including GST."
    if warnings:
        text += " " + " ".join(warnings) + " Say it again with that and I'll fix it."
    else:
        text += " Send it?"
    return text


def add_receipt(s: Session, job: Job, image_b64: str, mime: str = "image/jpeg") -> Draft:
    """He photographs the parts receipt that came with the delivery. The parts go on
    the customer's job (at cost plus the shop's markup) and the receipt goes in the
    books as an expense with its GST."""
    llm = get_llm()
    seen = llm.vision(RECEIPT_VISION_PROMPT, image_b64, mime=mime)
    text = (seen.content or "").strip()
    r = llm.chat([{"role": "system", "content": RECEIPT_PROMPT}, {"role": "user", "content": text}], tier="main", json_mode=True, max_tokens=1500, temperature=0)
    rc = _parse_json(r.content or "")
    model = " + ".join(m for m in (seen.model, r.model) if m)
    parts = [p for p in rc.get("parts") or [] if p.get("name") and _num(p.get("line_total_dollars"))]
    if not parts:
        return Draft(ok=False, readback="I couldn't read any parts on that receipt. Try again with the whole receipt in view.", transcript=text, model=model)
    markup = 1 + get_settings().parts_markup_percent / 100
    for p in parts:
        qty = _num(p.get("qty")) or 1
        line_inc = float(p["line_total_dollars"])
        s.add(JobLine(job_id=job.id, kind=LineKind.part, description=str(p["name"]), qty=qty, unit_cents=_ex_gst(line_inc * markup / qty)))
    total = _num(rc.get("total_dollars")) or sum(float(p["line_total_dollars"]) for p in parts)
    gst = _num(rc.get("gst_dollars"))
    from ..models import Expense

    supplier = svc.find_supplier(s, str(rc.get("supplier") or ""))
    s.add(Expense(day=svc.today(), description=f"Parts for job {job.id}" + (f" from {rc.get('supplier')}" if rc.get("supplier") else ""), amount_cents=int(round(total * 100)), gst_cents=int(round(gst * 100)) if gst is not None else int(round(total * 100 - total * 100 / (1 + get_settings().gst_rate))), category="parts", supplier_id=supplier.id if supplier else None))
    job.updated_at = datetime.utcnow()
    s.flush()
    svc.log_event(s, "owner", "receipt_added", f"job {job.id}: {len(parts)} parts from receipt", "job", job.id)
    view = svc.job_view(s, job)
    names = ", ".join(str(p["name"]).lower() for p in parts[:3])
    return Draft(ok=True, job=view, readback=f"Added {names} from the receipt. New total {view['total_cents'] / 100:,.2f} dollars including GST. Send it?", transcript=text, model=model)


def draft_from_text(s: Session, text: str, transcript_model: str = "", context: str = "") -> Draft:
    ex, model = extract(text, context)
    return draft_from_extracted(s, ex, text, " + ".join(m for m in (transcript_model, model) if m))


def _has_work(ex: dict[str, Any]) -> bool:
    return any(_num(ex.get(k)) for k in ("labour_hours", "labour_dollars", "total_dollars")) or bool(ex.get("parts")) or bool(ex.get("fees"))


def _not_found(s: Session, ex: dict[str, Any]) -> str:
    """Say what we looked for and offer the nearest jobs, never a flat "not found"."""
    from .joblookup import describe, search_jobs

    car = " ".join(str(ex.get(k) or "") for k in ("car", "rego")).strip()
    found = search_jobs(s, car=car, customer=str(ex.get("customer_name") or ""), status="open")
    near = [j for j in found.get("nearest", []) if j["status"] not in ("invoiced", "paid")]
    what = car or str(ex.get("customer_name") or "") or "which car it was"
    text = f"I couldn't match {what} to a job or a booking."
    if near:
        text += " Open jobs: " + "; ".join(describe(j) for j in near) + "."
    return text + " Say the rego, or the customer's name and the car, and I'll open it."


def draft_from_extracted(s: Session, ex: dict[str, Any], transcript: str = "", model: str = "") -> Draft:
    """Find the job, price it and build the read-back from an already extracted dict.
    Other readers (the hardened photo reader, booking prefill) enter here."""
    if not ex:
        return Draft(ok=False, readback="Sorry, I didn't get that. Try again: say the car, what you did, and how long it took.", transcript=transcript, model=model)
    job = find_or_open_job(s, ex)
    if not job:
        return Draft(ok=False, readback=_not_found(s, ex), transcript=transcript, extracted=ex, model=model)
    if not _has_work(ex):
        # "Corolla's done, invoice it": he gave no work or money, so keep what's on the job
        from .joblookup import prepare_invoice

        d = prepare_invoice(s, job)
        return Draft(ok=d["ok"], job=d["job"], readback=d["readback"], transcript=transcript, extracted=ex, model=model)
    if job.status in (JobStatus.invoiced, JobStatus.paid):
        v = svc.job_view(s, job)
        return Draft(ok=False, readback=f"{(v['customer'] or 'That').split()[0]}'s {' '.join(v['vehicle'].split()[:2])} is already invoiced ({v['invoice_number']}).", transcript=transcript, extracted=ex, model=model)
    warnings = apply_to_job(s, job, ex)
    view = svc.job_view(s, job)
    paid = str(ex.get("paid_method") or "").lower()
    return Draft(
        ok=True,
        job=view,
        readback=readback(view, warnings),
        warnings=warnings,
        transcript=transcript,
        extracted=ex,
        paid_method=paid if paid in ("eftpos", "cash", "transfer") else "",
        model=model,
    )
