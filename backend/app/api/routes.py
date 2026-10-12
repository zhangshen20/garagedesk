"""Dashboard and chat API. Deliberately plain JSON over REST; the React app and
the demo scripts both use it."""

from __future__ import annotations

import logging
import os
from collections import deque
from datetime import date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from .. import services as svc
from ..agent.backoffice import handle_owner_message
from ..agent.frontdesk import handle_customer_message
from ..agent.report import generate_daily_report
from ..agent.stt import available as stt_available
from ..config import get_settings
from ..db import get_session
from ..models import (
    Approval,
    ApprovalStatus,
    Booking,
    BookingStatus,
    Channel,
    Conversation,
    Customer,
    DailyReport,
    EventLog,
    Invoice,
    InvoiceStatus,
    Job,
    JobLine,
    JobStatus,
    Message,
    Outbox,
    Part,
    PurchaseOrder,
    Supplier,
    Vehicle,
)

router = APIRouter(prefix="/api", tags=["api"])


# --- chat -----------------------------------------------------------------------------


class ChatIn(BaseModel):
    text: str
    session_id: str
    channel: str = "web"  # web | sms | voice (sms/voice here = simulated)


@router.post("/chat/customer")
def chat_customer(body: ChatIn, s: Session = Depends(get_session)) -> dict[str, Any]:
    ch = Channel(body.channel)
    r = handle_customer_message(s, channel=ch, external_id=body.session_id, text=body.text)
    s.commit()
    return {"reply": r.reply, "steps": r.steps, "model": r.model}


class OwnerChatIn(BaseModel):
    text: str


@router.post("/chat/owner")
def chat_owner(body: OwnerChatIn, s: Session = Depends(get_session)) -> dict[str, Any]:
    r = handle_owner_message(s, body.text)
    s.commit()
    return {"reply": r.reply, "steps": r.steps, "model": r.model}


# --- owner app: speak, snap, tap ------------------------------------------------------


class VoiceIn(BaseModel):
    text: str


@router.post("/owner/voice")
def owner_voice(body: VoiceIn, s: Session = Depends(get_session)) -> dict[str, Any]:
    from ..agent.owner_app import handle_voice

    if not body.text.strip():
        raise HTTPException(400, "nothing heard")
    r = handle_voice(s, body.text.strip())
    s.commit()
    return r


# What the owner's phone reports about its microphone (speech API present, Home
# Screen mode, permission, errors), so a "the button doesn't record" report can
# be checked against what the phone actually did. Kept in memory and logged.
_DIAG: deque[dict[str, Any]] = deque(maxlen=300)
_diag_log = logging.getLogger("garagedesk.owner_diag")


class DiagIn(BaseModel):
    event: str
    detail: dict[str, Any] = {}


@router.post("/owner/diag")
def owner_diag(body: DiagIn, request: Request) -> dict[str, bool]:
    entry = {
        "at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "event": body.event[:60],
        "detail": {str(k)[:40]: str(v)[:300] for k, v in list(body.detail.items())[:25]},
        "ua": request.headers.get("user-agent", "")[:200],
    }
    _DIAG.append(entry)
    _diag_log.info("owner diag %s", entry)
    return {"ok": True}


@router.get("/owner/diag")
def owner_diag_list() -> list[dict[str, Any]]:
    return list(_DIAG)[-150:]


@router.post("/owner/audio")
def owner_audio(audio: UploadFile = File(...), s: Session = Depends(get_session)) -> dict[str, Any]:
    """What he said, recorded on the phone; transcribed here, then handled like dictation."""
    from ..agent.owner_app import handle_voice
    from ..agent.stt import transcribe

    data = audio.file.read()
    if len(data) > 15_000_000:
        raise HTTPException(413, "recording too long")
    if len(data) < 800:
        raise HTTPException(400, "nothing heard")
    try:
        text = transcribe(data)
    except RuntimeError as e:
        raise HTTPException(503, str(e)) from None
    except Exception:
        _diag_log.exception("transcribe failed")
        raise HTTPException(422, "couldn't hear that recording") from None
    _diag_log.info("owner audio %d bytes -> %r", len(data), text[:200])
    if not text:
        raise HTTPException(400, "nothing heard")
    r = handle_voice(s, text)
    s.commit()
    return {**r, "transcript": r.get("transcript") or text, "heard": text}


class PhotoIn(BaseModel):
    image_b64: str
    mime: str = "image/jpeg"


