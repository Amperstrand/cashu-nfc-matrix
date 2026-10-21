# cashu-nfc-matrix — agent onboarding

Private Amperstrand project: NFC interop matrix of cashu wallets (Android,
adb-driven on the bench S20) against nucula firmware (and later each
other). Test INFRASTRUCTURE project — we assert on other wallets'
behavior, we never modify them.

## The phone is the peer

- Place `phone-s20` (Samsung S20 FE, adb serial RF8NB01ZYAH, cashu.me
  v0.2.0 installed). Phone↔nucula NFC flows do NOT involve the ACR1252U —
  its CCID-write wedge rules (see nucula AGENTS.md) apply only when a
  suite explicitly drives the ACR. If a suite ever does: ONE CE scenario
  per power cycle, full stop.
- cashu.me sets FLAG_SECURE: screenshots are black — drive via
  `uiautomator dump` + text-bounds taps (helper pattern:
  /root/src/worktrees/phone_flow.py on the bench).
- Token hand-off to the phone: bench-served browser-link page on :8077
  (ufw open from bench LAN). `adb input text` / `am start -d` TRUNCATE
  ~400-char tokens — never use them for tokens.
- Mint: bench micronuts-mint, or `testnut.cashu.space` — never
  `.cashu.exchange` (stale keysets decode as 0).
- Every wallet app installed on the phone gets its own driver module +
  its own seed profile; never reuse the cashu.me bench wallet's funds
  for other wallets' tests without a fresh faucet mint.

## Bench discipline

- All hardware through labgrid (coordinator ai-legion:20408); acquire/
  release per suite; AB-BA bench-lock protocol shared with bolty-rs /
  micronuts / nucula lanes (flock before place, never reversed).
- Anything you did not start is not yours to kill.
- Hardware state changes end with a conwrt-lab registry commit.

## Git / PRs

- Amperstrand org ONLY. This repo is NOT a fork — but keep the habit:
  always `gh pr create -R Amperstrand/cashu-nfc-matrix --head <branch>`;
  never bare-create. No external-project interaction (wallet upstreams
  included: we test them, we don't post to them) without per-item owner
  signoff of a shown draft.
- Squash merges with evidence bodies; re-check mergeable after each.
