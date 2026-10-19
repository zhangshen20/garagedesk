"""Multi-turn conversations with the owner app against the live Nemotron models: does
the agent carry what he said a moment ago, use the shop's records, and never make up
a price, a customer or a car? Each conversation starts from fresh demo data.

    cd backend && .venv/bin/python scripts/memory_live_eval.py [conversation-number ...]
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("DATABASE_URL", "sqlite:///./memory-eval.db")
os.environ.setdefault("GARAGEDESK_SCHEDULER", "0")

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.config import get_settings
from app.db import get_engine
from app.models import (
    Approval,
    Customer,
    Invoice,
    InvoiceStatus,
    Job,
    JobStatus,
    OwnerFact,
    PurchaseOrder,
    Vehicle,
)

if not get_settings().nebius_api_key:
    sys.exit("NEBIUS_API_KEY not set")

Check = Callable[[dict[str, Any], Session], str | None]  # None = pass, else what went wrong


def lines(r: dict[str, Any]) -> list[dict[str, Any]]:
    return (r.get("job") or {}).get("lines") or []


def draft_for(rego: str, total: int | None = None) -> Check:
    def chk(r: dict[str, Any], s: Session) -> str | None:
        if r.get("kind") != "draft" or not r.get("ok"):
            return f"expected a draft for {rego}, got {r.get('kind')} ok={r.get('ok')}"
        if r["job"]["rego"] != rego:
            return f"draft is for {r['job']['rego']}, not {rego}"
        if total is not None and abs(r["job"]["total_cents"] - total) > 1:
            return f"total {r['job']['total_cents']} != {total}"
        return None

    return chk


def sent(rego: str) -> Check:
    """His invoice went to the approver (or straight out): an invoice approval or an invoice exists for the car's latest job."""

    def chk(r: dict[str, Any], s: Session) -> str | None:
        v = s.exec(select(Vehicle).where(Vehicle.rego == rego)).first()
        j = s.exec(select(Job).where(Job.vehicle_id == v.id).order_by(Job.updated_at.desc())).first() if v else None  # type: ignore[attr-defined]
        if j and (s.exec(select(Approval).where(Approval.kind == "invoice", Approval.ref_id == j.id)).first() or j.status in (JobStatus.invoiced, JobStatus.paid)):
            return None
        return f"not sent: kind={r.get('kind')} {r.get('readback', '')[:80]}"

    return chk


def says(*any_of: str) -> Check:
    def chk(r: dict[str, Any], s: Session) -> str | None:
        text = (r.get("readback") or "").lower()
        return None if any(a.lower() in text for a in any_of) else f"reply lacks any of {any_of}"

    return chk


def says_not(*none_of: str) -> Check:
    def chk(r: dict[str, Any], s: Session) -> str | None:
        text = (r.get("readback") or "").lower()
        bad = [a for a in none_of if a.lower() in text]
        return f"reply says {bad}" if bad else None

    return chk


def db(pred: Callable[[Session], bool], what: str) -> Check:
    return lambda r, s: None if pred(s) else what


def job_status(rego: str, status: JobStatus) -> Check:
    def pred(s: Session) -> bool:
        v = s.exec(select(Vehicle).where(Vehicle.rego == rego)).first()
        j = s.exec(select(Job).where(Job.vehicle_id == v.id).order_by(Job.updated_at.desc())).first() if v else None  # type: ignore[attr-defined]
        return bool(j and j.status == status)

    return db(pred, f"{rego} job not {status.value}")


def labour_hours(h: float) -> Check:
    def chk(r: dict[str, Any], s: Session) -> str | None:
        lab = [l for l in lines(r) if l["kind"] == "labour"]
        if not lab:
            return "no labour line"
        if lab[0]["qty"] == h and lab[0]["unit_cents"] == get_settings().labour_rate_cents:
            return None
        return f"labour {lab[0]['qty']} x {lab[0]['unit_cents']} not {h} hrs at rate"

    return chk


def no_invented_parts(r: dict[str, Any], s: Session) -> str | None:
    bad = [l["description"] for l in lines(r) if l["kind"] == "part"]
    return f"parts he never said: {bad}" if bad else None


def has_part(word: str) -> Check:
    return lambda r, s: None if any(word in l["description"].lower() for l in lines(r) if l["kind"] == "part") else f"no {word} part line"


