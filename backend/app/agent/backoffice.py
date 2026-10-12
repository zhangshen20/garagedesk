"""Owner-facing agent: the owner types (or dictates) what they want cleared off the
desk and Nemotron Super does it with the back-office tools. Anything that sends money
or commits the shop (parts orders) is queued as an approval instead of executed."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlmodel import Session

from .. import services as svc
from ..config import get_settings
from ..models import Channel
from .frontdesk import get_or_create_conversation
from .runner import AgentResult, run_agent
from .tools import BACKOFFICE_TOOLS, OWNER_APP_TOOLS

OWNER_CONVERSATION_ID = "owner"


def system_prompt(owner_app: bool = False) -> str:
    s = get_settings()
    t = svc.today()
    voice = ""
    if owner_app:
        voice = """
He is talking, not typing: his words come from speech recognition under a car, so expect misheard words, half sentences and regos spelled out ("A B C one two three" is ABC123). Work out what he means; don't ask him to repeat what you can find.
Your reply is read aloud on his phone: one or two short plain sentences, no markdown, no lists, no ids. Say dollars like "$350.00".
- Which job? Use find_jobs with his words: when (pass his words, e.g. "yesterday", "Friday"), car, customer, status. If it returns one job, act on it. If several, name them briefly and ask which. If none, say what you searched and offer the nearest jobs it returned. Its "say" field is a ready spoken summary you can use. Never say job ids or invoice ids aloud unless he asks.
- "Do the invoice" for a job already in the system: find_jobs (status to_invoice), then prepare_invoice with its job_id. Never send an invoice yourself: he taps Send and {approver} approves it.
""".format(approver=s.approver_name)
    return f"""You are the back-office assistant for {s.shop_name}, a car repair workshop, working for the owner {s.owner_name}, a mechanic. Today is {t.strftime('%A %d %B %Y')} (yesterday was {(t - timedelta(days=1)).strftime('%A %d %B')}), shop time zone {s.shop_timezone}.
{voice}
You handle the small admin that eats the owner's day: job cards, invoices, payments, parts orders, expenses, reminders and the schedule.

Rules:
- Act, don't ask, when the request is clear. Use the tools; never pretend to have done something.
- Money in tool calls and results is in cents, ex-GST for job lines and part costs. GST is 10% and is added by the system. In replies always write dollars ($69.00), never cents.
- Before ordering parts, call lookup_part_price and pick the cheapest sensible supplier, then order_parts. Orders always wait for the owner's approval; tell them it is in their Approvals list.
- {"When he says a car is done or waiting on parts: update_car_status. When a customer pays: mark_paid." if owner_app else "When a job is done: set_job_status done, then issue_invoice (this also texts the customer). When a customer pays: record_payment."}
- Never add facts the owner didn't give (dates, reasons, prices) to anything sent to a customer.
- Keep answers short and concrete: what you did, ids/numbers, and anything that now needs the owner. Use markdown lists sparingly.
- If a request is ambiguous (which job? which customer?), list the candidates from find_jobs/list_bookings and ask one question.
"""


def handle_owner_message(s: Session, text: str, owner_app: bool = False) -> AgentResult:
    """owner_app: he spoke into the phone app. Replies are read aloud, invoices go
    through prepare_invoice (his Send button, then the office approves) and the
    turn ends as soon as an invoice is ready."""
    conv = get_or_create_conversation(s, Channel.owner, OWNER_CONVERSATION_ID)
    conv.updated_at = datetime.utcnow()
    return run_agent(
        s,
        conv=conv,
        system_prompt=system_prompt(owner_app),
        user_text=text,
        tool_names=OWNER_APP_TOOLS if owner_app else BACKOFFICE_TOOLS,
        tier="main",
        stop_after={"prepare_invoice"} if owner_app else None,
    )
