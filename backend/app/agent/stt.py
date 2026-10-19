"""Speech to text on our own server.

iPhone browsers other than Safari (Chrome, in-app browsers) refuse the page
speech API, but they can all record audio. The owner app records what he says
and posts it here, and an open speech model on the VM's CPU turns it into text,
which then goes down the same Nemotron pipeline as typed or dictated words.
Nebius Token Factory has no speech model, so this runs locally.

The default model is NVIDIA Parakeet TDT 0.6B v2 (CC-BY-4.0, int8 ONNX). It was
trained on far more varied English than a small Whisper, so it hears speakers
whose first language isn't English much better, and on our 2-vCPU VM it takes
about 0.6 s for a 5 s recording (Whisper base.en: 1.2 s; small.en: 4 s;
large-v3-turbo: 14 s). It takes no prompt, so the cars it mishears are put back
afterwards from the cars it heard around them (see _fix_cars). Whisper is still
available with STT_ENGINE=whisper.
"""

from __future__ import annotations

import io
import logging
import re
import threading
from difflib import SequenceMatcher
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


def _parakeet() -> bool:
    return get_settings().stt_engine == "parakeet"


def _installed() -> bool:
    try:
        if _parakeet():
            import onnx_asr  # noqa: F401
        import faster_whisper  # noqa: F401  (also decodes the phone's mp4/webm audio)
    except ImportError:
        return False
    return True


def available() -> bool:
    return _mock() or _installed()


@lru_cache(maxsize=1)
def _model():
    s = get_settings()
    if _parakeet():
        import onnx_asr

        log.info("loading speech model %s", s.parakeet_model)
        return onnx_asr.load_model(s.parakeet_model, quantization="int8")
    from faster_whisper import WhisperModel

    log.info("loading speech model %s", s.stt_model)
    return WhisperModel(s.stt_model, device="cpu", compute_type="int8")


def transcribe(audio: bytes, extra_hint: str = "") -> str:
    if _mock():
        return MOCK_TRANSCRIPT
    if not _installed():
        raise RuntimeError("speech to text is not installed on this server")
    with _lock:  # one at a time on a small VM
        if _parakeet():
            from faster_whisper.audio import decode_audio

            samples = decode_audio(io.BytesIO(audio), sampling_rate=16000)
            if len(samples) < 1600:  # under a tenth of a second
                return ""
            text = _model().recognize(samples, sample_rate=16000)
        else:
            segments, _ = _model().transcribe(
                io.BytesIO(audio), language="en", beam_size=1, vad_filter=True, initial_prompt=(_HINT + " " + extra_hint).strip()
            )
            text = " ".join(seg.text.strip() for seg in segments)
    return _fix_words(_fix_cars(text.strip(), extra_hint))


# Whisper hears an Australian "labour" as "label" (seen live); nothing in a
# workshop job is a "label", so put it back. Parakeet spells it the American way.
_FIXES = [
    (re.compile(r"\blabels?\b", re.I), "labour"),
    (re.compile(r"\blabor\b", re.I), "labour"),
    (re.compile(r"\$(?=\d)"), " $"),  # Parakeet runs "labour$280" together
    (re.compile(r"\b(CX|BT|MX|HR|CR|RAV|ASX|XC)\s?(\d{1,2})\b", re.I), lambda m: f"{m[1].upper()}-{m[2]}"),
    (re.compile(r"\bex-?trail\b", re.I), "X-Trail"),
    (re.compile(r"  +"), " "),
]


def _fix_words(text: str) -> str:
    for pattern, word in _FIXES:
        text = pattern.sub(word, text)
    return text.strip()


