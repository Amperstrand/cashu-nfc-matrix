#!/usr/bin/env python3
"""Aggregate soak JSONL/JSON results into a stats summary.

Usage: aggregate_soak.py results/soak-*.jsonl [results/hil-*/t3-soak-*.json]
Prints + writes results/soak-summary.md (never hand-edited).
"""
from __future__ import annotations

import glob
import json
import statistics
import sys
from pathlib import Path


def rows_from_jsonl(p: str) -> list[dict]:
    out = []
    for line in Path(p).read_text().splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def stats(vals: list[float]) -> dict:
    if not vals:
        return {}
    return {
        "n": len(vals),
        "min": round(min(vals), 3),
        "p50": round(statistics.median(vals), 3),
        "mean": round(statistics.fmean(vals), 3),
        "max": round(max(vals), 3),
    }


def main(paths: list[str]) -> int:
    arm, conn, read, total = [], [], [], []
    ok = fail = 0
    interference = 0
    per_file = []
    for p in paths:
        rows = rows_from_jsonl(p) if p.endswith(".jsonl") else [json.loads(Path(p).read_text())]
        n_ok = n_fail = 0
        for r in rows:
            if r.get("cycle") is not None:  # tap_soak.py jsonl
                if r.get("ok"):
                    ok += 1; n_ok += 1
                    arm.append(r.get("arm_s", 0))
                    conn.append(r.get("connect_s", 0))
                    read.append(r.get("read_s", 0))
                    total.append(r.get("cycle_total_s", 0))
                else:
                    fail += 1; n_fail += 1
                interference += sum(1 for k in r if k.startswith("read_retry_") and r[k])
            elif "rows" in r:  # suites t3 json
                ok += r["ok"]; fail += r.get("fail", 0)
                for row in r["rows"]:
                    arm.append(row.get("arm_s", 0))
                    read.append(row.get("read_s", 0))
                n_ok, n_fail = r["ok"], r.get("fail", 0)
        per_file.append((p, n_ok, n_fail))
    lines = [
        "# soak summary (generated — aggregate_soak.py)",
        "",
        f"- cycles: {ok} ok / {fail} fail ({ok + fail} total)",
        f"- read-retry events (interference): {interference}",
        f"- arm_s: {stats(arm)}",
        f"- connect_s: {stats(conn)}",
        f"- ndef_read_s: {stats(read)}",
    ]
    if total:
        lines.append(f"- cycle_total_s: {stats(total)}")
    for p, n_ok, n_fail in per_file:
        lines.append(f"- `{p}`: {n_ok} ok / {n_fail} fail")
    text = "\n".join(lines)
    print(text)
    out = Path("results/soak-summary.md")
    out.parent.mkdir(exist_ok=True)
    prev = out.read_text() if out.exists() else ""
    stamp = f"\n_run {__import__('time').strftime('%Y-%m-%d %H:%M')}_\n"
    out.write_text(text + stamp + ("\n---\n" + prev if prev else ""))
    return 0


if __name__ == "__main__":
    args = sys.argv[1:] or sorted(glob.glob("results/soak-*.jsonl"))
    sys.exit(main(args))
