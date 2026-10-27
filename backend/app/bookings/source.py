"""Where site bookings come from.

``SiteBooking`` mirrors ``WorkshopBooking`` in the site's src/lib/booking-contract.ts
field for field (camelCase on the wire), so the site can return its existing
``mapBooking`` output unchanged.
"""

from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache
from typing import Literal, Protocol

import httpx
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from pydantic_settings import BaseSettings, SettingsConfigDict

SiteStatus = Literal["requested", "confirmed", "checked_in", "completed", "declined", "cancelled"]


class SiteBooking(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")

    id: str
    reference: str
    status: SiteStatus
    customer_name: str
    customer_email: str = ""
    customer_phone: str
    vehicle: str
    registration: str | None = None
    service: str
    notes: str | None = None
    leave_all_day: bool = False
    slot_date: date
    start_time: str  # "HH:MM", Melbourne local time
    updated_at: str = ""


class SiteLinkSettings(BaseSettings):
    """Kept separate from app.config so this module stays self-contained."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Base URL of the website, e.g. https://www.example-workshop.com.au
    site_bookings_url: str = ""
    # Bearer token the site checks on GET /integrations/garagedesk/bookings
    site_bookings_token: str = ""
    # Shared secret the site signs webhooks with (HMAC-SHA256 of the raw body)
    site_webhook_secret: str = ""
    # auto: http when site_bookings_url is set, otherwise mock
    site_bookings_mode: str = "auto"  # auto | http | mock

    @property
    def effective_mode(self) -> str:
        if self.site_bookings_mode == "auto":
            return "http" if self.site_bookings_url else "mock"
        return self.site_bookings_mode


@lru_cache
def get_link_settings() -> SiteLinkSettings:
    return SiteLinkSettings()


class BookingSource(Protocol):
    name: str

    def list_bookings(self, start: date, end: date) -> list[SiteBooking]: ...


class SiteUnavailable(RuntimeError):
    pass


class HttpBookingSource:
    """Reads ``GET {base}/integrations/garagedesk/bookings?from=YYYY-MM-DD&to=YYYY-MM-DD``.

    Also accepts the shape of the site's existing ``/admin/api/dashboard`` response
    (``{"bookings": [...]}``), so either endpoint works.
    """

    name = "http"
    path = "/integrations/garagedesk/bookings"

    def __init__(self, base_url: str, token: str, client: httpx.Client | None = None):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.client = client or httpx.Client(timeout=10)

    def list_bookings(self, start: date, end: date) -> list[SiteBooking]:
        headers = {"accept": "application/json"}
        if self.token:
            headers["authorization"] = f"Bearer {self.token}"
        try:
            r = self.client.get(
                self.base_url + self.path,
                params={"from": start.isoformat(), "to": end.isoformat()},
                headers=headers,
            )
            r.raise_for_status()
            data = r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise SiteUnavailable(f"Booking site could not be read: {e}") from e
        rows = data.get("bookings", []) if isinstance(data, dict) else data
        return [SiteBooking.model_validate(row) for row in rows]


class MockBookingSource:
    """A believable week at Sunshine North Mechanic, relative to ``today``.

    State is kept in memory so the demo can flip a booking to "completed" and
    watch the invoice draft appear, exactly as the real webhook would.
    """

    name = "mock"

    def __init__(self, today: date | None = None):
        from .. import services as svc

        self.today = today or svc.today()
        self._bookings = {b.reference: b for b in _mock_rows(self.today)}

    def list_bookings(self, start: date, end: date) -> list[SiteBooking]:
        rows = [b for b in self._bookings.values() if start <= b.slot_date <= end]
        return sorted(rows, key=lambda b: (b.slot_date, b.start_time, b.reference))

    def get(self, reference: str) -> SiteBooking | None:
        return self._bookings.get(reference.upper())

    def set_status(self, reference: str, status: SiteStatus) -> SiteBooking:
        b = self._bookings[reference.upper()]
        b = b.model_copy(update={"status": status})
        self._bookings[b.reference] = b
        return b


def _mock_rows(today: date) -> list[SiteBooking]:
    def bk(ref: str, offset: int, hhmm: str, status: SiteStatus, name: str, phone: str, email: str,
           vehicle: str, rego: str | None, service: str, notes: str | None = None, all_day: bool = False) -> SiteBooking:
        return SiteBooking(
            id=f"mock-{ref.lower()}", reference=ref, status=status, customer_name=name,
            customer_email=email, customer_phone=phone, vehicle=vehicle, registration=rego,
            service=service, notes=notes, leave_all_day=all_day,
            slot_date=today + timedelta(days=offset), start_time=hhmm,
        )

    return [
        bk("SNM-7K2Q", 0, "08:00", "checked_in", "Priya Nair", "0412 555 104", "priya.nair@example.com",
           "2017 Mazda CX-5", "1XY2ZA", "Logbook service", "Due for 60,000 km service. Squeak from rear left when braking.", True),
        bk("SNM-3HD8", 0, "09:30", "confirmed", "Tom Bradley", "0433 555 218", "tom.b@example.com",
           "2012 Ford Falcon XR6", "TBX612", "RWC & roadworthy inspection", "Selling the car this weekend."),
        bk("SNM-9WPL", 0, "11:00", "confirmed", "Mei Chen", "0401 555 377", "mei.chen@example.com",
           "2019 Toyota Corolla", "BFR9QK", "Brake service", "Grinding noise front wheels."),
        bk("SNM-2MVC", 1, "08:30", "confirmed", "Daniel Russo", "0422 555 940", "d.russo@example.com",
           "2015 Holden Commodore", "XRT482", "Battery replacement", "Car struggles to start on cold mornings."),
        bk("SNM-6TRB", 1, "10:00", "requested", "Aisha Khan", "0455 555 612", "aisha.k@example.com",
           "2020 Hyundai i30", None, "New tyres x2 (front)", None),
        bk("SNM-4GJN", 2, "08:00", "requested", "Luke Papadopoulos", "0468 555 031", "lukep@example.com",
           "2014 Nissan Navara", "1LP4NV", "Engine diagnostic", "Check engine light on since last week.", True),
        bk("SNM-8QSX", -1, "13:00", "cancelled", "Grace O'Neill", "0499 555 225", "grace@example.com",
           "2011 Honda Jazz", "GON011", "Logbook service", None),
    ]


_mock: MockBookingSource | None = None


def get_source() -> BookingSource:
    """The configured source. The mock is a process-wide singleton so its state
    (bookings flipped to completed in the demo) survives between requests."""
    global _mock
    cfg = get_link_settings()
    if cfg.effective_mode == "http":
        return HttpBookingSource(cfg.site_bookings_url, cfg.site_bookings_token)
    if _mock is None:
        _mock = MockBookingSource()
    return _mock


def reset_source() -> None:
    global _mock
    _mock = None
    get_link_settings.cache_clear()
