"""T3 — repetition/timing soak (marker: soak).

The same arm->read->verify cycle as T2, N times, every cycle a FRESH request
(unique id + amount). Default cycles small for hil dispatch; the nightly passes
--soak-cycles. Run only when the bench is otherwise idle (it holds phone+ACR
for the duration).
"""
from __future__ import annotations

import json
import time

import pytest

from bench.probe_acr import read_ndef_request

pytestmark = pytest.mark.soak


def test_read_soak(cashu_me, acr_place, request, evidence_dir):
    cycles = request.config.getoption("--soak-cycles")
    base = 100
    ok = 0
    failures: list[dict] = []
    rows = []
    for i in range(cycles):
        amount = base + i
        t0 = time.monotonic()
        try:
            st = cashu_me.create_request(amount)
            assert "Ask the sender" in st, f"arm failed: {st!r}"
            arm_s = time.monotonic() - t0
            t1 = time.monotonic()
            res = None
            for attempt in range(4):
                try:
                    res = read_ndef_request("ACR1252")
                    if res.get("creq"):
                        break
                except Exception:
                    pass
                time.sleep(2 + attempt * 2)
            assert res and res.get("creq"), f"read failed: {res}"
            read_s = time.monotonic() - t1
            creq = res["creq"]
            assert creq["a"] == amount, f"amount mismatch {creq}"
            ok += 1
            rows.append({"i": i, "amount": amount, "arm_s": round(arm_s, 2),
                         "read_s": round(read_s, 3), "id": creq.get("i")})
        except Exception as e:
            failures.append({"i": i, "amount": amount, "error": repr(e)[:200]})
        print(f"cycle {i}: ok={ok} fail={len(failures)}", flush=True)
    out = evidence_dir / f"t3-soak-{cycles}.json"
    out.write_text(json.dumps({"ok": ok, "fail": len(failures), "cycles": cycles,
                               "rows": rows, "failures": failures}, indent=1))
    assert not failures, f"{len(failures)}/{cycles} soak cycles failed: {failures[:3]}"
