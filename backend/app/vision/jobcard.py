"""Photo of a paper job card -> JobDraft.

  1. Vision models on Token Factory copy the handwriting (reader.py). Two read in
     parallel; agreement between them is the main confidence signal.
  2. NVIDIA Nemotron 3 Super tidies the reading into invoice wording, units and a
     catalogue match for each part. Token Factory has no Nemotron vision model, so
     Nemotron works from the transcription, never the pixels.
  3. Plain checks (phone format, rego shape, sane hours) and the shop's own records
     (rego already on file, number changed) adjust each field's confidence.
  4. Anything under CHECK_BELOW becomes a sentence the owner app reads back."""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from .. import services as svc
from ..config import get_settings
from ..models import Customer, Part, Vehicle
from . import normalise as nz
from .reader import KEYS, prepare_image, read_card
from .schema import CHECK_BELOW, DraftField, DraftLine, JobDraft

log = logging.getLogger(__name__)

SCALARS = [k for k in KEYS if k not in ("work_done", "parts")]

BASE = {"agree": 0.95, "single": 0.8, "disagree": 0.4, "blank": 0.0}
LABELS = {
    "customer_name": "Customer",
    "phone": "Phone",
    "vehicle": "Car",
    "rego": "Rego",
    "odometer_km": "Odometer",
    "labour_hours": "Labour",
    "mechanic": "Mechanic",
    "notes": "Notes",
}
REQUIRED = ("customer_name", "rego", "labour_hours")
# Fields that end up on the invoice or the customer's text; only these are read back.
SPOKEN = ("customer_name", "phone", "vehicle", "rego", "labour_hours")
QUESTIONS = {
    "customer_name": "Who's the customer?",
    "phone": "What's the customer's phone number?",
    "vehicle": "What car is it?",
    "rego": "What's the rego?",
    "labour_hours": "How many hours of labour?",
}


# --------------------------------------------------------------------------------------
# merging the readings
# --------------------------------------------------------------------------------------


def merge(readings: list[dict[str, Any]]) -> dict[str, Any]:
    """Primary model's text per box, plus how the other readers compare."""
    out: dict[str, Any] = {"fields": {}, "lists": {}, "unclear": set()}
    for r in readings:
        out["unclear"].update(r.get("unclear", []))
    for k in SCALARS:
        vals = [r.get(k, "") for r in readings]
        filled = [v for v in vals if v]
        if not filled:
            out["fields"][k] = {"raw": "", "agreement": "blank", "alternatives": []}
            continue
        keys = {nz.canon(v) for v in filled}
        if len(readings) < 2 or len(filled) < len(readings):
            agreement = "single" if len(keys) == 1 else "disagree"
        else:
            agreement = "agree" if len(keys) == 1 else "disagree"
        alts = sorted({v for v in filled if nz.canon(v) != nz.canon(filled[0])})
        out["fields"][k] = {"raw": filled[0], "agreement": agreement, "alternatives": alts}
    for k in ("work_done", "parts"):
        first = next((i for i, r in enumerate(readings) if r.get(k)), None)
        primary = readings[first][k] if first is not None else []
        others = [r.get(k) or [] for i, r in enumerate(readings) if i != first]
        lines = []
        for line in primary:
            if not others:
                agreement = "single"
            elif all(nz.canon(line) in {nz.canon(x) for x in o} for o in others):
                agreement = "agree"
            else:
                agreement = "disagree"
            alts = [x for o in others for x in o if x and nz.canon(x) != nz.canon(line) and _similar(x, line)]
            lines.append({"raw": line, "agreement": agreement, "alternatives": alts})
        out["lists"][k] = lines
    return out


def _similar(a: str, b: str) -> bool:
    from difflib import SequenceMatcher

    return SequenceMatcher(None, nz.canon(a), nz.canon(b)).ratio() > 0.6


# --------------------------------------------------------------------------------------
# tidying: Nemotron 3 Super when there's a key, the plain parsers otherwise
# --------------------------------------------------------------------------------------

