"""
The four MCP tools exposed by this server.

Each tool function is plain Python returning a pydantic BaseModel-derived JSON
dict, so the layer is testable without standing up the MCP loop.

server.py registers these on the FastMCP instance.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from milo_cost_auditor import audit_engine, payment, routing_advisor, telemetry


# ---- output schemas (re-exported for MCP introspection) -------------------

AuditReport = audit_engine.AuditReport
SavingsEstimate = audit_engine.SavingsEstimate
RoutingPlan = routing_advisor.RoutingPlan
PaymentRequest = payment.PaymentRequest


class ProAuditReport(BaseModel):
    """Pro-tier output: full per-call breakdown + recommendations + ready-to-paste configs."""

    base_report: audit_engine.AuditReport
    per_call_breakdown: list[Dict[str, Any]] = Field(default_factory=list)
    projection_30d_usd: float
    prompt_rewrite_recommendations: list[str]
    litellm_config_yaml: str
    bifrost_config_yaml: str
    tier: str
    pro_key_expires_at: Optional[str] = None
    notes: str


# ---- tools -----------------------------------------------------------------


def audit_usage_tool(invoice_csv: str, period_days: int = 30) -> Dict[str, Any]:
    """audit_usage MCP tool body. Returns AuditReport as dict."""
    telemetry.record_invocation("audit_usage")
    report = audit_engine.audit(invoice_csv, period_days=period_days)
    return report.model_dump()


def suggest_routing_tool(current_model: str, task_pattern: str) -> Dict[str, Any]:
    """suggest_routing MCP tool body. Returns RoutingPlan as dict."""
    telemetry.record_invocation("suggest_routing")
    plan = routing_advisor.suggest_routing(current_model, task_pattern)
    return plan.model_dump()


def estimate_savings_tool(invoice_csv: str) -> Dict[str, Any]:
    """estimate_savings MCP tool body. Returns SavingsEstimate as dict."""
    telemetry.record_invocation("estimate_savings")
    est = audit_engine.estimate(invoice_csv)
    return est.model_dump()


def get_pro_report_tool(
    invoice_csv: str,
    pro_key: str = "",
    *,
    tier: str = "starter",
    payment_hash: str = "",
) -> Dict[str, Any]:
    """get_pro_report MCP tool body.

    Validates pro_key locally. If invalid:
      - If a `payment_hash` is supplied, check our local LN-paid cache and
        promote the buyer to a fresh pro_key if the invoice has settled.
      - Otherwise, return a DUAL payment_request envelope (PayPal + Lightning).

    If valid, builds a full per-call report.
    """
    telemetry.record_invocation("get_pro_report")

    # Fast path: lookup-by-payment-hash for LN buyers polling for their key.
    if payment_hash and not pro_key:
        from milo_cost_auditor import lightning_ledger
        claimed = lightning_ledger.claim_paid_key(payment_hash)
        if claimed is not None:
            pro_key = claimed  # fall through to validation below

    validation = payment.validate_pro_key(pro_key)
    if not validation.valid:
        dual = payment.build_dual_payment_request(tier=tier)
        return {
            "status": "payment_required",
            "validation": validation.model_dump(),
            "payment_request": dual.legacy_paypal.model_dump(),  # back-compat
            "dual_payment_request": dual.model_dump(),
        }

    # Build the full report.
    base = audit_engine.audit(invoice_csv, period_days=30)
    calls = audit_engine.parse_invoice(invoice_csv)
    audit_engine._fill_missing_costs(calls)
    per_call: list[Dict[str, Any]] = []
    for c in calls:
        price = None
        from milo_cost_auditor.pricing_table import lookup
        p = lookup(c.model)
        if p is not None:
            from milo_cost_auditor.pricing_table import cheaper_than
            peers = cheaper_than(p, min_quality=3)
            cheapest_alt = peers[0].model if peers else None
            alt_cost = peers[0].cost_for(c.input_tokens, c.output_tokens) if peers else None
        else:
            cheapest_alt = None
            alt_cost = None
        per_call.append({
            "model": c.model,
            "input_tokens": c.input_tokens,
            "output_tokens": c.output_tokens,
            "cost_usd": round(c.cost_usd, 6),
            "cheapest_quality_peer": cheapest_alt,
            "peer_cost_usd": round(alt_cost, 6) if alt_cost is not None else None,
            "saving_if_switched_usd": (
                round(c.cost_usd - alt_cost, 6) if alt_cost is not None else 0.0
            ),
        })

    # 30-day projection: pass-through (audit already normalized).
    projection_30d = round(
        base.total_spend_usd * (30.0 / max(1, base.period_days)), 2
    )

    rewrite_recs = _prompt_rewrite_recommendations(calls)
    litellm_yaml = _global_litellm_yaml(calls)
    bifrost_yaml = _global_bifrost_yaml(calls)

    return {
        "status": "ok",
        "report": ProAuditReport(
            base_report=base,
            per_call_breakdown=per_call,
            projection_30d_usd=projection_30d,
            prompt_rewrite_recommendations=rewrite_recs,
            litellm_config_yaml=litellm_yaml,
            bifrost_config_yaml=bifrost_yaml,
            tier=validation.tier or "starter",
            pro_key_expires_at=validation.expires_at,
            notes=(
                "Paste litellm_config_yaml into your LiteLLM proxy and point your "
                "app's OPENAI_BASE_URL at the proxy. Re-run get_pro_report after "
                "30 days to confirm the projection."
            ),
        ).model_dump(),
    }


# ---- recommendation builders ---------------------------------------------


def _prompt_rewrite_recommendations(calls: list) -> list[str]:
    """Generate prompt-rewrite suggestions based on call shapes."""
    if not calls:
        return []
    recs: list[str] = []
    avg_input = sum(c.input_tokens for c in calls) / max(1, len(calls))
    avg_output = sum(c.output_tokens for c in calls) / max(1, len(calls))
    if avg_input > 8_000:
        recs.append(
            "Average input token count is high (>8k). Compress system prompts and "
            "move docs to retrieval — Gemini Flash with 1M+ context handles the "
            "expansion when you actually need it."
        )
    if avg_output > 2_000:
        recs.append(
            "Average output is large (>2k). For routine generation, request "
            "structured/JSON-mode output with a length cap. Long prose responses "
            "are usually a sign of missing constraints."
        )
    if avg_output > avg_input * 3:
        recs.append(
            "Output >> input ratio (summarization shape). Route summarization to "
            "claude-haiku-4.5, gemini-3-flash-preview, or deepseek-v3."
        )
    # frontier-on-tiny-prompt
    short_frontier = 0
    for c in calls:
        from milo_cost_auditor.pricing_table import lookup
        p = lookup(c.model)
        if p and p.quality_band >= 5 and c.input_tokens < 500:
            short_frontier += 1
    if short_frontier > 0:
        recs.append(
            f"{short_frontier} calls hit a frontier model with <500 input tokens. "
            "Add a router rule: if input < 500 tokens, downroute to gpt-5.4-mini or "
            "claude-haiku-4.5."
        )
    if not recs:
        recs.append(
            "Token shapes look healthy. Main waste is model selection, not prompt "
            "design — apply the routing recommendation and re-audit in 30 days."
        )
    return recs


def _global_litellm_yaml(calls: list) -> str:
    """Generate a global LiteLLM proxy config that downroutes per task pattern."""
    from milo_cost_auditor.pricing_table import lookup, cheaper_than
    used_models: list[str] = sorted({c.model for c in calls if lookup(c.model) is not None})
    lines: list[str] = []
    lines.append("# Generated by Milo Cost Auditor — global LiteLLM proxy config")
    lines.append("# https://docs.litellm.ai/docs/proxy/configs")
    lines.append("model_list:")
    for model in used_models:
        price = lookup(model)
        if price is None:
            continue
        peers = cheaper_than(price, min_quality=3)
        primary_alt = peers[0].model if peers else model
        primary_provider = peers[0].provider if peers else price.provider
        lines.append(f"  - model_name: {model}")
        lines.append(f"    litellm_params:")
        lines.append(f"      model: {primary_provider}/{primary_alt}")
        lines.append(f"      # downrouted from {model} (~{(price.input_per_million + price.output_per_million)/2:.2f}/1M)")
    lines.append("router_settings:")
    lines.append("  routing_strategy: simple-shuffle")
    lines.append("  num_retries: 2")
    return "\n".join(lines) + "\n"


def _global_bifrost_yaml(calls: list) -> str:
    """Generate a Bifrost gateway config (alternative router) for the same set."""
    from milo_cost_auditor.pricing_table import lookup, cheaper_than
    used_models: list[str] = sorted({c.model for c in calls if lookup(c.model) is not None})
    lines: list[str] = []
    lines.append("# Generated by Milo Cost Auditor — Bifrost gateway config")
    lines.append("# https://github.com/maximhq/bifrost")
    lines.append("routes:")
    for model in used_models:
        price = lookup(model)
        if price is None:
            continue
        peers = cheaper_than(price, min_quality=3)
        if not peers:
            continue
        lines.append(f"  - match: {model}")
        lines.append(f"    primary: {peers[0].provider}/{peers[0].model}")
        if len(peers) >= 2:
            lines.append(f"    fallback: {peers[1].provider}/{peers[1].model}")
        lines.append(f"    escalate: {price.provider}/{model}  # on 4xx/5xx")
    return "\n".join(lines) + "\n"
