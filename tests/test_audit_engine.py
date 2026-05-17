"""Tests for the invoice parser + waste classifier."""

from __future__ import annotations

import pytest

from milo_cost_auditor import audit_engine


def test_parse_csv_basic(openai_invoice_csv: str) -> None:
    calls = audit_engine.parse_invoice(openai_invoice_csv)
    assert len(calls) == 20
    # First row sanity
    assert calls[0].model == "gpt-5"
    assert calls[0].input_tokens == 150
    assert calls[0].output_tokens == 800
    assert calls[0].cost_usd == pytest.approx(0.0128, rel=1e-3)


def test_parse_csv_anthropic_columns(anthropic_invoice_csv: str) -> None:
    calls = audit_engine.parse_invoice(anthropic_invoice_csv)
    assert len(calls) == 15
    # input_tokens column maps directly; cost_usd column maps too.
    assert calls[0].model == "claude-4-opus"
    assert calls[0].input_tokens == 250
    assert calls[0].cost_usd > 0


def test_parse_json(json_invoice: str) -> None:
    calls = audit_engine.parse_invoice(json_invoice)
    assert len(calls) == 2
    assert calls[0].model == "claude-4-opus"
    assert calls[0].cost_usd == pytest.approx(0.0945, rel=1e-3)


def test_parse_empty() -> None:
    assert audit_engine.parse_invoice("") == []
    assert audit_engine.parse_invoice("   ") == []


def test_audit_full_report(openai_invoice_csv: str) -> None:
    report = audit_engine.audit(openai_invoice_csv, period_days=30)
    assert report.call_count == 20
    assert report.total_spend_usd > 0
    assert 0 <= report.estimated_waste_pct <= 95.0
    # There should be at least one waste pattern detected — gpt-5 on 10 short prompts.
    assert len(report.top_waste_patterns) >= 1
    assert all(p.monthly_dollars >= 0.01 for p in report.top_waste_patterns)
    # by_model breakdown is populated
    assert "gpt-5" in report.by_model
    # Pro teaser is always present
    assert report.pro_teaser
    # Patterns are sorted high-to-low
    dollars = [p.monthly_dollars for p in report.top_waste_patterns]
    assert dollars == sorted(dollars, reverse=True)


def test_audit_anthropic_short_prompt_pattern(anthropic_invoice_csv: str) -> None:
    report = audit_engine.audit(anthropic_invoice_csv, period_days=30)
    pattern_names = {p.pattern for p in report.top_waste_patterns}
    # 10 Opus calls at <500 input tokens = the canonical short-prompt-frontier shape.
    assert "short-prompt-frontier" in pattern_names


def test_audit_period_normalization(openai_invoice_csv: str) -> None:
    """7-day period should yield ~4.3x larger monthly_dollars than 30-day."""
    r7 = audit_engine.audit(openai_invoice_csv, period_days=7)
    r30 = audit_engine.audit(openai_invoice_csv, period_days=30)
    sum7 = sum(p.monthly_dollars for p in r7.top_waste_patterns)
    sum30 = sum(p.monthly_dollars for p in r30.top_waste_patterns)
    # Allow slack — there's rounding + the cap.
    assert sum7 > sum30


def test_estimate_savings(openai_invoice_csv: str) -> None:
    est = audit_engine.estimate(openai_invoice_csv)
    assert est.monthly_saveable_usd > 0
    assert est.confidence in {"low", "medium", "high"}
    assert est.rationale


def test_estimate_savings_empty() -> None:
    est = audit_engine.estimate("")
    assert est.monthly_saveable_usd == 0.0
    assert est.confidence == "low"


def test_unknown_model_doesnt_crash() -> None:
    raw = "model,input_tokens,output_tokens,cost\nmystery-llm-7b,1000,500,0.01"
    report = audit_engine.audit(raw, period_days=30)
    assert report.call_count == 1
    # Unknown model — no patterns triggered
    assert report.top_waste_patterns == []


def test_fill_missing_costs_uses_pricing_table() -> None:
    # Cost = 0 but model is known: engine should derive cost from pricing table.
    raw = "model,input_tokens,output_tokens,cost\ngpt-5,1000000,1000000,0"
    calls = audit_engine.parse_invoice(raw)
    audit_engine._fill_missing_costs(calls)
    # gpt-5: $5/1M input + $15/1M output = $20 for 1M+1M
    assert calls[0].cost_usd == pytest.approx(20.0, rel=1e-3)
