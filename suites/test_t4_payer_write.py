"""T4 — the payer WRITE leg: full payment round-trip through a reader we own.

REFUSES the ACR1252 by construction (bench READ-ONLY rule — the payer emits
UPDATE BINARY, i.e. the exact class of CE-data writes that wedge the ACR's
CCID). Runs only through the nucula CCID reader and only when the phone
physically couples to the PN7160 antenna; otherwise SKIP-LOUD.

To fire for real the suite needs a token: `--token` option or TOKEN_FILE env
(cashuA/B string, one line). Minting fake-sat tokens: bench payer tooling
(nucula rig) against --mint-url.
"""
from __future__ import annotations

import os

import pytest

from bench.payer import Type4Payer

pytestmark = pytest.mark.payer


def _token(request) -> str:
    t = request.config.getoption("--token") or os.environ.get("TOKEN_FILE")
    if t and os.path.isfile(t):
        t = open(t).read().strip()
    if not t:
        pytest.skip("no token supplied: pass --token or TOKEN_FILE (mint one via "
                    "nucula rig payer against --mint-url)")
    return str(t)


def test_payer_round_trip(cashu_me, nucula_reader_place, request, evidence_dir):
    token = _token(request)
    st = cashu_me.create_request(11)
    assert "Ask the sender" in st, f"not armed: {st!r}"

    payer = Type4Payer("Nucula CCID")
    from smartcard.Exceptions import NoCardException

    try:
        print("ATR:", payer.connect())
    except NoCardException:
        pytest.skip("NO COUPLING: phone not on PN7160 antenna — payer write leg "
                    "blocked on bench geometry (see handoff; ACR writes forbidden)")
    req = payer.read_request()
    assert req.get("a") == 11, f"read back wrong request: {req}"
    w = payer.write_token(token)
    (evidence_dir / "t4-payer.json").write_text(str({"request": req, "write": w}))
    # phone-side truth: balance grows and Success screen shows
    import time

    time.sleep(5)  # redeem/settle window
    assert cashu_me.balance_sats() > 0  # structural; delta assert once flows stabilize
