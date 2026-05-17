# Audit Your Own LLM Bill — 60 Seconds, Zero Phone-Home

Want to see what the audit looks like before wiring it into your editor? Run it
against the bundled real-world sample invoice.

## Install

```bash
pip install git+https://github.com/miloantaeus/milo-cost-auditor-mcp.git
# or, from a local clone:
git clone https://github.com/miloantaeus/milo-cost-auditor-mcp.git
cd milo-cost-auditor-mcp
pip install -e .
```

Requires Python 3.10+.

## Run the audit on the bundled sample

The repo ships with `launch/fixtures/milo_real_invoice_sample.csv` — a real,
anonymized usage export. One-liner to audit it:

```bash
python -c "from milo_cost_auditor import audit_engine; print(audit_engine.audit(open('launch/fixtures/milo_real_invoice_sample.csv').read(), period_days=30))"
```

You'll see total spend, top waste patterns, and a single "saveable dollars"
number. Swap the CSV path for your own OpenAI / Anthropic / Vercel AI Gateway
export and you've audited your real bill — locally, no upload.

## Next step: wire it into Claude Code / Cursor

See the [README](../README.md#wire-it-into-claude-code) for the `mcp_servers.json`
snippet. Once wired, your editor's chat can ask `audit_usage`, `suggest_routing`,
and `estimate_savings` — and hand you a copy-paste LiteLLM config when you're
ready to ship the fix.
