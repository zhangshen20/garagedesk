"""The one thing the app has just offered to do next ("Send it to Jenny?", "Say yes
when they've paid"). A short "yes" from the owner does it, "no" drops it. One shop,
one owner, one process: the latest offer lives in memory and goes stale on its own."""

from __future__ import annotations

import itertools
import json
import os
import re
import threading
import time
from typing import Any

from ..config import get_settings

_lock = threading.Lock()
_ids = itertools.count(1)
_offer: dict[str, Any] | None = None
_loaded = False


def _path() -> str:
    return os.path.join(get_settings().files_dir, "owner_offer.json")


def _save() -> None:
    try:
        os.makedirs(get_settings().files_dir, exist_ok=True)
        with open(_path(), "w") as f:
            json.dump(_offer, f)
    except OSError:
        pass


def _load() -> None:
    """First use after a start: pick up the offer that was open when it stopped."""
    global _offer, _loaded, _ids
    if _loaded:
        return
    _loaded = True
    try:
        with open(_path()) as f:
            o = json.load(f)
    except (OSError, ValueError):
        return
    if isinstance(o, dict) and o.get("expires", 0) > time.time():
        _offer = o
        _ids = itertools.count(int(o.get("id") or 0) + 1)

# A short answer is made only of these words, so "send the Hilux" or "done, Corolla
# ABC123" is never mistaken for a yes to something else.
YES_CORE = {"yes", "yeah", "yea", "yep", "yup", "ya", "sure", "ok", "okay", "righto", "sweet", "correct", "send", "go", "paid", "perfect", "beauty", "lovely"}
NO_CORE = {"no", "nah", "nope", "cancel", "wait", "hold", "hang", "don't", "stop", "later", "not"}
FILLER = {"please", "mate", "thanks", "thank", "you", "cheers", "it", "that", "that's", "right", "ahead", "do", "to", "on", "eftpos", "they've", "they", "have", "all", "good", "easy", "too", "yet", "on", "leave", "off", "just", "the", "invoice", "her", "him", "one", "this"}


def put(action: str, say: str, job_id: int | None = None, ttl_s: int = 15 * 60, approval_id: int | None = None) -> dict[str, Any]:
    """action: "send" (invoice to the approver), "paid" (EFTPOS), "order" (send the
    parts order waiting in approval_id) or "none" (just news)."""
    global _offer
    with _lock:
        _load()
        _offer = {"id": next(_ids), "action": action, "job_id": job_id, "approval_id": approval_id, "say": say, "turn": None, "expires": time.time() + ttl_s}
        _save()
        return public(_offer)


def current() -> dict[str, Any] | None:
    global _offer
    with _lock:
        _load()
        if _offer and _offer["expires"] < time.time():
            _offer = None
        return public(_offer) if _offer else None


def clear() -> None:
    global _offer, _loaded
    with _lock:
        _loaded = True
        if _offer is not None or os.path.exists(_path()):
            _offer = None
            _save()


def public(o: dict[str, Any] | None) -> dict[str, Any] | None:
    return {k: v for k, v in o.items() if k not in ("expires", "turn")} if o else None


def anchor(turn_id: int | None) -> None:
    """Tie the current offer to the last thing he said before it, so what he says after
    it can be told apart. Only the first call counts."""
    with _lock:
        if _offer is not None and _offer.get("turn") is None:
            _offer["turn"] = turn_id or 0
            _save()


def turn() -> int | None:
    with _lock:
        return _offer.get("turn") if _offer else None


def answer(text: str, extra: set[str] | None = None) -> str:
    """"yes", "no" or "" (not a short answer: treat it as a new instruction).
    extra: more words allowed as filler, e.g. the approver's name ("send it to Jenny")."""
    words = re.sub(r"[^\w' ]+", " ", text.lower()).split()
    allowed = YES_CORE | NO_CORE | FILLER | (extra or set())
    if not words or len(words) > 6 or any(w not in allowed for w in words):
        return ""
    if any(w in NO_CORE for w in words):
        return "no"
    if any(w in YES_CORE for w in words) or words in (["do", "it"], ["all", "good"], ["too", "easy"], ["that's", "right"]):
        return "yes"
    return ""
