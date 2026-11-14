"""Live vpcd round-trip: the stateful model served as a REAL virtual card.

The last vpicc piece (audit follow-up #5): starts GoldenVpicc on the
vpcd slot with ModelVpicc as the answerer, finds the vPICC reader via
pcscd, and drives the golden exchange set — every answer COMPUTED, not
replayed; 57/57 byte-exact required through the full pcscd → vpcd →
model stack.

Host requirements (bench-host only; graceful skip elsewhere):
  - pcscd with the vpcd driver + a reader.conf entry routing the
    "vPICC table card" slot to 127.0.0.1:35970 (bolty-rs bench setup;
    see upstream tools/hil/difftest/test_vpicc_model.py)
  - pyscard

Source: Amperstrand/bolty-rs test_vpicc_model.py (adapted: graceful
skip instead of env_dependent marker — this repo has no such marker).
"""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

pyscard = pytest.importorskip(
    "smartcard", reason="pyscard: bench-host dep for the live vpcd round trip")

from bench.vpicc.vpicc_golden import GoldenVpicc  # noqa: E402
from bench.vpicc.vpicc_model import ModelVpicc  # noqa: E402

VPICC_PORT = 35970  # table-card vpcd slot (patched driver, upstream default)
READER_NAMES = {"vPICC table card"}
GOLDEN = Path(__file__).resolve().parent.parent / "bench" / "vpicc" / "golden_acr1252.json"


def _vpcd_reader_present() -> bool:
    try:
        from smartcard.System import readers
        names = [str(r) for r in readers()]
    except Exception:  # noqa: BLE001 — no pcscd at all
        return False
    if not any(n in rn and "00 00" in rn for rn in names for n in READER_NAMES):
        return False
    # Concurrent suite runs would fight over the vpcd slot port — skip
    # gracefully instead of failing on a bind error.
    import socket
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", VPICC_PORT))
    except OSError:
        return False
    finally:
        s.close()
    return True


pytestmark = pytest.mark.skipif(
    not _vpcd_reader_present(),
    reason="vPICC table-card slot not configured in pcscd (bench-host setup "
           "required: vpcd driver + reader.conf entry for 127.0.0.1:35970)")


def test_model_golden_roundtrip_live():
    g = json.loads(GOLDEN.read_text())
    atr = (g.get("card_atr") or "").replace(" ", "")
    exchanges = []
    for r in g.get("results", []):
        capdu_hex = (r.get("apdu_hex") or "").replace(" ", "")
        if not capdu_hex or len(capdu_hex) < 8 or capdu_hex.startswith("FFCA"):
            continue
        exchanges.append((bytes.fromhex(capdu_hex),
                          bytes.fromhex(r.get("response_bytes") or "") +
                          bytes.fromhex(r.get("sw") or "6d00")))

    card = GoldenVpicc("127.0.0.1", VPICC_PORT, bytes.fromhex(atr),
                       answerer=ModelVpicc())
    card.start()
    try:
        deadline = time.time() + 60
        while not card.answered_probe.is_set() and time.time() < deadline:
            time.sleep(0.5)
        assert card.answered_probe.is_set(), "vpicc never answered an ATR probe"

        from smartcard.System import readers
        cand = [r for r in readers()
                if any(n in str(r) for n in READER_NAMES) and "00 00" in str(r)]
        assert cand, f"table-card slot not found: {[str(r) for r in readers()]}"
        conn = cand[0].createConnection()
        try:
            conn.connect()
        except Exception:
            time.sleep(3)
            conn = cand[0].createConnection()
            conn.connect()

        def _tx(capdu):
            box = {}

            def run():
                try:
                    d, s1, s2 = conn.transmit(list(capdu))
                    box["r"] = bytes(d) + bytes([s1, s2])
                except Exception as e:  # noqa: BLE001
                    box["err"] = repr(e)
            t = threading.Thread(target=run, daemon=True)
            t.start()
            end = time.time() + 200
            while time.time() < end and "r" not in box and "err" not in box:
                time.sleep(1.0)
            assert "r" in box, f"transmit stalled/errored: {box.get('err')}"
            return box["r"]

        sent = exact = 0
        for capdu, expected in exchanges:  # golden ORDER: budget consumes
            got = _tx(capdu)
            sent += 1
            if got == expected:
                exact += 1
        assert sent >= 1, "no exchanges executed"
        assert exact == sent, f"{sent - exact}/{sent} model deviations"
        assert len(card.apdus_seen) == sent, "pcscd short-circuited transmits"
    finally:
        card.stop()
