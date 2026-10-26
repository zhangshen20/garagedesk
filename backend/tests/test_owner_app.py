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
    assert r["kind"] in ("reply", "draft")  # with work on it, its invoice comes ready to send
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


def test_his_total_is_the_invoice_total(client):
    # the way he'd say it to his wife: what he did, and what to charge, all up
    r = client.post("/api/owner/voice", json={"text": "Corolla ABC123, front pads, hour and a half, $350 all up"}).json()
    assert r["ok"], r
    assert r["job"]["total_cents"] == 35000
    pads = next(l for l in r["job"]["lines"] if l["kind"] == "part")
    assert pads["unit_cents"] == 11900  # catalogue fills the part, labour takes the balance
    assert "350.00 dollars" in r["readback"]
    assert r["job"]["gst_cents"] + r["job"]["subtotal_cents"] == 35000


def test_his_item_and_labour_prices_are_used(client):
    r = client.post("/api/owner/voice", json={"text": "Corolla ABC123, pads $120, labour $180, one hour"}).json()
    assert r["ok"], r
    assert r["job"]["total_cents"] == 30000
    assert "labour 180.00" in r["readback"] and "pads front 120.00" in r["readback"]


def test_receipt_photo_adds_parts_and_books_the_expense(client):
    img = base64.b64encode(b"\xff\xd8\xff fake jpeg").decode()
    job = client.post("/api/owner/voice", json={"text": "Corolla ABC123, machined rotors, one hour labour"}).json()["job"]
    r = client.post(f"/api/owner/jobs/{job['job_id']}/receipt", json={"image_b64": img}).json()
    assert r["ok"], r
    parts = [l for l in r["job"]["lines"] if l["kind"] == "part"]
    assert len(parts) == 2
    assert r["job"]["total_cents"] == job["total_cents"] + 9460  # at cost, no markup by default
    assert "Added" in r["readback"]
    exp = client.get("/api/money").json()["summary"]
    assert exp["cash_out_cents"] >= 9460


def test_phone_mic_report_is_kept(client):
    r = client.post("/api/owner/diag", json={"event": "error", "detail": {"code": "not-allowed", "by": "press"}}, headers={"user-agent": "iPhone test"})
    assert r.status_code == 200
    last = client.get("/api/owner/diag").json()[-1]
    assert last["event"] == "error" and last["detail"]["code"] == "not-allowed" and last["ua"] == "iPhone test"


