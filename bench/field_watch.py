#!/usr/bin/env python3
"""Field watcher: poll the nucula CCID reader for the phone's HCE and keep
the phone armed while a human moves hardware. Loud on first activation.
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from smartcard.Exceptions import NoCardException
from smartcard.System import readers

from bench.probe_acr import read_ndef_request


def log(msg: str) -> None:
    print(f"{time.strftime('%H:%M:%S')} {msg}", flush=True)


def nucula_reader():
    cands = [r for r in readers() if "Nucula CCID" in str(r)]
    if not cands:
        raise RuntimeError("Nucula CCID reader not in pcscd")
    return cands[0]


def main(minutes: float = 30.0) -> int:
    from drivers.cashu_me import CashuMeDriver

    d = CashuMeDriver()
    r = nucula_reader()
    hits = 0
    last_arm_check = 0.0
    armed_at_start = d.create_request(21)
    log(f"phone armed: {armed_at_start[:50]}")
    deadline = time.monotonic() + minutes * 60
    while time.monotonic() < deadline:
        try:
            c = r.createConnection()
            c.connect()
        except NoCardException:
            pass
        except Exception as e:
            log(f"reader error: {type(e).__name__}: {str(e)[:60]}")
            time.sleep(2)
            try:
                r = nucula_reader()
            except Exception:
                pass
        else:
            atr = " ".join(f"{b:02x}" for b in c.getATR())
            hits += 1
            log(f"*** ACTIVATION #{hits} ATR={atr} ***")
            if hits == 1:
                try:
                    res = read_ndef_request("Nucula CCID")
                    log(f"FULL READ: aid={res.get('select_aid_sw')} e104={res.get('select_ndef_sw')}")
                    if res.get("creq"):
                        log(f"REQUEST DECODED VIA NUCULA: {res['creq']}")
                except Exception as e:
                    log(f"full read failed: {type(e).__name__}: {str(e)[:80]}")
            try:
                c.disconnect()
            except Exception:
                pass
        # keep the request armed (screen wanders, app state drifts)
        if time.monotonic() - last_arm_check > 45:
            last_arm_check = time.monotonic()
            try:
                if not d.is_armed():
                    log("phone drifted off request screen — re-arming")
                    d.create_request(21)
            except Exception as e:
                log(f"arm check failed: {type(e).__name__}: {str(e)[:60]}")
        time.sleep(2)
    log(f"watch ended: {hits} activations")
    return 0


if __name__ == "__main__":
    sys.exit(main(float(sys.argv[1]) if len(sys.argv) > 1 else 30))
