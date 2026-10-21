# handoff — wallet-matrix session (2026-10-21 22:20 → ~06:00 CEST)

## 1. Mission / context
- This session OWNS cashu-nfc-matrix (issue #1) + feeds nucula#33 O3 (NFC tap flows).
- Places HELD: phone-s20 (adb RF8NB01ZYAH), nucula-c3 (console+broker), ref-acr1252
  (READ-ONLY). Acquired 22:23 flock-first; comments set. nucula-rig NOT acquired.
- Peer lane: phone-hil (herdr w19) — now RUNNING its live HIL run (self-hosted runner
  `actions-runner-nucula`, esptool reflashing c3 since ~22:40); c3 console is THEIRS
  until they report done; I stay off.

## 2. Done so far (evidence; branch session/wallet-matrix-20261021, commit 273aa1c pushed)
- cashu.me HCE fully identified (bench/probe_acr.py + bench/ndef.py):
  - AID D2760000850101 (NDEF T4), CC: MLe=59 MLc=52, NDEF FID E104 max 0x70FF.
  - E104 present ONLY when a request with amount is armed (else 6A82) — matches
    upstream NfcType4Tag.kt (source-pinned: cashubtc/wallet, MIT).
  - NOT an NTAG424 SUN emulation: E105/E110/F000/F001/F002 all 6A82.
  - Request read LIVE over ACR: creqA{i:6e5b1afd, a:21, u:sat, m:[testnut.cashu.space]}.
  - ATR when routed+armed: 3B888001000000008081710079 (matches parent's note);
    bare 3B80800101 = pre-selection state.
- Chooser conflict root-caused: TWO bench HCE apps register the NDEF AID
  (com.amperstrand.boltcard.hce + dev.boltcard.hce). BOTH disabled for this window
  (restore at session end!): `pm enable` both. cashu.me selected → TapAgainDialog
  confirms routing.
- Phone arming path proven: Receive sheet → Ecash button (button area y≈1920, label
  tap misses!) → request screen → Amount row → 21 → armed ("Ask the sender to hold
  their phone near yours.").
- ACR wedge-myth resolved: the 180s "timeout" = AID-select hang while Android popped
  the chooser (no service routed → APDU never answered). Watchdog now in probe_acr.py.
- pcscd restarted once (22:33, serialized, no lane was mid-pcscd-op). NOTE: m5stick
  GemPC reader entry failed to re-init after restart (its FTDI replugged 21:46, port
  now ttyUSB3) — pre-existing, nucula-rig lane's to fix, not touched.

## 3. Current hardware/software state
- phone: cashu.me request screen ARMED (21 sat, Testnut). Screen on (2h timeout —
  re-arm stayon before soak). boltcard HCE apps disabled (see above).
- nucula-c3: BEING REFASHED by phone-hil's runner; both OTA slots were empty at
  22:44 mid-flash. nucula-ccid-broker: STOPPED by me (was fighting their esptool).
- pcscd: healthy; ACR PICC reader works (probe reproducible).
- testnut.cashu.space: phone-hil saw swap failures (TransactionUnbalanced + their
  malformed-C curl) — fresh MINT path untested; verify before payment leg.

## 4. Next steps (priority order)
1. drivers/cashu_me/driver.py: wake/launch/navigate/arm/balance + NFC phase read.
2. Tap-read soak via ACR (read direction): N arm→read→verify cycles with timings.
3. M1 inventory (issue #1): minibits PWA, eNuts, Numo (the HCE protocol cashu.me
   matches!), others; matrix rows + install notes (official sources only).
4. When phone-hil restores c3-ccid image: restart broker+pcscd, nucula-as-reader
   probe, then WRITE direction: mint 21 sats testnut, write NDEF token via D6,
   assert phone Success + balance 10,009→10,030.
5. PR + comments on #1 and nucula#33; final handoff; restore disabled apps.

## 5. Risks / coordination
- c3 exclusivity now with phone-hil's runner; my read of 'Nucula CCID via broker'
  blocked until their restore — broker start order: board settles → broker → pcscd
  restart (reader-missing ⇒ one more pcscd restart).
- ACR stays READ-ONLY (write path goes through nucula reader only).
- adb input/am start TRUNCATE ~400-char tokens — browser-link :8077 path only.
- Restore at end: pm enable com.amperstrand.boltcard.hce + dev.boltcard.hce.
- Anything not started by us is not ours to kill; end with conwrt-lab registry commit.
