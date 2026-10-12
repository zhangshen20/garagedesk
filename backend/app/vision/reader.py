"""Step 1: read the handwriting.

Two vision models on Nebius Token Factory read the same photo in parallel. Where
they agree we trust the reading; where they differ the owner gets asked. Neither
model corrects anything at this stage: they copy what is written."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from ..config import get_settings

log = logging.getLogger(__name__)

SAMPLES_DIR = Path(__file__).parent / "samples"

# MiniCPM-V 4.5 is the quickest accurate reader on Token Factory (about 2s a card);
# Qwen3.8-27B is the second opinion. Override with JOBCARD_VISION_MODELS.
DEFAULT_MODELS = "openbmb/MiniCPM-V-4_5,Qwen/Qwen3.8-27B"

KEYS = [
    "customer",
    "phone",
    "vehicle",
    "rego",
    "odometer",
    "work_done",
    "parts",
    "labour_hours",
    "mechanic",
    "notes",
    "other",
]

PROMPT = """You are reading a photo of a car mechanic's paper job card.
Copy what is handwritten in each box EXACTLY as written: keep abbreviations, spelling
mistakes, spacing and punctuation. Do not correct, expand or guess. Use "" for an empty box.

Reply with JSON only, these keys:
  "is_job_card": true/false (false if the photo is not a job card or work sheet),
  "customer", "phone", "vehicle", "rego", "odometer",
  "work_done": [one string per written line],
  "parts": [one string per written line],
  "labour_hours", "mechanic", "notes",
  "other": [anything else written on the card, e.g. prices or "paid EFTPOS", one string per line],
  "unclear": [keys of any box where a character was hard to read]"""

MAX_SIDE = 1600


def vision_models() -> list[str]:
    raw = os.environ.get("JOBCARD_VISION_MODELS", DEFAULT_MODELS)
    return [m.strip() for m in raw.split(",") if m.strip()]


def prepare_image(data: bytes) -> bytes:
    """Upright, at most 1600px, JPEG. iPhone photos carry rotation in EXIF and are
    often 4000px+, which costs tokens and time for no gain in legibility."""
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        im = Image.open(io.BytesIO(data))
        im = ImageOps.exif_transpose(im)
    except (UnidentifiedImageError, OSError) as e:
        raise ValueError("That file isn't a photo I can open. Try taking the picture again.") from e
    im = im.convert("RGB")
    im.thumbnail((MAX_SIDE, MAX_SIDE))
    out = io.BytesIO()
    im.save(out, format="JPEG", quality=85)
    return out.getvalue()


def parse_json(text: str | None) -> dict[str, Any]:
    """Models wrap JSON in code fences or add a sentence; take the outermost object."""
    if not text:
        return {}
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        v = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {}
    return v if isinstance(v, dict) else {}


def clean_reading(d: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k in KEYS:
        v = d.get(k)
        if k in ("work_done", "parts", "other"):
            if isinstance(v, str):
                v = [x for x in v.split("\n")]
            out[k] = [str(x).strip() for x in (v or []) if str(x).strip()]
        else:
            out[k] = "" if v is None else str(v).strip()
    out["unclear"] = [str(x) for x in (d.get("unclear") or []) if str(x) in KEYS]
    out["is_job_card"] = d.get("is_job_card", True) is not False
    return out


def _read_one(model: str, jpeg: bytes) -> dict[str, Any]:
    from openai import OpenAI

    s = get_settings()
    client = OpenAI(api_key=s.nebius_api_key, base_url=s.nebius_base_url, timeout=60)
    url = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()
    resp = client.chat.completions.create(
        model=model,
        temperature=0,
        max_tokens=1500,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {"type": "image_url", "image_url": {"url": url}},
                ],
            }
        ],
    )
    parsed = parse_json(resp.choices[0].message.content)
    if not parsed:
        raise ValueError(f"{model} returned no readable JSON")
    return {"model": model, **clean_reading(parsed)}


def read_card(original: bytes, jpeg: bytes) -> list[dict[str, Any]]:
    """Every configured vision model's reading of the card. Failures are dropped,
    so one slow or broken model never blocks the owner."""
    if get_settings().effective_llm_mode != "nebius":
        return mock_read(original)
    models = vision_models()
    readings: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=len(models)) as ex:
        futures = {m: ex.submit(_read_one, m, jpeg) for m in models}
        for m, f in futures.items():
            try:
                readings.append(f.result())
            except Exception as e:  # noqa: BLE001  any model error just drops that reader
                log.warning("vision model %s failed: %s", m, e)
    return readings


# --------------------------------------------------------------------------------------
# Mock mode: the bundled sample cards come with what was written on them, so the
# demo and the tests run the whole pipeline without a key.
# --------------------------------------------------------------------------------------

_FROM_SAMPLE = {
    "customer_name": "customer",
    "phone": "phone",
    "vehicle": "vehicle",
    "rego": "rego",
    "odometer": "odometer",
    "labour": "labour_hours",
    "mechanic": "mechanic",
    "notes": "notes",
}


def sample_names() -> list[str]:
    return sorted(p.stem for p in SAMPLES_DIR.glob("*.jpg"))


def _sample_index() -> dict[str, str]:
    return {hashlib.sha256(p.read_bytes()).hexdigest(): p.stem for p in SAMPLES_DIR.glob("*.jpg")}


def mock_read(original: bytes) -> list[dict[str, Any]]:
    name = _sample_index().get(hashlib.sha256(original).hexdigest())
    if not name:
        return []
    written = json.loads((SAMPLES_DIR / f"{name}.json").read_text())["written"]
    r: dict[str, Any] = {v: written.get(k, "") for k, v in _FROM_SAMPLE.items()}
    r["work_done"] = [x for x in written.get("work", "").split("\n") if x]
    r["parts"] = [x for x in written.get("parts", "").split("\n") if x]
    r["other"] = [x for x in written.get("other", "").split("\n") if x]
    r["unclear"] = []
    r["is_job_card"] = True
    return [{"model": f"mock/{m.split('/')[-1]}", **r} for m in vision_models()]
