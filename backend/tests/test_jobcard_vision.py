"""Job card photo -> job draft, in mock mode (no key). The bundled sample cards are
read from their ground truth; everything after the vision step is the real code."""

import base64
import io
import json

import pytest
from PIL import Image

from app.vision import normalise as nz
from app.vision.reader import SAMPLES_DIR, parse_json, prepare_image


def _expected(name):
    return json.loads((SAMPLES_DIR / f"{name}.json").read_text())["expected"]


def _card(client, name):
    r = client.post(f"/api/jobcards/samples/{name}/scan")
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.parametrize("name", sorted(p.stem for p in SAMPLES_DIR.glob("*.jpg")))
def test_every_sample_card_reads_to_its_ground_truth(client, name):
    r = _card(client, name)
    d, exp = r["jobcard"], _expected(name)
    assert d["rego"]["value"] == exp["rego"]
    assert d["labour_hours"]["value"] == exp["labour_hours"]
    assert d["odometer_km"]["value"] == exp["odometer_km"]
    if exp["phone"]:
        assert d["phone"]["value"] == "+61" + exp["phone"][1:]
    assert d["vehicle"]["value"]["make"] == exp["vehicle"]["make"]
    assert d["vehicle"]["value"]["model"] == exp["vehicle"]["model"]
    work = " ".join(w["value"] for w in d["work_done"]).lower()
    assert all(w in work for w in exp["work"])
    parts = " ".join(l["description"].lower() for l in d["lines"] if l["kind"] == "part")
    assert all(p in parts for p in exp["parts"])
    assert d["models"]["tidy"] == "rules" and d["photo_id"]
    # and it went through the owner app's pipeline onto a job for that car
    assert r["kind"] == "draft" and r["ok"]
    assert r["job"]["rego"] == exp["rego"]
    labour = [l for l in r["job"]["lines"] if l["kind"] == "labour"]
    assert len(labour) == 1 and labour[0]["qty"] == exp["labour_hours"] and labour[0]["unit_cents"] == 12000


def test_known_customer_matched_and_new_number_read_back(client):
    r = _card(client, "card_neat_service")
    assert r["job"]["customer"] == "Maria Nguyen"
    # a changed mobile is mentioned, but doesn't hold the invoice or overwrite the record
    assert "New number? On file it's 0411 000 001." in r["readback"]
    assert r["warnings"] == [] and r["readback"].endswith("Send it?")
    assert r["job"]["phone"] == "+61411000001"
    priced = {l["description"]: l["unit_cents"] for l in r["job"]["lines"] if l["kind"] == "part"}
    assert priced == {"Oil filter - Toyota": 2500, "Engine oil 5W-30 (5L)": 7500, "Brake pads front - Toyota Corolla": 11900}


def test_rego_on_file_for_someone_else_holds_the_invoice(client):
    r = _card(client, "card_dim_tyres")
    assert any("Priya Patel" in w for w in r["warnings"])
    assert r["readback"].endswith("Say it again with that and I'll fix it.")
    tyre = next(l for l in r["job"]["lines"] if l["kind"] == "part")
    assert tyre["qty"] == 2 and tyre["unit_cents"] == 16500


def test_new_car_opens_a_walk_in_not_someone_elses_job(client):
    """'Patel' and 'Ranger' are on other customers' jobs; the card's rego isn't."""
    before = {j["job_id"] for j in client.get("/api/jobs").json()["jobs"]}
    for name, who in (("card_partial_battery", "J. Patel"), ("card_messy_brakes", "Dave Kowalski")):
        r = _card(client, name)
        assert r["job"]["customer"] == who
        assert r["job"]["job_id"] not in before
    assert r["job"]["phone"] == "+61433908117"  # number from the card saved for the walk-in


def test_new_customer_without_phone_is_asked_for_it(client):
    r = _card(client, "card_partial_battery")
    assert r["jobcard"]["phone"]["needs_check"]
    assert "What's the customer's phone number?" in r["readback"]


def test_ranger_pads_never_priced_as_corolla_pads(client):
    r = _card(client, "card_messy_brakes")
    pads = next(l for l in r["job"]["lines"] if l["kind"] == "part" and "pad" in l["description"].lower())
    assert pads["unit_cents"] == 0 and "Corolla" not in pads["description"]
    assert any("Pads F & R" in w for w in r["warnings"])


