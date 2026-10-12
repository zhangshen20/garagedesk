"""What a seasoned workshop owner knows without thinking: the common jobs and what
goes into them, the cars on Melbourne's roads (and how speech recognition mangles
their names), shop slang, and how a small workshop's day runs.

The agent consults this to make sense of half sentences ("did the pads on the
high lux, hour and a half") and to suggest the obvious next step. Labour times
here are typical book times for reference only: they never set a price. The
owner's figures and the shop's catalogue do that."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Service:
    name: str
    said_as: tuple[str, ...]  # how he says it, lower case
    hours: tuple[float, float]  # typical labour, small to mid-size car
    parts: tuple[str, ...] = ()
    checks: str = ""  # what a good mechanic looks at or mentions while he's there
    follow_up: str = ""  # what usually happens next for the customer
    not_when: tuple[str, ...] = ()  # words that mean he meant a different job


SERVICES: tuple[Service, ...] = (
    Service("Logbook service (minor)", ("logbook", "log book", "service", "minor service", "oil service", "general service"), (1.0, 1.5),
            ("engine oil", "oil filter", "sump plug washer"), "brake pad wear, tyres, wipers, globes, fluids, battery test", "next service in 10,000 km or 6 to 12 months"),
    Service("Major service", ("major service", "big service", "major"), (2.0, 3.5),
            ("engine oil", "oil filter", "air filter", "cabin filter", "spark plugs", "brake fluid"), "as minor service plus belts and coolant"),
    Service("Oil and filter change", ("oil change", "oil and filter", "oil n filter", "change the oil"), (0.5, 0.5), ("engine oil", "oil filter")),
    Service("Front brake pads", ("front pads", "front brake pads", "pads front", "brake pads", "pads", "break pads"), (1.0, 1.5),
            ("brake pads front",), "rotor thickness (machine or replace), rear pads, brake fluid", "rear pads often due at the next visit"),
    Service("Rear brake pads or shoes", ("rear pads", "rear brakes", "back brakes", "brake shoes", "shoes"), (1.0, 1.5), ("brake pads rear",), "handbrake adjustment"),
    Service("Machine rotors", ("machine the rotors", "machined", "skim", "skimmed", "machining", "turn the discs"), (0.5, 0.5), (), "minimum thickness stamped on the rotor"),
    Service("Replace rotors", ("rotors", "discs", "new rotors", "new discs"), (0.5, 1.0), ("brake rotors pair",), not_when=("machine", "machined", "machining", "skim", "skimmed")),
    Service("Brake fluid flush", ("brake fluid", "bleed the brakes", "flush the brakes"), (0.5, 1.0), ("brake fluid DOT4",)),
    Service("Battery replacement", ("battery", "new battery", "flat battery", "won't start"), (0.3, 0.5), ("battery",), "test the alternator charging and clean terminals"),
    Service("Tyres fitted and balanced", ("tyres", "tires", "new tyres", "fit and balance", "puncture"), (0.5, 1.0), ("tyre",), "wheel alignment after new front tyres", "rotate every 10,000 km"),
    Service("Wheel alignment", ("alignment", "wheel alignment", "pulling to the left", "pulling to the right"), (0.5, 1.0)),
    Service("Roadworthy certificate (RWC) inspection", ("roadworthy", "rwc", "road worthy", "certificate"), (1.0, 1.5), (),
            "VicRoads RWC checks: tyres, brakes, steering, suspension, lights, windscreen, wipers, seatbelts, leaks", "a fail means a list of defects to quote; the RWC is valid 30 days"),
    Service("Timing belt replacement", ("timing belt", "cam belt", "cambelt"), (3.0, 5.0), ("timing belt kit", "water pump"), "do the water pump at the same time"),
    Service("Clutch replacement", ("clutch",), (4.0, 7.0), ("clutch kit",), "flywheel machining or replacement, rear main seal"),
    Service("Spark plugs", ("spark plugs", "plugs"), (0.5, 1.5), ("spark plugs",)),
    Service("Air filter", ("air filter",), (0.2, 0.2), ("air filter",)),
    Service("Cabin filter", ("cabin filter", "pollen filter"), (0.2, 0.3), ("cabin filter",)),
    Service("Wiper blades", ("wipers", "wiper blades", "blades"), (0.1, 0.2), ("wiper blades pair",)),
    Service("Coolant flush", ("coolant", "radiator flush", "coolant flush"), (0.5, 1.0), ("coolant",), "hoses, radiator cap, water pump weep"),
    Service("Thermostat replacement", ("thermostat", "overheating"), (1.0, 2.0), ("thermostat", "coolant")),
    Service("Water pump replacement", ("water pump",), (2.0, 4.0), ("water pump", "coolant")),
    Service("Radiator replacement", ("radiator",), (1.5, 3.0), ("radiator", "coolant")),
    Service("Alternator replacement", ("alternator", "not charging", "battery light"), (1.0, 2.5), ("alternator",)),
    Service("Starter motor replacement", ("starter", "starter motor", "clicking"), (1.0, 2.5), ("starter motor",)),
    Service("Shock absorbers / struts", ("shocks", "shock absorbers", "struts"), (1.5, 3.0), ("shock absorbers pair",), "wheel alignment after front struts"),
    Service("CV joint or boot", ("cv", "cv joint", "cv boot", "drive shaft", "clicking when turning"), (1.0, 2.0), ("cv shaft",)),
    Service("Suspension bushes", ("bushes", "control arm", "sway bar link"), (1.0, 3.0)),
    Service("Exhaust repair", ("exhaust", "muffler", "centre pipe"), (0.5, 2.0)),
    Service("Air-conditioning regas", ("aircon", "air con", "regas", "ac not cold"), (0.5, 1.0), ("refrigerant",), "leak test with dye"),
    Service("Diagnostic scan", ("check engine light", "engine light", "diagnostic", "scan", "fault code", "cel"), (0.5, 1.0), (), "read and clear codes, road test"),
    Service("Transmission service", ("transmission service", "auto service", "gearbox oil", "trans fluid"), (1.0, 1.5), ("transmission fluid", "transmission filter")),
    Service("Headlight or globe replacement", ("globe", "headlight", "bulb", "tail light"), (0.2, 0.5), ("globe",)),
    Service("Drive belt replacement", ("drive belt", "fan belt", "serpentine belt", "squealing"), (0.5, 1.0), ("drive belt",)),
)

# Cars on the road in Melbourne's west, with what speech recognition tends to make of them.
CARS: dict[str, tuple[str, ...]] = {
    "Toyota Corolla": ("corolla", "carolla", "corola", "karolla"),
    "Toyota Camry": ("camry", "camery", "cam ree"),
    "Toyota Hilux": ("hilux", "hi lux", "high lux", "highlux", "hylux", "hi-lux"),
    "Toyota RAV4": ("rav4", "rav 4", "rav four", "rav for", "rav-4"),
    "Toyota LandCruiser": ("landcruiser", "land cruiser", "cruiser"),
    "Toyota Prado": ("prado",),
    "Toyota Kluger": ("kluger", "kluga"),
    "Toyota Yaris": ("yaris",),
    "Mazda CX-5": ("cx-5", "cx5", "cx 5", "cx five", "c x five", "c x 5", "see ex five"),
    "Mazda CX-3": ("cx-3", "cx3", "cx 3", "cx three"),
    "Mazda3": ("mazda 3", "mazda3", "mazda three"),
    "Mazda BT-50": ("bt-50", "bt50", "bt 50", "bt fifty"),
    "Hyundai i30": ("i30", "i 30", "i thirty", "eye thirty", "i-30"),
    "Hyundai Tucson": ("tucson", "tuscon"),
    "Kia Cerato": ("cerato", "serrato", "cerrato", "sorato"),
    "Kia Sportage": ("sportage",),
    "Ford Ranger": ("ranger",),
    "Ford Falcon": ("falcon",),
    "Ford Territory": ("territory",),
    "Holden Commodore": ("commodore", "commadore", "comodore", "vf", "ve commodore"),
    "Holden Colorado": ("colorado",),
    "Honda Civic": ("civic",),
    "Honda CR-V": ("cr-v", "crv", "cr v", "c r v"),
    "Honda Jazz": ("jazz",),
    "Subaru Forester": ("forester", "forrester"),
    "Subaru Outback": ("outback",),
    "Subaru Impreza": ("impreza", "imprezza"),
    "Nissan X-Trail": ("x-trail", "xtrail", "x trail", "ex trail"),
    "Nissan Navara": ("navara", "navarra"),
    "Mitsubishi Triton": ("triton",),
    "Mitsubishi Outlander": ("outlander",),
    "Mitsubishi ASX": ("asx", "a s x"),
    "Mitsubishi Lancer": ("lancer",),
    "Volkswagen Golf": ("golf",),
    "Volkswagen Amarok": ("amarok",),
    "Isuzu D-Max": ("d-max", "dmax", "d max"),
    "MG ZS": ("mg zs", "mg"),
    "Tesla Model 3": ("tesla", "model 3"),
}

SLANG: dict[str, str] = {
    "rego": "registration plate (also the yearly registration)",
    "all up": "the total including GST and everything",
    "inc gst / plus gst": "a price said 'plus GST' needs 10% added; otherwise his figures already include GST",
    "pads": "brake pads (front unless he says rear)",
    "discs / rotors": "brake rotors; 'machined' or 'skimmed' means resurfaced, not replaced",
    "five W thirty / 5W-30": "engine oil grade",
    "RWC / roadworthy": "Victorian roadworthy certificate inspection",
    "carby": "carburettor",
    "ute": "utility vehicle (Hilux, Ranger, Navara, Triton, D-Max)",
    "servo": "petrol station",
    "smoko": "morning tea break",
    "chucked on / whacked on": "fitted",
    "hour and a half / hour 'n' half": "1.5 hours labour",
    "half hour": "0.5 hours labour",
    "a pair": "two items sold as one (wiper blades, pads per axle)",
    "eftpos / tap": "card payment on the terminal",
    "cash job": "paid cash (still needs a GST invoice)",
    "the missus / the wife": "whoever does the books and approves invoices",
}

WORKFLOW = """How this workshop runs:
- A car arrives from a booking (phone, text or the website) or as a walk-in, gets checked in, and becomes a job.
- A job goes: in progress -> waiting on parts (if a part has to come in) -> done -> invoice approved by whoever does the books -> invoice sent with the "ready to collect" text -> paid, usually EFTPOS at pickup.
- The owner works out the charge himself and says it: per item, a labour amount, or a total "all up". Those figures include GST. When he gives only hours, labour is the shop rate; unsaid part prices come from the shop's parts list.
- GST is 10%; tax invoices show it separately. Supplier parts arrive with a receipt that goes in the books as an expense with its GST.
- Parts orders go to the usual suppliers (Burson, Repco, the tyre wholesaler) and wait for his OK before they are sent.
- Regulars come back for the next service; a note like "rear pads 40%" is something to mention next visit."""

GROUNDING = f"""Workshop know-how you can rely on:
{WORKFLOW}
- You know cars and common jobs like a mechanic does (what a front brake job or a logbook service involves, roughly how long it takes, what to check while you're there). Use it to understand what he means and to suggest the obvious next step, never to set a price or invent work he didn't say he did."""


def _norm(text: str) -> str:
    return " " + re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip() + " "


def cars_in(text: str) -> list[str]:
    """Car names he said, however speech recognition spelled them."""
    t = _norm(text)
    found = []
    for car, said in CARS.items():
        if any(_norm(a) in t for a in said):
            found.append(car)
    return found


def services_in(text: str) -> list[Service]:
    """Common jobs he mentioned, most specific first ('front pads' before 'pads')."""
    t = _norm(text)
    hits: list[tuple[int, Service]] = []
    for sv in SERVICES:
        if any(_norm(w) in t for w in sv.not_when):
            continue
        best = max((len(a) for a in sv.said_as if _norm(a) in t), default=0)
        if best:
            hits.append((best, sv))
    hits.sort(key=lambda h: -h[0])
    out: list[Service] = []
    for _, sv in hits:
        if sv not in out:
            out.append(sv)
    return out[:4]


def describe(sv: Service) -> str:
    lo, hi = sv.hours
    hours = f"{lo:g} hrs" if lo == hi else f"{lo:g} to {hi:g} hrs"
    bits = [f"{sv.name}: typically {hours} labour"]
    if sv.parts:
        bits.append("parts usually " + ", ".join(sv.parts))
    if sv.checks:
        bits.append("while there check " + sv.checks)
    if sv.follow_up:
        bits.append(sv.follow_up)
    return "; ".join(bits) + "."


def knowhow_for(text: str) -> str:
    """The few lines of know-how that bear on what he just said (empty if none)."""
    lines = []
    for car in cars_in(text):
        said = [a for a in CARS[car] if _norm(a) in _norm(text)]
        if said and said[0].replace(" ", "").replace("-", "") not in car.lower().replace(" ", "").replace("-", ""):
            lines.append(f'"{said[0]}" is a {car}.')
    lines += [describe(sv) for sv in services_in(text)]
    return "\n".join(f"- {l}" for l in lines)


def lookup(topic: str) -> dict:
    """Answer a know-how question for the agent's tool call."""
    svs = services_in(topic)
    cars = cars_in(topic)
    t = _norm(topic)
    slang = {k: v for k, v in SLANG.items() if any(_norm(p) in t for p in re.split(r"\s*/\s*", k))}
    if not (svs or cars or slang):
        return {"found": False, "workflow": WORKFLOW}
    return {
        "found": True,
        "jobs": [describe(sv) for sv in svs],
        "cars": cars,
        "slang": slang,
        "note": "Typical times are for reference only. Prices come from what he says or the shop's parts list.",
    }


__all__ = ["SERVICES", "CARS", "SLANG", "WORKFLOW", "GROUNDING", "Service", "cars_in", "services_in", "describe", "knowhow_for", "lookup"]
