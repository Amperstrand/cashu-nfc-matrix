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

## 2026-10-23 midday — local-mint T5 blocked by WALLET HTTPS-ONLY rule

- Tested with hardware as-is: T5[Nucula] on default testnut GREEN (3:09) after
  hardening wipe() (mint-presence verify + 2x retry + explicit error).
- Local mint chain: phone REACHES 192.168.13.208 (ping ok, no AP isolation),
  adapter serves fine — but cashu.me REJECTS http:// mints at the URL
  validation gate ("Enter a valid HTTPS mint URL"). NFC/reader stack is NOT
  the blocker; TLS in front of :3338 is the only missing piece.
- Owner options: (a) nodns.shop record + DNS-01 cert -> serve TLS on LAN with
  A record pointing at 192.168.13.208; (b) router :443 forward to .208 +
  HTTP-01; (c) accept testnut as the wallet-side mint (current default).
- m5stick: foreign python3 holder GONE, but GemPC init still fails after
  pcscd restart — stick remains in console mode; needs its lane's reader-mode
  switch or a replug. Reader not enumerable until then.

## 2026-10-23 16:30-17:3x — M5STICK WINDOW (owner-directed, 3-5h unattended)

- Reader recovered: port contention (foreign python3 + pcscd both on ttyUSB0,
  re-enumerated from ttyUSB3) — sole-ownership pcscd restart -> 'M5stick GemPC'
  back. NOT console mode. ccid-tooling lane steered to hold until 19:30.
- FIRST MFRC522<->HCE read GREEN (creqA via m5stick, 0.09s).
- T5[M5stick GemPC] PASSED (2:19) — first full payment via MFRC522; faster
  than nucula (3:09). Place list now includes m5stick (4 seats).
