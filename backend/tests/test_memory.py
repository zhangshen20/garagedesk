"""The agent remembers what the owner said and knows the shop's history and the trade."""

from app.agent import knowhow


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


def test_knowhow_understands_shop_talk():
    assert knowhow.cars_in("did the pads on the high lux") == ["Toyota Hilux"]
    assert knowhow.cars_in("eye thirty in bay two") == ["Hyundai i30"]
    names = [s.name for s in knowhow.services_in("front pads and machined the rotors")]
    assert names[0] == "Front brake pads" and "Machine rotors" in names and "Replace rotors" not in names
    k = knowhow.knowhow_for("timing belt on the camry")
    assert "water pump" in k and "$" not in k
    assert knowhow.lookup("what's a rwc")["found"]


def test_correction_keeps_what_he_said_before(client):
    from app.agent import memory
    from app.db import session_scope

    client.post("/api/owner/voice", json={"text": "Corolla ABC123 done, front pads, hour and a half labour"})
    r = client.post("/api/owner/voice", json={"text": "actually make it 380 all up"}).json()
    assert r["kind"] == "draft" and r["transcript"] == "actually make it 380 all up"
    with session_scope() as s:
        assert memory.amend_text(s, "add wipers to that").startswith("Corolla ABC123 done")
        assert "380 all up" in memory.amend_text(s, "add wipers to that")
        assert memory.amend_text(s, "what's on today") is None


def _asked(s, said, outcome, kind="reply", described="", job_id=None):
    from app.models import OwnerTurn

    s.add(OwnerTurn(said=said, kind=kind, outcome=outcome, described=described, job_id=job_id))
    s.flush()


def test_answer_to_a_question_carries_on_the_request(client):
    from app.agent import memory
    from app.db import session_scope

    with session_scope() as s:
        _asked(s, "the car is done", "Which car is done, the Corolla or the CX-5?")
        assert memory.answer_text(s, "the CX-5") == "the car is done: the CX-5"
        assert memory.answer_text(s, "Maria's") == "the car is done: Maria's"
        # a fresh ask or a plain no is not an answer
        assert memory.answer_text(s, "what's on today") is None
        assert memory.answer_text(s, "the Hilux is done") is None
        assert memory.answer_text(s, "nah") is None
    with session_scope() as s:
        _asked(s, "the Corolla's done", "Invoice for Maria's Toyota Corolla: labour 198.00. Send it?", kind="draft", job_id=1)
        assert memory.answer_text(s, "the CX-5") is None  # "Send it?" is a yes/no, not a which-car


def test_naming_the_car_finishes_the_job_he_described(client):
    from app.agent import memory
    from app.db import session_scope

    with session_scope() as s:
        _asked(s, "front pads, hour and a half, 350 all up", "I couldn't match which car it was. Say the rego.", kind="draft", described="front pads, hour and a half, 350 all up")
        assert memory.amend_text(s, "the Corolla") == "front pads, hour and a half, 350 all up\nThen he added: the Corolla"


def test_send_before_priced_asks_then_takes_his_price(client):
    from app.db import session_scope
    from app.models import Job, JobLine, LineKind

    with session_scope() as s:
        job = s.get(Job, 1)
        s.add(JobLine(job_id=job.id, kind=LineKind.part, description="Oil filter", qty=1, unit_cents=0))
        _asked(s, "add a filter", "Invoice for Maria's Toyota Corolla: ... I don't have a price for Oil filter. What do you charge for it?", kind="draft", described="Corolla, filter", job_id=job.id)
        s.commit()
    r = client.post("/api/owner/voice", json={"text": "send it"}).json()
    assert r["readback"] == "Not yet. I don't have a price for Oil filter. What do you charge for it?"
    r = client.post("/api/owner/voice", json={"text": "25"}).json()
    assert r["kind"] == "draft" and r["transcript"] == "25"
    filt = [l for l in r["job"]["lines"] if l["description"] == "Oil filter"][0]
    assert filt["unit_cents"] == 2273  # $25.00 inc GST
    assert "oil filter 25.00" in r["readback"] and r["readback"].endswith("Send it?")


def test_new_work_without_a_car_is_not_pinned_to_the_last_job(client):
    from app.agent import memory
    from app.db import session_scope

    client.post("/api/owner/voice", json={"text": "Corolla ABC123 done, front pads, hour and a half labour"})
    took = {"car": "Maria's Corolla", "rego": "ABC123", "customer_name": "Maria Nguyen", "total_dollars": 350}
    with session_scope() as s:
        # the model borrowed the Corolla from memory, but he never named a car
        assert memory.ground_car(s, took, "front pads, hour and a half, 350 all up")["car"] == ""
        assert "The job he is on now" not in memory.owner_context(s, "front pads, 350 all up", for_extract=True)
        # he named it, or pointed back at it: keep it
        assert memory.ground_car(s, took, "the Corolla, 350 all up")["rego"] == "ABC123"
        assert memory.ground_car(s, took, "make it 350 all up for that one")["rego"] == "ABC123"
        assert memory.ground_car(s, took, "GLF222 front pads 350")["rego"] == "ABC123"
        assert memory.ground_car(s, took, "oil change 10W40, 120 all up")["car"] == ""