def priced(word: str) -> Check:
    def chk(r: dict[str, Any], s: Session) -> str | None:
        got = [l for l in lines(r) if word in l["description"].lower()]
        return None if got and all(l["unit_cents"] for l in got) else f"no priced {word} line"

    return chk


def not_draft(r: dict[str, Any], s: Session) -> str | None:
    return None if not (r.get("kind") == "draft" and r.get("ok")) else f"made a draft for {r['job']['rego']} it shouldn't have"


BASE_CUSTOMERS = [0]


def no_new_customer(r: dict[str, Any], s: Session) -> str | None:
    n = len(s.exec(select(Customer)).all()) - BASE_CUSTOMERS[0]
    return None if n == 0 else f"{n} customer(s) invented"


RESTART = "(the app restarts)"  # drops what's held in memory only, as a redeploy would

# Each conversation: a title and turns of (what he says, checks).
CONVERSATIONS: list[tuple[str, list[tuple[str, list[Check]]]]] = [
    ("Correct the total, then send", [
        ("Corolla ABC123, front pads, hour and a half, 350 all up", [draft_for("ABC123", 35000)]),
        ("actually make it 380 all up", [draft_for("ABC123", 38000), has_part("pad")]),
        ("yep send it", [sent("ABC123")]),
    ]),
    ("Status, then invoice 'it', then send", [
        # done means its invoice is got ready from what's on the job (the job-finding thread's design)
        ("the CX-5's done, roadworthy passed", [job_status("1KR9ZZ", JobStatus.done)]),
        ("make the invoice for it, hour of labour, 150 all up", [draft_for("1KR9ZZ", 15000)]),
        ("send it", [sent("1KR9ZZ")]),
    ]),
    ("Same as last time", [
        ("Liam's Ranger, did the battery again, same as last time", [draft_for("LOC777", 36600), has_part("battery")]),
        ("good, send it", [sent("LOC777")]),
    ]),
    ("Customer history questions", [
        ("when was Maria's Corolla last in and what did we do", [says("logbook", "service")]),
        ("what did we charge her for that", [says("308")]),
        ("anything I should tell her next time", [says("pad")]),
    ]),
    ("Remember a fact and use it", [
        ("remember Jack always pays cash", [db(lambda s: bool(s.exec(select(OwnerFact).where(OwnerFact.fact.contains("cash"))).first()), "fact not stored")]),  # type: ignore[attr-defined]
        ("how does Jack usually pay", [says("cash")]),
        ("and what's he driving", [says("cx-5", "cx5", "mazda")]),
    ]),
    ("Misheard car, booked today, part priced by him", [
        ("the civic in for the engine light, scanned it, replaced a coil pack, half hour labour, coil pack 95", [draft_for("AH5566"), has_part("coil")]),
        ("what should I check while it's in", [not_draft, says_not("coil pack 95 dollars")]),
        ("ok send that one", [sent("AH5566")]),
    ]),
    ("Never invents parts, then adds what he says", [
        ("Sofia's Cerato logbook service done, hour and a half", [draft_for("SR2020"), labour_hours(1.5), no_invented_parts]),
        ("add oil and a filter to that", [draft_for("SR2020"), labour_hours(1.5), has_part("oil")]),
        # the filter has no price for a Kia on file: it must ask, not look one up and send
        ("send it", [lambda r, s: None if sent("SR2020")(r, s) else "sent with an unpriced line"]),
    ]),
    ("Unknown car: ask, then use his answer", [
        ("the Golf's done, two hours", [not_draft, no_new_customer]),
        ("rego is GLF222, customer Ben Hall", [draft_for("GLF222"), labour_hours(2)]),
    ]),
    ("Chasing a payment by pronoun", [
        ("has Tom paid for the Commodore yet", [says("not", "unpaid", "owing", "outstanding", "overdue")]),
        ("he just paid on EFTPOS", [db(lambda s: all(i.status == InvoiceStatus.paid for i in s.exec(select(Invoice).where(Invoice.customer_id == 8)).all()), "Tom's invoice not paid")]),
    ]),
    ("Tomorrow's booking and its history", [
        ("is the Forester booked in", [says("tomorrow", (date.today() + timedelta(days=1)).strftime("%A"), "yes")]),
        ("what did we do on it last time", [says("tyre", "alignment")]),
    ]),
    ("Waiting on parts, then order them", [
        ("the Corolla's waiting on front pads", [job_status("ABC123", JobStatus.waiting_parts)]),
        ("order them from whoever's cheapest", [db(lambda s: bool(s.exec(select(PurchaseOrder)).first()), "no purchase order drafted")]),
        ("what did I just ask you to do", [says("pad"), says("order")]),
    ]),
    ("Yesterday, then 'that one' (date lookup is the job-finding thread's fix)", [
        ("what jobs did we finish yesterday", [says("i30", "priya")]),
        ("what did that one come to", [says("$", "dollars")]),
        ("did she pay", [says("paid", "yes", "eftpos")]),
    ]),
    # He answers the question the app just asked with a few words; the request he started carries on.
    ("Which car? Then the car", [
        ("the car is done", []),
        ("the CX-5", [job_status("1KR9ZZ", JobStatus.done)]),
    ]),
    ("Which job? Then the job, then a change", [
        ("update the invoice", [says("which")]),
        ("the Corolla", [draft_for("ABC123")]),
        ("add wipers 45", [draft_for("ABC123"), has_part("pad"), has_part("wiper")]),
    ]),
    ("Which car for the job he described? Then the car", [
        ("front pads, hour and a half, 350 all up", [not_draft, no_new_customer]),
        ("the Corolla", [draft_for("ABC123", 35000), has_part("pad")]),
    ]),
    ("What price? Then the price", [
        ("Sofia's Cerato logbook service done, hour and a half, oil and filter", [draft_for("SR2020")]),
        ("send it", [says("price", "charge")]),
        ("25", [draft_for("SR2020"), labour_hours(1.5), has_part("oil"), priced("filter")]),
        ("yep", [sent("SR2020")]),
    ]),
    ("Which one? 'The first one', then a change", [
        ("update the invoice", [says("which")]),
        ("the first one", [draft_for("ABC123")]),
        ("add wipers 45", [draft_for("ABC123"), labour_hours(1.5), has_part("pad"), has_part("wiper")]),
    ]),
    ("Which one? 'Yesterday's', then his price, then yes after the app restarts", [
        ("update the invoice", [says("which")]),
        ("yesterday's", [draft_for("DW4521")]),
        ("45 for the pads", [draft_for("DW4521", 17700)]),
        (RESTART, []),
        ("yep", [sent("DW4521")]),
    ]),
    ("No car said after talking about another: ask, don't bill the last one", [
        ("find yesterday's jobs and prepare invoice", [draft_for("DW4521")]),
        ("front pads, hour and a half, 350 all up", [not_draft]),
        ("the Corolla", [draft_for("ABC123", 35000), has_part("pad")]),
    ]),
    ("Which car? The rego, spelled out", [
        ("the car is done", []),
        ("A B C 1 2 3", [job_status("ABC123", JobStatus.done)]),
    ]),
    ("Send which one? Then the customer", [
        ("send the invoice", []),
        ("Maria's", [draft_for("ABC123")]),
    ]),
]


