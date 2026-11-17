#!/usr/bin/env python3
"""Offline ladder measurement: reads-per-cycle for long-form NDEF vs the
plain-read model (SESSION J charter, amperstrand-ops #23).

Drives ModelVpicc's rule engine DIRECTLY (no vpcd, no pcscd) with the two
candidate Type-4 read ladders, sweeping text/binary payload lengths:

  - legacy ladder  : fixed 0x20 (32B) NDEF windows — what
                     probe_acr.read_ndef_request emits today (physical lane,
                     evidence-pinned; simulated here, never altered)
  - mle ladder     : single-window reads with Le = min(MLe from CC, 0xFE)
                     (the model's capture-pinned READ BINARY accepts
                     Le 0x01..0xFE; 0x00/0xFF -> 6985)

Both ladders: SELECT AID -> SELECT CC -> READ CC (Le=0x0F) -> SELECT NDEF
-> READ BINARY windows until NLEN+2 bytes are reassembled. READ_BUDGET=3
successful content reads per card session (CC reads count) — the soak's
fresh-ModelVpicc-per-cycle models a re-tap.

Output: results/ndef-ladder-sweep-<ts>.json (evidence blob) + stdout table.
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bench.ndef import binary_type4_file, parse_type4_file, text_type4_file  # noqa: E402
from bench.vpicc.vpicc_model import Ntag424State, answer  # noqa: E402

SW = (0x90, 0x00)


def _tx(state: Ntag424State, apdu: bytes):
    rapdu = answer(state, apdu)
    return rapdu[:-2], (rapdu[-2], rapdu[-1])


def run_ladder(ndef_message: bytes, window_le: int | None) -> dict:
    """One card session against a FRESH model state; window_le=None means
    the legacy fixed 0x20 windows, an int means single-window Le reads."""
    state = Ntag424State(ndef_file=ndef_message)
    reads = {"cc": 0, "ndef": 0}
    d, sw = _tx(state, bytes.fromhex("00A4040007D276000085010100"))
    assert sw == SW, f"SELECT AID: {sw:x}"
    _tx(state, bytes.fromhex("00A4000C02E103"))
    d, sw = _tx(state, bytes.fromhex("00B000000F"))
    assert sw == SW and len(d) == 15, f"READ CC: {sw:x} len={len(d)}"
    reads["cc"] += 1
    mle = int.from_bytes(d[3:5], "big")
    le = 0x20 if window_le is None else min(window_le, 0xFE)
    _tx(state, bytes.fromhex("00A4000C02E104"))
    file = b""
    off = 0
    total = 1 << 20
    budget_wall = False
    while len(file) < total:
        d, sw = _tx(state, bytes([0x00, 0xB0, (off >> 8) & 0xFF, off & 0xFF, le]))
        if sw == (0x69, 0x85):
            budget_wall = True  # READ_BUDGET exhausted mid-file
            break
        if sw != SW or not d:
            break
        if off == 0 and len(d) >= 2:
            total = ((d[0] << 8) | d[1]) + 2
        file += bytes(d)
        off += len(d)
        reads["ndef"] += 1
    completed = len(file) >= total and total != 1 << 20
    ok = completed and file[:total] == len(ndef_message).to_bytes(2, "big") + ndef_message
    return {"file_len": total, "cc_reads": reads["cc"], "ndef_reads": reads["ndef"],
            "total_reads": reads["cc"] + reads["ndef"], "window_le": le,
            "cc_mle": mle, "completed": bool(completed), "budget_wall_hit": budget_wall,
            "reassembled_ok": bool(ok)}


def real_mint_table() -> list[dict]:
    """SESSION M: the real-mint cashuB class as a FIRST-CLASS artifact.

    Observed real-mint cashuB token lengths: 2715 and 2722 chars (SESSION M
    charter, amperstrand-ops #29). Exact min-reads at Le=0xFE (the widest
    window the capture-pinned READ BINARY accepts):

        file = 2 (NLEN) + NDEF message bytes
        mle  min reads = 1 CC + ceil(file / 254)
        legacy min reads = 1 CC + ceil(file / 32)

    Measured against the model rule engine (run_ladder drives a FRESH
    Ntag424State per ladder = one card session per re-tap), so 'wall' is
    what the soak would actually see, not an estimate.
    """
    rows = []
    for chars in (2715, 2722):
        for kind, msg in (
            ("text", text_type4_file("x" * chars)[2:]),
            ("binary", binary_type4_file(b"x" * chars)[2:]),
        ):
            file_len = len(msg) + 2
            mle_min = 1 + -(-file_len // 254)
            leg_min = 1 + -(-file_len // 32)
            mle = run_ladder(msg, window_le=0xFE)
            legacy = run_ladder(msg, window_le=None)
            rows.append({
                "payload_chars": chars, "kind": kind, "file_len": file_len,
                "mle_min_reads": mle_min, "mle_measured_reads": mle["total_reads"],
                "mle_budget_wall_hit": mle["budget_wall_hit"],
                "legacy_min_reads": leg_min,
                "legacy_measured_reads": legacy["total_reads"],
                "legacy_budget_wall_hit": legacy["budget_wall_hit"],
                "reads_over_budget": max(mle_min, 3) - 3,
                "carries_in_budget": mle_min <= 3 and not mle["budget_wall_hit"],
            })
    return rows


def main() -> int:
    # creqA baseline (the SESSION C proven size) + the charter sweep 100..500,
    # the advertised cliff neighborhood, and the real-mint 2722-char class.
    lengths = [33, 100, 150, 200, 250, 255, 256, 300, 350, 374, 400, 450,
               490, 494, 495, 496, 497, 500, 2715, 2722]
    rows = []
    for L in lengths:
        text = "x" * L
        msg_text = text_type4_file(text)[2:]      # long-form record at L > 255-3
        msg_bin = binary_type4_file(b"x" * L)[2:]
        for kind, msg in (("text", msg_text), ("binary", msg_bin)):
            legacy = run_ladder(msg, window_le=None)
            # mle ladder: Le bound taken FROM the CC it just read (0x2000 here)
            # -> clamped to the model's capture-pinned max Le 0xFE.
            mle = run_ladder(msg, window_le=legacy["cc_mle"])
            # parse round-trip through the shared codec (long-form branch)
            parsed_ok = False
            try:
                parsed_ok = (parse_type4_file(
                    (len(msg)).to_bytes(2, "big") + msg) == ("x" * L)
                    if kind == "text" else parse_type4_file(
                        (len(msg)).to_bytes(2, "big") + msg) == b"x" * L)
            except Exception:
                parsed_ok = False
            rows.append({"payload_chars": L, "kind": kind, "legacy": legacy,
                         "mle": mle, "parse_ok": parsed_ok})
    out = {"ts": time.strftime("%Y%m%d-%H%M%S"), "read_budget": 3, "rows": rows,
           "real_mint_class": real_mint_table(),
           "notes": {
               "legacy": "fixed 0x20 windows — probe_acr.read_ndef_request today (physical lane, untouched)",
               "mle": "single-window reads, Le = min(MLe from CC, 0xFE) — charter option (a)",
               "budget_rule": "READ_BUDGET=3 counts CC reads; 6985 wall after; fresh model per cycle = re-tap",
               "real_mint_class": "SESSION M: observed real-mint cashuB lengths 2715/2722 — exact min-reads at Le=0xFE vs budget 3",
           }}
    path = os.path.join(os.path.dirname(__file__), "..", "results",
                        f"ndef-ladder-sweep-{out['ts']}.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(out, fh, indent=1)
    print(f"{'chars':>5} {'kind':>6} {'file':>5} | {'legacy':>18} | {'mle':>18} | parse")
    print(f"{'':>5} {'':>6} {'':>5} | {'reads wall? done':>18} | {'reads wall? done':>18} |")
    for r in rows:
        for k in ("legacy", "mle"):
            r[k]["fits_budget"] = (r[k]["completed"] and not r[k]["budget_wall_hit"]
                                   and r[k]["total_reads"] <= 3)
        cell = lambda x: (f"{x['total_reads']:>5} {'YES' if x['budget_wall_hit'] else ' no ':>5} "
                          f"{'ok' if x['completed'] and x['reassembled_ok'] else 'TRUNC':>5}")
        print(f"{r['payload_chars']:>5} {r['kind']:>6} {r['legacy']['file_len']:>5} | "
              f"{cell(r['legacy']):>18} | {cell(r['mle']):>18} | {r['parse_ok']}")
    print(f"\nreal-mint cashuB class (SESSION M): min-reads at Le=0xFE vs READ_BUDGET=3")
    print(f"{'chars':>5} {'kind':>6} {'file':>5} | {'mle min/meas':>12} {'wall':>4} | {'leg min':>7} {'wall':>4} | over carries")
    for r in out["real_mint_class"]:
        print(f"{r['payload_chars']:>5} {r['kind']:>6} {r['file_len']:>5} | "
              f"{r['mle_min_reads']:>5}/{r['mle_measured_reads']:<6} "
              f"{'YES' if r['mle_budget_wall_hit'] else 'no':>4} | "
              f"{r['legacy_min_reads']:>7} "
              f"{'YES' if r['legacy_budget_wall_hit'] else 'no':>4} | "
              f"+{r['reads_over_budget']:<3} {'YES' if r['carries_in_budget'] else 'NO'}")
    print(f"-> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
