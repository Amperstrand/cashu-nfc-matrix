"""NDEF (Type 4 single text record) codec for the cashu.me HCE exchange.

Mirrors cashubtc/wallet NfcNdefCodec.kt (MIT) — single record, TNF well-known
'T' text or TNF MIME application/octet-stream; SR (<=255B) or long form.
"""
from __future__ import annotations

import base64

MB, ME, CF, SR, IL = 0x80, 0x40, 0x20, 0x10, 0x08


def parse_type4_file(file: bytes) -> str | bytes:
    nlen = int.from_bytes(file[0:2], "big")
    rec = file[2 : 2 + nlen]
    header = rec[0]
    if not (header & MB and header & ME):
        raise ValueError("only single-record messages supported")
    if header & CF or header & IL:
        raise ValueError("chunked/id-length records unsupported")
    tlen = rec[1]
    short = bool(header & SR)
    plen = rec[2] if short else int.from_bytes(rec[2:6], "big")
    cur = 3 if short else 6
    rtype = rec[cur : cur + tlen]
    payload = rec[cur + tlen : cur + tlen + plen]
    tnf = header & 0x07
    if tnf == 0x01 and rtype == b"T":
        lang = payload[0] & 0x3F
        return payload[1 + lang :].decode()
    if tnf == 0x02 and rtype.lower() == b"application/octet-stream":
        return bytes(payload)
    raise ValueError(f"unsupported record tnf={tnf} type={rtype!r}")


def parse_text_record(file: bytes) -> str:
    out = parse_type4_file(file)
    if not isinstance(out, str):
        raise ValueError("binary payload where text expected")
    return out


def text_type4_file(text: str, lang: str = "en") -> bytes:
    payload = bytes([len(lang) & 0x3F]) + lang.encode() + text.encode()
    header = bytes([MB | ME | SR | 0x01, 0x01, len(payload)]) + b"T" + payload
    return len(header).to_bytes(2, "big") + header


def binary_type4_file(data: bytes) -> bytes:
    short = len(data) <= 0xFF
    if short:
        header = bytes([MB | ME | SR | 0x02, 0x18, len(data)]) + b"application/octet-stream" + data
    else:
        header = (
            bytes([MB | ME | 0x02, 0x18]) + len(data).to_bytes(4, "big")
            + b"application/octet-stream" + data
        )
    return len(header).to_bytes(2, "big") + header


def decode_creq(text: str) -> dict:
    """Decode a creqA (NUT-18 request) string to a CBOR map."""
    import cbor2

    assert text.startswith("creqA"), "not a creqA request"
    pad = "=" * (-len(text[5:]) % 4)
    return cbor2.loads(base64.urlsafe_b64decode(text[5:] + pad))


def decode_cashu_token(token: str) -> dict:
    """Decode cashuA/B (v4 JSON base64url) tokens."""
    pad = "=" * (-len(token[6:]) % 4)
    import json

    return json.loads(base64.urlsafe_b64decode(token[6:] + pad))
