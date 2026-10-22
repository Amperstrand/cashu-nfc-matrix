"""T0 — place smoke: the bench can run a wallet session at all.

Requires --hil. Fast; run before any wallet driving.
"""
from __future__ import annotations

import subprocess

from drivers import ui
from suites.conftest import sh


def test_phone_adb_present(phone_place):
    r = sh(["adb", "-s", phone_place, "get-state"], timeout=30)
    assert r.returncode == 0 and r.stdout.strip() == "device"


def test_wallet_installed_and_version(phone_place):
    r = sh(["adb", "-s", phone_place, "shell", "dumpsys", "package", "com.cashu.me"])
    assert "com.cashu.me" in r.stdout
    m = [ln for ln in r.stdout.splitlines() if "versionName" in ln]
    assert m, "versionName not found"
    print("cashu.me", m[0].strip())


def test_phone_unlocked_screenon(phone_place):
    r = sh(["adb", "-s", phone_place, "shell", "dumpsys", "window"])
    assert "isKeyguardShowing=false" in r.stdout, "phone locked — HCE requires unlock"
    p = sh(["adb", "-s", phone_place, "shell", "dumpsys", "power"])
    assert "mWakefulness=Awake" in p.stdout, "phone asleep"


def test_acr_reader_in_pcscd(acr_place):
    from smartcard.System import readers

    rs = [str(x) for x in readers()]
    assert any("ACR1252" in r and "PICC" in r for r in rs), f"ACR1252 PICC missing: {rs}"


def test_nucula_reader_state_recorded(nucula_reader_place):
    """Informational: the nucula CCID reader may or may not couple to the phone
    (bench geometry); the suite only records its pcscd presence here."""
    from smartcard.System import readers

    rs = [str(x) for x in readers()]
    print("nucula reader:", [r for r in rs if "Nucula CCID" in r] or "MISSING")
    # not an assert-by-design: T2b owns the coupling verdict
