#!/usr/bin/env python3
"""Read-direction tap soak: N x (arm request on cashu.me -> ACR1252 Type-4 read
-> verify NUT-18 fields), timings + interference logged to JSONL.

Coexists with the bc-taploop lane (reads same phone every 30s): transient
reader-unavailable / no-card get retried with backoff, interference is logged
not hidden. Every cycle re-arms a FRESH amount so each NDEF is unique.

--virtual (SESSION C substitution mode): the phone-side NDEF peer is
replaced by the vpicc model — a fresh ModelVpicc per cycle carries a
fresh-amount creqA (built like suites/test_probe_vpicc.py), served on
the pcscd vpcd slot and read by the same probe_acr Type-4 ladder. Zero
silicon, zero phone, zero labgrid places; JSONL rows are tagged
mode=virtual. See bench/vpicc/README.md for what this mode does and
does not prove.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bench.error_class import classify_error  # noqa: E402
from bench.probe_acr import read_ndef_request  # noqa: E402
from drivers import ui  # noqa: E402
from drivers.cashu_me import CashuMeDriver  # noqa: E402

VPICC_PORT = 35970  # table-card vpcd slot (the pcscd driver's port — never bind-test)
VPICC_ATR = bytes.fromhex("3B8180018080")  # golden capture ATR (probe-smoke pinned)
VPICC_READER = "vPICC table card"


def virtual_slot_present() -> bool:
    """vPICC slot guard — same predicate as suites/test_probe_vpicc.py."""
    try:
        from smartcard.System import readers

        names = [str(r) for r in readers()]
    except Exception:  # noqa: BLE001 — no pcscd at all
        return False
    return any(VPICC_READER in n and "00 00" in n for n in names)


def build_creq_text(amount: int) -> str:
    """Fresh creqA per cycle — the test_probe_vpicc builder extended with
    the rotating amount (payment_soak arming pattern) so the parse+verify
    path (decode_creq -> a/u fields) is exercised for real each cycle."""
    import cbor2

    payload = cbor2.dumps({"k": "00", "a": amount, "u": "sat"})
    return "creqA" + base64.urlsafe_b64encode(payload).decode().rstrip("=")


def build_cashub_text(cycle: int, amount: int, target_len: int = 374) -> str:
    """Fresh cashuB-class token per cycle (SESSION J). Structurally faithful
    to observed CDK v4 tokens ({"t":[{"i":..,"d":[{"p":..,"s":..}]}],"u":..,
    "m":..}, base64url of the JSON after the 'cashuB' prefix) with per-cycle
    unique secrets + memo nonce, padded via the memo to exactly target_len
    (374 = the charter's long-form class; >255 payload chars is what forces
    the 4-byte NDEF length form). Read-side decode+field-verify is the
    exercised path (same standard as creqA: parse real, no mint crypto)."""
    import base64 as b64
    import json

    def _b64(blob: bytes) -> str:
        return b64.urlsafe_b64encode(blob).decode().rstrip("=")

    p = _b64(bytes([0x02]) + cycle.to_bytes(4, "big") + b"\x01")     # fresh proof
    s = _b64(b"s23j" + cycle.to_bytes(4, "big") + b"\x02")          # fresh secret
    memo = f"vpicc-soak c={cycle} a={amount}sat"

    def _enc(m: str) -> str:
        tok = {"t": [{"i": "00112233", "d": [{"p": p, "s": s}]}],
               "u": "sat", "m": m}
        return "cashuB" + _b64(json.dumps(tok, separators=(",", ":")).encode())

    # b64 expansion maps ~3 JSON bytes to 4 token chars — solve for the
    # memo length whose stripped-b64 encoding lands EXACTLY on target_len
    # (each ASCII memo char is exactly one JSON byte, so the map is affine).
    bare = len(_enc("").encode())
    n_target = next(n for n in range(bare, bare + 4096)
                    if len(_enc("y" * (n - bare))) == target_len)
    enc = _enc(memo + "x" * (n_target - bare - len(memo)))
    assert len(enc) == target_len, (len(enc), target_len)
    return enc


# Bytes that pass the model's plain-read file serving but FAIL NDEF parsing
# (no MB/ME flags) — the bad-read injection for error_class verification.
BAD_NDEF_MESSAGE = b"\x00\x00\x00garbage-not-a-record"


def soak_virtual(cycles: int, base_amount: int, out_path: str,
                 inject_bad_at: int | None = None,
                 ndef_kind: str = "creqA") -> int:
    """Substitution-mode soak: fresh virtual card content per cycle, read
    through the full pcscd -> vpcd -> model -> probe_acr ladder.

    A FRESH ModelVpicc per cycle models a re-tap: the capture-pinned
    READ_BUDGET (3 successful content reads per card session) is per
    answerer state. Do not raise the budget without a golden re-pin
    (bench/vpicc/LOCK).

    ndef_kind:
      - "creqA": the SESSION C mode — short record, LEGACY 0x20-window
        ladder (exactly 3 reads at these sizes; physical-lane shape).
      - "cashuB": the SESSION J long-form mode — 374-char token, read
        with the MLe single-window ladder (read_ndef_request_mle;
        1 CC + 2 x Le254 = exactly 3 reads). Fresh token per cycle.
    """
    from bench.ndef import text_type4_file
    from bench.vpicc.vpicc_golden import GoldenVpicc
    from bench.vpicc.vpicc_model import ModelVpicc

    if ndef_kind not in ("creqA", "cashuB"):
        raise ValueError(f"ndef_kind must be creqA|cashuB, got {ndef_kind!r}")
    if ndef_kind == "cashuB":
        from bench.probe_acr import read_ndef_request_mle as read_fn
    else:
        from bench.probe_acr import read_ndef_request as read_fn

    if not virtual_slot_present():
        print(f"SKIP: {VPICC_READER!r} slot not present (bench-host setup) — "
              "substitution mode unavailable, nothing attempted", flush=True)
        return 0

    def _arm_text(cycle: int, amount: int) -> str:
        return (build_creq_text(amount) if ndef_kind == "creqA"
                else build_cashub_text(cycle, amount))

    def _verify(res: dict, cycle: int, amount: int) -> bool:
        if ndef_kind == "creqA":
            creq = res.get("creq") or {}
            return creq.get("a") == amount and creq.get("u") == "sat"
        tok = res.get("cashu") or {}
        memo = tok.get("m", "")
        return (tok.get("u") == "sat"
                and f"c={cycle}" in memo and f"a={amount}sat" in memo)

    ok = fail = 0
    card = None
    try:
        with open(out_path, "a") as fh:
            for i in range(cycles):
                amount = base_amount + i
                rec: dict = {"cycle": i, "amount": amount, "mode": "virtual",
                             "ndef_kind": ndef_kind,
                             "ts": time.strftime("%H:%M:%S")}
                t0 = time.monotonic()
                # --- arm phase: build fresh NDEF, install on a FRESH model ---
                try:
                    if inject_bad_at == i:
                        raw_message = BAD_NDEF_MESSAGE  # deliberate parse failure
                        rec["injected"] = "bad_ndef"
                    else:
                        ndef_file = text_type4_file(_arm_text(i, amount))
                        raw_message = ndef_file[2:]  # model takes raw message
                    answerer = ModelVpicc(ndef_file=raw_message)
                    if card is None:
                        card = GoldenVpicc("127.0.0.1", VPICC_PORT, VPICC_ATR,
                                           answerer=answerer)
                        card.start()
                        deadline = time.time() + 60
                        while not card.answered_probe.is_set() and time.time() < deadline:
                            time.sleep(0.5)
                        if not card.answered_probe.is_set():
                            # port busy / slot wedged: skip gracefully, never
                            # disturb the pcscd domain (PR #13 lesson)
                            rec["arm_error"] = "vpcd slot never probed our card (port busy?)"
                            rec["arm_error_class"] = classify_error("other")
                            fail += 1
                            fh.write(json.dumps(rec) + "\n"); fh.flush()
                            print(json.dumps(rec), flush=True)
                            break
                    else:
                        card.answerer = answerer  # fresh card content per tap
                except Exception as e:  # noqa: BLE001
                    rec["arm_error"] = repr(e)[:200]
                    rec["arm_error_class"] = classify_error(e)
                if "arm_error" in rec:
                    fail += 1
                    fh.write(json.dumps(rec) + "\n"); fh.flush()
                    print(json.dumps(rec), flush=True)
                    continue
                rec["arm_s"] = round(time.monotonic() - t0, 2)
                # --- read phase (light retry; no RF interference on vpcd) ---
                res = None
                for attempt in range(2):
                    try:
                        res = read_fn(VPICC_READER)
                        if not _verify(res, i, amount) and attempt < 1:
                            raise RuntimeError(
                                f"token not parsed/verified: "
                                f"{res.get('parse_error', res.get('select_ndef_sw'))}")
                        break
                    except Exception as e:  # noqa: BLE001
                        rec[f"read_retry_{attempt}"] = repr(e)[:120]
                        time.sleep(1 + attempt)
                t_read = round(time.monotonic() - t0, 2)
                if res and _verify(res, i, amount):
                    reads = res.get("reads") or {
                        "cc": 1,
                        "ndef_windows": max(1, -(-res["ndef_len"] // 32)),  # legacy 0x20
                        "total": 1 + max(1, -(-res["ndef_len"] // 32)),
                    }
                    rec.update({
                        "ok": True,
                        "token_len": len(res.get("ndef_text", "")),
                        "ndef_len": res["ndef_len"],
                        "ladder": res.get("ladder", "legacy-0x20"),
                        "reads": reads,
                        "connect_s": res.get("connect_s"),
                        "read_s": res.get("read_s"),
                        "cycle_total_s": t_read,
                        "atr": res["atr"],
                    })
                    if ndef_kind == "creqA":
                        rec["creq"] = res["creq"]
                    else:
                        rec["cashu_memo"] = res["cashu"].get("m", "")[:44]
                    ok += 1
                else:
                    rec["ok"] = False
                    last_err = (res or {}).get("parse_error") or "read failed"
                    last_retry = rec.get("read_retry_0")
                    rec["read_error"] = last_err
                    rec["read_error_class"] = classify_error(
                        last_retry if last_retry is not None else last_err)
                    fail += 1
                fh.write(json.dumps(rec) + "\n"); fh.flush()
                print(json.dumps({k: rec.get(k) for k in ("cycle", "amount", "mode", "ndef_kind", "ok", "ladder", "reads", "token_len", "arm_s", "connect_s", "read_s", "cycle_total_s", "read_error", "read_error_class")}), flush=True)
                time.sleep(1.0)
    finally:
        if card is not None:
            card.stop()
    print(f"=== virtual soak done: {ok} ok / {fail} fail / {cycles} cycles -> {out_path}")
    return 0 if fail == 0 else 1


def soak(cycles: int, base_amount: int, out_path: str) -> int:
    d = CashuMeDriver()
    ok = fail = 0
    with open(out_path, "a") as fh:
        for i in range(cycles):
            amount = base_amount + i
            rec: dict = {"cycle": i, "amount": amount, "ts": time.strftime("%H:%M:%S")}
            st = ""
            t0 = time.monotonic()
            # --- arm phase (retry once with full self-heal) ---
            try:
                d.wake()
                st = d.create_request(amount)
                if not d.is_armed():
                    raise RuntimeError(f"not armed after create_request: {st!r}")
            except Exception as e:
                rec["arm_retry_0"] = repr(e)[:120]
                try:
                    ui.adb(d.serial, "shell", "am", "force-stop", d.package)
                    time.sleep(1.0)
                    d.launch()
                    st = d.create_request(amount)
                    if not d.is_armed():
                        raise RuntimeError(f"not armed after retry: {st!r}")
                except Exception as e2:
                    rec["arm_error"] = repr(e2)[:200]
                    # Arm failures are phone-side (adb/UI/app) by
                    # construction — but classify anyway so the JSONL
                    # schema is uniform across failure sites.
                    rec["arm_error_class"] = classify_error(e2)
            if "arm_error" not in rec:
                rec["arm_s"] = round(time.monotonic() - t0, 2)
                rec["nfc_status"] = st if isinstance(st, str) else ""
            else:
                fail += 1
                fh.write(json.dumps(rec) + "\n"); fh.flush()
                print(json.dumps(rec), flush=True)
                continue
            # --- read phase (retry transient interference) ---
            res = None
            for attempt in range(4):
                try:
                    res = read_ndef_request("ACR1252")
                    if res.get("creq") is None and attempt < 3:
                        raise RuntimeError(f"no creq parsed: {res.get('parse_error', res.get('select_ndef_sw'))}")
                    break
                except Exception as e:
                    rec[f"read_retry_{attempt}"] = repr(e)[:120]
                    time.sleep(2 + attempt * 3)
            t_read = round(time.monotonic() - t0, 2)
            if res and res.get("creq"):
                creq = res["creq"]
                good = creq.get("a") == amount and creq.get("u") == "sat"
                rec.update({
                    "ok": good,
                    "creq": creq,
                    "ndef_len": res["ndef_len"],
                    "connect_s": res.get("connect_s"),
                    "read_s": res.get("read_s"),
                    "cycle_total_s": t_read,
                    "atr": res["atr"],
                })
                ok += 1 if good else 0
                fail += 0 if good else 1
            else:
                rec["ok"] = False
                last_err = (res or {}).get("parse_error") or "read failed"
                # Retry loop may have logged the underlying exception in
                # read_retry_<n> — classify the LAST one seen so the
                # owner split (rpc/t1/tool) exists for reads too.
                last_retry = None
                for attempt in range(4):
                    k = f"read_retry_{attempt}"
                    if k in rec:
                        last_retry = rec[k]
                rec["read_error"] = last_err
                rec["read_error_class"] = classify_error(
                    last_retry if last_retry is not None else last_err)
                fail += 1
            fh.write(json.dumps(rec) + "\n"); fh.flush()
            print(json.dumps({k: rec.get(k) for k in ("cycle", "amount", "ok", "arm_s", "connect_s", "read_s", "cycle_total_s", "read_error", "read_retry_0")}), flush=True)
            time.sleep(1.0)
    print(f"=== soak done: {ok} ok / {fail} fail / {cycles} cycles -> {out_path}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--cycles", type=int, default=10)
    ap.add_argument("--base-amount", type=int, default=30)
    ap.add_argument("--out", default=None)
    ap.add_argument("--virtual", action="store_true",
                    help="substitution mode: vpicc model on the vpcd slot "
                         "instead of the phone (zero silicon — see "
                         "bench/vpicc/README.md)")
    ap.add_argument("--inject-bad-read", type=int, default=None, metavar="CYCLE",
                    help="(--virtual) serve unparseable NDEF at CYCLE to "
                         "verify error_class classification in virtual mode")
    ap.add_argument("--ndef-kind", choices=("creqA", "cashuB"), default="creqA",
                    help="(--virtual) token class: creqA = short record + "
                         "legacy 0x20 ladder (SESSION C); cashuB = 374-char "
                         "long-form + MLe single-window ladder (SESSION J)")
    args = ap.parse_args()
    stem = "virtual-soak" if args.virtual else "soak"
    if args.virtual and args.ndef_kind == "cashuB":
        stem = "virtual-soak-cashub"
    out = args.out or os.path.join(os.path.dirname(__file__), "..", "results",
                                   f"{stem}-{time.strftime('%Y%m%d-%H%M%S')}.jsonl")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    if args.virtual:
        sys.exit(soak_virtual(args.cycles, args.base_amount, out,
                              inject_bad_at=args.inject_bad_read,
                              ndef_kind=args.ndef_kind))
    sys.exit(soak(args.cycles, args.base_amount, out))
