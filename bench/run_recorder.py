#!/usr/bin/env python3
"""Run recorder — turns a suite run into a test-films footage directory.

Emits the layout downstream film tooling reads (Amperstrand/test-films:
"the run directory IS the footage store"):

  <run-dir>/
    timeline.jsonl      unified events (phone screens, NFC APDUs, mint,
                        field transitions, firmware) on one wall clock
    wire-broker.log     nucula-ccid-broker journal slice (CCID + console)
    phone-logcat.log    adb logcat slice (cdk, NfcService)
    stills/*.png        phone screenshots (kept only when non-black —
                        FLAG_SECURE surfaces render black and are pruned)
    mint/               token files (name only, amounts) + keyset snapshot
    film.md             self-describing run summary

Usage: suites get the session-scoped `rec` fixture (conftest). Terminal
states auto-still; failures always captured, passes opt-in via FILM=1.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from pathlib import Path

BLACK_PNG_MAX = 20000  # FLAG_SECURE screencaps land well under this


class RunRecorder:
    def __init__(self, root: Path):
        self.root = Path(root)
        (self.root / "stills").mkdir(parents=True, exist_ok=True)
        (self.root / "mint").mkdir(exist_ok=True)
        self.t0 = time.time()
        self._followers: list[tuple[str, subprocess.Popen]] = []
        self.event("run", "start")

    # ---- timeline ----
    def event(self, kind: str, text: str, **data) -> None:
        rec = {"t": round(time.time() - self.t0, 2),
               "wall": time.strftime("%H:%M:%S.%f")[:-3],
               "kind": kind, "text": text}
        rec.update(data)
        with open(self.root / "timeline.jsonl", "a") as fh:
            fh.write(json.dumps(rec) + "\n")

    # ---- followers ----
    def follow(self, name: str, cmd: list[str]) -> None:
        out = open(self.root / name, "ab", buffering=0)
        proc = subprocess.Popen(cmd, stdout=out, stderr=subprocess.DEVNULL)
        self._followers.append((name, proc))
        self.event("follower", f"started {name}")

    def start_default_followers(self, serial: str = "RF8NB01ZYAH") -> None:
        self.follow("wire-broker.log",
                    ["journalctl", "-u", "nucula-ccid-broker", "-f", "-n", "0",
                     "-o", "short-iso"])
        self.follow("phone-logcat.log",
                    ["adb", "-s", serial, "logcat", "-v", "time",
                     "cdk:*", "NfcService:*", "HostApduService:*", "*:S"])

    def stop_followers(self) -> None:
        for _, proc in self._followers:
            proc.terminate()
        for _, proc in self._followers:
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
        self._followers.clear()

    # ---- stills ----
    def still(self, name: str, serial: str = "RF8NB01ZYAH") -> Path | None:
        path = self.root / "stills" / f"{time.strftime('%H%M%S')}-{name}.png"
        try:
            raw = subprocess.run(
                ["adb", "-s", serial, "exec-out", "screencap", "-p"],
                capture_output=True, timeout=20,
            ).stdout
            if len(raw) < BLACK_PNG_MAX:  # black/FLAG_SECURE — skip
                self.event("still", f"{name}: pruned (black/secure, {len(raw)}B)")
                return None
            path.write_bytes(raw)
            self.event("still", f"{name}: {len(raw)}B -> {path.name}")
            return path
        except Exception as e:
            self.event("still", f"{name}: failed {type(e).__name__}")
            return None

    # ---- mint evidence ----
    def mint_evidence(self, token_path: str, amount: int) -> None:
        try:
            tok = Path(token_path).read_text().strip()
            (self.root / "mint" / f"token-{amount}sats.len").write_text(
                f"{len(tok)} chars, prefix={tok[:6]}…")
            self.event("mint", f"{amount} sats token, {len(tok)} chars")
        except Exception as e:
            self.event("mint", f"evidence failed: {e}")

    # ---- finish ----
    def finish(self, summary: str) -> None:
        self.stop_followers()
        self.event("run", "finish", summary=summary)
        events = [json.loads(l) for l in
                  open(self.root / "timeline.jsonl").read().splitlines()]
        (self.root / "film.md").write_text(
            f"# run film — {self.root.name}\n\n{summary}\n\n"
            f"## timeline ({len(events)} events)\n\n"
            "| t | wall | kind | what |\n|---|---|---|---|\n"
            + "\n".join(f"| {e['t']} | {e['wall']} | {e['kind']} | {e['text']} |"
                        for e in events)
            + "\n\nfootage: wire-broker.log, phone-logcat.log, stills/, mint/\n")