# The cars an Australian workshop sees most. With the cars in the shop today
# (the hint routes.py builds) they let a misheard make or model be put back from
# the word next to it: "Master CX-5" is a Mazda, "Nissan X-ray" is an X-Trail.
_MODELS = {
    "Toyota": "Corolla Camry Hilux RAV4 RAV-4 Prado LandCruiser Yaris Kluger Aurion Echo Tarago HiAce C-HR",
    "Mazda": "CX-3 CX-30 CX-5 CX-8 CX-9 BT-50 MX-5 Mazda2 Mazda3 Mazda6 Tribute",
    "Nissan": "X-Trail Navara Patrol Qashqai Pathfinder Pulsar Micra Juke Leaf Tiida Dualis",
    "Holden": "Commodore Colorado Cruze Captiva Barina Astra Trax Calais Rodeo",
    "Ford": "Ranger Falcon Territory Focus Fiesta Everest Escape Mondeo Kuga Transit",
    "Hyundai": "i30 Tucson Santa Kona Accent Elantra Getz Venue Ioniq Palisade",
    "Kia": "Cerato Sportage Sorento Rio Picanto Seltos Carnival Stonic",
    "Mitsubishi": "Triton Outlander Lancer Pajero ASX Eclipse Mirage",
    "Honda": "Civic Accord CR-V HR-V Jazz Odyssey City",
    "Subaru": "Forester Outback Impreza XV Liberty WRX BRZ",
    "Volkswagen": "Golf Polo Tiguan Amarok Passat Transporter",
    "Isuzu": "D-Max MU-X",
    "Suzuki": "Swift Vitara Jimny Baleno",
}
_REGO = re.compile(r"^[A-Z0-9]{5,7}$")


def _shop_models(extra_hint: str) -> dict[str, set[str]]:
    models = {make: set(names.split()) for make, names in _MODELS.items()}
    # "Cars in the workshop: Toyota Corolla ABC123, Mazda CX-5 1KR9ZZ."
    for car in re.sub(r"^.*?:", "", extra_hint).strip(" .").split(","):
        words = car.split()
        if len(words) >= 2 and not _REGO.match(words[1]):
            models.setdefault(words[0].title(), set()).add(words[1])
    return models


def _like(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _fix_regos(text: str, extra_hint: str) -> str:
    """Parakeet says a plate in pieces ("ABC 123"); join it when it's a car in the shop
    or reads like a plate (three capital letters, three digits)."""
    regos = {w.strip(".,") for w in extra_hint.split() if _REGO.match(w.strip(".,")) and re.search(r"\d", w)}
    words, out, i = text.split(" "), [], 0
    while i < len(words):
        for n in (3, 2):
            parts = words[i:i + n]
            cores = [re.sub(r"[.,!?;:]+$", "", w) for w in parts]
            # short pieces, and no full stop or comma inside the plate
            if len(parts) < n or any(not c.isalnum() or len(c) > 4 for c in cores) or cores[:-1] != parts[:-1]:
                continue
            joined = "".join(cores)  # the model capitalises plate letters; "and 350" isn't one
            if joined.upper() in regos or re.fullmatch(r"[A-Z]{3}\d{3}", joined):
                joined = joined.upper()
                out.append(joined + parts[-1][len(cores[-1]):])
                i += n
                break
        else:
            out.append(words[i])
            i += 1
    return " ".join(out)


def _fix_cars(text: str, extra_hint: str = "") -> str:
    text = _fix_regos(text, extra_hint)
    models = _shop_models(extra_hint)
    make_of = {m.lower().replace("-", ""): make for make, ms in models.items() for m in ms}
    makes = {make.lower(): make for make in models}
    words = text.split(" ")
    for i in range(len(words) - 1):
        word, nxt = words[i], words[i + 1]
        core, tail = re.match(r"^(.*?)([.,!?;:]*)$", word).groups()
        nxt_core = re.sub(r"[.,!?;:]+$", "", nxt)
        make = make_of.get(nxt_core.lower().replace("-", ""))
        # a known model after a word that sounds like its make ("Master CX-5")
        if make and core.lower() not in makes and core[:1].lower() == make[0].lower() and _like(core, make) >= 0.3:
            words[i] = make + tail
            continue
        # a make before a word that sounds like one of its models ("Nissan X-ray")
        if core.lower() in makes and not make:
            best = max(models[makes[core.lower()]], key=lambda m: _like(nxt_core, m))
            if _like(nxt_core, best) >= 0.6 and nxt_core[:1].lower() == best[0].lower():
                words[i + 1] = best + nxt[len(nxt_core):]
    return " ".join(words)


def warm_up() -> None:
    """Load the model in the background at start-up so his first recording isn't slow."""
    if _mock() or not _installed():
        return
    threading.Thread(target=_model, daemon=True).start()
