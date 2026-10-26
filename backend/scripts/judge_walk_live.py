"""Walk the live demo the way a judge would, over HTTPS only: every flow in the demo
script and README, through the same endpoints the phone and the dashboard use.
Standard library only (Pillow optional, for the receipt photo), so it runs from any
machine that can reach the demo.

    python3 backend/scripts/judge_walk_live.py [https://66-201-4-40.sslip.io]

It resets the demo data first and again at the end, so the demo is left fresh.
"""

from __future__ import annotations

import base64
import io
import json
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://66-201-4-40.sslip.io").rstrip("/")
CTX = ssl.create_default_context()  # a bad certificate fails here, as it would in a browser
results: list[tuple[str, bool, str, float]] = []


def http(method: str, path: str, body: Any = None, timeout: float = 120) -> tuple[int, bytes, dict[str, str]]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method, headers={"Content-Type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)


def j(method: str, path: str, body: Any = None) -> Any:
    code, raw, _ = http(method, path, body)
    if code != 200:
        raise AssertionError(f"{method} {path} -> HTTP {code}: {raw[:200]!r}")
    return json.loads(raw)


def check(name: str, fn: Any) -> Any:
    t0 = time.time()
    try:
        out = fn()
        results.append((name, True, "", time.time() - t0))
        print(f"PASS {time.time() - t0:5.1f}s  {name}", flush=True)
        return out
    except Exception as e:  # noqa: BLE001 - report every failure and keep walking
        results.append((name, False, str(e)[:300], time.time() - t0))
        print(f"FAIL {time.time() - t0:5.1f}s  {name}: {str(e)[:300]}", flush=True)
        return None


def say(text: str) -> dict[str, Any]:
    r = j("POST", "/api/owner/voice", {"text": text})
    print(f"        said {text!r}\n        heard back {r.get('readback')!r}", flush=True)
    return r


def need(cond: bool, why: str) -> None:
    if not cond:
        raise AssertionError(why)


def low(r: dict[str, Any]) -> str:
    return f"{r.get('readback') or ''} {r.get('say') or ''}".lower()


def latest_approval() -> tuple[int, str]:
    """The approve link texted to the wife, as it appears on the Outbox page."""
    for o in j("GET", "/api/outbox")["outbox"]:
        if "/approve/" in o["body"]:
            url = o["body"][o["body"].index("http") :].split()[0]
            u = urllib.parse.urlparse(url)
            need(u.netloc in BASE, f"approve link points at {u.netloc}, not the demo")
            return int(u.path.rsplit("/", 1)[1]), urllib.parse.parse_qs(u.query)["t"][0]
    raise AssertionError("no approve link in the Outbox")


def outbox_has(*words: str) -> None:
    bodies = [f"{o.get('subject') or ''} {o['body']}".lower() for o in j("GET", "/api/outbox")["outbox"]]
    need(any(all(w.lower() in b for w in words) for b in bodies), f"no Outbox message with {words}")


def receipt_b64() -> str:
    from PIL import Image, ImageDraw, ImageFont  # optional

    img = Image.new("RGB", (620, 760), "white")
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 26)
    except OSError:
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 26)
        except OSError:
            font = ImageFont.load_default()
    y = 30
    for line in ["BURSON AUTO PARTS", "Sunshine North VIC", "TAX INVOICE  #448210", "", "Qty  Item                 Amount", "1    Wiper blades pair     $38.50", "", "GST included           $3.50", "TOTAL                  $38.50", "", "EFTPOS  APPROVED"]:
        d.text((30, y), line, fill="black", font=font)
        y += 48
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


