"""The server voice. Kokoro (82M parameters, ONNX, int8) runs on the VM's CPU, so every
phone and every browser hears the same clear voice instead of whatever robot the
browser ships with. A sentence takes about half its own length to make on two cores;
the page asks for one sentence at a time and plays the first while the next is made.

Modes (TTS_MODE): auto = Kokoro when its model files are present, else off;
kokoro; mock (a short silent clip, for tests); off (the page uses the browser voice)."""

from __future__ import annotations

import io
import logging
import os
import struct
import threading
from collections import OrderedDict
from concurrent.futures import Future
from typing import Any

from ..config import get_settings

log = logging.getLogger("garagedesk.tts")

MAX_CHARS = 400
_CACHE_SIZE = 300

_lock = threading.Lock()  # one synthesis at a time: the VM has two cores
_state_lock = threading.Lock()
_cache: OrderedDict[str, bytes] = OrderedDict()
_inflight: dict[str, Future[bytes]] = {}
_engine: Any = None
_engine_failed = False


def _files() -> tuple[str, str]:
    d = get_settings().tts_model_dir
    return os.path.join(d, "kokoro-v1.0.int8.onnx"), os.path.join(d, "voices-v1.0.bin")


def mode() -> str:
    m = get_settings().tts_mode
    if m != "auto":
        return m
    if _engine_failed:
        return "off"
    model, voices = _files()
    if not (os.path.exists(model) and os.path.exists(voices)):
        return "off"
    try:
        import kokoro_onnx  # noqa: F401
    except ImportError:
        return "off"
    return "kokoro"


def available() -> bool:
    return mode() in ("kokoro", "mock")


def _load() -> Any:
    global _engine, _engine_failed
    if _engine is None:
        from kokoro_onnx import Kokoro

        try:
            _engine = Kokoro(*_files())
        except Exception:
            _engine_failed = True
            raise
        log.info("Kokoro voice loaded (%s)", get_settings().tts_voice)
    return _engine


def _wav(samples: Any, rate: int) -> bytes:
    import numpy as np

    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes()
    head = b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16) + b"data" + struct.pack("<I", len(pcm))
    return head + pcm


def _silent_wav(text: str) -> bytes:
    rate = 8000
    n = rate * max(1, len(text)) // 40
    buf = io.BytesIO()
    buf.write(b"RIFF" + struct.pack("<I", 36 + 2 * n) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16) + b"data" + struct.pack("<I", 2 * n))
    buf.write(b"\0\0" * n)
    return buf.getvalue()


def _make(text: str) -> bytes:
    if mode() == "mock":
        return _silent_wav(text)
    st = get_settings()
    with _lock:
        k = _load()
        voice = st.tts_voice
        lang = "en-gb" if voice[:1] == "b" else "en-us"
        samples, rate = k.create(text, voice=voice, speed=st.tts_speed, lang=lang)
    return _wav(samples, rate)


def synth(text: str) -> bytes:
    """WAV bytes for one sentence (or a few). Cached; concurrent asks share one run."""
    text = " ".join(text.split())[:MAX_CHARS]
    with _state_lock:
        if text in _cache:
            _cache.move_to_end(text)
            return _cache[text]
        fut = _inflight.get(text)
        owner = fut is None
        if owner:
            fut = Future()
            _inflight[text] = fut
    assert fut is not None
    if not owner:
        return fut.result(timeout=60)
    try:
        audio = _make(text)
    except BaseException as e:
        with _state_lock:
            _inflight.pop(text, None)
        fut.set_exception(e)
        raise
    with _state_lock:
        _cache[text] = audio
        while len(_cache) > _CACHE_SIZE:
            _cache.popitem(last=False)
        _inflight.pop(text, None)
    fut.set_result(audio)
    return audio


def prepare(texts: list[str]) -> None:
    """Start making these in the background (the read-back, before the phone asks)."""
    if not available() or not texts:
        return

    def run() -> None:
        for t in texts:
            try:
                synth(t)
            except Exception:
                log.exception("tts prepare failed")
                return

    threading.Thread(target=run, daemon=True, name="tts-prepare").start()


def warm() -> None:
    """Load the model and the phrases he hears all day, so they play at once."""
    from .spoken import approver, ask_send

    who = approver()
    prepare([ask_send(), f"Sent to {who}.", "No worries.", "Paid on EFTPOS. Receipt sent.", "Nothing waiting on a yes. Tell me the car and what you did."])