TIDY_PROMPT = """You turn a mechanic's handwritten job card (already transcribed) into a clean
job record for an Australian tax invoice. The shop is a small car repair workshop.

Rules:
- Never invent anything that is not on the card. Leave a field null if it is empty.
- Where two readers disagree ("alternatives"), pick the reading that makes sense for a
  car workshop (e.g. Australian phone formats, plate shapes, real car models) and add a
  short reason to "doubts" for that field.
- work_done: one entry per job, rewritten as clear invoice wording the customer
  understands ("F + R pads" -> "Replace front and rear brake pads"). Keep the same
  order and the same number of entries as written lines where you can.
- parts: one entry per written part line. qty is the count of items (5L of oil is 1).
  Set "sku" only if a catalogue part is clearly the same item AND fits this car.
- labour_hours: decimal hours ("1 1/2" -> 1.5).
- title: a short job title for the invoice, under 60 characters.

Reply with JSON only:
{"customer_name": str|null, "phone": str|null, "vehicle": {"make": str, "model": str, "year": int|null}|null,
 "rego": str|null, "odometer_km": int|null, "labour_hours": number|null,
 "work_done": [str], "parts": [{"description": str, "qty": number, "sku": str|null}],
 "mechanic": str|null, "notes": str|null, "title": str, "doubts": {"<field>": "<reason>"}}"""


def tidy_with_nemotron(merged: dict[str, Any], catalogue: list[dict[str, Any]]) -> dict[str, Any] | None:
    from ..llm import get_llm
    from .reader import parse_json

    card = {
        "fields": merged["fields"],
        "work_done_lines": merged["lists"].get("work_done", []),
        "parts_lines": merged["lists"].get("parts", []),
        "hard_to_read": sorted(merged["unclear"]),
    }
    cat = [{"sku": p["sku"], "name": p["name"]} for p in catalogue if p.get("sku")]
    try:
        r = get_llm().chat(
            [
                {"role": "system", "content": TIDY_PROMPT},
                {"role": "user", "content": json.dumps({"card": card, "catalogue": cat})},
            ],
            tier="main",
            json_mode=True,
            max_tokens=3000,
            temperature=0.1,
        )
    except Exception as e:  # noqa: BLE001  fall back to the plain parsers
        log.warning("Nemotron tidy failed: %s", e)
        return None
    out = parse_json(r.content)
    if out:
        out["_model"] = r.model
    return out or None


# --------------------------------------------------------------------------------------
# building the draft
# --------------------------------------------------------------------------------------


def _field(raw: str, agreement: str, value: Any, valid: bool, *, unclear: bool = False, doubt: str | None = None) -> DraftField:
    conf = BASE[agreement] if raw else 0.0
    note = None
    if raw and unclear:
        conf, note = min(conf, 0.55), "Hard to read on the card."
    if agreement == "disagree":
        note = "The two readings of the card don't match."
    if doubt:
        conf, note = min(conf, 0.6), doubt
    if raw and not valid:
        conf, note = min(conf, 0.45), note or "Doesn't look right."
    if value is None and raw:
        conf = min(conf, 0.3)
    return DraftField(value=value, raw=raw or None, confidence=round(conf, 2), note=note)


def _parse(key: str, raw: str) -> tuple[Any, bool]:
    if key == "phone":
        return nz.phone(raw)
    if key == "rego":
        return nz.rego(raw)
    if key == "vehicle":
        return nz.vehicle(raw)
    if key == "odometer":
        return nz.odometer(raw)
    if key == "labour_hours":
        return nz.hours(raw)
    return (raw or None), bool(raw)


