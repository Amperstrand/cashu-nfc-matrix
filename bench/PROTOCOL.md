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
