"""Turn a site booking into a job draft: everything the owner would otherwise have
to say or type again (customer, phone, car, rego, what was booked).

The draft only proposes; Talk-to-Invoice or a job-card photo adds what was
actually done, and nothing is invoiced without the owner (or his wife) saying so.
"""

from __future__ import annotations

import re
from typing import Any

from .source import SiteBooking

# Hourly labour rate in cents, ex-GST. Same demo rate the seed data uses until
# the owner gives his real one.
LABOUR_RATE_CENTS = 12000

# Typical labour for what customers book on the site, used only as a starting
# suggestion. Keys are matched against the free-text service field.
TYPICAL_LABOUR: list[tuple[str, str, float]] = [
    (r"logbook|service\b", "Logbook service labour", 1.5),
    (r"rwc|roadworthy", "Roadworthy (RWC) inspection", 1.0),
    (r"pre-?purchase", "Pre-purchase inspection", 1.0),
    (r"brake", "Brake service labour", 1.5),
    (r"diagnos|check engine", "Engine diagnostic", 1.0),
    (r"batter", "Battery test and replacement", 0.5),
    (r"tyre|tire", "Tyre fitting and balancing", 0.5),
    (r"transmission|gearbox", "Transmission service labour", 2.0),
]

_YEAR = re.compile(r"^(19|20)\d{2}$")


def normalise_rego(rego: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", (rego or "").upper())


def split_vehicle(text: str) -> dict[str, Any]:
    """'2017 Mazda CX-5' -> year 2017, make Mazda, model CX-5."""
    words = (text or "").split()
    year = None
    if words and _YEAR.match(words[0]):
        year = int(words.pop(0))
    elif words and _YEAR.match(words[-1]):
        year = int(words.pop())
    make = words[0] if words else ""
    model = " ".join(words[1:])
    return {"year": year, "make": make, "model": model}


def suggested_lines(service: str) -> list[dict[str, Any]]:
    text = (service or "").lower()
    for pattern, description, hours in TYPICAL_LABOUR:
        if re.search(pattern, text):
            return [{
                "kind": "labour",
                "description": description,
                "qty": hours,
                "unit_cents": LABOUR_RATE_CENTS,
                "suggested": True,
            }]
    return []


def job_draft(b: SiteBooking) -> dict[str, Any]:
    vehicle = split_vehicle(b.vehicle)
    rego = normalise_rego(b.registration)
    missing = []
    if not rego:
        missing.append("rego")
    lines = suggested_lines(b.service)
    if not lines:
        missing.append("work_done")
    return {
        "source": "booking_site",
        "source_ref": b.reference,
        "customer": {"name": b.customer_name.strip(), "phone": b.customer_phone.strip(), "email": b.customer_email.strip() or None},
        "vehicle": {"rego": rego or None, **vehicle, "description": b.vehicle.strip()},
        "title": b.service.strip(),
        "notes": (b.notes or "").strip() or None,
        "lines": lines,
        "missing": missing,
        "booked_for": {"day": b.slot_date.isoformat(), "start": b.start_time, "leave_all_day": b.leave_all_day},
    }
