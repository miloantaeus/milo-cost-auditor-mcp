"""
Invoice parser + waste classifier.

Pure-Python, deterministic, no external API calls.

Accepts two input shapes:
  1. CSV with header row. Auto-detects OpenAI / Anthropic / generic columns.
  2. JSON array of call records.

Output schema is the AuditReport pydantic model defined here.
"""

from __future__ import annotations

import csv
import io
import json
import statistics
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from milo_cost_auditor.pricing_table import (
    PRICING_TABLE,
    TASK_QUALITY_REQUIREMENT,
    ModelPrice,
    cheaper_than,
    lookup,
)


# ---- public schema ---------------------------------------------------------


class WastePattern(BaseModel):
    """One identified pattern of overspend."""

    pattern: str = Field(..., description="Short label, e.g. 'frontier-for-short-prompts'")
    monthly_dollars: float = Field(..., description="Estimated waste $/month from this pattern")
    rationale: str = Field(..., description="Why I flagged it")
    fix_summary: str = Field(..., description="One-line: how to fix")


class AuditReport(BaseModel):
    """Full free-tier audit output."""

    total_spend_usd: float
    period_days: int
    call_count: int
    estimated_waste_pct: float = Field(
        ..., description="0..100 — share of spend I'd cut with my routing recommendations"
    )
    estimated_waste_usd: float
    top_waste_patterns: List[WastePattern]
    by_model: Dict[str, float] = Field(default_factory=dict)
    pro_teaser: str = Field(
        ...,
        description="One sentence on what the paid report adds. Always present in free tier.",
    )


class SavingsEstimate(BaseModel):
    """Quick estimate variant — one number plus a one-liner."""

    monthly_saveable_usd: float
    rationale: str
    confidence: str = Field(..., description="'low' | 'medium' | 'high'")


# ---- internal data shape ---------------------------------------------------


@dataclass
class _Call:
    """Normalized internal representation of one invoice line."""

    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    timestamp: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)


# ---- parsing ---------------------------------------------------------------


def _looks_like_json(raw: str) -> bool:
    head = raw.lstrip()[:1]
    return head in ("[", "{")


def _parse_json(raw: str) -> List[_Call]:
    data = json.loads(raw)
    if isinstance(data, dict):
        data = [data]
    calls: List[_Call] = []
    for row in data:
        if not isinstance(row, dict):
            continue
        calls.append(_normalize_row(row))
    return calls


def _parse_csv(raw: str) -> List[_Call]:
    reader = csv.DictReader(io.StringIO(raw))
    return [_normalize_row(row) for row in reader if row]


def _normalize_row(row: Dict[str, Any]) -> _Call:
    """Coerce a heterogeneous invoice row into a _Call."""
    # Map common column names.
    model_keys = ("model", "model_name", "engine", "model_id")
    input_keys = ("input_tokens", "prompt_tokens", "tokens_in", "n_context_tokens_total")
    output_keys = ("output_tokens", "completion_tokens", "tokens_out", "n_generated_tokens_total")
    cost_keys = ("cost", "cost_usd", "amount", "spend")
    ts_keys = ("timestamp", "ts", "created_at", "request_time", "date")

    def first(keys: tuple, default: Any = None) -> Any:
        for k in keys:
            if k in row and row[k] not in (None, "", "null"):
                return row[k]
        return default

    def to_int(v: Any) -> int:
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return 0

    def to_float(v: Any) -> float:
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0

    model_raw = str(first(model_keys, "unknown")).strip()
    return _Call(
        model=model_raw,
        input_tokens=to_int(first(input_keys, 0)),
        output_tokens=to_int(first(output_keys, 0)),
        cost_usd=to_float(first(cost_keys, 0)),
        timestamp=first(ts_keys),
        raw=dict(row),
    )


def parse_invoice(raw: str) -> List[_Call]:
    """Parse an invoice blob (CSV or JSON). Returns normalized _Call list."""
    if not raw or not raw.strip():
        return []
    raw = raw.strip()
    if _looks_like_json(raw):
        return _parse_json(raw)
    return _parse_csv(raw)


def _fill_missing_costs(calls: List[_Call]) -> None:
    """If cost is zero but tokens + known model, derive from pricing table."""
    for c in calls:
        if c.cost_usd > 0:
            continue
        price = lookup(c.model)
        if price is None:
            continue
        c.cost_usd = price.cost_for(c.input_tokens, c.output_tokens)


