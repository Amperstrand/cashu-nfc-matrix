#!/usr/bin/env python3
"""Per-chunk write-latency probe (ccid-firmware-rs#408 evidence tool).

Times every UPDATE BINARY chunk of a full Type-4 file write with us
precision on the host side. Constant ~400 ms/chunk through the nucula =
NCI collect-round bound (issue #408); ~15 ms through the ACR1252.

Usage: arm the phone (Tap, amount), then:
  python3 bench/write_latency_probe.py <token-file> [reader-substr=Nucula]
"""
import sys, time, statistics

sys.path.insert(0, ".")
from bench.field_arbiter import grant  # noqa: E402
from smartcard.System import readers  # noqa: E402
from bench.ndef import text_type4_file  # noqa: E402


def main() -> None:
    token = open(sys.argv[1]).read().strip()
    sub = "Nucula CCID"
    for a in sys.argv[2:]:
        if a.startswith("reader-substr="):
            sub = a.split("=", 1)[1]
    file = text_type4_file(token)
    grant({"Nucula": "nucula", "ACR": "acr"}.get(sub.split()[0], "m5stick"))
    r = [x for x in readers() if sub in str(x)][0]
    c = r.createConnection()
    c.connect()
    proto = c.getProtocol()

    def tx(apdu):
        t0 = time.perf_counter()
        _, s1, s2 = c.transmit(apdu, proto)
        return (time.perf_counter() - t0) * 1000, s1, s2

    tx([0x00, 0xA4, 0x04, 0x00, 0x07, 0xD2, 0x76, 0x00, 0x00, 0x85, 0x01, 0x01, 0x00])
    tx([0x00, 0xA4, 0x00, 0x0C, 0x02, 0xE1, 0x04])
    tx([0x00, 0xD6, 0x00, 0x00, 0x02, 0x00, 0x00])
    lats = []
    for off in range(0, len(file), 52):
        ch = file[off:off + 52]
        lat, s1, s2 = tx([0x00, 0xD6, (off >> 8) & 0xFF, off & 0xFF, len(ch)] + list(ch))
        assert (s1, s2) == (0x90, 0x00), f"chunk @{off}: SW={s1:02x}{s2:02x}"
        lats.append(lat)
    print(f"[{sub}] {len(lats)} chunks: median={statistics.median(lats):.1f}ms "
          f"mean={statistics.fmean(lats):.1f}ms min={min(lats):.1f}ms "
          f"max={max(lats):.1f}ms total={sum(lats)/1000:.1f}s")
    grant("quiet")


if __name__ == "__main__":
    main()
