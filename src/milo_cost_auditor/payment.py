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


class KeyValidation(BaseModel):
    """Result of validating a pro_key."""

    valid: bool
    tier: Optional[str] = None
    expires_at: Optional[str] = None
    reason: Optional[str] = None


# ---- env / secret handling ------------------------------------------------


_DEV_KEY = "milo-cost-auditor-dev-only-DO-NOT-USE-IN-PROD"


def _get_hmac_secret() -> bytes:
    """Return the HMAC secret. Falls back to dev key with a warning."""
    secret = os.environ.get("MILO_COST_AUDITOR_HMAC_KEY")
    if secret:
        return secret.encode("utf-8")
    # Dev-mode fallback. Anything signed with this key will validate ONLY when
    # the same dev key is in use — i.e. it won't accidentally validate a
    # production key. The warning is emitted at server boot in server.py.
    return _DEV_KEY.encode("utf-8")


def is_dev_mode() -> bool:
    """True when no MILO_COST_AUDITOR_HMAC_KEY is set."""
    return not os.environ.get("MILO_COST_AUDITOR_HMAC_KEY")


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
    parts = token.split(".")
    if len(parts) != 2:
        return KeyValidation(valid=False, reason="malformed_token")
    payload_b64, sig = parts
    secret = _get_hmac_secret()
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
