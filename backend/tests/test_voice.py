"""What the owner hears: a short read-back, the next step offered, a plain "yes" does it,
and the server voice returns audio any browser can play."""

from urllib.parse import parse_qs, urlparse

from app.voice import offers, spoken


def _approval(client) -> tuple[int, str]:
    body = next(o["body"] for o in client.get("/api/outbox").json()["outbox"] if "/approve/" in o["body"])
    url = urlparse(body[body.index("http"):].split()[0])
    return int(url.path.rsplit("/", 1)[-1]), parse_qs(url.query)["t"][0]


def test_money_and_hours_said_like_a_person():
    assert spoken.dollars(35000) == "three hundred and fifty dollars"
    assert spoken.dollars(21910) == "two hundred and nineteen dollars ten"
    assert spoken.words(1250) == "one thousand two hundred and fifty"
    assert spoken.hours(1.5) == "an hour and a half"
    assert spoken.hours(0.5) == "half an hour"
    assert spoken.sentences("Maria's Corolla. Three hundred and fifty dollars all up. Send it to Jenny?") == [
        "Maria's Corolla.",
        "Three hundred and fifty dollars all up.",
        "Send it to Jenny?",
    ]


def test_short_answers_only():
    assert offers.answer("Yep, send it") == "yes"
    assert offers.answer("send it to Jenny", extra={"jenny"}) == "yes"
    assert offers.answer("nah not yet") == "no"
    # these are new instructions, never a yes to the last offer
    assert offers.answer("send the Hilux") == ""
    assert offers.answer("Corolla done") == ""
    assert offers.answer("done Corolla ABC123 front pads") == ""


def test_draft_is_said_short_then_yes_sends_it(client):
    r = client.post("/api/owner/voice", json={"text": "Corolla ABC123, front pads, hour and a half, 350 all up"}).json()
    assert r["kind"] == "draft" and r["ok"], r
    # the screen keeps every line; out loud it's the car, the work, the money, the next step
    assert "219.10" in r["readback"]
    say = r["say"]
    assert say.startswith("Maria's Corolla.") and "three hundred and fifty dollars all up" in say.lower()
    assert "an hour and a half labour" in say and say.endswith("Send it to the office?")
    assert "219" not in say and len(say) < len(r["readback"]) + 40
    assert r["offer"]["action"] == "send" and r["offer"]["job_id"] == r["job"]["job_id"]

    today = client.get("/api/owner/today").json()
    assert today["offer"]["action"] == "send" and today["tts"] is True

    y = client.post("/api/owner/voice", json={"text": "yep"}).json()
    assert y["kind"] == "done" and y["action"] == "sent" and y["say"] == "Sent to the office."
    assert any("/approve/" in o["body"] for o in client.get("/api/outbox").json()["outbox"])
    # nothing left to say yes to
    again = client.post("/api/owner/voice", json={"text": "yes"}).json()
    assert again["kind"] == "done" and not again["ok"]


def test_no_drops_the_offer(client):
    client.post("/api/owner/voice", json={"text": "Corolla ABC123, front pads, hour and a half, 350 all up"})
    n = client.post("/api/owner/voice", json={"text": "nah"}).json()
    assert n["say"] == "No worries." and client.get("/api/owner/today").json()["offer"] is None
    assert not any("/approve/" in o["body"] for o in client.get("/api/outbox").json()["outbox"])


def test_approval_is_announced_and_yes_marks_it_paid(client):
    job = client.post("/api/owner/voice", json={"text": "Corolla ABC123, front pads, hour and a half, 350 all up"}).json()["job"]
    client.post(f"/api/owner/jobs/{job['job_id']}/send")
    assert client.get("/api/owner/today").json()["offer"] is None
    aid, t = _approval(client)
    client.post(f"/api/approve/{aid}", json={"t": t, "approve": True})
    offer = client.get("/api/owner/today").json()["offer"]
    assert offer["action"] == "paid" and offer["say"].startswith("The office approved Maria's Corolla.")
    p = client.post("/api/owner/voice", json={"text": "yeah they've paid"}).json()
    assert p["action"] == "paid" and p["say"] == "Paid on EFTPOS. Receipt sent to Maria."
    assert any("receipt" in o["body"].lower() or "paid" in o["body"].lower() for o in client.get("/api/outbox").json()["outbox"] if "Maria" in o["body"] or o["to"])


def test_sent_back_is_announced(client):
    job = client.post("/api/owner/voice", json={"text": "Corolla ABC123, front pads, hour and a half, 350 all up"}).json()["job"]
    client.post(f"/api/owner/jobs/{job['job_id']}/send")
    aid, t = _approval(client)
    client.post(f"/api/approve/{aid}", json={"t": t, "approve": False, "note": "pads were 140"})
    offer = client.get("/api/owner/today").json()["offer"]
    assert offer["action"] == "none" and "sent back Maria's Corolla: pads were 140." in offer["say"]


def test_server_voice_returns_wav(client):
    r = client.get("/api/tts", params={"t": "Sent to the office."})
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav"
    assert r.content[:4] == b"RIFF" and r.content[8:12] == b"WAVE"
    assert client.get("/api/tts", params={"t": "x" * 1000}).status_code == 413


def test_server_voice_off_means_browser_voice(client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("TTS_MODE", "off")
    get_settings.cache_clear()
    assert client.get("/api/tts", params={"t": "Hello."}).status_code == 503
    assert client.get("/api/owner/today").json()["tts"] is False


def test_draft_say_leaves_out_part_codes():
    view = {"customer": "Liam O'Connor", "vehicle": "Ford Ranger XYZ789", "total_cents": 36600, "lines": [
        {"kind": "part", "description": "Battery N70ZZ", "qty": 1, "unit_cents": 27273},
        {"kind": "part", "description": "Engine oil 5W-30 (5L)", "qty": 1, "unit_cents": 7500},
        {"kind": "labour", "description": "Labour (0.5 hrs)", "qty": 0.5, "unit_cents": 12000},
    ]}
    said = spoken.draft_say(view, [])
    assert "n70zz" not in said.lower()
    assert said.startswith("Liam's Ranger. Battery, engine oil 5w-30 and half an hour labour.")
