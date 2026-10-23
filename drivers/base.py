"""WalletOps — the uniform per-wallet interface for dry matrix testing.

Every wallet driver implements this, suites express flows against the
interface (parametrized over wallets x readers), and adding a wallet =
writing a driver that conforms here. Owner directive 2026-10-22: helpers
for wipe/create/send/receive/request so runs need zero LLM tokens.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class WalletOps(Protocol):
    id: str                 # matrix row id, e.g. "cashu_me"
    package: str            # android package
    serial: str             # adb serial

    # ---- lifecycle ----
    def wipe(self) -> None:
        """Factory reset (testnet wallets only — bench policy). Includes
        onboarding to a usable state + default mint configured."""

    def ensure_ready(self) -> None:
        """Idempotent: from ANY state (fresh install, wiped, degraded,
        mid-flow) to 'home with a mint configured'. Handles licenses,
        warnings, Nostr-degrade healing — the automation tax, paid here."""

    def add_mint(self, url: str) -> None:
        """Register a mint (idempotent)."""
        ...

    # ---- money ops (all return/expect amounts in sats) ----
    def balance_sats(self) -> int:
        ...

    def request_payment(self, amount_sats: int) -> str:
        """Arm an NFC request for amount; returns the wallet's status line.
        The wallet must present a Type-4 NDEF HCE (Numo protocol) while
        armed. Disarms when the screen is left."""
        ...
        ...

    def await_payment(self, timeout_s: float = 60) -> int:
        """Block until a payment lands (success screen / balance delta);
        returns credited sats. MUST NOT navigate (BACK disarms HCE)."""
        ...

    def send_payment_token(self, amount_sats: int) -> str:
        """Produce a spendable cashu token string of amount (mint+swap).
        Returns the token; caller delivers it (NFC write, browser-link...)."""
        ...

    # ---- introspection ----
    def screen_state(self) -> str:
        """Classifier: welcome|seed|mint_picker|home|sheet|request|settings|
        unknown — the conditional-driver core."""
        ...

    def is_armed(self) -> bool:
        """True while the NFC request is presenting."""
        ...
