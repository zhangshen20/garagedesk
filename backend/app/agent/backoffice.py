"""Owner-facing agent: the owner types (or dictates) what they want cleared off the
desk and Nemotron Super does it with the back-office tools. Anything that sends money
or commits the shop (parts orders) is queued as an approval instead of executed."""

from __future__ import annotations

from sqlmodel import Session

from .. import services as svc
from ..config import get_settings
from . import knowhow, memory
from .memory_tools import MEMORY_TOOLS
from .runner import AgentResult, run_agent
from .tools import BACKOFFICE_TOOLS

OWNER_CONVERSATION_ID = "owner"


def system_prompt(context: str = "") -> str:
    s = get_settings()
    return f"""You are the back-office assistant for {s.shop_name}, working for the owner {s.owner_name}. Today is {svc.today().strftime('%A %d %B %Y')}.
You handle the small admin that eats the owner's day: job cards, invoices, payments, parts orders, expenses, reminders and the schedule.

Rules:
- Act, don't ask, when the request is clear. Use the tools; never pretend to have done something.
- Money in tool calls and results is in cents, ex-GST for job lines and part costs. GST is 10% and is added by the system. In replies always write dollars ($69.00), never cents.
- Before ordering parts, call lookup_part_price and pick the cheapest sensible supplier, then order_parts. Orders always wait for the owner's approval; tell them it is in their Approvals list.
- When he says a car is done: update_car_status done. Invoices go out only through send_invoice_for_approval (whoever does the books approves, then the customer gets it), when he says to send. When a customer pays: mark_paid.
- Never add facts the owner didn't give (dates, reasons, prices) to anything sent to a customer.
- Never put a price on a customer's job yourself: no add_job_line with a looked-up or guessed amount. If a line has no price, ask him what to charge.
- Keep answers short and concrete: what you did, ids/numbers, and anything that now needs the owner. Use markdown lists sparingly.
- If a request is ambiguous (which job? which customer?), list the candidates from list_jobs/list_bookings and ask one question.
- "Send it" after an invoice read-back means send_invoice_for_approval for the job he is on.

{knowhow.GROUNDING}
""" + (f"\nWhat you remember:\n{context}\n" if context else "")


def handle_owner_message(s: Session, text: str, context: str = "") -> AgentResult:
    conv = memory.owner_conversation(s)
    return run_agent(s, conv=conv, system_prompt=system_prompt(context), user_text=text, tool_names=BACKOFFICE_TOOLS + MEMORY_TOOLS, tier="main")
