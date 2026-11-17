# bench/vpicc — vendored stateful NTAG424 model (rung 1)

Vendored from Amperstrand/bolty-rs `tools/hil/difftest/` (provenance in
the file headers, sha256-pinned by `LOCK`, self-asserted by
`suites/test_vpicc_model.py`). Purpose: hardware-free reader-side
testing for this bench — the ACR SELECT/READ-BINARY ladder that
`bench/probe_acr.py` drives can be exercised against the model over
vpcd instead of a physical card.

Scope: **rungs 1-4** — rung 1: stateful file selection, read budgets,
empirical error semantics, 57/57 byte-exact against the committed golden;
rungs 2-4 (vpicc_model_auth.py + suites/test_vpicc_auth.py): mutual
AuthenticateEV2 (AN12196-pinned vectors), FULL-mode secure write+read
roundtrips — pycryptodome bench-host dep, importorskip elsewhere.
golden (captured from ACR1252 ↔ NTAG424 04C474FA967380, 2026-08-29).
Auth/secure-mode rungs (2-4: mutual AuthenticateEV2, FULL-mode secure
read/write) live upstream in bolty-rs; port on demand per
docs/cross-project-infra-audit-2026-11-12.md follow-up #5.

- `vpicc_model.py` — the rule engine (stdlib only)
- `golden_acr1252.json` — the pinned golden capture
- `check_model_vs_golden.py` — offline gate (57/57)
- `LOCK` — reference-lock + re-vendor procedure
- `suites/test_vpicc_model.py` — pytest wrapper (both assertions)

vpcd wiring: `vpicc_golden.py` (vendored) + `suites/test_vpicc_live.py`
— the model served as a REAL virtual card through pcscd's vpcd driver.
Requires the bench-host "vPICC table card" slot (127.0.0.1:35970);
skips gracefully elsewhere. VERIFIED LIVE on ai-legion 2026-11-14:
57/57 byte-exact through the full pcscd -> vpcd -> model stack.

## Substitution mode — `tap_soak --virtual` (SESSION C, 2026-11-18)

`bench/tap_soak.py --virtual` replaces the phone-side HCE peer of the
read-direction soak with the vpicc model: each cycle builds a FRESH
creqA (rotating amount, payment_soak arming pattern), installs it on a
fresh `ModelVpicc(ndef_file=...)`, and reads it back through the
unchanged `probe_acr` Type-4 ladder over the pcscd vpcd slot. JSONL
rows are tagged `mode=virtual`; the error_class taxonomy applies
unchanged (verify with `--inject-bad-read CYCLE`, which serves one
unparseable NDEF and must classify as `tool`).

**What each mode proves:**

- **physical tap_soak (phone HCE + ACR1252)**: the REAL exchange —
  wallet app behavior, HCE serving, RF/timing on actual silicon.
- **virtual (`--virtual`, vpcd)**: transport + protocol only — the
  pcscd→vpcd→card→reader ladder, NDEF construction/parsing, creq
  verify, soak bookkeeping and error classification, at ~zero cost
  and zero hardware exposure. It does NOT prove RF/timing/HCE.

**Slot-contention rule:** the vpcd slot (127.0.0.1:35970) belongs to
pcscd; the vpicc client connects OUT to it. One card session at a
time — if another lane (difftest, nightly `test_probe_vpicc` /
`test_vpicc_live`) holds it, our card never gets probed; tap_soak
detects that (answered-probe deadline) and skips gracefully. NEVER
bind-test 35970 (PR #13 lesson: the DRIVER listens there) and never
restart pcscd to "fix" a busy slot.

**READ_BUDGET note (a substitution-mode finding):** the model's
capture-pinned READ_BUDGET is 3 successful content reads per card
session (anti-hammering wall, 6985 after). The standard probe ladder
consumes exactly 3 reads at creqA sizes (1 CC + 2 NDEF windows,
36-byte file) — a fresh `ModelVpicc` PER CYCLE is therefore required
and sufficient (a re-tap = a fresh card session; this mirrors a
physical re-tap, where each new field activation starts a session).
One shared model instance across cycles hits the 6985 wall after the
first cycle. If a future ladder needs >3 reads per cycle, that is a
finding to document — do NOT raise READ_BUDGET without a golden
re-pin (`LOCK`, the reference-lock + re-vendor procedure).

## Long NDEF vs READ_BUDGET — the MLe ladder (SESSION J, 2026-11-17)

Can the substitution soak carry LONG NDEF (cashuB 374-char tokens,
long-form records)? **Yes — via wider windows, not a bigger budget.**
`bench/probe_acr.py::read_ndef_request_mle` keeps the SELECT shape but
reads NDEF windows with Le = min(MLe from CC, 0xFE):

- measured (`bench/ndef_ladder_sweep.py`, evidence in
  `results/ndef-ladder-sweep-*.json`): cashuB-374 = 386B file =
  1 CC read + 2 x Le254 windows = **exactly 3 reads** — budget holds,
  no golden re-pin, `LOCK` untouched. The legacy 0x20 ladder needs 13
  reads there and dies on the 6985 wall after read 3 (truncated).
- why 0xFE: the card's own READ BINARY rule (capture-pinned) answers
  Le 0x00/0xFF with 6985 — the CC advertises MLe 0x2000, which exceeds
  the card's acceptance; the ladder clamps.
- **cliff, documented not hacked**: files > 508B (text payload > 496
  chars) exceed the budget under BOTH ladders — 3 reads x max 254B.
  Real-mint cashuB tokens (2722 chars observed) do NOT fit; carrying
  them needs either dropping the CC read or a READ_BUDGET re-pin —
  both are separate-charter material (physical lane / LOCK).
- physical lane untouched: `read_ndef_request` still emits the
  evidence-pinned fixed 0x20 windows (byte-pinned by
  `suites/test_vpicc_ladder.py::test_legacy_ladder_never_widens_windows`).
  `tap_soak --virtual --ndef-kind=cashuB` is the only caller of the
  mle ladder; `--ndef-kind=creqA` (default) keeps the SESSION C shape.
