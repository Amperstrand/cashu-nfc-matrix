# cashu-nfc-matrix

NFC interop test matrix for cashu: **every Android cashu wallet with NFC
capability, tested against nucula firmware** — and later wallet-vs-wallet.

## Why

The bench Samsung S20 FE (adb-driven via its labgrid place) is a full
NFC peer: wallet apps bring HCE tag emulation (device reads phone) and/or
reader mode (phone reads device). Putting a phone and a nucula board in
the same field exercises the REAL interop surface — other wallets'
quirks, timing, NDEF/Type-4 layouts — with zero custom hardware. The
ACR1252U wedge (and the switched-hub workaround) drops out of the
critical path: phone↔nucula flows never write the ACR's emulated memory.

## Matrix (living table — updated 2026-10-21/22 wallet-matrix session; evidence in bench/PROTOCOL.md + run logs)

| Wallet | Platform | NFC mode | vs nucula CE (phone reads) | vs nucula reader (phone presents) | Status |
|---|---|---|---|---|---|
| cashu.me v0.2.0 (cashubtc/wallet) | native Android (Capacitor) | HCE Type-4 NDEF, AID D2760000850101; armed=request+amount; accepts token write-back (cashuA/B, crawB MIME); reader mode on Send→Tap | pending nucula-CE presentation | **protocol GO** (bench/PROTOCOL.md), **bench NO-GO**: phone sits on ACR antenna, not PN7160 (manual move needed); ACR read of HCE PROVEN 2026-10-21 (creqA live-decoded) | driver + probe done (drivers/, bench/) |
| Numo v1.9 (cashubtc/Numo, PoS) | native Android | HCE Type-4 NDEF armed on Charge screen; request = `BITCOIN:?CREQ=creqB(bech32)`; CC byte-identical to cashu.me | n/a (it IS the receiver side) | same geometry constraint; ACR read PROVEN live (117B NDEF, 2026-10-21) | onboarded + probed |
| minibits v0.4.5-beta.1 (minibits-cash) | React Native (play/zapstore/github) | reader (reads requests, pays + writes token back) + HCE share (dynamic registration via react-native-hce; `requireDeviceUnlock=false`) | TBD | TBD | installed; onboarding BLOCKED at Terms fetch — phone-side egress filter on bench AP suspected (host 200, phone fail; Nostr relays blocked likewise) |
| eNuts (cashubtc/eNuts) | React Native (TestFlight/alpha) | NFC reader per enuts.cash ("QR and NFC ready"); HCE TBD | TBD | TBD | inventory only (alpha rebuild in flight; APK = v1.0.0-alpha.2) |
| dev.boltcard.hce + com.amperstrand.boltcard.hce (bench apps) | native | HCE on NDEF AID (boltcard URI) | n/a | conflicts with wallets on D2760000850101 (AppChooser popup + SELECT hang) | both DISABLED during wallet-matrix window; restore at session end |

NFC-capable but not Android-reachable per Numo's compatibility list: Sovran (iOS),
Macadamia (iOS). Phoenix listed as tap-to-pay compatible (ecash support unverified).

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
(the bench labgrid coordinator); state changes end with a conwrt-lab
registry commit. Secrets never enter commits.
