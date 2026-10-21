"""Fixtures for the cashu NFC interop suites (bench: ai-legion labgrid lab).

--hil gates every hardware touch (ccid-firmware-rs idiom, mirrors nucula's
tests/hil/phone): plain `pytest` touches nothing; the bench runner and the
operator pass --hil explicitly.

Bench discipline encoded here:
- flock /tmp/amperstrand-bench.lock BEFORE labgrid acquire, never reversed
  (AB-BA protocol shared with every other lane on this host);
- places are acquired per module and released on teardown;
- a busy bench (place held by another lane) is a LOUD SKIP, not a failure;
- the ACR1252 is READ-ONLY on this bench: the payer suite refuses it by
  construction (bench/payer.py guard) and no test ever emits UPDATE BINARY
  through the ACR.
"""
from __future__ import annotations

import datetime
import fcntl
import os
import subprocess
import time
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
RESULTS_ROOT = REPO / "results"

BENCH_LOCK = "/tmp/amperstrand-bench.lock"
LABGRID = ["labgrid-client", "-x", "ai-legion:20408"]


def sh(cmd: list[str], timeout: float = 60) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def pytest_addoption(parser):
    parser.addoption("--hil", action="store_true", default=False,
                     help="drive real bench hardware (labgrid/adb/pcscd)")
    parser.addoption("--mint-url", action="store",
                     default="https://testnut.cashu.space",
                     help="mint the wallets use (fake-sat testnut default)")
    parser.addoption("--soak-cycles", action="store", type=int, default=5,
                     help="cycles for the soak suite (CI dispatch overrides)")
    parser.addoption("--token", action="store", default=None,
                     help="cashuA/B token string for the payer write test")


def _need_hil(request) -> None:
    if not request.config.getoption("--hil"):
        pytest.skip("hardware gated: pass --hil on the bench runner")


class BenchLock:
    """flock holder around labgrid acquire (AB-BA discipline)."""

    def __init__(self):
        self.fd = None

    def __enter__(self):
        self.fd = open(BENCH_LOCK, "w")
        fcntl.flock(self.fd, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        if self.fd:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
            self.fd.close()
        return False


def acquire_places(names: list[str], why: str, timeout_s: float = 120.0):
    """Acquire labgrid places flock-first. Returns holder list or skips loudly
    when the bench is busy with another lane."""
    held = []
    deadline = time.monotonic() + timeout_s
    with BenchLock():
        for name in names:
            while True:
                r = sh(LABGRID + ["-p", name, "acquire"], timeout=timeout_s)
                if r.returncode == 0:
                    sh(LABGRID + ["-p", name, "set-comment",
                                  f"cashu-nfc-matrix hil ({why})"])
                    held.append(name)
                    break
                busy = "currently acquired" in (r.stdout + r.stderr)
                if not busy or time.monotonic() > deadline:
                    for h in held:
                        sh(LABGRID + ["-p", h, "release"])
                    who = sh(LABGRID + ["-p", name, "show"], timeout=30).stdout
                    pytest.skip(f"bench busy: {name} held\n{who[-400:]}")
                time.sleep(5)
    return held


def release_places(names: list[str]):
    with BenchLock():
        for name in names:
            sh(LABGRID + ["-p", name, "release"])


# ---------------------------------------------------------------- evidence


@pytest.fixture(scope="session")
def evidence_dir(request) -> Path:
    _need_hil(request)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    d = RESULTS_ROOT / f"hil-{stamp}"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------- places


@pytest.fixture(scope="module")
def phone_place(request):
    """phone-s20 for the whole module. Restores the two bench boltcard HCE
    apps on teardown (they are disabled during wallet tests to avoid NDEF-AID
    AppChooser conflicts — see bench/PROTOCOL.md)."""
    _need_hil(request)
    held = acquire_places(["phone-s20"], why="phone driving")
    from drivers import ui

    for pkg in ("com.amperstrand.boltcard.hce", "dev.boltcard.hce"):
        sh(["adb", "-s", ui.DEFAULT_SERIAL, "shell", "pm", "disable-user",
            "--user", "0", pkg])
    yield ui.DEFAULT_SERIAL
    for pkg in ("com.amperstrand.boltcard.hce", "dev.boltcard.hce"):
        sh(["adb", "-s", ui.DEFAULT_SERIAL, "shell", "pm", "enable", pkg])
    release_places(held)


@pytest.fixture(scope="module")
def acr_place(request):
    """ref-acr1252 (READ-ONLY discipline)."""
    _need_hil(request)
    held = acquire_places(["ref-acr1252"], why="ACR field read")
    yield "ACS ACR1252"
    release_places(held)


@pytest.fixture(scope="module")
def nucula_reader_place(request):
    """nucula-c3 console+broker. Teardown leaves broker+pcscd healthy."""
    _need_hil(request)
    held = acquire_places(["nucula-c3"], why="nucula as reader")
    # board settles -> broker -> pcscd restart (documented pickup order)
    sh(["systemctl", "restart", "nucula-ccid-broker"])
    time.sleep(6)
    sh(["systemctl", "restart", "pcscd"])
    time.sleep(5)
    yield "Nucula CCID"
    release_places(held)


# ---------------------------------------------------------------- wallets


@pytest.fixture(scope="module")
def cashu_me(phone_place):
    import sys

    sys.path.insert(0, str(REPO))
    from drivers.cashu_me import CashuMeDriver

    d = CashuMeDriver(phone_place)
    d.wake()
    d.launch()
    return d
