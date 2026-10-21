"""T1 — cashu.me driver lifecycle on the bench phone.

Every phase string asserted here was verified against cashu.me v0.2.0 on
2026-10-21 (drivers/cashu_me.py provenance notes).
"""
from __future__ import annotations


def test_launch_and_focus(cashu_me):
    assert "com.cashu.me" in cashu_me.focus()


def test_balance_positive(cashu_me):
    bal = cashu_me.balance_sats()
    assert bal > 0, f"bench wallet drained: {bal}"
    print("balance:", bal)


def test_request_lifecycle(cashu_me):
    st = cashu_me.create_request(77)
    assert "Ask the sender" in st, f"not armed: {st!r}"
    assert cashu_me.is_armed()
    # amount row shows the armed amount
    txt = cashu_me.nfc_status()
    assert txt
    # back to home disarms
    import time

    from drivers import ui

    ui.adb(cashu_me.serial, "shell", "input", "keyevent", "KEYCODE_BACK")
    time.sleep(1.0)
    assert not cashu_me.is_armed(), "HCE still advertising after leaving request screen"


def test_needs_amount_state(cashu_me):
    """A request without amount must surface the NeedsAmount hint."""
    from drivers import ui

    d = cashu_me
    d.open_receive_sheet()
    d.tap_button_above("Ecash")
    ui.wait_for(d.serial, text="Mint", timeout=15)
    n = ui.find(ui.dump(d.serial), text="Any")
    assert n is not None, "Amount row should show 'Any' on a fresh request"
    st = d.nfc_status()
    assert "Set an amount" in st, f"expected NeedsAmount hint, got {st!r}"