def test_upload_photo_and_fetch_it_back(client):
    data = (SAMPLES_DIR / "card_neat_service.jpg").read_bytes()
    url = "data:image/jpeg;base64," + base64.b64encode(data).decode()
    r = client.post("/api/jobcards/scan", json={"image_b64": url})
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] and d["job"]["rego"] == "ABC123"
    img = client.get(f"/api/jobcards/photos/{d['jobcard']['photo_id']}.jpg")
    assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"
    assert client.get("/api/jobcards/photos/../../etc.jpg").status_code == 404


def test_scan_again_replaces_lines_on_the_same_job(client):
    first = _card(client, "card_neat_service")["job"]
    second = _card(client, "card_neat_service")["job"]
    assert first["job_id"] == second["job_id"] and len(second["lines"]) == len(first["lines"])


def test_unreadable_photo_asks_for_a_retake(client):
    buf = io.BytesIO()
    Image.new("RGB", (400, 300), (200, 200, 200)).save(buf, format="JPEG")
    r = client.post("/api/jobcards/scan", json={"image_b64": base64.b64encode(buf.getvalue()).decode()}).json()
    assert not r["ok"] and "couldn't read" in r["readback"].lower()


def test_not_an_image_is_rejected(client):
    r = client.post("/api/jobcards/scan", json={"image_b64": base64.b64encode(b"hello").decode()})
    assert r.status_code == 415
    assert client.post("/api/jobcards/scan", json={"image_b64": "%%%"}).status_code == 400


def test_samples_listed_and_served(client):
    names = client.get("/api/jobcards/samples").json()["samples"]
    assert "card_messy_brakes" in names
    assert client.get(f"/api/jobcards/samples/{names[0]}.jpg").status_code == 200
    assert client.post("/api/jobcards/samples/nope/scan").status_code == 404


def test_written_price_and_paid_on_the_card(client, monkeypatch):
    d = _scan_with(client, monkeypatch, [_reading("a", parts=["Wiper blades $45"], other=["Paid EFTPOS"]), _reading("b", parts=["Wiper blades $45"], other=["Paid EFTPOS"])])
    assert d["paid_method"] == "eftpos"
    wipers = next(l for l in d["job"]["lines"] if l["kind"] == "part")
    assert wipers["unit_cents"] == round(4500 / 1.1)  # written prices include GST


# --- confidence -----------------------------------------------------------------------


def _reading(model, **over):
    r = {
        "model": model, "customer": "Ben Hall", "phone": "0412 000 111", "vehicle": "Kia Rio",
        "rego": "BHX442", "odometer": "", "work_done": ["Oil change"], "parts": ["Oil filter x1"],
        "labour_hours": "1", "mechanic": "", "notes": "", "other": [], "unclear": [], "is_job_card": True,
    }
    r.update(over)
    return r


def _scan_with(client, monkeypatch, readings):
    monkeypatch.setattr("app.vision.jobcard.read_card", lambda original, jpeg: readings)
    data = (SAMPLES_DIR / "card_neat_service.jpg").read_bytes()
    return client.post("/api/jobcards/scan", json={"image_b64": base64.b64encode(data).decode()}).json()


def test_readers_agreeing_means_no_questions(client, monkeypatch):
    d = _scan_with(client, monkeypatch, [_reading("a"), _reading("b")])
    assert d["jobcard"]["rego"]["confidence"] >= 0.9 and not d["jobcard"]["rego"]["needs_check"]
    assert d["jobcard"]["overall_confidence"] >= 0.9
    assert d["job"]["customer"] == "Ben Hall" and d["job"]["phone"] == "+61412000111"


def test_readers_disagreeing_on_rego_holds_the_invoice(client, monkeypatch):
    d = _scan_with(client, monkeypatch, [_reading("a"), _reading("b", rego="8HX442")])
    card = d["jobcard"]
    assert card["rego"]["needs_check"] and card["rego"]["confidence"] < 0.75
    assert any(w.startswith("Rego: B H X 4 4 2") for w in d["warnings"])
    assert card["overall_confidence"] < 0.75


def test_unclear_box_and_bad_phone_lower_confidence(client, monkeypatch):
    d = _scan_with(client, monkeypatch, [_reading("a", phone="0412 00 11", unclear=["labour_hours"]), _reading("b", phone="0412 00 11")])
    card = d["jobcard"]
    assert card["phone"]["needs_check"] and card["phone"]["note"] == "Doesn't look right."
    assert card["labour_hours"]["needs_check"] and "Hard to read" in card["labour_hours"]["note"]
    assert d["job"]["phone"].startswith("unknown")  # a doubtful number is not saved


def test_one_reader_down_still_produces_a_draft(client, monkeypatch):
    d = _scan_with(client, monkeypatch, [_reading("a")])
    assert d["ok"] and d["jobcard"]["rego"]["value"] == "BHX442" and not d["jobcard"]["rego"]["needs_check"]


