"""Tests for the Lightning Network payment path (LNBitsProvider + ledger).

Mocks ALL HTTP — no real LN calls. We use httpx.MockTransport to inject
canned LNBits responses into the provider.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, Optional

import httpx
import pytest

from milo_cost_auditor import lightning, lightning_ledger, payment, tools


# ---- HTTP mocking helpers -------------------------------------------------


def make_mock_client(handler) -> httpx.Client:
    """Build an httpx.Client backed by a MockTransport handler.

    handler signature: (request: httpx.Request) -> httpx.Response
    """
    transport = httpx.MockTransport(handler)
    return httpx.Client(transport=transport, timeout=5.0)


def fixed_invoice_response(
    payment_hash: str = "abc123def456" * 4,
    bolt11: str = "lnbc100u1p0testfakebolt11invoicestring",
) -> Dict[str, Any]:
    return {
        "payment_hash": payment_hash,
        "payment_request": bolt11,
        "checking_id": payment_hash,
    }


# ---- USD/sats conversion --------------------------------------------------


def test_usd_to_sats_rounds_up() -> None:
    # 9 USD * 1000 = 9000 sats exact
    assert lightning.usd_to_sats(9) == 9000
    assert lightning.usd_to_sats(29) == 29000
    assert lightning.usd_to_sats(99) == 99000
    # Non-integer: rounds UP (never underbills).
    assert lightning.usd_to_sats(0.001) == 1
    assert lightning.usd_to_sats(0.0011) == 2


def test_usd_to_sats_custom_rate() -> None:
    assert lightning.usd_to_sats(1.0, rate=2000) == 2000


def test_usd_to_sats_rejects_nonpositive() -> None:
    with pytest.raises(ValueError):
        lightning.usd_to_sats(0)
    with pytest.raises(ValueError):
        lightning.usd_to_sats(-1)


def test_tier_amount_sats() -> None:
    assert payment.tier_amount_sats("starter") == 9000
    assert payment.tier_amount_sats("team") == 29000
    assert payment.tier_amount_sats("org") == 99000
    # Unknown tier falls back to starter.
    assert payment.tier_amount_sats("platinum") == 9000


# ---- LNBitsProvider — happy path -----------------------------------------


def test_lnbits_create_invoice_returns_bolt11(monkeypatch) -> None:
    """create_invoice posts to /api/v1/payments and parses BOLT-11 back."""
    monkeypatch.setenv("MILO_LIGHTNING_INVOICE_KEY", "test-invoice-key")
    captured: Dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/payments"
        assert request.method == "POST"
        assert request.headers.get("X-Api-Key") == "test-invoice-key"
        body = json.loads(request.content)
        captured["body"] = body
        assert body["out"] is False
        assert body["amount"] == 9000
        assert body["unit"] == "sat"
        assert body["memo"].startswith("milo-cost-auditor")
        return httpx.Response(200, json=fixed_invoice_response())

    client = make_mock_client(handler)
    provider = lightning.LNBitsProvider(http_client=client)
    invoice = provider.create_invoice(amount_sats=9000, memo="milo-cost-auditor starter (9 USD)")
    assert invoice.amount_sats == 9000
    assert invoice.payment_request.startswith("lnbc")
    assert invoice.payment_hash
    assert invoice.provider == "lnbits"
    assert invoice.expires_at > time.time()
    assert captured["body"]["expiry"] == 3600  # 60 min default


def test_lnbits_create_invoice_rejects_zero_amount(monkeypatch) -> None:
    monkeypatch.setenv("MILO_LIGHTNING_INVOICE_KEY", "k")
    provider = lightning.LNBitsProvider(http_client=make_mock_client(lambda r: httpx.Response(200, json={})))
    with pytest.raises(ValueError):
        provider.create_invoice(amount_sats=0, memo="x")
    with pytest.raises(ValueError):
        provider.create_invoice(amount_sats=-100, memo="x")


def test_lnbits_create_invoice_rejects_extreme_expiry(monkeypatch) -> None:
    monkeypatch.setenv("MILO_LIGHTNING_INVOICE_KEY", "k")
    provider = lightning.LNBitsProvider(http_client=make_mock_client(lambda r: httpx.Response(200, json={})))
    with pytest.raises(ValueError):
        provider.create_invoice(amount_sats=1000, memo="x", expires_minutes=0)
    with pytest.raises(ValueError):
        provider.create_invoice(amount_sats=1000, memo="x", expires_minutes=60 * 24 * 7 + 1)


def test_lnbits_check_payment_unpaid() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/payments/abc123"
        return httpx.Response(200, json={"paid": False})

    client = make_mock_client(handler)
    provider = lightning.LNBitsProvider(http_client=client)
    status = provider.check_payment("abc123")
    assert status.paid is False
    assert status.payment_hash == "abc123"
    assert status.preimage is None


def test_lnbits_check_payment_paid_returns_preimage() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"paid": True, "preimage": "deadbeef"})

    client = make_mock_client(handler)
    provider = lightning.LNBitsProvider(http_client=client)
    status = provider.check_payment("xyz")
    assert status.paid is True
    assert status.preimage == "deadbeef"


def test_lnbits_check_payment_validates_hash_length() -> None:
    provider = lightning.LNBitsProvider(http_client=make_mock_client(lambda r: httpx.Response(200, json={})))
    with pytest.raises(ValueError):
        provider.check_payment("")
    with pytest.raises(ValueError):
        provider.check_payment("a" * 200)  # too long


# ---- LNBitsProvider — error paths ----------------------------------------


def test_lnbits_unconfigured_invoice_key_raises(monkeypatch) -> None:
    monkeypatch.delenv("MILO_LIGHTNING_INVOICE_KEY", raising=False)
    provider = lightning.LNBitsProvider(invoice_key="")
    with pytest.raises(lightning.LightningProviderUnconfigured):
        provider.create_invoice(amount_sats=100, memo="x")


def test_lnbits_5xx_surfaces_provider_error(monkeypatch) -> None:
    monkeypatch.setenv("MILO_LIGHTNING_INVOICE_KEY", "k")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="Service Unavailable")

    client = make_mock_client(handler)
    provider = lightning.LNBitsProvider(http_client=client)
    with pytest.raises(lightning.LightningProviderError) as exc_info:
        provider.create_invoice(amount_sats=100, memo="x")
    assert "503" in str(exc_info.value)


def test_lnbits_missing_payment_request_in_response(monkeypatch) -> None:
    monkeypatch.setenv("MILO_LIGHTNING_INVOICE_KEY", "k")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"checking_id": "abc"})  # no payment_request

    client = make_mock_client(handler)
    provider = lightning.LNBitsProvider(http_client=client)
    with pytest.raises(lightning.LightningProviderError):
        provider.create_invoice(amount_sats=100, memo="x")


# ---- factory --------------------------------------------------------------


def test_get_provider_defaults_to_lnbits(monkeypatch) -> None:
    monkeypatch.delenv("MILO_LIGHTNING_PROVIDER", raising=False)
    p = lightning.get_provider()
    assert isinstance(p, lightning.LNBitsProvider)
    assert p.name == "lnbits"


def test_get_provider_alby_via_env(monkeypatch) -> None:
    monkeypatch.setenv("MILO_LIGHTNING_PROVIDER", "alby")
    p = lightning.get_provider()
    assert isinstance(p, lightning.AlbyProvider)
    assert p.name == "alby"


def test_get_provider_rejects_unknown(monkeypatch) -> None:
    monkeypatch.setenv("MILO_LIGHTNING_PROVIDER", "venmo")
    with pytest.raises(ValueError):
        lightning.get_provider()


# ---- ledger ---------------------------------------------------------------


def test_ledger_record_and_get() -> None:
    lightning_ledger.reset_for_tests()
    lightning_ledger.record_invoice(
        payment_hash="hash1",
        amount_sats=9000,
        tier="starter",
        bolt11="lnbc1...",
        memo="test",
    )
    row = lightning_ledger.get("hash1")
    assert row is not None
    assert row["amount_sats"] == 9000
    assert row["tier"] == "starter"
    assert row["paid_at"] is None
    assert row["pro_key"] is None


def test_ledger_idempotent_insert() -> None:
    lightning_ledger.reset_for_tests()
    lightning_ledger.record_invoice(
        payment_hash="hash2", amount_sats=100, tier="team", bolt11="ln1"
    )
    lightning_ledger.record_invoice(
        payment_hash="hash2", amount_sats=99999, tier="org", bolt11="ln2"
    )
    # Second insert is a no-op (INSERT OR IGNORE).
    row = lightning_ledger.get("hash2")
    assert row["amount_sats"] == 100
    assert row["tier"] == "team"


def test_ledger_mark_paid_transitions_once() -> None:
    lightning_ledger.reset_for_tests()
    lightning_ledger.record_invoice(
        payment_hash="hash3", amount_sats=100, tier="starter", bolt11="ln"
    )
    assert lightning_ledger.mark_paid("hash3", pro_key="key-A") is True
    # Second call must NOT overwrite.
    assert lightning_ledger.mark_paid("hash3", pro_key="key-B") is False
    assert lightning_ledger.claim_paid_key("hash3") == "key-A"


def test_ledger_mark_paid_missing_returns_false() -> None:
    lightning_ledger.reset_for_tests()
    assert lightning_ledger.mark_paid("nonexistent", pro_key="x") is False


def test_ledger_claim_unpaid_returns_none() -> None:
    lightning_ledger.reset_for_tests()
    lightning_ledger.record_invoice(
        payment_hash="hash4", amount_sats=100, tier="starter", bolt11="ln"
    )
    assert lightning_ledger.claim_paid_key("hash4") is None


def test_ledger_list_outstanding_only_unpaid() -> None:
    lightning_ledger.reset_for_tests()
    lightning_ledger.record_invoice(
        payment_hash="paid", amount_sats=100, tier="starter", bolt11="ln1"
    )
    lightning_ledger.record_invoice(
        payment_hash="unpaid", amount_sats=200, tier="team", bolt11="ln2"
    )
    lightning_ledger.mark_paid("paid", pro_key="some-key")
    out = lightning_ledger.list_outstanding()
    hashes = [r["payment_hash"] for r in out]
    assert "unpaid" in hashes
    assert "paid" not in hashes


# ---- dual payment request -------------------------------------------------


def test_build_dual_payment_request_with_lightning(monkeypatch) -> None:
    """Happy path: LN provider returns invoice, both rails surfaced."""
    monkeypatch.setenv("MILO_LIGHTNING_INVOICE_KEY", "k")
    lightning_ledger.reset_for_tests()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=fixed_invoice_response(
            payment_hash="dualhash1",
            bolt11="lnbc100u1pdual",
        ))

    client = make_mock_client(handler)
    provider = lightning.LNBitsProvider(http_client=client)
    dual = payment.build_dual_payment_request(tier="starter", lightning_provider=provider)
    assert dual.tier == "starter"
    assert dual.amount_usd == 9
    assert dual.legacy_paypal.payment_url.startswith("https://store-v2-khaki")
    assert dual.lightning is not None
    assert dual.lightning.amount_sats == 9000
    assert dual.lightning.bolt11 == "lnbc100u1pdual"
    assert dual.lightning.payment_hash == "dualhash1"
    assert dual.lightning.provider == "lnbits"
    assert dual.preferred_rail == "lightning"

    # Side effect: the invoice was persisted in the ledger.
    row = lightning_ledger.get("dualhash1")
    assert row is not None
    assert row["amount_sats"] == 9000
    assert row["tier"] == "starter"


def test_build_dual_payment_request_lightning_disabled() -> None:
    """When enable_lightning=False, only PayPal leg returned."""
    dual = payment.build_dual_payment_request(tier="team", enable_lightning=False)
    assert dual.lightning is None
    assert dual.preferred_rail == "paypal"
    assert dual.legacy_paypal.amount_usd == 29


def test_build_dual_payment_request_falls_back_when_ln_errors(monkeypatch) -> None:
    """If LN provider raises, we still return a valid PayPal-only response."""
    monkeypatch.setenv("MILO_LIGHTNING_INVOICE_KEY", "k")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="kaboom")

    client = make_mock_client(handler)
    provider = lightning.LNBitsProvider(http_client=client)
    dual = payment.build_dual_payment_request(tier="starter", lightning_provider=provider)
    assert dual.lightning is None
    assert dual.preferred_rail == "paypal"
    assert dual.legacy_paypal.amount_usd == 9


# ---- get_pro_report integration -------------------------------------------


def test_get_pro_report_without_key_returns_dual_payment(openai_invoice_csv: str, monkeypatch) -> None:
    """Without pro_key: response includes both legacy + dual payment request."""
    # Force LN fallback so we don't actually hit the network in this test.
    # (build_dual_payment_request will catch the env error.)
    monkeypatch.delenv("MILO_LIGHTNING_INVOICE_KEY", raising=False)
    out = tools.get_pro_report_tool(openai_invoice_csv, pro_key="")
    assert out["status"] == "payment_required"
    # Back-compat: legacy payment_request still present.
    assert out["payment_request"]["http_status"] == 402
    assert out["payment_request"]["payment_url"].startswith("https://store-v2-khaki")
    # New: dual envelope.
    assert "dual_payment_request" in out
    dual = out["dual_payment_request"]
    assert dual["tier"] == "starter"
    assert dual["legacy_paypal"]["http_status"] == 402
    # LN leg is None because invoice_key was unset (fail-gracefully path).
    assert dual["lightning"] is None
    assert dual["preferred_rail"] == "paypal"


def test_get_pro_report_with_payment_hash_promotes_to_key(
    openai_invoice_csv: str, monkeypatch
) -> None:
    """Buyer paid the LN invoice; watcher attached a key; second call validates."""
    monkeypatch.setenv("MILO_COST_AUDITOR_DEV_MODE", "1")
    lightning_ledger.reset_for_tests()
    # Simulate watcher having issued a key.
    valid_token = payment.issue_pro_key("team", "2099-01-01T00:00:00Z")
    lightning_ledger.record_invoice(
        payment_hash="paid-hash-xyz",
        amount_sats=29000,
        tier="team",
        bolt11="lnbc...",
    )
    lightning_ledger.mark_paid("paid-hash-xyz", pro_key=valid_token)

    out = tools.get_pro_report_tool(
        openai_invoice_csv,
        pro_key="",
        payment_hash="paid-hash-xyz",
    )
    assert out["status"] == "ok"
    assert out["report"]["tier"] == "team"


def test_get_pro_report_payment_hash_unpaid_still_returns_402(
    openai_invoice_csv: str,
) -> None:
    """A payment_hash for an unpaid invoice returns the dual payment envelope."""
    lightning_ledger.reset_for_tests()
    lightning_ledger.record_invoice(
        payment_hash="unpaid-hash", amount_sats=9000, tier="starter", bolt11="ln"
    )
    out = tools.get_pro_report_tool(
        openai_invoice_csv,
        pro_key="",
        payment_hash="unpaid-hash",
    )
    assert out["status"] == "payment_required"
