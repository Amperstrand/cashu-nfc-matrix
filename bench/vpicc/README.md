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

## Real-mint cashuB vs READ_BUDGET — the LOCK decision (SESSION M, 2026-11-17)

**Decision: READ_BUDGET stays 3. Real-mint cashuB tokens (2715–2722
chars observed) are documented WON'T-CARRY by the virtual soak; carrying
them requires NEW physical capture evidence first** (hil charter filed —
budget re-pin is LOCK-gated, and there is nothing to re-vendor: see the
upstream check below). LOCK untouched; sha256s unchanged.

### The numbers (evidence: `results/ndef-ladder-sweep-*.json`, `real_mint_class` block)

Exact min-reads at the widest window the capture-pinned READ BINARY
accepts (Le=0xFE): file = NLEN(2) + NDEF message; reads = 1 CC +
ceil(file/254):

| token | kind | file B | mle min reads | legacy min reads | budget 3 |
|---|---|---|---|---|---|
| 2715 | text | 2727 | **12** | 87 | +9 over, wall |
| 2715 | binary | 2747 | **12** | 87 | +9 over, wall |
| 2722 | text | 2734 | **12** | 87 | +9 over, wall |
| 2722 | binary | 2754 | **12** | 88 | +9 over, wall |

Measured through the model rule engine: BOTH ladders hit the 6985 wall
after the 3rd successful content read (file truncated at 2 x 254B /
2 x 32B). No window-splitting trick can help: 3 x 254B = 762B < 2727B,
and even dropping the CC read (the ladder's MLe source) leaves
3 x 254B < 2727B. The token class is 4x the budget at max window.

### The re-pin fact base (from the golden captures)

- LOCK-pinned golden (2026-08-29, card 04C474FA967380, ONE continuous
  session): exactly 3 successful content reads in the entire capture —
  `read_cc_full` (15B), `read_cc_partial` (4B), `read_no_select` (15B)
  — then EVERY later READ BINARY answers 6985. The unconfounded wall
  evidence is `stress_read_cc_10x` r0–r9 (valid Le=0x0F, all 6985
  after the 3rd success); `malformed_le_zero`/`_max` are 6985 too but
  dual-caused (the Le 0x00/0xFF rule). **No captured exchange anywhere
  shows a 4th successful content read, nor a successful read after a
  6985.**
- Corroboration: upstream bolty-rs carries a SECOND capture
  (`tools/hil/difftest/results/golden_acr1252_card2.json`, card
  04455FFA967380, 2026-08-29 18:20, predates the 7c254a2 vendoring):
  identical behavior — 3 successes (same test_ids), then 6985 for every
  later read. Two independent NTAG424 cards, same budget = 3.
- Upstream check (2026-11-17, bolty-rs @ 39bb080): `vpicc_model.py`,
  `golden_acr1252.json`, `vpicc_model_auth.py`, `vpicc_golden.py` are
  byte-identical to the 7c254a2 vendoring (vendored file = header +
  upstream; LOCK sha256 f01e6dbd/f95148ae verified). `READ_BUDGET = 3`
  unchanged. **No upstream re-pin exists to re-vendor.**
- Nit (kept as-is: vendored file is sha-pinned): the vendored module
  docstring's prose says "first 2 reads" while citing the 3 successful
  test_ids; the executable rule and the golden both say exactly 3.

### What would change the decision

Only NEW golden capture evidence of a card serving >3 successful
content reads per session (or an upstream LOCK re-pin, which does not
exist): the hil capture charter covers the physical session. The cliff
itself is now TEST-PINNED —
`suites/test_vpicc_ladder.py::test_real_mint_class_budget_wall_both_ladders`
asserts the 2715/2722 class hits the 6985 wall under BOTH ladders, so a
budget raise or window widening without new evidence fails CI.
