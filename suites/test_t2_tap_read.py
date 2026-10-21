"""T2 — tap read flows: armed wallet HCE -> reader -> verified NUT-18 request.

Parametrized over the wallets that can present (cashu.me always; Numo if
installed). The ACR1252 leg is read-only by construction (probe never emits
UPDATE BINARY — bench rule).
"""
from __future__ import annotations

import pytest

from bench.probe_acr import read_ndef_request

CC_PINNED = "000f20003b00340406e10470ff0000"  # cashu.me == Numo, 2026-10-21
ATR_PINNED_PREFIX = "3b 88 80 01 00 00 00 00 80 81 71 00 79"


def _probe_with_retries(subst: str, tries: int = 4):
    import time

    last: Exception = RuntimeError("no probe attempt executed")
    for i in range(tries):
        try:
            return read_ndef_request(subst)
        except Exception as e:  # bc-taploop interleave / transient reader state
            last = e
            time.sleep(2 + i * 2)
    raise last


@pytest.mark.parametrize("amount", [21, 64])
def test_cashu_me_request_over_acr(cashu_me, acr_place, evidence_dir, amount):
    st = cashu_me.create_request(amount)
    assert "Ask the sender" in st, f"not armed: {st!r}"
    res = _probe_with_retries("ACR1252")
    (evidence_dir / f"t2-cashu-me-{amount}.json").write_text(
        __import__("json").dumps(res, indent=1)
    )
    assert res.get("select_aid_sw") == "9000"
    assert res["cc"] == CC_PINNED, f"CC drifted: {res['cc']}"
    assert res["atr"] == ATR_PINNED_PREFIX, f"ATR drifted: {res['atr']}"
    creq = res["creq"]
    assert creq["a"] == amount, f"amount mismatch: {creq}"
    assert creq["u"] == "sat"
    assert creq["m"], "mint list empty"


def test_unarmed_e104_absent(cashu_me, acr_place):
    """E104 must 6A82 with no armed request (receiver truthfulness)."""
    from drivers import ui

    ui.adb(cashu_me.serial, "shell", "am", "force-stop", "com.cashu.me")
    import time

    time.sleep(1.5)
    ui.adb(cashu_me.serial, "shell", "monkey", "-p", "com.cashu.me",
           "-c", "android.intent.category.LAUNCHER", "1")
    time.sleep(3)
    cashu_me.go_home()  # armed request screen is NOT open
    res = read_ndef_request("ACR1252")
    assert res.get("select_aid_sw") == "9000"
    assert res.get("select_ndef_sw") == "6a82", (
        f"E104 answered without armed request: {res.get('select_ndef_sw')}"
    )


@pytest.mark.skipif(
    __import__("subprocess").run(
        ["adb", "-s", __import__("drivers.ui", fromlist=["ui"]).DEFAULT_SERIAL,
         "shell", "pm", "list", "packages"],
        capture_output=True, text=True).stdout.find("com.electricdreams.numo") < 0,
    reason="Numo not installed on bench phone",
)
def test_numo_request_over_acr(phone_place, acr_place, evidence_dir):
    """Numo v1.9 PoS: Charge screen arms HCE; request is BIP21+creqB."""
    import sys
    import time

    sys.path.insert(0, ".")
    from drivers import ui
    from drivers.numo import NumoDriver

    d = NumoDriver(phone_place)
    try:
        d.launch()
        d.charge(33)
        assert d.is_armed(), f"numo not armed: {d.screen()!r}"
        # isolate: cashu.me is the AID default; disable it for this probe
        sh_out = ui.adb(phone_place, "shell", "pm", "disable-user", "--user", "0", "com.cashu.me")
        time.sleep(1.0)
        res = _probe_with_retries("ACR1252")
        (evidence_dir / "t2-numo.json").write_text(__import__("json").dumps(res, indent=1))
        assert res.get("select_aid_sw") == "9000"
        assert res["cc"] == CC_PINNED
        text = res.get("ndef_text", "")
        assert text.upper().startswith("BITCOIN:?CREQ="), f"unexpected numo payload: {text[:60]!r}"
    finally:
        ui.adb(phone_place, "shell", "pm", "enable", "com.cashu.me")
