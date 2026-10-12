"""Turn a draft invoice into the few words he needs to hear.

The written read-back (jobcard.readback) stays on screen with every line and cent.
Out loud he only needs enough to know it's the right car and the right money, the
way his wife would have repeated it back on the phone, then the obvious next step."""

from __future__ import annotations

import re
from typing import Any

from ..config import get_settings

_ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def words(n: int) -> str:
    """Australian number words: 350 -> "three hundred and fifty"."""
    if n < 0:
        return "minus " + words(-n)
    if n < 20:
        return _ONES[n]
    if n < 100:
        t, o = divmod(n, 10)
        return _TENS[t] + (f"-{_ONES[o]}" if o else "")
    if n < 1000:
        h, r = divmod(n, 100)
        return f"{_ONES[h]} hundred" + (f" and {words(r)}" if r else "")
    for size, name in ((1_000_000, "million"), (1000, "thousand")):
        if n >= size:
            big, r = divmod(n, size)
            tail = "" if not r else (f" and {words(r)}" if r < 100 else f" {words(r)}")
            return f"{words(big)} {name}{tail}"
    return str(n)


def dollars(cents: int) -> str:
    """35000 -> "three hundred and fifty dollars"; 21910 -> "two hundred and nineteen dollars ten"."""
    d, c = divmod(int(round(cents)), 100)
    out = f"{words(d)} dollar{'s' if d != 1 else ''}"
    return out + (f" {words(c)}" if c else "")


def hours(h: float) -> str:
    whole, frac = int(h), round(h - int(h), 2)
    part = {0.25: "a quarter", 0.5: "a half", 0.75: "three quarters"}.get(frac)
    if frac == 0:
        return "an hour" if whole == 1 else f"{words(whole)} hours"
    if not part:
        return f"{h:g} hours"
    if whole == 0:
        return "half an hour" if frac == 0.5 else f"{part} of an hour"
    if whole == 1:
        return f"an hour and {part}"
    return f"{words(whole)} and {part} hours"


def car_name(vehicle: str) -> str:
    """"Toyota Corolla ABC123" -> "Corolla": the word he'd use in the workshop."""
    parts = vehicle.split()
    return parts[1] if len(parts) >= 2 else (parts[0] if parts else "car")


def first_name(customer: str) -> str:
    return (customer or "").split()[0] if (customer or "").strip() else ""


def approver() -> str:
    return get_settings().approver_name or "the office"


def ask_send() -> str:
    return f"Send it to {approver()}?"


_SIDES = {"front", "rear", "left", "right", "lh", "rh"}


def _item(line: dict[str, Any]) -> str:
    desc = line["description"]
    if line["kind"] == "labour":
        # a total said "all up" puts the balance on one labour line: "Pads etc (1.5 hrs)"
        m = re.search(r"\(([\d.]+) hrs?\)", desc)
        h = float(m.group(1)) if m else float(line["qty"])
        return f"{hours(h)} labour"
    name = desc.split(" - ")[0].split("(")[0].strip().lower()
    # catalogue names read backwards ("brake pads front"); say it the shop way
    w = name.split()
    if len(w) > 1 and w[-1] in _SIDES:
        name = " ".join([w[-1], *w[:-1]])
    return name


def draft_say(view: dict[str, Any], warnings: list[str]) -> str:
    """Maria's Corolla. Front pads and an hour and a half labour. Three hundred and fifty
    dollars all up. Send it to Jenny?"""
    first = first_name(view.get("customer", ""))
    car = car_name(view.get("vehicle", ""))
    head = f"{first}'s {car}." if first else f"The {car}."
    lines = sorted(view.get("lines", []), key=lambda l: l["kind"] == "labour")
    items = [_item(l) for l in lines]
    if len(items) > 3:
        items = items[:2] + [f"{words(len(items) - 2)} more"]
    said = (", ".join(items[:-1]) + " and " + items[-1]) if len(items) > 1 else (items[0] if items else "")
    body = f" {said[:1].upper()}{said[1:]}." if said else ""
    total = f" {dollars(view.get('total_cents', 0))[:1].upper()}{dollars(view.get('total_cents', 0))[1:]} all up."
    if warnings:
        return f"{head}{body}{total} " + " ".join(say_money(w) for w in warnings) + " Say it again to fix it."
    return f"{head}{body}{total} {ask_send()}"


_MONEY = re.compile(r"\$?(\d[\d,]*)\.(\d\d)(?: dollars)?")


def say_money(text: str) -> str:
    """Text written for the screen, with its money said as words."""
    def m(x: re.Match[str]) -> str:
        return dollars(int(x.group(1).replace(",", "")) * 100 + int(x.group(2)))

    return _MONEY.sub(m, text)


def sentences(text: str) -> list[str]:
    """How the phone asks for audio: one sentence at a time, so the first one plays
    while the rest are still being made. The page splits the same way."""
    out = []
    for line in text.split("\n"):
        line = re.sub(r"\s+", " ", re.sub(r"[*_`#>]", "", line)).strip()
        out += [p for p in re.split(r"(?<=[.?!])\s+", line) if p]
    return out
