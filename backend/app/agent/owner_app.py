"""The owner app's one big button. Whatever he says lands here.

Nemotron Nano decides in well under a second whether he is describing finished
work (that becomes a draft invoice via jobcard.py) or asking for anything else
("Hilux is done", "Corolla paid on EFTPOS", "need front pads for the Mazda"),
which goes to the back-office agent and its tools."""

from __future__ import annotations

import json
from typing import Any

from sqlmodel import Session

from ..llm import get_llm
from .backoffice import handle_owner_message
from .jobcard import draft_from_text

INTENT_PROMPT = """You route what a mechanic shop owner just said into his phone. Decide the intent of the owner's words.
"job_card": he is describing work he finished on a car so it can be invoiced (what was done, parts fitted, labour time).
"other": anything else: a car's progress ("Hilux is done", "waiting on parts"), a payment ("paid on EFTPOS"), ordering parts, a question.
Reply with JSON only: {"intent": "job_card" | "other"}"""


def route(text: str) -> str:
    r = get_llm().chat(
        [{"role": "system", "content": INTENT_PROMPT}, {"role": "user", "content": text}],
        tier="fast",
        json_mode=True,
        max_tokens=50,
        temperature=0,
    )
    try:
        return str(json.loads(r.content or "{}").get("intent", "other"))
    except json.JSONDecodeError:
        return "job_card" if "job_card" in (r.content or "") else "other"


def handle_voice(s: Session, text: str) -> dict[str, Any]:
    from ..voice.flow import reply_to_offer, with_voice

    # "yes" / "nah" answers the step the app just offered (send it, mark it paid)
    short = reply_to_offer(s, text)
    if short is not None:
        return short
    if route(text) == "job_card":
        return with_voice({"kind": "draft", **draft_from_text(s, text).as_dict()})
    r = handle_owner_message(s, text)
    return with_voice({"kind": "reply", "readback": r.reply, "steps": r.steps, "model": r.model})
