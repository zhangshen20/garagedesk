"""Back-office tools for memory and know-how. Registered in the same tool registry as
tools.py; the owner agent gets them through MEMORY_TOOLS."""

from __future__ import annotations

from typing import Any

from sqlmodel import Session, select

from .. import services as svc
from ..models import Job, JobLine
from . import knowhow, memory
from .tools import S, tool

I = {"type": "integer"}


@tool(
    "recall_customer",
    "What the shop's records say about a customer or car: past visits with items and amounts, the job in the shop now, his notes, and facts he asked you to remember. Use for 'same as last time', 'what did we charge Maria', 'when was the Ranger last in'.",
    {"about": {**S, "description": "rego, car or customer name as he said it"}},
    ["about"],
)
def _recall_customer(s: Session, about: str) -> dict[str, Any]:
    return memory.recall(s, about)


@tool(
    "remember",
    "Keep a fact the owner tells you to remember ('Jack always pays cash', 'Maria's Corolla takes 0W-20'). It comes back whenever that customer or car comes up.",
    {"about": {**S, "description": "customer, car or rego the fact is about; empty for the shop in general"}, "fact": S},
    ["fact"],
)
def _remember(s: Session, fact: str, about: str = "") -> dict[str, Any]:
    return memory.remember_fact(s, about, fact)


@tool(
    "shop_knowhow",
    "Mechanic know-how: what a common job involves, typical labour time, parts usually needed, what to check, car names and shop slang. Times are typical only and never a price.",
    {"topic": S},
    ["topic"],
)
def _shop_knowhow(s: Session, topic: str) -> dict[str, Any]:
    return knowhow.lookup(topic)


@tool(
    "send_invoice_for_approval",
    "Send a finished job's invoice to whoever does the books to approve ('send it', 'send the Corolla'). This is how invoices go out; she approves, then the customer gets it.",
    {"job_id": I},
    ["job_id"],
)
def _send_invoice_for_approval(s: Session, job_id: int) -> dict[str, Any]:
    j = s.get(Job, int(job_id))
    if not j:
        return {"error": "no such job"}
    lines = s.exec(select(JobLine).where(JobLine.job_id == j.id)).all()
    if not lines:
        return {"error": "that job has no items yet; describe the work first"}
    unpriced = [l.description for l in lines if not l.unit_cents]
    if unpriced:
        return {"error": f"not sent: no price yet for {', '.join(unpriced)}. Ask him what to charge; don't look one up or add one yourself"}
    r = svc.request_invoice_approval(s, j)
    return {"job_id": j.id, **r}


MEMORY_TOOLS = ["recall_customer", "remember", "shop_knowhow", "send_invoice_for_approval"]
