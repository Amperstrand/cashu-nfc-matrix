#!/usr/bin/env python3
"""Read-direction tap soak: N x (arm request on cashu.me -> ACR1252 Type-4 read
-> verify NUT-18 fields), timings + interference logged to JSONL.

Coexists with the bc-taploop lane (reads same phone every 30s): transient
reader-unavailable / no-card get retried with backoff, interference is logged
not hidden. Every cycle re-arms a FRESH amount so each NDEF is unique.
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bench.probe_acr import read_ndef_request  # noqa: E402
from drivers import ui  # noqa: E402
from drivers.cashu_me import CashuMeDriver  # noqa: E402


def soak(cycles: int, base_amount: int, out_path: str) -> int:
    d = CashuMeDriver()
    ok = fail = 0
    with open(out_path, "a") as fh:
        for i in range(cycles):
            amount = base_amount + i
            rec: dict = {"cycle": i, "amount": amount, "ts": time.strftime("%H:%M:%S")}
            st = ""
            t0 = time.monotonic()
            # --- arm phase (retry once with full self-heal) ---
            try:
                d.wake()
                st = d.create_request(amount)
                if not d.is_armed():
                    raise RuntimeError(f"not armed after create_request: {st!r}")
            except Exception as e:
                rec["arm_retry_0"] = repr(e)[:120]
                try:
                    ui.adb(d.serial, "shell", "am", "force-stop", d.package)
                    time.sleep(1.0)
                    d.launch()
                    st = d.create_request(amount)
                    if not d.is_armed():
                        raise RuntimeError(f"not armed after retry: {st!r}")
                except Exception as e2:
                    rec["arm_error"] = repr(e2)[:200]
            if "arm_error" not in rec:
                rec["arm_s"] = round(time.monotonic() - t0, 2)
                rec["nfc_status"] = st if isinstance(st, str) else ""
            else:
                fail += 1
                fh.write(json.dumps(rec) + "\n"); fh.flush()
                print(json.dumps(rec), flush=True)
                continue
            # --- read phase (retry transient interference) ---
            res = None
            for attempt in range(4):
                try:
                    res = read_ndef_request("ACR1252")
                    if res.get("creq") is None and attempt < 3:
                        raise RuntimeError(f"no creq parsed: {res.get('parse_error', res.get('select_ndef_sw'))}")
                    break
                except Exception as e:
                    rec[f"read_retry_{attempt}"] = repr(e)[:120]
                    time.sleep(2 + attempt * 3)
            t_read = round(time.monotonic() - t0, 2)
            if res and res.get("creq"):
                creq = res["creq"]
                good = creq.get("a") == amount and creq.get("u") == "sat"
                rec.update({
                    "ok": good,
                    "creq": creq,
                    "ndef_len": res["ndef_len"],
                    "connect_s": res.get("connect_s"),
                    "read_s": res.get("read_s"),
                    "cycle_total_s": t_read,
                    "atr": res["atr"],
                })
                ok += 1 if good else 0
                fail += 0 if good else 1
            else:
                rec["ok"] = False
                rec["read_error"] = (res or {}).get("parse_error") or "read failed"
                fail += 1
            fh.write(json.dumps(rec) + "\n"); fh.flush()
            print(json.dumps({k: rec.get(k) for k in ("cycle", "amount", "ok", "arm_s", "connect_s", "read_s", "cycle_total_s", "read_error", "read_retry_0")}), flush=True)
            time.sleep(1.0)
    print(f"=== soak done: {ok} ok / {fail} fail / {cycles} cycles -> {out_path}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--cycles", type=int, default=10)
    ap.add_argument("--base-amount", type=int, default=30)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    out = args.out or os.path.join(os.path.dirname(__file__), "..", "results",
                                   f"soak-{time.strftime('%Y%m%d-%H%M%S')}.jsonl")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    sys.exit(soak(args.cycles, args.base_amount, out))
