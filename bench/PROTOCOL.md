# The "Numo protocol" — NFC ecash exchange over NDEF Type 4 (as served by cashu.me v0.2.0 and Numo v1.9)

Source-pinned from cashubtc/wallet (`Core/NfcReceive/*`, MIT) and verified on the
bench S20 FE over the ACR1252 (read direction) on 2026-10-21. All byte values below
were observed live unless noted.

## Transport: ISO-DEP + NDEF Type 4 tag

- AID: `D2760000850101` (NFC Forum Type 4 Tag AID), category `other`
- CC file: FID `E103`, content (15B, byte-identical cashu.me vs Numo):

  ```
  00 0F 20 00 3B 00 34 04 06 E1 04 70 FF 00 00
  |CCLEN|v|MLe=59|MLc=52 |TLV: T=04 L=06 file=E104 max=0x70FF rd=open wr=open|
  ```

- NDEF file: FID `E104`. cashu.me: SELECT returns `6A82` while no request with an
  amount is armed (CC still advertises E104). Armed = a saved request with amount
  + default settlement mint, request-detail screen resumed.
- HCE ATR as seen by pcscd (S20 FE): `3B 88 80 01 00 00 00 00 80 81 71 00 79`
  when a service is routed; a bare `3B 80 80 01 01` appears pre-selection/ambiguous
  routing. A SELECT NDEF during ambiguous routing HANGS (Android waits for the
  user's app choice) — always ensure exactly one candidate service first.
- Phone-side service flags (cashu.me): `requireDeviceUnlock=true`,
  `requireDeviceScreenOn=true` — keep screen on + unlocked for automation.
  minibits declares `requireDeviceUnlock=false`.
- No NTAG424 SUN/proprietary files: E105/E110/F000/F001/F002 all `6A82`. "NTAG424
  bolt card" claims = Type-4 shape only, not SUN.

## Request phase (receiver -> payer)

READ BINARY on E104 returns an NDEF single text record (`T`, lang `en`):

- cashu.me:  `creqA<base64url(CBOR NUT-18 map)>` — observed
  `{i: 6e5b1afd, a: 21, u: sat, s: null, m: [https://testnut.cashu.space], d: null}`
- Numo v1.9: `BITCOIN:?CREQ=<UPPERCASE creqB bech32>` — BIP21 URI wrapper;
  creqB = bech32(hrp=`creqb`, data=compact CBOR v1). NUT-18 spec defines only
  creqA; creqB is a CDK-side compact encoding. Parsers must accept both.

## Payment phase (payer -> receiver)

Payer SELECTs E104 then UPDATE BINARY (`00 D6 off len data`, Le per chunk <= MLc=52)
the NDEF Type-4 file image (2-byte NLEN prefix + single NDEF record):

- writing offset 0 with first two data bytes `00 00` resets the receiver's
  incoming buffer (start-of-transfer marker);
- receiver completes when all bytes in `[0, NLEN+2)` are written, then parses;
- accepted payloads: NDEF text record carrying `cashuA|cashuB|crawB` token string
  (extractToken scans for the prefixes), or MIME `application/octet-stream` with
  CDK raw token bytes;
- receiver then validates terms (amount/mint/unit vs request), redeems (same
  mint) or swaps to its settlement mint, and shows Success/Failure.
- partial write + connection loss >3.5s => Failure ("Connection lost while
  receiving") — receiver never acts on partial NLEN data.

## Reader-side APDU recipe (host/nucula payer)

```
00 A4 04 00 07 D2760000850101 00        SELECT NDEF app       -> 9000
00 A4 00 0C 02 E103                     SELECT CC             -> 9000
00 B0 00 00 0F                          READ CC (15B)
00 A4 00 0C 02 E104                     SELECT NDEF file      -> 9000 (armed) / 6A82
00 B0 <off> <len<=59>                   READ NDEF (NLEN+2 bytes total)
... mint/swap matching token ...
00 A4 00 0C 02 E104                     SELECT NDEF file (write target)
00 D6 <off> <len<=52> <data>            UPDATE BINARY, chunked, starts 00 00
```

## Bench constraints observed (2026-10-21)

- S20 HCE answers the ACR1252 antenna reliably (14/14 connects at 5s cadence);
  the nucula-c3 PN7160 antenna does NOT couple to the phone at current bench
  geometry (design doc: T3=phone on ACR, T4=phone on PN7160) — moving the phone
  is a manual human op.
- ACR1252 stays READ-ONLY on this bench (CCID CE-write wedge rule). The D6 write
  path must go through a reader we own end-to-end (nucula) or an owner waiver.
- The bc-taploop lane reads the same phone every 30s (read-only Type-4 NDEF);
  coexists with our probes; its activations can interleave — retry on transient
  reader-unavailable.

## Lessons appended 2026-10-22 (all bench-proven, encoded in suites/)

1. **Fee headroom**: testnut's sat keyset charges input_fee_ppk=100 — a 1-sat
   token redeems to ZERO (cdk mint returns TransactionUnbalanced(0,0,0) =
   empty OUTPUTS; the keep-amount rounds away). Always mint >= 2 sats for
   receive flows; 21 is the house default. Host-side repro: the rig's
   receives_a_token_back test fails identically — mint /v1/keysets showed
   input_fee_ppk=100 on the active keyset.
2. **Phone network**: the wallet must run on the LAB wifi (SSID '2',
   192.168.13.0/24). The tollgate AP filters egress and the wallet then
   fails POSTs (swap/redeem) silently against cached balances.
   bench/wifi_check.sh gates every HIL run; bench/wifi_connect.py fixes it.
3. **Mint resets**: testnut resets wipe keysets+quotes; wallets with cached
   keysets must re-add the mint (or be wiped) or fresh tokens decode to 0
   valid proofs.
4. **PN7160 first-exchange warm-up (fresh c3-ccid fw)**: the FIRST exchange
   after idle can answer SW=6400; a brand-new connection then works.
   Type4Payer.connect() retries through it.
5. **Do not navigate the phone while a redemption is in flight** —
   balance_sats() presses BACK (go_home) and disarms the HCE mid-redeem.
   Watch the request screen text instead; read the balance only after.
6. The c3-ccid image that was on the board before 2026-10-22 08:05 NEVER
   activated the phone (reader blind); a fresh build from ccid-firmware-rs
   main (8c8a8337, c3-ccid preset) coupled instantly. If the nucula reader
   goes blind again: reflash first, debug second.


## m5stick/MFRC522 reader (2026-10-23)

- Same GemPC-twin serial contract as the nucula broker (115200, reader.conf
  entry /etc/reader.conf.d/m5stick-gempc). Phone HCE behaves identically:
  ATR 3b 80 81 31 fe 45 8b, CC byte-identical to ACR/nucula reads.
- Per-APDU latency: **34ms median** (write_latency_probe) vs ACR ~15ms /
  nucula 400ms — same ccid-firmware-rs skeleton, so the delta isolates the
  pn7160-nci exchange path (ccid-firmware-rs#408).
- First-exchange SW=6400 warm-up quirk ALSO present via m5stick (reader-
  independent: it is the phone HCE stack, not the PN7160).
- Recovery lesson: 'stick in console mode' was misdiagnosis — the serial
  port was contended (foreign holder + pcscd). GemPCTwin init failing in
  pcscd journal = check `fuser` FIRST, pcscd restart second.
- boltcard-hce (UI-less HCE service): SELECT AID answered 6400 then silent
  when its service is not armed — do not treat as reader failure.