def build_draft(s: Session, readings: list[dict[str, Any]], *, use_llm: bool) -> JobDraft:
    merged = merge(readings)
    catalogue = [
        {"id": p.id, "sku": p.sku, "name": p.name, "sell_cents": p.sell_cents}
        for p in s.exec(select(Part)).all()
    ]
    tidy = tidy_with_nemotron(merged, catalogue) if use_llm else None
    doubts: dict[str, str] = {k: str(v) for k, v in ((tidy or {}).get("doubts") or {}).items()}
    unclear = merged["unclear"]
    f = merged["fields"]

    draft = JobDraft()
    key_map = {
        "customer": "customer_name",
        "phone": "phone",
        "vehicle": "vehicle",
        "rego": "rego",
        "odometer": "odometer_km",
        "labour_hours": "labour_hours",
        "mechanic": "mechanic",
        "notes": "notes",
    }
    for src, dst in key_map.items():
        raw, agreement = f[src]["raw"], f[src]["agreement"]
        value, valid = _parse(src, raw)
        # Nemotron's pick wins when it passes the same check (it resolves
        # disagreements and odd handwriting better than the first reader).
        if tidy and tidy.get(dst) not in (None, "", {}):
            t = tidy[dst]
            if dst == "vehicle" and isinstance(t, dict):
                value, valid = {"make": t.get("make") or "", "model": t.get("model") or "", "year": t.get("year")}, bool(t.get("make") and t.get("model"))
            elif dst in ("customer_name", "mechanic", "notes"):
                value, valid = str(t), True
            else:
                tv, tvalid = _parse(src, str(t))
                if tvalid:
                    value, valid = tv, True
        setattr(draft, dst, _field(raw, agreement, value, valid, unclear=src in unclear, doubt=doubts.get(dst)))
    veh = draft.vehicle.value if isinstance(draft.vehicle.value, dict) else None

    # work done
    work_lines = merged["lists"].get("work_done", [])
    tidy_work = [str(x) for x in (tidy or {}).get("work_done") or [] if str(x).strip()]
    if tidy_work:
        same = len(tidy_work) == len(work_lines)
        worst = min((BASE[w["agreement"]] for w in work_lines), default=0.8)
        for i, text in enumerate(tidy_work):
            w = work_lines[i] if same else None
            conf = BASE[w["agreement"]] if w else worst
            draft.work_done.append(
                DraftField(value=text, raw=w["raw"] if w else None, confidence=conf,
                           note="The two readings of the card don't match." if w and w["agreement"] == "disagree" else None)
            )
    else:
        for w in work_lines:
            draft.work_done.append(_field(w["raw"], w["agreement"], w["raw"], True, unclear="work_done" in unclear))

    # parts -> invoice lines
    by_sku = {p["sku"]: p for p in catalogue if p.get("sku")}
    part_lines = merged["lists"].get("parts", [])
    tidy_parts = [p for p in (tidy or {}).get("parts") or [] if isinstance(p, dict) and p.get("description")]
    # (description, qty, as written, catalogue hit, agreement)
    items: list[tuple[str, float, str | None, dict[str, Any] | None, str]] = []
    if tidy_parts:
        same = len(tidy_parts) == len(part_lines)
        for i, p in enumerate(tidy_parts):
            pl = part_lines[i] if same else None
            hit = by_sku.get(p.get("sku") or "")
            # trust Nemotron's sku only if the same fit rule agrees it suits this car
            if hit and nz.match_part(hit["name"].partition(" - ")[0], [hit], veh) is None:
                hit = None
            hit = hit or nz.match_part(str(p["description"]), catalogue, veh)
            try:
                qty = float(p.get("qty") or 1)
            except (TypeError, ValueError):
                qty = 1.0
            items.append((str(p["description"]), qty, pl["raw"] if pl else None, hit, pl["agreement"] if pl else "single"))
    else:
        for pl in part_lines:
            desc, qty = nz.part_line(pl["raw"])
            items.append((desc, qty, pl["raw"], nz.match_part(desc, catalogue, veh), pl["agreement"]))

    hours_v = draft.labour_hours.value
    if draft.work_done or hours_v:
        summary = "; ".join(str(w.value) for w in draft.work_done) or "Workshop labour"
        draft.lines.append(
            DraftLine(kind="labour", description=summary, qty=float(hours_v or 0), raw=draft.labour_hours.raw,
                      confidence=draft.labour_hours.confidence, note=draft.labour_hours.note)
        )
    for desc, qty, raw, hit, agreement in items:
        conf = BASE[agreement]
        note = "The two readings of the card don't match." if agreement == "disagree" else None
        if not hit:
            conf, note = min(conf, 0.6), note or "Not in the parts list, so there's no price for it yet."
        draft.lines.append(
            DraftLine(kind="part", description=hit["name"] if hit else desc, qty=qty, raw=raw,
                      unit_cents=hit["sell_cents"] if hit else None, part_id=hit["id"] if hit else None,
                      sku=hit["sku"] if hit else None, confidence=round(conf, 2), note=note)
        )

    _match_records(s, draft)
    for name in REQUIRED:
        fld: DraftField = getattr(draft, name)
        if fld.value in (None, ""):
            fld.confidence, fld.note = 0.0, "Not on the card."
    if not draft.work_done:
        draft.warnings.append("No work written on the card.")

    title = str((tidy or {}).get("title") or "").strip()
    draft.title = title[:80] if title else ", ".join(str(w.value) for w in draft.work_done)[:60]
    _finish(draft)
    draft.models = {
        "vision": [r.get("model") for r in readings],
        "tidy": (tidy or {}).get("_model") or "rules",
    }
    draft.readings = readings
    return draft


