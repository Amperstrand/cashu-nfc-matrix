# handoff — wallet-matrix session (2026-10-21 22:20 → ~06:00 CEST)

## 1. Mission / context
- This session OWNS cashu-nfc-matrix (issue #1) + feeds nucula#33 O3 (NFC tap flows).
- Places HELD: phone-s20 (adb RF8NB01ZYAH), nucula-c3 (console+broker), ref-acr1252
  (READ-ONLY). Acquired 22:23 under flock-first; comments set. nucula-rig NOT acquired
  (shares ACR). Parent reservation handed over; release by parent at end.
- Peer lane: phone-hil (herdr w19) — stopped nucula-ccid-broker 22:11 for console work,
  prompted to not reflash c3 during our window; broker restart is ours.
- cashu.me v0.2.0 on phone, wallet funded 10,009 sats on testnut.cashu.space (.space ONLY).
- KNOWN from parent: Tap screen = NTAG424-style HCE; ACR read ATR 3b888001000000008081710079;
  NDEF AID SELECT probe was cut short by a timeout. Phone found on AppChooserActivity
  (leftover NFC chooser dialog from parent's probe) — must dismiss + restore Tap screen.

## 2. Done so far (evidence)
- Repo cloned; README/AGENTS/issue #1 + nucula#33 read.
- Places acquired + commented (labgrid who shows nucula-c3, phone-s20, ref-acr1252 @ 22:23).
- phone-hil steered: no c3 reflash this window, broker restart coordination.
- (append as session progresses — every claim gets a log/artifact path)

## 3. Current hardware/software state
- nucula-ccid-broker: DOWN (SIGTERM 22:11, phone-hil). Firmware on c3 = ccid-serving
  image (broker journal shows GetSlotStatus answered until stop). Restart pending
  coordination reply.
- pcscd: system instance; ACR1252 reader = 'ACS ACR1252 Dual Reader PICC 01 00' (verify
  after next pcscd restart).
- Phone: screen on (2h timeout), cashu.me installed; current focus = NFC AppChooser.

## 4. Next steps (priority order)
1. Dismiss AppChooser, relaunch cashu.me, navigate to Send→Tap, verify HCE ATR via ACR.
2. Resume AID/file probing over ACR (NDEF AID D2760000850101 → CC → NDEF file; else
   DESFire/boltcard AIDs). Document exact NTAG424 file layout cashu.me presents.
3. drivers/cashu_me/: durable adb driver (wake/launch/navigate by dumped bounds,
   Tap-screen present, balance read).
4. Broker+pcscd restart once phone-hil replies → nucula-as-reader vs HCE probing.
5. Token round-trip if nucula reader can consume the HCE; else precise gap doc.
6. M1 inventory rows (minibits + others), PR everything, comment #1 + nucula#33.

## 5. Risks / coordination
- ACR = READ-ONLY (CCID wedge; replug-only recovery). HCE reads are safe/unlimited.
- adb input/am start TRUNCATE ~400-char tokens — never use for token transfer;
  browser-link :8077 path per AGENTS.md.
- phone-hil observed testnut.cashu.space swap failures (TransactionUnbalanced) —
  may break phone SEND flows; bench micronuts-mint is fallback; verify before soak.
- Anything not started by us is not ours to kill; end with conwrt-lab registry commit.