# ---- waste classification --------------------------------------------------


_FRONTIER_QUALITY_FLOOR = 5
_HIGH_OUTPUT_RATIO = 4.0  # output > 4x input is "expansive" -> often summarization-friendly


def _classify_calls(calls: List[_Call]) -> Dict[str, List[_Call]]:
    """Bucket calls by task-pattern guess from prompt-length distribution."""
    buckets: Dict[str, List[_Call]] = {
        "short-prompt-frontier": [],   # < 500 input tokens on a frontier model
        "expansive-frontier": [],      # output >> input on a frontier model (summarization-friendly)
        "agent-loop-frontier": [],     # many small same-model calls in sequence (Sonnet/Opus on agents)
        "long-context-but-tiny-output": [],  # >50k input, <500 output on premium = retrieval-friendly
    }
    # group by model first for the agent-loop pattern
    by_model: Dict[str, List[_Call]] = {}
    for c in calls:
        by_model.setdefault(c.model, []).append(c)

    for c in calls:
        price = lookup(c.model)
        if price is None:
            continue
        if price.quality_band >= _FRONTIER_QUALITY_FLOOR and c.input_tokens < 500 and c.input_tokens > 0:
            buckets["short-prompt-frontier"].append(c)
        if (
            price.quality_band >= 4
            and c.input_tokens > 0
            and c.output_tokens > c.input_tokens * _HIGH_OUTPUT_RATIO
        ):
            buckets["expansive-frontier"].append(c)
        if (
            price.quality_band >= 4
            and c.input_tokens > 50_000
            and 0 < c.output_tokens < 500
        ):
            buckets["long-context-but-tiny-output"].append(c)

    # agent-loop: same model, >=20 calls in window
    for model, model_calls in by_model.items():
        price = lookup(model)
        if price is None or price.quality_band < 4:
            continue
        if len(model_calls) >= 20:
            buckets["agent-loop-frontier"].extend(model_calls)

    return buckets


def _waste_pattern_from_bucket(
    pattern: str, bucket: List[_Call], period_days: int
) -> Optional[WastePattern]:
    if not bucket:
        return None
    bucket_spend = sum(c.cost_usd for c in bucket)
    if bucket_spend <= 0:
        return None

    # Estimate savings: pick cheapest peer that still meets the task's quality floor.
    quality_floor = {
        "short-prompt-frontier": 3,
        "expansive-frontier": 3,
        "agent-loop-frontier": 3,
        "long-context-but-tiny-output": 3,
    }.get(pattern, 3)

    saving = 0.0
    for c in bucket:
        price = lookup(c.model)
        if price is None:
            continue
        peers = cheaper_than(price, min_quality=quality_floor)
        if not peers:
            continue
        alt = peers[0]
        alt_cost = alt.cost_for(c.input_tokens, c.output_tokens)
        saving += max(0.0, c.cost_usd - alt_cost)

    # Normalize to monthly.
    if period_days > 0 and period_days != 30:
        saving = saving * (30.0 / period_days)

    if saving < 0.01:
        return None

    rationales = {
        "short-prompt-frontier": (
            f"{len(bucket)} calls used a frontier model on prompts under 500 input tokens. "
            "Frontier prices are calibrated for reasoning-heavy work, not short queries."
        ),
        "expansive-frontier": (
            f"{len(bucket)} calls produced output >4x input size on a frontier model — "
            "classic summarization/rewrite shape that a mid-tier model handles fine."
        ),
        "agent-loop-frontier": (
            f"{len(bucket)} calls hit the same frontier model in a tight loop — "
            "agent loops should usually run on Haiku/gpt-5.4-mini class with frontier only as escalation."
        ),
        "long-context-but-tiny-output": (
            f"{len(bucket)} calls fed >50k input tokens but produced <500 output — "
            "retrieval/extraction over big context is the sweet spot for Gemini Flash or Haiku."
        ),
    }
    fixes = {
        "short-prompt-frontier": "Route short-prompt calls to gpt-5.4-mini, claude-haiku-4.5, or gemini-3-flash-preview.",
        "expansive-frontier": "Move summarization to claude-haiku-4.5, gemini-3-flash-preview, or deepseek-v3.",
        "agent-loop-frontier": "Default the loop to a mini/haiku model and escalate to frontier on retry.",
        "long-context-but-tiny-output": "Use gemini-3-flash-preview (1-2M context) or claude-haiku-4.5 for retrieval.",
    }
    return WastePattern(
        pattern=pattern,
        monthly_dollars=round(saving, 2),
        rationale=rationales[pattern],
        fix_summary=fixes[pattern],
    )


