"""Say every owner utterance in tests/owner_utterances.py to the real Nemotron
models on Token Factory and score what happens. Needs NEBIUS_API_KEY.

    cd backend && python scripts/owner_eval_live.py            # all cases
    cd backend && python scripts/owner_eval_live.py inv- find-  # cases whose id starts so
"""

from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
os.environ.setdefault("GARAGEDESK_SCHEDULER", "0")
os.environ["DATABASE_URL"] = "sqlite://"
os.environ.setdefault("LLM_MODE", "nebius")

from app.config import get_settings  # noqa: E402
from tests.owner_utterances import CASES, run_case  # noqa: E402

if get_settings().effective_llm_mode == "nebius" and not get_settings().nebius_api_key:
    sys.exit("NEBIUS_API_KEY not set")

prefixes = sys.argv[1:]
cases = [c for c in CASES if not prefixes or any(c["id"].startswith(p) for p in prefixes)]
with ThreadPoolExecutor(max_workers=int(os.environ.get("EVAL_WORKERS", "6"))) as pool:
    results = list(pool.map(run_case, cases))

failed = 0
for r in results:
    ok = not r["problems"]
    failed += not ok
    out = r["out"]
    print(f"{'PASS' if ok else 'FAIL'} {r['case']['id']:<26} {out.get('seconds', 0):>5}s  {r['said']}")
    print(f"     -> {out.get('kind')}: {(out.get('readback') or '')[:220]}")
    if out.get("steps"):
        print("        tools:", ", ".join(f"{st['tool']}({json.dumps(st['args'])[:80]})" for st in out["steps"]))
    for p in r["problems"]:
        print("        !", p)
secs = sorted(r["out"].get("seconds", 0) for r in results)
print(f"\n{len(results) - failed}/{len(results)} passed; median {secs[len(secs) // 2]}s, slowest {secs[-1]}s")
sys.exit(1 if failed else 0)
