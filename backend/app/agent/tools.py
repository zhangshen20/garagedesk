"""Tools the Nemotron agents can call. Each tool is a plain function taking a
Session plus keyword args and returning a JSON-serialisable dict. The OpenAI
function schema is declared next to the implementation so they can't drift."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

from sqlmodel import Session, select

from .. import services as svc
from ..config import get_settings
from ..models import (
    Booking,
    BookingStatus,
    Channel,
    Customer,
    Invoice,
    Job,
    JobLine,
    JobStatus,
    LineKind,
    Vehicle,
)
from .parts_lookup import lookup_part_price

ToolFn = Callable[..., dict[str, Any]]
REGISTRY: dict[str, tuple[dict[str, Any], ToolFn]] = {}


def tool(name: str, description: str, params: dict[str, Any], required: list[str] | None = None):
    schema = {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": params, "required": required or []},
        },
    }

    def deco(fn: ToolFn) -> ToolFn:
        REGISTRY[name] = (schema, fn)
        return fn

    return deco


def schemas_for(names: list[str]) -> list[dict[str, Any]]:
    return [REGISTRY[n][0] for n in names]


def run_tool(s: Session, name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name not in REGISTRY:
        return {"error": f"unknown tool {name}"}
    try:
        return REGISTRY[name][1](s, **{k: v for k, v in args.items() if not k.startswith("_")})
    except TypeError as e:
        return {"error": f"bad arguments: {e}"}
    except ValueError as e:
        return {"error": str(e)}


S = {"type": "string"}
I = {"type": "integer"}


# --- shared ---------------------------------------------------------------------------


@tool(
    "find_or_create_customer",
    "Look up a customer by phone or rego; create them (and their vehicle) if new. Always call this before booking.",
    {"name": S, "phone": S, "rego": {**S, "description": "registration plate, if given"}, "vehicle": {**S, "description": "make and model, e.g. 'Toyota Corolla'"}},
    ["name"],
)
def _find_or_create_customer(s: Session, name: str = "", phone: str = "", rego: str = "", vehicle: str = "") -> dict[str, Any]:
    c, v = svc.find_or_create_customer(s, name=name, phone=phone, rego=rego, vehicle=vehicle)
    return {"customer_id": c.id, "name": c.name, "phone": c.phone, "vehicle_id": v.id if v else None, "vehicle": f"{v.make} {v.model} {v.rego}" if v else None, "existing": not c.name.startswith("Unknown")}


@tool(
    "list_availability",
    "List open drop-off times. Days may be 'today', 'tomorrow', a weekday name or YYYY-MM-DD.",
    {"from_day": S, "days": {**I, "description": "how many days to look ahead (default 3)"}},
)
def _list_availability(s: Session, from_day: str = "tomorrow", days: int = 3) -> dict[str, Any]:
    d = svc.parse_day(from_day)
    slots = svc.availability(s, d, max(1, min(int(days or 3), 14)))
    return {"from": d.isoformat(), "slots": slots[:24], "hours": get_settings().shop_hours}


@tool(
    "create_booking",
    "Book a car in. Requires a customer_id from find_or_create_customer and a free slot from list_availability.",
    {"customer_id": I, "vehicle_id": I, "day": S, "start": {**S, "description": "HH:MM 24h"}, "service": S, "notes": S},
    ["customer_id", "day", "start", "service"],
)
def _create_booking(s: Session, customer_id: int, day: str, start: str, service: str, vehicle_id: int | None = None, notes: str | None = None, _source: str = "web") -> dict[str, Any]:
    c = s.get(Customer, int(customer_id))
    if not c:
        return {"error": "customer not found"}
    v = s.get(Vehicle, int(vehicle_id)) if vehicle_id else None
    try:
        b = svc.create_booking(s, customer=c, vehicle=v, day=svc.parse_day(day), start=svc.parse_time(start), service=service, source=_source, notes=notes)
    except ValueError:
        return {"error": "that time is full, offer another slot"}
    return svc.booking_view(s, b)


@tool("find_booking", "Find an upcoming booking by phone or rego.", {"phone": S, "rego": S})
def _find_booking(s: Session, phone: str = "", rego: str = "") -> dict[str, Any]:
    c = svc.find_customer(s, phone=phone, rego=rego)
    if not c:
        return {"found": False}
    b = s.exec(select(Booking).where(Booking.customer_id == c.id, Booking.day >= svc.today(), Booking.status.in_([BookingStatus.requested, BookingStatus.confirmed])).order_by(Booking.day)).first()  # type: ignore[attr-defined]
    return {"found": True, **svc.booking_view(s, b)} if b else {"found": False, "customer": c.name}


@tool("cancel_booking", "Cancel a booking by id.", {"booking_id": I}, ["booking_id"])
def _cancel_booking(s: Session, booking_id: int) -> dict[str, Any]:
    b = s.get(Booking, int(booking_id))
    if not b:
        return {"error": "not found"}
    b.status = BookingStatus.cancelled
    svc.log_event(s, "frontdesk", "booking_cancelled", svc.booking_reference(b), "booking", b.id)
    return {"ok": True, "reference": svc.booking_reference(b)}


@tool("reschedule_booking", "Move a booking to a new day/time.", {"booking_id": I, "day": S, "start": S}, ["booking_id", "day", "start"])
def _reschedule_booking(s: Session, booking_id: int, day: str, start: str) -> dict[str, Any]:
    b = s.get(Booking, int(booking_id))
    if not b:
        return {"error": "not found"}
    d, t = svc.parse_day(day), svc.parse_time(start)
    bay = svc.first_free_bay(s, d, t)
    if bay is None:
        return {"error": "that time is full"}
    b.day, b.start, b.bay = d, t, bay
    svc.log_event(s, "frontdesk", "booking_moved", f"{svc.booking_reference(b)} -> {d} {t}", "booking", b.id)
    return svc.booking_view(s, b)


@tool("get_job_status", "Check progress of a car currently in the workshop by rego or phone.", {"rego": S, "phone": S})
def _get_job_status(s: Session, rego: str = "", phone: str = "") -> dict[str, Any]:
    c = svc.find_customer(s, phone=phone, rego=rego)
    if not c:
        return {"found": False}
    job = s.exec(select(Job).where(Job.customer_id == c.id, Job.status != JobStatus.paid).order_by(Job.created_at.desc())).first()  # type: ignore[attr-defined]
    if not job:
        return {"found": False, "customer": c.name}
    v = s.get(Vehicle, job.vehicle_id) if job.vehicle_id else None
    text = {
        JobStatus.quoted: "waiting for your go-ahead on the quote",
        JobStatus.approved: "booked for work",
        JobStatus.in_progress: "being worked on now",
        JobStatus.waiting_parts: "waiting on a part to arrive",
        JobStatus.done: "finished and ready to collect",
        JobStatus.invoiced: "ready to collect; the invoice has been sent",
    }.get(job.status, job.status.value)
    sub, gst, tot = svc.job_totals(s, job)
    nxt = "We'll text you the moment it's ready." if job.status in (JobStatus.in_progress, JobStatus.waiting_parts) else ""
    return {"found": True, "job_id": job.id, "vehicle": f"{v.make} {v.model}" if v else "car", "status": job.status.value, "status_text": text, "total_cents": tot, "next": nxt}


@tool("shop_info", "Opening hours, address and services offered.", {})
def _shop_info(s: Session) -> dict[str, Any]:
    st = get_settings()
    return {"name": st.shop_name, "address": st.shop_address, "hours": st.shop_hours, "phone": st.shop_phone, "services": ["logbook service", "roadworthy (RWC) inspection", "brakes", "tyres", "clutch", "battery", "diagnostics"]}


@tool("send_sms", "Send an SMS to a customer (confirmations, reminders, 'your car is ready').", {"to": S, "body": S}, ["to", "body"])
def _send_sms(s: Session, to: str, body: str) -> dict[str, Any]:
    from ..channels.transport import send

    ob = send(s, Channel.sms, svc.normalise_phone(to), body)
    return {"ok": True, "outbox_id": ob.id, "delivered": ob.delivered}


# --- back office ----------------------------------------------------------------------


@tool("list_bookings", "Bookings for a day.", {"day": S})
def _list_bookings(s: Session, day: str = "today") -> dict[str, Any]:
    d = svc.parse_day(day)
    bs = s.exec(select(Booking).where(Booking.day == d, Booking.status != BookingStatus.cancelled).order_by(Booking.start)).all()  # type: ignore[attr-defined]
    return {"day": d.isoformat(), "bookings": [svc.booking_view(s, b) for b in bs]}


@tool("list_jobs", "Jobs in the workshop, optionally filtered by status.", {"status": {**S, "enum": [x.value for x in JobStatus]}})
def _list_jobs(s: Session, status: str | None = None) -> dict[str, Any]:
    q = select(Job)
    if status:
        q = q.where(Job.status == JobStatus(status))
    return {"jobs": [svc.job_view(s, j) for j in s.exec(q.order_by(Job.updated_at.desc())).all()[:30]]}  # type: ignore[attr-defined]


@tool("get_job", "Full job card with lines and totals.", {"job_id": I}, ["job_id"])
def _get_job(s: Session, job_id: int) -> dict[str, Any]:
    j = s.get(Job, int(job_id))
    return svc.job_view(s, j) if j else {"error": "not found"}


@tool(
    "add_job_line",
    "Add labour, a part or a fee to a job card. unit_cents is ex-GST.",
    {"job_id": I, "kind": {**S, "enum": ["labour", "part", "fee"]}, "description": S, "qty": {"type": "number"}, "unit_cents": I},
    ["job_id", "kind", "description", "unit_cents"],
)
def _add_job_line(s: Session, job_id: int, kind: str, description: str, unit_cents: int, qty: float = 1) -> dict[str, Any]:
    j = s.get(Job, int(job_id))
    if not j:
        return {"error": "not found"}
    s.add(JobLine(job_id=j.id, kind=LineKind(kind), description=description, qty=float(qty), unit_cents=int(unit_cents)))
    s.flush()
    return svc.job_view(s, j)


@tool("set_job_status", "Move a job card to a new status.", {"job_id": I, "status": {**S, "enum": [x.value for x in JobStatus]}, "note": S}, ["job_id", "status"])
def _set_job_status(s: Session, job_id: int, status: str, note: str | None = None) -> dict[str, Any]:
    j = s.get(Job, int(job_id))
    if not j:
        return {"error": "not found"}
    j.status = JobStatus(status)
    if note:
        j.mechanic_notes = ((j.mechanic_notes or "") + "\n" + note).strip()
    from datetime import datetime

    j.updated_at = datetime.utcnow()
    svc.log_event(s, "backoffice", "job_status", f"job {j.id} -> {status}", "job", j.id)
    return svc.job_view(s, j)


@tool("issue_invoice", "Issue the GST tax invoice for a finished job and send it to the customer.", {"job_id": I}, ["job_id"])
def _issue_invoice(s: Session, job_id: int) -> dict[str, Any]:
    j = s.get(Job, int(job_id))
    if not j:
        return {"error": "not found"}
    inv = svc.issue_and_send_invoice(s, j)
    link = svc.invoice_link(inv)
    return {"number": inv.number, "total_cents": inv.total_cents, "gst_cents": inv.gst_cents, "pdf": link}


@tool("record_payment", "Record a payment against an invoice; issues a receipt when paid in full.", {"invoice_number": S, "amount_cents": I, "method": {**S, "enum": ["eftpos", "card", "cash", "transfer"]}}, ["invoice_number", "amount_cents"])
def _record_payment(s: Session, invoice_number: str, amount_cents: int, method: str = "card") -> dict[str, Any]:
    inv = s.exec(select(Invoice).where(Invoice.number == invoice_number)).first()
    if not inv:
        return {"error": "invoice not found"}
    svc.record_payment(s, inv, int(amount_cents), method)
    return {"number": inv.number, "status": inv.status.value, "receipt": bool(inv.receipt_pdf_path)}


@tool(
    "update_car_status",
    "The owner says how a car is going ('the Hilux is done', 'Mazda waiting on parts till Thursday'). Finds the job from loose words (rego, make, model or customer name), moves it to the new status and texts the customer.",
    {"car": {**S, "description": "words identifying the car, e.g. 'Hilux' or 'Maria's Corolla'"}, "status": {**S, "enum": ["in_progress", "waiting_parts", "done"]}, "message": {**S, "description": "only what the owner actually said for the customer, e.g. 'part arrives Thursday'; leave empty if he said nothing more. Never add dates or details he didn't say."}},
    ["car", "status"],
)
def _update_car_status(s: Session, car: str, status: str, message: str = "") -> dict[str, Any]:
    from .jobcard import match_open_job

    j = match_open_job(s, car)
    if not j:
        return {"error": f"no open job matches '{car}'"}
    j.status = JobStatus(status)
    from datetime import datetime

    j.updated_at = datetime.utcnow()
    v = svc.job_view(s, j)
    first, model = (v["customer"] or "there").split()[0], " ".join(v["vehicle"].split()[:2]) or "car"
    body = {
        "done": f"Hi {first}, your {model} is finished. We'll send the invoice shortly.",
        "waiting_parts": f"Hi {first}, your {model} is waiting on a part.",
        "in_progress": f"Hi {first}, we're working on your {model} now.",
    }[status]
    if message:
        body += f" {message.strip().rstrip('.')}."
    from ..channels.transport import send

    send(s, Channel.sms, v["phone"], f"{body} - {get_settings().shop_trading_name}")
    svc.log_event(s, "owner", "car_status", f"{model} -> {status}", "job", j.id)
    return {"job_id": j.id, "customer": v["customer"], "vehicle": v["vehicle"], "status": status, "texted": v["phone"]}


@tool(
    "mark_paid",
    "Mark a car's invoice paid in full ('Corolla paid on EFTPOS'). Finds the latest unpaid invoice from loose words and texts the customer a receipt.",
    {"car": S, "method": {**S, "enum": ["eftpos", "cash", "transfer"]}},
    ["car"],
)
def _mark_paid(s: Session, car: str, method: str = "eftpos") -> dict[str, Any]:
    from .jobcard import match_open_job

    j = match_open_job(s, car, statuses=[JobStatus.invoiced])
    if not j:
        return {"error": f"no unpaid invoice matches '{car}'"}
    inv = s.exec(select(Invoice).where(Invoice.job_id == j.id, Invoice.status == svc.InvoiceStatus.issued)).first()
    if not inv:
        return {"error": "invoice not found"}
    svc.record_payment(s, inv, inv.total_cents, method)
    return {"number": inv.number, "status": inv.status.value, "method": method, "total_cents": inv.total_cents}


@tool("list_unpaid_invoices", "Outstanding invoices and how overdue they are.", {})
def _list_unpaid(s: Session) -> dict[str, Any]:
    u = svc.unpaid_invoices(s)
    return {"invoices": u, "total_cents": sum(x["total_cents"] for x in u)}


@tool("lookup_part_price", "Find the best price for a part across suppliers (live web search + catalogue).", {"query": S, "vehicle": S}, ["query"])
def _lookup_part_price(s: Session, query: str, vehicle: str = "") -> dict[str, Any]:
    return lookup_part_price(s, query, vehicle)


@tool(
    "order_parts",
    "Draft a purchase order to a supplier. It is NOT sent until the owner approves it on the dashboard.",
    {"supplier_name": S, "items": {"type": "array", "items": {"type": "object", "properties": {"description": S, "qty": I, "unit_cost_cents": I, "part_id": I}, "required": ["description", "qty"]}}, "job_id": I, "message": {**S, "description": "optional custom order text"}},
    ["supplier_name", "items"],
)
def _order_parts(s: Session, supplier_name: str, items: list[dict[str, Any]], job_id: int | None = None, message: str | None = None) -> dict[str, Any]:
    sup = svc.find_supplier(s, supplier_name)
    if not sup:
        from ..models import Supplier

        sup = Supplier(name=supplier_name, order_channel="email", email=f"orders@{supplier_name.lower().replace(' ', '')}.example")
        s.add(sup)
        s.flush()
    job = s.get(Job, int(job_id)) if job_id else None
    po = svc.create_purchase_order(s, supplier=sup, items=items, job=job, message=message)
    view = svc.po_view(s, po)
    a = svc.request_approval(s, kind="purchase_order", title=f"Send parts order PO-{po.id} to {sup.name}", detail=", ".join(f"{l['qty']} x {l['description']}" for l in view["lines"]) + f" (${view['total_cents'] / 100:.2f} ex GST)", ref_table="purchaseorder", ref_id=po.id, payload=view)
    return {"po_id": po.id, "supplier": sup.name, "approval_id": a.id, "status": "awaiting_owner_approval", "total_cents": view["total_cents"]}


@tool("add_expense", "Record a shop expense (rent, consumables, fuel...). amount_cents is what was paid inc GST.", {"description": S, "amount_cents": I, "category": S, "day": S}, ["description", "amount_cents"])
def _add_expense(s: Session, description: str, amount_cents: int, category: str = "general", day: str = "today") -> dict[str, Any]:
    from ..models import Expense

    gst = int(round(amount_cents - amount_cents / (1 + get_settings().gst_rate)))
    e = Expense(day=svc.parse_day(day), description=description, amount_cents=int(amount_cents), gst_cents=gst, category=category)
    s.add(e)
    s.flush()
    return {"expense_id": e.id, "gst_cents": gst}


@tool("money_summary", "Cash in/out and GST collected over a date range.", {"from_day": S, "to_day": S})
def _money_summary(s: Session, from_day: str = "today", to_day: str = "today") -> dict[str, Any]:
    from datetime import datetime, time

    from ..models import Expense, Payment

    a, b = svc.parse_day(from_day), svc.parse_day(to_day)
    pays = s.exec(select(Payment).where(Payment.paid_at >= datetime.combine(a, time.min), Payment.paid_at <= datetime.combine(b, time.max))).all()
    exps = s.exec(select(Expense).where(Expense.day >= a, Expense.day <= b)).all()
    invs = s.exec(select(Invoice).where(Invoice.issued_at >= datetime.combine(a, time.min), Invoice.issued_at <= datetime.combine(b, time.max))).all()
    return {"from": a.isoformat(), "to": b.isoformat(), "cash_in_cents": sum(p.amount_cents for p in pays), "cash_out_cents": sum(e.amount_cents for e in exps), "gst_collected_cents": sum(i.gst_cents for i in invs), "gst_paid_cents": sum(e.gst_cents for e in exps), "invoices_issued": len(invs)}


FRONTDESK_TOOLS = ["shop_info", "find_or_create_customer", "list_availability", "create_booking", "find_booking", "cancel_booking", "reschedule_booking", "get_job_status"]
BACKOFFICE_TOOLS = ["update_car_status", "mark_paid", "list_bookings", "list_jobs", "get_job", "add_job_line", "set_job_status", "issue_invoice", "record_payment", "list_unpaid_invoices", "lookup_part_price", "order_parts", "add_expense", "money_summary", "send_sms", "find_or_create_customer", "list_availability", "create_booking"]


def _unused(*_: Any) -> None:  # keep imports referenced for type checkers
    _ = (json, date, timedelta)
