"""matrixctl registry + plan/run/set/verify-state (plan §2/§4).

Extends __main__.survey with the full surface:
  set <fact> <value>     record a human physical action (bench-facts.yaml)
  plan [--tier ...]      runnable set NOW + wall-time estimate
  run <plan-file|->      execute plan cells (pytest/soak), results appended
  verify-state           assert assumed geometry still holds (mid-run)

Dev discipline: everything is fixture-testable; `run` requires --yes to
touch hardware, --dry-run prints the commands only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import yaml

from .__main__ import REPO, STATE_PATH, _run, cmd_survey, survey

FACTS_PATH = REPO / "bench-facts.yaml"
REGISTRY_PATH = Path(__file__).parent / "registry.yaml"

PHONE_AT_VALID = ("nucula-coil", "acr-stack", "m5stick-coil", "off-bench",
                  "any-reader-coil")
C3_DUTY_VALID = ("ccid", "bolty")

TIER_WEIGHT = {"core": 3.0, "extended": 1.5, "opportunistic": 0.7}


def load_facts() -> dict:
    if FACTS_PATH.exists():
        return yaml.safe_load(FACTS_PATH.read_text()) or {}
    return {}


def load_registry() -> dict:
    return yaml.safe_load(REGISTRY_PATH.read_text())["cells"]


# ---------------------------------------------------------------- set


def cmd_set(args: argparse.Namespace) -> int:
    facts = load_facts()
    fact, value = args.fact, args.value
    if fact == "phone.at":
        if value not in PHONE_AT_VALID:
            print(f"phone.at must be one of {PHONE_AT_VALID}")
            return 2
        facts.setdefault("phone", {})["at"] = value
    elif fact == "c3.duty":
        if value not in C3_DUTY_VALID:
            print(f"c3.duty must be one of {C3_DUTY_VALID}")
            return 2
        facts.setdefault("boards", {})["c3"] = value
    elif fact.startswith("card."):
        facts.setdefault("cards", {})[fact[5:]] = value
    elif fact == "network.bench-ap-egress":
        facts.setdefault("network", {})["bench_ap_egress"] = value
    else:
        print(f"unknown fact {fact!r} (phone.at | c3.duty | network.bench-ap-egress)")
        return 2
    FACTS_PATH.write_text(yaml.safe_dump(facts, sort_keys=True))
    print(f"set {fact} = {value} (bench-facts.yaml)")
    return 0


# ---------------------------------------------------------------- plan


def current_state(fake: str | None = None) -> dict:
    """survey (probeable) merged with human facts (physical truth §1)."""
    st = survey(fake, "RF8NB01ZYAH") if fake else survey(None, "RF8NB01ZYAH")
    facts = load_facts()
    st.setdefault("phone", {}).setdefault("at", facts.get("phone", {}).get("at", "off-bench"))
    st["boards"] = st.get("boards") or {}
    st["boards"].setdefault("c3", facts.get("boards", {}).get("c3", "unknown"))
    st.setdefault("network", {}).setdefault(
        "bench_ap_egress", facts.get("network", {}).get("bench_ap_egress", "unknown"))
    return st


def _requires_met(req: dict, state: dict) -> tuple[bool, str]:
    want_phone = req.get("phone_at")
    if want_phone and want_phone != "any-reader-coil":
        at = state["phone"].get("at")
        if at != want_phone:
            return False, f"phone at {at!r}, need {want_phone!r}"
    want_c3 = req.get("c3")
    if want_c3 and state["boards"].get("c3") != want_c3:
        return False, f"c3 duty {state['boards'].get('c3')!r}, need {want_c3!r}"
    # reader presence in pcscd (the m5stick serial can be held by another
    # lane's console daemon -> reader absent regardless of phone position)
    want_reader = req.get("pcscd_reader")
    if want_reader:
        readers = " ".join(state.get("pcscd", {}).get("readers", []))
        if want_reader not in readers:
            return False, f"reader {want_reader!r} not in pcscd (serial held?)"
    return True, ""


def plan(fake: str | None = None, tier: str = "all") -> dict:
    state = current_state(fake)
    cells = load_registry()
    runnable, blocked = [], []
    for name, c in cells.items():
        if tier != "all" and c["tier"] != tier:
            continue
        ok, why = _requires_met(c.get("requires", {}), state)
        entry = {"cell": name, "tier": c["tier"], "wall_min": c["cost"]["wall_min"],
                 "suite": c["suite"]}
        (runnable if ok else blocked).append(
            entry if ok else {**entry, "blocked": why})
    return {"state_mode": state.get("survey_mode", "live"),
            "phone_at": state["phone"].get("at"),
            "c3": state["boards"].get("c3"),
            "runnable": runnable, "blocked": blocked,
            "wall_min_total": sum(r["wall_min"] for r in runnable)}


def cmd_plan(args: argparse.Namespace) -> int:
    p = plan(args.fake, args.tier)
    print(f"phone_at={p['phone_at']} c3={p['c3']} tier={args.tier}")
    print(f"runnable NOW ({p['wall_min_total']} min est):")
    for r in p["runnable"]:
        print(f"  [+] {r['cell']} ({r['tier']}, {r['wall_min']}m)")
    for b in p["blocked"]:
        print(f"  [-] {b['cell']}: {b['blocked']}")
    if args.out:
        Path(args.out).write_text(json.dumps(p, indent=1))
        print(f"plan written: {args.out}")
    return 0


# ---------------------------------------------------------------- run


def cmd_run(args: argparse.Namespace) -> int:
    plan_file = Path(args.plan)
    p = json.loads(plan_file.read_text())
    for cell in p["runnable"]:
        suite = cell["suite"]
        print(f"=== {cell['cell']}: {suite}")
        if args.dry_run:
            continue
        if not args.yes:
            print("refusing to touch hardware without --yes (dev: --dry-run)")
            return 2
        if suite.startswith("SOAK_"):
            env_var, _, rest = suite.partition(" ")
            cmd = ["/usr/bin/python3", rest]  # env applied below
            r = _run(cmd, timeout=3600)
        else:
            r = _run(["/usr/bin/python3", "-m", "pytest", suite,
                      "--hil", "--timeout=900", "--timeout-method=signal",
                      "-m", "payer"], timeout=3600)
        print(r.stdout[-2000:] if r.stdout else f"rc={r.returncode}")
    return 0


# ---------------------------------------------------------------- verify


def cmd_verify(args: argparse.Namespace) -> int:
    want = json.loads(Path(args.assume).read_text()) if args.assume else {}
    state = current_state(args.fake)
    bad = []
    for fact, need in want.items():
        have = (state["phone"].get("at") if fact == "phone.at"
                else state["boards"].get("c3") if fact == "c3.duty" else None)
        if have != need:
            bad.append(f"{fact}: assumed {need!r}, bench says {have!r}")
    print("\n".join(bad) if bad else "state holds: all assumed facts verified")
    return 1 if bad else 0


def extend_parser(sub: argparse._SubParsersAction) -> None:
    sp = sub.add_parser("set", help="record a human physical action")
    sp.add_argument("fact")
    sp.add_argument("value")
    sp.set_defaults(fn=cmd_set)
    sp = sub.add_parser("plan", help="runnable set NOW + wall-time estimate")
    sp.add_argument("--tier",
                    choices=["core", "extended", "opportunistic", "all"],
                    default="all")
    sp.add_argument("--fake")
    sp.add_argument("--out", help="write plan json for `run`")
    sp.set_defaults(fn=cmd_plan)
    sp = sub.add_parser("run", help="execute a plan (hardware: needs --yes)")
    sp.add_argument("plan")
    sp.add_argument("--yes", action="store_true")
    sp.add_argument("--dry-run", action="store_true")
    sp.set_defaults(fn=cmd_run)
    sp = sub.add_parser("verify-state", help="mid-run geometry assertion")
    sp.add_argument("--assume", help="json of {fact: value} to assert")
    sp.add_argument("--fake")
    sp.set_defaults(fn=cmd_verify)


if __name__ == "__main__":
    from .__main__ import main as _m  # pragma: no cover
    _m()
