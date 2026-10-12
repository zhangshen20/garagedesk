"""Draw the sample job-card photos used by the vision tests and the demo.

The owner writes job cards on paper, so these imitate that: a printed shop form
filled in by hand in blue biro, photographed slightly crooked on a bench. The
"handwriting" is a slanted font with per-letter jitter, which is close enough to
exercise the vision model; real phone photos can be dropped into the same folder.

    python backend/scripts/make_sample_jobcards.py

Writes backend/app/vision/samples/<name>.jpg plus <name>.json (the ground truth)."""

from __future__ import annotations

import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = Path(__file__).resolve().parents[1] / "app" / "vision" / "samples"

FONT_DIRS = ["/usr/share/fonts/truetype", "/usr/share/fonts/opentype", "/Library/Fonts", "/System/Library/Fonts"]


def _font(names: list[str], size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for d in FONT_DIRS:
        for p in Path(d).rglob("*") if Path(d).exists() else []:
            if p.name in names:
                return ImageFont.truetype(str(p), size)
    return ImageFont.load_default(size)


PRINT = ["LiberationSans-Bold.ttf", "DejaVuSans-Bold.ttf", "Arial Bold.ttf"]
PRINT_REG = ["LiberationSans-Regular.ttf", "DejaVuSans.ttf", "Arial.ttf"]
HAND = ["FreeSansOblique.ttf", "LiberationSans-Italic.ttf", "DejaVuSans-Oblique.ttf", "Noteworthy.ttc"]

INK = (28, 52, 140)
PAPER = (246, 242, 230)


def handwrite(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, size: int, rnd: random.Random, mess: float) -> None:
    """Letter by letter with wobble in baseline, size and spacing."""
    x, y = xy
    for ch in text:
        s = max(10, int(size * (1 + rnd.uniform(-0.04, 0.04) * (1 + mess))))
        f = _font(HAND, s)
        dy = rnd.uniform(-1.5, 1.5) * (1 + mess * 2)
        draw.text((x, y + size + dy), ch, font=f, fill=INK, anchor="ls")
        w = draw.textlength(ch, font=f)
        x += w * rnd.uniform(0.9, 1.05) + (rnd.uniform(0, 2) * mess)


def card(fields: dict[str, str], *, seed: int, mess: float, angle: float, blur: float, dim: float = 1.0) -> Image.Image:
    rnd = random.Random(seed)
    W, H = 1240, 1650
    im = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(im)
    d.text((60, 50), "SUNSHINE NORTH MECHANIC", font=_font(PRINT, 52), fill=(20, 20, 20))
    d.text((60, 115), "17 Whitehill Ave, Sunshine North VIC 3020   ·   JOB CARD", font=_font(PRINT_REG, 28), fill=(60, 60, 60))
    d.line((60, 160, W - 60, 160), fill=(30, 30, 30), width=3)

    label_f = _font(PRINT, 26)
    rows = [
        ("Date", "date"),
        ("Customer", "customer_name"),
        ("Phone", "phone"),
        ("Vehicle", "vehicle"),
        ("Rego", "rego"),
        ("Odometer", "odometer"),
    ]
    y = 200
    for label, key in rows:
        d.text((60, y + 18), label + ":", font=label_f, fill=(40, 40, 40))
        d.line((260, y + 60, W - 60, y + 60), fill=(150, 150, 150), width=2)
        if fields.get(key):
            handwrite(d, (280 + rnd.randint(-6, 12), y + 8), fields[key], 44, rnd, mess)
        y += 80

    def block(title: str, key: str, n_lines: int) -> None:
        nonlocal y
        y += 20
        d.text((60, y), title, font=label_f, fill=(40, 40, 40))
        y += 40
        lines = fields.get(key, "").split("\n") if fields.get(key) else []
        for i in range(n_lines):
            d.line((60, y + 58, W - 60, y + 58), fill=(170, 170, 200), width=2)
            if i < len(lines):
                handwrite(d, (80 + rnd.randint(-4, 14), y + 6), lines[i], 42, rnd, mess)
            y += 66

    block("WORK DONE", "work", 4)
    block("PARTS", "parts", 3)
    y += 20
    d.text((60, y + 18), "Labour hrs:", font=label_f, fill=(40, 40, 40))
    d.line((260, y + 60, 560, y + 60), fill=(150, 150, 150), width=2)
    handwrite(d, (285, y + 8), fields.get("labour", ""), 44, rnd, mess)
    d.text((620, y + 18), "Mechanic:", font=label_f, fill=(40, 40, 40))
    d.line((780, y + 60, W - 60, y + 60), fill=(150, 150, 150), width=2)
    handwrite(d, (800, y + 8), fields.get("mechanic", ""), 44, rnd, mess)
    y += 90
    block("NOTES", "notes", 2)

    # grime: a coffee ring and a thumb smudge on the messy ones
    if mess > 0.5:
        ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
        od = ImageDraw.Draw(ov)
        od.ellipse((W - 380, H - 420, W - 120, H - 160), outline=(120, 80, 40, 70), width=14)
        od.ellipse((140, 900, 260, 980), fill=(60, 60, 60, 40))
        im = Image.alpha_composite(im.convert("RGBA"), ov.filter(ImageFilter.GaussianBlur(6))).convert("RGB")

    # put it on a workbench and photograph it crooked
    bench = Image.new("RGB", (W + 300, H + 300), (92, 84, 76))
    bench.paste(im, (150, 150))
    bench = bench.rotate(angle, resample=Image.BICUBIC, fillcolor=(92, 84, 76))
    if blur:
        bench = bench.filter(ImageFilter.GaussianBlur(blur))
    if dim < 1.0:
        # workshop light: darker, warmer, with a shadow falling across the card
        from PIL import ImageEnhance

        bench = ImageEnhance.Brightness(bench).enhance(dim)
        shade = Image.linear_gradient("L").rotate(35, expand=True).resize(bench.size)
        bench = Image.composite(bench, ImageEnhance.Brightness(bench).enhance(0.55), shade)
    scale = 2 if dim < 1.0 else 3
    return bench.resize((bench.width * scale // 4, bench.height * scale // 4))


SAMPLES = [
    {
        "name": "card_neat_service",
        "seed": 1,
        "mess": 0.1,
        "angle": -1.5,
        "blur": 0.0,
        "fields": {
            "date": "12/10/26",
            "customer_name": "Maria Nguyen",
            "phone": "0412 345 678",
            "vehicle": "Toyota Corolla 2017",
            "rego": "ABC123",
            "odometer": "84,210 km",
            "work": "Logbook service 90,000\nReplace front brake pads\nTop up coolant",
            "parts": "Oil filter x1\nEngine oil 5W-30 5L\nFront brake pads (Bendix) x1 set",
            "labour": "2.5",
            "mechanic": "Tony",
            "notes": "Rear tyres getting low, told cust",
        },
        "expected": {
            "customer_name": "Maria Nguyen",
            "phone": "0412345678",
            "vehicle": {"make": "Toyota", "model": "Corolla", "year": 2017},
            "rego": "ABC123",
            "odometer_km": 84210,
            "labour_hours": 2.5,
            "parts": ["oil filter", "engine oil", "brake pads"],
            "work": ["logbook service", "brake pads", "coolant"],
        },
    },
    {
        "name": "card_messy_brakes",
        "seed": 7,
        "mess": 0.9,
        "angle": 4.0,
        "blur": 1.2,
        "fields": {
            "date": "12/10",
            "customer_name": "Dave Kowalski",
            "phone": "0433 908 117",
            "vehicle": "Ford Ranger",
            "rego": "1XY 9KL",
            "odometer": "",
            "work": "F + R pads & machine rotors\nBrake fluid flush",
            "parts": "Pads F & R\nDOT4 1L",
            "labour": "1 1/2",
            "mechanic": "Sam",
            "notes": "Cust waiting - call when done",
        },
        "expected": {
            "customer_name": "Dave Kowalski",
            "phone": "0433908117",
            "vehicle": {"make": "Ford", "model": "Ranger", "year": None},
            "rego": "1XY9KL",
            "odometer_km": None,
            "labour_hours": 1.5,
            "parts": ["pads", "dot4"],
            "work": ["pads", "rotors", "brake fluid"],
        },
    },
    {
        "name": "card_partial_battery",
        "seed": 3,
        "mess": 0.4,
        "angle": -3.0,
        "blur": 0.6,
        "fields": {
            "date": "12/10/26",
            "customer_name": "J. Patel",
            "phone": "",
            "vehicle": "Mazda 3",
            "rego": "DEF456",
            "odometer": "",
            "work": "Replace battery\nTest charging system OK",
            "parts": "Battery DIN55 x1",
            "labour": "0.5",
            "mechanic": "",
            "notes": "",
        },
        "expected": {
            "customer_name": "J. Patel",
            "phone": None,
            "vehicle": {"make": "Mazda", "model": "3", "year": None},
            "rego": "DEF456",
            "odometer_km": None,
            "labour_hours": 0.5,
            "parts": ["battery"],
            "work": ["battery"],
        },
    },
    {
        "name": "card_dim_tyres",
        "seed": 11,
        "mess": 1.0,
        "angle": 7.0,
        "blur": 2.0,
        "dim": 0.6,
        "quality": 45,
        "fields": {
            "date": "13/10",
            "customer_name": "Sione Tupou",
            "phone": "0450 118 562",
            "vehicle": "Hyundai i30 2014",
            "rego": "XYZ789",
            "odometer": "143k",
            "work": "2 x front tyres fitted + balance\nWheel alignment",
            "parts": "Tyre 205/55R16 x2",
            "labour": "1",
            "mechanic": "Tony",
            "notes": "",
        },
        "expected": {
            "customer_name": "Sione Tupou",
            "phone": "0450118562",
            "vehicle": {"make": "Hyundai", "model": "i30", "year": 2014},
            "rego": "XYZ789",
            "odometer_km": 143000,
            "labour_hours": 1.0,
            "parts": ["tyre"],
            "work": ["tyre", "alignment"],
        },
    },
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for s in SAMPLES:
        im = card(s["fields"], seed=s["seed"], mess=s["mess"], angle=s["angle"], blur=s["blur"], dim=s.get("dim", 1.0))
        im.save(OUT / f"{s['name']}.jpg", quality=s.get("quality", 72))
        (OUT / f"{s['name']}.json").write_text(
            json.dumps({"written": s["fields"], "expected": s["expected"]}, indent=2) + "\n"
        )
        print("wrote", OUT / f"{s['name']}.jpg")


if __name__ == "__main__":
    main()
