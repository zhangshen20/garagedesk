"""Twilio webhooks for SMS and voice. Voice uses Twilio's own speech-to-text
(<Gather input="speech">) and text-to-speech (<Say>), so a phone call needs nothing
beyond a Twilio number. The same endpoints are also what the dashboard's
"simulate a call / text" buttons hit, so everything is testable without Twilio."""

from __future__ import annotations

from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import Response
from sqlmodel import Session

from ..agent.frontdesk import handle_customer_message
from ..config import get_settings
from ..db import get_session
from ..models import Channel

router = APIRouter(prefix="/twilio", tags=["twilio"])


def _twiml(body: str) -> Response:
    return Response(content=f'<?xml version="1.0" encoding="UTF-8"?><Response>{body}</Response>', media_type="application/xml")


@router.post("/sms")
def sms_webhook(From: str = Form(...), Body: str = Form(""), s: Session = Depends(get_session)) -> Response:
    result = handle_customer_message(s, channel=Channel.sms, external_id=From, text=Body)
    s.commit()
    return _twiml(f"<Message>{escape(result.reply)}</Message>")


@router.post("/voice")
def voice_webhook(request: Request, From: str = Form(""), CallSid: str = Form(""), SpeechResult: str = Form(""), s: Session = Depends(get_session)) -> Response:
    """First hit: greet and listen. Later hits: carry SpeechResult into the agent."""
    settings = get_settings()
    action = str(request.url_for("voice_webhook"))
    if not SpeechResult:
        greeting = f"Hi, you've reached {settings.shop_trading_name}. How can I help?"
        return _twiml(f'<Gather input="speech" language="en-AU" speechTimeout="auto" action="{action}" method="POST"><Say voice="Polly.Nicole">{escape(greeting)}</Say></Gather><Say voice="Polly.Nicole">Sorry, I didn\'t catch that. Goodbye.</Say>')
    result = handle_customer_message(s, channel=Channel.voice, external_id=From or CallSid or "unknown-caller", text=SpeechResult)
    s.commit()
    done = any(k in result.reply.lower() for k in ("goodbye", "bye for now", "will call you back", "see you then"))
    say = f'<Say voice="Polly.Nicole">{escape(result.reply)}</Say>'
    if done:
        return _twiml(say + "<Hangup/>")
    return _twiml(f'<Gather input="speech" language="en-AU" speechTimeout="auto" action="{action}" method="POST">{say}</Gather><Say voice="Polly.Nicole">Thanks for calling. Goodbye.</Say>')
