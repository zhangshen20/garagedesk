"""Keep GarageDesk in step with the website's bookings.

Every site booking that GarageDesk has seen gets a ``SiteBookingLink`` row. That
row ties the site's reference (e.g. SNM-7K2Q) to the local customer, booking and,
once work starts, the job. It makes every operation here idempotent: syncing
twice, or a webhook arriving after a poll, never creates a second job.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from pydantic import NaiveDatetime
from sqlmodel import Field, Session, SQLModel, select

from .. import services as svc
from ..models import (
    Booking,
    BookingStatus,
    Customer,
    Job,
    JobLine,
    JobStatus,
    LineKind,
    Vehicle,
    now,
)
from .drafts import job_draft, normalise_rego, split_vehicle
from .source import BookingSource, SiteBooking


class SiteBookingLink(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    site_id: str = Field(index=True, unique=True)
    reference: str = Field(index=True, unique=True)
    site_status: str
    booking_id: int | None = Field(default=None, foreign_key="booking.id")
    job_id: int | None = Field(default=None, foreign_key="job.id")
    synced_at: NaiveDatetime = Field(default_factory=now)


_STATUS_MAP = {
    "requested": BookingStatus.requested,
    "confirmed": BookingStatus.confirmed,
    "checked_in": BookingStatus.checked_in,
    "completed": BookingStatus.completed,
    "declined": BookingStatus.cancelled,
    "cancelled": BookingStatus.cancelled,
}
_INACTIVE = {"declined", "cancelled"}


def get_link(s: Session, reference: str) -> SiteBookingLink | None:
    return s.exec(select(SiteBookingLink).where(SiteBookingLink.reference == reference.upper())).first()


def _same_person(a: str, b: str) -> bool:
    return a.strip().lower().split()[:1] == b.strip().lower().split()[:1]


def _upsert_customer(s: Session, b: SiteBooking) -> tuple[Customer, Vehicle | None]:
    """Match on phone first. A rego alone only matches when the name agrees too,
    because cars change hands and a wrong match would invoice the wrong person."""
    rego = normalise_rego(b.registration)
    parts = split_vehicle(b.vehicle)
    name = b.customer_name.strip()
    c = svc.find_customer(s, phone=b.customer_phone)
    by_rego = s.exec(select(Vehicle).where(Vehicle.rego == rego)).first() if rego else None
    if c is None and by_rego is not None:
        owner = s.get(Customer, by_rego.customer_id)
        if owner and _same_person(owner.name, name):
            c = owner
    if c is None:
        c = Customer(name=name or "Unknown", phone=svc.normalise_phone(b.customer_phone))
        s.add(c)
        s.flush()
    if b.customer_email and not c.email:
        c.email = b.customer_email.strip()

    v = by_rego if by_rego is not None and by_rego.customer_id == c.id else None
    if v is None:
        q = select(Vehicle).where(Vehicle.customer_id == c.id)
        q = q.where(Vehicle.rego == rego) if rego else q.where(Vehicle.make == parts["make"], Vehicle.model == parts["model"])
        v = s.exec(q).first()
    if v is None and (rego or parts["make"]):
        v = Vehicle(customer_id=c.id, rego=rego or "UNKNOWN", make=parts["make"] or "Unknown", model=parts["model"])
        s.add(v)
        s.flush()
    if v is not None and v.year is None and parts["year"]:
        v.year = parts["year"]
    return c, v


def upsert(s: Session, b: SiteBooking) -> tuple[SiteBookingLink, bool]:
    """Mirror one site booking locally. Returns (link, created)."""
    link = s.exec(select(SiteBookingLink).where(SiteBookingLink.site_id == b.id)).first()
    created = link is None
    if link is None:
        link = SiteBookingLink(site_id=b.id, reference=b.reference.upper(), site_status=b.status)
        if b.status in _INACTIVE:
            s.add(link)
            s.flush()
            return link, True
        c, v = _upsert_customer(s, b)
        start = svc.parse_time(b.start_time)
        bay = svc.first_free_bay(s, b.slot_date, start) or 1
        booking = Booking(
            customer_id=c.id, vehicle_id=v.id if v else None, day=b.slot_date, start=start, bay=bay,
            service=b.service.strip(), status=_STATUS_MAP[b.status], source="web",
            notes=f"Website booking {b.reference}" + (f": {b.notes.strip()}" if b.notes else ""),
        )
        s.add(booking)
        s.flush()
        link.booking_id = booking.id
        s.add(link)
        svc.log_event(s, "system", "site_booking_imported", f"{b.reference} {b.customer_name} {b.service}", "booking", booking.id)
    else:
        if link.booking_id:
            booking = s.get(Booking, link.booking_id)
            if booking:
                booking.status = _STATUS_MAP[b.status]
                booking.day = b.slot_date
                booking.start = svc.parse_time(b.start_time)
        link.site_status = b.status
        link.synced_at = now()
    s.flush()
    return link, created


def start_job(s: Session, b: SiteBooking, *, done: bool = False) -> tuple[Job, bool]:
    """Create the job card for a site booking, prefilled from the booking.
    Returns (job, created). Calling it again returns the same job."""
    link, _ = upsert(s, b)
    if link.job_id:
        job = s.get(Job, link.job_id)
        if job:
            if done and job.status in (JobStatus.quoted, JobStatus.approved, JobStatus.in_progress, JobStatus.waiting_parts):
                job.status = JobStatus.done
                job.updated_at = datetime.utcnow()
            return job, False
    booking = s.get(Booking, link.booking_id) if link.booking_id else None
    if booking is None:
        c, v = _upsert_customer(s, b)
        customer_id, vehicle_id = c.id, v.id if v else None
    else:
        customer_id, vehicle_id = booking.customer_id, booking.vehicle_id
    draft = job_draft(b)
    job = Job(
        booking_id=link.booking_id, customer_id=customer_id, vehicle_id=vehicle_id,
        title=draft["title"], status=JobStatus.done if done else JobStatus.in_progress,
        mechanic_notes=draft["notes"],
    )
    s.add(job)
    s.flush()
    for line in draft["lines"]:
        s.add(JobLine(job_id=job.id, kind=LineKind(line["kind"]), description=line["description"], qty=line["qty"], unit_cents=line["unit_cents"]))
    link.job_id = job.id
    svc.log_event(s, "system", "site_job_started", f"{b.reference} -> job {job.id}", "job", job.id)
    s.flush()
    return job, True


def on_completed(s: Session, b: SiteBooking) -> dict[str, Any]:
    """The site marked the booking completed: make sure there is a finished job
    with the booking's details on it, ready for the invoice. The invoice itself
    is only issued once the owner confirms the work and price."""
    job, created = start_job(s, b, done=True)
    if created:
        svc.log_event(s, "system", "invoice_draft_started", f"{b.reference} completed on the website; job {job.id} ready to invoice", "job", job.id)
    return {"reference": b.reference, "job_id": job.id, "created": created, "job": svc.job_view(s, job)}


def handle_site_booking(s: Session, b: SiteBooking) -> dict[str, Any]:
    """One booking changed on the site (webhook or poll)."""
    if b.status == "completed":
        return {"action": "invoice_draft", **on_completed(s, b)}
    link, created = upsert(s, b)
    return {"action": "imported" if created else "updated", "reference": link.reference, "booking_id": link.booking_id}


def sync(s: Session, source: BookingSource, start: date | None = None, days: int = 7) -> dict[str, Any]:
    """Pull bookings from the site and mirror them. Bookings that turned
    "completed" since the last sync start an invoice draft, so the link works
    even if the site never sends a webhook."""
    start = start or svc.today()
    end = start + timedelta(days=max(days, 1) - 1)
    summary: dict[str, Any] = {"source": source.name, "from": start.isoformat(), "to": end.isoformat(), "imported": [], "updated": [], "invoice_drafts": []}
    for b in source.list_bookings(start, end):
        existing = get_link(s, b.reference)
        if b.status == "completed" and not (existing and existing.job_id and existing.site_status == "completed"):
            summary["invoice_drafts"].append(on_completed(s, b)["reference"])
            continue
        _, created = upsert(s, b)
        summary["imported" if created else "updated"].append(b.reference)
    return summary
