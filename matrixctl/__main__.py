"""matrixctl — bench-state model + survey (step 1 of the automation plan).

`matrixctl survey` probes the bench (adb / pcscd / labgrid / board FWID),
writes bench-state.yaml, and prints DELTAS vs the previous survey. Probes
are individually fake-able for development: `--fake <fixture.json>` runs
the whole survey against a fixture (bench contended; no hardware in dev).

State model (bench-state.yaml):

  timestamp: <iso>
  phone: {serial, adb_state, wifi_ip}
  pcscd: {readers: [...]}
  labgrid: {places_held: {place: holder}}
  boards: {nucula_c3: {fwid, fwid_source}}
  survey_mode: live|fake:<fixture>

The state file is generated; surveys are committed as history under
state/ so `next`/`plan` (later steps) can rank by staleness.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
STATE_PATH = REPO / "bench-state.yaml"
STATE_HISTORY = REPO / "state" / "surveys"

PHONE_SERIAL_DEFAULT = "RF8NB01ZYAH"


def _run(cmd: list[str], timeout: int = 10) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


# ---------------------------------------------------------------- probes


def probe_phone(serial: str) -> dict:
    r = _run(["adb", "-s", serial, "get-state"])
    adb_state = r.stdout.strip() if r.returncode == 0 else "absent"
    wifi_ip = None
    if adb_state == "device":
        ip = _run(["adb", "-s", serial, "shell",
                   "ip", "-4", "addr", "show", "wlan0"])
        for part in ip.stdout.split():
            if part.startswith("192.168.") and "/" in part:
                wifi_ip = part.split("/")[0]
                break
    return {"serial": serial, "adb_state": adb_state, "wifi_ip": wifi_ip}


def probe_pcscd() -> dict:
    try:
        from smartcard.System import readers
    except Exception:
        return {"readers": [], "error": "pyscard unavailable"}
    try:
        return {"readers": sorted(str(r) for r in readers())}
    except Exception as e:
        return {"readers": [], "error": str(e)[:80]}


def probe_labgrid() -> dict:
    r = _run(["labgrid-client", "who"], timeout=15)
    held: dict[str, str] = {}
    for line in r.stdout.splitlines()[1:]:
        cols = line.split()
        if len(cols) >= 3:
            held[cols[2]] = f"{cols[0]}@{cols[1]}"
    return {"places_held": held}


def probe_boards() -> dict:
    """c3 firmware identity: last boot banner in the broker journal
    (bolty vs ccid images identify themselves there). No port access."""
    fwid, source = "unknown", "none"
    r = _run(["journalctl", "-u", "nucula-ccid-broker", "-n", "200",
              "--no-pager"], timeout=15)
    for line in r.stdout.splitlines():
        low = line.lower()
        if "bolty" in low:
            fwid, source = "bolty", "broker-journal"
        elif "ccid" in low and "esp32-ccid" in low:
            fwid, source = "esp32-ccid", "broker-journal"
    return {"nucula_c3": {"fwid": fwid, "fwid_source": source}}


# ---------------------------------------------------------------- survey


def survey(fake: str | None, serial: str) -> dict:
    if fake:
        fx = json.loads(Path(fake).read_text())
        state = dict(fx)
        state["survey_mode"] = f"fake:{Path(fake).name}"
        state["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        return state
    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "phone": probe_phone(serial),
        "pcscd": probe_pcscd(),
        "labgrid": probe_labgrid(),
        "boards": probe_boards(),
        "survey_mode": "live",
    }


def _delta(prev: dict, cur: dict, path: str = "") -> list[str]:
    out: list[str] = []
    for k in sorted(set(prev) | set(cur), key=str):
        p, c = prev.get(k, "<absent>"), cur.get(k, "<absent>")
        if isinstance(p, dict) and isinstance(c, dict):
            out += _delta(p, c, f"{path}{k}.")
        elif p != c:
            out.append(f"~ {path}{k}: {p!r} -> {c!r}")
    return out


def cmd_survey(args: argparse.Namespace) -> int:
    state = survey(args.fake, args.serial)
    prev = {}
    if STATE_PATH.exists():
        try:
            prev = yaml.safe_load(STATE_PATH.read_text()) or {}
        except yaml.YAMLError:
            prev = {}
    STATE_PATH.write_text(yaml.safe_dump(state, sort_keys=True))
    STATE_HISTORY.mkdir(parents=True, exist_ok=True)
    (STATE_HISTORY / f"survey-{time.strftime('%Y%m%d-%H%M%S')}.yaml").write_text(
        yaml.safe_dump(state, sort_keys=True))
    print(yaml.safe_dump(state, sort_keys=True))
    d = _delta(prev.get("phone", {}), state.get("phone", {}), "phone.")
    d += _delta(prev.get("boards", {}), state.get("boards", {}), "boards.")
    d += [f"~ pcscd.readers: {len(prev.get('pcscd', {}).get('readers', []))}"
          f" -> {len(state.get('pcscd', {}).get('readers', []))}"]
    old_held = prev.get("labgrid", {}).get("places_held", {})
    new_held = state.get("labgrid", {}).get("places_held", {})
    d += [f"~ labgrid.{p}: {'held' if p in new_held else 'released'}"
          for p in sorted(set(old_held) | set(new_held))
          if (p in old_held) != (p in new_held)]
    print("--- deltas vs previous survey ---")
    print("\n".join(d) if d else "(none)")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="matrixctl")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("survey", help="probe bench, write state, print deltas")
    sp.add_argument("--fake", help="fixture json (dev: no hardware)")
    sp.add_argument("--serial", default=PHONE_SERIAL_DEFAULT)
    sp.set_defaults(fn=cmd_survey)
    from .registry import extend_parser  # noqa: E402
    extend_parser(sub)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
