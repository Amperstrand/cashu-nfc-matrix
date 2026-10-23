"""matrixctl next — THE HUMAN DIRECTIVE (plan §3/§4).

Ranking = (unlocked value x staleness) / human effort, computed over the
GAP between current bench state and each better state. Output is written
for the OWNER: one physical action + one sentence of why — never a menu.

Staleness comes from results/*.jsonl (last time each cell's evidence was
produced) vs the registry's max_age_d. Dev: fixture-driven like the rest.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

from . import registry as reg

REPO = reg.REPO
RESULTS = REPO / "results"

# cell-name -> (jsonl reader substring, wallet) for evidence lookup
EVIDENCE_KEYS = {
    "cashu_me-nucula-payment": ("nucula", "cashu_me"),
    "soak-nucula": ("nucula", "cashu_me"),
    "cashu_me-m5stick-payment": ("m5stick", "cashu_me"),
    "soak-m5stick": ("m5stick", "cashu_me"),
}

# what one physical action costs the human (minutes of owner time)
ACTION_EFFORT = {
    "none": 0.0,
    "move-phone": 2.0,
    "reflash-c3": 15.0,
}


def last_evidence_age_d(cell: str) -> float | None:
    key = EVIDENCE_KEYS.get(cell)
    if not key:
        return None
    reader_sub, wallet = key
    newest = 0.0
    for f in RESULTS.glob("payment-soak-*.jsonl"):
        m = re.match(r"payment-soak-(\d{8}-\d{6})\.jsonl", f.name)
        if not m:
            continue
        ts = time.mktime(time.strptime(m.group(1), "%Y%m%d-%H%M%S"))
        for line in f.read_text().splitlines():
            if reader_sub in line and f'"wallet": "{wallet}"' in line:
                newest = max(newest, ts)
    if not newest:
        return None  # never run: infinitely stale
    return (time.time() - newest) / 86400.0


def _staleness_factor(cell: str, max_age_d) -> float:
    if max_age_d is None:
        return 0.5  # opportunistic: mildly preferred when free
    age = last_evidence_age_d(cell)
    if age is None:
        return 3.0  # never proven: top staleness
    return max(0.1, age / float(max_age_d))


def compute_next(fake: str | None = None) -> dict:
    """Return {action, why, unlocked: [cells], rank} — the single directive."""
    cells = reg.load_registry()
    state_now = reg.current_state(fake)
    at = state_now["phone"].get("at")
    c3 = state_now["boards"].get("c3")

    # candidate future states = the physical actions available
    futures = {}
    if at != "nucula-coil" or c3 != "ccid":
        pass  # computed below regardless
    futures["move-phone->m5stick-coil"] = {"phone": {"at": "m5stick-coil"}}
    futures["move-phone->nucula-coil"] = {"phone": {"at": "nucula-coil"}}
    futures["move-phone->acr-stack"] = {"phone": {"at": "acr-stack"}}
    if c3 != "ccid":
        futures["reflash-c3->ccid"] = {"boards": {"c3": "ccid"},
                                       "phone": {"at": at}}
    # no-touch: current state
    futures["none"] = {}

    ranked = []
    for action, override in futures.items():
        st = {"phone": {**state_now["phone"], **override.get("phone", {})},
              "boards": {**state_now["boards"], **override.get("boards", {})},
              "pcscd": state_now.get("pcscd", {})}
        unlocked, value = [], 0.0
        for name, c in cells.items():
            ok, _ = reg._requires_met(c.get("requires", {}), st)
            if not ok:
                continue
            ok_now, _ = reg._requires_met(c.get("requires", {}), state_now)
            if ok_now:
                continue  # already runnable — not "unlocked" by this action
            w = reg.TIER_WEIGHT[c["tier"]]
            s = _staleness_factor(name, c.get("max_age_d"))
            value += w * s
            unlocked.append(name)
        if not unlocked:
            continue
        effort = ACTION_EFFORT.get(
            "none" if action == "none" else
            "reflash-c3" if action.startswith("reflash") else "move-phone", 1.0)
        ranked.append({"action": action, "unlocked": unlocked,
                       "value": round(value, 2), "effort": effort,
                       "rank": round(value / (1.0 + effort), 2)})
    ranked.sort(key=lambda r: -r["rank"])
    if not ranked:
        return {"action": "none",
                "why": "everything provable is proven within budget; wait for "
                       "staleness to accrue or a board/wallet change",
                "unlocked": [], "rank": 0.0}
    best = ranked[0]
    mins = sum(cells[u]["cost"]["wall_min"] for u in best["unlocked"]
               if u in cells)
    best["why"] = (f"unlocks {len(best['unlocked'])} cells "
                   f"(~{mins} min bench time) — ranked {best['rank']} "
                   f"(value {best['value']} / effort {best['effort']})")
    return best


def cmd_next(args: argparse.Namespace) -> int:
    d = compute_next(args.fake)
    print(f"ACTION: {d['action']}")
    print(f"WHY:    {d['why']}")
    for u in d.get("unlocked", []):
        print(f"  -> {u}")
    return 0


def extend(sub) -> None:
    sp = sub.add_parser("next", help="the one best next physical action")
    sp.add_argument("--fake")
    sp.set_defaults(fn=cmd_next)
