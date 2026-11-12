"""Soak failure classification (ccid-firmware-rs #444 taxonomy).

payment_soak.py carried this inline; tap_soak needed the same split, so
the classifier lives here and both soaks import it. The classes have
DIFFERENT OWNERS — conflating them is what made the #444 wedge look
like one problem when it was three:

  rpc  — reader-context death / pcscd-restart wedge (reader host owner)
  t1   — card-level exchange loss, transient, latency-doubling precursor
  tool — phone UI automation / NDEF parse (bench tooling owner)
  other— everything else (triage bucket, never silently dropped)
"""

from __future__ import annotations


def classify_error(err) -> str:
    """Map an exception (or its repr string) to the owner class."""
    s = err if isinstance(err, str) else repr(err)
    if "RPC transport" in s or "Unknown reader" in s:
        return "rpc"
    if "transmit" in s.lower() or "NoCard" in s:
        return "t1"
    if ("adb" in s or "uiautomator" in s or "unsupported record" in s
            or "parse" in s.lower() or "no creq" in s):
        return "tool"
    return "other"
