"""The owner-utterance evaluation set, run with the mock models (CI). The same
cases run against the real Nemotron models with scripts/owner_eval_live.py."""

import pytest

from tests.owner_utterances import CASES, run_case


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_owner_says(client, case):  # client: fresh settings and mock LLM
    r = run_case(case)
    assert not r["problems"], f"{r['said']!r} -> {r['out'].get('readback')!r}: {r['problems']}"
