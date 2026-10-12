"""The owner app: speak or photograph a job card, get a priced draft, send it for
approval, the approver taps once, the customer gets the invoice; EFTPOS marks it paid."""

import base64
from urllib.parse import parse_qs, urlparse


def _outbox(client):
    return client.get("/api/outbox").json()["outbox"]


def _approval_link(client) -> tuple[int, str]:
    body = next(o["body"] for o in _outbox(client) if "/approve/" in o["body"])
    url = urlparse(body[body.index("http"):].split()[0])
    return int(url.path.rsplit("/", 1)[-1]), parse_qs(url.query)["t"][0]


def test_spoken_job_card_becomes_priced_draft(client):
    r = client.post("/api/owner/voice", json={"text": "Corolla ABC123 done. Front pads and an oil filter, hour and a half labour"}).json()
    assert r["kind"] == "draft" and r["ok"], r
    job = r["job"]
    assert job["rego"] == "ABC123" and job["status"] == "done"
    kinds = [l["kind"] for l in job["lines"]]
    assert kinds.count("labour") == 1 and kinds.count("part") == 2
    labour = next(l for l in job["lines"] if l["kind"] == "labour")
    assert labour["qty"] == 1.5 and labour["unit_cents"] == 12000
    # parts priced from the catalogue, not invented
    assert all(l["unit_cents"] > 0 for l in job["lines"])
    assert "Send it?" in r["readback"] and "Maria" in r["readback"]
    # saying it again replaces the lines rather than doubling them
    r2 = client.post("/api/owner/voice", json={"text": "Corolla ABC123, front pads, hour and a half"}).json()
    assert len(r2["job"]["lines"]) == 2


def test_missing_price_is_read_back(client):
    r = client.post("/api/owner/voice", json={"text": "CX-5 1KR9ZZ, replaced the battery, half an hour labour, wiper blades"}).json()
    assert r["ok"]
    assert "battery" in r["readback"].lower() or "wiper" in r["readback"].lower()


def test_unknown_car_asks_for_rego(client):
    r = client.post("/api/owner/voice", json={"text": "Hilux done, pads, one hour labour"}).json()
    assert r["kind"] == "draft" and not r["ok"]
    assert "rego" in r["readback"].lower()


def test_photo_of_paper_job_card(client):
    img = base64.b64encode(b"\xff\xd8\xff fake jpeg").decode()
    r = client.post("/api/owner/photo", json={"image_b64": img}).json()
    assert r["ok"], r
    assert "Front brake" in r["transcript"]
    pads = next(l for l in r["job"]["lines"] if l["kind"] == "part")
    assert pads["unit_cents"] == round(11900 / 1.1)  # "$119" written on the card is inc GST
    assert r["paid_method"] == "eftpos"


def test_send_waits_for_approver_then_texts_customer(client):
    job = client.post("/api/owner/voice", json={"text": "Corolla ABC123 done, front pads, hour and a half labour"}).json()["job"]
    r = client.post(f"/api/owner/jobs/{job['job_id']}/send").json()
    assert r["status"] == "awaiting_approval"
    assert not any("ready to collect" in o["body"] for o in _outbox(client))
    aid, token = _approval_link(client)
    assert client.get(f"/api/approve/{aid}", params={"t": "wrong"}).status_code == 404
    view = client.get(f"/api/approve/{aid}", params={"t": token}).json()
    assert view["job"]["job_id"] == job["job_id"] and view["kind"] == "invoice"
    d = client.post(f"/api/approve/{aid}", json={"t": token, "approve": True}).json()
    assert d["status"] == "approved" and d["invoice_number"].startswith("INV-")
    assert any("ready to collect" in o["body"] and d["invoice_number"] in o["body"] for o in _outbox(client))
    # one tap on EFTPOS: paid, receipt texted
    p = client.post(f"/api/owner/jobs/{job['job_id']}/paid", json={"method": "eftpos"}).json()
    assert p["status"] == "paid"
    assert any("EFTPOS" in o["body"] and "Receipt" in o["body"] for o in _outbox(client))


def test_approver_sends_it_back(client):
    job = client.post("/api/owner/voice", json={"text": "Corolla ABC123, front pads, hour and a half labour"}).json()["job"]
    client.post(f"/api/owner/jobs/{job['job_id']}/send")
    aid, token = _approval_link(client)
    d = client.post(f"/api/approve/{aid}", json={"t": token, "approve": False, "note": "labour is 2 hours"}).json()
    assert d["status"] == "rejected"
    assert any("labour is 2 hours" in o["body"] for o in _outbox(client))
    assert client.get(f"/api/jobs/{job['job_id']}").json()["invoice_number"] is None


def test_status_update_and_paid_by_voice(client):
    r = client.post("/api/owner/voice", json={"text": "The CX-5 is done"}).json()
    assert r["kind"] == "reply"
    assert any(s["tool"] == "update_car_status" for s in r["steps"])
    assert any("Jack" in o["body"] and "finished" in o["body"] for o in _outbox(client))
    today = client.get("/api/owner/today").json()
    assert any(j["rego"] == "1KR9ZZ" and j["status"] == "done" for j in today["jobs"])


def test_unknown_rego_is_not_matched_by_name(client):
    # a new customer who shares a surname with Priya Patel, and a Ranger that isn't Liam's
    r = client.post("/api/owner/voice", json={"text": "Mazda 3 DEF456 for J Patel, front pads, one hour labour"}).json()
    assert not r["ok"] or r["job"]["rego"] == "DEF456"
    r = client.post("/api/owner/voice", json={"text": "Ranger 1XY9KL, oil filter, half an hour"}).json()
    assert not r["ok"] or r["job"]["rego"] == "1XY9KL"


def test_part_for_another_car_is_not_used(client):
    from app.agent.jobcard import match_part
    from app.db import session_scope

    with session_scope() as s:
        assert match_part(s, "Pads", "Mazda CX-5 1KR9ZZ") is None
        assert match_part(s, "Brake pads front", "Toyota Corolla ABC123") is not None


def test_demo_reset_restores_clean_state(client):
    client.post("/api/owner/voice", json={"text": "The CX-5 is done"})
    assert client.post("/api/demo/reset").json()["ok"]
    today = client.get("/api/owner/today").json()
    assert any(j["rego"] == "1KR9ZZ" and j["status"] == "in_progress" for j in today["jobs"])
    assert len(client.get("/api/outbox").json()["outbox"]) <= 2  # only the seeded receipt
