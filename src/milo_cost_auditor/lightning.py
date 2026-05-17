"""
Lightning Network payment providers — the M2M-friendly side of x402/L402.

The PayPal path in payment.py requires Owner KYC (PayPal account is Orry's).
Lightning closes that loop autonomously:

  - LNBits public instances (legend.lnbits.com, demo.lnbits.com, etc.) let
    anyone create a wallet via POST /api/v1/wallet — no email, no KYC, no
    captcha. We get back invoice_key + admin_key, then mint BOLT-11 invoices
    via POST /api/v1/payments.

  - Alby Hub (self-hosted; Alby Cloud was sunset in 2024) speaks the same
    LNBits-style API surface, so AlbyProvider is a thin URL re-target of
    LNBitsProvider once you've stood one up.

Provider selection:
  MILO_LIGHTNING_PROVIDER=lnbits     (default — public LNBits, no setup)
  MILO_LIGHTNING_PROVIDER=alby       (self-hosted Alby Hub)
  MILO_LIGHTNING_PROVIDER=custom     (use MILO_LIGHTNING_BASE_URL + KEY env)

Env vars:
  MILO_LIGHTNING_BASE_URL    base URL (default https://demo.lnbits.com)
  MILO_LIGHTNING_INVOICE_KEY LNBits invoice key (required for invoice creation)
                             — get one free at https://demo.lnbits.com (no signup)
                             — or run our own LNBits instance for full sovereignty

Honest scope:
  - This module DOES NOT custody funds. LNBits/Alby holds the satoshis.
  - The "no KYC" claim is true for *Milo's* side — buyers still need an LN
    wallet (Alby browser, Phoenix, Wallet of Satoshi, Zeus, etc.).
  - We're using public LNBits as v0.2 bootstrap. v0.3 should run our own
    LNBits container (~10 min on Vercel/Fly/Railway, $0–5/mo).
"""

from __future__ import annotations

import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx


# ---- public dataclasses ---------------------------------------------------


@dataclass
class Invoice:
    """A Lightning invoice ready to be paid by any LN wallet."""

    payment_request: str          # BOLT-11 string ("lnbc...")
    payment_hash: str             # hex-encoded SHA256 of preimage
    amount_sats: int
    expires_at: float             # unix timestamp
    provider: str                 # "lnbits" / "alby" / "custom"
    memo: str = ""
    checking_id: Optional[str] = None  # provider-side handle (LNBits-specific)
    raw_response: Dict[str, Any] = field(default_factory=dict)

    def is_expired(self, now_ts: Optional[float] = None) -> bool:
        return (now_ts if now_ts is not None else time.time()) >= self.expires_at


@dataclass
class PaymentStatus:
    """Result of polling an invoice's payment state."""

    paid: bool
    payment_hash: str
    preimage: Optional[str] = None
    raw_response: Dict[str, Any] = field(default_factory=dict)


# ---- provider exceptions --------------------------------------------------


class LightningProviderError(RuntimeError):
    """Raised when an upstream Lightning provider returns a non-2xx response."""


class LightningProviderUnconfigured(RuntimeError):
    """Raised when required env vars (e.g. invoice key) are missing."""


# ---- abstract base --------------------------------------------------------


class LightningProvider(ABC):
    """Abstract LN invoice issuer + status checker."""

    name: str = "abstract"

    @abstractmethod
    def create_invoice(
        self,
        amount_sats: int,
        memo: str,
        expires_minutes: int = 60,
    ) -> Invoice:
        """Mint a BOLT-11 invoice. Raises on upstream error."""

    @abstractmethod
    def check_payment(self, payment_hash: str) -> PaymentStatus:
        """Poll for payment confirmation. Returns PaymentStatus."""


# ---- LNBits concrete provider --------------------------------------------


# Sane defaults: demo.lnbits.com is the canonical "try LNBits" instance.
# Operators wanting persistence should host their own LNBits or pick a
# long-lived community node (https://lnbits.com/instances).
DEFAULT_LNBITS_BASE_URL = "https://demo.lnbits.com"
HTTP_TIMEOUT_SECONDS = 15.0


