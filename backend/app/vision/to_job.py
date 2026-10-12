"""Hand a scanned card to the owner app's Talk-to-Invoice pipeline (agent/jobcard.py).

The photo goes through the same apply_to_job / readback as a
spoken job, so pricing, labour rate and approval all behave identically. What the
careful reader adds lands in the same response: doubtful customer, rego, car,
labour or work become `warnings` (the app reads them out and holds Send until
they are fixed); smaller doubts such as a changed phone number are only read out."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlmodel import Session, select

from .. import services as svc
from ..agent.jobcard import Draft, _job_from_todays_booking, apply_to_job, match_open_job, readback
from ..models import Customer, Job, JobLine, JobStatus, LineKind, Vehicle
from . import normalise as nz
from .schema import JobDraft

# Doubts serious enough to hold the invoice. Unpriced parts and missing labour are
# already warned about by apply_to_job, so they are not repeated here.
BLOCKING = {"customer_name", "rego", "vehicle", "labour_hours", "work_done"}


def to_owner_draft(s: Session, card: JobDraft) -> dict[str, Any]:
    ex = card.to_extract()
    transcript = _transcript(card)
    model = " + ".join([*(m for m in card.models.get("vision", []) if m), str(card.models.get("tidy") or "")]).strip(" +")
    base = {"kind": "draft", "jobcard": card.model_dump(exclude={"readings"})}
    if card.warnings and not card.lines:
        say = " ".join(card.readback) or "I couldn't read that card."
        return {**base, **Draft(ok=False, readback=say, warnings=card.warnings, transcript=transcript, model=model).as_dict()}
    job = find_job(s, card)
    if not job:
        say = "I couldn't match that card to a job. " + (
            "What's the rego?" if not ex["rego"] else "Who's the customer?"
        )
        return {**base, **Draft(ok=False, readback=say, transcript=transcript, extracted=ex, model=model).as_dict()}
    if job.status in (JobStatus.invoiced, JobStatus.paid):
        return {**base, **Draft(ok=False, readback="That job is already invoiced.", transcript=transcript, extracted=ex, model=model).as_dict()}

    warnings = apply_to_job(s, job, ex)
    warnings += _unprice_misfits(s, job, card)
    _save_phone(s, job, card)
    if card.photo_id:
        job.mechanic_notes = ((job.mechanic_notes or "") + f"\nJob card photo: /api/jobcards/photos/{card.photo_id}.jpg").strip()
    blocking = [c["say"] for c in card.checks if c["field"] in BLOCKING]
    if card.labour_hours.value is None:
        blocking = [b for b in blocking if not b.startswith("How many hours")]
    info = [c["say"] for c in card.checks if c["field"] not in BLOCKING and c["field"] != "part"]
    all_warnings = blocking + warnings
    view = svc.job_view(s, job)
    say = " ".join([readback(view, []).removesuffix(" Send it?"), *all_warnings, *info])
    say += " Say it again with that and I'll fix it." if all_warnings else " Send it?"
    svc.log_event(s, "owner", "job_card_photo", f"job {job.id}: {card.title} ({card.overall_confidence:.0%} sure)", "job", job.id)
    return {
        **base,
        **Draft(
            ok=True,
            job=view,
            readback=say,
            warnings=all_warnings,
            transcript=transcript,
            extracted=ex,
            paid_method=ex["paid_method"],
            model=model,
        ).as_dict(),
    }


def _save_phone(s: Session, job: Job, card: JobDraft) -> None:
    """A walk-in opened from the card has no number yet; keep the one written on it."""
    c = s.get(Customer, job.customer_id)
    number, ok = nz.phone(str(card.phone.value or ""))
    if c and ok and card.phone.confidence >= 0.75 and (not c.phone or c.phone.startswith("unknown")):
        c.phone = number


def _transcript(card: JobDraft) -> str:
    parts = [
        card.customer_name.raw,
        card.phone.raw,
        card.vehicle.raw,
        card.rego.raw,
        *(w.raw for w in card.work_done),
        *(line.raw for line in card.lines if line.kind == "part"),
        card.labour_hours.raw and f"Labour {card.labour_hours.raw}",
        card.notes.raw,
    ]
    return "\n".join(p for p in parts if p)


def find_job(s: Session, card: JobDraft) -> Job | None:
    """A card always names the car by rego, so match on the rego only. Loose word
    matching ("Ranger", "Patel") would put a new customer's work on someone else's job."""
    rego = str(card.rego.value or "")
    if not rego:
        return None
    job = match_open_job(s, "", rego)
    if job and _rego_of(s, job) == rego:
        return job
    job = _job_from_todays_booking(s, "", rego)
    if job and _rego_of(s, job) == rego:
        return job
    if not card.customer_name.value and not card.customer_id:
        return None
    veh = card.vehicle.value if isinstance(card.vehicle.value, dict) else {}
    c, v = svc.find_or_create_customer(
        s,
        name=str(card.customer_name.value or ""),
        phone=str(card.phone.value or "") if card.phone.confidence >= 0.75 else "",
        rego=rego,
        vehicle=" ".join(str(x) for x in (veh.get("make"), veh.get("model")) if x),
    )
    if v and veh.get("year") and not v.year:
        v.year = veh["year"]
    j = Job(customer_id=c.id, vehicle_id=v.id if v else None, title=card.title or "Workshop job", status=JobStatus.in_progress, updated_at=datetime.utcnow())
    s.add(j)
    s.flush()
    svc.log_event(s, "owner", "job_opened", f"from job card photo: {c.name} {rego}", "job", j.id)
    return j


def _rego_of(s: Session, job: Job) -> str:
    v = s.get(Vehicle, job.vehicle_id) if job.vehicle_id else None
    return v.rego if v else ""


def _unprice_misfits(s: Session, job: Job, card: JobDraft) -> list[str]:
    """apply_to_job prices parts by loose name match. Where the reader found the part
    isn't in the catalogue for this car (Ranger pads vs the Corolla pads we stock),
    undo that price rather than bill the wrong part."""
    ours = [line for line in card.lines if line.kind == "part"]
    rows = s.exec(select(JobLine).where(JobLine.job_id == job.id, JobLine.kind == LineKind.part).order_by(JobLine.id)).all()
    out = []
    for mine, row in zip(ours, rows):
        if mine.part_id is None and mine.price_dollars is None and row.part_id is not None:
            row.part_id, row.unit_cents, row.description = None, 0, mine.description
            out.append(f"I don't have a price for {mine.description}.")
    s.flush()
    return out
