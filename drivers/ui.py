"""adb + uiautomator UI driving for FLAG_SECURE apps (screenshots are black).

dump() pulls the current window hierarchy; node lookup by text/rid; tap() by
node bounds center. Designed for cashu.me on the bench S20 but wallet-agnostic.
"""
from __future__ import annotations

import re
import subprocess
import time
import xml.etree.ElementTree as ET

DEFAULT_SERIAL = "RF8NB01ZYAH"


def adb(serial: str, *args: str, timeout: float = 30) -> str:
    """Run adb; hang-proof: stdout goes to a file (no pipe drainage), and the
    whole process group is killed on timeout (adb's device-side grandchildren
    hold pipes open forever otherwise — observed as a 25-min wedge mid-soak)."""
    import os
    import signal
    import subprocess
    import tempfile

    with tempfile.TemporaryFile("w+") as out:
        proc = subprocess.Popen(
            ["adb", "-s", serial, *args],
            stdout=out,
            stderr=subprocess.STDOUT,  # diagnosable failures (monkey et al.)
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            raise TimeoutError(f"adb {args[:3]} timed out after {timeout}s")
        out.seek(0)
        text = out.read()
        if proc.returncode != 0:
            raise RuntimeError(
                f"adb {args} failed: rc={proc.returncode}: {text.strip()[:300]}"
            )
        return text


def launch_app(serial: str, package: str, timeout: float = 30) -> str:
    """Resolve the launcher activity then start it (monkey is flaky; a bare
    component would break across activities being renamed)."""
    out = adb(serial, "shell", "cmd", "package", "resolve-activity", "--brief",
              "-c", "android.intent.category.LAUNCHER", package, timeout=timeout)
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    comp = lines[-1] if lines else ""
    if "/" not in comp:
        raise RuntimeError(f"cannot resolve launcher for {package}: {out.strip()[:200]}")
    return adb(serial, "shell", "am", "start", "-n", comp, timeout=timeout)


def dump(serial: str = DEFAULT_SERIAL) -> ET.Element:
    adb(serial, "shell", "uiautomator", "dump", "/sdcard/ui.xml")
    xml = adb(serial, "shell", "cat", "/sdcard/ui.xml")
    return ET.fromstring(xml.strip())


def nodes(root: ET.Element) -> list[dict]:
    out = []
    for n in root.iter("node"):
        out.append(
            {
                "text": n.get("text") or "",
                "rid": n.get("resource-id") or "",
                "cls": (n.get("class") or "").split(".")[-1],
                "bounds": n.get("bounds") or "",
                "clickable": n.get("clickable") == "true",
                "checked": n.get("checked") == "true",
                "package": n.get("package") or "",
            }
        )
    return out


def bounds_center(b: str) -> tuple[int, int]:
    m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", b)
    if not m:
        raise ValueError(f"bad bounds {b!r}")
    x1, y1, x2, y2 = map(int, m.groups())
    return (x1 + x2) // 2, (y1 + y2) // 2


def find(
    root: ET.Element,
    text: str | None = None,
    rid: str | None = None,
    contains: str | None = None,
    cls: str | None = None,
) -> dict | None:
    """First node matching all given criteria."""
    for n in nodes(root):
        if text is not None and n["text"] != text:
            continue
        if rid is not None and n["rid"] != rid:
            continue
        if contains is not None and contains not in n["text"]:
            continue
        if cls is not None and n["cls"] != cls:
            continue
        return n
    return None


def wait_for(
    serial: str,
    text: str | None = None,
    rid: str | None = None,
    contains: str | None = None,
    timeout: float = 15.0,
    poll: float = 0.6,
) -> dict:
    """Poll dumps until a matching node appears; return its node dict."""
    deadline = time.monotonic() + timeout
    last_exc: Exception | None = None
    while time.monotonic() < deadline:
        try:
            root = dump(serial)
            hit = find(root, text=text, rid=rid, contains=contains)
            if hit:
                return hit
        except Exception as e:  # uiautomator can blip mid-animation
            last_exc = e
        time.sleep(poll)
    raise TimeoutError(
        f"wait_for(text={text!r}, rid={rid!r}, contains={contains!r}) failed; last error: {last_exc}"
    )


def tap_node(serial: str, node: dict) -> None:
    x, y = bounds_center(node["bounds"])
    adb(serial, "shell", "input", "tap", str(x), str(y))


def tap_text(serial: str, text: str, timeout: float = 15.0) -> dict:
    node = wait_for(serial, text=text, timeout=timeout)
    tap_node(serial, node)
    return node


def current_focus(serial: str) -> str:
    out = adb(serial, "shell", "dumpsys", "window")
    for line in out.splitlines():
        if "mCurrentFocus" in line:
            return line.split("=", 1)[1].strip()
    return "?"


def screen_text(serial: str) -> str:
    root = dump(serial)
    lines = [n["text"] for n in nodes(root) if n["text"]]
    return "\n".join(lines)