@router.post("/owner/photo")
def owner_photo(body: PhotoIn, s: Session = Depends(get_session)) -> dict[str, Any]:
    from ..agent.jobcard import draft_from_text, transcribe_photo

    b64 = body.image_b64.split(",", 1)[-1]  # accept a data: URL too
    if len(b64) > 12_000_000:
        raise HTTPException(413, "photo too large")
    text, vmodel = transcribe_photo(b64, body.mime)
    if not text:
        return {"kind": "draft", "ok": False, "readback": "I couldn't read that photo. Try again with the whole card in view.", "transcript": ""}
    r = draft_from_text(s, text, transcript_model=vmodel)
    s.commit()
    return {"kind": "draft", **r.as_dict()}


def _owner_job_view(s: Session, j: Job) -> dict[str, Any]:
    v = svc.job_view(s, j)
    a = s.exec(select(Approval).where(Approval.kind == "invoice", Approval.ref_id == j.id).order_by(Approval.id.desc())).first()  # type: ignore[attr-defined]
    v["approval"] = {"id": a.id, "status": a.status.value} if a else None
    return v


@router.get("/owner/today")
def owner_today(s: Session = Depends(get_session)) -> dict[str, Any]:
    settings = get_settings()
    open_statuses = [JobStatus.in_progress, JobStatus.waiting_parts, JobStatus.done, JobStatus.approved, JobStatus.invoiced]
    jobs = s.exec(select(Job).where(Job.status.in_(open_statuses)).order_by(Job.updated_at.desc())).all()  # type: ignore[attr-defined]
    today = svc.today()
    waiting = s.exec(select(Booking).where(Booking.day == today, Booking.status.in_([BookingStatus.confirmed, BookingStatus.requested])).order_by(Booking.start)).all()  # type: ignore[attr-defined]
    return {
        "shop": settings.shop_trading_name,
        "owner": settings.owner_name,
        "approver": settings.approver_name,
        "stt": stt_available(),
        "jobs": [_owner_job_view(s, j) for j in jobs],
        "arriving": [svc.booking_view(s, b) for b in waiting if not s.exec(select(Job).where(Job.booking_id == b.id)).first()],
    }


@router.post("/owner/jobs/{job_id}/send")
def owner_send(job_id: int, s: Session = Depends(get_session)) -> dict[str, Any]:
    j = s.get(Job, job_id)
    if not j:
        raise HTTPException(404)
    if not s.exec(select(JobLine).where(JobLine.job_id == j.id)).first():
        raise HTTPException(400, "job card is empty")
    r = svc.request_invoice_approval(s, j)
    s.commit()
    return r


@router.post("/owner/jobs/{job_id}/receipt")
def owner_receipt(job_id: int, body: PhotoIn, s: Session = Depends(get_session)) -> dict[str, Any]:
    from ..agent.jobcard import add_receipt

    j = s.get(Job, job_id)
    if not j:
        raise HTTPException(404)
    if j.status in (JobStatus.invoiced, JobStatus.paid):
        raise HTTPException(400, "job already invoiced")
    b64 = body.image_b64.split(",", 1)[-1]
    if len(b64) > 12_000_000:
        raise HTTPException(413, "photo too large")
    r = add_receipt(s, j, b64, body.mime)
    s.commit()
    return {"kind": "draft", **r.as_dict()}


class PaidIn(BaseModel):
    method: str = "eftpos"


@router.post("/owner/jobs/{job_id}/paid")
def owner_paid(job_id: int, body: PaidIn, s: Session = Depends(get_session)) -> dict[str, Any]:
    inv = s.exec(select(Invoice).where(Invoice.job_id == job_id, Invoice.status == InvoiceStatus.issued)).first()
    if not inv:
        raise HTTPException(404, "no unpaid invoice for that job")
    svc.record_payment(s, inv, inv.total_cents, body.method)
    s.commit()
    return {"number": inv.number, "status": inv.status.value, "method": body.method}


# --- approve page for whoever does the books (link texted to her phone) -----------------


def _checked_approval(s: Session, approval_id: int, t: str) -> Approval:
    import hmac as _hmac

    a = s.get(Approval, approval_id)
    if not a or not _hmac.compare_digest(svc.approval_token(a), t or ""):
        raise HTTPException(404)
    return a


@router.get("/approve/{approval_id}")
def approve_view(approval_id: int, t: str = "", s: Session = Depends(get_session)) -> dict[str, Any]:
    a = _checked_approval(s, approval_id, t)
    out: dict[str, Any] = {**_approval_view(a), "approver": get_settings().approver_name, "shop": get_settings().shop_trading_name}
    if a.kind == "invoice" and a.ref_id:
        j = s.get(Job, a.ref_id)
        out["job"] = svc.job_view(s, j) if j else None
    return out


