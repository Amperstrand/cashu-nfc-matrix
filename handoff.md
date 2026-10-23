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

## 2026-10-22 evening window — perf root-cause (ccid-firmware-rs#408)

- LIVE MEASURED: nucula write leg = 400.0 ms/chunk CONSTANT (53/53 within
  1.2 ms band; 21.2 s total) vs ACR1252 ~15 ms/chunk (0.8 s). Timer, not RF.
- ROOT CAUSE: pn7160-nci exchange = poll-round based (12x200 ms) + credit
  gating -> small APDU burns 2 full rounds = 400 ms regardless of the
  phone answering in ~5 ms. Source: crates/pn7160-nci/src/lib.rs exchange.
- FILED: ccid-firmware-rs#408 (cross-refs #119/#137/#120/#261), fix =
  harvest-before-sleep (0-ms poll after TX/credit) with rounds as fallback;
  verification via 0xD2 turnaround probe + T5 write timing.
- TOOL: bench/write_latency_probe.py (any reader, per-chunk us timing),
  commit c5feead. Comments posted on #408 and nucula#33.
- Journal-timestamp caveat: journalctl short-iso has NO sub-second —
  wire-log delta analysis only bounds latency to whole seconds; host-side
  perf_counter is the precise instrument.
- CI-payment item still waits on mint executing as the ubuntu runner
  (root-created files unreadable by ubuntu on this host even at 0666/777 —
  LSM-class; workaround: run mint step as root or prebuild the test binary).

## 2026-10-22 late window — CI PAYMENT GREEN (after 8 dispatches)

- **T5[Nucula CCID] PASSED ON CI (run 39845791451)**: first fully
  CI-driven NFC payment (runner mints, arms, writes over NFC, phone
  redeems, balance asserted). Evidence in the run's artifacts.
- Dispatch-chain root causes fixed along the way (each one a commit):
  stale root-owned /tmp/mint logs vs runner user -> per-PID temp files;
  runner HOME unset -> old /usr/bin/cargo 1.75 vs lockfile v4 -> absolute
  cargo resolution to /home/ubuntu/.cargo/bin; unquoted colon in step
  name broke workflow_dispatch (yaml parse); killed-run labgrid leaks ->
  pre-step releases stale holds; arbiter ops as ubuntu were polkit/EACCES
  no-ops -> sudo -n elevation (ubuntu has NOPASSWD); ACR bind hardcode
  '1-4' stale on replug -> live sysfs path via pyusb; owner-state /tmp
  file root<->runner collisions -> per-user fallback.
- cdk rig: /home/ubuntu/src/cdk is a SYMLINK into /root (700) — the whole
  'LSM' theory was that; dereferenced ubuntu-owned copy at /opt/bench/cdk;
  rig at /opt/bench/nucula-rig builds as ubuntu (cargo 1.99).
- M5stick cell BLOCKED (hardware, foreign): /dev/ttyUSB3 held by root
  python3 (PID 2059177, another lane) and the stick answers its CONSOLE
  protocol ('unknown: ... nfc') — not in GemPC reader mode; pcscd
  'M5stick GemPC init failed' every restart since 22:19. Not ours to kill.
- ACR cell: grant+reader verified working as ubuntu locally; CI failure
  at 20:19 was pre-sudo-fix run; expect green on next dispatch.

## 2026-10-23 — BENCH-LOCAL MINT LIVE (determinism unlock done)

- systemd `micronuts-demo-mint` (enabled, 0.0.0.0:3338): micronuts-audit-adapter
  bridging the stdio mint_server over Cashu REST. Zero input fees, in-memory.
- VALIDATED end-to-end from host: rig mint (21 sat, 2715-char cashuB, m=127.0.0.1:3338)
  -> cdk wallet receive -> RECEIVED=21 in 0.21s total. No testnut in the loop.
