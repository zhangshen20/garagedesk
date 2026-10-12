"""Step 2 helpers: turn what was written into clean values, and check them.

These run in every mode. With a key, Nemotron 3 Super does the tidying (it copes
with "F + R pads & machine rotors" far better than regexes) and these parsers
validate its answer; without a key they do the tidying themselves."""

from __future__ import annotations

import re
from fractions import Fraction
from typing import Any

MAKES = {
    "toyota": "Toyota", "mazda": "Mazda", "hyundai": "Hyundai", "kia": "Kia", "ford": "Ford",
    "holden": "Holden", "honda": "Honda", "nissan": "Nissan", "subaru": "Subaru", "vw": "Volkswagen",
    "volkswagen": "Volkswagen", "bmw": "BMW", "mercedes": "Mercedes-Benz", "merc": "Mercedes-Benz",
    "tesla": "Tesla", "mitsubishi": "Mitsubishi", "suzuki": "Suzuki", "isuzu": "Isuzu", "audi": "Audi",
    "lexus": "Lexus", "jeep": "Jeep", "volvo": "Volvo", "skoda": "Skoda", "renault": "Renault",
    "peugeot": "Peugeot", "mg": "MG", "byd": "BYD", "gwm": "GWM", "haval": "Haval", "ldv": "LDV",
}


def canon(v: Any) -> str:
    """Comparison key: case, spaces and punctuation don't count as disagreement."""
    if isinstance(v, list):
        return "|".join(canon(x) for x in v)
    return re.sub(r"[^a-z0-9/]", "", str(v or "").lower())


def phone(raw: str) -> tuple[str | None, bool]:
    """-> (E.164, looks valid). Australian mobiles and landlines."""
    digits = re.sub(r"[^\d+]", "", raw or "")
    if not digits:
        return None, False
    if digits.startswith("+61"):
        digits = "0" + digits[3:]
    elif digits.startswith("61") and len(digits) == 11:
        digits = "0" + digits[2:]
    ok = bool(re.fullmatch(r"0[2-478]\d{8}", digits))
    return ("+61" + digits[1:] if ok else digits), ok


def rego(raw: str) -> tuple[str | None, bool]:
    r = re.sub(r"[^A-Z0-9]", "", (raw or "").upper())
    if not r:
        return None, False
    return r, 2 <= len(r) <= 7


def vehicle(raw: str) -> tuple[dict[str, Any] | None, bool]:
    words = (raw or "").replace(",", " ").split()
    if not words:
        return None, False
    year = None
    rest = []
    for w in words:
        if re.fullmatch(r"(19[6-9]\d|20[0-4]\d)", w):
            year = int(w)
        else:
            rest.append(w)
    if not rest:
        return {"make": "", "model": "", "year": year}, False
    make = MAKES.get(rest[0].lower())
    if make:
        model = " ".join(rest[1:])
    else:
        make, model = rest[0].title(), " ".join(rest[1:])
    return {"make": make, "model": model, "year": year}, bool(make and model)


def hours(raw: str) -> tuple[float | None, bool]:
    """'2.5', '1 1/2', '1½', '1h30', '90 min', '1hr 30m' -> hours."""
    t = (raw or "").lower().replace("½", " 1/2").replace("¼", " 1/4").replace("¾", " 3/4").strip()
    if not t:
        return None, False
    m = re.fullmatch(r"(\d+)\s*(?:h|hr|hrs|hours?)\s*(\d+)\s*(?:m|min|mins)?", t)
    if m:
        h = int(m.group(1)) + int(m.group(2)) / 60
    elif m := re.fullmatch(r"(\d+)\s*(?:m|min|mins|minutes)", t):
        h = int(m.group(1)) / 60
    else:
        t = re.sub(r"\s*(?:h|hr|hrs|hours?)\.?$", "", t)
        try:
            h = float(sum(Fraction(p) for p in t.split()))
        except (ValueError, ZeroDivisionError):
            return None, False
    h = round(h, 2)
    return h, 0 < h <= 16


def odometer(raw: str) -> tuple[int | None, bool]:
    t = (raw or "").lower().replace(",", "").replace(" ", "")
    if not t:
        return None, False
    m = re.match(r"(\d+(?:\.\d+)?)(k(?!m))?", t)
    if not m:
        return None, False
    km = float(m.group(1)) * (1000 if m.group(2) else 1)
    return int(km), 0 < km < 1_500_000


def price(raw: str) -> tuple[str, float | None]:
    """'Pads $119' -> ('Pads', 119.0). Only a figure with a dollar sign counts."""
    m = re.search(r"\$\s*(\d+(?:,\d{3})*(?:\.\d{1,2})?)", raw or "")
    if not m:
        return raw, None
    return (raw[: m.start()] + raw[m.end() :]).strip(" -,:@"), float(m.group(1).replace(",", ""))


def paid_method(texts: list[str]) -> str:
    for t in texts:
        m = re.search(r"\bpaid\b.*?\b(eftpos|card|cash|transfer|eft|bank)\b", (t or "").lower())
        if m:
            return {"card": "eftpos", "eft": "eftpos", "bank": "transfer"}.get(m.group(1), m.group(1))
    return ""


def part_line(raw: str) -> tuple[str, float]:
    """'Oil filter x1' -> ('Oil filter', 1); '2 x wiper blades' -> ('wiper blades', 2).
    Litres and sizes ('5L', 'DIN55') are part of the description, not a quantity."""
    t = raw.strip()
    m = re.search(r"\s*[x×]\s*(\d+(?:\.\d+)?)\b(?:\s*(?:set|pair|pcs?))?\s*$", t, re.I)
    if m:
        return t[: m.start()].strip(" -,"), float(m.group(1))
    m = re.match(r"^(\d+)\s*[x×]\s+(.*)$", t, re.I)
    if m:
        return m.group(2).strip(), float(m.group(1))
    return t, 1.0


_STOP = {"the", "and", "of", "for", "a", "x", "set", "pair", "front", "rear", "f", "r", "l", "1l", "5l"}


def _tokens(s: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", s.lower())
    out = set()
    for w in words:
        if w in _STOP:
            continue
        out.add(w[:-1] if w.endswith("s") and len(w) > 3 else w)
    return out


def match_part(description: str, catalogue: list[dict[str, Any]], veh: dict[str, Any] | None) -> dict[str, Any] | None:
    """Best catalogue part for a written line, or None. A part named for one model
    ('Brake pads front - Toyota Corolla') never matches a different car."""
    want = _tokens(description)
    if not want:
        return None
    car = " ".join(str((veh or {}).get(k) or "") for k in ("make", "model")).lower()
    best, best_score = None, 0.0
    for p in catalogue:
        name = p["name"]
        base, _, fits = name.partition(" - ")
        if fits:
            fits_tokens = _tokens(fits)
            if car.strip() and not (fits_tokens & _tokens(car)):
                continue
            if not car.strip():
                continue
        have = _tokens(base)
        overlap = want & have
        if not overlap:
            continue
        score = len(overlap) / len(want | have)
        if score > best_score:
            best, best_score = p, score
    return best if best_score >= 0.3 else None