def _match_records(s: Session, d: JobDraft) -> None:
    """Fill gaps and catch conflicts from the shop's own records."""
    v = None
    if d.rego.value:
        v = s.exec(select(Vehicle).where(Vehicle.rego == d.rego.value)).first()
    c = s.get(Customer, v.customer_id) if v else None
    if not c and d.phone.value:
        c = svc.find_customer(s, phone=str(d.phone.value))
    if not c:
        if d.customer_name.value:
            d.customer_name.note = d.customer_name.note or "New customer."
        if not d.phone.value:
            # without a number nobody can text them the invoice or "car is ready"
            d.phone.confidence, d.phone.note = 0.0, "New customer with no number on the card."
            d.phone.raw = ""
        return
    d.customer_id = c.id
    if v:
        d.vehicle_id = v.id
        d.rego.confidence = max(d.rego.confidence, 0.95)  # a plate we already know
        d.rego.note = None
    # name: same surname counts as the same person ("J. Patel" vs "Priya Patel")
    card_name = str(d.customer_name.value or "")
    if not card_name:
        d.customer_name = DraftField(value=c.name, confidence=0.9, note=f"From your records for {d.rego.value}.")
    elif _same_person(card_name, c.name):
        d.customer_name.value = c.name
        d.customer_name.confidence = max(d.customer_name.confidence, 0.9)
        d.customer_name.note = None
    else:
        d.customer_name.confidence = min(d.customer_name.confidence, 0.5)
        d.customer_name.note = f"Rego {d.rego.value} is on file for {c.name}, but the card says {card_name}."
    # phone
    if not d.phone.value:
        d.phone = DraftField(value=c.phone, confidence=0.9, note="From your records.")
    elif nz.canon(d.phone.value) == nz.canon(c.phone):
        d.phone.confidence = max(d.phone.confidence, 0.95)
        d.phone.note = None
    else:
        d.phone.confidence = min(d.phone.confidence, 0.6)
        d.phone.note = f"New number? On file it's {_spoken_phone(c.phone)}."
    # vehicle
    if v and (not d.vehicle.value or not d.vehicle.value.get("make")):
        d.vehicle = DraftField(value={"make": v.make, "model": v.model, "year": v.year}, confidence=0.9, note="From your records.")
    elif v and d.vehicle.value and nz.canon(d.vehicle.value.get("make")) != nz.canon(v.make):
        d.vehicle.confidence = min(d.vehicle.confidence, 0.5)
        d.vehicle.note = f"Rego {v.rego} is a {v.make} {v.model} on file."
    elif v:
        d.vehicle.confidence = max(d.vehicle.confidence, 0.9)
        if d.vehicle.value and not d.vehicle.value.get("year") and v.year:
            d.vehicle.value["year"] = v.year


