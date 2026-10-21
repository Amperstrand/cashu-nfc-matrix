"""cashu.me v0.2.0 adb driver (FLAG_SECURE-safe: uiautomator text-bounds only).

UI geometry notes (v0.2.0, S20 FE 1080x2400 dumps):
- Action-tab labels ("Scan"/"Ecash"/"Tap", "Scan"/"Ecash"/"Bitcoin") render ~150px
  BELOW their clickable View — tapping the label text misses. tap_button_above()
  finds the label and taps the button strip above it.
- The Receive sheet's "Ecash" bottom button CREATES a fresh NUT-18 request and
  opens the request detail screen (QR + NFC arming).
- NFC arming needs: request with amount (not "Any") + default settlement mint.
  Armed state shows "Ask the sender to hold their phone near yours."
"""
from __future__ import annotations

import re
import time

from drivers import ui

LABEL_TO_BUTTON_DY = 156  # label center -> button center


class DriverError(RuntimeError):
    pass


class CashuMeDriver:
    package = "com.cashu.me"
    main_activity = "com.cashu.me/com.cashu.me.App.MainActivity"

    def __init__(self, serial: str = ui.DEFAULT_SERIAL):
        self.serial = serial

    # ---------- low-level helpers ----------

    def tap_button_above(self, label: str, timeout: float = 15.0) -> None:
        node = ui.wait_for(self.serial, text=label, timeout=timeout)
        x, y = ui.bounds_center(node["bounds"])
        ui.adb(self.serial, "shell", "input", "tap", str(x), str(y - LABEL_TO_BUTTON_DY))

    def focus(self) -> str:
        return ui.current_focus(self.serial)

    # ---------- device ----------

    def wake(self) -> None:
        ui.adb(self.serial, "shell", "input", "keyevent", "KEYCODE_WAKEUP")
        time.sleep(0.5)
        ui.adb(self.serial, "shell", "svc", "power", "stayon", "true")
        locked = ui.adb(self.serial, "shell", "dumpsys", "window")
        if "isKeyguardShowing=true" in locked:
            raise DriverError("device locked — HCE requires unlock; unlock manually")

    def launch(self) -> None:
        ui.adb(self.serial, "shell", "monkey", "-p", self.package,
               "-c", "android.intent.category.LAUNCHER", "1")
        time.sleep(3.0)
        # the app RESUMES its last screen (request detail, sheet, ...) —
        # normalize to the wallet home before doing anything else
        self.go_home()

    # ---------- navigation ----------

    def open_receive_sheet(self) -> None:
        """Wallet home -> Receive sheet (paste/scan/ecash/bitcoin). Self-heals
        from any foreign app state by relaunching."""
        try:
            self._open_receive_sheet_once()
        except DriverError:
            ui.adb(self.serial, "shell", "am", "force-stop", self.package)
            time.sleep(1.0)
            self.launch()
            self._open_receive_sheet_once()

    def _open_receive_sheet_once(self) -> None:
        n = ui.find(ui.dump(self.serial), text="Receive")
        if n is None:  # maybe already on sheet
            if ui.find(ui.dump(self.serial), text="Paste a Cashu token"):
                return
            raise DriverError("not on wallet home and not on receive sheet")
        ui.tap_node(self.serial, n)
        ui.wait_for(self.serial, text="Paste a Cashu token", timeout=10)

    def ensure_requestable(self) -> None:
        """Recover the app's degraded Nostr runtime state.

        Observed on the bench: after sustained relay-connection failures (the
        bench AP blocks the default Nostr relays), the Receive sheet's Ecash
        path fails with 'Nostr isn't ready — check your relays in Settings.'
        Config is actually fine (relays + keys present); the runtime service
        state is what degraded, and it re-initializes when the Nostr settings
        screen resumes. This drives that round-trip once.
        """
        import time

        from drivers import ui

        ui.adb(self.serial, "shell", "input", "keyevent", "KEYCODE_BACK")
        time.sleep(1.0)
        self.go_home()
        ui.adb(self.serial, "shell", "input", "tap", "120", "184")  # top-left settings
        ui.wait_for(self.serial, text="Nostr", timeout=12)
        ui.tap_text(self.serial, "Nostr", timeout=8)
        ui.wait_for(self.serial, contains="RELAYS", timeout=12)
        ui.adb(self.serial, "shell", "input", "keyevent", "KEYCODE_BACK")
        time.sleep(0.8)
        ui.adb(self.serial, "shell", "input", "keyevent", "KEYCODE_BACK")
        time.sleep(0.8)

    def create_request(self, amount: int | None) -> str:
        """Receive sheet -> new NUT-18 request. Set amount via picker if given.

        Returns the NFC status line shown once armed/needs-amount.
        Self-heals one 'Nostr isn't ready' degradation via ensure_requestable().
        """
        try:
            return self._create_request_once(amount)
        except (TimeoutError, DriverError):
            self.ensure_requestable()
            return self._create_request_once(amount)

    def _create_request_once(self, amount: int | None) -> str:
        self.open_receive_sheet()
        # fast-fail detection: the degraded sheet shows the Nostr banner and
        # the request screen never opens
        sheet = ui.screen_text(self.serial)
        if "Nostr isn't ready" in sheet:
            raise DriverError("nostr degraded (sheet banner)")
        self.tap_button_above("Ecash")
        ui.wait_for(self.serial, text="Mint", timeout=15)
        if amount is not None:
            any_node = ui.wait_for(self.serial, text="Any", timeout=10)
            ui.tap_node(self.serial, any_node)
            ui.wait_for(self.serial, text="Done", timeout=10)
            for digit in str(amount):
                ui.tap_text(self.serial, digit, timeout=8)
                time.sleep(0.25)
            ui.tap_text(self.serial, "Done", timeout=8)
            time.sleep(1.0)
        return self.nfc_status()

    def nfc_status(self) -> str:
        """First status line of the request screen (NFC phase hint)."""
        for probe in ("Ask the sender", "Set an amount", "Waiting for payment",
                      "Turn on NFC", "isn't available"):
            n = ui.find(ui.dump(self.serial), contains=probe)
            if n:
                return n["text"]
        return ""

    def is_armed(self) -> bool:
        return "Ask the sender" in self.nfc_status()

    # ---------- wallet ----------

    def go_home(self) -> None:
        for _ in range(6):
            txt = ui.screen_text(self.serial)
            if "View all activity" in txt or ("Testnut mint" in txt and "Receive" in txt):
                return
            # anything else (sheet, request detail, settings, chooser): back out
            ui.adb(self.serial, "shell", "input", "keyevent", "KEYCODE_BACK")
            time.sleep(1.2)
        raise DriverError(f"cannot find wallet home; focus={self.focus()}")

    def balance_sats(self) -> int:
        """Total balance off the wallet home ('₿10,009')."""
        self.go_home()
        for n in ui.nodes(ui.dump(self.serial)):
            m = re.match(r"[₿\s]*([\d,]+)$", n["text"].strip())
            if m and len(m.group(1)) >= 2:
                return int(m.group(1).replace(",", ""))
        raise DriverError("balance text not found")

    def balance_by_mint(self) -> dict[str, int]:
        self.go_home()
        out: dict[str, int] = {}
        ns = ui.nodes(ui.dump(self.serial))
        for i, n in enumerate(ns):
            if n["text"].endswith("mint") or "Testnut" in n["text"]:
                for m in ns[i + 1:]:
                    mm = re.match(r"[₿\s]*([\d,]+)$", m["text"].strip())
                    if mm:
                        out[n["text"]] = int(mm.group(1).replace(",", ""))
                        break
        return out
