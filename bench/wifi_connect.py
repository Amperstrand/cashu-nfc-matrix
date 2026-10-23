#!/usr/bin/python3
"""Connect the bench phone to the LAB wifi (SSID '2', 192.168.13.0/24).

Why: the tollgate AP filters egress (Nostr relays, minibits.cash, and
silently degrades wallet POSTs); every HIL run must start from lab wifi.

The PSK is read live from the host's NetworkManager profile '2' and is never
printed or stored. Run on the bench host as root.
"""
import subprocess
import sys
import time

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent / "drivers"))
APK_DIR = __import__("os").environ.get(
    "WALLET_APK_DIR", str(__import__("pathlib").Path.home() / "src" / "wallet-matrix-apks"))
import ui  # noqa: E402

S = ui.DEFAULT_SERIAL


def psk() -> str:
    out = subprocess.run(
        ["nmcli", "-s", "-g", "802-11-wireless-security.psk", "con", "show", "2"],
        capture_output=True, text=True,
    ).stdout.strip()
    if not out:
        raise SystemExit("no psk in NetworkManager profile '2'")
    return out


def on_lab_wifi() -> bool:
    out = subprocess.run(
        ["adb", "-s", S, "shell", "ip", "addr", "show", "wlan0"],
        capture_output=True, text=True, timeout=30,
    ).stdout
    return "192.168.13." in out


def main() -> int:
    if on_lab_wifi():
        print("already on lab wifi")
        return 0
    ui.adb(S, "shell", "input", "keyevent", "KEYCODE_WAKEUP")
    ui.adb(S, "shell", "am", "start", "-a", "android.settings.WIFI_SETTINGS")
    time.sleep(2.5)
    n = ui.wait_for(S, text="2", timeout=15)
    x, y = ui.bounds_center(n["bounds"])
    ui.adb(S, "shell", "input", "tap", "760", str(y))
    time.sleep(2.5)
    txt = ui.screen_text(S)
    if "Enter password" in txt or "Password" in txt:
        ui.adb(S, "shell", "input", "text", psk().replace(" ", "%s"))
        time.sleep(0.8)
        ui.tap_text(S, "Connect", timeout=8)
        time.sleep(7)
    print("connected:", on_lab_wifi(), "|", ui.screen_text(S)[:150].replace("\n", " | "))
    return 0 if on_lab_wifi() else 1


if __name__ == "__main__":
    sys.exit(main())
