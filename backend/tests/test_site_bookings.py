"""The read-only link to the shop's website bookings (Sunshine North Mechanic)."""

import hashlib
import hmac
import json
import time
from datetime import date

import httpx
import pytest

from app.bookings import source as src
from app.bookings.drafts import job_draft, split_vehicle
from app.bookings.source import HttpBookingSource, SiteBooking, SiteUnavailable

# One booking exactly as the site's mapBooking() returns it (WorkshopBooking, camelCase).
SITE_ROW = {
    "id": "6f1c2a9e-0000-4000-8000-000000000001",
    "reference": "SNM-ZZ01",
    "slotId": "slot-1",
    "status": "confirmed",
    "customerName": "Jordan Lee",
    "customerEmail": "jordan@example.com",
    "customerPhone": "0412 345 678",
    "vehicle": "2016 Subaru Forester",
    "registration": "1ab 2cd",
    "service": "Logbook service",
    "notes": "Oil light came on",
    "leaveAllDay": False,
    "slotDate": "2026-10-13",
    "startTime": "08:30",
    "emailStatus": "sent",
    "emailLastSentAt": None,
    "emailLastError": None,
    "createdAt": "2026-10-10 01:00:00",
    "updatedAt": "2026-10-10 01:00:00",
}


@pytest.fixture(autouse=True)
def fresh_source(monkeypatch):
    for key in ("SITE_BOOKINGS_URL", "SITE_BOOKINGS_TOKEN", "SITE_WEBHOOK_SECRET", "SITE_BOOKINGS_MODE"):
        monkeypatch.delenv(key, raising=False)
    src.reset_source()
    yield
    src.reset_source()


def test_site_row_parses_and_drafts():
    b = SiteBooking.model_validate(SITE_ROW)
    d = job_draft(b)
    assert d["customer"] == {"name": "Jordan Lee", "phone": "0412 345 678", "email": "jordan@example.com"}
    assert d["vehicle"]["rego"] == "1AB2CD"
    assert (d["vehicle"]["year"], d["vehicle"]["make"], d["vehicle"]["model"]) == (2016, "Subaru", "Forester")
    assert d["lines"][0]["kind"] == "labour" and d["lines"][0]["suggested"]
    assert d["missing"] == []
    assert d["source_ref"] == "SNM-ZZ01"


def test_draft_says_what_is_missing():
    b = SiteBooking.model_validate({**SITE_ROW, "registration": None, "service": "Weird rattle"})
    d = job_draft(b)
    assert d["missing"] == ["rego", "work_done"] and d["lines"] == []


def test_split_vehicle_handles_year_anywhere():
    assert split_vehicle("Toyota Hilux 2018") == {"year": 2018, "make": "Toyota", "model": "Hilux"}
    assert split_vehicle("Ute") == {"year": None, "make": "Ute", "model": ""}


def test_http_source_reads_site_endpoint():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"bookings": [SITE_ROW]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    rows = HttpBookingSource("https://site.example/", "tok", client).list_bookings(date(2026, 10, 13), date(2026, 10, 19))
    assert rows[0].reference == "SNM-ZZ01"
    assert seen["url"] == "https://site.example/integrations/garagedesk/bookings?from=2026-10-13&to=2026-10-19"
    assert seen["auth"] == "Bearer tok"


def test_http_source_reports_outage():
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(403, text="Access denied")))
    with pytest.raises(SiteUnavailable):
        HttpBookingSource("https://site.example", "", client).list_bookings(date(2026, 10, 13), date(2026, 10, 13))


def test_list_bookings_with_drafts(client):
    r = client.get("/api/site-bookings").json()
    assert r["source"] == "mock"
    refs = [b["reference"] for b in r["bookings"]]
    assert "SNM-7K2Q" in refs and "SNM-8QSX" not in refs  # cancelled one hidden
    priya = next(b for b in r["bookings"] if b["reference"] == "SNM-7K2Q")
    assert priya["draft"]["vehicle"]["rego"] == "1XY2ZA"
    assert priya["garagedesk"] is None


