"""T3v — virtual substitution-mode soak pin (SESSION C, 2026-11-18).

Pins bench/tap_soak.py --virtual: a fresh-amount creqA served by a
fresh ModelVpicc per cycle on the vpcd slot, read through the unchanged
probe_acr ladder, JSONL tagged mode=virtual — plus the bad-read
injection proving the error_class taxonomy classifies virtual-mode
failures (parse failure -> "tool").

Bench-host only (vPICC slot + cbor2); skips gracefully elsewhere.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

pytest.importorskip("smartcard", reason="pyscard: bench-host dep")
pytest.importorskip("cbor2", reason="cbor2: bench-host dep")

from bench.tap_soak import soak_virtual, virtual_slot_present  # noqa: E402

pytestmark = pytest.mark.skipif(
    not virtual_slot_present(),
    reason="vPICC table-card slot not configured (bench-host setup)")


def _rows(path: str) -> list[dict]:
    return [json.loads(l) for l in Path(path).read_text().splitlines() if l]


def test_virtual_soak_fresh_amounts():
    with tempfile.TemporaryDirectory() as d:
        out = str(Path(d) / "v.jsonl")
        rc = soak_virtual(cycles=2, base_amount=30, out_path=out)
        rows = _rows(out)
        assert rc == 0 and len(rows) == 2, rows
        assert all(r.get("mode") == "virtual" and r.get("ok") for r in rows)
        assert [r["amount"] for r in rows] == [30, 31]
        # the parse+verify path is real: decoded creq carries the armed fields
        assert [r["creq"]["a"] for r in rows] == [30, 31]
        assert all(r["creq"].get("u") == "sat" for r in rows)


def test_virtual_soak_bad_read_classifies_as_tool():
    with tempfile.TemporaryDirectory() as d:
        out = str(Path(d) / "v-bad.jsonl")
        rc = soak_virtual(cycles=3, base_amount=40, out_path=out,
                          inject_bad_at=1)
        rows = _rows(out)
        assert len(rows) == 3, rows
        bad = rows[1]
        assert bad.get("injected") == "bad_ndef" and bad.get("ok") is False
        assert bad.get("read_error_class") == "tool", bad  # NDEF parse owner
        # neighbors unaffected — fresh card per cycle absorbs the fault
        assert rows[0].get("ok") is True and rows[2].get("ok") is True
        assert rc != 0  # the injected failure is visible, never hidden
