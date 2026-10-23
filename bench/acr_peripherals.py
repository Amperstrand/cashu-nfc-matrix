#!/usr/bin/env python3
"""ACR1252 peripherals: buzzer control (default OFF for automation; the LED
already follows RF activity natively — the visual 'money is moving' cue).

Method: CCID escape commands through pyscard SCardControl.
  1. GET_FEATURE_REQUEST (SCARD_CTL_CODE 3400) -> discover FEATURE_CCID_ESC
  2. ACR1252U PICC operating parameters:
       GET:  FF 00 00 46 00          -> current parameter byte
       SET:  FF 00 00 43 01 <PP>     -> write parameter byte
     PP bit 1 = buzzer (1 = ON, 0 = OFF); other bits read-modify-write.
     (Command indexes 43/46 per ACR1252U PICC command set; ACR122U used 24.)

CLI: acr_peripherals.py status | buzzer on|off
Default policy: the suite's acr_place fixture sets buzzer OFF each run.
"""
from __future__ import annotations

import sys

SCARD_CTL_CODE = lambda c: 0x42000000 + c  # noqa: E731
GET_FEATURE_REQUEST = SCARD_CTL_CODE(3400)
FEATURE_CCID_ESC = 0x21  # ccid feature tag for escape (confirmed via TLV)

GET_PICC_PARAMS = [0xFF, 0x00, 0x00, 0x46, 0x00]
SET_PICC_PARAMS = [0xFF, 0x00, 0x00, 0x43, 0x01]
BUZZER_BIT = 0x02


def _reader():
    from smartcard.System import readers

    cands = [r for r in readers() if "ACR1252" in str(r) and "PICC" in str(r)]
    if not cands:
        raise SystemExit("ACR1252 PICC not present")
    return cands[0]


def _escape_code(conn) -> int:
    feat = conn.control(GET_FEATURE_REQUEST, [])
    for i in range(0, len(feat) - 1, 2):
        if feat[i] == FEATURE_CCID_ESC:
            return SCARD_CTL_CODE(feat[i + 1])
    raise SystemExit("FEATURE_CCID_ESC not offered by driver")


def get_pp(conn=None) -> int:
    own = conn is None
    if own:
        conn = _reader().createConnection()
        conn.connect()
    try:
        code = _escape_code(conn)
        res, sw1, sw2 = conn.control(code, GET_PICC_PARAMS)
        if not res:
            raise SystemExit(f"empty GET params response SW={sw1:02x}{sw2:02x}")
        return res[-1]
    finally:
        if own:
            conn.disconnect()


def set_buzzer(on: bool) -> int:
    conn = _reader().createConnection()
    conn.connect()
    try:
        code = _escape_code(conn)
        pp = get_pp(conn)
        pp_new = (pp | BUZZER_BIT) if on else (pp & ~BUZZER_BIT)
        res, sw1, sw2 = conn.control(code, SET_PICC_PARAMS + [pp_new])
        print(f"PP {pp:#04x} -> {pp_new:#04x} (buzzer {'ON' if on else 'OFF'}) "
              f"SW={sw1:02x}{sw2:02x} res={bytes(res).hex()}")
        back = get_pp(conn)
        print(f"read-back PP={back:#04x} "
              f"buzzer-bit={'on' if back & BUZZER_BIT else 'off'}")
        return back
    finally:
        conn.disconnect()


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "status"
    if mode == "status":
        try:
            pp = get_pp()
            print(f"PP={pp:#04x} buzzer={'ON' if pp & BUZZER_BIT else 'off'} "
                  f"(set with: acr_peripherals.py buzzer on|off)")
        except SystemExit as e:
            print(f"escape path blocked on this firmware/driver combo: {e}")
            print("fallback: ACS 'PUTools/ACR1252U-NT tooling' on a Windows host "
                  "can set the buzzer persistently; or accept beeps.")
    elif mode == "buzzer":
        try:
            set_buzzer(sys.argv[2] == "on")
        except SystemExit as e:
            print(f"escape path blocked: {e}")
    else:
        raise SystemExit(__doc__)