def _same_person(a: str, b: str) -> bool:
    ta, tb = a.lower().replace(".", " ").split(), b.lower().split()
    if not ta or not tb:
        return False
    if ta[-1] != tb[-1]:
        return False
    return len(ta) == 1 or ta[0][0] == tb[0][0]


def _spoken_phone(p: str) -> str:
    v, _ = nz.phone(p)
    d = "0" + v[3:] if v and v.startswith("+61") else (v or p)
    return f"{d[:4]} {d[4:7]} {d[7:]}" if len(d) == 10 else d


def _spoken(name: str, fld: DraftField) -> str:
    v = fld.value
    if name == "phone" and v:
        return _spoken_phone(str(v))
    if name == "vehicle" and isinstance(v, dict):
        return " ".join(str(x) for x in (v.get("make"), v.get("model"), v.get("year")) if x)
    if name == "rego" and v:
        return " ".join(str(v))
    if name == "labour_hours" and v is not None:
        return f"{v:g} hours"
    if name == "odometer_km" and v is not None:
        return f"{v:,} km"
    return str(v)


def _finish(d: JobDraft) -> None:
    for name in LABELS:
        fld: DraftField = getattr(d, name)
        fld.needs_check = fld.confidence < CHECK_BELOW and (fld.raw is not None or name in REQUIRED)
        if fld.needs_check:
            label = LABELS[name]
            if name not in SPOKEN:
                continue  # flagged in the app, but not worth interrupting him for
            if fld.value in (None, ""):
                d.readback.append(QUESTIONS[name])
            else:
                d.readback.append(f"{label}: {_spoken(name, fld)}. {fld.note or 'Is that right?'}")
    for w in d.work_done:
        w.needs_check = w.confidence < CHECK_BELOW
        if w.needs_check:
            d.readback.append(f"Work: {w.value}. {w.note or 'Is that right?'}")
    for line in d.lines:
        line.needs_check = line.confidence < CHECK_BELOW
        if line.needs_check and line.kind == "part":
            d.readback.append(f"Part: {line.description}. {line.note or 'Is that right?'}")
    key = [getattr(d, n).confidence for n in REQUIRED] + [w.confidence for w in d.work_done]
    d.overall_confidence = round(min(key) if key else 0.0, 2)


# --------------------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------------------


def photos_dir() -> Path:
    p = Path(get_settings().files_dir) / "jobcards"
    p.mkdir(parents=True, exist_ok=True)
    return p


def scan_jobcard(s: Session, original: bytes) -> JobDraft:
    t0 = time.monotonic()
    jpeg = prepare_image(original)
    photo_id = uuid.uuid4().hex[:16]
    (photos_dir() / f"{photo_id}.jpg").write_bytes(jpeg)
    readings = read_card(original, jpeg)
    use_llm = get_settings().effective_llm_mode == "nebius"
    if not readings:
        d = JobDraft(photo_id=photo_id)
        d.warnings.append("Couldn't read the card." + ("" if use_llm else " (mock mode reads only the bundled sample cards)"))
        d.readback.append("I couldn't read that card. Try again with the whole card in the photo and good light.")
        return d
    if not any(r.get("is_job_card", True) for r in readings):
        d = JobDraft(photo_id=photo_id, readings=readings)
        d.warnings.append("That photo doesn't look like a job card.")
        d.readback.append("That doesn't look like a job card. Take a photo of the card itself.")
        return d
    d = build_draft(s, readings, use_llm=use_llm)
    d.photo_id = photo_id
    d.models["seconds"] = round(time.monotonic() - t0, 1)
    svc.log_event(s, "owner", "jobcard_scanned", f"{d.title} ({d.overall_confidence:.0%} sure)")
    return d
