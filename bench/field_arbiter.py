#!/usr/bin/env python3
"""Field arbiter for the static 3-device NFC bench (ACR + nucula + phone).

Exactly one reader owns the RF field per test phase; the others are muted.
Muting is real (no RF), not just "not used":

- ACR1252  -> USB driver unbind (reversible; proven repeatedly on this bench)
- nucula   -> broker stop (PN7160 parks: idle AND deaf without host polls;
              restart DTR-resets the board -> fresh poll loop, which also
              heals the 'parked after pcscd churn' state)

Transitions restart pcscd (reader set changes) — serialized, ~10-15 s.

Usage (suite fixtures or CLI):
    from bench.field_arbiter import field
    with field("nucula"):
        ...  # only the nucula's field is live
CLI: field_arbiter.py nucula|acr|quiet|status
"""
from __future__ import annotations

import subprocess
import time

ACR_USB = "1-4"  # /sys/bus/usb/devices/1-4 = ACR1252 (verify with lsusb)
BENCH_LOCK = "/tmp/amperstrand-bench.lock"
STATE_FILE = "/tmp/nfc-field-owner"


def sh(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60)


def _acr_bind(on: bool) -> None:
    action = "bind" if on else "unbind"
    import usb.core as _u
    devs = list(_u.find(find_all=True, idVendor=0x072F, idProduct=0x1252)) or \
        list(_u.find(find_all=True, idVendor=0x072F))
    for d in devs:
        # resolve the CURRENT bus/port path — the ACR was replugged by the
        # owner (bus/port changed); a hardcoded ACR_USB goes stale forever
        pn = getattr(d, "port_numbers", None)
        path = f"{d.bus}-" + ".".join(str(p) for p in pn) if pn else f"{d.bus}-{d.address}"
        sh(["bash", "-c", f"echo {path} > /sys/bus/usb/drivers/usb/{action}"])


def _broker(on: bool) -> None:
    sh(["systemctl", "start" if on else "stop", "nucula-ccid-broker"])


def _pcscd_restart() -> None:
    sh(["systemctl", "restart", "pcscd"])
    time.sleep(4)


def _readers() -> list[str]:
    try:
        from smartcard.System import readers

        return [str(r) for r in readers()]
    except Exception:
        return []


def status() -> str:
    rs = _readers()
    acr = any("ACR1252" in r and "PICC" in r for r in rs)
    nuc = any("Nucula CCID" in r for r in rs)
    owner = open(STATE_FILE).read().strip() if _exists(STATE_FILE) else "?"
    return f"owner={owner} acr_in_pcscd={acr} nucula_in_pcscd={nuc}"


def _exists(p: str) -> bool:
    try:
        open(p)
        return True
    except OSError:
        return False


def grant(owner: str) -> None:
    """owner: 'acr' | 'nucula' | 'm5stick' | 'quiet'.

    SINGLE-WRITER: the arbiter is host-global (USB binds, pcscd) — a CI run
    and a local run racing it corrupt each other's reader state (observed:
    first CI dispatch raced a local T5; labgrid place locks do not cover
    host-global effects). Exclusive lock, fail loudly on contention."""
    import fcntl as _f
    import os as _os

    lk = _os.open("/tmp/nfc-field-arbiter.lock", _os.O_RDWR | _os.O_CREAT, 0o666)
    try:
        _os.fchmod(lk, 0o666)
    except PermissionError:
        pass
    try:
        _f.flock(lk, _f.LOCK_EX | _f.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("field arbiter busy: another matrix driver owns the "
                         "host (CI run or local suite) — do not race it")
    try:
        _grant_locked(owner)
    finally:
        _os.close(lk)


def _grant_locked(owner: str) -> None:
    if owner == "acr":
        _acr_bind(True)
        _broker(False)
        _pcscd_restart()
    elif owner == "nucula":
        _acr_bind(False)
        _broker(True)   # restart = board reset = fresh, unparked poll loop
        time.sleep(6)   # board settle before pcscd handshake
        _pcscd_restart()
    elif owner == "m5stick":
        _acr_bind(False)
        _broker(False)
        _pcscd_restart()
    elif owner == "quiet":
        _acr_bind(False)
        _broker(False)
        _pcscd_restart()
    else:
        raise ValueError(f"unknown owner {owner!r}")
    import os as _o
    import getpass as _gp
    # shared file first; a foreign-owner 0644 leftover (root<->runner) falls
    # back to a per-user file — the state is display-only, never gate on it
    for _p in (STATE_FILE, f"{STATE_FILE}-{_gp.getuser()}"):
        try:
            _fd = _o.open(_p, _o.O_RDWR | _o.O_CREAT | _o.O_TRUNC, 0o666)
            try:
                _o.fchmod(_fd, 0o666)
            except PermissionError:
                pass
            with _o.fdopen(_fd, "w") as f:
                f.write(owner)
            break
        except PermissionError:
            continue
    print(f"[field] granted -> {owner} ({status()})")


class field:
    """Context manager: `with field('nucula'):` — restores 'quiet' after."""

    def __init__(self, owner: str):
        self.owner = owner

    def __enter__(self):
        grant(self.owner)
        return self

    def __exit__(self, *exc):
        grant("quiet")
        return False


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "status":
        print(status())
    else:
        grant(sys.argv[1] if len(sys.argv) > 1 else "quiet")
