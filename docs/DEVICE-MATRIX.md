# Device matrix — every reader × presenter combination on the bench

The framework's goal (owner directive 2026-10-22): test EVERY combination,
emit a live grid of tested/works/blocked per cell. Axes:

## Readers (RF front-ends that read a presenting device)

| id | hardware | firmware | pcscd name | place | status |
|---|---|---|---|---|---|
| `acr1252` | ACR1252U PICC | (reader stock) | `ACS ACR1252 Dual Reader [..PICC] 01 00` | ref-acr1252 | PROVEN both directions (read + pay) |
| `nucula-pn7160` | nucula C3 + PN7160 | ccid-firmware-rs `c3-ccid` (via broker) | `Nucula CCID via broker 00 00` | nucula-c3 | PROVEN both directions; needs phone flush on antenna |
| `m5stick-mfrc522` | M5Stick + MFRC522 | ccid-firmware-rs `m5stick` (GemPC twin) | `M5stick GemPC (MFRC522) 00 00` | nucula-rig (m5stick-usb) | reader exists; pcscd entry needs DTR-hold recovery after the FTDI replug — NEXT UNLOCK |

## Presenters (devices that hold/serve the wallet side)

| id | role | status |
|---|---|---|
| `cashu.me` (S20 HCE) | request-presenting wallet; accepts token write-back | PROVEN paid by BOTH readers |
| `numo` (S20 HCE) | PoS request presenter | probed (ACR); payer leg = same code path |
| `minibits` / `enuts` | phone wallets | blocked (Terms egress) / inventory |
| `nucula-wallet-fw` | nucula C3 running the WALLET image (presents like a tag, pays as wallet) | NOT YET on this bench session — flash path exists (phone-hil harness); the m5stick/nucula-wallet combos wait on it |
| `acr1252-as-tag` | ACR PICC emulation | FORBIDDEN (wedge class) — not a matrix cell |

## The grid (cells = payment round-trip results; updated per run)

| reader ↓ / presenter → | cashu.me | numo | nucula-wallet-fw |
|---|---|---|---|
| `acr1252` | **PASS** (T5[ACR1252], 2026-10-22) | probe-only | planned |
| `nucula-pn7160` | **PASS** (T5[Nucula CCID], 2026-10-22; needs flush geometry) | probe-only | planned |
| `m5stick-mfrc522` | planned (needs reader recovery) | planned | planned |

## How the suite fills the grid

- `suites/test_t0_place_smoke.py::test_device_matrix_grid` probes EVERY
  configured reader (presence in pcscd + one coupling attempt) and emits
  the live grid into the run's evidence dir — combinations that are absent
  skip LOUDLY with the recovery hint.
- Payment cells run via T5's reader parametrization; presenter axis grows
  by adding driver params (Numo driver exists).
- Field arbiter guarantees one-reader-at-a-time on the static stack.

## Naming note (owner's shorthand → here)

"microbits/microfips" in chat = **micronuts** (Amperstrand mint/wallet
Rust stack); "nucula with c nucula" = nucula C3 board; m5stick/522 =
M5Stick MFRC522 reader seat.


## 2026-10-23 — m5stick/MFRC522 × S20 HCE (owner-assigned window)

| cell | result | evidence |
|---|---|---|
| MFRC522 ← cashu.me HCE read (creqA) | **GREEN** | full NDEF 94B, CC identical to ACR/nucula, 0.09s read |
| MFRC522 → cashu.me HCE write (token) | **GREEN** | T5[M5stick GemPC] PASSED 2:19 (full payment, balance asserted) |
| per-APDU latency | **34.0 ms median** (53 chunks/1.8s) | write_latency_probe; vs ACR ~15ms, nucula 400ms (#408) |

Notes: the 'console mode' diagnosis was wrong — the stick was in reader mode
all along; a foreign lane's serial holder broke pcscd's GemPC init (port
contention, not firmware state). Self-held labgrid places ('already
acquired') now count as present in conftest. m5stick grant added to the
arbiter (ACR muted + broker parked + pcscd restart).
