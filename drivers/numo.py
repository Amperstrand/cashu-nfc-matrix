"""Numo v1.9 PoS driver (bench S20, uiautomator text-bounds only).

Keypad -> amount -> Charge -> 'Pay <amt> sat / Scan or Tap to Pay /
Waiting for payment...' (HCE armed).
"""
from __future__ import annotations

import time

from drivers import ui


class NumoDriver:
    package = "com.electricdreams.numo"

    def __init__(self, serial: str = ui.DEFAULT_SERIAL):
        self.serial = serial

    def launch(self) -> None:
        ui.launch_app(self.serial, self.package)
        # onboarding guard: if the wallet-setup flow shows, run through it
        # (fresh-install only; leaves default mint, zero funds)
        time.sleep(4)
        self._finish_onboarding_if_present()
        ui.wait_for(self.serial, contains="Charge", timeout=25)

    def _finish_onboarding_if_present(self) -> None:
        for _ in range(8):
            root = ui.dump(self.serial)
            txt = [n["text"] for n in ui.nodes(root) if n["text"]]
            if any("Charge" in t for t in txt):
                return
            for label in ("Get started", "Create New Wallet", "Continue", "Skip", "Dismiss"):
                n = ui.find(root, text=label)
                if n:
                    ui.tap_node(self.serial, n)
                    time.sleep(2.0)
                    break
            else:
                break

    def charge(self, amount: int) -> str:
        """Type amount on keypad and hit Charge. Returns pay-screen status."""
        for digit in str(amount):
            ui.tap_text(self.serial, digit, timeout=8)
            time.sleep(0.25)
        ui.tap_text(self.serial, "Charge", timeout=8)
        return ui.wait_for(self.serial, contains="Waiting for payment", timeout=15)["text"]

    def is_armed(self) -> bool:
        root = ui.dump(self.serial)
        return ui.find(root, contains="Waiting for payment") is not None

    def screen(self) -> str:
        return ui.screen_text(self.serial)