class ApproveIn(BaseModel):
    t: str
    approve: bool
    note: str | None = None


@router.post("/approve/{approval_id}")
def approve_decide(approval_id: int, body: ApproveIn, s: Session = Depends(get_session)) -> dict[str, Any]:
    a = _checked_approval(s, approval_id, body.t)
    if a.status != ApprovalStatus.pending:
        return _approval_view(a)
    r = svc.decide_approval(s, a, body.approve, note=body.note, actor="approver")
    s.commit()
    return {**_approval_view(a), **r}


# --- demo ----------------------------------------------------------------------------


@router.post("/demo/reset")
def demo_reset() -> dict[str, Any]:
    from ..db import reset_demo_data

    if not get_settings().demo_reset_enabled:
        raise HTTPException(403, "demo reset is turned off")
    reset_demo_data()
    return {"ok": True, "today": svc.today().isoformat()}


# --- overview -------------------------------------------------------------------------


@router.get("/overview")
def overview(s: Session = Depends(get_session)) -> dict[str, Any]:
    today = svc.today()
    bookings = s.exec(select(Booking).where(Booking.day == today, Booking.status != BookingStatus.cancelled).order_by(Booking.start)).all()  # type: ignore[attr-defined]
    approvals = s.exec(select(Approval).where(Approval.status == ApprovalStatus.pending)).all()
    unpaid = svc.unpaid_invoices(s)
    jobs = s.exec(select(Job).where(Job.status.in_([JobStatus.in_progress, JobStatus.waiting_parts, JobStatus.done]))).all()  # type: ignore[attr-defined]
    money = svc.day_snapshot(s, today)
    events = s.exec(select(EventLog).order_by(EventLog.created_at.desc(), EventLog.id.desc())).all()[:25]  # type: ignore[attr-defined]
    settings = get_settings()
    return {
        "shop": {"name": settings.shop_name, "trading_name": settings.shop_trading_name, "address": settings.shop_address, "hours": settings.shop_hours, "bays": settings.bays, "owner": settings.owner_name},
        "llm": {"mode": settings.effective_llm_mode, "fast": settings.model_fast, "main": settings.model_main, "deep": settings.model_deep, "tavily": bool(settings.tavily_api_key), "twilio": settings.twilio_enabled},
        "today": today.isoformat(),
        "bookings_today": [svc.booking_view(s, b) for b in bookings],
        "jobs_open": [svc.job_view(s, j) for j in jobs],
        "approvals_pending": [_approval_view(a) for a in approvals],
        "unpaid": {"count": len(unpaid), "total_cents": sum(u["total_cents"] for u in unpaid)},
        "cash_in_cents": money["cash_in_cents"],
        "cash_out_cents": money["cash_out_cents"],
        "bookings_tomorrow": money["bookings_tomorrow"],
        "events": [{"at": e.created_at.isoformat(), "actor": e.actor, "action": e.action, "detail": e.detail} for e in events],
    }


# --- bookings -------------------------------------------------------------------------


@router.get("/bookings")
def bookings(day: str = "today", days: int = 7, s: Session = Depends(get_session)) -> dict[str, Any]:
    d = svc.parse_day(day)
    bs = s.exec(select(Booking).where(Booking.day >= d, Booking.day < d + timedelta(days=days)).order_by(Booking.day, Booking.start)).all()  # type: ignore[attr-defined]
    return {"from": d.isoformat(), "bookings": [svc.booking_view(s, b) for b in bs], "availability": svc.availability(s, d, days)}


class BookingPatch(BaseModel):
    status: str | None = None
    day: str | None = None
    start: str | None = None


@router.patch("/bookings/{booking_id}")
def patch_booking(booking_id: int, body: BookingPatch, s: Session = Depends(get_session)) -> dict[str, Any]:
    b = s.get(Booking, booking_id)
    if not b:
        raise HTTPException(404)
    if body.status:
        b.status = BookingStatus(body.status)
        if b.status == BookingStatus.checked_in and not s.exec(select(Job).where(Job.booking_id == b.id)).first():
            j = Job(booking_id=b.id, customer_id=b.customer_id, vehicle_id=b.vehicle_id, title=b.service, status=JobStatus.in_progress)
            s.add(j)
            svc.log_event(s, "owner", "job_opened", f"from booking {svc.booking_reference(b)}", "job", None)
    if body.day and body.start:
        b.day, b.start = svc.parse_day(body.day), svc.parse_time(body.start)
    s.commit()
    return svc.booking_view(s, b)


