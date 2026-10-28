"""What happens around each read-back: the short version he hears, the next step
offered, and a plain "yes" or "no" acting on that offer."""

from __future__ import annotations

import re
from typing import Any

from sqlmodel import Session, select

from .. import services as svc
from ..agent import memory
from ..models import Approval, ApprovalStatus, Invoice, InvoiceStatus, Job
from . import offers, spoken, tts

# the models write X\u2011Trail and Maria\u2019s; the screen, the checks and the voice want plain text
_PLAIN = str.maketrans({"\u2010": "-", "\u2011": "-", "\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"', "\u00a0": " ", "\u202f": " "})


def plain_text(t: str) -> str:
    return t.translate(_PLAIN)


def with_voice(r: dict[str, Any]) -> dict[str, Any]:
    """Add `say` (what is spoken) and `offer` (the next step) to an owner-app result,
    and start making the audio before the phone asks for it."""
    if r.get("readback"):
        r["readback"] = plain_text(r["readback"])
    job = r.get("job")
    if r.get("kind") == "draft" and r.get("ok") and job:
        warnings = r.get("warnings") or []
        r["say"] = spoken.draft_say(job, warnings)
        if warnings:
            offers.clear()
            r["offer"] = None
        else:
            r["offer"] = offers.put("send", spoken.ask_send(), job_id=job["job_id"])
    else:
        # agent answers can run long on screen; out loud, the first two sentences
        # invoice numbers stay on screen; out loud they're noise
        heard = re.sub(r"\s*\(INV-[\d-]+\)", "", r.get("readback") or "")
        heard = re.sub(r"\s+[\u2013\u2014]\s+", ", ", heard)  # a dash read aloud is a pause
        r.setdefault("say", "\n".join(spoken.sentences(spoken.say_money(heard))[:2]))
        r.setdefault("offer", offers.current())
    r["say_full"] = spoken.say_money(r.get("readback") or "")
    tts.prepare(spoken.sentences(r["say"]))
    return r


def reply_to_offer(s: Session, text: str) -> dict[str, Any] | None:
    """A short yes/no answers the last offer. Anything longer is a new instruction."""
    who = spoken.approver()
    said = offers.answer(text, extra=set(who.lower().split()))
    if not said:
        return None
    # the offer is also kept on disk; failing that, the last clean draft still waits on his yes
    o = offers.current() or (memory.waiting_on_yes(s) if said == "yes" else None)
    since = _turns_since(s, offers.turn()) if offers.current() else []
    if since and since[-1].outcome.rstrip().endswith("?") and since[-1].kind != "draft":
        # the app has asked him something since that offer: "yes" answers the question
        return None
    if o and since and said == "yes" and not _names_action(text, o["action"]):
        # they've talked about other things since: a bare "yes" may not mean this, so
        # say what it would do and let him say it
        return _done(_confirm(s, o), ok=False)
    if said == "no":
        offers.clear()
        if o and o["action"] == "order":
            # "no" means don't send it: take it off the approvals list too
            a = s.get(Approval, o.get("approval_id") or 0)
            if a and a.status == ApprovalStatus.pending:
                svc.decide_approval(s, a, False, note="owner said no", actor="owner")
            return _done("No worries, order cancelled.")
        return _done("No worries." if o else "Okay.")
    if not o or o["action"] == "none":
        offers.clear()
        # "send it" while the draft still has a line with no price: ask for it, don't start over
        held = memory.unpriced_draft(s) if said == "yes" else None
        if held:
            what = " ".join(f"I don't have a price for {m}." for m in held[1])
            ask = "What do you charge for it?" if len(held[1]) == 1 else "What do you charge for them?"
            return _done(f"Not yet. {what} {ask}", ok=False, job=svc.job_view(s, held[0]))
        if "invoice" in text.lower():
            return _done("Which car's invoice?", ok=False)
        return _done("Nothing waiting on a yes. Tell me the car and what you did.", ok=False)
    if o["action"] == "order":
        offers.clear()
        a = s.get(Approval, o.get("approval_id") or 0)
        if not a or a.status != ApprovalStatus.pending:
            return _done("That order's already been dealt with.")
        svc.decide_approval(s, a, True, actor="owner")
        return _done("Order sent.", action="ordered")
    job = s.get(Job, o["job_id"]) if o.get("job_id") else None
    if not job:
        offers.clear()
        return _done("I lost track of that job. Say it again.", ok=False)
    view = svc.job_view(s, job)
    first = spoken.first_name(view["customer"]) or "the customer"
    if o["action"] == "send":
        offers.clear()
        if not view["lines"]:
            return _done("That job has nothing on it yet.", ok=False)
        r = svc.request_invoice_approval(s, job)
        if r["status"] == "sent":
            say = f"Invoice sent to {first}."
        elif r["status"] == "already_invoiced":
            say = "That one's already invoiced."
        else:
            say = f"Sent to {who}."
        return _done(say, job=svc.job_view(s, job), action="sent")
    if o["action"] == "paid":
        offers.clear()
        inv = s.exec(select(Invoice).where(Invoice.job_id == job.id, Invoice.status == InvoiceStatus.issued)).first()
        if not inv:
            return _done("That one's already paid.")
        svc.record_payment(s, inv, inv.total_cents, "eftpos")
        return _done(f"Paid on EFTPOS. Receipt sent to {first}.", job=svc.job_view(s, job), action="paid")
    return None


def _last_turn_id(s: Session) -> int:
    from ..models import OwnerTurn

    last = s.exec(select(OwnerTurn).order_by(OwnerTurn.id.desc())).first()  # type: ignore[union-attr]
    return last.id or 0 if last else 0


def _turns_since(s: Session, turn: int | None) -> list[Any]:
    """What he said after the offer was made (oldest first)."""
    if turn is None:
        return []
    return [t for t in memory.recent_turns(s, 5) if (t.id or 0) > turn]


_ACTION_WORDS = {"send": r"\bsend\b", "order": r"\b(send|order)\b", "paid": r"\bpaid\b"}


def _names_action(text: str, action: str) -> bool:
    return bool(re.search(_ACTION_WORDS.get(action, r"$^"), text, re.I))


def _confirm(s: Session, o: dict[str, Any]) -> str:
    job = s.get(Job, o["job_id"]) if o.get("job_id") else None
    if o["action"] == "send" and job:
        v = svc.job_view(s, job)
        return f"Say 'send it' to send {spoken.first_name(v['customer']) or 'the'}'s {spoken.car_name(v['vehicle'])} to {spoken.approver()}."
    if o["action"] == "paid" and job:
        v = svc.job_view(s, job)
        return f"Say 'paid' when {spoken.first_name(v['customer']) or 'they'} has paid for the {spoken.car_name(v['vehicle'])}."
    if o["action"] == "order":
        return "Say 'send the order' to send that parts order."
    return "Nothing waiting on a yes. Tell me the car and what you did."


def _done(say: str, ok: bool = True, job: dict[str, Any] | None = None, action: str = "") -> dict[str, Any]:
    r = {"kind": "done", "ok": ok, "readback": say, "say": say, "job": job, "action": action, "offer": offers.current()}
    tts.prepare(spoken.sentences(say))
    return r


def after_approval(s: Session, job: Job | None, approved: bool, note: str | None) -> None:
    """The approver tapped. Tell him straight away, and offer the obvious next step."""
    if not job:
        return
    view = svc.job_view(s, job)
    first = spoken.first_name(view["customer"])
    car = f"{first}'s {spoken.car_name(view['vehicle'])}" if first else f"the {spoken.car_name(view['vehicle'])}"
    who = spoken.approver()
    if approved:
        say = f"{who[:1].upper()}{who[1:]} approved {car}. The invoice is with {first or 'the customer'}. Say yes when they've paid on EFTPOS."
        offers.put("paid", say, job_id=job.id, ttl_s=8 * 3600)
        offers.anchor(_last_turn_id(s))
    else:
        say = f"{who[:1].upper()}{who[1:]} sent back {car}" + (f": {note.strip().rstrip('.')}." if note and note.strip() else ".") + " Say it again to fix it."
        offers.put("none", say, job_id=job.id, ttl_s=3600)
        offers.anchor(_last_turn_id(s))
    tts.prepare(spoken.sentences(say))