- Gotchas hit + resolved: (1) adapter binary lives at /root/.cargo-target/debug/
  (cargo config target-dir — NOT ./target); mint_server at /root/src/micronuts/target.
  (2) `cargo build -p A --bin X -p B` silently builds nothing for B — build
  packages separately. (3) mint_token.sh reads MINT_URL not MINT — a token with
  m=testnut against the local mint yields UnknownShortKeysetId (client-side,
  red herring; the adapter's keyset id IS correct CDK-v1 form).
- Next: switch T5/soak default to MINT_URL=http://<lan-ip>:3338 + phone add_mint
  (add_mint flow already in driver); then CI payments stop depending on testnut.

## 2026-10-23 checkpoint 2 — PR #4 open; mint switch mapped; ACR healthy

- PR #4 (hil-suites -> main) opened with full evidence body.
- Local mint reachable from PHONE subnet: host = 192.168.13.208, service on
  0.0.0.0:3338 -> phone add_mint target = http://192.168.13.208:3338.
- ACR wedge report (micronuts #132 work): checked 01:3x — USB present
  (072f:223b dev 030) AND enumerates in pcscd; no wedge visible now
  (replug may have happened or it self-recovered). T5[ACR] still gated on
  phone placement, not reader health.
- NEXT (T5 local-mint switch): wipe() currently hardcodes testnut in
  drivers/cashu_me.py (mint-picker ADD at x~924); parametrize wipe/add_mint
  with MINT_URL default http://192.168.13.208:3338, then T5/soak run
  fully bench-local. Procedure proven at CLI level (RECEIVED=21, 0.21s).

## 2026-10-23 ~04:40 — RED CI TRIAGED: DISK FULL (owner decision needed)

- Runs 39886689060 (scheduled, main) + 39852224171: runner EXECUTED the suite
  (01:55 job ran 11 min) but died uploading — / is 100% (685 MB free of 937G).
  NOT the ACR (USB dev 030 present, pcscd-healthy; no wedge).
- Safe cleanups already done in my domain: scratch logs/probe dirs removed;
  docker image prune (sweeper-sanctioned, dangling) reclaimed 0B.
- NOT mine to delete (owner decision list, ranked):
    /home/ubuntu            287G  (lane data: src 79G, avd-goldens 19G,
                                   .bitcoin 12G, tollgate-virtual-lab 13G...)
    /root/src/worktrees     74G   (release-verify worktrees + their target/)
    /root/.cargo-target     48G   (SHARED live build cache — deleting breaks
                                   phone-hil/other live builds mid-flight)
    /root/src/ccid-firmware-rs 17G (repo + targets; sweeper phase-aware)
- Until / has multi-GB free: CI will keep failing uploads; suites writing
  evidence dirs may also fail. RECOMMEND: owner-gated deep sweep or pausing
  lanes for one sweeper pass with phases enabled.
- PR #4 landed (squash) unless merge failed — see report. Queue unchanged:
  wipe/add_mint parametrization + T5 on local mint (192.168.13.208:3338).

## 2026-10-23 08:5x — PERF ANALYSIS COMPLETE (ccid-firmware-rs#408)

- 0xD2 turnaround split measured live (raw-serial probe, broker parked, phone
  armed): SELECT x6 = 400.4ms host RTT; serve turnaround 0.000ms, card exchange
  399.2ms -> ALL 400ms is inside pn7160 exchange; serve path + pcscd + broker
  contribute nothing. GSS x6 = 1.1ms (protocol+wire fine).
- Anomaly for fix lane: 0xD2 words 4-8 (blocks/wtx/recoveries) read ZERO while
  card=399ms — decomposition instrumentation not populating on this path.
- Commented on #408 (issuecomment-6358399783). Perf item CLOSED from matrix
  side; fix + verification now fully owned by the ccid-firmware-rs perf lane.
- Perf verdict one-liner: constant 400ms/APDU = 2x200ms NCI collect rounds +
  credit gate in exchange(); fix = harvest-before-sleep, expected effect
  ~26x on writes (21s -> <2s for a 2.7KB token).
