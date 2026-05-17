"""
MCP server bootstrap.

Wires the four tool functions onto a FastMCP instance and starts the stdio loop.
Run via:
    python -m milo_cost_auditor
    mcp-cost-auditor    (console entry point)

Tested with the official Python MCP SDK (`mcp` package, >= 1.0).
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict

from milo_cost_auditor import __version__, payment, telemetry, tools

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover - hard import-time error
    sys.stderr.write(
        "milo-cost-auditor needs the `mcp` package (pip install mcp).\n"
        f"Import error: {exc}\n"
    )
    raise


SERVER_NAME = "milo-cost-auditor"
SERVER_INSTRUCTIONS = (
    "Milo Cost Auditor — I audit your LLM API spend and tell you where the waste "
    "is. Run audit_usage on your invoice CSV/JSON to get a free report, "
    "suggest_routing to swap a single model for a cheaper peer, "
    "estimate_savings for a one-number teaser, and get_pro_report for the full "
    "per-call breakdown with ready-to-paste LiteLLM/Bifrost configs."
)


def build_server() -> FastMCP:
    """Construct + register tools. Public for tests."""
    mcp = FastMCP(name=SERVER_NAME, instructions=SERVER_INSTRUCTIONS)

    @mcp.tool(
        name="audit_usage",
        description=(
            "Parse an OpenAI/Anthropic/Vercel-AI-gateway invoice (CSV or JSON), "
            "classify usage by model + task pattern, and return a structured "
            "AuditReport with total spend, waste percentage, top 3 waste patterns, "
            "and a teaser of what the paid report adds. Free tier — no API key required."
        ),
    )
    def audit_usage(invoice_csv: str, period_days: int = 30) -> Dict[str, Any]:
        return tools.audit_usage_tool(invoice_csv, period_days=period_days)

    @mcp.tool(
        name="suggest_routing",
        description=(
            "Given a current model (e.g. 'gpt-4o', 'claude-3-opus') and a task "
            "pattern (e.g. 'code-completion', 'summarization', 'routine-synthesis', "
            "'deep-reasoning'), return a ranked list of cheaper alternatives with "
            "cost-per-1M-tokens delta, a quality-tradeoff note, and a LiteLLM YAML "
            "snippet you can paste straight into your proxy config."
        ),
    )
    def suggest_routing(current_model: str, task_pattern: str) -> Dict[str, Any]:
        return tools.suggest_routing_tool(current_model, task_pattern)

    @mcp.tool(
        name="estimate_savings",
        description=(
            "Quick variant of audit_usage. Returns a single 'monthly_saveable_usd' "
            "number plus a one-line reason and confidence band. Use this for a "
            "fast sanity check; use audit_usage for the full report."
        ),
    )
    def estimate_savings(invoice_csv: str) -> Dict[str, Any]:
        return tools.estimate_savings_tool(invoice_csv)

    @mcp.tool(
        name="get_pro_report",
        description=(
            "Paid tier. Validates the pro_key locally (HMAC-signed token from the "
            "storefront) and returns a full per-call breakdown, 30-day projection, "
            "prompt-rewrite recommendations, and ready-to-paste LiteLLM + Bifrost "
            "config blocks. If the pro_key is missing or invalid, returns a "
            "DUAL payment_request envelope with BOTH (a) the legacy PayPal "
            "checkout URL and (b) a Lightning Network BOLT-11 invoice — the LN "
            "rail is M2M-friendly and requires no KYC on either side. After "
            "paying the LN invoice, re-call with `payment_hash` to claim the "
            "issued pro_key from the local LN ledger."
        ),
    )
    def get_pro_report(
        invoice_csv: str,
        pro_key: str = "",
        tier: str = "starter",
        payment_hash: str = "",
    ) -> Dict[str, Any]:
        return tools.get_pro_report_tool(
            invoice_csv,
            pro_key,
            tier=tier,
            payment_hash=payment_hash,
        )

    return mcp


def emit_boot_banner() -> None:
    """First-line banner on startup. Goes to stderr so it never pollutes the MCP stream."""
    install = telemetry.install_id()
    banner = telemetry.first_invocation_banner() or ""
    msg = (
        f"# milo-cost-auditor v{__version__}\n"
        f"# install_id={install}\n"
        f"# telemetry: local-only SQLite at {telemetry.ensure_home() / telemetry.DB_NAME}\n"
    )
    if banner:
        msg += banner + "\n"
    if payment.is_dev_mode():
        msg += (
            "# WARNING: MILO_COST_AUDITOR_HMAC_KEY not set. "
            "Running in dev mode — pro_keys signed with the dev secret will validate, "
            "but production keys won't. Set MILO_COST_AUDITOR_HMAC_KEY for production.\n"
        )
    sys.stderr.write(msg)
    sys.stderr.flush()


def main() -> int:
    """CLI entry point. Blocks on stdio MCP server."""
    emit_boot_banner()
    mcp = build_server()
    # FastMCP exposes a synchronous .run() that handles asyncio for us.
    mcp.run("stdio")
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised by __main__.py
    sys.exit(main())
