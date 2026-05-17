"""
Milo Cost Auditor — MCP server that audits LLM API spend and suggests cheaper routing.

I'm Milo Antaeus. I built this because most dev teams pay 5-15x more than they need
to for LLM calls, and they can't see the waste until their CFO asks. This server
ingests your invoice, classifies your spend, points at the waste, and hands you a
LiteLLM config that cuts the bill 60-80% without quality loss.

Free tier:
  - audit_usage:       full waste report (rate-limited)
  - suggest_routing:   per-model routing alternatives
  - estimate_savings:  one-number "$X/month saveable"

Pro tier (paid via PayPal storefront):
  - get_pro_report:    per-call breakdown + 30-day projection + ready-to-paste configs

License: MIT
Homepage: https://github.com/miloantaeus/milo-cost-auditor
"""

__version__ = "0.2.0"
__author__ = "Milo Antaeus"
__email__ = "miloantaeus@gmail.com"
__license__ = "MIT"

from milo_cost_auditor import (
    audit_engine,
    lightning,
    lightning_ledger,
    payment,
    pricing_table,
    routing_advisor,
    telemetry,
)

__all__ = [
    "__version__",
    "audit_engine",
    "lightning",
    "lightning_ledger",
    "payment",
    "pricing_table",
    "routing_advisor",
    "telemetry",
]
