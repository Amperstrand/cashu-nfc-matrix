"""vpicc rung-1 port: offline gate for the vendored stateful model.

Two assertions, both host-safe (no pcscd, no hardware):
1. reference-lock — the vendored model + golden match bench/vpicc/LOCK
2. golden-exact  — every replayable golden exchange answers byte-exact
   through the rule engine (the upstream 57/57 check, vendored)

Rung scope: PRE-AUTH only (SELECT/READ-BINARY ladder + empirical rules).
The auth/secure-mode rungs (2-4) live upstream in bolty-rs; porting them
here is future work per docs/cross-project-infra-audit-2026-11-12.md #5.
"""

import hashlib
import re
import subprocess
import sys
from pathlib import Path

BENCH = Path(__file__).resolve().parent.parent / "bench"
VPICC = BENCH / "vpicc"

LOCKED = ["vpicc_model.py", "golden_acr1252.json"]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def test_vendored_model_is_reference_locked():
    lock = (VPICC / "LOCK").read_text()
    pinned = dict(re.findall(r"^(\S+) sha256: ([0-9a-f]{64})$", lock, re.M))
    assert pinned, "LOCK parsed empty — format broken?"
    for rel in LOCKED:
        actual = _sha256(VPICC / rel)
        assert pinned.get(rel) == actual, (
            f"{rel} drifted from the reference-locked vpicc vendor drop "
            f"({actual} vs {pinned.get(rel)}). Re-vendor deliberately per "
            "bench/vpicc/LOCK."
        )
        assert f"{rel} sha256: {actual}" in lock


def test_model_answers_golden_byte_exact():
    """The vendored offline gate must pass 57/57 against the vendored
    golden (behavior computed, only FILE DATA canned)."""
    proc = subprocess.run(
        [sys.executable, str(VPICC / "check_model_vs_golden.py")],
        capture_output=True, text=True, timeout=120, cwd=str(VPICC),
    )
    assert proc.returncode == 0, (
        f"golden check failed:\n{proc.stdout[-800:]}\n{proc.stderr[-400:]}"
    )
    assert "57/57" in proc.stdout, proc.stdout[-400:]