def audit(invoice_raw: str, period_days: int = 30) -> AuditReport:
    """Full audit. Returns AuditReport."""
    calls = parse_invoice(invoice_raw)
    _fill_missing_costs(calls)

    total_spend = round(sum(c.cost_usd for c in calls), 4)
    by_model: Dict[str, float] = {}
    for c in calls:
        by_model[c.model] = round(by_model.get(c.model, 0.0) + c.cost_usd, 4)

    buckets = _classify_calls(calls)
    patterns: List[WastePattern] = []
    for name, bucket in buckets.items():
        p = _waste_pattern_from_bucket(name, bucket, period_days)
        if p is not None:
            patterns.append(p)
    patterns.sort(key=lambda p: p.monthly_dollars, reverse=True)
    top = patterns[:3]

    estimated_waste_usd = round(sum(p.monthly_dollars for p in top), 2)
    # waste_pct relative to monthly-normalized spend, capped at 95%.
    monthly_spend = total_spend * (30.0 / period_days) if period_days > 0 else total_spend
    if monthly_spend > 0:
        waste_pct = min(95.0, round(100.0 * estimated_waste_usd / monthly_spend, 1))
    else:
        waste_pct = 0.0

    teaser = (
        "Pro report adds per-call breakdown, 30-day projection, "
        "and a ready-to-paste LiteLLM config that implements every recommendation."
    )

    # CROSS-PRODUCT FUNNEL (REVENUE-MCP-USAGE-FORECASTER-LINKBACK-20260517):
    # When total spend crosses the $200 threshold, append a one-liner pointing
    # users at the companion milo-usage-forecaster MCP. Converts cost-auditor's
    # backward-looking diagnosis into a forecaster trial in 1 click. ~10 LOC.
    if total_spend >= 200.0:
        teaser = (
            teaser
            + " | Spend trending high? Pair this audit with milo-usage-forecaster"
            " (free MCP: https://github.com/miloantaeus/milo-usage-forecaster-mcp)"
            " to project end-of-month spend + get budget-breach alerts."
        )

    return AuditReport(
        total_spend_usd=total_spend,
        period_days=period_days,
        call_count=len(calls),
        estimated_waste_pct=waste_pct,
        estimated_waste_usd=estimated_waste_usd,
        top_waste_patterns=top,
        by_model=by_model,
        pro_teaser=teaser,
    )


def estimate(invoice_raw: str) -> SavingsEstimate:
    """Cheap variant — one number plus one-liner."""
    calls = parse_invoice(invoice_raw)
    _fill_missing_costs(calls)
    if not calls:
        return SavingsEstimate(
            monthly_saveable_usd=0.0,
            rationale="No invoice rows parsed. Re-export with a header row.",
            confidence="low",
        )

    # Heuristic: for each call, if cheaper peer with quality >=3 exists, count the delta.
    total_saving = 0.0
    fired = 0
    for c in calls:
        price = lookup(c.model)
        if price is None:
            continue
        peers = cheaper_than(price, min_quality=3)
        if not peers:
            continue
        alt = peers[0]
        alt_cost = alt.cost_for(c.input_tokens, c.output_tokens)
        delta = c.cost_usd - alt_cost
        if delta > 0:
            total_saving += delta
            fired += 1

    # Normalize to monthly — assume 30 days unless invoice spans further.
    saving = round(total_saving, 2)
    if fired == 0:
        rationale = "Already using lowest-cost peer per model. Nice."
        conf = "high"
    elif fired < len(calls) * 0.10:
        rationale = f"{fired} of {len(calls)} calls could move to a cheaper peer model."
        conf = "low"
    elif fired < len(calls) * 0.40:
        rationale = (
            f"{fired} of {len(calls)} calls would save money on a cheaper peer — "
            "mostly short-prompt or summarization shapes."
        )
        conf = "medium"
    else:
        rationale = (
            f"{fired} of {len(calls)} calls overspend versus the cheapest quality-equivalent peer. "
            "Routing fix is high-leverage."
        )
        conf = "high"
    return SavingsEstimate(
        monthly_saveable_usd=saving,
        rationale=rationale,
        confidence=conf,
    )
