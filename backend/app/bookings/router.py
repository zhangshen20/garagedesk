"""HTTP API for the website booking link, mounted under /api/site-bookings."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import ValidationError
from sqlmodel import Session

from .. import services as svc
from ..db import get_session
from .drafts import job_draft
from .link import get_link, handle_site_booking, start_job, sync
from .source import MockBookingSource, SiteBooking, SiteUnavailable, get_link_settings, get_source

router = APIRouter(prefix="/api/site-bookings", tags=["site-bookings"])

# How far back and ahead to look when finding a booking by its reference.
LOOKUP_BACK_DAYS = 14
LOOKUP_AHEAD_DAYS = 60
# Webhooks older than this are refused, so a captured request cannot be replayed.
WEBHOOK_MAX_AGE_SECONDS = 300


def _list(start, days: int) -> list[SiteBooking]:
    try:
        return get_source().list_bookings(start, start + timedelta(days=max(days, 1) - 1))
    except SiteUnavailable as e:
        raise HTTPException(502, str(e)) from e


def _find(reference: str) -> SiteBooking:
    start = svc.today() - timedelta(days=LOOKUP_BACK_DAYS)
    for b in _list(start, LOOKUP_BACK_DAYS + LOOKUP_AHEAD_DAYS):
        if b.reference.upper() == reference.upper():
            return b
    raise HTTPException(404, f"No website booking {reference}")


def _view(s: Session, b: SiteBooking) -> dict[str, Any]:
    link = get_link(s, b.reference)
    return {
        **b.model_dump(mode="json"),
        "draft": job_draft(b),
        "garagedesk": {"booking_id": link.booking_id, "job_id": link.job_id} if link else None,
    }


@router.get("")
def list_site_bookings(day: str = "today", days: int = 7, include_inactive: bool = False, s: Session = Depends(get_session)) -> dict[str, Any]:
    """Today's and upcoming website bookings, each with a ready-made job draft."""
    rows = _list(svc.parse_day(day), min(days, 62))
    if not include_inactive:
        rows = [b for b in rows if b.status not in ("declined", "cancelled")]
    return {"source": get_source().name, "bookings": [_view(s, b) for b in rows]}


@router.post("/sync")
def sync_site_bookings(day: str = "today", days: int = 7, s: Session = Depends(get_session)) -> dict[str, Any]:
    """Mirror website bookings onto the GarageDesk board. Bookings marked
    completed on the site start an invoice draft."""
    try:
        summary = sync(s, get_source(), svc.parse_day(day), min(days, 62))
    except SiteUnavailable as e:
        raise HTTPException(502, str(e)) from e
    s.commit()
    return summary


@router.get("/{reference}/draft")
def site_booking_draft(reference: str) -> dict[str, Any]:
    return job_draft(_find(reference))


@router.post("/{reference}/start-job")
def start_job_from_site_booking(reference: str, s: Session = Depends(get_session)) -> dict[str, Any]:
    """The car has arrived: open its job card with the booking's details on it."""
    job, created = start_job(s, _find(reference))
    s.commit()
    return {"created": created, "job": svc.job_view(s, job)}


@router.post("/{reference}/demo-complete")
def demo_complete(reference: str, s: Session = Depends(get_session)) -> dict[str, Any]:
    """Demo only: mark a mock website booking completed, as the owner would on the
    site, and run the same handler the real webhook runs."""
    source = get_source()
    if not isinstance(source, MockBookingSource):
        raise HTTPException(409, "Only available with the mock booking source")
    if not source.get(reference):
        raise HTTPException(404, f"No website booking {reference}")
    result = handle_site_booking(s, source.set_status(reference, "completed"))
    s.commit()
    return result


def verify_signature(secret: str, timestamp: str, body: bytes, signature: str) -> bool:
    expected = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    given = signature.removeprefix("sha256=")
    return hmac.compare_digest(expected, given)


@router.post("/webhook")
async def site_webhook(
    request: Request,
    x_garagedesk_timestamp: str = Header(default=""),
    x_garagedesk_signature: str = Header(default=""),
    s: Session = Depends(get_session),
) -> dict[str, Any]:
    """Called by the website whenever a booking changes status.

    Body: ``{"event": "booking.updated", "booking": <WorkshopBooking>}``.
    Headers: ``X-GarageDesk-Timestamp`` (unix seconds) and
    ``X-GarageDesk-Signature: sha256=<hex HMAC-SHA256 of "{timestamp}.{raw body}">``.
    """
    secret = get_link_settings().site_webhook_secret
    if not secret:
        raise HTTPException(503, "Website webhook is not configured")
    body = await request.body()
    try:
        age = abs(time.time() - int(x_garagedesk_timestamp))
    except ValueError:
        age = None
    if age is None or age > WEBHOOK_MAX_AGE_SECONDS or not verify_signature(secret, x_garagedesk_timestamp, body, x_garagedesk_signature):
        raise HTTPException(401, "Bad signature")
    try:
        payload = json.loads(body)
        booking = SiteBooking.model_validate(payload["booking"])
    except (ValueError, KeyError, TypeError, ValidationError) as e:
        raise HTTPException(422, f"Unreadable booking: {e}") from e
    result = handle_site_booking(s, booking)
    s.commit()
    return result