def test_not_a_job_card(client, monkeypatch):
    d = _scan_with(client, monkeypatch, [_reading("a", is_job_card=False)])
    assert not d["ok"] and "doesn't look like a job card" in d["readback"]


def test_nemotron_tidy_is_used_but_checked(client, monkeypatch):
    """With a key, Nemotron's wording and picks are used, but a part it matches to
    another car's catalogue entry is dropped and a broken phone is not accepted."""
    from app.llm import LLMReply

    class FakeLLM:
        def chat(self, messages, **kw):
            assert kw["tier"] == "main" and kw["json_mode"]
            return LLMReply(
                content="```json\n" + json.dumps({
                    "customer_name": "Ben Hall", "phone": "12", "vehicle": {"make": "Kia", "model": "Rio", "year": None},
                    "rego": "BHX442", "labour_hours": 1, "work_done": ["Engine oil and filter change"],
                    "parts": [{"description": "Brake pads", "qty": 1, "sku": "BP-COR-F", "price_dollars": None}],
                    "title": "Oil change", "paid_method": "cash", "doubts": {},
                }) + "\n```",
                model="nvidia/nemotron-3-super-120b-a12b",
            )

    monkeypatch.setattr("app.llm.get_llm", lambda: FakeLLM())
    from app.db import session_scope
    from app.vision.jobcard import build_draft

    with session_scope() as s:
        d = build_draft(s, [_reading("a"), _reading("b")], use_llm=True)
    assert d.title == "Oil change" and d.paid_method == "cash"
    assert d.work_done[0].value == "Engine oil and filter change"
    assert d.phone.value == "+61412000111"  # Nemotron's "12" failed the check; the card's number stands
    pads = next(l for l in d.lines if l.kind == "part")
    assert pads.sku is None  # Corolla pads don't fit a Kia Rio
    assert d.models["tidy"] == "nvidia/nemotron-3-super-120b-a12b"
    assert d.to_extract()["parts"] == [{"name": "Brake pads", "qty": 1.0, "price_dollars": None}]


# --- parsers --------------------------------------------------------------------------


@pytest.mark.parametrize("raw,want", [
    ("2.5", 2.5), ("1 1/2", 1.5), ("1½", 1.5), ("1h30", 1.5), ("90 min", 1.5),
    ("1hr 30m", 1.5), ("3 hrs", 3.0), ("", None), ("lots", None),
])
def test_hours(raw, want):
    assert nz.hours(raw)[0] == want


def test_phone_rego_odometer_vehicle():
    assert nz.phone("0412 345 678") == ("+61412345678", True)
    assert nz.phone("+61 3 9000 1234") == ("+61390001234", True)
    assert nz.phone("0412 34")[1] is False
    assert nz.rego("1xy 9kl") == ("1XY9KL", True)
    assert nz.rego("ABCDEFGH")[1] is False
    assert nz.odometer("84,210 km") == (84210, True)
    assert nz.odometer("143k") == (143000, True)
    assert nz.vehicle("vw golf 2019") == ({"make": "Volkswagen", "model": "golf", "year": 2019}, True)


def test_price_and_paid():
    assert nz.price("Pads $119") == ("Pads", 119.0)
    assert nz.price("Battery DIN55 x1") == ("Battery DIN55 x1", None)
    assert nz.paid_method(["Paid EFTPOS"]) == "eftpos"
    assert nz.paid_method(["paid by card", "x"]) == "eftpos"
    assert nz.paid_method(["unpaid?"]) == ""


def test_part_line_quantities():
    assert nz.part_line("Oil filter x1") == ("Oil filter", 1.0)
    assert nz.part_line("Tyre 205/55R16 x2") == ("Tyre 205/55R16", 2.0)
    assert nz.part_line("2 x wiper blades") == ("wiper blades", 2.0)
    assert nz.part_line("Engine oil 5W-30 5L") == ("Engine oil 5W-30 5L", 1.0)


def test_parse_json_tolerates_fences_and_chatter():
    assert parse_json('Sure!\n```json\n{"rego": "A1"}\n```') == {"rego": "A1"}
    assert parse_json("no json here") == {}


def test_iphone_rotation_is_applied():
    im = Image.new("RGB", (400, 200), (255, 255, 255))
    exif = Image.Exif()
    exif[0x0112] = 6  # "rotate 90 CW to view", as iPhone portrait shots are stored
    buf = io.BytesIO()
    im.save(buf, format="JPEG", exif=exif)
    out = Image.open(io.BytesIO(prepare_image(buf.getvalue())))
    assert out.size == (200, 400)
