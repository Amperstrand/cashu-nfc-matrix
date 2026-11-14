"""End-to-end substitution smoke: probe_acr reads a VIRTUAL card.

The vpicc payoff (audit follow-up #5 final leg): bench.probe_acr's
generic Type-4 ladder against the model served over vpcd, carrying a
REAL creqA NDEF built by this repo's own bench.ndef.text_type4_file —
proving the whole read path works without physical silicon.

Bench-host only (vPICC slot + cbor2); skips gracefully elsewhere.
"""

from __future__ import annotations

import base64
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

pytest.importorskip("smartcard", reason="pyscard: bench-host dep")
cbor2 = pytest.importorskip("cbor2", reason="cbor2: bench-host dep")

from bench.vpicc.vpicc_golden import GoldenVpicc  # noqa: E402
from bench.vpicc.vpicc_model import ModelVpicc  # noqa: E402
from bench.ndef import text_type4_file  # noqa: E402

VPICC_PORT = 35970
GOLDEN_ATR = bytes.fromhex("3B8180018080")


def _slot_present() -> bool:
    try:
        from smartcard.System import readers
        names = [str(r) for r in readers()]
    except Exception:  # noqa: BLE001
        return False
    if not any("vPICC table card" in n and "00 00" in n for n in names):
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
    not _slot_present(),
    reason="vPICC table-card slot not configured (bench-host setup)")


def test_probe_acr_reads_creq_from_virtual_card():
    # A real (tiny) NUT-18 request: creqA + base64url(CBOR map)
    payload = cbor2.dumps({"k": "00"})  # minimal valid CBOR map
    creq_text = "creqA" + base64.urlsafe_b64encode(payload).decode().rstrip("=")
    ndef_file = text_type4_file(creq_text)  # len-prefix + text record
    raw_message = ndef_file[2:]             # the model takes the raw message

    card = GoldenVpicc("127.0.0.1", VPICC_PORT, GOLDEN_ATR,
                       answerer=ModelVpicc(ndef_file=raw_message))
    card.start()
    try:
        deadline = time.time() + 60
        while not card.answered_probe.is_set() and time.time() < deadline:
            time.sleep(0.5)
        assert card.answered_probe.is_set(), "vpicc never answered an ATR probe"

        from bench.probe_acr import read_ndef_request
        out = read_ndef_request("vPICC table card")
        assert out.get("select_aid_sw") == "9000", out
        assert out.get("select_ndef_sw") == "9000", out
        assert "parse_error" not in out, out
        assert out.get("ndef_text") == creq_text, out
        creq = out.get("creq")
        assert isinstance(creq, dict), out
    finally:
        card.stop()