# --- jobs -----------------------------------------------------------------------------


@router.get("/jobs")
def jobs(status: str | None = None, s: Session = Depends(get_session)) -> dict[str, Any]:
    q = select(Job)
    if status:
        q = q.where(Job.status == JobStatus(status))
    return {"jobs": [svc.job_view(s, j) for j in s.exec(q.order_by(Job.updated_at.desc())).all()]}  # type: ignore[attr-defined]


@router.get("/jobs/{job_id}")
def job(job_id: int, s: Session = Depends(get_session)) -> dict[str, Any]:
    j = s.get(Job, job_id)
    if not j:
        raise HTTPException(404)
    return svc.job_view(s, j)


# --- money ----------------------------------------------------------------------------


@router.get("/invoices")
def invoices(s: Session = Depends(get_session)) -> dict[str, Any]:
    out = []
    for inv in s.exec(select(Invoice).order_by(Invoice.issued_at.desc())).all():  # type: ignore[attr-defined]
        c = s.get(Customer, inv.customer_id)
        out.append({"number": inv.number, "customer": c.name if c else "", "job_id": inv.job_id, "subtotal_cents": inv.subtotal_cents, "gst_cents": inv.gst_cents, "total_cents": inv.total_cents, "status": inv.status.value, "issued_at": inv.issued_at.isoformat(), "due": inv.due_at.isoformat() if inv.due_at else None, "pdf": f"/api/invoices/{inv.number}/pdf", "receipt": f"/api/invoices/{inv.number}/receipt" if inv.receipt_pdf_path else None})
    return {"invoices": out}


@router.get("/invoices/{number}/pdf")
def invoice_pdf(number: str, s: Session = Depends(get_session)) -> FileResponse:
    inv = s.exec(select(Invoice).where(Invoice.number == number)).first()
    if not inv or not inv.pdf_path or not os.path.exists(inv.pdf_path):
        raise HTTPException(404)
    return FileResponse(inv.pdf_path, media_type="application/pdf", filename=f"{number}.pdf")


@router.get("/invoices/{number}/receipt")
def receipt_pdf(number: str, s: Session = Depends(get_session)) -> FileResponse:
    inv = s.exec(select(Invoice).where(Invoice.number == number)).first()
    if not inv or not inv.receipt_pdf_path or not os.path.exists(inv.receipt_pdf_path):
        raise HTTPException(404)
    return FileResponse(inv.receipt_pdf_path, media_type="application/pdf", filename=f"{number}-receipt.pdf")


class PaymentIn(BaseModel):
    amount_cents: int
    method: str = "card"


@router.post("/invoices/{number}/payments")
def pay_invoice(number: str, body: PaymentIn, s: Session = Depends(get_session)) -> dict[str, Any]:
    inv = s.exec(select(Invoice).where(Invoice.number == number)).first()
    if not inv:
        raise HTTPException(404)
    svc.record_payment(s, inv, body.amount_cents, body.method)
    s.commit()
    return {"number": inv.number, "status": inv.status.value}


@router.get("/money")
def money(days: int = 30, s: Session = Depends(get_session)) -> dict[str, Any]:
    from ..agent.tools import run_tool

    end = svc.today()
    start = end - timedelta(days=days - 1)
    summary = run_tool(s, "money_summary", {"from_day": start.isoformat(), "to_day": end.isoformat()})
    # per-day series for the dashboard sparkline
    series = []
    for i in range(days):
        d = start + timedelta(days=i)
        snap = svc.day_snapshot(s, d)
        series.append({"day": d.isoformat(), "in": snap["cash_in_cents"], "out": snap["cash_out_cents"]})
    return {"summary": summary, "series": series, "unpaid": svc.unpaid_invoices(s)}


# --- parts & suppliers ----------------------------------------------------------------


@router.get("/parts")
def parts(s: Session = Depends(get_session)) -> dict[str, Any]:
    sups = {x.id: x for x in s.exec(select(Supplier)).all()}
    return {
        "parts": [{"id": p.id, "sku": p.sku, "name": p.name, "supplier": sups[p.supplier_id].name if p.supplier_id in sups else None, "cost_cents": p.cost_cents, "sell_cents": p.sell_cents, "stock": p.stock_qty, "reorder_level": p.reorder_level, "low": p.reorder_level > 0 and p.stock_qty <= p.reorder_level} for p in s.exec(select(Part)).all()],
        "suppliers": [{"id": x.id, "name": x.name, "contact": x.contact_name, "channel": x.order_channel, "email": x.email, "phone": x.phone} for x in sups.values()],
        "purchase_orders": [svc.po_view(s, po) for po in s.exec(select(PurchaseOrder).order_by(PurchaseOrder.created_at.desc())).all()],  # type: ignore[attr-defined]
    }


