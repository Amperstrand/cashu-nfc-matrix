#!/usr/bin/env python3
"""ACR1252 field probe: connect + APDU battery under a hard watchdog.

Every transmit is wrapped in SIGALRM(15s) — the shared bench field can swallow
frames (observed: activation answers, first SELECT hangs forever), and a stuck
SCardTransmit otherwise wedges the calling shell for minutes.

READ-ONLY by construction: only SELECT / READ BINARY / GET DATA go out.
"""
from __future__ import annotations

import signal
import sys
import time

from smartcard.System import readers


class TransmitTimeout(Exception):
    pass


def _alarm(signum, frame):
    raise TransmitTimeout("transmit watchdog fired")


def get_acr():
    cands = [x for x in readers() if "ACR1252" in str(x) and "PICC" in str(x)]
    if not cands:
        raise RuntimeError("ACR1252 PICC not present in pcscd")
    return cands[0]


def probe(aids: list[tuple[str, list[int]]], follow_ndef: bool = True) -> int:
    r = get_acr()
    t0 = time.monotonic()
    c = r.createConnection()
    c.connect()
    print(f"[{time.monotonic()-t0:6.2f}s] connect ATR: {' '.join(f'{b:02x}' for b in c.getATR())}")
    proto = c.getProtocol()

    def xchg(name, apdu, rx=256):
        old = signal.signal(signal.SIGALRM, _alarm)
        signal.alarm(15)
        try:
            d, sw1, sw2 = c.transmit(apdu, proto)
            print(f"[{time.monotonic()-t0:6.2f}s] {name}: > {' '.join(f'{b:02x}' for b in apdu)}")
            print(f"[{time.monotonic()-t0:6.2f}s]          < {' '.join(f'{b:02x}' for b in d)} SW={sw1:02x}{sw2:02x}")
            return bytes(d), sw1, sw2
        except TransmitTimeout:
            print(f"[{time.monotonic()-t0:6.2f}s] {name}: TIMEOUT >{' '.join(f'{b:02x}' for b in apdu)}")
            raise
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old)

    hit = None
    for name, aid in aids:
        try:
            d, s1, s2 = xchg(f"SELECT {name}", [0x00, 0xA4, 0x04, 0x00, len(aid)] + aid + [0x00])
        except TransmitTimeout:
            print("field ate the frame; reconnect needed")
            return 3
        if (s1, s2) == (0x90, 0x00):
            hit = name
            print(f"*** AID {name} SELECTED OK ***")
            break
        else:
            print(f"    {name} not selected (SW {s1:02x}{s2:02x})")

    if hit and follow_ndef and hit == "NDEF":
        # Type 4 tag: CC file then NDEF file
        xchg("SELECT CC E103", [0x00, 0xA4, 0x00, 0x0C, 0x02, 0xE1, 0x03])
        d, s1, s2 = xchg("READ CC", [0x00, 0xB0, 0x00, 0x00, 0x0F])
        if (s1, s2) == (0x90, 0x00) and len(d) >= 15:
            # Type 4 CC: CCLEN(2) Ver MLe(2) MLc(2) [TLVs: T=04 L=06 FileID(2) MaxSize(2) RD(1) WR(1)]
            ndef_fid = (d[9] << 8) | d[10]
            ndef_max = (d[11] << 8) | d[12]
            print(f"CC: ver={d[2]:02x} MLe={int.from_bytes(d[3:5],'big')} MLc={int.from_bytes(d[5:7],'big')} "
                  f"ndef_fid={ndef_fid:04x} max_ndef={ndef_max} rd={d[13]:02x} wr={d[14]:02x}")
            xchg("SELECT NDEF file", [0x00, 0xA4, 0x00, 0x0C, 0x02, (ndef_fid >> 8) & 0xFF, ndef_fid & 0xFF])
            file = b""
            off = 0
            total = 0
            while True:
                try:
                    d2, s1b, s2b = xchg(f"READ NDEF @{off}", [0x00, 0xB0, (off >> 8) & 0xFF, off & 0xFF, 0x20])
                except TransmitTimeout:
                    break
                if (s1b, s2b) != (0x90, 0x00) or not d2:
                    break
                if off == 0 and len(d2) >= 2:
                    nlen = (d2[0] << 8) | d2[1]
                    total = nlen + 2
                    print(f"NDEF NLEN={nlen} -> file {total}B")
                file += bytes(d2)
                off += len(d2)
                if len(file) >= (total or 1 << 20):
                    break
            print(f"NDEF file ({len(file)}B): {file.hex()}")
            try:
                import os
                import sys
                sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                from bench.ndef import parse_text_record, decode_creq

                text = parse_text_record(file)
                print(f"NDEF text: {text!r}")
                print(f"creqA decoded: {decode_creq(text)}")
            except Exception as e:
                print(f"NDEF parse failed: {e}")
            # NTAG424-ness: proprietary files a real NTAG424 DNA would serve
            for fid in (0xE105, 0xE110, 0xF000, 0xF001, 0xF002):
                try:
                    _, a1, a2 = xchg(f"SELECT {fid:04x}", [0x00, 0xA4, 0x00, 0x0C, 0x02, (fid >> 8) & 0xFF, fid & 0xFF])
                    if (a1, a2) == (0x90, 0x00):
                        xchg(f"READ {fid:04x} @0", [0x00, 0xB0, 0x00, 0x00, 0x20])
                except TransmitTimeout:
                    break
    return 0


if __name__ == "__main__":
    AID_NDEF = [0xD2, 0x76, 0x00, 0x00, 0x85, 0x01, 0x01]
    AID_BOLTCARD_ASCII = [0xA0, 0x00, 0x00, 0x04] + [ord(ch) for ch in "qnula"]
    AID_NUCULA_ASCII = [0xA0, 0x00, 0x00, 0x04] + [ord(ch) for ch in "nucula"]
    sys.exit(probe([("NDEF", AID_NDEF), ("boltcard-ascii", AID_BOLTCARD_ASCII), ("nucula-ascii", AID_NUCULA_ASCII)]))
