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
