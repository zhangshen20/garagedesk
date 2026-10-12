"""Owner-facing agent: the owner types (or dictates) what they want cleared off the
desk and Nemotron Super does it with the back-office tools. Anything that sends money
or commits the shop (parts orders) is queued as an approval instead of executed."""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Session

from .. import services as svc
from ..config import get_settings
from ..models import Channel
from .frontdesk import get_or_create_conversation
from .runner import AgentResult, run_agent
from .tools import BACKOFFICE_TOOLS

OWNER_CONVERSATION_ID = "owner"


def system_prompt() -> str:
    s = get_settings()
    return f"""You are the back-office assistant for {s.shop_name}, working for the owner {s.owner_name}. Today is {svc.today().strftime('%A %d %B %Y')}.
You handle the small admin that eats the owner's day: job cards, invoices, payments, parts orders, expenses, reminders and the schedule.

Rules:
- Act, don't ask, when the request is clear. Use the tools; never pretend to have done something.
- Money in tool calls and results is in cents, ex-GST for job lines and part costs. GST is 10% and is added by the system. In replies always write dollars ($69.00), never cents.
- Before ordering parts, call lookup_part_price and pick the cheapest sensible supplier, then order_parts. Orders always wait for the owner's approval; tell them it is in their Approvals list.
- When a job is done: set_job_status done, then issue_invoice (this also texts the customer). When a customer pays: record_payment.
- Never add facts the owner didn't give (dates, reasons, prices) to anything sent to a customer.
- Keep answers short and concrete: what you did, ids/numbers, and anything that now needs the owner. Use markdown lists sparingly.
- If a request is ambiguous (which job? which customer?), list the candidates from list_jobs/list_bookings and ask one question.
"""


def handle_owner_message(s: Session, text: str) -> AgentResult:
    conv = get_or_create_conversation(s, Channel.owner, OWNER_CONVERSATION_ID)
    conv.updated_at = datetime.utcnow()
    return run_agent(s, conv=conv, system_prompt=system_prompt(), user_text=text, tool_names=BACKOFFICE_TOOLS, tier="main")
