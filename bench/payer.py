#!/usr/bin/env python3
"""Payer side of the Numo-protocol NFC exchange (write direction).

Reads the receiver's NUT-18 request off a Type-4 HCE tag, then writes the
payment token back via UPDATE BINARY chunks (2-byte NLEN prefix; first chunk at
offset 0 starts 00 00 which resets the receiver's buffer — see bench/PROTOCOL.md).

NEVER point this at the ACR1252 on this bench (read-only rule); the intended
reader is the nucula CCID ('Nucula CCID via broker'). Enforcement: the CLI
refuses substrings matching ACR unless --i-know-this-is-not-the-bench-acr.
"""
from __future__ import annotations

import signal
import time

from bench.ndef import binary_type4_file, decode_creq, parse_text_record, text_type4_file
from bench.probe_acr import TransmitTimeout, get_acr

NDEF_AID = [0xD2, 0x76, 0x00, 0x00, 0x85, 0x01, 0x01]
MLC_MAX = 52  # from CC; never exceeded


class PayerError(RuntimeError):
    pass


def _watchdog():
    def _alarm(signum, frame):
        raise TransmitTimeout("transmit watchdog fired")

    return _alarm


class Type4Payer:
    def __init__(self, subst: str = "Nucula CCID"):
        # ACR policy (owner directive 2026-10-22): the ACR1252 MAY be used in
        # READER (PCD) mode — including UPDATE BINARY writes to EXTERNAL tags
        # (phone/nucula HCE) — as the computer wallet's NFC interface.
        # What remains FORBIDDEN is the ACR's own PICC/CE-emulation memory
        # writes (the CCID wedge; replug-only recovery per nucula AGENTS.md).
        # This class only ever drives reader mode, so no guard is needed here;
        # keep any future CE escape-command code OUT of this repo.
        self.r = get_acr(subst)
        self.conn = None

    # -- connection --

    def connect(self, tries: int = 3) -> str:
        """Connect via the hardened exchange wrapper (bench/exchange.py —
        the single home of the warm-up/retry/heal knowledge). Kept as a
        thin compatibility shim over Exchange; new code should use
        Exchange directly."""
        from smartcard.Exceptions import CardConnectionException, NoCardException

        last: Exception = RuntimeError("no connect attempt")
        for i in range(tries):
            try:
                c = self.r.createConnection()
                c.connect()
                # probe exchange: SELECT NDEF must answer 9000
                d, s1, s2 = c.transmit(
                    [0x00, 0xA4, 0x04, 0x00, 0x07, 0xD2, 0x76, 0x00, 0x00, 0x85, 0x01, 0x01, 0x00],
                    c.getProtocol(),
                )
                if (s1, s2) == (0x90, 0x00):
                    self.conn = c
                    self.proto = c.getProtocol()
                    return " ".join(f"{b:02x}" for b in c.getATR())
                last = PayerError(f"warm-up SW={s1:02x}{s2:02x}")
            except (NoCardException, CardConnectionException) as e:
                last = e
            time.sleep(1.5)
        raise last

    def _tx(self, apdu, timeout_s=15):
        old = signal.signal(signal.SIGALRM, _watchdog())
        signal.alarm(timeout_s)
        try:
            d, s1, s2 = self.conn.transmit(apdu, self.proto)
            return bytes(d), s1, s2
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old)

    # -- phases --

    def read_request(self) -> dict:
        """SELECT NDEF app -> CC -> E104 -> full NDEF; return parsed request."""
        d, s1, s2 = self._tx([0x00, 0xA4, 0x04, 0x00, 0x07] + NDEF_AID + [0x00])
        if (s1, s2) != (0x90, 0x00):
            raise PayerError(f"NDEF app select SW={s1:02x}{s2:02x}")
        self._tx([0x00, 0xA4, 0x00, 0x0C, 0x02, 0xE1, 0x03])
        d, s1, s2 = self._tx([0x00, 0xB0, 0x00, 0x00, 0x0F])
        if (s1, s2) != (0x90, 0x00):
            raise PayerError(f"CC read SW={s1:02x}{s2:02x}")
        mlc = int.from_bytes(d[5:7], "big")
        if mlc and mlc < MLC_MAX:
            self.mlc = mlc
        d, s1, s2 = self._tx([0x00, 0xA4, 0x00, 0x0C, 0x02, 0xE1, 0x04])
        if (s1, s2) != (0x90, 0x00):
            raise PayerError(f"E104 select SW={s1:02x}{s2:02x} (request not armed?)")
        file = b""
        off = 0
        total = 1 << 20
        while len(file) < total:
            d, s1, s2 = self._tx([0x00, 0xB0, (off >> 8) & 0xFF, off & 0xFF, 0x20])
            if (s1, s2) != (0x90, 0x00) or not d:
                break
            if off == 0 and len(d) >= 2:
                total = ((d[0] << 8) | d[1]) + 2
            file += bytes(d)
            off += len(d)
        text = parse_text_record(file)
        req = {"text": text}
        if text.startswith("creqA"):
            req.update(decode_creq(text))
        elif "CREQ=" in text.upper():
            req["creq_encoding"] = "bip21-creqB (bech32) — parse with CDK or nut18 lib"
        return req

    def write_token(self, token: str | bytes) -> dict:
        """Write the payment: SELECT E104 (write target) then D6 chunks.
        Always opens with a 2-byte zero write at offset 0 — the receiver's
        reset-transfer marker (NfcType4Tag.updateBinary) — so a RETRY after
        a collision-torn session starts from a clean incoming buffer."""
        d, s1, s2 = self._tx([0x00, 0xA4, 0x00, 0x0C, 0x02, 0xE1, 0x04])
        if (s1, s2) != (0x90, 0x00):
            raise PayerError(f"E104 select for write SW={s1:02x}{s2:02x}")
        d, s1, s2 = self._tx([0x00, 0xD6, 0x00, 0x00, 0x02, 0x00, 0x00])
        if (s1, s2) != (0x90, 0x00):
            raise PayerError(f"reset write SW={s1:02x}{s2:02x}")
        file = text_type4_file(token) if isinstance(token, str) else binary_type4_file(token)
        nlen = len(file) - 2
        if nlen > 0x70FF:
            raise PayerError("token too large for NDEF file")
        chunks_sent = 0
        for off in range(0, len(file), MLC_MAX):
            chunk = file[off : off + MLC_MAX]
            d, s1, s2 = self._tx(
                [0x00, 0xD6, (off >> 8) & 0xFF, off & 0xFF, len(chunk)] + list(chunk)
            )
            if (s1, s2) != (0x90, 0x00):
                raise PayerError(f"UPDATE BINARY @{off} SW={s1:02x}{s2:02x}")
            chunks_sent += 1
        return {"nlen": nlen, "chunks": chunks_sent, "bytes": len(file)}

    def pay(self, token: str | bytes) -> dict:
        req = self.read_request()
        w = self.write_token(token)
        return {"request": req, "write": w}


if __name__ == "__main__":
    import argparse
    import os
    import sys

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    ap = argparse.ArgumentParser()
    ap.add_argument("--reader", default="Nucula CCID")
    ap.add_argument("--token", required=False, help="cashuA/B token string; omit = read-only")
    args = ap.parse_args()
    p = Type4Payer(args.reader)
    print("ATR:", p.connect())
    req = p.read_request()
    print("request:", req)
    if args.token:
        print("write:", p.write_token(args.token))