def test_recorded_speech_becomes_a_draft(client):
    # mock mode: the server's speech-to-text returns a fixed sentence
    assert client.get("/api/owner/today").json()["stt"] is True
    r = client.post("/api/owner/audio", files={"audio": ("talk.m4a", b"\0" * 4000, "audio/mp4")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "draft" and body["heard"].startswith("Corolla ABC123")
    assert body["job"]["total_cents"] == 35000


def test_empty_recording_is_refused(client):
    r = client.post("/api/owner/audio", files={"audio": ("talk.m4a", b"\0" * 10, "audio/mp4")})
    assert r.status_code == 400


def test_speech_hint_lists_cars_in_the_shop(client):
    from app.api.routes import _cars_in_shop
    from app.db import session_scope

    with session_scope() as s:
        hint = _cars_in_shop(s)
    assert "ABC123" in hint and "1KR9ZZ" in hint


def test_misheard_labour_is_put_back():
    from app.agent.stt import _fix_words

    assert _fix_words("Mazda 1KR9ZZ, oil and filter, label 120.") == "Mazda 1KR9ZZ, oil and filter, labour 120."


def test_stated_totals_come_out_to_the_cent(client):
    """Whatever total he says and whatever parts are on it, the invoice comes to exactly
    that total, its lines add up, and GST is 1/11 of the total."""
    import random

    from sqlmodel import select

    from app import services as svc
    from app.agent.jobcard import _hit_total
    from app.db import session_scope
    from app.models import Job, JobLine, LineKind

    rng = random.Random(7)
    with session_scope() as s:
        job = s.exec(select(Job)).first()
        for i in range(400):
            for l in s.exec(select(JobLine).where(JobLine.job_id == job.id)).all():
                s.delete(l)
            job.stated_total_cents = None
            s.flush()
            parts = [JobLine(job_id=job.id, kind=LineKind.part, description=f"p{k}", qty=rng.choice([1, 1, 2, 4]), unit_cents=rng.randint(100, 9000)) for k in range(rng.randint(0, 3))]
            s.add_all(parts)
            s.flush()
            parts_ex = sum(int(p.qty * p.unit_cents) for p in parts)
            total = rng.randint(parts_ex * 11 // 10 + 200, parts_ex * 11 // 10 + 200_000)
            if i % 4 == 0:
                total -= total % 100  # whole dollars, the way he says it
            labour = JobLine(job_id=job.id, kind=LineKind.labour, description="Labour", qty=1.5, unit_cents=12000) if i % 2 else None
            if labour:
                s.add(labour)
                s.flush()
            assert _hit_total(s, job, labour, "Labour", 1.5, total / 100, labour_fixed=False) == []
            sub, gst, tot = svc.job_totals(s, job)
            lines = s.exec(select(JobLine).where(JobLine.job_id == job.id)).all()
            assert tot == total, (total, sub, gst)
            assert sub + gst == tot and sum(int(l.qty * l.unit_cents) for l in lines) == sub
            assert gst == svc.gst_in(total)


def test_spoken_380_all_up_is_380(client):
    r = client.post("/api/owner/voice", json={"text": "Corolla ABC123 done, front pads, hour and a half, 380 all up"}).json()
    assert r["job"]["total_cents"] == 38000, r["readback"]
    r = client.post("/api/owner/voice", json={"text": "Corolla ABC123 done, front pads, hour and a half, 170 all up"}).json()
    assert r["job"]["total_cents"] == 17000, r["readback"]  # $170 used to come out a cent off


def test_misheard_cars_are_put_back():
    from app.agent.stt import _fix_cars, _fix_words

    def fix(t, hint=""):
        return _fix_words(_fix_cars(t, hint))

    # seen from Parakeet: the make or model is misheard next to a word it got right
    assert fix("Master CX5, Rotors and Labor,$280.") == "Mazda CX-5, Rotors and labour, $280."
    assert fix("Nissan X-ray oil and filter. Send it to Jenny.") == "Nissan X-Trail oil and filter. Send it to Jenny."
    assert fix("Nissan extrail oil and filter.") == "Nissan X-Trail oil and filter."
    # plates said in pieces are joined
    assert fix("Corolla ABC 123. Front pads") == "Corolla ABC123. Front pads"
    assert fix("Mazda 1KR 9ZZ oil", "Cars in the workshop: Mazda CX-5 1KR9ZZ.") == "Mazda 1KR9ZZ oil"
    assert fix("year 2012 and 350 all up") == "year 2012 and 350 all up"
    # names and right words are left alone
    assert fix("Maria's Corolla ABC123, front pads.") == "Maria's Corolla ABC123, front pads."
    assert fix("Toyota Corolla year 2012, master cylinder.") == "Toyota Corolla year 2012, master cylinder."
    # a car only this shop has comes from today's hint
    assert fix("Skoda Octavio front pads", "Cars in the workshop: Skoda Octavia 2AB3CD.") == "Skoda Octavia front pads"


def test_accented_shop_words_are_put_back():
    from app.agent.stt import fix_heard

    hint = "Cars in the workshop: Nissan X-Trail DW4521, Mazda CX-5 1KR9ZZ, Kia Cerato SR2020."
    # heard live on 2026-10-19 from an owner whose first language isn't English
    assert fix_heard("CX-5, taxi and voice.", hint) == "CX-5, tax invoice."
    assert fix_heard("CX-5, Corolla, taxi in voice.", hint) == "CX-5, Corolla, tax invoice."
    assert fix_heard("Nissan X-7.", hint) == "Nissan X-Trail."
    # from the accented test set (scripts/stt_accent_eval.py)
    assert fix_heard("Mark the X trail paid by F-pose.", hint) == "Mark the X-Trail paid by EFTPOS."
    assert fix_heard("Do the invoice for your go DW4521.", hint) == "Do the invoice for rego DW4521."
    assert fix_heard("Front rotors for the Mazda, Rigo 1KR9ZZ.", hint) == "Front rotors for the Mazda, rego 1KR9ZZ."
    assert fix_heard("Logbook service on the Kia Cerrado, two hours later.", hint) == "Logbook service on the Kia Cerato, two hours labour."
    assert fix_heard("The Helix needs a timing belt.", hint) == "The Hilux needs a timing belt."
    assert fix_heard("Roadworthy certificate for the Master CX file.", hint) == "Roadworthy certificate for the Mazda CX-5."
    assert fix_heard("add an extra item to the sin voice", hint) == "add an extra item to the invoice"
    assert fix_heard("Get the inverse for DW4521", hint) == "Get the invoice for DW4521"
    # ordinary words stay
    assert fix_heard("Text the customer, he'll pay later.", hint) == "Text the customer, he'll pay later."
    assert fix_heard("Replaced the brake master cylinder.", hint) == "Replaced the brake master cylinder."
    assert fix_heard("Regal blue Corolla, the rego is ABC123.", hint) == "Regal blue Corolla, the rego is ABC123."


def test_app_page_never_serves_files_outside_the_build(tmp_path):
    from app.main import static_file

    (tmp_path / "static").mkdir()
    (tmp_path / "static" / "manifest.webmanifest").write_text("{}")
    (tmp_path / "secret.env").write_text("KEY=1")
    root = str(tmp_path / "static")
    assert static_file("manifest.webmanifest", root)
    assert static_file("../secret.env", root) is None
    assert static_file("/etc/passwd", root) is None
    assert static_file("", root) is None


def test_paid_car_back_again_gets_a_new_job(client):
    say = lambda t: client.post("/api/owner/voice", json={"text": t}).json()  # noqa: E731
    first = say("Corolla ABC123 done. Front pads, hour and a half labour")
    assert client.post(f"/api/owner/jobs/{first['job']['job_id']}/send").status_code == 200
    aid, t = _approval_link(client)
    client.post(f"/api/approve/{aid}", json={"t": t, "approve": True})
    assert client.post(f"/api/owner/jobs/{first['job']['job_id']}/paid", json={"method": "eftpos"}).status_code == 200
    again = say("Corolla ABC123, replaced the wiper blades, half an hour")
    assert again["kind"] == "draft" and again["job"], again
    assert again["job"]["job_id"] != first["job"]["job_id"] and again["job"]["rego"] == "ABC123"
    assert "Maria" in again["job"]["customer"]
