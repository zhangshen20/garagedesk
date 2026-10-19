"""A working day in the shop, end to end, against the live models: everything the owner
does from his phone, through the same HTTP endpoints the phone uses. Each flow starts
from fresh demo data and a cold start (page reloaded, server restarted, nothing kept in
memory), so nothing passes because of state left over from an earlier step.

    cd backend && .venv/bin/python scripts/owner_day_live.py [flow-name ...] [--audio]

--audio: say each line with the server's own voice and send the recording to
/api/owner/audio, as the phone does, instead of sending the words as text. Needs the
server's speech to text and voice (they are on the VM).
"""

from __future__ import annotations

import base64
import io
import os
import sys
import time
from collections.abc import Callable
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("DATABASE_URL", "sqlite:///./owner-day.db")
os.environ.setdefault("FILES_DIR", "./owner-day-files")
os.environ.setdefault("GARAGEDESK_SCHEDULER", "0")

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.config import get_settings
from app.db import get_engine
from app.models import (
    Approval,
    ApprovalStatus,
    Booking,
    Expense,
    Job,
    Outbox,
    POStatus,
    PurchaseOrder,
)

if not get_settings().nebius_api_key:
    sys.exit("NEBIUS_API_KEY not set")

AUDIO = "--audio" in sys.argv
Check = Callable[[dict[str, Any], Session], str | None]  # None = pass, else what went wrong


# --- the phone ---------------------------------------------------------------------------


class Phone:
    def __init__(self, c: TestClient) -> None:
        self.c = c
        self.timings: list[float] = []

    def cold_start(self) -> dict[str, Any]:
        """The server restarted and he opened the page again: only the database and
        what the server wrote to disk survive."""
        from app.voice import offers

        offers._offer = None
        offers._loaded = False
        return self.c.get("/api/owner/today").json()

    def say(self, text: str) -> dict[str, Any]:
        t0 = time.time()
        if AUDIO:
            from app.voice import tts

            wav = tts.synth(text)
            r = self.c.post("/api/owner/audio", files={"audio": ("talk.wav", wav, "audio/wav")})
        else:
            r = self.c.post("/api/owner/voice", json={"text": text})
        self.timings.append(time.time() - t0)
        if r.status_code != 200:
            return {"kind": "error", "readback": f"HTTP {r.status_code}: {r.text[:200]}"}
        return r.json()

    def today(self) -> dict[str, Any]:
        return self.c.get("/api/owner/today").json()


# --- checks ------------------------------------------------------------------------------


def text_of(r: dict[str, Any]) -> str:
    return f"{r.get('readback') or ''} {r.get('say') or ''}"


def draft(rego: str, total: int | None = None, *, ready: bool = True) -> Check:
    def chk(r: dict[str, Any], s: Session) -> str | None:
        if r.get("kind") != "draft" or not r.get("ok") or not r.get("job"):
            return f"expected a draft for {rego}, got {r.get('kind')} ok={r.get('ok')}"
        if r["job"]["rego"] != rego:
            return f"draft is for {r['job']['rego']}, not {rego}"
        if total is not None and abs(r["job"]["total_cents"] - total) > 1:
            return f"total {r['job']['total_cents']} != {total}"
        if ready and r.get("warnings"):
            return f"draft not ready: {r['warnings']}"
        if ready and (r.get("offer") or {}).get("action") != "send":
            return "no 'send it?' offer on a ready draft"
        return None

    return chk


def kind(k: str) -> Check:
    return lambda r, s: None if r.get("kind") == k else f"expected {k}, got {r.get('kind')}"


def says(*words: str) -> Check:
    """Every one of these words is in what he hears or sees (case-insensitive)."""

    def chk(r: dict[str, Any], s: Session) -> str | None:
        t = text_of(r).lower()
        missing = [w for w in words if w.lower() not in t]
        return f"answer lacks {missing}" if missing else None

    return chk


def says_any(*words: str) -> Check:
    def chk(r: dict[str, Any], s: Session) -> str | None:
        t = text_of(r).lower()
        return None if any(w.lower() in t for w in words) else f"answer mentions none of {list(words)}"

    return chk