def run(selected: set[int]) -> int:
    from app.main import app

    passed = failed = 0
    report: list[str] = []
    with TestClient(app) as c:
        for n, (title, turns) in enumerate(CONVERSATIONS, 1):
            if selected and n not in selected:
                continue
            c.post("/api/demo/reset")
            with Session(get_engine()) as s0:
                BASE_CUSTOMERS[0] = len(s0.exec(select(Customer)).all())
            print(f"\n##### {n}. {title}")
            for said, checks in turns:
                if said == RESTART:
                    from app.voice import offers

                    offers.clear()
                    print(f"  {RESTART}")
                    continue
                t0 = time.time()
                r = c.post("/api/owner/voice", json={"text": said}).json()
                dt = time.time() - t0
                print(f"  OWNER: {said}")
                tools = [st["tool"] for st in r.get("steps") or []]
                print(f"  AGENT [{r.get('kind')} {dt:.1f}s {'+'.join(tools)}]: {(r.get('readback') or '')[:300]}")
                with Session(get_engine()) as s:
                    for chk in checks:
                        err = chk(r, s)
                        if err:
                            failed += 1
                            print(f"    FAIL: {err}")
                            report.append(f"{n}. {title} / '{said}': {err}")
                        else:
                            passed += 1
    print(f"\n{passed} checks passed, {failed} failed")
    for line in report:
        print("  -", line)
    print(json.dumps({"passed": passed, "failed": failed}))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run({int(a) for a in sys.argv[1:]}))