def test_sync_puts_site_bookings_on_the_board_once(client):
    first = client.post("/api/site-bookings/sync").json()
    assert "SNM-3HD8" in first["imported"]
    again = client.post("/api/site-bookings/sync").json()
    assert again["imported"] == [] and "SNM-3HD8" in again["updated"]
    board = client.get("/api/bookings", params={"day": "today", "days": 3}).json()["bookings"]
    tom = [b for b in board if b["customer"] == "Tom Bradley"]
    assert len(tom) == 1 and tom[0]["source"] == "web" and "TBX612" in tom[0]["vehicle"]


def test_rego_on_someone_elses_car_does_not_merge_customers(client, monkeypatch):
    # ABC123 is Maria Nguyen's Corolla in the seed data; a new owner books it on the site.
    row = {**SITE_ROW, "customerName": "Sam Patel", "customerPhone": "0400 111 222", "registration": "ABC123", "vehicle": "2016 Toyota Corolla"}
    monkeypatch.setattr(src.MockBookingSource, "list_bookings", lambda self, a, b: [SiteBooking.model_validate(row)])
    client.post("/api/site-bookings/sync", params={"day": "2026-10-13"})
    board = client.get("/api/bookings", params={"day": "2026-10-13", "days": 1}).json()["bookings"]
    assert any(b["customer"] == "Sam Patel" and "ABC123" in b["vehicle"] for b in board)
    assert not any(b["customer"] == "Maria Nguyen" and b["source"] == "web" for b in board)


def test_start_job_prefills_from_booking(client):
    r = client.post("/api/site-bookings/SNM-7K2Q/start-job").json()
    job = r["job"]
    assert r["created"] and job["customer"] == "Priya Nair" and job["rego"] == "1XY2ZA"
    assert job["vehicle"] == "Mazda CX-5 1XY2ZA"
    assert job["lines"][0]["description"] == "Logbook service labour"
    assert "Squeak" in job["mechanic_notes"]
    again = client.post("/api/site-bookings/SNM-7K2Q/start-job").json()
    assert not again["created"] and again["job"]["job_id"] == job["job_id"]


def test_completed_on_site_starts_invoice_draft(client):
    r = client.post("/api/site-bookings/SNM-9WPL/demo-complete").json()
    assert r["action"] == "invoice_draft" and r["created"]
    assert r["job"]["status"] == "done" and r["job"]["invoice_number"] is None
    assert r["job"]["total_cents"] > 0
    # a later poll sees the same completed booking and does not start a second job
    s = client.post("/api/site-bookings/sync").json()
    assert "SNM-9WPL" not in s["invoice_drafts"]
    listed = next(b for b in client.get("/api/site-bookings").json()["bookings"] if b["reference"] == "SNM-9WPL")
    assert listed["garagedesk"]["job_id"] == r["job_id"]


def _signed(secret: str, payload: dict, ts: int | None = None) -> tuple[bytes, dict]:
    body = json.dumps(payload).encode()
    ts = str(ts or int(time.time()))
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return body, {"x-garagedesk-timestamp": ts, "x-garagedesk-signature": f"sha256={sig}", "content-type": "application/json"}


def test_webhook_completed_booking(client, monkeypatch):
    monkeypatch.setenv("SITE_WEBHOOK_SECRET", "s3cret")
    src.reset_source()
    payload = {"event": "booking.updated", "booking": {**SITE_ROW, "status": "completed"}}
    body, headers = _signed("s3cret", payload)
    r = client.post("/api/site-bookings/webhook", content=body, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["action"] == "invoice_draft"
    assert r.json()["job"]["customer"] == "Jordan Lee"
    # the same delivery again is harmless
    assert client.post("/api/site-bookings/webhook", content=body, headers=headers).json()["created"] is False


def test_webhook_rejects_bad_or_stale_signature(client, monkeypatch):
    payload = {"event": "booking.updated", "booking": SITE_ROW}
    body, headers = _signed("s3cret", payload)
    assert client.post("/api/site-bookings/webhook", content=body, headers=headers).status_code == 503
    monkeypatch.setenv("SITE_WEBHOOK_SECRET", "s3cret")
    src.reset_source()
    _, bad = _signed("wrong", payload)
    assert client.post("/api/site-bookings/webhook", content=body, headers=bad).status_code == 401
    stale_body, stale = _signed("s3cret", payload, ts=int(time.time()) - 3600)
    assert client.post("/api/site-bookings/webhook", content=stale_body, headers=stale).status_code == 401
