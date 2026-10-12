"""Speech to text on our own server.

iPhone browsers other than Safari (Chrome, in-app browsers) refuse the page
speech API, but they can all record audio. The owner app records what he says
and posts it here; faster-whisper (an open Whisper model, run on the VM's CPU)
turns it into text, which then goes down the same Nemotron pipeline as typed or
dictated words. Nebius Token Factory has no speech model, so this runs locally.
"""

from __future__ import annotations

import io
import logging
import re
import threading
from functools import lru_cache

from ..config import get_settings

log = logging.getLogger("garagedesk.stt")
_lock = threading.Lock()

# Words a Whisper model mishears in a workshop; listing them steers it.
_HINT = (
    "Mechanic workshop job. Rego, labour, hour and a half, all up, front pads, rotors, "
    "oil and filter, Corolla, Hilux, CX-5, Commodore, Ranger, EFTPOS, GST."
)

MOCK_TRANSCRIPT = "Corolla ABC123, front pads, hour and a half, 350 all up"


def _mock() -> bool:
    # tests and keyless local runs: no model download, a fixed sentence instead
    return get_settings().effective_llm_mode == "mock"


def available() -> bool:
    if _mock():
        return True
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return False
    return True


@lru_cache(maxsize=1)
def _model():
    from faster_whisper import WhisperModel

    s = get_settings()
    log.info("loading speech model %s", s.stt_model)
    return WhisperModel(s.stt_model, device="cpu", compute_type="int8")


def transcribe(audio: bytes, extra_hint: str = "") -> str:
    if _mock():
        return MOCK_TRANSCRIPT
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        raise RuntimeError("speech to text is not installed on this server") from None
    with _lock:  # one at a time on a small VM
        segments, _ = _model().transcribe(
            io.BytesIO(audio), language="en", beam_size=1, vad_filter=True, initial_prompt=(_HINT + " " + extra_hint).strip()
        )
        return _fix_words(" ".join(seg.text.strip() for seg in segments).strip())


# Whisper hears an Australian "labour" as "label" (seen live); nothing in a
# workshop job is a "label", so put it back.
_FIXES = [(re.compile(r"\blabels?\b", re.I), "labour")]


def _fix_words(text: str) -> str:
    for pattern, word in _FIXES:
        text = pattern.sub(word, text)
    return text


def warm_up() -> None:
    """Load the model in the background at start-up so his first recording isn't slow."""
    if _mock():
        return
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return
    threading.Thread(target=_model, daemon=True).start()
