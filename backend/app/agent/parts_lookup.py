"""Live parts price lookup. Uses Tavily web search when a key is present, then has
Nemotron Nano pull structured prices out of the results. Falls back to the local
parts catalogue so the flow still works offline."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx
from sqlmodel import Session, select

from ..config import get_settings
from ..llm import get_llm
from ..models import Part, Supplier

log = logging.getLogger(__name__)


def lookup_part_price(s: Session, query: str, vehicle: str = "") -> dict[str, Any]:
    local = _local_matches(s, query, vehicle)
    web = _web_search(f"{query} {vehicle} price Australia auto parts".strip())
    offers: list[dict[str, Any]] = []
    if web:
        offers = _extract_offers(query, web)
    for p in local:
        sup = s.get(Supplier, p.supplier_id) if p.supplier_id else None
        offers.append({"supplier": sup.name if sup else "Stock", "price_cents": p.cost_cents, "source": "catalogue", "part_id": p.id, "description": p.name})
    offers = [o for o in offers if o.get("price_cents")]
    offers.sort(key=lambda o: o["price_cents"])
    best = offers[0] if offers else None
    if not best:
        # no price anywhere (no web search on this server, nothing on the shelf for this
        # car): he's ordering, not quoting, so the shop's usual supplier for that kind of
        # part takes the order and prices it on their invoice
        sup = _usual_supplier(s, query)
        return {"query": query, "offers": [], "best_supplier": sup, "best_price_cents": None, "best_part_id": None, "searched_web": bool(web),
                "note": f"No price found. Order it from {sup} with no unit_cost_cents; they price it on their invoice."}
    return {
        "query": query,
        "offers": offers[:6],
        "best_supplier": best["supplier"] if best else None,
        "best_price_cents": best["price_cents"] if best else None,
        "best_part_id": best.get("part_id") if best else None,
        "searched_web": bool(web),
    }


def _local_matches(s: Session, query: str, vehicle: str = "") -> list[Part]:
    words = [w for w in query.lower().split() if len(w) > 2]
    # Need most of the query to match, so "brake pads toyota" doesn't pull in
    # every Toyota part on the shelf.
    need = max(1, (len(words) + 1) // 2)
    from .knowhow import cars_in

    car = set(re.findall(r"[a-z0-9]+", f"{query} {vehicle}".lower()))
    named = bool(vehicle.strip() or cars_in(query))  # no car named: anything on the shelf
    out = []
    for p in s.exec(select(Part)).all():
        name = p.name.lower()
        # "Brake pads front - Toyota Corolla" only fits a Corolla: never offer it for a Kia
        fits = set(re.findall(r"[a-z0-9]+", name.split(" - ", 1)[1])) if " - " in name else set()
        if named and fits and not (fits & car):
            continue
        if sum(w in name for w in words) >= need:
            out.append(p)
    return out


def _usual_supplier(s: Session, query: str) -> str:
    """The supplier the shop already buys this kind of part from (any car), else its first."""
    words = {w for w in re.findall(r"[a-z]+", query.lower()) if len(w) > 2}
    best, score = None, 0
    for p in s.exec(select(Part)).all():
        kind = set(re.findall(r"[a-z]+", p.name.split(" - ", 1)[0].lower()))
        n = len(words & kind)
        if n > score and p.supplier_id:
            best, score = p.supplier_id, n
    sup = s.get(Supplier, best) if best else s.exec(select(Supplier)).first()
    return sup.name if sup else "the parts supplier"


# Australian shops that sell car parts to the trade or over the counter. An open web
# search for "front pads CX-5 price" comes back with company directories, press
# releases and overseas factories, none of which he can order from today.
PARTS_SITES = [
    "repco.com.au", "supercheapauto.com.au", "autobarn.com.au", "sparesbox.com.au",
    "burson.com.au", "autopro.com.au", "partsbox.com.au", "ebay.com.au", "amazon.com.au",
    "bendix.com.au", "rydeaustralia.com.au", "autoone.com.au", "brakewarehouse.com.au",
]


def _parts_site(url: str) -> bool:
    host = re.sub(r"^https?://", "", url or "").split("/", 1)[0].lower()
    return any(host == d or host.endswith("." + d) for d in PARTS_SITES)


def _web_search(q: str) -> list[dict[str, Any]]:
    key = get_settings().tavily_api_key
    if not key:
        return []
    try:
        r = httpx.post(
            "https://api.tavily.com/search",
            json={"api_key": key, "query": q, "max_results": 8, "include_answer": False, "search_depth": "basic", "include_domains": PARTS_SITES},
            timeout=20,
        )
        r.raise_for_status()
        return [x for x in r.json().get("results", []) if _parts_site(x.get("url", ""))]
    except Exception as e:  # noqa: BLE001
        log.warning("Tavily search failed: %s", e)
        return []


def _extract_offers(query: str, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Nemotron Nano turns raw search snippets into {supplier, price} rows."""
    snippets = "\n\n".join(f"[{r.get('title')}] ({r.get('url')})\n{r.get('content', '')[:600]}" for r in results)
    prompt = (
        "You extract product prices from web search snippets. classify each result and return JSON: "
        '{"offers":[{"supplier":str,"price_aud":number,"description":str,"url":str}]} . '
        "Only include product listings from a shop selling the requested part that clearly state an AUD price. "
        "supplier is the shop's name (e.g. Repco, Supercheap Auto, Sparesbox). Max 5 offers."
    )
    try:
        reply = get_llm().chat(
            [{"role": "system", "content": prompt}, {"role": "user", "content": f"Part: {query}\n\n{snippets}"}],
            tier="fast",
            json_mode=True,
            max_tokens=600,
        )
        data = json.loads(reply.content or "{}")
        out = []
        for o in data.get("offers", []):
            if not _parts_site(str(o.get("url", ""))):
                continue  # only shops he can actually order from
            try:
                out.append({"supplier": str(o.get("supplier", "web"))[:60], "price_cents": int(round(float(o["price_aud"]) * 100)), "source": o.get("url", "web"), "description": o.get("description", query)})
            except (KeyError, ValueError, TypeError):
                continue
        return out
    except Exception as e:  # noqa: BLE001
        log.warning("offer extraction failed: %s", e)
        return []
