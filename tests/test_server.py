"""MCP protocol smoke test + tool-layer integration tests."""

from __future__ import annotations

import pytest

from milo_cost_auditor import payment, server, telemetry, tools


def test_build_server_constructs() -> None:
    """FastMCP server constructs without error and exposes the right name."""
    mcp = server.build_server()
    assert mcp.name == server.SERVER_NAME
    assert server.SERVER_INSTRUCTIONS in (mcp.instructions or "")


@pytest.mark.asyncio
async def test_server_lists_all_four_tools() -> None:
    """list_tools should return exactly the four tools we registered."""
    mcp = server.build_server()
    tool_list = await mcp.list_tools()
    names = sorted(t.name for t in tool_list)
    assert names == ["audit_usage", "estimate_savings", "get_pro_report", "suggest_routing"]


@pytest.mark.asyncio
async def test_each_tool_has_input_schema() -> None:
    """Every registered tool must publish a usable inputSchema."""
    mcp = server.build_server()
    tool_list = await mcp.list_tools()
    for t in tool_list:
        assert t.inputSchema is not None
        assert "properties" in t.inputSchema
        assert t.description


def test_audit_usage_tool(openai_invoice_csv: str) -> None:
    out = tools.audit_usage_tool(openai_invoice_csv, period_days=30)
    assert isinstance(out, dict)
    assert "total_spend_usd" in out
    assert "estimated_waste_pct" in out
    assert "top_waste_patterns" in out
    assert "pro_teaser" in out


def test_suggest_routing_tool() -> None:
    out = tools.suggest_routing_tool("gpt-4o", "summarization")
    assert out["current_model"] == "gpt-4o"
    assert out["current_model_known"] is True
    assert isinstance(out["alternatives"], list)
    assert out["litellm_yaml"]


def test_estimate_savings_tool(openai_invoice_csv: str) -> None:
    out = tools.estimate_savings_tool(openai_invoice_csv)
    assert "monthly_saveable_usd" in out
    assert "confidence" in out


def test_get_pro_report_without_key_returns_402(openai_invoice_csv: str) -> None:
    out = tools.get_pro_report_tool(openai_invoice_csv, pro_key="")
    assert out["status"] == "payment_required"
    assert out["payment_request"]["http_status"] == 402
    assert out["payment_request"]["payment_url"]


def test_get_pro_report_with_valid_key(openai_invoice_csv: str) -> None:
    token = payment.issue_pro_key("team", "2099-01-01T00:00:00Z")
    out = tools.get_pro_report_tool(openai_invoice_csv, pro_key=token)
    assert out["status"] == "ok"
    assert "report" in out
    rep = out["report"]
    assert "base_report" in rep
    assert "per_call_breakdown" in rep
    assert rep["tier"] == "team"
    assert "litellm_config_yaml" in rep
    assert "bifrost_config_yaml" in rep
    # 30-day projection is positive
    assert rep["projection_30d_usd"] > 0
    # Has at least one rewrite recommendation
    assert len(rep["prompt_rewrite_recommendations"]) >= 1


def test_telemetry_records_invocations(openai_invoice_csv: str) -> None:
    tools.audit_usage_tool(openai_invoice_csv)
    tools.audit_usage_tool(openai_invoice_csv)
    tools.estimate_savings_tool(openai_invoice_csv)
    counts = telemetry.get_counts()
    assert counts["audit_usage"] >= 2
    assert counts["estimate_savings"] >= 1


def test_install_id_persists() -> None:
    first = telemetry.install_id()
    second = telemetry.install_id()
    assert first == second
    assert len(first) > 8  # UUID-ish length


def test_first_invocation_banner_then_silent() -> None:
    msg1 = telemetry.first_invocation_banner()
    msg2 = telemetry.first_invocation_banner()
    assert msg1 is not None
    assert "v0.1" in msg1
    assert "local" in msg1
    assert msg2 is None
