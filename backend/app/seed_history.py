"""Past visits for the demo's regulars, so the agent has a real history to remember:
"same as last time for Maria's Corolla", "when was the Ranger last in". All of it
sits a month or more back, outside this quarter's GST figures and today's board."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlmodel import Session, select

from . import services as svc
from .models import (
    Customer,
    Invoice,
    InvoiceStatus,
    Job,
    JobLine,
    JobStatus,
    LineKind,
    OwnerFact,
    Payment,
    Vehicle,
)

# rego, days ago, title, lines (kind, description, qty, unit_cents ex GST), notes
VISITS: list[tuple[str, int, str, list[tuple[LineKind, str, float, int]], str | None]] = [
    ("ABC123", 182, "Logbook service", [
        (LineKind.labour, "Logbook service", 1, 15455),
        (LineKind.part, "Engine oil 5W-30 (5L)", 1, 7500),
        (LineKind.part, "Oil filter - Toyota", 1, 2500),
    ], "Front pads getting low, maybe 3 months."),
    ("ABC123", 365, "Logbook service and wiper blades", [
        (LineKind.labour, "Logbook service", 1, 15455),
        (LineKind.part, "Engine oil 5W-30 (5L)", 1, 7500),
        (LineKind.part, "Oil filter - Toyota", 1, 2500),
        (LineKind.part, "Wiper blades pair", 1, 3636),
    ], None),
    ("1KR9ZZ", 95, "Logbook service", [
        (LineKind.labour, "Logbook service", 1.5, 12000),
        (LineKind.part, "Engine oil 5W-30 (5L)", 1, 7500),
        (LineKind.part, "Oil filter", 1, 2500),
        (LineKind.part, "Cabin filter - universal", 1, 3500),
    ], None),
    ("LOC777", 60, "Battery replacement", [
        (LineKind.labour, "Fit battery, test charging", 0.5, 12000),
        (LineKind.part, "Battery N70ZZ", 1, 27273),
    ], "Alternator charging fine."),
    ("LOC777", 240, "Major service", [
        (LineKind.labour, "Major service", 3, 12000),
        (LineKind.part, "Engine oil 5W-30 (5L) x2", 2, 7500),
        (LineKind.part, "Oil, air and fuel filters", 1, 9091),
    ], None),
    ("GC8899", 120, "Tyres and alignment", [
        (LineKind.part, "Tyre 225/60R17", 2, 18182),
        (LineKind.labour, "Fit, balance and wheel alignment", 1, 12000),
    ], "Rear tyres about half."),
    ("AH5566", 45, "Brake pads front", [
        (LineKind.labour, "Replace front pads", 1, 12000),
        (LineKind.part, "Brake pads front - Honda Civic", 1, 10000),
    ], None),
]

FACTS: list[tuple[str | None, str]] = [
    ("LOC777", "Liam usually pays by bank transfer and wants the invoice emailed."),
    ("ABC123", "Maria likes a text before any extra work over $100."),
]


def seed_history(s: Session) -> None:
    for rego, days_ago, title, lines, notes in VISITS:
        v = s.exec(select(Vehicle).where(Vehicle.rego == rego)).first()
        if not v:
            continue
        when = datetime.utcnow() - timedelta(days=days_ago)
        j = Job(customer_id=v.customer_id, vehicle_id=v.id, title=title, status=JobStatus.paid, mechanic_notes=notes, created_at=when, updated_at=when)
        s.add(j)
        s.flush()
        s.add_all([JobLine(job_id=j.id, kind=k, description=d, qty=q, unit_cents=u) for k, d, q, u in lines])
        s.flush()
        # written directly: no texts to the customer, no PDFs, for visits long settled
        sub, gst, tot = svc.job_totals(s, j)
        inv = Invoice(number=svc.next_invoice_number(s), job_id=j.id, customer_id=j.customer_id, subtotal_cents=sub, gst_cents=gst, total_cents=tot, status=InvoiceStatus.paid, issued_at=when, due_at=when.date() + timedelta(days=7))
        s.add(inv)
        s.flush()
        s.add(Payment(invoice_id=inv.id, amount_cents=tot, method="eftpos", paid_at=when))
        j.status = JobStatus.paid
    for rego, fact in FACTS:
        v = s.exec(select(Vehicle).where(Vehicle.rego == rego)).first() if rego else None
        c = s.get(Customer, v.customer_id) if v else None
        s.add(OwnerFact(fact=fact, customer_id=c.id if c else None, vehicle_id=v.id if v else None))
    s.flush()
