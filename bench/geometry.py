"""Geometry-aware cell selection.

The bench phone sits in exactly ONE reader's field at a time (physical
fact). Parametrized cells for other readers used to fail loudly ("NoCard",
"reader not present") — noise that hid real regressions. A cell whose
geometry is not live now SKIPS with a precise reason instead.

The phone's current position is declared, not detected (detection would
need hardware):

  - file:  bench/phone-at            (one word: nucula | acr | m5stick)
  - env:   PHONE_AT=nucula           (env wins over the file)
  - CI:    the workflow dispatch sets PHONE_AT per stage

`unknown` (neither set) keeps ALL cells running — legacy behavior, no
silent skips from a stale declaration.

Bench discipline unchanged: the field arbiter still serializes readers;
this only gates which cells make sense to attempt.
"""
from __future__ import annotations

import os
from pathlib import Path

VALID = ("nucula", "acr", "m5stick", "unknown")

# reader-name substring -> geometry slot
READER_TO_SLOT = {
    "Nucula": "nucula",
    "ACR": "acr",
    "M5stick": "m5stick",
}


def phone_at() -> str:
    v = os.environ.get("PHONE_AT", "").strip().lower()
    if v in VALID:
        return v
    f = Path(__file__).parent / "phone-at"
    if f.exists():
        v = f.read_text().strip().lower()
        if v in VALID:
            return v
    return "unknown"


def slot_for_reader(reader: str) -> str:
    for k, v in READER_TO_SLOT.items():
        if reader.startswith(k):
            return v
    return "unknown"


def cell_live(reader: str) -> tuple[bool, str]:
    """(live?, reason). Live when the declared position matches the reader
    (or nothing is declared)."""
    at = phone_at()
    if at == "unknown":
        return True, ""
    slot = slot_for_reader(reader)
    if slot == at:
        return True, ""
    return False, f"phone declared at '{at}', not in {reader}'s field (bench/phone-at)"
