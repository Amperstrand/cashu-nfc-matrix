# cashu-nfc-matrix

NFC interop test matrix for cashu: **every Android cashu wallet with NFC
capability, tested against nucula firmware** — and later wallet-vs-wallet.

## Why

The bench Samsung S20 FE (labgrid place `phone-s20`, adb-driven) is a full
NFC peer: wallet apps bring HCE tag emulation (device reads phone) and/or
reader mode (phone reads device). Putting a phone and a nucula board in
the same field exercises the REAL interop surface — other wallets'
quirks, timing, NDEF/Type-4 layouts — with zero custom hardware. The
ACR1252U wedge (and the switched-hub workaround) drops out of the
critical path: phone↔nucula flows never write the ACR's emulated memory.

## Matrix (living table — the first milestone fills this in)

| Wallet | Platform | NFC mode | vs nucula CE (phone reads) | vs nucula reader (phone presents) | Status |
|---|---|---|---|---|---|
| cashu.me v0.2.0 (cashubtc/wallet) | native Android | HCE (AID D2760000850101) + deep-link receive | TBD | proven path (bench 2026-10-17) | driver in progress |
| minibits | PWA (Chrome) | WebNFC read (NDEFReader); HCE not available to PWAs | TBD | n/a (read-only) | inventory |
| …more wallets | | | | | inventory |

## Layout (planned)

- `drivers/<wallet>/` — adb/uiautomator driver per wallet (install,
  onboard, send-by-NFC, receive-by-tap; FLAG_SECURE-safe UI driving)
- `suites/` — pytest+labgrid stages: T0 place smoke → T1 wallet onboard →
  T2 tap flows both directions vs each nucula place (atom/m5stick/v2) →
  T3 repetition/timing matrix → T4 cross-wallet (future)
- `bench/` — mint fixtures (bench micronuts-mint / testnut.cashu.space —
  NEVER .cashu.exchange), browser-link token server, coordination
  (reuses the AB-BA bench-lock protocol; see bolty-rs
  docs/labgrid-bench-sharing.md)
- `.github/workflows/` — dispatch-only HIL runner + nightly soak

## Conventions

Read AGENTS.md. Bench hardware through labgrid places only
(coordinator ai-legion:20408); state changes end with a conwrt-lab
registry commit. Secrets never enter commits.
