"""Live parts price lookup. Uses Tavily web search when a key is present, then has
Nemotron Nano pull structured prices out of the results. Falls back to the local
parts catalogue so the flow still works offline."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from sqlmodel import Session, select

from ..config import get_settings
from ..llm import get_llm
from ..models import Part, Supplier

log = logging.getLogger(__name__)


def lookup_part_price(s: Session, query: str, vehicle: str = "") -> dict[str, Any]:
    local = _local_matches(s, query)
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
    return {
        "query": query,
        "offers": offers[:6],
        "best_supplier": best["supplier"] if best else None,
        "best_price_cents": best["price_cents"] if best else None,
        "best_part_id": best.get("part_id") if best else None,
        "searched_web": bool(web),
    }


def _local_matches(s: Session, query: str) -> list[Part]:
    words = [w for w in query.lower().split() if len(w) > 2]
    parts = s.exec(select(Part)).all()
    return [p for p in parts if any(w in p.name.lower() for w in words)]


def _web_search(q: str) -> list[dict[str, Any]]:
    key = get_settings().tavily_api_key
    if not key:
        return []
    try:
        r = httpx.post(
            "https://api.tavily.com/search",
            json={"api_key": key, "query": q, "max_results": 5, "include_answer": False, "search_depth": "basic"},
            timeout=20,
        )
        r.raise_for_status()
        return r.json().get("results", [])
    except Exception as e:  # noqa: BLE001
        log.warning("Tavily search failed: %s", e)
        return []


def _extract_offers(query: str, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Nemotron Nano turns raw search snippets into {supplier, price} rows."""
    snippets = "\n\n".join(f"[{r.get('title')}] ({r.get('url')})\n{r.get('content', '')[:600]}" for r in results)
    prompt = (
        "You extract product prices from web search snippets. classify each result and return JSON: "
        '{"offers":[{"supplier":str,"price_aud":number,"description":str,"url":str}]} . '
        "Only include results that clearly state an AUD price for the requested part. Max 5 offers."
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
            try:
                out.append({"supplier": str(o.get("supplier", "web"))[:60], "price_cents": int(round(float(o["price_aud"]) * 100)), "source": o.get("url", "web"), "description": o.get("description", query)})
            except (KeyError, ValueError, TypeError):
                continue
        return out
    except Exception as e:  # noqa: BLE001
        log.warning("offer extraction failed: %s", e)
        return []
