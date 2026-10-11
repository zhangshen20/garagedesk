"""Outbound delivery. Every message goes through the outbox table; when Twilio
credentials exist SMS is actually sent, otherwise the outbox *is* the delivery
(the dashboard shows it), so the product works without any paid accounts."""

from __future__ import annotations

import logging

import httpx
from sqlmodel import Session

from ..config import get_settings
from ..models import Channel, Outbox

log = logging.getLogger(__name__)


def send(s: Session, channel: Channel, to: str, body: str, subject: str | None = None) -> Outbox:
    ob = Outbox(channel=channel, to=to, body=body, subject=subject)
    s.add(ob)
    s.flush()
    settings = get_settings()
    if channel == Channel.sms and settings.twilio_enabled:
        try:
            r = httpx.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json",
                data={"From": settings.twilio_from_number, "To": to, "Body": body},
                auth=(settings.twilio_account_sid, settings.twilio_auth_token),
                timeout=15,
            )
            r.raise_for_status()
            ob.provider_ref = r.json().get("sid")
            ob.delivered = True
        except Exception as e:  # noqa: BLE001
            log.warning("Twilio send failed: %s", e)
    else:
        # Mock delivery: the outbox row is what the owner sees on the dashboard.
        ob.delivered = True
        ob.provider_ref = "mock"
    return ob
