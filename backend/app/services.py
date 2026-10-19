"""Business logic the agents and the API share. No LLM calls in here."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlmodel import Session, select

from .config import get_settings
from .models import (
    Approval,
    ApprovalStatus,
    Booking,
    BookingStatus,
    Channel,
    Customer,
    EventLog,
    Expense,
    Invoice,
    InvoiceStatus,
    Job,
    JobLine,
    JobStatus,
    Outbox,
    Part,
    Payment,
    POLine,
    POStatus,
    PurchaseOrder,
    Supplier,
    Vehicle,
)

OPEN_HOURS = [time(8, 0), time(9, 0), time(10, 0), time(11, 0), time(13, 0), time(14, 0), time(15, 0), time(16, 0)]
CLOSED_WEEKDAYS = {6}  # Sunday


def today() -> date:
    return datetime.now(ZoneInfo(get_settings().shop_timezone)).date()


_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_NUMBERS = {"one": 1, "a": 1, "an": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7}


def parse_day(value: str | date | None, *, past: bool = False) -> date:
    """A day as people say it, in the shop's time zone. `past` decides what a bare
    weekday means: "Friday" is the coming Friday for a booking (past=False) and the
    Friday just gone when he's asking about work already done (past=True)."""
    if isinstance(value, date):
        return value
    v = re.sub(r"[^a-z0-9/\- ]", "", (value or "today").strip().lower().replace("'s", ""))
    v = re.sub(r"\s+", " ", v).strip()
    t = today()
    if v in ("", "today", "this morning", "this arvo", "this afternoon", "tonight", "now", "earlier", "earlier today", "this evening"):
        return t
    if v in ("yesterday", "yday", "last night", "yesterday morning", "yesterday afternoon", "yesterday arvo"):
        return t - timedelta(days=1)
    if v in ("day before yesterday", "the day before yesterday"):
        return t - timedelta(days=2)
    if v == "tomorrow":
        return t + timedelta(days=1)
    m = re.fullmatch(r"(\d+|one|two|three|four|five|six|seven|a|an) days? ago", v)
    if m:
        n = int(m.group(1)) if m.group(1).isdigit() else _NUMBERS[m.group(1)]
        return t - timedelta(days=n)
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m", "%d %B %Y", "%d %b %Y", "%d %B", "%d %b"):
        try:
            d = datetime.strptime(v, fmt).date()
            if d.year == 1900:
                d = d.replace(year=t.year)
                if past and d > t:
                    d = d.replace(year=t.year - 1)
                elif not past and d < t:
                    d = d.replace(year=t.year + 1)
            return d
        except ValueError:
            continue
    m = re.fullmatch(r"(last|this|next|on|this past|past)? ?([a-z]+?)(?: just gone| gone)?", v)
    if m and len(m.group(2)) >= 3:
        word, lead = m.group(2), (m.group(1) or "")
        for i, name in enumerate(_WEEKDAYS):
            if name.startswith(word[:3]) and (name.startswith(word) or word.startswith(name[:3])):
                back = lead in ("last", "past", "this past") or v.endswith("gone") or (past and lead not in ("next",))
                d = t
                if back:
                    d -= timedelta(days=1)
                    while d.weekday() != i:
                        d -= timedelta(days=1)
                else:
                    d += timedelta(days=1)
                    while d.weekday() != i:
                        d += timedelta(days=1)
                return d
    raise ValueError(f"Unrecognised date: {value!r}")


def utc_bounds(a: date, b: date) -> tuple[datetime, datetime]:
    """Start of day a to end of day b in the shop's time zone, as naive UTC (how
    timestamps are stored)."""
    tz, utc = ZoneInfo(get_settings().shop_timezone), ZoneInfo("UTC")
    lo = datetime.combine(a, time.min, tzinfo=tz).astimezone(utc).replace(tzinfo=None)
    hi = datetime.combine(b, time.max, tzinfo=tz).astimezone(utc).replace(tzinfo=None)
    return lo, hi


