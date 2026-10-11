"""End-of-day owner report, written by Nemotron 3 Ultra from a structured snapshot
of the whole day. This is the one place the biggest model is worth paying for:
it has to reason across cash, jobs, parts and tomorrow's board in one pass."""

from __future__ import annotations

import json
from datetime import date

from sqlmodel import Session, select

from .. import services as svc
from ..config import get_settings
from ..llm import get_llm
from ..models import DailyReport

REPORT_PROMPT = """You write the end-of-day daily report for the owner of a small independent mechanic workshop.
You get a JSON snapshot of the day. Write in Markdown, under 300 words, in this shape:

## End of day — {day}
One or two sentences on how the day went (jobs, cash, anything unusual).

### Money
Cash in, cash out, GST collected today, total still owed to us (name the overdue ones).

### What needs you
A short list of decisions waiting: approvals, overdue invoices to chase, parts to order, low stock. If nothing, say so.

### Tomorrow
Cars booked, first drop-off, anything to prepare (parts expected, RWC inspections, long jobs).

### One suggestion
One concrete, specific thing that would make tomorrow smoother or make/save money, based on the data. Not generic advice.

Be concrete: use names, numbers, dollar amounts (cents / 100). Never invent data not in the snapshot."""


def generate_daily_report(s: Session, d: date | None = None, force: bool = False) -> DailyReport:
    d = d or svc.today()
    existing = s.exec(select(DailyReport).where(DailyReport.day == d)).first()
    if existing and not force:
        return existing
    snapshot = svc.day_snapshot(s, d)
    reply = get_llm().chat(
        [
            {"role": "system", "content": REPORT_PROMPT.replace("{day}", d.strftime("%A %d %B %Y")) + "\n\nTask: daily report."},
            {"role": "user", "content": json.dumps(snapshot, default=str)},
        ],
        tier="deep",
        temperature=0.3,
        max_tokens=900,
    )
    content = reply.content or "No report generated."
    if existing:
        existing.content_md, existing.model = content, reply.model
        rep = existing
    else:
        rep = DailyReport(day=d, content_md=content, model=reply.model)
        s.add(rep)
    s.flush()
    svc.log_event(s, "backoffice", "daily_report", f"{d} via {reply.model}", "dailyreport", rep.id)
    # Text the owner a two-line heads-up; the full report lives on the dashboard.
    from ..channels.transport import send
    from ..models import Channel

    first = next((ln for ln in content.splitlines() if ln and not ln.startswith("#")), "Report ready.")
    send(s, Channel.sms, get_settings().owner_phone, f"{get_settings().shop_name} end of day: {first[:200]} Full report on your dashboard.")
    return rep