- PERF: m5stick 34.0ms/chunk median vs nucula 400ms / ACR ~15ms — same
  firmware skeleton, different driver -> isolates pn7160-nci (#408 comment).
- Fixes: driver launch-from-launcher; conftest self-hold acceptance
  ('already acquired' + ai-legion/root); write_latency_probe any-reader grant.
- 5-cycle m5stick payment soak running (m5-soak.log).

## 2026-10-23 m5stick window WRAP (~2h in)

- 10-cycle soak: **7 ok / 3 fail — sustained-traffic soft wedge** filed as
  ccid-firmware-rs issue (see latest): reader deaf after ~7 payment cycles,
  pcscd reinit recovers. 5/5 green soak ran minutes earlier (cycle-count
  class, not time).
- Numo x m5stick GREEN (T2 formal row param'd; 433B BIP21 URI). ACR cell of
  the same param = geometry-gated (phone on m5stick).
- boltcard-hce x m5stick inconclusive (SELECT 6400, service un-armed —
  belongs to boltcard2 lane; not chased).
- All commits pushed (b187904..): T2 numo param, numo driver fixes, PROTOCOL
  m5stick section, soak grant mapping, conftest self-hold.
- NEXT when phone can move: nucula comparison soak (13-green ceiling) or ACR
  cell. m5stick ceiling = 7 cycles until the firmware lane fixes the wedge.

## 2026-10-23 ~18:15 — #408 FIX BUILT + FLASHED LIVE (PR #445)

- Branch perf/408-harvest-first-wait (ccid-firmware-rs): DATA_FIRST_WAIT_MS=10
  in credit-gate + RX collect loops; stall clock stays nominal; 2 new host
  regression tests (95/95 green).
- Built `c3-ccid` profile (BUILD GOTCHA: session venv on PATH breaks
  idf_tools.py venv detection — use `env -i HOME=/root PATH=/root/.cargo/bin:...`).
- Flashed at 0x40000 (esptool via build.sh --flash), boot check passed,
  broker restarted, 'Nucula CCID via broker' enumerated, wire frames flowing.
- PR #445 open. LATENCY VERIFICATION PENDING: phone must return to the
  nucula coil (write_latency_probe + 0xD2: expect 399ms -> tens of ms).
- Broker stopped/restarted by me during flash (owner of broker this window).

## 2026-10-23 ~18:5x — INTERFERENCE EVENT + STANDDOWN (nucula side)

- ntag424-delta lane alert: c3 runs BOLTY board-nucula firmware (owner-
  approved 16:45; my 18:05 c3-ccid flash was measured through until ~18:2x
  then superseded). All 'Nucula CCID' probing STOPPED and stays stopped
  until the board returns to CCID duty.
- Bench damage acknowledged: my arbiter's naked pcscd restarts (per grant,
  soak cycles, flash cycles) = the 80-cycle pcscd churn. FIXED: arbiter now
  routes through pcscd-ctl --project wallet-matrix (tollgate-lab #15/#16),
  commit 3c5ab1f. Coordination reply: ops#26 / kanban t_4bc7ec5b.
- #408 STATUS: PR #445 carries round-1 (400->210ms constant, live-measured)
  + round-2 (progressive ladder + LAST_DATA_ARRIVAL_MS via 0xD2 word 8,
  95/95 host tests, built ok, flashed once but superseded). VERIFICATION
  RECIPE READY for the next CCID window: flash perf/408-harvest-first-wait,
  write_latency_probe + 0xD2 -> expect <210ms and the arrival word tells
  exactly where DATA lands.
- Remaining matrix work re-targets ACR1252/CardMan ONLY. Phone must move
  onto the ACR stack (on top of the m5stick = phone>m5stick>ACR) for
  T5[ACR] + the m5stick x ACR crosstalk probes.

## 2026-10-23 ~19:0x — #408 ROUND-2 VERIFIED: 40ms (10x total)

- Late-captured background probe (ran against round-2 firmware just before
  the bolty reflash): 53 chunks median 40.0ms constant (39.8-40.1), 2.1s
  total. Curve: 400 -> 210 -> 40ms. Natural peer response ~25-35ms (matches
  m5stick 34ms). PR #445 comment posted — verification COMPLETE host-side;
  0xD2 word-8 cross-check = optional next-CCID-window follow-up.

## 2026-10-23 ~19:4x — OWNER-DIRECTED TOP-3 REFACTORS (code-only, no hw)

1. GEOMETRY-AWARE CELLS: bench/geometry.py — phone position declared via
   PHONE_AT env or bench/phone-at file (never detected); T5 + T2 reader
   params now skip cells whose geometry is not live, with the reason.
   'unknown' (default) = legacy all-run. CI dispatches set PHONE_AT.
2. HARDENED EXCHANGE WRAPPER: bench/exchange.py — single home for
   warm-up-6400 retry, enumeration wait, stale-reader cache reset + heal.
   payer.py connect() documented as shim; full delegation deferred to the
   next hardware window (no blind refactor of live RF paths).
3. FILM-FIRST + RENDERED MATRIX: bench/render_matrix.py generates
   results/MATRIX.md + README <!-- matrix:begin --> block from
   results/*.jsonl (soak records now stamped reader+wallet; legacy files
   backfilled). Unit-tested in suites/test_render_matrix.py (plain pytest).
- EVIDENCE BANKED: evidence/2026-10-23-m5stick-window/ (11 files: m5 soaks,
  T5/T2 runs, fwbuild/fwflash logs) — /tmp/opencode/wallet-matrix is now
  disposable for the ccid-tooling migration/prune.
- Plain pytest: 16 skipped (hil-gated) + 2 render/geometry tests pass.

## 2026-10-23 ~20:15 — AUTOMATION PLAN step 1 LANDED (7b2c1f0)

- NOTE: /root/src/wallet-matrix-automation-plan.md referenced by the owner
  directive DOES NOT EXIST on this host (searched /root/src) — implemented
  from the inline spec in the directive. If the file surfaces, diff against
  it.
- matrixctl/ package: survey subcommand (python3 -m matrixctl survey).
  Probes: adb phone state+wifi, pcscd readers, labgrid places, c3 FWID
  (broker-journal banner heuristic). bench-state.yaml written + state/
  surveys history; deltas printed vs previous. Fixture-driven dev mode
  (--fake) — no hardware (bench contended by bolty). 2 plain tests green.
- Checkout moved: /root/src/wallet-matrix (post-migration; /tmp tree gone).
- NEXT: step 2 cell registry (requires/tier/cost/value/max-age, generalize
  bench/geometry.py), then 'next' ranking, then status/README + geometry
  docs + CI wiring.

## 2026-10-23 ~20:4x — AUTOMATION PLAN steps 2-4 LANDED (owner plan file now real)

- Plan file existed this time (owner wrote it); step 1 stands unchanged.
- STEP 2 (960a2c9 + 05f4fa5): matrixctl/registry.yaml = cell registry DATA
  (requires/tier/cost/value/max_age/suite), seeded per §3 (core: cashu.me x
  nucula+m5stick read+payment; extended: soaks/perf/numo; opportunistic:
  ACR/crosstalk/CardMan). plan/set/run/verify-state subcommands. bench-facts.yaml
  = human physical truth ('set phone.at ...'); planner demo on REAL state:
  phone nucula + c3 bolty => zero core runnable (the standdown as data).
- STEP 3 (258e4fb): 'next' — ranking (unlocked value x staleness)/effort over
  physical-action futures; staleness from results/*.jsonl vs max_age. Live
  answer for current bench: move phone -> m5stick-coil (unlocks read+payment+
  soak; outranks c3 reflash at 15min effort). Owner-facing one-action output.
- STEP 4 (75b5c57): staleness marks in render_matrix (fresh/aging/stale/never),
  docs/geometry.md with photo slots for the 4 positions, hil.yml survey+next
  pre-steps (bench-state becomes a CI artifact + the human directive prints
  in every run log). 11 plain tests green.
- Tier tuning = registry.yaml data only; runner code untouched.

## 2026-10-23 ~21:1x — OWNER NOTICE folded in: NTAG424 tag ON the c3 board

- Physical NTAG424 now sits on nucula-c3 (bolty fw window). Attribution
  rule + ATR pins recorded in bench/PROTOCOL.md; cards ledger live
  (matrixctl set card.<label> <position>; card.ntag424-owner-placed ->
  nucula-board); registry gained opportunistic cell ntag424-read
  (boltcard-class target, no phone needed, coordinate ntag424-delta).
- Lanes notified via herdr (w0:pP ntag424-delta + w16:p8 nucula-verify).
- Concurrent: T5[ACR1252] rerun in flight (first attempt's mint step
  failed transiently — manual mint minted fine).

## 2026-10-23 ~21:4x — ACR stack geometry finding + grant-mapping bugfix

- T5[ACR] attempts: (1) transient mint failure, (2) MY pcscd-ctl kwarg
  TypeError, (3) MY grant-mapping bug ('ACR' dict key never matched
  'ACR1252' -> ACR cell granted m5stick, unbinding its own reader) — both
  fixed + pushed. (4) grant now correct; phone armed; ACR healthy — but
  NoCard: the m5stick body sits BETWEEN phone and ACR and kills coupling.
  Owner action: phone DIRECTLY on the ACR antenna; stick beside it.
  Documented in docs/geometry.md.

## 2026-10-23 ~22:1x — close-out items

- ACR RF stage verdict: DEAD (phone side triple-verified armed+unlocked+
  foregrounded; ~11 min total polling across placements = NoCard; USB
  re-enumerated 21:03). RECOVERY = physical USB replug of the ACR
  (documented cure for this wedge class) — owner action pending. T5[ACR]
  + crosstalk cells blocked on it.
- apks banked: /root/src/wallet-matrix-apks (98M); wifi_connect.py
  re-pointed (repo drivers + WALLET_APK_DIR) — f4f1d57. /tmp/opencode/
  wallet-matrix fully disposable (old checkout there is stale; repo lives
  in ~/src/wallet-matrix).
- plan --tier now accepts opportunistic (was missing from choices).

## 2026-10-23 ~22:3x — plan step 4 code-only parts DONE (blocked-window work)

- (a) CI: smoke stage = survey + plan --tier core + pytest -m 'not extended';
  full = core+extended (marker registered; numo marked extended). matrixctl
  plan/run dry-run prints the cell mapping in every CI log.
- (b) geometry.md: measured placement laws (phone FACE-DOWN, coil center-
  upper back; m5stick BESIDE never between; c3-ok-as-spacer; centering)
  + 4 photo TODO slots for the owner.
- (c) renderer: staleness color marks (green/yellow/red age vs registry
  max-age; white=no budget; orange=never proven) + result red/green —
  README table now self-describing.
- 11 plain tests green. ACR replug still pending (thread resumes on 'done').

## 2026-10-24 ~02:0x — ACR post-replug: USB alive, RF still dead

- Replug executed (~01:5x): dmesg shows re-auth + reset; USB config OK;
  pcscd lists both ACR slots after a settle-then-restart (pcscd-ctl
  retries raced the device init — a plain restart after settle bound it).
- Armed phone (verified unlocked+foregrounded) on reader: STILL NoCard
  after 2 min live polling. USB/contact side healthy; RF field dead.
- FINAL DISCRIMINATOR (owner, 30s): any physical contactless card (bank
  card / boltcard) flat on the ACR while we poll. Card detected = RF
  alive and the phone's HCE radio is the suspect (then: phone reboot or
  NFC toggle). Still NoCard = ACR RF stage dead for good -> reader
  retirement / RMA; ACR matrix cells park as hardware-gated.

## 2026-10-24 ~07:3x — /tmp reclaim survived; tier-driven CI VALIDATED GREEN

- /tmp/opencode/wallet-matrix reclaimed: zero loss (repo at ~/src/wallet-matrix
  @1d6cfbe+; apks banked; wifi_connect re-pointed — all yesterday).
- CI smoke dispatch 40073406149 exposed the design flaw: workflow ran ALL
  suites regardless of plan (legacy non-gated ACR tests went red on a bench
  where 0 cells are runnable). FIXED per plan §5: smoke is plan-gated (0
  runnable => survey-only GREEN with junit placeholder); legacy T0/T2-ACR
  tests geometry-gated; T0 import-order fix. Second dispatch: GREEN.
- Smoke on the CURRENT bench = survey-only by design; the moment facts
  change (c3 back on ccid, or phone+m5stick geometry), the same dispatch
  runs real cells. Loose ends: ACR bank-card discriminator + c3 CCID
  return (both owner/lane-gated).
