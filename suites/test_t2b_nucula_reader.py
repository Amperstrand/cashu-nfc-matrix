"""T2b — the nucula-as-reader leg: same Type-4 read through the c3's PN7160
via the CCID broker ('Nucula CCID via broker' in pcscd).

Bench geometry truth (HIL-PHONE-DESIGN.md): the phone sits on the ACR antenna;
T4 needs it on the PN7160 antenna. Until someone moves the phone, this suite
SKIP-LOUDLY when no coupling — a skip here is a real bench fact, never a pass.
"""
from __future__ import annotations

import time

import pytest

from bench.probe_acr import read_ndef_request


def _coupled(subst: str, tries: int = 4) -> bool:
    from smartcard.System import readers

    rs = [str(r) for r in readers()]
    if not any(subst in r for r in rs):
        pytest.skip(f"reader {subst!r} not present in pcscd (broker down?)")
    for _ in range(tries):
        try:
            read_ndef_request(subst)
            return True
        except Exception:
            time.sleep(2)
    return False


def test_nucula_reader_reads_cashu_me_request(cashu_me, nucula_reader_place, evidence_dir):
    st = cashu_me.create_request(55)
    assert "Ask the sender" in st, f"not armed: {st!r}"
    if not _coupled("Nucula CCID"):
        pytest.skip(
            "NO COUPLING: phone not on PN7160 antenna (bench geometry — "
            "move phone onto nucula antenna to enable; design doc T4)"
        )
    res = read_ndef_request("Nucula CCID")
    (evidence_dir / "t2b-nucula-read.json").write_text(str(res))
    assert res.get("creq", {}).get("a") == 55
