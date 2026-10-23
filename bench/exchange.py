"""One hardened exchange wrapper for every NFC tool (refactor 2).

The retry/heal knowledge was scattered: Type4Payer.connect's warm-up
retries, get_acr's 20s enumeration retry, per-chunk retries in probes,
and payment_soak's recovery path each encoded a piece. `Exchange` is the
single place that knows:

  - fresh connections answer the FIRST exchange with SW=6400 (PN7160
    warm-up; bench-verified reader-independent — the phone HCE stack):
    retry once on a fresh connection before surfacing an error
  - reader enumeration after bind/pcscd restart lags seconds for ccid
    hotplug readers: bounded wait with cache refresh
  - a transmit failure mid-session usually means a stale pyscard reader
    (context died across a pcscd restart): reset the process-wide cache
    and re-resolve before giving up

No hardware is touched at import time; plain pytest never instantiates
this (hil-gated suites only).
"""
from __future__ import annotations

import time

from bench import probe_acr

WARMUP_SW = (0x64, 0x00)
ENUMERATE_TIMEOUT_S = 20.0
TRANSMIT_RETRIES = 3


class Exchange:
    """Hardened reader session: resolve + connect + transmit with the
    bench's known failure classes handled in one place."""

    def __init__(self, subst: str):
        self.subst = subst
        self._conn = None
        self._proto = None

    def connect(self) -> None:
        deadline = time.monotonic() + ENUMERATE_TIMEOUT_S
        while True:
            probe_acr._READER_CACHE.clear()
            try:
                reader = probe_acr.get_acr(self.subst)
                conn = reader.createConnection()
                conn.connect()
                self._conn = conn
                self._proto = conn.getProtocol()
                return
            except Exception:
                if time.monotonic() > deadline:
                    raise
                time.sleep(1.5)

    def transmit(self, apdu: list[int]) -> tuple[list[int], int, int]:
        """One APDU with warm-up/retry handling. Returns (data, sw1, sw2)."""
        last_exc: Exception | None = None
        for attempt in range(TRANSMIT_RETRIES):
            if self._conn is None:
                self.connect()
            try:
                conn = self._conn
                assert conn is not None
                data, sw1, sw2 = conn.transmit(apdu, self._proto)
                if (sw1, sw2) == WARMUP_SW and attempt == 0:
                    time.sleep(0.3)  # warm-up quirk: fresh exchange next
                    continue
                return data, sw1, sw2
            except Exception as e:  # stale reader/context class
                last_exc = e
                self._conn = None
                time.sleep(0.5)
                self.connect()
        raise last_exc  # type: ignore[misc]

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.disconnect()
            except Exception:
                pass
            self._conn = None