def never(*words: str) -> Check:
    def chk(r: dict[str, Any], s: Session) -> str | None:
        t = text_of(r).lower()
        bad = [w for w in words if w.lower() in t]
        return f"answer says {bad}" if bad else None

    return chk


def no_question() -> Check:
    return lambda r, s: "asked him a question it shouldn't need" if "?" in (r.get("readback") or "").replace("Send it?", "").replace("Send the order?", "") else None


def offer(action: str | None) -> Check:
    def chk(r: dict[str, Any], s: Session) -> str | None:
        got = (r.get("offer") or {}).get("action")
        return None if got == action else f"offer is {got}, expected {action}"

    return chk


def job_status(rego: str, *statuses: str) -> Check:
    def chk(r: dict[str, Any], s: Session) -> str | None:
        jobs = [j for j in s.exec(select(Job)).all() if _rego(s, j) == rego]
        latest = max(jobs, key=lambda j: j.updated_at) if jobs else None
        if not latest:
            return f"no job for {rego}"
        return None if latest.status.value in statuses else f"{rego} job is {latest.status.value}, expected {statuses}"

    return chk


def no_new_jobs(before: int) -> Check:
    return lambda r, s: None if len(s.exec(select(Job)).all()) == before else f"jobs went from {before} to {len(s.exec(select(Job)).all())}"


def outbox_has(*words: str) -> Check:
    def chk(r: dict[str, Any], s: Session) -> str | None:
        bodies = [f"{o.subject or ''} {o.body}".lower() for o in s.exec(select(Outbox)).all()]
        return None if any(all(w.lower() in b for w in words) for b in bodies) else f"no message with {list(words)} sent"

    return chk


def _rego(s: Session, j: Job) -> str:
    from app.models import Vehicle

    v = s.get(Vehicle, j.vehicle_id) if j.vehicle_id else None
    return v.rego if v else ""


# --- things he does that aren't talking --------------------------------------------------


def office_approves(c: TestClient, s: Session, approve: bool = True, note: str = "") -> str | None:
    """She taps Approve (or Fix) on the link texted to her."""
    from app import services as svc

    a = s.exec(select(Approval).where(Approval.kind == "invoice", Approval.status == ApprovalStatus.pending).order_by(Approval.id.desc())).first()  # type: ignore[attr-defined]
    if not a:
        return "nothing waiting for the office to approve"
    page = c.get(f"/api/approve/{a.id}", params={"t": svc.approval_token(a)})
    if page.status_code != 200:
        return f"approve page {page.status_code}"
    r = c.post(f"/api/approve/{a.id}", json={"approve": approve, "t": svc.approval_token(a), "note": note or None})
    return None if r.status_code == 200 else f"approve tap {r.status_code}"


