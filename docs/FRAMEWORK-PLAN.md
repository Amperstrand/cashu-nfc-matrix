# Framework plan — cashu NFC interop as a regression harness

Owner directive (2026-10-22): the matrix becomes THE automated regression
framework: labgrid-placed Android wallets × nucula hardware/software, running
on the bench CI runner without LLM tokens.

## The two axes

**Wallets (phone-s20, adb-driven, FLAG_SECURE-safe)**

| wallet | status | driver |
|---|---|---|
| cashu.me v0.2.0 | FULL round-trip green (T5) | drivers/cashu_me.py (conditional state-machine) |
| Numo v1.9 | HCE probed (BIP21+creqB), onboarded | drivers/numo.py |
| minibits 0.4.5 | installed; Terms fetch blocked by bench egress — needs lab-wifi retest FIRST | none yet |
| eNuts alpha | inventory (alpha APK exists) | none |
| next: anything Numo lists as tap-to-pay | Sovran/Macadamia are iOS-only | — |

**Device roles (nucula-c3 place)**

| role | firmware | status |
|---|---|---|
| Reader (pcscd via broker) | ccid-firmware-rs `c3-ccid` | PROVEN both directions (read + write) |
| Wallet/tag (phone reads device) | nucula wallet fw | phone-hil lane's suites (T0-T4); matrix reuses their flash paths |
| Mint host | micronuts bench mint (local) | **the missing piece** — see below |

## The mint question (regression quality gate)

testnut.cashu.space is shared infra: it RESETS (stale keysets, dead tokens,
changed fees — two of tonight's four root causes). For repeatable regression
the payer must mint from a bench-local mint:

- `RIG_DIR`'s default MINT_URL = http://127.0.0.1:3338 (micronuts-audit-adapter,
  FakeWallet backend, auto-settling quotes) — the rig tests already target it.
- TODO (owner-visible): run it as a SUPERVISED systemd service on the bench
  host, bind it on the lab LAN (192.168.13.x), add the mint to the phone via
  `CashuMeDriver.add_mint()`, and flip `MINT_URL` in `bench/mint_token.sh`.
  Then the whole T5 loop (mint→wipe→arm→write→redeem) has zero internet
  dependency. (nucula#33 prereq 3 said exactly this.)

## Suite map (what guards what)

- T0 place smoke — phones/readers/locks present, wallet installed
- T1 driver lifecycle — launch/balance/arm/disarm (wallet UI regressions)
- T2 tap read — CC pinned, ATR pinned, NUT-18 decode (HCE regressions)
- T2b nucula read leg — same through the c3 reader (reader regressions)
- T3 soak — N arm→read cycles with timing (stability + perf regressions)
- T4 payer write — token write-back mechanics (payer regressions)
- T5 payment round-trip — THE e2e: mint→wipe→arm→read→write→redeem→assert
- T6 (planned) wallet↔wallet: cashu.me pays Numo (both on one phone is
  impossible — HCE+reader same device; needs a second NFC phone on the
  bench OR the nucula wallet fw as the second peer)
- T7 (planned) micronuts firmware seat: nucula running wallet fw — reuse
  phone-hil's flash/console harness, matrix wallets as counterparties

## CI pipeline (runner: ai-legion-bench-matrix, [self-hosted,bench])

- workflow_dispatch: smoke (T0-T1) | full (T0-T2b) | payment (T5) | soak (T3, N)
- nightly 01:37 UTC: full + payment (disjoint from nucula fuzz 03:23)
- every run: bench inventory artifact, junit, evidence dirs, soak summary
  committed to the repo (results/ is evidence, PRs cite it)

## Failure-triage map (encoded from tonight)

| symptom | cause class | action |
|---|---|---|
| reader "no card" forever, reader otherwise healthy | stale/blind c3 image | reflash c3-ccid (assert fw sha in O0) |
| phone swap fails "Connection error" | wrong AP (tollgate) | bench/wifi_connect.py |
| redeem TransactionUnbalanced(0,0,0) | 1-sat token vs input fee | mint >= 2 sats |
| token decodes to 0 proofs | mint reset, stale keysets | wipe + re-add mint |
| AppChooser popup / SELECT hang | competing HCE apps | conftest disables boltcard apps |
| transmit watchdog kill → reader unavailable | pcscd IFD wedge | acr_place pcscd-restart heal |
| first exchange SW=6400 | PN7160 warm-up | payer connect retries |

## ACR1252 roles (owner directive 2026-10-22) + the computer wallet

Three distinct roles — decide per role, not per device:

1. **ACR = the computer's NFC reader (ALLOWED, the big unlock)** — a host
   cashu wallet whose NFC front-end is the ACR in reader mode. It READS any
   presenting device (nucula wallet-fw request, phone wallets) and PAYS by
   writing tokens to that EXTERNAL tag (UPDATE BINARY through the reader —
   ordinary PCD behavior, no wedge class). This removes the phone dependency
   for nucula-side testing and creates the "computer cashu wallet with NFC".
   Engine decision: **nutbar's cashud** (Amperstrand, Rust, CDK 0.18.1 +
   axum daemon) — do not reinvent. Integration: payer.py's Type-4 transport +
   codec (bench/ndef.py) becomes cashud's `nfc` module (in-org upstream),
   or cashud serves token-engine endpoints that the bench payer calls.
   Proven pieces already: mint (rig CDK), Type-4 read+write (payer.py),
   fee/wifi/reset handling (suites).
2. **ACR = tag (PICC/CE emulation) — STILL FORBIDDEN** except the documented
   one-CE-scenario-per-power-cycle debug pattern; writing the ACR's own
   emulated memory is the CCID wedge (replug-only recovery). Not CI material.
3. **ACR = passive RF monitor — not possible** (active poller, no sniffer
   mode). Wire-level recording comes from the broker journal + APDU logs +
   phone logcat (to be bundled per-run as CI artifacts).

Status: payer.py ACR reader-mode enabled (owner directive, dated above);
CE/PICC escape code must stay out of this repo. First ACR-driven payment
test armed — needs the phone (or a nucula running wallet fw) in the ACR's
field.