def parse_period(value: str | None) -> tuple[date, date]:
    """A day or a span ("this week", "last week", "the last few days"), inclusive."""
    v = re.sub(r"\s+", " ", (value or "").strip().lower())
    t = today()
    monday = t - timedelta(days=t.weekday())
    if v in ("this week", "the week"):
        return monday, t
    if v in ("last week", "the week before"):
        return monday - timedelta(days=7), monday - timedelta(days=1)
    if v in ("last few days", "the last few days", "past few days", "recently", "lately", "this past week", "past week", "the past week", "last 7 days"):
        return t - timedelta(days=7), t
    if v in ("this month", "the month", "month to date"):
        return t.replace(day=1), t
    if v in ("last month", "the month before"):
        end = t.replace(day=1) - timedelta(days=1)
        return end.replace(day=1), end
    q_start = date(t.year, 3 * ((t.month - 1) // 3) + 1, 1)
    if v in ("this quarter", "the quarter", "quarter to date"):
        return q_start, t
    if v in ("last quarter", "the quarter before", "previous quarter"):
        end = q_start - timedelta(days=1)
        return date(end.year, 3 * ((end.month - 1) // 3) + 1, 1), end
    if v in ("this year", "the year"):
        return date(t.year, 1, 1), t
    d = parse_day(v, past=True)
    return d, d


def parse_time(value: str | time) -> time:
    if isinstance(value, time):
        return value
    v = value.strip().lower().replace(".", ":")
    for fmt in ("%H:%M", "%I:%M%p", "%I%p", "%I:%M %p", "%I %p", "%H"):
        try:
            return datetime.strptime(v, fmt).time()
        except ValueError:
            continue
    raise ValueError(f"Unrecognised time: {value!r}")


def log_event(s: Session, actor: str, action: str, detail: str | None = None, ref_table: str | None = None, ref_id: int | None = None) -> None:
    s.add(EventLog(actor=actor, action=action, detail=detail, ref_table=ref_table, ref_id=ref_id))


# --- customers ------------------------------------------------------------------------


def normalise_phone(p: str) -> str:
    digits = "".join(ch for ch in (p or "") if ch.isdigit() or ch == "+")
    if digits.startswith("0") and len(digits) == 10:
        digits = "+61" + digits[1:]
    return digits


def find_customer(s: Session, *, phone: str = "", rego: str = "", name: str = "") -> Customer | None:
    if phone:
        c = s.exec(select(Customer).where(Customer.phone == normalise_phone(phone))).first()
        if c:
            return c
    if rego:
        v = s.exec(select(Vehicle).where(Vehicle.rego == rego.upper().replace(" ", ""))).first()
        if v:
            return s.get(Customer, v.customer_id)
    if name:
        c = s.exec(select(Customer).where(Customer.name.ilike(name))).first()  # type: ignore[attr-defined]
        if c:
            return c
    return None


def find_or_create_customer(s: Session, *, name: str, phone: str, rego: str = "", vehicle: str = "") -> tuple[Customer, Vehicle | None]:
    c = find_customer(s, phone=phone, rego=rego)
    if not c:
        c = Customer(name=name or "Unknown caller", phone=normalise_phone(phone) or f"unknown-{datetime.utcnow().timestamp():.0f}")
        s.add(c)
        s.flush()
    elif name and c.name.startswith("Unknown"):
        c.name = name
    v: Vehicle | None = None
    if rego:
        v = s.exec(select(Vehicle).where(Vehicle.rego == rego.upper().replace(" ", ""))).first()
    if not v and (rego or vehicle):
        make, _, model = (vehicle or "Unknown Unknown").partition(" ")
        v = Vehicle(customer_id=c.id, rego=rego.upper().replace(" ", "") or "UNKNOWN", make=make, model=model or "")
        s.add(v)
        s.flush()
    return c, v


# --- bookings -------------------------------------------------------------------------


def availability(s: Session, from_day: date, days: int = 3) -> list[dict[str, Any]]:
    bays = get_settings().bays
    out: list[dict[str, Any]] = []
    for i in range(days):
        d = from_day + timedelta(days=i)
        if d.weekday() in CLOSED_WEEKDAYS:
            continue
        taken = s.exec(
            select(Booking).where(Booking.day == d, Booking.status.in_([BookingStatus.requested, BookingStatus.confirmed, BookingStatus.checked_in]))  # type: ignore[attr-defined]
        ).all()
        for t in OPEN_HOURS:
            used = sum(1 for b in taken if b.start == t)
            free = bays - used
            if free > 0:
                out.append({"day": d.isoformat(), "start": t.strftime("%H:%M"), "free_bays": free})
    return out


def first_free_bay(s: Session, d: date, t: time) -> int | None:
    """Free bay at that time; prefer the bay with the fewest cars that day so the board stays balanced."""
    active = [BookingStatus.requested, BookingStatus.confirmed, BookingStatus.checked_in]
    days_bookings = s.exec(select(Booking).where(Booking.day == d, Booking.status.in_(active))).all()  # type: ignore[attr-defined]
    taken_now = {b.bay for b in days_bookings if b.start == t}
    load = {bay: sum(1 for b in days_bookings if b.bay == bay) for bay in range(1, get_settings().bays + 1)}
    free = [bay for bay in load if bay not in taken_now]
    return min(free, key=lambda bay: (load[bay], bay)) if free else None


def create_booking(s: Session, *, customer: Customer, vehicle: Vehicle | None, day: date, start: time, service: str, source: str = "desk", notes: str | None = None) -> Booking:
    bay = first_free_bay(s, day, start)
    if bay is None:
        raise ValueError("slot_full")
    b = Booking(customer_id=customer.id, vehicle_id=vehicle.id if vehicle else None, day=day, start=start, bay=bay, service=service, source=source, notes=notes)
    s.add(b)
    s.flush()
    log_event(s, "frontdesk" if source != "desk" else "owner", "booking_created", f"{customer.name} {service} {day} {start.strftime('%H:%M')}", "booking", b.id)
    return b


def booking_reference(b: Booking) -> str:
    return f"SAC-{b.id:04d}"


def booking_view(s: Session, b: Booking) -> dict[str, Any]:
    c = s.get(Customer, b.customer_id)
    v = s.get(Vehicle, b.vehicle_id) if b.vehicle_id else None
    return {
        "booking_id": b.id,
        "reference": booking_reference(b),
        "day": b.day.isoformat(),
        "start": b.start.strftime("%H:%M"),
        "bay": b.bay,
        "service": b.service,
        "status": b.status.value,
        "customer": c.name if c else "",
        "phone": c.phone if c else "",
        "vehicle": f"{v.make} {v.model} {v.rego}" if v else "",
        "source": b.source,
    }


# --- jobs & money ---------------------------------------------------------------------


def job_totals(s: Session, job: Job) -> tuple[int, int, int]:
    """(subtotal ex GST, GST, total inc GST) in cents.
    When he stated the total and the lines were built to it, GST is 1/11 of that total
    and the three add up to exactly what he said. Otherwise GST is 10% of the lines."""
    lines = s.exec(select(JobLine).where(JobLine.job_id == job.id)).all()
    subtotal = int((sum((Decimal(str(l.qty)) * l.unit_cents for l in lines), Decimal(0))).quantize(Decimal(1), ROUND_HALF_UP))
    stated = job.stated_total_cents
    if stated is not None and subtotal == stated - gst_in(stated):
        return subtotal, stated - subtotal, stated
    gst = gst_on(subtotal)
    return subtotal, gst, subtotal + gst


def gst_on(subtotal_cents: int) -> int:
    """GST on an ex-GST amount, rounded half up to the cent as on a tax invoice."""
    return int((Decimal(subtotal_cents) * Decimal(str(get_settings().gst_rate))).quantize(Decimal(1), ROUND_HALF_UP))


def gst_in(total_cents: int) -> int:
    """The GST inside a GST-inclusive amount (1/11 at 10%), rounded half up to the cent."""
    rate = Decimal(str(get_settings().gst_rate))
    return int((Decimal(total_cents) * rate / (1 + rate)).quantize(Decimal(1), ROUND_HALF_UP))


def job_view(s: Session, job: Job) -> dict[str, Any]:
    c = s.get(Customer, job.customer_id)
    v = s.get(Vehicle, job.vehicle_id) if job.vehicle_id else None
    lines = s.exec(select(JobLine).where(JobLine.job_id == job.id)).all()
    sub, gst, tot = job_totals(s, job)
    inv = s.exec(select(Invoice).where(Invoice.job_id == job.id, Invoice.status != InvoiceStatus.void)).first()
    return {
        "job_id": job.id,
        "title": job.title,
        "status": job.status.value,
        "customer": c.name if c else "",
        "phone": c.phone if c else "",
        "vehicle": f"{v.make} {v.model} {v.rego}" if v else "",
        "rego": v.rego if v else "",
        "lines": [{"kind": l.kind.value, "description": l.description, "qty": l.qty, "unit_cents": l.unit_cents} for l in lines],
        "subtotal_cents": sub,
        "gst_cents": gst,
        "total_cents": tot,
        "invoice_number": inv.number if inv else None,
        "mechanic_notes": job.mechanic_notes,
        "booking_id": job.booking_id,
    }


def next_invoice_number(s: Session) -> str:
    n = len(s.exec(select(Invoice)).all()) + 1
    return f"INV-{today().year}-{n:05d}"


def issue_invoice(s: Session, job: Job) -> Invoice:
    existing = s.exec(select(Invoice).where(Invoice.job_id == job.id, Invoice.status != InvoiceStatus.void)).first()
    if existing:
        return existing
    sub, gst, tot = job_totals(s, job)
    inv = Invoice(number=next_invoice_number(s), job_id=job.id, customer_id=job.customer_id, subtotal_cents=sub, gst_cents=gst, total_cents=tot, due_at=today() + timedelta(days=7))
    s.add(inv)
    job.status = JobStatus.invoiced
    job.updated_at = datetime.utcnow()
    s.flush()
    from .invoices import render_invoice_pdf

    inv.pdf_path = render_invoice_pdf(s, inv)
    log_event(s, "backoffice", "invoice_issued", f"{inv.number} ${tot / 100:.2f}", "invoice", inv.id)
    return inv


def invoice_link(inv: Invoice) -> str:
    return f"{get_settings().public_base_url}/api/invoices/{inv.number}/pdf"


def issue_and_send_invoice(s: Session, job: Job) -> Invoice:
    """Issue the tax invoice and text it to the customer with "your car is ready"."""
    already = s.exec(select(Invoice).where(Invoice.job_id == job.id, Invoice.status != InvoiceStatus.void)).first()
    inv = issue_invoice(s, job)
    if already:
        return inv
    c = s.get(Customer, job.customer_id)
    v = s.get(Vehicle, job.vehicle_id) if job.vehicle_id else None
    from .channels.transport import send

    car = f"{v.make} {v.model}" if v else job.title
    first = c.name.split()[0] if c else ""
    send(s, Channel.sms, c.phone if c else "", f"Hi {first}, your {car} is ready to collect. Tax invoice {inv.number} for ${inv.total_cents / 100:.2f} inc GST: {invoice_link(inv)} - {get_settings().shop_trading_name}")
    return inv


def request_invoice_approval(s: Session, job: Job) -> dict[str, Any]:
    """The owner said "send". The person who does the books gets a one-tap approval on
    her phone; small invoices can go straight out once she trusts it."""
    settings = get_settings()
    view = job_view(s, job)
    if job.status in (JobStatus.invoiced, JobStatus.paid):
        return {"status": "already_invoiced", "invoice_number": view["invoice_number"]}
    if settings.auto_approve_invoice_under_cents and view["total_cents"] < settings.auto_approve_invoice_under_cents:
        inv = issue_and_send_invoice(s, job)
        return {"status": "sent", "invoice_number": inv.number, "total_cents": inv.total_cents}
    pending = s.exec(select(Approval).where(Approval.kind == "invoice", Approval.ref_id == job.id, Approval.status == ApprovalStatus.pending)).first()
    if pending:
        pending.detail = _invoice_approval_detail(view)
        a = pending
    else:
        a = request_approval(s, kind="invoice", title=f"Invoice for {view['customer']} ({' '.join(view['vehicle'].split()[:2])})", detail=_invoice_approval_detail(view), ref_table="job", ref_id=job.id)
    from .channels.transport import send

    send(s, Channel.sms, settings.approver_phone, f"{settings.owner_name} finished {view['customer']}'s {' '.join(view['vehicle'].split()[:2])}. Invoice ${view['total_cents'] / 100:.2f} inc GST is ready. Check and approve: {approval_link(a)}")
    return {"status": "awaiting_approval", "approval_id": a.id, "approver": settings.approver_name, "total_cents": view["total_cents"]}


def _invoice_approval_detail(view: dict[str, Any]) -> str:
    items = "; ".join(f"{l['description']} x{l['qty']:g}" for l in view["lines"])
    return f"{items}. Total ${view['total_cents'] / 100:.2f} inc GST (GST ${view['gst_cents'] / 100:.2f})."


def approval_token(a: Approval) -> str:
    return hmac.new(get_settings().app_secret.encode(), f"approval:{a.id}".encode(), hashlib.sha256).hexdigest()[:20]


def approval_link(a: Approval) -> str:
    return f"{get_settings().public_base_url}/approve/{a.id}?t={approval_token(a)}"


def record_payment(s: Session, inv: Invoice, amount_cents: int, method: str = "card", reference: str | None = None) -> Payment:
    p = Payment(invoice_id=inv.id, amount_cents=amount_cents, method=method, reference=reference)
    s.add(p)
    s.flush()
    paid = sum(x.amount_cents for x in s.exec(select(Payment).where(Payment.invoice_id == inv.id)).all())
    if paid >= inv.total_cents:
        inv.status = InvoiceStatus.paid
        job = s.get(Job, inv.job_id)
        if job:
            job.status = JobStatus.paid
        from .invoices import render_receipt_pdf

        inv.receipt_pdf_path = render_receipt_pdf(s, inv)
        c = s.get(Customer, inv.customer_id)
        if c:
            from .channels.transport import send

            send(s, Channel.sms, c.phone, f"Thanks {c.name.split()[0]}, paid ${inv.total_cents / 100:.2f} by {method.upper() if method == 'eftpos' else method}. Receipt: {get_settings().public_base_url}/api/invoices/{inv.number}/receipt - {get_settings().shop_trading_name}")
    log_event(s, "backoffice", "payment_recorded", f"{inv.number} ${amount_cents / 100:.2f} {method}", "invoice", inv.id)
    return p


def unpaid_invoices(s: Session) -> list[dict[str, Any]]:
    out = []
    for inv in s.exec(select(Invoice).where(Invoice.status == InvoiceStatus.issued)).all():
        c = s.get(Customer, inv.customer_id)
        out.append({"number": inv.number, "customer": c.name if c else "", "total_cents": inv.total_cents, "due": inv.due_at.isoformat() if inv.due_at else None, "days_overdue": max(0, (today() - inv.due_at).days) if inv.due_at else 0})
    return out


# --- suppliers & parts ----------------------------------------------------------------


def find_supplier(s: Session, name: str) -> Supplier | None:
    if not name:
        return None
    return s.exec(select(Supplier).where(Supplier.name.ilike(f"%{name}%"))).first()  # type: ignore[attr-defined]


def create_purchase_order(s: Session, *, supplier: Supplier, items: list[dict[str, Any]], job: Job | None, message: str | None = None) -> PurchaseOrder:
    po = PurchaseOrder(supplier_id=supplier.id, job_id=job.id if job else None, message=message)
    s.add(po)
    s.flush()
    for it in items:
        s.add(POLine(po_id=po.id, part_id=it.get("part_id"), description=it["description"], qty=int(it.get("qty", 1)), unit_cost_cents=int(it.get("unit_cost_cents") or 0)))
    if job and job.status in (JobStatus.approved, JobStatus.in_progress):
        job.status = JobStatus.waiting_parts
    s.flush()
    return po


def po_view(s: Session, po: PurchaseOrder) -> dict[str, Any]:
    sup = s.get(Supplier, po.supplier_id)
    lines = s.exec(select(POLine).where(POLine.po_id == po.id)).all()
    return {
        "po_id": po.id,
        "supplier": sup.name if sup else "",
        "supplier_channel": sup.order_channel if sup else "email",
        "status": po.status.value,
        "job_id": po.job_id,
        "lines": [{"description": l.description, "qty": l.qty, "unit_cost_cents": l.unit_cost_cents} for l in lines],
        "total_cents": sum(l.qty * l.unit_cost_cents for l in lines),
        "message": po.message,
        "expected_date": po.expected_date.isoformat() if po.expected_date else None,
    }


def send_purchase_order(s: Session, po: PurchaseOrder) -> Outbox:
    """Called after the owner approves. Writes to the outbox (mock) / provider (live)."""
    sup = s.get(Supplier, po.supplier_id)
    view = po_view(s, po)
    body = po.message or _default_po_text(view)
    channel = Channel.sms if (sup and sup.order_channel == "sms") else Channel.email
    to = (sup.phone if channel == Channel.sms else sup.email) if sup else ""
    from .channels.transport import send

    ob = send(s, channel, to or "unknown", body, subject=f"Parts order PO-{po.id} from {get_settings().shop_name}")
    po.status = POStatus.sent
    po.expected_date = today() + timedelta(days=2)
    log_event(s, "backoffice", "po_sent", f"PO-{po.id} to {view['supplier']}", "purchaseorder", po.id)
    return ob


def _default_po_text(view: dict[str, Any]) -> str:
    s = get_settings()
    lines = "\n".join(f"- {l['qty']} x {l['description']}" for l in view["lines"])
    return f"Hi {view['supplier']},\n\nPlease supply:\n{lines}\n\nDeliver to {s.shop_name}, {s.shop_address}. Reference PO-{view['po_id']}.\n\nThanks,\n{s.owner_name}"


# --- approvals ------------------------------------------------------------------------


def request_approval(s: Session, *, kind: str, title: str, detail: str, ref_table: str, ref_id: int, payload: dict[str, Any] | None = None) -> Approval:
    a = Approval(kind=kind, title=title, detail=detail, ref_table=ref_table, ref_id=ref_id, payload_json=json.dumps(payload or {}))
    s.add(a)
    s.flush()
    log_event(s, "backoffice", "approval_requested", title, "approval", a.id)
    return a


def decide_approval(s: Session, a: Approval, approve: bool, note: str | None = None, actor: str = "owner") -> dict[str, Any]:
    a.status = ApprovalStatus.approved if approve else ApprovalStatus.rejected
    a.decided_at = datetime.utcnow()
    result: dict[str, Any] = {"approval_id": a.id, "status": a.status.value}
    if a.kind == "invoice" and a.ref_id:
        job = s.get(Job, a.ref_id)
        if job and approve:
            inv = issue_and_send_invoice(s, job)
            result["invoice_number"] = inv.number
        elif job:
            # back to the owner with her note; he fixes it by saying it again
            if note:
                job.mechanic_notes = ((job.mechanic_notes or "") + f"\n{get_settings().approver_name}: {note}").strip()
            from .channels.transport import send

            send(s, Channel.sms, get_settings().owner_phone, f"{get_settings().approver_name} sent back {a.title}: {note or 'please check it'}")
    if approve and a.kind == "purchase_order" and a.ref_id:
        po = s.get(PurchaseOrder, a.ref_id)
        if po and po.status == POStatus.draft:
            ob = send_purchase_order(s, po)
            result["sent_via"] = ob.channel.value
    if not approve and a.kind == "purchase_order" and a.ref_id:
        po = s.get(PurchaseOrder, a.ref_id)
        if po:
            po.status = POStatus.cancelled
    log_event(s, actor, "approval_" + a.status.value, a.title + (f" ({note})" if note else ""), "approval", a.id)
    return result


# --- reporting ------------------------------------------------------------------------


def day_snapshot(s: Session, d: date) -> dict[str, Any]:
    """Everything the Ultra model needs to write the owner's end-of-day report."""
    bookings = s.exec(select(Booking).where(Booking.day == d)).all()
    tomorrow = s.exec(select(Booking).where(Booking.day == d + timedelta(days=1), Booking.status.in_([BookingStatus.confirmed, BookingStatus.requested]))).all()  # type: ignore[attr-defined]
    start, end = datetime.combine(d, time.min), datetime.combine(d, time.max)
    payments = s.exec(select(Payment).where(Payment.paid_at >= start, Payment.paid_at <= end)).all()
    expenses = s.exec(select(Expense).where(Expense.day == d)).all()
    invoices = s.exec(select(Invoice).where(Invoice.issued_at >= start, Invoice.issued_at <= end)).all()
    jobs_done = s.exec(select(Job).where(Job.updated_at >= start, Job.updated_at <= end, Job.status.in_([JobStatus.done, JobStatus.invoiced, JobStatus.paid]))).all()  # type: ignore[attr-defined]
    waiting = s.exec(select(Job).where(Job.status == JobStatus.waiting_parts)).all()
    approvals = s.exec(select(Approval).where(Approval.status == ApprovalStatus.pending)).all()
    pos = s.exec(select(PurchaseOrder).where(PurchaseOrder.status == POStatus.sent)).all()
    low_stock = s.exec(select(Part).where(Part.stock_qty <= Part.reorder_level, Part.reorder_level > 0)).all()
    events = s.exec(select(EventLog).where(EventLog.created_at >= start, EventLog.created_at <= end)).all()
    unpaid = unpaid_invoices(s)
    return {
        "day": d.isoformat(),
        "shop": get_settings().shop_name,
        "bookings_today": [booking_view(s, b) for b in bookings],
        "bookings_tomorrow": len(tomorrow),
        "tomorrow_board": [booking_view(s, b) for b in tomorrow],
        "jobs_completed": len(jobs_done),
        "jobs_waiting_parts": [job_view(s, j)["title"] + f" (job {j.id})" for j in waiting],
        "invoices_issued": [{"number": i.number, "total_cents": i.total_cents} for i in invoices],
        "cash_in_cents": sum(p.amount_cents for p in payments),
        "cash_out_cents": sum(e.amount_cents for e in expenses),
        "expenses": [{"description": e.description, "amount_cents": e.amount_cents, "category": e.category} for e in expenses],
        "unpaid_invoices": unpaid,
        "unpaid_total_cents": sum(u["total_cents"] for u in unpaid),
        "pending_approvals": [f"{a.title}: {a.detail}" for a in approvals],
        "open_purchase_orders": [po_view(s, p) for p in pos],
        "low_stock": [{"name": p.name, "stock": p.stock_qty, "reorder_level": p.reorder_level} for p in low_stock],
        "agent_actions": [f"{e.created_at.strftime('%H:%M')} {e.actor}: {e.action} {e.detail or ''}" for e in events],
    }
