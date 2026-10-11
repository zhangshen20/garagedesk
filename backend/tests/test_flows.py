"""End-to-end flows through the API with the mock Nemotron. The same tool loop,
prompts and tools run against the real models; only the model is swapped."""

import os


def test_health_and_seed(client):
    assert client.get("/healthz").json()["status"] == "ok"
    o = client.get("/api/overview").json()
    assert o["shop"]["name"]
    assert len(o["bookings_today"]) >= 3
    assert o["unpaid"]["count"] >= 1


def test_customer_books_over_web_chat(client):
    r = client.post("/api/chat/customer", json={"text": "Hi it's Ben Hall, Toyota Camry rego BHX442, needs a logbook service", "session_id": "web-t1"}).json()
    tools = [s["tool"] for s in r["steps"]]
    assert tools == ["find_or_create_customer", "list_availability", "create_booking"]
    assert "SAC-" in r["reply"]
    bk = client.get("/api/bookings", params={"day": "tomorrow", "days": 3}).json()["bookings"]
    assert any(b["customer"] == "Ben Hall" and "BHX442" in b["vehicle"] for b in bk)
    # transcript persisted
    convs = client.get("/api/conversations").json()["conversations"]
    conv = next(c for c in convs if c["external_id"] == "web-t1")
    msgs = client.get(f"/api/conversations/{conv['id']}").json()["messages"]
    assert any(m["role"] == "tool" and m["tool"] == "create_booking" for m in msgs)


def test_sms_status_check_returns_twiml(client):
    r = client.post("/twilio/sms", data={"From": "+61411000001", "Body": "is my Corolla ABC123 ready yet?"})
    assert r.status_code == 200 and "<Message>" in r.text
    assert "Corolla" in r.text


def test_voice_call_greets_then_answers(client):
    first = client.post("/twilio/voice", data={"From": "+61422000000"})
    assert "<Gather" in first.text and "Sunshine" in first.text
    second = client.post("/twilio/voice", data={"From": "+61422000000", "SpeechResult": "what are your opening hours"})
    assert "Mon-Sat" in second.text


def test_parts_order_needs_owner_approval_then_sends(client):
    r = client.post("/api/chat/owner", json={"text": "order brake pads for job 3"}).json()
    assert [s["tool"] for s in r["steps"]] == ["lookup_part_price", "order_parts"]
    approvals = client.get("/api/approvals").json()["approvals"]
    pending = [a for a in approvals if a["status"] == "pending" and a["kind"] == "purchase_order"]
    assert pending
    assert client.get("/api/outbox").json()["outbox"] == [] or all("orders@" not in o["to"] for o in client.get("/api/outbox").json()["outbox"])
    d = client.post(f"/api/approvals/{pending[0]['id']}", json={"approve": True}).json()
    assert d["status"] == "approved" and d["sent_via"] == "email"
    ob = client.get("/api/outbox").json()["outbox"]
    assert any(o["channel"] == "email" and "PO-" in (o["subject"] or "") for o in ob)
    parts = client.get("/api/parts").json()
    assert parts["purchase_orders"][0]["status"] == "sent"


def test_invoice_gst_and_pdf_and_payment(client):
    r = client.post("/api/chat/owner", json={"text": "invoice job 4"}).json()
    assert "INV-" in r["reply"]
    inv = next(i for i in client.get("/api/invoices").json()["invoices"] if i["job_id"] == 4)
    assert inv["gst_cents"] == round(inv["subtotal_cents"] * 0.10)
    assert inv["total_cents"] == inv["subtotal_cents"] + inv["gst_cents"]
    pdf = client.get(inv["pdf"])
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    # the customer was texted
    assert any(inv["number"] in o["body"] for o in client.get("/api/outbox").json()["outbox"])
    p = client.post(f"/api/invoices/{inv['number']}/payments", json={"amount_cents": inv["total_cents"], "method": "card"}).json()
    assert p["status"] == "paid"
    rec = client.get(f"/api/invoices/{inv['number']}/receipt")
    assert rec.status_code == 200 and rec.content[:4] == b"%PDF"


def test_daily_report_generated_and_owner_texted(client):
    r = client.post("/api/reports/generate").json()
    assert "End of day" in r["content_md"]
    assert client.get("/api/reports").json()["reports"][0]["day"] == r["day"]
    ob = client.get("/api/outbox").json()["outbox"]
    assert any("end of day" in o["body"].lower() for o in ob)


def test_check_in_opens_job_card(client):
    today = client.get("/api/overview").json()["bookings_today"]
    b = next(x for x in today if x["status"] == "confirmed")
    client.patch(f"/api/bookings/{b['booking_id']}", json={"status": "checked_in"})
    jobs = client.get("/api/jobs", params={"status": "in_progress"}).json()["jobs"]
    assert any(j["booking_id"] == b["booking_id"] for j in jobs)


def test_mock_mode_reported(client):
    assert client.get("/api/overview").json()["llm"]["mode"] == "mock"
    assert os.environ["LLM_MODE"] == "mock"
