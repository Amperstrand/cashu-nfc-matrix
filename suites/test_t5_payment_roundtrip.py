"""T5 — full NFC payment round-trip through BOTH readers (static bench).

Two phases, one static stack (nucula wedged between ACR and phone):
  ["Nucula CCID"] — arbiter grants the field to the nucula (ACR muted)
  ["ACR1252"]     — arbiter grants the field to the ACR (nucula parked)
Each phase: mint -> wipe phone wallet -> arm -> read request -> WRITE token
over NFC -> phone redeems -> balance asserted.

Runner requirements (encoded, no LLM in the loop):
- phone on the LAB wifi (SSID '2', 192.168.13.0/24) — the tollgate AP
  filters egress and the wallet will silently swap against cached state
  (bench/wifi_check.sh asserts this precondition)
- nucula-c3 on fresh ccid-firmware-rs (c3-ccid preset)
- the nucula rig (payer feature) for token minting — bench/mint_token.sh
- FEE HEADROOM: amounts >= 2 sats (testnut input_fee_ppk=100 eats 1-sat
  tokens; cdk mint returns TransactionUnbalanced(0,0,0))
"""
from __future__ import annotations

import os
import subprocess
import time

import pytest

from bench.field_arbiter import grant
from bench.payer import Type4Payer

pytestmark = pytest.mark.payer

AMOUNT = 21  # fee headroom; see module docstring


def _phone_on_lab_wifi(serial: str) -> bool:
    out = subprocess.run(
        ["adb", "-s", serial, "shell", "ip", "addr", "show", "wlan0"],
        capture_output=True, text=True, timeout=30,
    ).stdout
    return "192.168.13." in out


@pytest.fixture(scope="module")
def bench_places(request):
    """All three places for the whole module; fields arbitrated per phase."""
    from suites.conftest import acquire_places, release_places

    if not request.config.getoption("--hil"):
        pytest.skip("hardware gated: pass --hil on the bench runner")
    held = acquire_places(["phone-s20", "nucula-c3", "ref-acr1252", "m5stick"],
                          why="T5 tri-reader payment (m5stick seat added 10-23)")
    yield held
    grant("quiet")
    release_places(held)


def _reader_params():
    import pytest as _pytest
    from bench import geometry
    out = []
    for r in ("Nucula CCID", "ACR1252", "M5stick GemPC"):
        live, reason = geometry.cell_live(r)
        marks = [] if live else [_pytest.mark.skip(reason=reason)]
        out.append(_pytest.param(r, marks=marks))
    return out


@pytest.mark.parametrize("reader", _reader_params())
def test_nfc_payment_round_trip(bench_places, reader, request, evidence_dir, rec, tmp_path):
    from drivers import ui
    from drivers.cashu_me import CashuMeDriver

    serial = "RF8NB01ZYAH"
    if not _phone_on_lab_wifi(serial):
        pytest.skip("phone not on lab wifi — run bench/wifi_connect.py")

    token_file = tmp_path / "token.txt"
    mint_url = os.environ.get("MINT_URL", "https://testnut.cashu.space")
    env = dict(os.environ, MINT_URL=mint_url)
    r = subprocess.run(
        ["bash", "bench/mint_token.sh", str(token_file), str(AMOUNT)],
        capture_output=True, text=True, timeout=300, env=env,
        cwd=str(evidence_dir.parent.parent),
    )
    if r.returncode != 0:
        pytest.skip(f"mint failed (rig/mint reachable?): {r.stdout[-200:]}")
    token = token_file.read_text().strip()
    assert token.startswith("cashu")

    cashu_me = CashuMeDriver(serial)
    cashu_me.wipe(setup_mint=mint_url)  # local bench mint when MINT_URL is set
    bal0 = cashu_me.balance_sats()
    assert bal0 == 0, f"fresh wallet not zero: {bal0}"

    rec.event("wallet", f"wipe done, arming {AMOUNT} sat request")
    st = cashu_me.create_request(AMOUNT)
    assert "Ask the sender" in st, f"not armed: {st!r}"
    rec.event("wallet", "armed", amount=AMOUNT)
    rec.still("armed-request")

    # ---- field arbitration: exactly one reader live for this phase ----
    grant("nucula" if reader.startswith("Nucula") else "acr" if reader.startswith("ACR") else "m5stick")

    rec.event("nfc", f"field granted; payer connecting via {reader}")
    payer = Type4Payer(reader)
    print(f"[{reader}] ATR:", payer.connect())
    req = payer.read_request()
    assert req.get("a") == AMOUNT, f"wrong request over NFC: {req}"
    t0 = time.time()
    w = payer.write_token(token)
    write_s = round(time.time() - t0, 1)
    print(f"[{reader}] write: {w} in {write_s}s")
    rec.event("nfc", "token written", reader=reader, chunks=w["chunks"], write_s=write_s)
    rec.mint_evidence(str(token_file), AMOUNT)
    grant("quiet")  # release the field while the phone redeems over wifi

    # watch the request screen (NO navigation — balance_sats would BACK out
    # and disarm mid-redemption; learned the hard way)
    for _ in range(15):
        time.sleep(4)
        txt = ui.screen_text(cashu_me.serial)
        if "Payment received" in txt:
            rec.event("wallet", "phone shows Payment received")
            rec.still("payment-received")
            break
        if "failed" in txt.lower():
            pytest.fail(f"phone reported payment failure: {txt[:300]}")
    else:
        pytest.fail("no success screen within 60s of the NFC write")

    bal1 = cashu_me.balance_sats()
    credited = bal1 - bal0
    assert credited == AMOUNT - 1, (
        f"expected {AMOUNT - 1} net of 1-sat input fee, got {credited} "
        f"({bal0} -> {bal1})"
    )
    (evidence_dir / f"t5-roundtrip-{reader.replace(' ', '-').lower()}.txt").write_text(
        f"reader={reader} amount={AMOUNT} credited={credited} "
        f"write_s={write_s} chunks={w['chunks']} bytes={w['bytes']}\n"
    )
