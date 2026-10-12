"""Run the bundled job-card photos (or your own) through the live pipeline and
score them against the ground truth.

    NEBIUS_API_KEY=... python backend/scripts/jobcard_live_eval.py [photo.jpg ...]

Uses a throwaway in-memory database seeded with the demo shop, so the
"rego already on file" checks behave as in the demo."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("FILES_DIR", "/tmp/garagedesk-eval-files")

from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlmodel import Session, SQLModel, create_engine  # noqa: E402

from app import db, models  # noqa: E402,F401
from app.seed import seed_if_empty  # noqa: E402
from app.vision.jobcard import scan_jobcard  # noqa: E402
from app.vision.reader import SAMPLES_DIR  # noqa: E402
from app.vision.to_job import to_owner_draft  # noqa: E402


def score(d: dict, exp: dict) -> list[str]:
    misses = []
    for k in ("customer_name", "phone", "rego", "odometer_km", "labour_hours"):
        want = exp.get(k)
        got = d[k]["value"]
        if k == "phone" and want:
            want = "+61" + want[1:]
        if k == "customer_name" and d["customer_id"]:
            continue  # replaced by the name on file
        if (want or None) != (got or None):
            misses.append(f"{k}: want {want!r} got {got!r}")
    veh = d["vehicle"]["value"] or {}
    if exp["vehicle"]["make"] != veh.get("make") or exp["vehicle"]["model"].lower() not in (veh.get("model") or "").lower():
        misses.append(f"vehicle: want {exp['vehicle']} got {veh}")
    text = " ".join(str(w["value"]) for w in d["work_done"]).lower()
    misses += [f"work missing {w!r}" for w in exp["work"] if w not in text]
    parts = " ".join(f"{l['description']} {l['raw'] or ''}" for l in d["lines"] if l["kind"] == "part").lower()
    misses += [f"part missing {p!r}" for p in exp["parts"] if p not in parts]
    return misses


def main() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    db._engine = engine
    SQLModel.metadata.create_all(engine)
    paths = [Path(p) for p in sys.argv[1:]] or sorted(SAMPLES_DIR.glob("*.jpg"))
    with Session(engine) as s:
        seed_if_empty(s)
        s.commit()
        for p in paths:
            t = time.monotonic()
            card = scan_jobcard(s, p.read_bytes())
            took = time.monotonic() - t
            owner = to_owner_draft(s, card)
            d = card.model_dump()
            print(f"\n=== {p.name}  ({took:.1f}s, overall {d['overall_confidence']:.0%}, models {d['models']})")
            print("title:", d["title"])
            for k in ("customer_name", "phone", "vehicle", "rego", "odometer_km", "labour_hours", "mechanic", "notes"):
                f = d[k]
                flag = " <- check" if f["needs_check"] else ""
                print(f"  {k:14} {json.dumps(f['value']):40} {f['confidence']:.2f}{flag} {f['note'] or ''}")
            for w in d["work_done"]:
                print(f"  work           {w['value']!r:40} {w['confidence']:.2f}")
            for l in d["lines"]:
                print(f"  line {l['kind']:6} {l['description'][:38]!r:40} qty {l['qty']:g} {l['unit_cents']} {l['confidence']:.2f}")
            print("  owner app says:", owner["readback"])
            truth = p.with_suffix(".json")
            if truth.exists():
                misses = score(d, json.loads(truth.read_text())["expected"])
                print("  score:", "all fields right" if not misses else misses)


if __name__ == "__main__":
    main()
