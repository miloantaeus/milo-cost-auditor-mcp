"""
x402-pattern payment + HMAC pro_key validation.

This module does NOT process payments. It:
  1. Issues a structured 402 Payment Required response with PayPal storefront URL.
  2. Validates a signed pro_key (HMAC-SHA256 over {tier, expires_at}).

The actual money handling happens on store-v2-khaki.vercel.app via Milo's
existing PayPal direct-buy buttons. After purchase, the customer's email
receives a pro_key blob they paste into Claude Code / Cursor as the
MILO_COST_AUDITOR_PRO_KEY env var.

Key format:
    <base64(json({tier, expires_at}))>.<hex(HMAC-SHA256(payload, secret))>

Time is treated as ISO-8601 UTC (Zulu) strings.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Dict, Optional

from pydantic import BaseModel, Field


# ---- pricing tiers (hardcoded) --------------------------------------------

TIERS: Dict[str, Dict[str, object]] = {
    "starter": {
        "price_usd_monthly": 9,
        "audits_per_month": 15,
        "label": "Starter",
        "paypal_button": "https://store-v2-khaki.vercel.app/products/cost-auditor-starter",
    },
    "team": {
        "price_usd_monthly": 29,
        "audits_per_month": None,  # unlimited
        "label": "Team",
        "paypal_button": "https://store-v2-khaki.vercel.app/products/cost-auditor-team",
    },
    "org": {
        "price_usd_monthly": 99,
        "audits_per_month": None,
        "label": "Org",
        "paypal_button": "https://store-v2-khaki.vercel.app/products/cost-auditor-org",
        "extras": "custom routing rules + per-team dashboards",
    },
    # BOT-ONLY TIER (gap-20260517-bot-only-pro-key-tier-experiment).
    # Lightning-only, 50% off PayPal Starter. Segments demand cleanly:
    # only agents (or devs wearing agent hats) hit the LN endpoint.
    # 30-day kill criterion: 0 LN settlements at $4.50 → agent-payment market
    # doesn't exist for this niche → self-deprecate per market-truth doctrine.
    # 1+ settlement → proof of agent-payment thesis → reinvest in M2M tier.
    "starter_lightning_only": {
        "price_usd_monthly": 4.5,
        "audits_per_month": 15,
        "label": "Starter (Lightning-only — 50% off, bot-friendly)",
        "paypal_button": None,  # explicitly NO PayPal path
        "rail": "lightning_only",
        "experiment_kill_criterion_days": 30,
        "experiment_kill_threshold_settlements": 0,
        "note": (
            "50% off the PayPal-Starter tier. Pay in sats only via Lightning Network. "
            "Designed for M2M payments: agents paying agents. No KYC on either side. "
            "30-day experiment — see CHANGELOG / gap-20260517-bot-only-pro-key-tier-experiment."
        ),
    },
}


# ---- public schemas --------------------------------------------------------


class PaymentRequest(BaseModel):
    """x402-style payment request returned when pro_key is missing or invalid."""

    http_status: int = 402
    error: str = "Payment Required"
    message: str
    amount_usd: float
    currency: str = "USD"
    tier: str
    payment_url: str
    pro_key_format: str = (
        "<base64(json({tier, expires_at}))>.<hex(HMAC-SHA256(payload, secret))>"
    )
    instructions: str


class LightningPaymentOption(BaseModel):
    """Lightning Network payment leg of a dual payment request.

    L402-style: pay the BOLT-11 invoice with any LN wallet, then poll
    /api/v1/payments/<hash> until paid=true. The watcher CLI auto-issues
    the pro_key and returns it on the same MCP turn (no email roundtrip).
    """

    rail: str = "lightning"
    amount_sats: int
    bolt11: str
    payment_hash: str
    expires_at: str  # ISO-8601 Zulu
    provider: str  # "lnbits" / "alby" / "custom"
    memo: str
    instructions: str
    poll_endpoint_hint: str = (
        "Run `milo-cost-auditor-lightning-payment-watcher --once` to claim a "
        "pro_key as soon as the invoice settles."
    )


class DualPaymentRequest(BaseModel):
    """Both payment rails surfaced to the buyer.

    `lightning` is None when LN provider isn't configured — callers should
    fall back to the PayPal `legacy_paypal` leg.
    """

    tier: str
    amount_usd: float
    legacy_paypal: PaymentRequest
    lightning: Optional["LightningPaymentOption"] = None
    preferred_rail: str = "lightning"  # nudge agents to the M2M-friendly path
    notes: str = (
        "Two payment rails offered. Lightning is faster, cheaper, and requires "
        "no KYC on either side (agents can pay agents). PayPal is the legacy "
        "human-buyer path; needs an Owner-managed PayPal account."
    )


class KeyValidation(BaseModel):
    """Result of validating a pro_key."""

    valid: bool
    tier: Optional[str] = None
    expires_at: Optional[str] = None
    reason: Optional[str] = None


# ---- env / secret handling ------------------------------------------------


# SECURITY HARDENING (per Gemini security audit 2026-05-17):
# 1. CRITICAL: Silent dev-key fallback in production = anyone can forge
#    pro_keys with the publicly-visible dev key. Fixed by requiring
#    explicit MILO_COST_AUDITOR_DEV_MODE=1 to allow dev key.
# 2. HIGH: Static dev key replaced with per-process random — even in
#    dev mode, the key changes between server restarts (forces tests/clients
#    to be aware of dev-mode rather than silently relying on a known string).
import secrets as _secrets

# Per-process random dev key; not a constant. Tests can override via secret param.
# Stored as bytes since hmac.new() requires bytes for the key parameter.
_DEV_KEY = _secrets.token_hex(32).encode("utf-8")


class MissingProductionSecret(RuntimeError):
    """Raised when a production HMAC secret is required but not set."""


def _get_hmac_secret() -> bytes:
    """Return the HMAC secret.

    Production: requires MILO_COST_AUDITOR_HMAC_KEY env var (32+ random hex).
    Dev mode: requires MILO_COST_AUDITOR_DEV_MODE=1 to explicitly opt in;
              uses per-process random _DEV_KEY (changes on each server restart).
    """
    secret = os.environ.get("MILO_COST_AUDITOR_HMAC_KEY")
    if secret:
        return secret.encode("utf-8")
    # Fail-secure: refuse dev key unless explicitly enabled.
    if os.environ.get("MILO_COST_AUDITOR_DEV_MODE") == "1":
        return _DEV_KEY
    raise MissingProductionSecret(
        "MILO_COST_AUDITOR_HMAC_KEY not set. Production refuses dev fallback. "
        "For local development, set MILO_COST_AUDITOR_DEV_MODE=1 (per-process "
        "random dev key will be used)."
    )


def is_dev_mode() -> bool:
    """True when no MILO_COST_AUDITOR_HMAC_KEY is set AND dev mode is enabled."""
    return (
        not os.environ.get("MILO_COST_AUDITOR_HMAC_KEY")
        and os.environ.get("MILO_COST_AUDITOR_DEV_MODE") == "1"
    )


# ---- key issue + verify ---------------------------------------------------


def issue_pro_key(tier: str, expires_at_iso: str, secret: Optional[bytes] = None) -> str:
    """Mint a pro_key (mostly used by tests + storefront fulfillment script)."""
    if tier not in TIERS:
        raise ValueError(f"unknown tier: {tier!r}; valid: {list(TIERS)}")
    payload = {"tier": tier, "expires_at": expires_at_iso}
    payload_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload_bytes).rstrip(b"=").decode("ascii")
    sec = secret if secret is not None else _get_hmac_secret()
    sig = hmac.new(sec, payload_b64.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"


def validate_pro_key(token: Optional[str], *, now_ts: Optional[float] = None) -> KeyValidation:
    """Validate a pro_key. Returns KeyValidation."""
    if not token or not isinstance(token, str):
        return KeyValidation(valid=False, reason="missing_token")
    # SECURITY: bound the token length to prevent DoS via massive HMAC inputs
    # (per Gemini security audit 2026-05-17). Legitimate keys are <512 chars.
    if len(token) > 1024:
        return KeyValidation(valid=False, reason="token_too_large")
    parts = token.split(".")
    if len(parts) != 2:
        return KeyValidation(valid=False, reason="malformed_token")
    payload_b64, sig = parts
    # SECURITY: catch non-ASCII gracefully instead of crashing server.
    try:
        payload_b64_bytes = payload_b64.encode("ascii")
        sig.encode("ascii")  # also validate sig is ascii-safe
    except UnicodeEncodeError:
        return KeyValidation(valid=False, reason="malformed_token")
    try:
        secret = _get_hmac_secret()
    except MissingProductionSecret:
        # Production secret unconfigured: refuse all validations.
        # This is fail-secure — better to reject all than silently allow forgeries.
        return KeyValidation(valid=False, reason="server_missing_production_secret")
    expected_sig = hmac.new(secret, payload_b64.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_sig, sig):
        return KeyValidation(valid=False, reason="bad_signature")
    # decode payload (pad b64)
    try:
        pad = "=" * (-len(payload_b64) % 4)
        payload_bytes = base64.urlsafe_b64decode(payload_b64 + pad)
        payload = json.loads(payload_bytes)
    except Exception:
        return KeyValidation(valid=False, reason="payload_decode_failed")
    tier = payload.get("tier")
    expires_at_iso = payload.get("expires_at")
    if tier not in TIERS:
        return KeyValidation(valid=False, reason="unknown_tier")
    if not expires_at_iso:
        return KeyValidation(valid=False, reason="missing_expiry")
    # parse expiry
    try:
        exp_struct = _parse_iso8601_utc(expires_at_iso)
    except ValueError:
        return KeyValidation(valid=False, reason="bad_expiry_format")
    current = now_ts if now_ts is not None else time.time()
    if exp_struct < current:
        return KeyValidation(
            valid=False,
            tier=tier,
            expires_at=expires_at_iso,
            reason="expired",
        )
    return KeyValidation(
        valid=True,
        tier=tier,
        expires_at=expires_at_iso,
        reason=None,
    )


def _parse_iso8601_utc(iso: str) -> float:
    """Parse a Zulu ISO-8601 string into a unix timestamp."""
    s = iso.strip()
    # Accept both "2026-12-31T23:59:59Z" and "2026-12-31T23:59:59+00:00"
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    from datetime import datetime
    return datetime.fromisoformat(s).timestamp()


# ---- payment request builder ---------------------------------------------


def build_payment_request(tier: str = "starter") -> PaymentRequest:
    """Build a 402 Payment Required payload for the requested tier."""
    if tier not in TIERS:
        tier = "starter"
    t = TIERS[tier]
    return PaymentRequest(
        message=(
            f"This is a pro tool. Pick the {t['label']} tier "
            f"(${t['price_usd_monthly']}/mo) on the storefront, "
            "then set MILO_COST_AUDITOR_PRO_KEY in your shell."
        ),
        amount_usd=float(t["price_usd_monthly"]),  # type: ignore[arg-type]
        tier=tier,
        payment_url=str(t["paypal_button"]),
        instructions=(
            "1. Open the payment_url and complete checkout. "
            "2. You'll receive an emailed pro_key — copy the full token. "
            "3. export MILO_COST_AUDITOR_PRO_KEY='<token>' in the shell that runs your "
            "MCP client. 4. Re-run get_pro_report; the key is verified locally — "
            "no callback to my server is required."
        ),
    )


# ---- dual-rail payment (PayPal + Lightning) ------------------------------


def tier_amount_sats(tier: str, *, rate: Optional[int] = None) -> int:
    """Sat amount for a tier at the configured USD->sats rate."""
    from milo_cost_auditor import lightning as _ln
    if tier not in TIERS:
        tier = "starter"
    usd = float(TIERS[tier]["price_usd_monthly"])  # type: ignore[arg-type]
    return _ln.usd_to_sats(usd, rate=rate)


def build_dual_payment_request(
    tier: str = "starter",
    *,
    lightning_provider: Optional[object] = None,
    enable_lightning: bool = True,
    invoice_memo: Optional[str] = None,
    expires_minutes: int = 60,
) -> "DualPaymentRequest":
    """Build a dual-rail payment request: PayPal (legacy) + Lightning (M2M).

    If Lightning provider creation or invoice minting fails for ANY reason
    (env unset, network down, upstream 5xx), we still return a valid
    DualPaymentRequest with lightning=None — the PayPal rail must always
    work as a fallback.
    """
    if tier not in TIERS:
        tier = "starter"
    paypal_leg = build_payment_request(tier)

    if not enable_lightning:
        return DualPaymentRequest(
            tier=tier,
            amount_usd=paypal_leg.amount_usd,
            legacy_paypal=paypal_leg,
            lightning=None,
            preferred_rail="paypal",
        )

    from milo_cost_auditor import lightning as _ln
    try:
        provider = lightning_provider or _ln.get_provider()
        amount_sats = tier_amount_sats(tier)
        memo = invoice_memo or f"milo-cost-auditor {tier} ({paypal_leg.amount_usd:g} USD)"
        invoice = provider.create_invoice(  # type: ignore[union-attr]
            amount_sats=amount_sats,
            memo=memo,
            expires_minutes=expires_minutes,
        )
        # Persist in the local ledger so the watcher can poll for settlement.
        # Best-effort: a ledger write failure must not block returning the
        # invoice to the buyer (they can still pay; manual reconciliation works).
        try:
            from milo_cost_auditor import lightning_ledger as _ledger
            _ledger.record_invoice(
                payment_hash=invoice.payment_hash,
                amount_sats=invoice.amount_sats,
                tier=tier,
                bolt11=invoice.payment_request,
                memo=invoice.memo,
                provider=invoice.provider,
            )
        except Exception as _e:  # noqa: BLE001
            import sys as _sys
            _sys.stderr.write(f"# lightning ledger write failed: {_e}\n")
        ln_option = LightningPaymentOption(
            amount_sats=invoice.amount_sats,
            bolt11=invoice.payment_request,
            payment_hash=invoice.payment_hash,
            expires_at=_ln.iso8601_utc(invoice.expires_at),
            provider=invoice.provider,
            memo=invoice.memo,
            instructions=(
                "1. Open the bolt11 invoice in any LN wallet (Alby, Phoenix, "
                "Wallet of Satoshi, Zeus, etc.). 2. Pay the invoice. "
                "3. Re-run get_pro_report with the same payment_hash, OR run "
                "`milo-cost-auditor-lightning-payment-watcher --once` to claim "
                "the pro_key. No KYC, no PayPal account, no email roundtrip."
            ),
        )
        return DualPaymentRequest(
            tier=tier,
            amount_usd=paypal_leg.amount_usd,
            legacy_paypal=paypal_leg,
            lightning=ln_option,
            preferred_rail="lightning",
        )
    except Exception as exc:  # noqa: BLE001 — provider can raise anything
        # Log nothing to stdout (would pollute MCP stream). Return PayPal-only.
        import sys as _sys
        _sys.stderr.write(
            f"# lightning rail unavailable, falling back to PayPal-only: "
            f"{type(exc).__name__}: {exc}\n"
        )
        return DualPaymentRequest(
            tier=tier,
            amount_usd=paypal_leg.amount_usd,
            legacy_paypal=paypal_leg,
            lightning=None,
            preferred_rail="paypal",
        )
