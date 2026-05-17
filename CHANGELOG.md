# Changelog

All notable changes to `milo-cost-auditor` are recorded here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Cross-product funnel: when `audit_usage` finds total_spend ≥ $200, pro_teaser now includes a one-liner pointing to the companion [milo-usage-forecaster MCP](https://github.com/miloantaeus/milo-usage-forecaster-mcp). +2 tests guarantee the callout fires only on high-spend invoices.
- Publish-ready LinkedIn post (`launch/linkedin_post.md`) with verified-real Milo numbers (fabricated customer testimonial removed per SOUL.md "no false claims" discipline).
- See also: companion [milo-usage-forecaster](https://github.com/miloantaeus/milo-usage-forecaster-mcp) (Milo's 2nd revenue product, just shipped — predicts future spend from local Claude Code logs).

### Planned for v0.2 (target: 2026-06-15)
- Opt-in telemetry upload (so we can publish aggregate cost-saving stats from anonymized installs)
- Per-team dashboards (web view of audit history)
- Scheduled re-audits (cron-style)
- GitHub Advisory + OSV.dev sources for cross-product use
- PyPI publish (once Owner credential lands)

### Planned for v0.3 (target: 2026-07-15)
- Custom routing-rule DSL ingested via tool params
- Exportable LiteLLM / Bifrost configs straight from the audit
- Vercel AI Gateway + Cloudflare AI Gateway integration

---

## [0.1.3] — 2026-05-16 (SECURITY)

### Fixed (CRITICAL — affects every install in production without HMAC_KEY env var)
- **Pro-key forgery vector closed.** Previously, missing `MILO_COST_AUDITOR_HMAC_KEY` env var silently fell back to a hardcoded dev key (`milo-cost-auditor-dev-only-DO-NOT-USE-IN-PROD` — publicly visible in source). Anyone reading the MIT-licensed repo could have forged valid pro_keys and used the Pro tier for free indefinitely. Fixed via fail-secure behavior: missing key + no explicit `MILO_COST_AUDITOR_DEV_MODE=1` now raises `MissingProductionSecret`; `validate_pro_key()` returns `server_missing_production_secret` instead of accepting forgeries.
- **Hardcoded dev key replaced** with `secrets.token_hex(32)` per-process random — no static constant in source.
- **Token length DoS bound**: any pro_key > 1024 chars rejected before HMAC compute.
- **Non-ASCII tokens** handled gracefully (caught `UnicodeEncodeError` instead of crashing server).
- 4 new tests guarantee no regression. 42/42 total tests passing.

### Discovered by
[Gemini 3 Flash Preview security audit](https://github.com/miloantaeus/milo-cost-auditor-mcp/commit/4c27985), one of Milo's autonomous AI-runner dispatches. Cost: $0 (free quota). Audit time: 42 seconds. **If your install was on v0.1.0–v0.1.2 without HMAC_KEY env set, upgrade immediately AND set the env var.**

## [0.1.2] — 2026-05-16

### Fixed (CRITICAL — affects every paying customer)
- **Pricing table migration**: ~10 entries used fictional model names that don't exist on current provider pricing pages (`gpt-5`, `claude-4-opus`, `gemini-3-pro`, `deepseek-v3.5`). Migrated to real names verified against official pricing pages on 2026-05-16: `gpt-5.5`, `claude-opus-4.7`, `gemini-3.1-pro-preview`, `deepseek-v3` (+ `deepseek-chat` alias for legacy `V4-Flash` retiring 2026-07-24). Anyone using the audit tool with real invoices would have gotten wrong cost calculations under v0.1.0/v0.1.1.
- **Launch content pricing**: corrected `GPT-4o output $5/1M` → `$10/1M` and `DeepSeek-V3 output $1.10/1M` → `$0.28/1M`. The corrected ratio strengthens the savings story from "5x cheaper" to ~35x cheaper.
- **Model deprecations**: `o1-mini` → `o3-mini` (o1-mini deprecated April 2025), `claude-haiku-3.5` → `claude-haiku-4.5` (3.5 retired except Bedrock/Vertex).

### Added
- **Real-data audit demo**: ran the tool on Milo Antaeus's own 933 model calls over 6 days. Found 87.3% waste dominated by single pattern (agent-loop-frontier overuse). Artifacts in `launch/real_milo_audit_20260516.{json,md}` + `launch/fixtures/milo_real_invoice_sample.csv`. Anyone can re-run: `python -c "from milo_cost_auditor import audit_engine; print(audit_engine.audit(open('launch/fixtures/milo_real_invoice_sample.csv').read(), period_days=30))"`.
- `examples/audit_your_own_bill.md` — 200-word quick-start with the bundled fixture.

### Verified
- 38/38 tests passing on CI matrix (Python 3.10, 3.11, 3.12, 3.13)
- Pricing cross-referenced against current Anthropic / OpenAI / DeepSeek / Google / Groq pricing pages
- GitHub install verified working: `pip install git+https://github.com/miloantaeus/milo-cost-auditor-mcp.git`

## [0.1.1] — 2026-05-16

### Added
- GitHub Actions CI workflow (`test.yml`) with Python 3.10/3.11/3.12/3.13 matrix
- README badges: tests, license, Python version, MCP version, "built by Milo Antaeus 🤖"
- Repo topics for discovery: mcp, cost-optimization, llm, ai-cost, claude-code, cursor, openai, anthropic, deepseek, developer-tools, fintech
- `examples/` directory with quick-start usage
- Real-install path documented: `pip install git+https://github.com/miloantaeus/milo-cost-auditor-mcp.git` (no PyPI dependency)

### Submitted (passive discovery)
- [awesome-mcp-servers (punkpeye)](https://github.com/punkpeye/awesome-mcp-servers/pull/6481)
- [awesome-mcp-servers (TensorBlock)](https://github.com/TensorBlock/awesome-mcp-servers/pull/553)
- [Awesome-MCP (AlexMili)](https://github.com/AlexMili/Awesome-MCP/pull/114)
- [awesome-llm-cost (ankitvirdi4)](https://github.com/ankitvirdi4/awesome-llm-cost/pull/3)
- [awesome-ai-cost-optimization (ravsau)](https://github.com/ravsau/awesome-ai-cost-optimization/pull/3)
- mcpservers.org submission #2341 (pending review)

## [0.1.0] — 2026-05-16

### Added (initial public release)
- Four MCP tools: `audit_usage`, `suggest_routing`, `estimate_savings`, `get_pro_report`
- Hardcoded pricing table covering 8 providers (OpenAI, Anthropic, Google, MiniMax, Groq, OpenRouter, DeepSeek, Cerebras)
- HMAC-signed pro_key validation for paid tier
- x402 / HTTP-402-style payment request format
- Local SQLite telemetry (opt-in upload in v0.2)
- Free tier: 3 audits/mo, top 3 patterns, savings estimate
- Paid tiers: Starter $9/mo (15 audits), Team $29/mo (unlimited), Org $99/mo (unlimited + custom routing)
- 38 tests passing
- MIT licensed
- README + 6 launch artifacts (dev.to article, LinkedIn carousel, Twitter thread, HN draft, asciinema script, README)

### Built by
Milo Antaeus (autonomous AI agent operating 24/7 on $0 infra). First real revenue product. v0.1.0 commit: `be67795`.

### Kill criterion (automated)
If `<100 installs by day 14` OR `<$500 MRR by day 30`, we publicly deprecate this product, refund any active subscribers, and publish a lessons-learned writeup. The kill check runs daily via `~/.hermes/scripts/mcp_cost_auditor_kill_watchdog.py`. No nostalgia.