def receipt_photo(c: TestClient, job_id: int) -> dict[str, Any]:
    """A supplier receipt, photographed: Burson, one pair of wiper blades, $38.50."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (620, 760), "white")
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 26)
    except OSError:
        font = ImageFont.load_default()
    y = 30
    for line in ["BURSON AUTO PARTS", "Sunshine North VIC", "TAX INVOICE  #448210", "", "Qty  Item                 Amount", "1    Wiper blades pair     $38.50", "", "GST included           $3.50", "TOTAL                  $38.50", "", "EFTPOS  APPROVED"]:
        d.text((30, y), line, fill="black", font=font)
        y += 48
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return c.post(f"/api/owner/jobs/{job_id}/receipt", json={"image_b64": b64, "mime": "image/jpeg"}).json()


# --- the day -----------------------------------------------------------------------------
# Each step: ("say", words, [checks]) | ("cold", None, [checks on /today]) |
# ("do", fn(c, s) -> error | None, []) | ("check", None, [checks on the last answer])

Step = tuple[str, Any, list[Check]]


def _jobs(s: Session) -> int:
    return len(s.exec(select(Job)).all())


FLOWS: dict[str, list[Step]] = {
    # the whole point: replace the phone call to his wife
    "invoice-to-paid": [
        ("cold", None, []),
        ("say", "Corolla ABC123, front pads, hour and a half, 350 all up", [draft("ABC123", 35000), says("Maria", "three hundred and fifty")]),
        ("say", "yep", [kind("done"), says_any("sent to", "invoice sent")]),
        ("cold", None, []),
        ("do", lambda c, s: office_approves(c, s), []),
        ("cold", None, [lambda t, s: None if (t.get("offer") or {}).get("action") == "paid" else f"after the office approved, the phone shows {t.get('offer')}"]),
        ("cold", None, []),  # a redeploy between "approved" and "they've paid"
        ("say", "yes they've paid", [kind("done"), says("paid"), job_status("ABC123", "paid")]),
        ("check", None, [outbox_has("receipt")]),
    ],
    # she sends it back; he fixes it by voice and sends again
    "office-sends-back": [
        ("cold", None, []),
        ("say", "the X-Trail, rear pads, an hour, pads 99", [draft("DW4521")]),
        ("say", "send it", [kind("done")]),
        ("do", lambda c, s: office_approves(c, s, approve=False, note="labour should be an hour and a half"), []),
        ("cold", None, [lambda t, s: None if "sent back" in ((t.get("offer") or {}).get("say") or "") else "phone doesn't say the office sent it back"]),
        ("say", "change the labour on the X-Trail to an hour and a half", [draft("DW4521"), says("hour and a half")]),
        ("say", "send it", [kind("done"), says_any("sent to", "invoice sent")]),
    ],
    # he names no car; the app asks which; he answers with just the car
    "which-car": [
        ("cold", None, []),
        ("say", "do the invoice", [says_any("which", "?"), never("logbook")]),
        ("say", "the Nissan", [draft("DW4521", 24090)]),
        ("say", "yep", [kind("done"), says_any("sent to", "invoice sent")]),
    ],
    "find-yesterday": [
        ("cold", None, []),
        ("say", "find yesterday's jobs and prepare invoice", [draft("DW4521", 24090)]),
        ("say", "what's on the Nissan invoice", [says("X-Trail")]),
        ("say", "take the labour off the Nissan", [draft("DW4521", 10890), never("didn't hear")]),
    ],
    "same-as-last-time": [
        ("cold", None, []),
        ("say", "Liam's Ranger, same as last time", [draft("LOC777", 36600), no_question()]),
    ],
    # a part with no price in the shop's list, covered by his "all up" figure
    "total-covers-the-part": [
        ("cold", None, []),
        ("say", "the Civic, put an oxygen sensor in, hour, 260 all up", [draft("AH5566", 26000), no_question()]),
    ],
    "receipt-photo": [
        ("cold", None, []),
        ("say", "Corolla ABC123, replaced the wiper blades, half an hour", [draft("ABC123", ready=False)]),
        ("do", lambda c, s: None if (r := receipt_photo(c, s.exec(select(Job).where(Job.title.contains("Corolla")).order_by(Job.updated_at.desc())).first().id)).get("ok") else f"receipt: {r.get('readback')}", []),  # type: ignore[union-attr]
        ("check", None, [lambda r, s: None if s.exec(select(Expense).where(Expense.category == "parts")).first() else "receipt not booked as an expense"]),
    ],
    "status-and-questions": [
        ("cold", None, []),
        ("say", "the CX-5 is waiting on parts", [job_status("1KR9ZZ", "waiting_parts"), never("invoice for")]),
        ("say", "is the Hyundai paid", [says("paid"), says_any("i30", "Priya", "Hyundai")]),
        ("say", "what's the Civic in for", [says("check engine"), never("September")]),
        ("say", "which cars haven't been invoiced", [says("X-Trail"), never("invoiced and paid")]),
        ("say", "who owes me money", [says_any("Tom", "Commodore")]),
    ],
    "money-and-day": [
        ("cold", None, []),
        ("say", "what have I got on today", [says_any("Corolla", "Maria"), says_any("Ranger", "Liam")]),
        ("say", "how many cars tomorrow", [says_any("one", "1", "Grace", "Forester")]),
        ("say", "what did we take yesterday", [says("$")]),
        ("say", "how much GST this quarter", [says_any("GST")]),
    ],
    "parts-order": [
        ("cold", None, []),
        ("say", "order front pads for the Kia Cerato", [offer("order"), says("send the order"), never("Corolla")]),
        ("cold", None, [lambda t, s: None if (t.get("offer") or {}).get("action") == "order" else "order offer lost on restart"]),
        ("say", "yes", [kind("done"), says("order sent")]),
        ("check", None, [lambda r, s: None if s.exec(select(PurchaseOrder).where(PurchaseOrder.status == POStatus.sent)).first() else "order not sent to the supplier"]),
    ],
    "booking": [
        ("cold", None, []),
        ("do", lambda c, s: setattr(sys.modules[__name__], "_before", _jobs(s)), []),
        ("say", "book Grace in for Thursday at 9 for a service", [never("tell me what you did"), lambda r, s: None if _jobs(s) == _before else "a booking opened a job"]),
        ("check", None, [lambda r, s: None if len([b for b in s.exec(select(Booking)).all()]) > 0 else "no bookings"]),
    ],
    # "yes" goes to what was just asked, never to a stale offer
    "stale-yes": [
        ("cold", None, []),
        ("say", "the CX-5 is done, roadworthy passed", [draft("1KR9ZZ")]),
        ("say", "what's on today", [kind("reply")]),
        ("say", "yes", [lambda r, s: "a later yes sent an old draft" if s.exec(select(Approval).where(Approval.kind == "invoice", Approval.status == ApprovalStatus.pending)).first() else None, says("send it")]),
        ("say", "send it", [kind("done"), says_any("sent to", "invoice sent")]),
    ],
    "nonsense": [
        ("cold", None, []),
        ("do", lambda c, s: setattr(sys.modules[__name__], "_before", _jobs(s)), []),
        ("say", "blah blah the weather's nice", [lambda r, s: None if _jobs(s) == _before else "nonsense opened a job", offer(None)]),
        ("say", "um", [lambda r, s: None if _jobs(s) == _before else "nonsense opened a job"]),
        ("say", "Corolla", [lambda r, s: None if _jobs(s) == _before else "a bare car name opened a job", never("I didn't hear the labour")]),
    ],
}

_before = 0


def run(name: str, steps: list[Step]) -> list[str]:
    from app.main import app

    fails: list[str] = []
    with TestClient(app) as c:
        c.post("/api/demo/reset")
        phone = Phone(c)
        last: dict[str, Any] = {}
        for i, (what, arg, checks) in enumerate(steps):
            with Session(get_engine()) as s:
                if what == "cold":
                    t = phone.cold_start()
                    errs = [e for chk in checks if (e := chk(t, s))]
                    label = "(page reloaded)"
                elif what == "do":
                    e = arg(c, s)
                    s.commit()
                    errs = [e] if e else []
                    label = "(tap)"
                elif what == "check":
                    errs = [e for chk in checks if (e := chk(last, s))]
                    label = "(check)"
                else:
                    last = phone.say(arg)
                    errs = [e for chk in checks if (e := chk(last, s))]
                    label = f"> {arg}"
                    if last.get("heard") and last["heard"] != arg:
                        label += f"  [heard: {last['heard']}]"
            mark = "ok " if not errs else "FAIL"
            took = f" {phone.timings[-1]:.1f}s" if what == "say" else ""
            print(f"  {mark} {label}{took}")
            if what == "say":
                print(f"       < {(last.get('say') or last.get('readback') or '').replace(chr(10), ' ')[:220]}")
            for e in errs:
                print(f"       ! {e}")
                fails.append(f"{name} step {i + 1} ({arg if isinstance(arg, str) else what}): {e}")
        slow = [t for t in phone.timings if t > 20]
        if slow:
            fails.append(f"{name}: {len(slow)} answer(s) over 20 s ({', '.join(f'{t:.1f}' for t in slow)})")
    return fails


def main() -> None:
    names = [a for a in sys.argv[1:] if not a.startswith("--")] or list(FLOWS)
    fails: list[str] = []
    for n in names:
        print(f"\n{n}")
        fails += run(n, FLOWS[n])
    print(f"\n{len(names) - len({f.split(' ')[0].rstrip(':') for f in fails})}/{len(names)} flows clean")
    for f in fails:
        print(" -", f)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