def main() -> None:
    print(f"Walking {BASE}\n")

    # --- first visit: pages, certificate, health -----------------------------------
    for p, want in [("/healthz", b"ok"), ("/", b"<div id=\"root\""), ("/owner", b"<div id=\"root\""), ("/chat", b"<div id=\"root\""), ("/approve/1?t=x", b"<div id=\"root\"")]:
        def page(p: str = p, want: bytes = want) -> None:
            code, raw, _ = http("GET", p)
            need(code == 200, f"HTTP {code}")
            need(want in raw, f"page doesn't contain {want!r}")

        check(f"GET {p} over valid HTTPS", page)

    def assets() -> None:
        _, html, _ = http("GET", "/owner")
        refs = [s.split('"')[0] for s in html.decode().split('src="')[1:] + html.decode().split('href="')[1:] if s.startswith("/assets/")]
        need(refs, "no /assets in the page")
        for r in refs:
            code, _, _ = http("GET", r)
            need(code == 200, f"{r} -> {code}")

    check("page scripts and styles load", assets)
    check("Reset demo data", lambda: need(j("POST", "/api/demo/reset")["ok"], "reset not ok"))

    def today() -> None:
        t = j("GET", "/api/owner/today")
        need(t.get("stt"), "server speech-to-text is off: hold-to-talk won't work")
        need(t.get("tts"), "server voice is off")
        need(t.get("approver"), "no approver name")
        need(len(t.get("jobs", [])) >= 3, f"only {len(t.get('jobs', []))} jobs in the demo data")
        print(f"        shop={t.get('shop')!r} approver={t.get('approver')!r} jobs={len(t['jobs'])}")

    check("owner app opens (today, speech, voice)", today)

    # --- shot 2/3: Corolla, yep -----------------------------------------------------
    r = check("Corolla ABC123, front pads, hour and a half, 350 all up", lambda: say("Corolla ABC123, front pads, hour and a half, 350 all up"))
    if r:
        def corolla() -> None:
            need(r.get("kind") == "draft" and r.get("ok"), f"not a draft: {r.get('kind')}")
            need(r["job"]["rego"] == "ABC123", f"rego {r['job']['rego']}")
            need(r["job"]["total_cents"] == 35000, f"total {r['job']['total_cents']}")
            need("maria" in low(r) and "three hundred and fifty" in low(r), "read-back lacks Maria / three hundred and fifty")
            need((r.get("offer") or {}).get("action") == "send", "no 'send it?' offer")

        check("  draft is Maria's Corolla, $350.00, offers to send", corolla)

        def voice() -> None:
            code, raw, hdr = http("GET", "/api/tts?t=" + urllib.parse.quote((r.get("readback") or "Sent.").split(". ")[0][:150]))
            need(code == 200 and raw[:4] == b"RIFF", f"tts HTTP {code}")
            print(f"        read-back audio {len(raw)} bytes")

        check("  read-back is spoken (server voice)", voice)
    r = check("yep", lambda: say("yep"))
    check("  sent to Jenny", lambda: need(r is not None and r.get("kind") == "done" and ("sent to" in low(r) or "invoice sent" in low(r)), f"got {r and r.get('kind')}"))

    # --- shot 6/7: wife approves, customer text, paid EFTPOS ------------------------
    def wife() -> None:
        aid, t = latest_approval()
        page = j("GET", f"/api/approve/{aid}?t={t}")
        need(page.get("job") and page["job"]["total_cents"] == 35000, "approve page doesn't show the $350 invoice")
        d = j("POST", f"/api/approve/{aid}", {"t": t, "approve": True})
        need(d.get("status") == "approved", f"status {d.get('status')}")

    check("wife opens the texted link and taps Approve and send", wife)
    check("customer texted: car ready + tax invoice", lambda: outbox_has("maria", "ready"))

    def pdf() -> None:
        inv = j("GET", "/api/invoices")
        inv = inv.get("invoices", inv) if isinstance(inv, dict) else inv
        num = inv[0]["number"]
        code, raw, _ = http("GET", f"/api/invoices/{num}/pdf")
        need(code == 200 and raw[:4] == b"%PDF", f"pdf HTTP {code}")

    check("tax invoice PDF opens", pdf)
    check("phone offers Paid EFTPOS after approval", lambda: need((j("GET", "/api/owner/today").get("offer") or {}).get("action") == "paid", "no paid offer"))
    r = check("yes (they've paid)", lambda: say("yes"))
    check("  marked paid, receipt sent", lambda: (need(r is not None and "paid" in low(r), "no 'paid' in answer"), outbox_has("receipt")))

    # --- shot 4: yesterday's jobs ---------------------------------------------------
    r = check("Find yesterday's jobs and prepare the tax invoice.", lambda: say("Find yesterday's jobs and prepare the tax invoice."))
    check("  Dan's X-Trail $240.90", lambda: need(r is not None and r.get("job") and r["job"]["rego"] == "DW4521" and r["job"]["total_cents"] == 24090, f"got {r and r.get('job', {}) and r['job'].get('rego')}"))

    # --- shot 5: same as last time --------------------------------------------------
    r = check("Liam's Ranger, did the battery again, same as last time.", lambda: say("Liam's Ranger, did the battery again, same as last time."))
    check("  Liam's Ranger $366.00", lambda: need(r is not None and r.get("job") and r["job"]["total_cents"] == 36600, f"got {r and (r.get('job') or {}).get('total_cents')}"))

    # --- wife sends one back (Fix) --------------------------------------------------
    say("send it")

    def fix() -> None:
        aid, t = latest_approval()
        d = j("POST", f"/api/approve/{aid}", {"t": t, "approve": False, "note": "labour should be an hour"})
        need(d.get("status") == "rejected", f"status {d.get('status')}")
        o = (j("GET", "/api/owner/today").get("offer") or {}).get("say") or ""
        need("sent back" in o.lower() or "fix" in o.lower(), f"phone says {o!r}")

    check("wife taps Fix: it goes back to his phone", fix)

    # --- shot 8: parts order --------------------------------------------------------
    r = check("Order front pads for the Kia Cerato.", lambda: say("Order front pads for the Kia Cerato."))
    check("  reads the order back, asks to send", lambda: need(r is not None and (r.get("offer") or {}).get("action") == "order", f"offer {r and r.get('offer')}"))
    r = check("Yes.", lambda: say("Yes."))
    check("  order sent", lambda: need(r is not None and "order sent" in low(r), "no 'order sent'"))

    # --- shot 9 and the rest of his day ---------------------------------------------
    r = check("What have I got on today?", lambda: say("What have I got on today?"))
    check("  lists today's cars", lambda: need(r is not None and ("corolla" in low(r) or "maria" in low(r)), "no Corolla/Maria"))
    for q, words in [("Who owes me money?", ("$", "owe", "nobody", "no one", "commodore")), ("How much GST this quarter?", ("gst",)), ("What did we take yesterday?", ("$",))]:
        r = check(q, lambda q=q: say(q))
        check("  answers from the records", lambda r=r, words=words: need(r is not None and any(w in low(r) for w in words), f"none of {words}"))
    r = check("The CX-5 is waiting on parts till Thursday", lambda: say("The CX-5 is waiting on parts till Thursday"))
    check("  CX-5 waiting on parts, customer told", lambda: (need(r is not None and "invoice for" not in low(r), "made an invoice"), outbox_has("jack")))
    check("Remember Jack always pays cash", lambda: say("Remember Jack always pays cash"))
    r = check("How does Jack usually pay?", lambda: say("How does Jack usually pay?"))
    check("  remembers cash", lambda: need(r is not None and "cash" in low(r), "no 'cash'"))
    before = len(j("GET", "/api/bookings").get("bookings", []) if isinstance(j("GET", "/api/bookings"), dict) else j("GET", "/api/bookings"))
    r = check("Book Grace in for Thursday at 9 for a service", lambda: say("Book Grace in for Thursday at 9 for a service"))

    def booked() -> None:
        b = j("GET", "/api/bookings")
        b = b.get("bookings", b) if isinstance(b, dict) else b
        need(len(b) > before or "book" in low(r or {}), f"bookings {before} -> {len(b)}")

    check("  booking made", booked)
    r = check("blah blah the weather's nice", lambda: say("blah blah the weather's nice"))
    check("  nonsense makes no job or offer", lambda: need(r is not None and not r.get("offer"), f"offer {r and r.get('offer')}"))

    # --- receipt photo --------------------------------------------------------------
    def photo() -> None:
        try:
            b64 = receipt_b64()
        except ImportError:
            print("        (Pillow not installed: receipt photo skipped)")
            return
        d = say("Corolla ABC123, replaced the wiper blades, half an hour")
        need(d.get("job"), "no draft")
        out = j("POST", f"/api/owner/jobs/{d['job']['job_id']}/receipt", {"image_b64": b64, "mime": "image/jpeg"})
        print(f"        receipt read back {out.get('readback')!r}")
        need(out.get("ok"), f"receipt not added: {out.get('readback')}")

    check("receipt photo adds the part at cost", photo)

    # --- dashboard pages --------------------------------------------------------------
    for p in ["/api/overview", "/api/jobs", "/api/invoices", "/api/money", "/api/parts", "/api/approvals", "/api/conversations", "/api/customers", "/api/reports", "/api/jobcards/samples"]:
        check(f"dashboard {p}", lambda p=p: j("GET", p))
    check("customer chat replies", lambda: need(j("POST", "/api/chat/customer", {"text": "Hi, can I book a service for my Corolla next week?", "session_id": "judge-walk", "channel": "web"}).get("reply"), "no reply"))
    check("Ultra daily report generates", lambda: j("POST", "/api/reports/generate"))

    check("Reset demo data (leave it fresh)", lambda: need(j("POST", "/api/demo/reset")["ok"], "reset not ok"))

    fails = [r for r in results if not r[1]]
    slow = sorted(results, key=lambda r: -r[3])[:5]
    print(f"\n{len(results) - len(fails)}/{len(results)} passed")
    print("slowest: " + ", ".join(f"{n.strip()} {t:.1f}s" for n, _, _, t in slow))
    for n, _, why, _ in fails:
        print(f"FAILED: {n.strip()}: {why}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
