"""Data model for a small workshop: who, what car, what work, what money.

Kept deliberately flat. Every table has an integer id; money is stored in cents."""

from datetime import date, datetime, time
from enum import Enum

from pydantic import NaiveDatetime
from sqlmodel import Field, SQLModel


def now() -> datetime:
    return datetime.utcnow().replace(microsecond=0)


class Customer(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    phone: str = Field(index=True)
    email: str | None = None
    notes: str | None = None
    created_at: NaiveDatetime = Field(default_factory=now)


class Vehicle(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    customer_id: int = Field(foreign_key="customer.id", index=True)
    rego: str = Field(index=True)  # registration plate
    make: str
    model: str
    year: int | None = None
    odometer_km: int | None = None


class BookingStatus(str, Enum):
    requested = "requested"
    confirmed = "confirmed"
    checked_in = "checked_in"
    completed = "completed"
    cancelled = "cancelled"
    no_show = "no_show"


class Booking(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    customer_id: int = Field(foreign_key="customer.id", index=True)
    vehicle_id: int | None = Field(default=None, foreign_key="vehicle.id")
    day: date = Field(index=True)
    start: time
    duration_min: int = 60
    bay: int = 1
    service: str  # free text, e.g. "logbook service", "RWC inspection"
    status: BookingStatus = BookingStatus.confirmed
    notes: str | None = None
    source: str = "desk"  # phone | sms | web | desk
    created_at: NaiveDatetime = Field(default_factory=now)


class JobStatus(str, Enum):
    quoted = "quoted"
    approved = "approved"
    in_progress = "in_progress"
    waiting_parts = "waiting_parts"
    done = "done"
    invoiced = "invoiced"
    paid = "paid"


class Job(SQLModel, table=True):
    """A job card: the work actually done on a car. Usually born from a booking."""

    id: int | None = Field(default=None, primary_key=True)
    booking_id: int | None = Field(default=None, foreign_key="booking.id")
    customer_id: int = Field(foreign_key="customer.id", index=True)
    vehicle_id: int | None = Field(default=None, foreign_key="vehicle.id")
    title: str
    status: JobStatus = JobStatus.quoted
    mechanic_notes: str | None = None
    # the total he said ("350 all up"), inc GST: the invoice comes to exactly this,
    # GST being 1/11 of it, while the lines still add up to it (see services.job_totals)
    stated_total_cents: int | None = None
    created_at: NaiveDatetime = Field(default_factory=now)
    updated_at: NaiveDatetime = Field(default_factory=now)


class LineKind(str, Enum):
    labour = "labour"
    part = "part"
    fee = "fee"


class JobLine(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="job.id", index=True)
    kind: LineKind
    description: str
    qty: float = 1
    unit_cents: int = 0  # ex-GST
    part_id: int | None = Field(default=None, foreign_key="part.id")


class Supplier(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    contact_name: str | None = None
    email: str | None = None
    phone: str | None = None
    order_channel: str = "email"  # email | sms
    notes: str | None = None


class Part(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    sku: str | None = Field(default=None, index=True)
    name: str
    supplier_id: int | None = Field(default=None, foreign_key="supplier.id")
    cost_cents: int = 0  # what we pay, ex-GST
    sell_cents: int = 0  # what we charge, ex-GST
    stock_qty: int = 0
    reorder_level: int = 0


class POStatus(str, Enum):
    draft = "draft"
    sent = "sent"
    received = "received"
    cancelled = "cancelled"


class PurchaseOrder(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    supplier_id: int = Field(foreign_key="supplier.id")
    job_id: int | None = Field(default=None, foreign_key="job.id")
    status: POStatus = POStatus.draft
    message: str | None = None  # the order text the agent drafted
    expected_date: date | None = None
    created_at: NaiveDatetime = Field(default_factory=now)


class POLine(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    po_id: int = Field(foreign_key="purchaseorder.id", index=True)
    part_id: int | None = Field(default=None, foreign_key="part.id")
    description: str
    qty: int = 1
    unit_cost_cents: int = 0


class InvoiceStatus(str, Enum):
    issued = "issued"
    paid = "paid"
    void = "void"


class Invoice(SQLModel, table=True):
    """Australian tax invoice: GST shown separately, ABN on the document."""

    id: int | None = Field(default=None, primary_key=True)
    number: str = Field(index=True, unique=True)
    job_id: int = Field(foreign_key="job.id")
    customer_id: int = Field(foreign_key="customer.id")
    subtotal_cents: int
    gst_cents: int
    total_cents: int
    status: InvoiceStatus = InvoiceStatus.issued
    issued_at: NaiveDatetime = Field(default_factory=now)
    due_at: date | None = None
    pdf_path: str | None = None
    receipt_pdf_path: str | None = None


class Payment(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    invoice_id: int = Field(foreign_key="invoice.id", index=True)
    amount_cents: int
    method: str = "card"  # card | cash | transfer
    paid_at: NaiveDatetime = Field(default_factory=now)
    reference: str | None = None


class Expense(SQLModel, table=True):
    """Anything the shop pays for that isn't a PO: rent, consumables, tooling."""

    id: int | None = Field(default=None, primary_key=True)
    day: date = Field(index=True)
    description: str
    amount_cents: int  # inc-GST as paid
    gst_cents: int = 0
    category: str = "general"
    supplier_id: int | None = Field(default=None, foreign_key="supplier.id")


class Channel(str, Enum):
    web = "web"
    sms = "sms"
    voice = "voice"
    email = "email"
    owner = "owner"  # the owner talking to the back-office agent


class Conversation(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    channel: Channel
    external_id: str = Field(index=True)  # phone number, web session id, call sid
    customer_id: int | None = Field(default=None, foreign_key="customer.id")
    summary: str | None = None
    intent: str | None = None
    open: bool = True
    created_at: NaiveDatetime = Field(default_factory=now)
    updated_at: NaiveDatetime = Field(default_factory=now)


class Message(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    conversation_id: int = Field(foreign_key="conversation.id", index=True)
    role: str  # user | assistant | tool | system
    content: str
    tool_name: str | None = None
    tool_call_id: str | None = None
    tool_calls_json: str | None = None
    model: str | None = None
    created_at: NaiveDatetime = Field(default_factory=now)


class ApprovalStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class Approval(SQLModel, table=True):
    """Something the agent wants to do but won't without the owner's say-so:
    sending a supplier order, quoting above a threshold, issuing a refund."""

    id: int | None = Field(default=None, primary_key=True)
    kind: str  # purchase_order | quote | refund | other
    title: str
    detail: str
    payload_json: str | None = None
    ref_table: str | None = None
    ref_id: int | None = None
    status: ApprovalStatus = ApprovalStatus.pending
    created_at: NaiveDatetime = Field(default_factory=now)
    decided_at: NaiveDatetime | None = None


class Outbox(SQLModel, table=True):
    """Every outbound SMS, email or call the system makes. In mock mode this is the
    delivery; in live mode it is the audit log."""

    id: int | None = Field(default=None, primary_key=True)
    channel: Channel
    to: str
    subject: str | None = None
    body: str
    delivered: bool = False
    provider_ref: str | None = None
    created_at: NaiveDatetime = Field(default_factory=now)


class DailyReport(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    day: date = Field(index=True, unique=True)
    content_md: str
    model: str
    created_at: NaiveDatetime = Field(default_factory=now)


class EventLog(SQLModel, table=True):
    """Human-readable trail of what the agents did, shown on the dashboard."""

    id: int | None = Field(default=None, primary_key=True)
    actor: str  # frontdesk | backoffice | owner | system
    action: str
    detail: str | None = None
    ref_table: str | None = None
    ref_id: int | None = None
    created_at: NaiveDatetime = Field(default_factory=now)


class OwnerTurn(SQLModel, table=True):
    """One thing the owner said into his phone and what came of it. The agent reads
    the recent ones back so "send it", "that one" or "the Corolla from this
    morning" mean something."""

    id: int | None = Field(default=None, primary_key=True)
    said: str
    kind: str = "reply"  # draft | reply | follow_up
    outcome: str = ""  # what the agent said back
    ready: bool = False  # a clean draft read back, waiting on "send it"
    described: str = ""  # for drafts: his whole description of the job so far, corrections folded in
    job_id: int | None = Field(default=None, foreign_key="job.id", index=True)
    customer_id: int | None = Field(default=None, foreign_key="customer.id")
    created_at: NaiveDatetime = Field(default_factory=now, index=True)


class OwnerFact(SQLModel, table=True):
    """Something the owner asked the agent to keep in mind ("Jack always pays cash",
    "Maria's Corolla takes 0W-20"). Brought up whenever that customer or car is."""

    id: int | None = Field(default=None, primary_key=True)
    fact: str
    customer_id: int | None = Field(default=None, foreign_key="customer.id", index=True)
    vehicle_id: int | None = Field(default=None, foreign_key="vehicle.id")
    created_at: NaiveDatetime = Field(default_factory=now)
