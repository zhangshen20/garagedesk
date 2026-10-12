"""What the owner actually says into the phone, and what should happen.

Shared by tests/test_owner_utterances.py (mock models, runs in CI) and
scripts/owner_eval_live.py (the real Nemotron models on Token Factory).

Each case runs against freshly seeded demo data (see app/seed.py, all dates are
relative to today in Melbourne):
  yesterday   Priya Patel  Hyundai i30   XYZ789  logbook service, invoiced and paid
  yesterday   Dan Walker   Nissan X-Trail DW4521 rear brake pads, done, NOT invoiced ($240.90)
  3 days ago  Tom Baker    Holden Commodore TB1234 brakes, invoiced, unpaid (overdue)
  today       Maria Nguyen Toyota Corolla ABC123 front pads, on the hoist ($328.90 so far)
  today       Jack Thompson Mazda CX-5   1KR9ZZ  roadworthy, on the hoist
  today, booked, no job yet: Liam's Ford Ranger LOC777 (battery), Sofia's Kia Cerato
  SR2020 (logbook), Ahmed's Honda Civic AH5566 (check engine light)
  tomorrow    Grace Chen   Subaru Forester GC8899

kind may be a list when either outcome is right ("the Corolla is done" can text
the customer or get the invoice ready).
Fields: say (may hold {dow-N}: the weekday N days ago), before (things said first, for
follow-ups), kind ("draft" shows the invoice with a Send button, "reply" is spoken),
job (rego on the draft), total (inc GST, on the draft), mentions (all must be in the
spoken reply), any (at least one), not (none), tools (the agent must have called each).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

# never acceptable, whatever he said
ALWAYS_NOT = ["in today's jobs", "didn't catch that", "Sorry, something went wrong"]

CASES: list[dict[str, Any]] = [
    # --- invoice a job that's already in the system ----------------------------------
    {"id": "inv-yesterday-shen", "say": "find yesterday's jobs and prepare invoice", "kind": "draft", "job": "DW4521", "total": "240.90"},
    {"id": "inv-yesterday-shen2", "say": "try to find yesterday jobs and prepare invoice", "kind": "draft", "job": "DW4521"},
    {"id": "inv-yesterday-short", "say": "do yesterday's invoice", "kind": "draft", "job": "DW4521"},
    {"id": "inv-model", "say": "invoice the X-Trail", "kind": "draft", "job": "DW4521"},
    {"id": "inv-name-make", "say": "bill Dan for the Nissan", "kind": "draft", "job": "DW4521"},
    {"id": "inv-name", "say": "do the invoice for Dan", "kind": "draft", "job": "DW4521"},
    {"id": "inv-spelled-rego", "say": "do the invoice for rego D W 4 5 2 1", "kind": "draft", "job": "DW4521"},
    {"id": "inv-mumbled", "say": "um yeah the uh nissan from yesterday can you sort the bill out", "kind": "draft", "job": "DW4521"},
    {"id": "inv-today-on-hoist", "say": "can you do the invoice for Maria's Corolla", "kind": "draft", "job": "ABC123", "total": "328.90"},
    {"id": "inv-make", "say": "make the invoice for the Toyota", "kind": "draft", "job": "ABC123"},
    {"id": "inv-misheard", "say": "invoice the Carolla", "kind": "draft", "job": "ABC123"},
    {"id": "inv-cx5", "say": "invoice for the CX-5 please", "kind": "draft", "job": "1KR9ZZ"},
    {"id": "inv-already-paid", "say": "prepare the invoice for the Hyundai from yesterday", "kind": "reply", "mentions": ["paid"], "not": ["couldn't find"]},
    {"id": "inv-already-invoiced", "say": "invoice the Commodore", "kind": "reply", "mentions": ["already invoiced"]},
    {"id": "inv-weekday", "say": "invoice the Holden from {dow-3}", "kind": "reply", "mentions": ["already invoiced"]},
    {"id": "inv-booked-no-work", "say": "do the invoice for the Ranger", "kind": "reply", "mentions": ["Ranger"], "any": ["what you did", "tell me"]},
    {"id": "inv-unknown-car", "say": "invoice the BMW", "kind": "reply", "mentions": ["couldn't"], "any": ["X-Trail", "Corolla", "CX-5"]},
    {"id": "inv-which-one", "say": "do the invoices", "kind": "reply", "mentions": ["X-Trail", "Corolla"], "any": ["which"]},
    {"id": "inv-follow-up", "before": ["do the invoices"], "say": "the Nissan one", "kind": "draft", "job": "DW4521"},
    # --- find and ask about jobs -----------------------------------------------------
    {"id": "find-yesterday", "say": "what did we do yesterday", "kind": "reply", "mentions": ["Hyundai", "X-Trail"]},
    {"id": "find-today", "say": "what jobs have we got on the hoist today", "kind": "reply", "mentions": ["Corolla"]},
    {"id": "find-not-invoiced", "say": "which cars aren't invoiced yet", "kind": "reply", "mentions": ["X-Trail", "Corolla"], "not": ["Hyundai", "Commodore"]},
    {"id": "find-paid", "say": "is the Hyundai paid", "kind": "reply", "mentions": ["paid"]},
    {"id": "find-owing", "say": "who still owes us money", "kind": "reply", "any": ["Tom", "Commodore"]},
    {"id": "find-what-for", "say": "what was the Commodore in for", "kind": "reply", "any": ["brake", "Brake"]},
    {"id": "find-name", "say": "find Priya's job", "kind": "reply", "mentions": ["Hyundai"]},
    {"id": "find-weekday", "say": "what did we do on {dow-3}", "kind": "reply", "mentions": ["Commodore"]},
    {"id": "find-mazda", "say": "what's the Mazda in for", "kind": "reply", "any": ["roadworthy", "Roadworthy", "RWC"]},
    {"id": "find-spelled-rego", "say": "find the job for rego X Y Z seven eight nine", "kind": "reply", "mentions": ["Hyundai"]},
    {"id": "find-unknown", "say": "anything for the Tesla", "kind": "reply", "any": ["couldn't", "no job", "don't have", "nothing", "didn't find", "no tesla"]},
    # --- new work: he says what he did and what to charge ----------------------------
    {"id": "card-demo-line", "say": "Corolla ABC123, front pads, hour and a half, 350 all up", "kind": "draft", "job": "ABC123", "total": "350.00"},
    {"id": "card-labour-amount", "say": "Mazda CX-5 roadworthy done, one hour, labour 165 dollars", "kind": "draft", "job": "1KR9ZZ", "total": "165.00"},
    {"id": "card-from-booking", "say": "Liam's Ranger, new battery 260, half an hour labour", "kind": "draft", "job": "LOC777", "total": "326.00"},
    {"id": "card-total", "say": "Sofia's Cerato logbook service, oil and filter, hour and a half, 280 all up", "kind": "draft", "job": "SR2020", "total": "280.00"},
    {"id": "card-spelled-rego", "say": "Civic A H 5 5 6 6, check engine light, scanned it and cleared the code, 66 all up", "kind": "draft", "job": "AH5566", "total": "66.00"},
    {"id": "card-invoice-with-prices", "say": "invoice the corolla, front pads 120 and labour 180", "kind": "draft", "job": "ABC123", "total": "300.00"},
    {"id": "card-redo-yesterday", "say": "the X-Trail from yesterday, rear pads and a wheel alignment, 300 all up", "kind": "draft", "job": "DW4521", "total": "300.00"},
    {"id": "card-walk-in", "say": "walk-in, Ben Lee, Toyota Hilux rego BEN001, oil change, 150 all up", "kind": "draft", "job": "BEN001", "total": "150.00"},
    # --- status, payments and the rest of the desk -----------------------------------
    {"id": "status-done", "say": "the Corolla is done", "kind": ["reply", "draft"], "any": ["Maria", "Corolla", "invoice", "Invoice"]},
    {"id": "status-parts", "say": "Mazda's waiting on parts", "kind": "reply", "tools": ["update_car_status"], "any": ["Jack", "Mazda", "CX-5"]},
    {"id": "paid-eftpos", "say": "Commodore paid on EFTPOS", "kind": "reply", "tools": ["mark_paid"], "any": ["paid", "Paid"]},
    {"id": "paid-cash-name", "say": "Tom paid cash", "kind": "reply", "tools": ["mark_paid"], "any": ["paid", "Paid"]},
    {"id": "schedule-today", "say": "what's on today", "kind": "reply", "any": ["Ranger", "Liam", "Corolla", "Maria"]},
    {"id": "schedule-tomorrow", "say": "who's coming in tomorrow", "kind": "reply", "any": ["Grace", "Forester"]},
    {"id": "order-parts", "say": "order front pads for the Corolla", "kind": "reply", "tools": ["order_parts"], "any": ["approv", "Approv"]},
    {"id": "expense", "say": "log an expense, 45 dollars for brake cleaner", "kind": "reply", "tools": ["add_expense"]},
    {"id": "money-yesterday", "say": "how much did we take yesterday", "kind": "reply", "tools": ["money_summary"], "any": ["$"]},
]


def render(text: str, today) -> str:  # noqa: ANN001
    for n in range(1, 8):
        text = text.replace(f"{{dow-{n}}}", (today - timedelta(days=n)).strftime("%A"))
    return text


def check(case: dict[str, Any], out: dict[str, Any]) -> list[str]:
    """What's wrong with the outcome, in words. Empty means it passed."""
    problems: list[str] = []
    said = (out.get("readback") or "").replace("\u2019", "'")
    low = said.lower()
    kinds = case["kind"] if isinstance(case["kind"], list) else [case["kind"]]
    if out.get("kind") not in kinds or (out.get("kind") == "draft" and not out.get("ok")):
        problems.append(f"wanted {case['kind']}, got {out.get('kind')} ok={out.get('ok')}")
    job = out.get("job") or {}
    if case.get("job") and (job.get("rego") or "").upper() != case["job"]:
        problems.append(f"wanted job {case['job']}, got {job.get('rego')}")
    if case.get("total") and job:
        # his total can be a cent out: lines are whole cents ex GST, and some
        # GST-inclusive totals (e.g. $280.00) have no whole-cent subtotal
        got = f"{job.get('total_cents', 0) / 100:.2f}"
        if abs(float(got) - float(case["total"])) > 0.011:
            problems.append(f"wanted total {case['total']}, got {got}")
    for m in case.get("mentions", []):
        if m.lower() not in low:
            problems.append(f"reply doesn't mention {m!r}")
    if case.get("any") and not any(m.lower() in low for m in case["any"]):
        problems.append(f"reply mentions none of {case['any']}")
    for m in case.get("not", []) + ALWAYS_NOT:
        if m.lower() in low:
            problems.append(f"reply says {m!r}")
    called = {st["tool"] for st in out.get("steps") or []}
    for t in case.get("tools", []):
        if t not in called:
            problems.append(f"agent didn't call {t} (called {sorted(called) or 'nothing'})")
    return problems


def run_case(case: dict[str, Any]) -> dict[str, Any]:
    """Seed a fresh shop, say the case's words into the owner app and check it."""
    import time

    from sqlalchemy.pool import StaticPool
    from sqlmodel import Session, SQLModel, create_engine

    from app import models  # noqa: F401  (registers the tables)
    from app import services as svc
    from app.agent.owner_app import handle_voice
    from app.seed import seed

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        seed(s)
        s.commit()
        t = svc.today()
        for before in case.get("before", []):
            handle_voice(s, render(before, t))
            s.commit()
        said = render(case["say"], t)
        t0 = time.time()
        try:
            out = handle_voice(s, said)
            s.commit()
        except Exception as e:  # a crash is a failed case, not a stopped run
            out = {"kind": "error", "readback": f"{type(e).__name__}: {e}"}
        out["seconds"] = round(time.time() - t0, 1)
    engine.dispose()
    return {"case": case, "said": said, "out": out, "problems": check(case, out)}