class LNBitsProvider(LightningProvider):
    """LNBits-compatible HTTP provider (works with any LNBits-API server)."""

    name = "lnbits"

    def __init__(
        self,
        base_url: Optional[str] = None,
        invoice_key: Optional[str] = None,
        http_client: Optional[httpx.Client] = None,
    ) -> None:
        self.base_url = (
            base_url
            or os.environ.get("MILO_LIGHTNING_BASE_URL")
            or DEFAULT_LNBITS_BASE_URL
        ).rstrip("/")
        self.invoice_key = (
            invoice_key
            or os.environ.get("MILO_LIGHTNING_INVOICE_KEY")
            or ""
        )
        self._http = http_client  # injectable for tests
        # We intentionally allow invoice_key="" at construction so that
        # check_payment (which doesn't always need it) still works; only
        # create_invoice raises on missing key.

    # ---- internals --------------------------------------------------------

    def _client(self) -> httpx.Client:
        if self._http is not None:
            return self._http
        return httpx.Client(timeout=HTTP_TIMEOUT_SECONDS)

    def _post(self, path: str, json_body: Dict[str, Any]) -> Dict[str, Any]:
        if not self.invoice_key:
            raise LightningProviderUnconfigured(
                "MILO_LIGHTNING_INVOICE_KEY not set. Get a free invoice key at "
                f"{self.base_url} (no signup required) and export it."
            )
        url = f"{self.base_url}{path}"
        headers = {
            "X-Api-Key": self.invoice_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        client = self._client()
        try:
            resp = client.post(url, headers=headers, json=json_body)
        except httpx.HTTPError as exc:
            raise LightningProviderError(f"LNBits POST {path} failed: {exc}") from exc
        if resp.status_code >= 400:
            raise LightningProviderError(
                f"LNBits POST {path} -> HTTP {resp.status_code}: {resp.text[:300]}"
            )
        try:
            return resp.json()
        except ValueError as exc:
            raise LightningProviderError(
                f"LNBits POST {path} returned non-JSON: {resp.text[:200]}"
            ) from exc

    def _get(self, path: str, *, with_key: bool = False) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        headers: Dict[str, str] = {"Accept": "application/json"}
        if with_key and self.invoice_key:
            headers["X-Api-Key"] = self.invoice_key
        client = self._client()
        try:
            resp = client.get(url, headers=headers)
        except httpx.HTTPError as exc:
            raise LightningProviderError(f"LNBits GET {path} failed: {exc}") from exc
        if resp.status_code >= 400:
            raise LightningProviderError(
                f"LNBits GET {path} -> HTTP {resp.status_code}: {resp.text[:300]}"
            )
        try:
            return resp.json()
        except ValueError as exc:
            raise LightningProviderError(
                f"LNBits GET {path} returned non-JSON: {resp.text[:200]}"
            ) from exc

    # ---- public API -------------------------------------------------------

    def create_invoice(
        self,
        amount_sats: int,
        memo: str,
        expires_minutes: int = 60,
    ) -> Invoice:
        if not isinstance(amount_sats, int) or amount_sats <= 0:
            raise ValueError(f"amount_sats must be positive int, got {amount_sats!r}")
        if expires_minutes < 1 or expires_minutes > 60 * 24 * 7:
            raise ValueError(
                f"expires_minutes out of range [1, {60 * 24 * 7}]: {expires_minutes}"
            )
        # LNBits memo capped at ~640 chars by most upstreams; trim defensively.
        safe_memo = (memo or "")[:512]
        body = {
            "out": False,
            "amount": amount_sats,
            "unit": "sat",
            "memo": safe_memo,
            "expiry": expires_minutes * 60,
        }
        data = self._post("/api/v1/payments", body)
        # LNBits payload variants: "payment_request" or sometimes nested.
        pr = data.get("payment_request") or data.get("bolt11") or ""
        ph = data.get("payment_hash") or ""
        if not pr or not ph:
            raise LightningProviderError(
                f"LNBits response missing payment_request/payment_hash: {data}"
            )
        return Invoice(
            payment_request=pr,
            payment_hash=ph,
            amount_sats=amount_sats,
            expires_at=time.time() + (expires_minutes * 60),
            provider=self.name,
            memo=safe_memo,
            checking_id=data.get("checking_id"),
            raw_response=data,
        )

    def check_payment(self, payment_hash: str) -> PaymentStatus:
        if not payment_hash or not isinstance(payment_hash, str):
            raise ValueError("payment_hash must be a non-empty string")
        # Bound the hash length so a malformed input can't trigger a DoS URL.
        if len(payment_hash) > 128:
            raise ValueError("payment_hash too long (max 128 chars)")
        data = self._get(f"/api/v1/payments/{payment_hash}", with_key=True)
        return PaymentStatus(
            paid=bool(data.get("paid", False)),
            payment_hash=payment_hash,
            preimage=data.get("preimage"),
            raw_response=data,
        )


# ---- Alby concrete provider ----------------------------------------------


# Alby Hub exposes a Nostr Wallet Connect (NWC) interface natively but also
# ships an LNBits-compatible REST shim for backward compatibility. For our
# purposes (mint invoice + poll status) the LNBits adapter is sufficient.
DEFAULT_ALBY_BASE_URL = "https://api.getalby.com"  # placeholder; replace with hub URL


class AlbyProvider(LNBitsProvider):
    """Alby Hub provider — same wire shape as LNBits, different base URL.

    Configure via:
        MILO_LIGHTNING_PROVIDER=alby
        MILO_LIGHTNING_BASE_URL=https://<your-alby-hub-host>
        MILO_LIGHTNING_INVOICE_KEY=<invoice-key>
    """

    name = "alby"

    def __init__(
        self,
        base_url: Optional[str] = None,
        invoice_key: Optional[str] = None,
        http_client: Optional[httpx.Client] = None,
    ) -> None:
        super().__init__(
            base_url=base_url
            or os.environ.get("MILO_LIGHTNING_BASE_URL")
            or DEFAULT_ALBY_BASE_URL,
            invoice_key=invoice_key,
            http_client=http_client,
        )


# ---- factory --------------------------------------------------------------


_PROVIDERS: Dict[str, type[LightningProvider]] = {
    "lnbits": LNBitsProvider,
    "alby": AlbyProvider,
    "custom": LNBitsProvider,  # custom is just LNBits wire with overridden URL
}


def get_provider(
    name: Optional[str] = None,
    *,
    http_client: Optional[httpx.Client] = None,
) -> LightningProvider:
    """Return a Lightning provider; defaults to LNBits.

    Pass `http_client` for test injection.
    """
    selected = (name or os.environ.get("MILO_LIGHTNING_PROVIDER") or "lnbits").lower()
    cls = _PROVIDERS.get(selected)
    if cls is None:
        # Fail loud: misconfiguration shouldn't silently fall back to a
        # different provider than the operator asked for.
        raise ValueError(
            f"Unknown MILO_LIGHTNING_PROVIDER={selected!r}; "
            f"valid: {sorted(_PROVIDERS)}"
        )
    return cls(http_client=http_client)


# ---- USD <-> sats conversion ---------------------------------------------


# 2026-Q2 rate-of-thumb: ~$100k BTC -> 1 USD ≈ 1000 sats.
# v0.2: hardcoded constant (deterministic + offline).
# v0.3: pull live rate from coingecko/kraken with a 60s cache + 5% safety margin.
DEFAULT_USD_TO_SATS_RATE = 1000


def usd_to_sats(usd: float, *, rate: Optional[int] = None) -> int:
    """Convert USD to sats. Always rounds UP — never underbills the buyer."""
    if usd <= 0:
        raise ValueError(f"usd must be positive, got {usd}")
    rate_val = rate if rate is not None else DEFAULT_USD_TO_SATS_RATE
    # Round up so a $9.00 tier never quotes 8,999 sats due to float drift.
    return int(-(-(usd * rate_val) // 1))


def iso8601_utc(ts: float) -> str:
    """Format a unix timestamp as a Zulu ISO-8601 string."""
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
