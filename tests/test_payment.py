"""Tests for x402 payment + HMAC key validation."""

from __future__ import annotations

import os
import time

import pytest

from milo_cost_auditor import payment


def test_issue_and_validate_roundtrip() -> None:
    token = payment.issue_pro_key("starter", "2099-01-01T00:00:00Z")
    v = payment.validate_pro_key(token)
    assert v.valid is True
    assert v.tier == "starter"
    assert v.expires_at == "2099-01-01T00:00:00Z"
    assert v.reason is None


def test_validate_missing_token() -> None:
    assert payment.validate_pro_key("").valid is False
    assert payment.validate_pro_key(None).valid is False  # type: ignore[arg-type]
    assert payment.validate_pro_key("garbage").valid is False


def test_validate_malformed_token() -> None:
    assert payment.validate_pro_key("nopayload.nosig").valid is False
    v = payment.validate_pro_key("only-one-part")
    assert v.reason == "malformed_token"


def test_validate_bad_signature() -> None:
    token = payment.issue_pro_key("team", "2099-01-01T00:00:00Z")
    # Tamper with the signature.
    payload, sig = token.split(".")
    bad = f"{payload}.{'0' * len(sig)}"
    v = payment.validate_pro_key(bad)
    assert v.valid is False
    assert v.reason == "bad_signature"


def test_expired_key_rejected() -> None:
    token = payment.issue_pro_key("starter", "2020-01-01T00:00:00Z")
    v = payment.validate_pro_key(token)
    assert v.valid is False
    assert v.reason == "expired"
    assert v.tier == "starter"  # decoded even though expired


def test_validate_unknown_tier(monkeypatch) -> None:
    """Forge a key with an unknown tier: should fail unknown_tier."""
    import base64, hashlib, hmac, json
    secret = payment._get_hmac_secret()
    payload = {"tier": "platinum", "expires_at": "2099-01-01T00:00:00Z"}
    pb = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    pb64 = base64.urlsafe_b64encode(pb).rstrip(b"=").decode("ascii")
    sig = hmac.new(secret, pb64.encode("ascii"), hashlib.sha256).hexdigest()
    token = f"{pb64}.{sig}"
    v = payment.validate_pro_key(token)
    assert v.valid is False
    assert v.reason == "unknown_tier"


def test_payment_request_shape() -> None:
    req = payment.build_payment_request("starter")
    assert req.http_status == 402
    assert req.currency == "USD"
    assert req.tier == "starter"
    assert req.amount_usd == 9
    assert req.payment_url.startswith("https://store-v2-khaki.vercel.app")
    assert "MILO_COST_AUDITOR_PRO_KEY" in req.instructions


def test_payment_request_falls_back_to_starter() -> None:
    req = payment.build_payment_request("unknown-tier-xyz")
    assert req.tier == "starter"


def test_dev_mode_detection(monkeypatch) -> None:
    monkeypatch.delenv("MILO_COST_AUDITOR_HMAC_KEY", raising=False)
    assert payment.is_dev_mode() is True
    monkeypatch.setenv("MILO_COST_AUDITOR_HMAC_KEY", "prod-key")
    assert payment.is_dev_mode() is False


def test_prod_key_doesnt_validate_against_dev_secret(monkeypatch) -> None:
    """Sign with prod key, then try to validate with dev key in env: must reject."""
    monkeypatch.setenv("MILO_COST_AUDITOR_HMAC_KEY", "prod-secret-aaa")
    token = payment.issue_pro_key("team", "2099-01-01T00:00:00Z")
    # Swap to a different secret; same token must now fail.
    monkeypatch.setenv("MILO_COST_AUDITOR_HMAC_KEY", "prod-secret-bbb")
    v = payment.validate_pro_key(token)
    assert v.valid is False
    assert v.reason == "bad_signature"
