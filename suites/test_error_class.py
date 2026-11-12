"""error_class: the #444 owner taxonomy shared by the soaks."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bench.error_class import classify_error  # noqa: E402


def test_rpc_class():
    assert classify_error("RPC transport error") == "rpc"
    assert classify_error(Exception("Unknown reader ACR1252")) == "rpc"


def test_t1_class():
    assert classify_error("card transmit failed") == "t1"
    assert classify_error(ValueError("NoCardException")) == "t1"


def test_tool_class():
    assert classify_error("adb: device offline") == "tool"
    assert classify_error("unsupported record") == "tool"
    assert classify_error(RuntimeError("no creq parsed")) == "tool"
    assert classify_error("NDEF parse_error") == "tool"


def test_other_never_silent():
    assert classify_error(RuntimeError("weird new failure")) == "other"
