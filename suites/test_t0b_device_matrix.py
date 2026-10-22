"""Device-matrix grid probe: enumerate every configured bench reader,
check presence + one coupling attempt, and emit the live grid.

This is the 'what's testable RIGHT NOW' snapshot for docs/DEVICE-MATRIX.md —
absent readers skip loudly with their recovery hint instead of hiding.
"""
from __future__ import annotations

import time

READERS = [
    # (id, pcscd substring, recovery hint when absent)
    ("acr1252", "ACR1252", "check USB bind: bench/field_arbiter.py status; lsusb"),
    ("nucula-pn7160", "Nucula CCID",
     "broker+pcscd dance: field_arbiter grant nucula; if still blind -> reflash c3-ccid"),
    ("m5stick-mfrc522", "M5stick GemPC",
     "DTR-hold recovery across a pcscd restart (FTDI replugged); see amperstrand-ops skill"),
]


def test_device_matrix_grid(phone_place, request, evidence_dir):
    from smartcard.System import readers

    # SURVEY mode: bring both controllable readers up for the probe, then
    # return the bench to quiet (fields arbitrated, not left on).
    from bench.field_arbiter import _acr_bind, _broker, _pcscd_restart

    _acr_bind(True)
    _broker(True)
    time.sleep(6)
    _pcscd_restart()
    try:
        _grid(readers, evidence_dir)
    finally:
        from bench.field_arbiter import grant

        grant("quiet")


def _grid(readers, evidence_dir):
    rs = list(readers())
    names = [str(r) for r in rs]
    grid = ["# live device-matrix grid (readers)"]
    for rid, subst, hint in READERS:
        present = [r for r, n in zip(rs, names) if subst in n]
        coupled = "-"
        if present:
            try:
                c = present[0].createConnection()
                c.connect()
                coupled = "COUPLES (ATR " + " ".join(f"{b:02x}" for b in c.getATR()[:6]) + "..)"
                c.disconnect()
            except Exception as e:
                coupled = f"present, no coupling ({type(e).__name__})"
        else:
            print(f"{rid}: ABSENT -> {hint}")
        grid.append(f"- {rid}: {'present' if present else 'ABSENT'} | {coupled}")
        print(f"{rid}: {'present' if present else 'ABSENT'} | {coupled}")
    out = evidence_dir / "device-matrix-grid.txt"
    out.write_text("\n".join(grid) + "\n")
