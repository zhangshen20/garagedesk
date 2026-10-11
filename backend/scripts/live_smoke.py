"""Run the real agents against Nebius Token Factory and print what the Nemotron
models did. Needs NEBIUS_API_KEY in the environment.

    cd backend && .venv/bin/python scripts/live_smoke.py
"""

from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("DATABASE_URL", "sqlite:///./live-smoke.db")
os.environ.setdefault("GARAGEDESK_SCHEDULER", "0")

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app

if not get_settings().nebius_api_key:
    sys.exit("NEBIUS_API_KEY not set")

if os.path.exists("live-smoke.db"):
    os.remove("live-smoke.db")


_last = [time.time()]


def show(label: str, r: dict) -> None:
    now = time.time()
    print(f"\n=== {label} [{r.get('model')}] {now - _last[0]:.1f}s")
    _last[0] = now
    for s in r.get("steps", []):
        print(f"  -> {s['tool']}({json.dumps(s['args'])[:120]})")
    print("  reply:", (r.get("reply") or "")[:400])


with TestClient(app) as c:
    print("LLM mode:", c.get("/healthz").json())
    t = _last[0] = time.time()
    show("web booking", c.post("/api/chat/customer", json={"text": "Hi, Ben Hall here. My Toyota Camry, rego BHX442, is due for a logbook service. Got anything tomorrow morning? My number is 0412 345 678.", "session_id": "web-live-1"}).json())
    show("web booking follow-up", c.post("/api/chat/customer", json={"text": "9 is good, book it", "session_id": "web-live-1"}).json())
    show("sms status", c.post("/api/chat/customer", json={"text": "hey is my corolla ready? rego ABC123", "session_id": "+61411000001", "channel": "sms"}).json())
    show("voice hours", c.post("/api/chat/customer", json={"text": "yeah hi what time are you open till on saturday", "session_id": "+61422000000", "channel": "voice"}).json())
    show("owner: today", c.post("/api/chat/owner", json={"text": "what's on today and who's waiting on parts?"}).json())
    show("owner: order parts", c.post("/api/chat/owner", json={"text": "order front brake pads for the corolla on job 3 from whoever is cheapest"}).json())
    show("owner: invoice", c.post("/api/chat/owner", json={"text": "job 4 is finished, invoice it"}).json())
    show("owner: expense", c.post("/api/chat/owner", json={"text": "add an expense, $64 brake cleaner from burson, consumables"}).json())
    t0 = time.time()
    rep = c.post("/api/reports/generate").json()
    print(f"\n=== daily report [{rep['model']}] {time.time() - t0:.1f}s\n{rep['content_md']}")
    print(f"\nTotal time {time.time() - t:.1f}s")
    print("\nApprovals:", json.dumps(c.get("/api/approvals").json(), indent=1)[:600])
