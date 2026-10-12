"""GarageDesk API. Serves the JSON API, Twilio webhooks and (in production) the
built React dashboard from ./static."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api.routes import router as api_router
from .bookings.router import router as site_bookings_router
from .channels.twilio import router as twilio_router
from .config import get_settings
from .db import init_db, session_scope

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("garagedesk")

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")


def _end_of_day_job() -> None:
    from .agent.report import generate_daily_report

    with session_scope() as s:
        generate_daily_report(s, force=True)
        s.commit()


def _reminders_job() -> None:
    """Text tomorrow's customers a reminder (the agent's most boring, most valuable task)."""
    from datetime import timedelta

    from sqlmodel import select

    from . import services as svc
    from .channels.transport import send
    from .models import Booking, BookingStatus, Channel, Customer

    with session_scope() as s:
        tomorrow = svc.today() + timedelta(days=1)
        for b in s.exec(select(Booking).where(Booking.day == tomorrow, Booking.status == BookingStatus.confirmed)).all():
            c = s.get(Customer, b.customer_id)
            if c:
                send(s, Channel.sms, c.phone, f"Reminder from {get_settings().shop_trading_name}: {b.service} tomorrow at {b.start.strftime('%-I:%M%p').lower()}. Reply if you need to change it.")
        s.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    settings = get_settings()
    if os.environ.get("GARAGEDESK_SEED", "1") == "1":
        from .seed import seed_if_empty

        with session_scope() as s:
            seed_if_empty(s)
    log.info("GarageDesk up. LLM mode=%s main=%s", settings.effective_llm_mode, settings.model_main)
    scheduler = BackgroundScheduler(timezone=settings.shop_timezone)
    scheduler.add_job(_end_of_day_job, CronTrigger(hour=17, minute=45))
    scheduler.add_job(_reminders_job, CronTrigger(hour=16, minute=0))
    if os.environ.get("GARAGEDESK_SCHEDULER", "1") == "1":
        scheduler.start()
    yield
    if scheduler.running:
        scheduler.shutdown(wait=False)


app = FastAPI(title="GarageDesk", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(api_router)
app.include_router(site_bookings_router)
app.include_router(twilio_router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "llm": get_settings().effective_llm_mode}


if os.path.isdir(STATIC_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(STATIC_DIR, "assets")), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str) -> FileResponse:
        candidate = os.path.join(STATIC_DIR, full_path)
        if full_path and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))
