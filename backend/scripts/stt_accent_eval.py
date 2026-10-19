"""How well the server hears accented English: shop lines said by Kokoro voices whose
first language isn't English, with a little shop noise, transcribed by the speech
model this server is set to (STT_ENGINE), before and after the shop-word fixes.

"mild" voices read English with English sounds and a foreign voice (Mandarin, Hindi,
Japanese, Spanish, Italian, Portuguese, French speakers); "heavy" ones read it with
their own language's sounds, which is harsher than most real speakers. Native
American and British voices are the baseline.

    cd backend && STT_ENGINE=parakeet python scripts/stt_accent_eval.py
    cd backend && STT_ENGINE=whisper  python scripts/stt_accent_eval.py

Needs the stt and tts extras and the Kokoro files (TTS_MODEL_DIR), as in the Docker image.
"""

from __future__ import annotations

import os
import re
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("LLM_MODE", "nebius")  # mock mode would skip the real model

import numpy as np

from app.agent import stt
from app.voice import tts

LINES = [
    "Corolla ABC123, front pads, hour and a half, 350 all up",
    "find yesterday's jobs and prepare the tax invoice",
    "make a tax invoice for the CX-5",
    "invoice the Nissan X-Trail for Dan",
    "add an extra item to this invoice",
    "order front brake rotors and engine oil for a 2012 Toyota Corolla",
    "front rotors for the Mazda, rego 1KR9ZZ, the owner is Jack Thompson",
    "the Hilux needs a timing belt and a water pump",
    "logbook service on the Kia Cerato, two hours labour",
    "oil and filter change, 180 all up",
    "what jobs have we got on the hoist today",
    "who still owes us money",
    "the Commodore is done, text the customer",
    "same as last time for Liam's Ranger",
    "replace the battery and charge three hundred dollars",
    "rear brake pads and machined the discs on the Subaru Forester",
    "the Honda Civic has a check engine light, scanned and cleared the codes",
    "make it 380 all up",
    "four new tyres and a wheel alignment for the Hyundai i30",
    "mark the X-Trail paid by EFTPOS",
    "roadworthy certificate for the Mazda CX-5",
    "replaced the radiator hose and topped up the coolant",
    "half an hour labour plus parts for the wiper blades",
    "do the invoice for rego D W 4 5 2 1",
]
HINT = (
    "Cars in the workshop: Nissan X-Trail DW4521, Toyota Corolla ABC123, Mazda CX-5 1KR9ZZ, "
    "Ford Ranger LOC777, Kia Cerato SR2020, Honda Civic AH5566, Subaru Forester GC8899."
)
# (voice, how it reads English, tier)
VOICES = [
    ("zm_yunxi", "en-us", "mild"), ("zf_xiaoxiao", "en-us", "mild"), ("hm_omega", "en-us", "mild"),
    ("jm_kumo", "en-us", "mild"), ("zm_yunjian", "cmn", "heavy"), ("hf_alpha", "hi", "heavy"),
    ("ef_dora", "es", "heavy"), ("im_nicola", "it", "heavy"), ("pm_alex", "pt-br", "heavy"),
    ("ff_siwis", "fr-fr", "heavy"), ("am_adam", "en-us", "native"), ("bm_george", "en-gb", "native"),
]
_NUM = {"zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9"}


def norm(t: str) -> list[str]:
    t = t.lower().replace("$", " ").replace("-", " ").replace("'s", "s").replace("labor", "labour").replace("tires", "tyres")
    t = re.sub(r"(\d),(\d)", r"\1\2", t)
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    t = re.sub(r"(?<=[a-z])(?=\d)|(?<=\d)(?=[a-z])", " ", t)
    out: list[str] = []
    for w in (_NUM.get(x, x) for x in t.split()):
        out.extend(list(w) if w.isdigit() or (len(w) <= 3 and not w.isalpha()) else [w])
    return out


def edits(ref: list[str], hyp: list[str]) -> int:
    row = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        prev, row[0] = row[0], i
        for j, h in enumerate(hyp, 1):
            prev, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, prev + (r != h))
    return row[-1]


def clip(engine, text: str, voice: str, lang: str, rng) -> bytes:
    s, sr = engine.create(text, voice=voice, speed=float(rng.uniform(0.9, 1.1)), lang=lang)
    idx = np.round(np.arange(0, len(s), sr / 16000)).astype(int)
    s = s[idx[idx < len(s)]]
    pad = np.zeros(int(16000 * rng.uniform(0.2, 0.6)), dtype=np.float32)
    s = np.concatenate([pad, s, pad])
    s = s + rng.normal(0, 1, len(s)) * np.sqrt(np.mean(s**2) / 10 ** (rng.uniform(12, 25) / 10))
    return tts._wav(s.astype(np.float32), 16000)


def main() -> None:
    import faster_whisper.audio  # noqa: F401  (decodes the clips like the phone's audio)

    rng = np.random.default_rng(7)
    voice = tts._load()
    stt._model()  # load first so the timing is per recording
    totals: dict[str, list[float]] = {}
    for vi, (name, lang, tier) in enumerate(VOICES):
        for li, line in enumerate(LINES):
            if (li + vi) % 2:  # half the lines per voice
                continue
            wav = clip(voice, line, name, lang, rng)
            t0 = time.time()
            raw = stt.transcribe(wav, HINT, fix=False)
            secs = time.time() - t0
            fixed = stt.fix_heard(raw, HINT)
            ref = norm(line)
            t = totals.setdefault(tier, [0, 0, 0, 0.0, 0])
            t[0] += len(ref)
            t[1] += edits(ref, norm(raw))
            t[2] += edits(ref, norm(fixed))
            t[3] += secs
            t[4] += 1
            if "-v" in sys.argv:
                print(f"{name}/{lang}: {line!r}\n   heard {raw!r}\n   fixed {fixed!r}")
    print(f"engine {stt.engine()}")
    for tier, (words, e_raw, e_fix, secs, n) in totals.items():
        print(f"{tier:6s} {n:3d} clips  word errors {e_raw / words:6.1%} -> after shop fixes {e_fix / words:6.1%}   {secs / n:.2f} s a clip")
    w = sum(t[0] for t in totals.values())
    print(f"all    word errors {sum(t[1] for t in totals.values()) / w:6.1%} -> {sum(t[2] for t in totals.values()) / w:6.1%}")


if __name__ == "__main__":
    main()
