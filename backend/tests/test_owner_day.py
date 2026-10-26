"""Things the owner hits in a working day that don't need the models: the diary and
the money answered from the books, offers that survive a restart, a stale "yes", a
booking that isn't a job, and parts for the right car. The full day against the live
models is scripts/owner_day_live.py."""

from app.voice import offers

DRAFT = "Corolla ABC123 front pads hour and a half 350 all up"


def _say(client, text):
    return client.post("/api/owner/voice", json={"text": text}).json()


def test_whats_on_today_reads_the_diary(client):
    r = _say(client, "what have I got on today")
    assert r["kind"] == "reply"
    for name in ("Maria", "Liam", "Sofia", "Ahmed"):
        assert name in r["readback"]
    assert _say(client, "how many cars tomorrow")["readback"].startswith("One car tomorrow")


def test_money_questions_come_from_the_books(client):
    r = _say(client, "what did we take yesterday")
    assert r["steps"][0]["args"] == {"period": "yesterday"} and "$" in r["readback"]
    r = _say(client, "how much GST this quarter")
    assert "GST this quarter" in r["readback"] and ("to pay" in r["readback"] or "back" in r["readback"])


def test_this_week_starts_on_monday(client):
    from app import services as svc

    a, b = svc.parse_period("this week")
    assert a.weekday() == 0 and b == svc.today()
    a, b = svc.parse_period("last quarter")
    assert a.day == 1 and a.month in (1, 4, 7, 10) and (b - a).days > 80


def test_send_offer_survives_a_restart(client):
    r = _say(client, DRAFT)
    assert r["offer"]["action"] == "send"
    offers._offer, offers._loaded = None, False  # the server restarted
    assert client.get("/api/owner/today").json()["offer"]["action"] == "send"
    assert _say(client, "yep")["readback"].startswith("Sent to")


def test_a_yes_after_other_talk_checks_first(client):
    _say(client, DRAFT)
    _say(client, "what's on today")
    r = _say(client, "yes")
    assert r["kind"] == "done" and "send it" in r["readback"].lower()
    assert not any("/approve/" in o["body"] for o in client.get("/api/outbox").json()["outbox"])
    assert _say(client, "send it")["readback"].startswith("Sent to")


def test_filler_is_not_an_instruction(client):
    r = _say(client, "um")
    assert "didn't catch" in r["readback"]


def test_routing_guards():
    from app.agent.owner_app import _BOOKING, _EDIT, _SAME_AGAIN, _status_from

    assert _BOOKING.search("book Grace in for Thursday at 9 for a service")
    assert not _BOOKING.search("fitted new pads in the Corolla")
    assert _SAME_AGAIN.search("Liam's Ranger, same as last time")
    assert _status_from("which cars haven't been invoiced") == "to_invoice"
    assert _EDIT.search("take the labour off the Nissan")
    assert _EDIT.search("add wiper blades to the CX-5, 45")
    assert not _EDIT.search("Corolla ABC123 front pads hour and a half 350 all up")


def test_parts_for_another_car_are_not_offered(client):
    from app.agent.parts_lookup import _local_matches
    from app.db import session_scope

    with session_scope() as s:
        assert not any("Corolla" in p.name for p in _local_matches(s, "front brake pads", "Kia Cerato"))
        assert any("Corolla" in p.name for p in _local_matches(s, "front brake pads", "Toyota Corolla"))


def test_a_total_covers_a_part_with_no_price(client):
    from app.agent.jobcard import apply_to_job
    from app.db import session_scope
    from app.models import Job

    with session_scope() as s:
        job = s.get(Job, 4)
        warnings = apply_to_job(s, job, {"labour_hours": 1, "labour_description": "Replace O2 sensor", "total_dollars": 260, "parts": [{"name": "Oxygen sensor", "qty": 1, "price_dollars": None}]})
        from app import services as svc

        view = svc.job_view(s, job)
        assert warnings == []
        assert view["total_cents"] == 26000
        assert all(l["unit_cents"] > 0 for l in view["lines"])
        assert "oxygen sensor supplied" in view["lines"][0]["description"]


def test_who_owes_me_is_not_limited_to_a_day_said_earlier(monkeypatch):
    from app.agent import owner_app
    from app.llm import LLMReply

    class Fake:
        def chat(self, *a, **k):
            return LLMReply(content='{"intent": "find", "when": "today", "status": "unpaid"}', model="fake")

    monkeypatch.setattr(owner_app, "get_llm", lambda: Fake())
    before = [{"role": "user", "content": "What have I got on today?"}, {"role": "assistant", "content": "5 cars today."}]
    r = owner_app.route("Who owes me money?", before)
    assert r["status"] == "unpaid" and r["when"] == ""
    assert owner_app.route("Who owes me money from today?", before)["when"] == "today"