# --- approvals ------------------------------------------------------------------------


def _approval_view(a: Approval) -> dict[str, Any]:
    return {"id": a.id, "kind": a.kind, "title": a.title, "detail": a.detail, "status": a.status.value, "created_at": a.created_at.isoformat(), "ref_table": a.ref_table, "ref_id": a.ref_id}


@router.get("/approvals")
def approvals(s: Session = Depends(get_session)) -> dict[str, Any]:
    return {"approvals": [_approval_view(a) for a in s.exec(select(Approval).order_by(Approval.created_at.desc())).all()]}  # type: ignore[attr-defined]


class Decision(BaseModel):
    approve: bool


@router.post("/approvals/{approval_id}")
def decide(approval_id: int, body: Decision, s: Session = Depends(get_session)) -> dict[str, Any]:
    a = s.get(Approval, approval_id)
    if not a:
        raise HTTPException(404)
    if a.status != ApprovalStatus.pending:
        return _approval_view(a)
    r = svc.decide_approval(s, a, body.approve)
    s.commit()
    return {**_approval_view(a), **r}


# --- conversations & outbox -----------------------------------------------------------


@router.get("/conversations")
def conversations(s: Session = Depends(get_session)) -> dict[str, Any]:
    out = []
    for c in s.exec(select(Conversation).order_by(Conversation.updated_at.desc())).all()[:50]:  # type: ignore[attr-defined]
        cust = s.get(Customer, c.customer_id) if c.customer_id else None
        last = s.exec(select(Message).where(Message.conversation_id == c.id, Message.role.in_(["user", "assistant"]), Message.content != "").order_by(Message.id.desc())).first()  # type: ignore[attr-defined]
        out.append({"id": c.id, "channel": c.channel.value, "external_id": c.external_id, "customer": cust.name if cust else None, "intent": c.intent, "summary": c.summary, "last": last.content[:140] if last else "", "updated_at": c.updated_at.isoformat()})
    return {"conversations": out}


@router.get("/conversations/{conv_id}")
def conversation(conv_id: int, s: Session = Depends(get_session)) -> dict[str, Any]:
    c = s.get(Conversation, conv_id)
    if not c:
        raise HTTPException(404)
    msgs = s.exec(select(Message).where(Message.conversation_id == c.id).order_by(Message.id)).all()
    return {"id": c.id, "channel": c.channel.value, "external_id": c.external_id, "messages": [{"role": m.role, "content": m.content, "tool": m.tool_name, "tool_calls": m.tool_calls_json, "model": m.model, "at": m.created_at.isoformat()} for m in msgs]}


@router.get("/outbox")
def outbox(s: Session = Depends(get_session)) -> dict[str, Any]:
    return {"outbox": [{"id": o.id, "channel": o.channel.value, "to": o.to, "subject": o.subject, "body": o.body, "delivered": o.delivered, "provider_ref": o.provider_ref, "at": o.created_at.isoformat()} for o in s.exec(select(Outbox).order_by(Outbox.id.desc())).all()[:100]]}  # type: ignore[attr-defined]


# --- reports --------------------------------------------------------------------------


@router.get("/reports")
def reports(s: Session = Depends(get_session)) -> dict[str, Any]:
    return {"reports": [{"day": r.day.isoformat(), "content_md": r.content_md, "model": r.model, "created_at": r.created_at.isoformat()} for r in s.exec(select(DailyReport).order_by(DailyReport.day.desc())).all()]}  # type: ignore[attr-defined]


@router.post("/reports/generate")
def generate_report(day: str = "today", force: bool = True, s: Session = Depends(get_session)) -> dict[str, Any]:
    r = generate_daily_report(s, svc.parse_day(day), force=force)
    s.commit()
    return {"day": r.day.isoformat(), "content_md": r.content_md, "model": r.model}


# --- customers ------------------------------------------------------------------------


@router.get("/customers")
def customers(s: Session = Depends(get_session)) -> dict[str, Any]:
    out = []
    for c in s.exec(select(Customer).order_by(Customer.name)).all():
        vs = s.exec(select(Vehicle).where(Vehicle.customer_id == c.id)).all()
        out.append({"id": c.id, "name": c.name, "phone": c.phone, "email": c.email, "vehicles": [f"{v.year or ''} {v.make} {v.model} ({v.rego})".strip() for v in vs]})
    return {"customers": out}


def _unused() -> None:
    _ = (date, datetime)
