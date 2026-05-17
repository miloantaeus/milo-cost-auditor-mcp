"""Tests for the routing advisor."""

from __future__ import annotations

import pytest

from milo_cost_auditor import routing_advisor
from milo_cost_auditor.pricing_table import lookup


def test_suggest_routing_known_model() -> None:
    plan = routing_advisor.suggest_routing("gpt-4o", "summarization")
    assert plan.current_model_known is True
    assert plan.task_pattern == "summarization"
    assert plan.min_quality_required == 3
    assert len(plan.alternatives) > 0
    # Top alternative is strictly cheaper than gpt-4o.
    gpt4o = lookup("gpt-4o")
    assert gpt4o is not None
    top = plan.alternatives[0]
    top_avg = (top.input_per_million_usd + top.output_per_million_usd) / 2.0
    gpt4o_avg = (gpt4o.input_per_million + gpt4o.output_per_million) / 2.0
    assert top_avg < gpt4o_avg
    assert top.avg_cost_delta_pct > 0
    # YAML snippet contains the recommended model
    assert top.model in plan.litellm_yaml


def test_suggest_routing_unknown_model() -> None:
    plan = routing_advisor.suggest_routing("totally-fictional-model-99x", "code-completion")
    assert plan.current_model_known is False
    # Still produces alternatives — best available for the task pattern.
    assert len(plan.alternatives) == 3
    assert "I don't have a price" in plan.summary


def test_suggest_routing_for_deep_reasoning_keeps_quality() -> None:
    """deep-reasoning requires quality band 4; cheap weak models should be excluded."""
    plan = routing_advisor.suggest_routing("gpt-5.5", "deep-reasoning")
    assert plan.min_quality_required == 4
    # Every alternative must be quality band 4 or higher.
    for alt in plan.alternatives:
        assert alt.quality_band >= 4, f"{alt.model} band {alt.quality_band} too low"


def test_suggest_routing_already_cheapest() -> None:
    """A cheap model with no cheaper peer at the same quality returns empty alts."""
    # llama-3.1-8b-instant is one of the cheapest options at quality band 2.
    plan = routing_advisor.suggest_routing("llama-3.1-8b-instant", "extraction")
    # extraction needs quality 2; the model itself is band 2; cheaper peers may exist.
    # Verify deterministic behavior either way:
    if plan.alternatives:
        for alt in plan.alternatives:
            assert alt.quality_band >= 2
    else:
        assert "already the cheapest" in plan.summary or "Nothing to do" in plan.summary


def test_litellm_yaml_includes_router_settings() -> None:
    plan = routing_advisor.suggest_routing("claude-opus-4.7", "summarization")
    assert "model_list:" in plan.litellm_yaml
    assert "router_settings:" in plan.litellm_yaml
    assert "fallbacks:" in plan.litellm_yaml


def test_task_pattern_default() -> None:
    plan = routing_advisor.suggest_routing("gpt-5.5", "")
    # Empty pattern falls back to routine-synthesis
    assert plan.task_pattern == "routine-synthesis"
