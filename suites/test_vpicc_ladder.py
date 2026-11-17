"""SESSION J pin: long-form NDEF (cashuB) vs READ_BUDGET=3 — the ladder
answer (amperstrand-ops #23).

All offline (no pcscd, no hardware): the REAL probe_acr ladders are driven
through a fake reader/connection backed by ModelVpicc's rule engine, so the
pinned facts are about the shipped code, not a re-implementation:

1. legacy ladder (read_ndef_request, the physical lane's shape): exactly 3
   reads at creqA sizes — and at cashuB-374 it HITS the 6985 budget wall
   (truncated). This pins the problem the session was chartered to answer.
2. MLe single-window ladder (read_ndef_request_mle): cashuB-374 completes
   in exactly 3 content reads (1 CC + 2 x Le=0xFE), byte-exact reassembly,
   token decode round-trip — the budget HOLDS, no golden re-pin needed.
3. the cliff is documented, not hidden: >508B NDEF files (text >496 chars;
   real-mint 2722-char tokens) exceed the budget under BOTH ladders — a
   finding for a future charter (budget re-pin is LOCK-gated).
3b. SESSION M decision pin (amperstrand-ops #29): the real-mint class
   (2715/2722 chars, text+binary) asserts the 6985 wall under BOTH
   ladders — documented won't-carry; a budget raise requires NEW golden
   capture evidence (hil), never code.
4. physical-lane byte-identity: read_ndef_request emits only 0x20 NDEF
   windows (never Le>0x20) — the substitution-mode ladder cannot leak into
   the evidence-pinned physical read shape.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

pytest.importorskip("smartcard", reason="pyscard: probe_acr imports it")
pytest.importorskip("cbor2", reason="cbor2: creqA builder dep")

import bench.probe_acr as probe_acr  # noqa: E402
from bench.ndef import text_type4_file  # noqa: E402
from bench.tap_soak import build_cashub_text, build_creq_text  # noqa: E402
from bench.vpicc.vpicc_model import ModelVpicc  # noqa: E402


class FakeConn:
    """pyscard-connection shape over a fresh ModelVpicc answerer."""

    def __init__(self, answerer: ModelVpicc) -> None:
        self.model = answerer
        self.apdus: list[bytes] = []
        self.sws: list[tuple[int, int]] = []

    def connect(self):  # noqa: D102
        return None

    def getATR(self):  # noqa: D102
        return list(bytes.fromhex("3B8180018080"))

    def getProtocol(self):  # noqa: D102
        return 1

    def transmit(self, apdu, proto):
        capdu = bytes(apdu)
        self.apdus.append(capdu)
        if not capdu[:1] == b"\x90":  # pre-auth ladder only
            rapdu = self.model.answer(capdu)
        else:  # pragma: no cover — auth engine path unused here
            rapdu = self.model.answer(capdu)
        self.sws.append((rapdu[-2], rapdu[-1]))
        return list(rapdu[:-2]), rapdu[-2], rapdu[-1]


class FakeReader:
    def __init__(self, model: ModelVpicc) -> None:
        self.conn = FakeConn(model)
        self.name = "fake vPICC table card 00 00"

    def createConnection(self):  # noqa: D102
        return self.conn


def _run(monkeypatch, message_builder) -> tuple[dict, FakeConn]:
    model = ModelVpicc(ndef_file=text_type4_file(message_builder())[2:])
    fake = FakeReader(model)
    monkeypatch.setattr(probe_acr, "get_acr", lambda subst="": fake)
    return fake.conn.apdus


def _run_msg(monkeypatch, message: bytes) -> FakeConn:
    """Like _run but with raw NDEF message bytes (binary records too)."""
    model = ModelVpicc(ndef_file=message)
    fake = FakeReader(model)
    monkeypatch.setattr(probe_acr, "get_acr", lambda subst="": fake)
    return fake.conn


def _ndef_read_apdus(apdus):
    return [a for a in apdus if a[1] == 0xB0]


# --- 1. legacy ladder: creqA fits exactly, cashuB hits the wall ----------

def test_legacy_ladder_creqa_is_exactly_three_reads(monkeypatch):
    apdus = _run(monkeypatch, lambda: build_creq_text(30))
    res = probe_acr.read_ndef_request("fake")
    reads = _ndef_read_apdus(apdus)
    assert res["creq"]["a"] == 30 and res["creq"]["u"] == "sat"
    assert len(reads) == 3, reads  # 1 CC + 2 NDEF windows — zero headroom
    assert all(a[-1] == 0x20 for a in reads[1:])  # fixed 0x20 windows


def test_legacy_ladder_cashub_374_hits_budget_wall(monkeypatch):
    apdus = _run(monkeypatch, lambda: build_cashub_text(0, 30))
    res = probe_acr.read_ndef_request("fake")
    reads = _ndef_read_apdus(apdus)
    # 3 successful content reads (CC + 2 x 32B), then the 4th READ is
    # refused by the capture-pinned budget wall — file stays truncated.
    assert len(reads) == 4
    assert res["ndef_len"] == 2 * 32  # 64 of 386 bytes — never completed
    assert "parse_error" in res or res.get("creq") is None


# --- 2. MLe single-window ladder: cashuB fits exactly --------------------


def test_mle_ladder_cashub_374_fits_budget_exactly(monkeypatch):
    apdus = _run(monkeypatch, lambda: build_cashub_text(7, 37))
    res = probe_acr.read_ndef_request_mle("fake")
    reads = _ndef_read_apdus(apdus)
    assert res["ladder"] == "mle" and res["window_le"] == 0xFE
    assert res["reads"] == {"cc": 1, "ndef_windows": 2, "total": 3}
    assert len(reads) == 3
    assert reads[0][-1] == 0x0F  # CC read stays 15B
    assert reads[1][-1] == 0xFE and reads[2][-1] == 0xFE
    assert "budget_wall_sw" not in res  # completed before the wall
    assert res["ndef_len"] == 386 and "parse_error" not in res
    assert res["cashu"]["u"] == "sat" and "c=7" in res["cashu"]["m"]
    assert "a=37sat" in res["cashu"]["m"]  # armed fields survived the wire


def test_mle_ladder_creqa_unchanged_semantics(monkeypatch):
    """Short payloads ride the mle ladder fine too (1 CC + 1 window)."""
    apdus = _run(monkeypatch, lambda: build_creq_text(41))
    res = probe_acr.read_ndef_request_mle("fake")
    assert res["reads"]["total"] == 2  # 42B file fits one Le=0xFE window
    assert res["creq"]["a"] == 41


# --- 3. the cliff is documented (finding, not a hack) ---------------------

@pytest.mark.parametrize("chars,wall", [(496, False), (497, True), (2722, True)])
def test_mle_ladder_cliff_at_508b_files(monkeypatch, chars, wall):
    apdus = _run(monkeypatch, lambda: "x" * chars)
    res = probe_acr.read_ndef_request_mle("fake")
    if wall:
        assert res.get("budget_wall_sw") == "6985"
        assert res["reads"]["total"] == 3  # budget consumed, file truncated
    else:
        assert "budget_wall_sw" not in res and res["reads"]["total"] == 3


# --- 3b. real-mint cliff pin (SESSION M): 6985 under BOTH ladders ---------
#
# Decision artifact for amperstrand-ops #29: real-mint cashuB tokens
# (2715/2722 chars observed) are documented WON'T-CARRY. READ_BUDGET=3 is
# pinned by TWO independent golden captures (04C474FA967380 LOCK-pinned;
# 04455FFA967380 upstream card2) — exactly 3 successful content reads,
# no 4th in any capture — so raising the budget needs NEW physical
# capture evidence (hil charter), not code. This test pins the cliff so
# a "fix" that silently widens the budget or the windows fails HERE.

_REAL_MINT = pytest.mark.parametrize("chars", [2715, 2722])
_REAL_MINT_KIND = pytest.mark.parametrize("kind", ["text", "binary"])


@_REAL_MINT
@_REAL_MINT_KIND
def test_real_mint_class_budget_wall_both_ladders(monkeypatch, chars, kind):
    from bench.ndef import binary_type4_file

    msg = (text_type4_file("x" * chars) if kind == "text"
           else binary_type4_file(b"x" * chars))[2:]
    file_len = len(msg) + 2
    # exact min-reads at the widest accepted window (Le=0xFE): the class
    # needs 1 CC + ceil(file/254) = 12 reads — 4x the budget.
    assert 1 + -(-file_len // 254) == 12

    # mle ladder: wall reported, budget consumed, file never completes
    conn = _run_msg(monkeypatch, msg)
    res = probe_acr.read_ndef_request_mle("fake")
    assert res["budget_wall_sw"] == "6985"
    assert res["reads"] == {"cc": 1, "ndef_windows": 2, "total": 3}
    assert res["ndef_len"] < file_len  # 2 x 254B of 2727..2754B

    # legacy ladder: 3 successful reads then the 4th READ BINARY = 6985
    conn = _run_msg(monkeypatch, msg)
    res = probe_acr.read_ndef_request("fake")
    reads = _ndef_read_apdus(conn.apdus)
    assert len(reads) == 4  # 1 CC + 2 NDEF windows + 1 refused
    assert conn.sws[-1] == (0x69, 0x85)  # the 4th read's 6985 wall
    assert res["ndef_len"] == 2 * 32  # truncated — never completed


# --- 4. physical-lane byte-identity guard ---------------------------------

def test_legacy_ladder_never_widens_windows(monkeypatch):
    """The physical lane's read shape is evidence-pinned: whatever the
    substitution lane does, read_ndef_request must keep emitting fixed
    0x20 NDEF windows (SESSION J stop condition, encoded as a test)."""
    for builder in (lambda: build_creq_text(9),
                    lambda: build_cashub_text(1, 9),  # long payload...
                    lambda: "x" * 500):               # ...and overlong ones
        apdus = _run(monkeypatch, builder)
        probe_acr.read_ndef_request("fake")
        for a in _ndef_read_apdus(apdus):
            assert a[-1] in (0x0F, 0x20), a.hex()  # CC=15B, NDEF=32B only


# --- 5. the cashuB builder itself ------------------------------------------

def test_cashub_builder_fresh_exact_length():
    t0 = build_cashub_text(0, 30)
    t1 = build_cashub_text(1, 31)
    assert len(t0) == len(t1) == 374
    assert t0 != t1  # fresh token per cycle
    from bench.ndef import decode_cashu_token

    tok = decode_cashu_token(t1)
    assert tok["u"] == "sat" and "c=1" in tok["m"] and "a=31sat" in tok["m"]
