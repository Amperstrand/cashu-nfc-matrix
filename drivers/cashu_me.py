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
from pathlib import Path
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
        ui.launch_app(self.serial, self.package)
        time.sleep(3.0)
        # the app RESUMES its last screen (request detail, sheet, ...) —
        # normalize to the wallet home before doing anything else
        self.go_home()

    # ---------- navigation ----------

    def open_receive_sheet(self) -> None:
        """Wallet home -> Receive sheet (paste/scan/ecash/bitcoin). Prefers
        graceful BACK navigation out of whatever screen is up; force-stop +
        relaunch only as the last resort (process death makes the HCE service
        rebind racily for tens of seconds)."""
        try:
            self._to_wallet_home_graceful()
            self._open_receive_sheet_once()
        except (DriverError, TimeoutError):
            ui.adb(self.serial, "shell", "am", "force-stop", self.package)
            time.sleep(1.0)
            self.launch()
            self._open_receive_sheet_once()

    def _to_wallet_home_graceful(self) -> None:
        import time as _t

        for _ in range(3):
            root = ui.dump(self.serial)
            if ui.find(root, text="Receive"):
                return
            # request detail / sheet / anything app-internal: BACK out
            ui.adb(self.serial, "shell", "input", "keyevent", "KEYCODE_BACK")
            _t.sleep(1.0)
        raise DriverError("not on a screen that backs out to wallet home")

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

    # ---------- screen classification (conditional driver core) ----------
    #
    # The app is driven by STATE, not by fixed scripts: every entry point
    # classifies the current screen and routes. This survives app versions
    # with/without the mint picker, mintless fresh wallets, and resumes.

    def screen_state(self) -> str:
        """One of: welcome|seed|mint_picker|home|sheet|request|settings|unknown."""
        txt = ui.screen_text(self.serial)
        if "Create Wallet" in txt or "Restore Wallet" in txt:
            return "welcome"
        if "Tap to reveal" in txt or "Seed" in txt.split("\n")[0]:
            return "seed"
        if "first mint" in txt:
            return "mint_picker"
        if "Paste a Cashu token" in txt:
            return "sheet"
        if "Cashu Request" in txt or "Ask the sender" in txt or "Set an amount" in txt:
            return "request"
        if "DISPLAY" in txt or "Backup & Restore" in txt:
            return "settings"
        if ("View all activity" in txt) or ("Receive" in txt and "Send" in txt
                                            and "History" in txt):
            return "home"
        return "unknown"

    def _await_state(self, timeout: float = 8.0) -> str:
        """Wait for the UI to settle into a classified state (transitions
        read as 'unknown' for a second or two — acting on them BACKs into
        the wrong place)."""
        deadline = time.monotonic() + timeout
        state = "unknown"
        while time.monotonic() < deadline:
            state = self.screen_state()
            if state != "unknown":
                return state
            time.sleep(0.8)
        return state

    def ensure_onboarded(self, prefer_mint: str | None = None) -> None:
        """Drive from ANY state to a usable wallet. If the mint picker shows
        and prefer_mint is given, use the picker's custom-URL flow; otherwise
        Skip (the mint can be added later via add_mint)."""
        for _ in range(10):
            state = self._await_state()
            if state == "home":
                return
            if state == "welcome":
                ui.tap_text(self.serial, "Create Wallet", timeout=10)
                time.sleep(2.5)
            elif state == "seed":
                ui.tap_text(self.serial, "Tap to reveal", timeout=10)
                time.sleep(1.5)
                row = ui.wait_for(self.serial,
                                  contains="written down my seed phrase", timeout=10)
                x, y = ui.bounds_center(row["bounds"])
                ui.adb(self.serial, "shell", "input", "tap", str(x), str(y))
                time.sleep(1.0)
                ui.tap_text(self.serial, "I've Saved My Seed Phrase", timeout=10)
                time.sleep(2.5)
            elif state == "mint_picker":
                if prefer_mint:
                    try:
                        self._picker_add_mint(prefer_mint)
                        continue
                    except (TimeoutError, DriverError):
                        pass  # fall through to Skip; add_mint() recovers later
                ui.tap_text(self.serial, "Skip for now", timeout=10)
                time.sleep(4)
            elif state in ("sheet", "request", "settings", "unknown"):
                ui.adb(self.serial, "shell", "input", "keyevent", "KEYCODE_BACK")
                time.sleep(1.2)
        if self.screen_state() != "home":
            raise DriverError(f"ensure_onboarded stuck in {self.screen_state()}")

    def _picker_add_mint(self, url: str) -> None:
        """In-onboarding mint picker custom-URL flow (fragile geometry:
        the row's ADD control sits at the right edge, x~924)."""
        ui.wait_for(self.serial, contains="Add custom", timeout=15)
        ui.tap_text(self.serial, "Add custom mint URL", timeout=10)
        time.sleep(1.5)
        e = ui.find(ui.dump(self.serial), cls="EditText")
        if e is None:
            raise DriverError("picker URL field not found")
        ui.tap_node(self.serial, e)
        time.sleep(0.6)
        ui.adb(self.serial, "shell", "input", "text", url.replace(" ", "%s"))
        time.sleep(1.0)
        row = ui.wait_for(self.serial, text=url, timeout=10)
        _, y = ui.bounds_center(row["bounds"])
        ui.adb(self.serial, "shell", "input", "tap", "924", str(y))
        time.sleep(2.5)
        ui.tap_text(self.serial, "Continue", timeout=10)
        time.sleep(4)

    # ---------- WalletOps conformance ----------
    id = "cashu_me"

    def ensure_ready(self) -> None:
        """Idempotent any-state -> usable wallet (onboarding, mint, Nostr
        heal). WalletOps interface (drivers/base.py)."""
        self.ensure_onboarded(prefer_mint="https://testnut.cashu.space")
        txt = ui.screen_text(self.serial)
        if "Testnut" not in txt:
            self.add_mint("https://testnut.cashu.space")

    def request_payment(self, amount_sats: int) -> str:
        return self.create_request(amount_sats)

    def await_payment(self, timeout_s: float = 60) -> int:
        """Watch the request screen WITHOUT navigation; returns credited
        sats (amount minus 1-sat input fee at current testnut keysets)."""
        bal0 = None
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            txt = ui.screen_text(self.serial)
            if "Payment received" in txt:
                break
            if "failed" in txt.lower():
                raise DriverError(f"wallet rejected payment: {txt[:200]}")
            time.sleep(3)
        else:
            raise DriverError("no success screen before timeout")
        time.sleep(2)
        for _ in range(8):
            try:
                return self.balance_sats()
            except DriverError:
                time.sleep(2)
        raise DriverError("balance unreadable after success")

    def send_payment_token(self, amount_sats: int) -> str:
        """Mint a fresh spendable token via the rig (bench/mint_token.sh)."""
        import subprocess

        out = f"/tmp/walletops-token-{amount_sats}.txt"
        r = subprocess.run(
            ["bash", "bench/mint_token.sh", out, str(amount_sats)],
            capture_output=True, text=True, timeout=300, cwd=str(Path(__file__).resolve().parent.parent),
        )
        if r.returncode != 0:
            raise DriverError(f"mint failed: {r.stdout[-150:]}")
        return open(out).read().strip()

    # ---------- wallet lifecycle ----------

    def wipe(self, setup_mint: str | None = "https://testnut.cashu.space") -> None:
        """Factory-reset the bench wallet (testnet-only by bench policy).

        pm clear -> onboarding -> (conditional) first mint. Works with or
        without the mint picker; if the picker's custom-URL flow fails, the
        wallet is left mintless and setup continues via add_mint().
        """
        ui.adb(self.serial, "shell", "pm", "clear", self.package)
        time.sleep(1.5)
        ui.launch_app(self.serial, self.package)
        time.sleep(4)
        self.ensure_onboarded(prefer_mint=setup_mint)
        if setup_mint and self.screen_state() == "home":
            # picker skipped or absent — ensure the mint exists via Mints screen
            try:
                self.add_mint(setup_mint)
            except (TimeoutError, DriverError):
                # mint may already be there (picker path succeeded)
                if "Testnut" not in ui.screen_text(self.serial):
                    raise

    def add_mint(self, url: str) -> None:
        """Mints screen -> Add mint -> url. No-op-friendly: state-routed."""
        for _ in range(4):
            state = self.screen_state()
            if state == "mint_picker":
                self._picker_add_mint(url)
                return
            if state == "home":
                break
            ui.adb(self.serial, "shell", "input", "keyevent", "KEYCODE_BACK")
            time.sleep(1.0)
        ui.adb(self.serial, "shell", "input", "tap", "908", "2092")  # Mints nav
        ui.wait_for(self.serial, text="Add mint", timeout=15)
        ui.tap_text(self.serial, "Add mint", timeout=10)
        time.sleep(1.5)
        e = ui.find(ui.dump(self.serial), cls="EditText")
        if e is None:
            raise DriverError("add-mint URL field not found")
        ui.tap_node(self.serial, e)
        time.sleep(0.5)
        ui.adb(self.serial, "shell", "input", "text", url.replace(" ", "%s"))
        time.sleep(0.8)
        for label in ("Add", "Add mint", "Connect", "Continue"):
            m = ui.find(ui.dump(self.serial), text=label)
            if m:
                ui.tap_node(self.serial, m)
                break
        time.sleep(3)

    def go_home(self) -> None:
        for _ in range(6):
            focus = self.focus()
            if "launcher" in focus.lower():
                ui.launch_app(self.serial, self.package)  # BACKed out — return
                time.sleep(3.0)
                continue
            if self.screen_state() == "home":
                return
            ui.adb(self.serial, "shell", "input", "keyevent", "KEYCODE_BACK")
            time.sleep(1.2)
        raise DriverError(f"cannot find wallet home; focus={self.focus()}")

    def balance_sats(self) -> int:
        """Total balance off the wallet home ('₿10,009' / fresh '₿0')."""
        self.go_home()
        cands = []
        for n in ui.nodes(ui.dump(self.serial)):
            m = re.match(r"[₿\s]*([\d,]+)$", n["text"].strip())
            if m:
                cands.append(int(m.group(1).replace(",", "")))
        if cands:
            return max(cands)  # balance row dominates stray counters
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
