"""The agent remembers what the owner said and knows the shop's history and the trade."""

from app.agent import knowhow


def _outbox(client):
    return client.get("/api/outbox").json()["outbox"]


def test_send_it_after_a_read_back_sends_that_job(client):
    d = client.post("/api/owner/voice", json={"text": "Corolla ABC123 done, front pads, hour and a half labour"}).json()
    assert d["ok"] and "Send it?" in d["readback"]
    r = client.post("/api/owner/voice", json={"text": "Yep, send it"}).json()
    assert r["kind"] == "follow_up" and r["send"]["status"] == "awaiting_approval"
    assert r["job"]["job_id"] == d["job"]["job_id"]
    assert any("/approve/" in o["body"] for o in _outbox(client))
    # saying it again doesn't send twice
    again = client.post("/api/owner/voice", json={"text": "send it"}).json()
    assert again["kind"] != "follow_up"


def test_send_it_with_nothing_drafted_is_not_guessed(client):
    r = client.post("/api/owner/voice", json={"text": "send it"}).json()
    assert r["kind"] == "reply"
    assert not any("/approve/" in o["body"] for o in _outbox(client))


def test_draft_needing_a_fix_is_not_sent_on_yes(client):
    d = client.post("/api/owner/voice", json={"text": "CX-5 1KR9ZZ done, replaced the wiper blades"}).json()
    assert d["ok"] and d["warnings"]
    r = client.post("/api/owner/voice", json={"text": "yes"}).json()
    assert r["kind"] != "follow_up"


def test_context_carries_turns_focus_and_history(client):
    from app.agent import memory
    from app.db import session_scope

    client.post("/api/owner/voice", json={"text": "Corolla ABC123 done, front pads, hour and a half labour"})
    with session_scope() as s:
        ctx = memory.owner_context(s, "same again for it")
        assert "hour and a half" in ctx  # what he said earlier
        assert "The job he is on now" in ctx and "Maria Nguyen" in ctx
        assert "Logbook service" in ctx  # a past visit from the records
        assert "Maria likes a text" in ctx  # a fact kept for her
        assert "yesterday was" in ctx
        # names, regos spelled out, and misheard models all find the car
        assert memory.mentioned(s, "the ABC 123")[0][1].rego == "ABC123"
        assert memory.mentioned(s, "Liam's ute, the ranger")[0][0].name.startswith("Liam")
        assert memory.mentioned(s, "the cx five")[0][1].rego == "1KR9ZZ"
        # nothing in the prompt can trip the offline model's routing words
        for phrase in ("job card", "classify", "daily report", "supplier receipt"):
            assert phrase not in ctx.lower()


def test_remember_and_recall_tools(client):
    import app.agent.memory_tools  # noqa: F401  registers the tools
    from app.agent.tools import run_tool
    from app.db import session_scope

    with session_scope() as s:
        r = run_tool(s, "remember", {"about": "Jack's CX-5", "fact": "Jack always pays cash"})
        assert r["about"] == "Jack Thompson"
        got = run_tool(s, "recall_customer", {"about": "1KR9ZZ"})
        assert got["found"] and "Jack always pays cash" in got["records"][0]
        assert "Logbook service" in got["records"][0]
        assert run_tool(s, "shop_knowhow", {"topic": "timing belt"})["jobs"]


def test_owner_turns_go_to_todays_transcript(client):
    from sqlmodel import select

    from app.agent import memory
    from app.db import session_scope
    from app.models import Message

    client.post("/api/owner/voice", json={"text": "Corolla ABC123 done, front pads, hour and a half labour"})
    with session_scope() as s:
        conv = memory.owner_conversation(s)
        said = [m.content for m in s.exec(select(Message).where(Message.conversation_id == conv.id)).all()]
        assert any("hour and a half" in m for m in said)


def test_knowhow_understands_shop_talk():
    assert knowhow.cars_in("did the pads on the high lux") == ["Toyota Hilux"]
    assert knowhow.cars_in("eye thirty in bay two") == ["Hyundai i30"]
    names = [s.name for s in knowhow.services_in("front pads and machined the rotors")]
    assert names[0] == "Front brake pads" and "Machine rotors" in names and "Replace rotors" not in names
    k = knowhow.knowhow_for("timing belt on the camry")
    assert "water pump" in k and "$" not in k
    assert knowhow.lookup("what's a rwc")["found"]
