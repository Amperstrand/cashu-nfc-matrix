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


def _probe_with_retries(subst: str, tries: int = 4, wedged_s: float = 45.0):
    """Probe with interference tolerance.

    - transient NoCard/unavailable (bc-taploop interleave): short backoff
    - a TransmitTimeout watchdog KILL leaves pcscd's IFD busy on the reader
      for tens of seconds; the next attempt must cool down long enough or
      every later connect reports 'Reader is unavailable' (0x80100017).
    """
    import time

    from bench.probe_acr import TransmitTimeout

    last: Exception = RuntimeError("no probe attempt executed")
    for i in range(tries):
        try:
            return read_ndef_request(subst)
        except TransmitTimeout as e:
            last = e
            time.sleep(wedged_s)  # let pcscd's IFD clear
        except Exception as e:
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


@pytest.mark.flaky(reruns=2, reruns_delay=45)
def test_unarmed_e104_absent(cashu_me, acr_place):
    """E104 must 6A82 with no armed request (receiver truthfulness).

    Disarms by LEAVING the request screen (BACK), not by killing the app:
    the HCE service stays bound and answers SELECT NDEF, so the probe can
    never hang. Force-stop+early-probe = nobody answers the SELECT = the
    watchdog kill wedges the ACR's IFD until a pcscd restart (bench fact).
    """
    import time

    from drivers import ui

    st = cashu_me.create_request(12)
    assert "Ask the sender" in st, f"not armed: {st!r}"
    ui.adb(cashu_me.serial, "shell", "input", "keyevent", "KEYCODE_BACK")
    time.sleep(2.0)
    assert not cashu_me.is_armed(), "still advertising after leaving request screen"
    res = _probe_with_retries("ACR1252", tries=3)
    assert res.get("select_aid_sw") == "9000"
    assert res.get("select_ndef_sw") == "6a82", (
        f"E104 answered without armed request: {res.get('select_ndef_sw')}"
    )


@pytest.mark.flaky(reruns=2, reruns_delay=45)
@pytest.mark.skipif(
    __import__("subprocess").run(
        ["adb", "-s", __import__("drivers.ui", fromlist=["ui"]).DEFAULT_SERIAL,
         "shell", "pm", "list", "packages"],
        capture_output=True, text=True).stdout.find("com.electricdreams.numo") < 0,
    reason="Numo not installed on bench phone",
)
def _reader_params():
    import pytest as _pytest
    from bench import geometry
    out = []
    for r in ("ACR1252", "M5stick GemPC"):
        live, reason = geometry.cell_live(r)
        marks = [] if live else [_pytest.mark.skip(reason=reason)]
        out.append(_pytest.param(r, marks=marks))
    return out


@pytest.mark.parametrize("reader", _reader_params())
def test_numo_request(phone_place, acr_place, evidence_dir, reader):
    """Numo v1.9 PoS: Charge screen arms HCE; request is BIP21+CREQ or
    BIP21+LIGHTNING (both observed on the bench; both are NDEF URI records).
    """
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
        ui.adb(phone_place, "shell", "pm", "disable-user", "--user", "0", "com.cashu.me")
        time.sleep(1.0)
        res = _probe_with_retries(reader)
        (evidence_dir / f"t2-numo-{reader.split()[0].lower()}.json").write_text(
            __import__("json").dumps(res, indent=1))
        assert res.get("select_aid_sw") == "9000"
        assert res["cc"] == CC_PINNED
        text = res.get("ndef_text", "")
        assert text.upper().startswith("BITCOIN:?"), f"unexpected numo payload: {text[:60]!r}"
    finally:
        ui.adb(phone_place, "shell", "pm", "enable", "com.cashu.me")
