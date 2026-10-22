"""T5 — full NFC payment round-trip through the nucula reader.

This is the crown-jewel test: wallet wipe -> fresh onboard -> mint a fake-sat
token -> arm a matching request -> payer WRITES the token over NFC via the
nucula CCID reader -> the phone redeems -> balance asserted.

Runner requirements (all encoded, no LLM in the loop):
- phone on the LAB wifi (SSID '2', 192.168.13.0/24) — the tollgate AP
  filters egress and the wallet will silently swap against cached state;
  bench/wifi_check.sh asserts this precondition
- nucula-c3 on fresh ccid-firmware-rs (c3-ccid preset); broker + pcscd up
- the nucula rig (payer feature) for token minting — bench/mint_token.sh
- FEE HEADROOM: amounts >= 2 sats (testnut input_fee_ppk=100 eats 1-sat
  tokens; cdk mint returns TransactionUnbalanced(0,0,0))
"""
from __future__ import annotations

import subprocess
import time

import pytest

from bench.payer import Type4Payer

pytestmark = pytest.mark.payer

AMOUNT = 21  # fee headroom; see module docstring


def _phone_on_lab_wifi(serial: str) -> bool:
    out = subprocess.run(
        ["adb", "-s", serial, "shell", "ip", "addr", "show", "wlan0"],
        capture_output=True, text=True, timeout=30,
    ).stdout
    return "192.168.13." in out


def test_nfc_payment_round_trip(cashu_me, nucula_reader_place, request, evidence_dir, tmp_path):
    from drivers import ui

    if not _phone_on_lab_wifi(cashu_me.serial):
        pytest.skip("phone not on lab wifi (192.168.13.x) — connect via "
                    "bench/wifi_connect.py; the tollgate AP filters egress")

    token_file = tmp_path / "token.txt"
    r = subprocess.run(
        ["bash", "bench/mint_token.sh", str(token_file), str(AMOUNT)],
        capture_output=True, text=True, timeout=300, cwd=str(evidence_dir.parent.parent),
    )
    if r.returncode != 0:
        pytest.skip(f"mint failed (rig/mint reachable?): {r.stdout[-200:]}")
    token = token_file.read_text().strip()
    assert token.startswith("cashu")

    cashu_me.wipe()  # conditional onboarding: picker used if present, else Mints screen
    bal0 = cashu_me.balance_sats()
    assert bal0 == 0, f"fresh wallet not zero: {bal0}"

    st = cashu_me.create_request(AMOUNT)
    assert "Ask the sender" in st, f"not armed: {st!r}"

    payer = Type4Payer("Nucula CCID")
    print("ATR:", payer.connect())
    req = payer.read_request()
    assert req.get("a") == AMOUNT, f"wrong request over NFC: {req}"
    t0 = time.time()
    w = payer.write_token(token)
    write_s = round(time.time() - t0, 1)
    print(f"write: {w} in {write_s}s")

    # watch the request screen (NO navigation — balance_sats would BACK out
    # and disarm mid-redemption; learned the hard way)
    for _ in range(15):
        time.sleep(4)
        txt = ui.screen_text(cashu_me.serial)
        if "Payment received" in txt:
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
    (evidence_dir / "t5-roundtrip.txt").write_text(
        f"amount={AMOUNT} credited={credited} write_s={write_s} "
        f"chunks={w['chunks']} bytes={w['bytes']}\n"
    )
