# handoff — wallet-matrix sessions (2026-10-21 22:20 → ongoing overnight)

## 1. Mission / context
- Own cashu-nfc-matrix (issue #1) + feed nucula#33 O3; 8h unattended program
  (owner directive ~23:40): expand NFC cashu wallet test suites into repeatable
  CI for cashu-nfc-matrix (+ nucula/micronuts reuse), test/commit/push/comment
  Amperstrand-only.
- Places: acquired per-suite-module by suites/conftest.py (flock-first, loud
  skips on busy). NO standing interactive holds from this session.
- Peer lane: phone-hil done for the night (c3 restored to ccid image, broker
  up, place released; declared no further flashing/polling tonight).

## 2. Done (evidence: PR #2 merged; results/ + hil-run logs + PR bodies)
- cashu.me + Numo HCE fully identified + pinned (PR #2, bench/PROTOCOL.md):
  Type-4 NDEF AID D2760000850101, CC pinned byte-identical, E104 only when
  armed, live creqA decode (cashu.me) + BITCOIN:?CREQ=creqB (Numo).
- NEW self-hosted runner provisioned: actions.runner.Amperstrand-cashu-nfc-
  matrix.ai-legion-bench-matrix.service (user ubuntu, labels
  [self-hosted,Linux,X64,bench], /opt/actions-runner-matrix). Actions enabled
  on the repo for the first time tonight.
- suites/ T0-T4 + .github/workflows/hil.yml (dispatch smoke|full|soak +
  nightly 01:37 UTC; NO PR triggers — root-runner doctrine; pushes via SSH
  remote since the gh OAuth token lacks `workflow` scope).
- ROOT CAUSE #1 (soak stall): adb pipe-drainage hang — subprocess kill leaves
  grandchild-held pipes; ui.adb now file-backed + process-group kill.
- ROOT CAUSE #2 (wallet-side): cashu.me degrades to 'Nostr isn't ready' after
  sustained relay failures (bench AP blocks default Nostr relays). Gate is
  config-only (keys + relay URIs, connectivity NOT checked); visiting
  Settings→Nostr heals the runtime state. Driver self-heals
  (ensure_requestable). This also explains the 23:08 soak stall.
- ROOT CAUSE #3: app resumes last screen; monkey launch flaky →
  ui.launch_app() (resolve-activity + am start) + go_home() normalize.
- moto g7 power (ZY326DPC7R, second adb device): NO NFC feature — not usable
  for wallet-vs-wallet; another lane's device, untouched.

## 3. Current state
- Suite runs in tmux (matrix-hil, hil-run3.log): T0 5/5 PASS, Numo T2 PASSED
  live, T2b skip-loud (no PN7160 coupling — phone on ACR antenna),
  T1/T2-cashu.me re-verifying after driver fixes (runs 1-2 had fixture errors
  from resume-state + monkey).
- Runner online; workflow not yet dispatched (after suite green + merge).
- minibits: installed (official APK, sha-pinned), onboarding blocked at Terms
  fetch (bench AP egress; host-side 200, phone-side ConnectException);
  logcat forensics pending (phone busy with suite).
- boltcard HCE apps: disabled/restored per-module by conftest.

## 4. Next (priority)
1. Suite green → merge → `gh workflow run hil-nfc-matrix -f stage=full` →
   first true CI proof on the bench runner.
2. Dispatch stage=soak (60 cycles) overnight; aggregate_soak.py; PR numbers.
3. minibits Terms logcat probe + bench-AP allowlist ask for minibits.cash.
4. Payer T4 geometry-blocked: needs phone moved onto PN7160 antenna (human);
   everything else ready (bench/payer.py refuses ACR by rule).
5. Cross-repo: nucula hil.yml could reuse these matrix suites as the O3 leg.

## 5. Risks / coordination
- ACR READ-ONLY forever; payer refuses it in code.
- bc-taploop (Oct 19, bc-worker lane) reads the phone every 30s — retries
  absorb it; not ours to kill.
- No external posts; wallet upstreams untouched; secrets never committed.
- End-of-session: restore boltcard apps if disabled, broker+pcscd healthy,
  places released (already), this file updated.
