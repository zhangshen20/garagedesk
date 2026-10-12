"""The owner app's one big button. Whatever he says lands here.

Nemotron Nano decides in well under a second whether he is describing finished
work (that becomes a draft invoice via jobcard.py) or asking for anything else
("Hilux is done", "Corolla paid on EFTPOS", "need front pads for the Mazda"),
which goes to the back-office agent and its tools."""

from __future__ import annotations

import json
import re
from typing import Any

from sqlmodel import Session

from ..llm import get_llm
from . import memory
from .backoffice import handle_owner_message
from .jobcard import draft_from_text

INTENT_PROMPT = """You route what a mechanic shop owner just said into his phone. Decide the intent of the owner's words.
"job_card": he is describing work he finished on a car so it can be invoiced (what was done, parts fitted, labour time).
"other": anything else: a car's progress ("Hilux is done", "waiting on parts"), a payment ("paid on EFTPOS"), ordering parts, a question.
"Send it", a payment, or a question about a job is "other" even when the context below mentions a draft. Correcting or adding to the work on the job he is on ("make it 380 all up", "add wipers to that") is "job_card", and so is "same as last time" for a car.
Examples:
"Corolla ABC123, front pads, hour and a half, 350 all up" -> job_card
"did a logbook service on the Cerato, hour and a half" -> job_card
"add oil and a filter to that" -> job_card
"the CX-5's done, roadworthy passed" -> other (a status, no work or money to invoice)
"what did we charge her for that" -> other
"ok send that one" -> other
"remember Jack always pays cash" -> other
Reply with JSON only: {"intent": "job_card" | "other"}"""

# Plainly not a description of work, whatever the model thinks: a question, "send it", or "waiting on parts".
_QUESTION = re.compile(r"^\s*(what|what's|whats|when|where|who|which|how|why|does|has|is|are|was|were|should|any|anything|remember)\b", re.I)
_SEND = re.compile(r"\b(send|approve|waiting (?:on|for)|order|remember)\b", re.I)
_EDIT = re.compile(r"\b(make it|change|add)\b", re.I)
_WORK = re.compile(r"\b(make it|change|add|all up|labour|labor|hours?|hrs?|same as last|same again|\d+)\b", re.I)


def route(text: str, context: str = "") -> str:
    if _QUESTION.match(text) and not _EDIT.search(text):
        return "other"
    if _SEND.search(text) and not _WORK.search(text):
        return "other"
    system = INTENT_PROMPT + (f"\n\nContext:\n{context}" if context else "")
    r = get_llm().chat(
        [{"role": "system", "content": system}, {"role": "user", "content": text}],
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
    out = memory.follow_up(s, text)  # "yep, send it" right after a read-back
    if out is None:
        amended = memory.amend_text(s, text)  # "make it 380 all up" right after a draft
        if amended or route(text, memory.route_context(s)) == "job_card":
            words = amended or text
            out = {"kind": "draft", **draft_from_text(s, words, context=memory.owner_context(s, words, for_extract=True)).as_dict(), "transcript": text, "described": words}
        else:
            r = handle_owner_message(s, text, context=memory.owner_context(s, text))
            out = {"kind": "reply", "readback": r.reply, "steps": r.steps, "model": r.model}
    memory.remember_turn(s, text, out)
    return out
