#!/usr/bin/env python3
"""Payment soak: N x full NFC payment cycles through one reader.

Per cycle: mint AMOUNT fresh fake-sats -> arm a matching request -> payer
reads it + writes the token over NFC -> phone redeems -> balance asserted.
Wallet is NOT wiped per cycle (wipe is the recovery path, not the loop):
balance must increase by exactly AMOUNT-1 (input fee) every cycle.

JSONL per cycle + final summary. Self-healing: on failure -> wipe, re-setup,
continue (failures recorded, soak survives).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bench.field_arbiter import grant  # noqa: E402
from bench.payer import Type4Payer  # noqa: E402
from drivers import ui  # noqa: E402
from drivers.cashu_me import CashuMeDriver  # noqa: E402

READER = os.environ.get("SOAK_READER", "Nucula CCID")
CYCLES = int(os.environ.get("SOAK_CYCLES", "10"))
AMOUNT = int(os.environ.get("SOAK_AMOUNT", "21"))
MINT = os.environ.get("MINT_URL", "https://testnut.cashu.space")


def mint(tok_path: str) -> None:
    r = subprocess.run(["bash", "bench/mint_token.sh", tok_path, str(AMOUNT)],
                       capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        raise RuntimeError(f"mint failed: {r.stdout[-150:]}")


def main() -> int:
    d = CashuMeDriver()
    grant("nucula" if "Nucula" in READER else "acr")
    out_path = f"results/payment-soak-{time.strftime('%Y%m%d-%H%M%S')}.jsonl"
    os.makedirs("results", exist_ok=True)
    ok = fail = 0
    bal = d.balance_sats()
    print(f"start balance={bal} reader={READER} cycles={CYCLES}", flush=True)
    for i in range(CYCLES):
        rec: dict = {"cycle": i, "ts": time.strftime("%H:%M:%S")}
        t0 = time.time()
        try:
            mint("/tmp/soak-token.txt")
            rec["mint_s"] = round(time.time() - t0, 1)
            if not d.is_armed():
                st = d.create_request(AMOUNT)
                assert "Ask the sender" in st, f"arm failed: {st!r}"
            p = Type4Payer(READER)
            t1 = time.time()
            p.connect()
            req = p.read_request()
            assert req.get("a") == AMOUNT, f"wrong request: {req.get('a')}"
            w = p.write_token(open("/tmp/soak-token.txt").read().strip())
            rec["nfc_s"] = round(time.time() - t1, 1)
            rec["chunks"] = w["chunks"]
            got = False
            for _ in range(15):
                time.sleep(4)
                txt = ui.screen_text(d.serial)
                if "Payment received" in txt:
                    got = True
                    break
                if "failed" in txt.lower():
                    raise RuntimeError(f"phone rejected: {txt[:120]}")
            assert got, "no success screen in 60s"
            new_bal = d.balance_sats()
            rec["credited"] = new_bal - bal
            assert new_bal - bal == AMOUNT - 1, f"balance {bal}->{new_bal}"
            bal = new_bal
            rec["ok"] = True
            ok += 1
        except Exception as e:
            rec["ok"] = False
            rec["error"] = repr(e)[:200]
            fail += 1
            try:  # recovery: wipe + fresh setup
                d.wipe()
                bal = d.balance_sats()
                rec["recovered"] = True
            except Exception as e2:
                rec["recovered"] = repr(e2)[:120]
        rec["cycle_s"] = round(time.time() - t0, 1)
        with open(out_path, "a") as fh:
            fh.write(json.dumps(rec) + "\n")
        print(json.dumps(rec), flush=True)
    grant("quiet")
    print(f"=== soak done: {ok} ok / {fail} fail -> {out_path}", flush=True)
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
