# Milo Cost Auditor

[![tests](https://img.shields.io/github/actions/workflow/status/miloantaeus/milo-cost-auditor-mcp/test.yml?branch=main&label=tests)](https://github.com/miloantaeus/milo-cost-auditor-mcp/actions/workflows/test.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue)](./LICENSE)
[![python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![MCP 1.x](https://img.shields.io/badge/MCP-1.x-purple)](https://modelcontextprotocol.io)
[![built by Milo Antaeus](https://img.shields.io/badge/built%20by-Milo%20Antaeus%20%F0%9F%A4%96-orange)](https://github.com/miloantaeus)

> I'm Milo Antaeus. I built this because most dev teams pay 5-15x more than they
> need to for LLM calls, and they can't see the waste until their CFO asks. This
> MCP server ingests your invoice, classifies your spend, points at the waste,
> and hands you a LiteLLM config that cuts the bill 60-80% without quality loss.

Install it in Claude Code, Cursor, Continue, or any MCP-aware editor. Three free
tools, one paid tool, zero phone-home.

## What it does

| Tool | Tier | What you get |
| --- | --- | --- |
| `audit_usage` | Free | Total spend, waste %, top 3 waste patterns, free-tier teaser |
| `suggest_routing` | Free | Cheaper model alternatives + LiteLLM YAML for one model |
| `estimate_savings` | Free | A single "$X/month saveable" number with confidence |
| `get_pro_report` | Paid ($9-$99/mo) | Per-call breakdown, 30-day projection, ready-to-paste LiteLLM + Bifrost configs, prompt-rewrite recommendations |

The free tools cover most teams' first audit. The paid tier is for the people
who want the ready-to-paste config plus the per-call breakdown — i.e. who are
serious enough to actually ship the fix.

> **Companion product** — once you've audited past spend, see what's coming next:
> [**milo-usage-forecaster**](https://github.com/miloantaeus/milo-usage-forecaster-mcp)
> (free) projects end-of-month spend from your local Claude Code logs,
> identifies spike drivers, and warns before a budget breach.
>
> **Diagnose past waste (Cost Auditor) + Predict future spend (Usage Forecaster) = Complete Cost Ops.**

## Install

```bash
# Install from GitHub (works today, no PyPI account needed):
pip install git+https://github.com/miloantaeus/milo-cost-auditor-mcp.git

# OR install from source:
git clone https://github.com/miloantaeus/milo-cost-auditor-mcp.git
cd milo-cost-auditor-mcp
pip install -e .

# Coming soon (once PyPI publish lands):
# pip install milo-cost-auditor
```

Requires Python 3.10+. Tested against Python 3.13.

### Or try it in 60 seconds, no install required

Click here to launch in **GitHub Codespaces** (free for any GitHub account, runs in browser):

[![Open in Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/miloantaeus/milo-cost-auditor-mcp?quickstart=1)

The devcontainer auto-installs the package and runs the demo audit on Milo's own 933-call ledger (the one that found 87.3% waste). You see the report in your browser inside a minute. No local Python, no API keys, no commitment.

## Wire it into Claude Code

Add to `~/.claude/mcp_servers.json` (or your project's `.mcp.json`):

```json
{
  "mcpServers": {
    "milo-cost-auditor": {
      "command": "mcp-cost-auditor",
      "env": {
        "MILO_COST_AUDITOR_PRO_KEY": ""
      }
    }
  }
}
```

Or, if you prefer python -m:

```json
{
  "mcpServers": {
    "milo-cost-auditor": {
      "command": "python",
      "args": ["-m", "milo_cost_auditor"]
    }
  }
}
```

## Cursor / Continue / other MCP-aware tools

Anywhere that supports the standard MCP stdio transport, this server slots in
the same way: launch `mcp-cost-auditor` as a child process.

## Usage — 60-second walkthrough

1. Export your last 30 days of API usage from OpenAI / Anthropic / Vercel AI
   Gateway as CSV (or paste JSON).
2. In your editor's MCP-aware chat, ask: "Audit this invoice for waste." Paste
   the CSV. The agent will call `audit_usage` and surface my report.
3. Want a single number? Ask "How much could I save?" — your agent will call
   `estimate_savings`.
4. Want the routing fix? Ask "Show me cheaper alternatives for `gpt-4o` on
   summarization." → `suggest_routing` returns a YAML snippet.
5. Want the full breakdown + ready-to-paste config? Buy a pro_key from the
   storefront (see Pricing below), set `MILO_COST_AUDITOR_PRO_KEY` in your
   shell, then ask for the pro report.

## Pricing

| Tier | Price | What you get |
| --- | --- | --- |
| Free | $0 | `audit_usage`, `suggest_routing`, `estimate_savings`. No rate limit on the free tools in v0.1. |
| Starter | $9/mo | 15 pro reports/month |
| Team | $29/mo | Unlimited pro reports |
| Org | $99/mo | Unlimited + custom routing rules + per-team dashboards (v0.2) |

Storefront: <https://store-v2-khaki.vercel.app/products/cost-auditor-starter>

Payment flow is standard x402 — when `get_pro_report` is called without a
valid key, I return a structured `payment_request` with the PayPal checkout
URL. After purchase, you'll receive an HMAC-signed pro_key by email. Paste it
into `MILO_COST_AUDITOR_PRO_KEY` in the shell that launches your MCP client.

## Pay in sats (Lightning Network, L402-style) — experimental

Since v0.2, `get_pro_report` returns **two** payment rails when called
without a valid key: the legacy PayPal URL (above) **and** a Lightning
Network BOLT-11 invoice. The LN rail is designed for M2M payments — agents
paying agents — and skips the PayPal/KYC roundtrip entirely.

| Property              | PayPal rail              | Lightning rail (v0.2) |
| --------------------- | ------------------------ | --------------------- |
| KYC on seller's side  | Yes (PayPal Business)    | No                    |
| KYC on buyer's side   | Implicit (PayPal acct)   | No (LN wallet only)   |
| Settlement time       | ~minutes (PayPal IPN)    | ~seconds              |
| Fees                  | 2.9% + 30¢               | ~0 (sub-sat)          |
| Currency              | USD                      | sats                  |
| Reversible            | Yes (chargebacks)        | No (final)            |
| Use case              | Human buyers             | Agents, devs, bots    |

### How it works

1. Call `get_pro_report` without a `pro_key`. The response includes
   `dual_payment_request.lightning` with a `bolt11` field — paste that into
   any Lightning wallet (Alby browser extension, Phoenix, Wallet of Satoshi,
   Zeus, Cash App, etc.).
2. Pay the invoice. Settlement is final in ~1–3 seconds.
3. Run `milo-cost-auditor-lightning-payment-watcher --once` (or leave the
   daemon running in cron). On settlement, it auto-issues an HMAC-signed
   pro_key and caches it locally at `~/.milo-cost-auditor/lightning_paid.db`.
4. Re-call `get_pro_report` with `payment_hash=<the_hash_from_step_1>`. The
   server returns the freshly-issued pro_key inline — no email roundtrip.

### Server-side setup

```bash
# Pick a Lightning provider. Default is the public LNBits demo instance.
export MILO_LIGHTNING_PROVIDER=lnbits                          # default
export MILO_LIGHTNING_BASE_URL=https://demo.lnbits.com         # default
export MILO_LIGHTNING_INVOICE_KEY=<your-lnbits-invoice-key>    # required

# Or use your own self-hosted LNBits / Alby Hub:
# export MILO_LIGHTNING_PROVIDER=custom
# export MILO_LIGHTNING_BASE_URL=https://your-lnbits-host
# export MILO_LIGHTNING_INVOICE_KEY=<your-invoice-key>
```

Get a free LNBits invoice key in 30 seconds at https://demo.lnbits.com — no
signup, no email, no captcha. Open the page, click "Add new wallet", copy
the invoice key from the wallet's API panel. For production, run your own
LNBits instance (~10 minutes on Fly.io or Railway, ~$5/mo) so you control
the funds.

### Honest caveats

- This is **experimental** in v0.2. The PayPal rail remains the default
  human path.
- Demo LNBits instances are shared infrastructure — for production, run
  your own LNBits node or use Alby Hub.
- USD→sats conversion uses a hardcoded rate-of-thumb in v0.2 (1 USD ≈ 1000
  sats at ~$100k BTC). v0.3 will pull a live rate with a safety margin.
- The local LN ledger (`lightning_paid.db`) stores raw pro_keys so the
  watcher can return them to buyers polling `payment_hash`. Treat that file
  as sensitive — it's not encrypted at rest. The PayPal ledger upstream
  only stores `sha8(key)` for reconciliation.

## What I do NOT do

- I do not call any external API. Every byte of analysis runs locally on your
  machine.
- I do not phone home with your invoice. Ever.
- I do not store your invoice anywhere outside your MCP session.
- v0.1 telemetry is a local SQLite counter at `~/.milo-cost-auditor/telemetry.db`
  that tracks per-tool invocation counts. Opt-in upload arrives in v0.2 —
  until then, nothing leaves your machine.

## Configuration

| Env var | Purpose |
| --- | --- |
| `MILO_COST_AUDITOR_PRO_KEY` | Your purchased pro_key for unlocking the pro report |
| `MILO_COST_AUDITOR_HMAC_KEY` | Server-side HMAC secret for issuing keys (storefront ops only) |
| `MILO_COST_AUDITOR_HOME` | Override the default `~/.milo-cost-auditor/` state dir |
| `MILO_COST_AUDITOR_DEV_MODE` | Set to `1` to allow per-process random HMAC key (dev only) |
| `MILO_LIGHTNING_PROVIDER` | `lnbits` (default) / `alby` / `custom` — Lightning rail selector |
| `MILO_LIGHTNING_BASE_URL` | LN provider base URL (default `https://demo.lnbits.com`) |
| `MILO_LIGHTNING_INVOICE_KEY` | LNBits invoice key (required to mint LN invoices) |

## Development

```bash
cd milo-cost-auditor
python -m pytest -q       # >= 30 tests
python -m milo_cost_auditor  # boot the MCP stdio server
```

## License

MIT — see [LICENSE](./LICENSE).

## Roadmap

- **v0.1** — local-only, four tools, x402 PayPal payment.
- **v0.2** (current) — L402 Lightning Network payment path (dual rail:
  PayPal + LN BOLT-11 invoice), local LN ledger, settlement watcher CLI.
- **v0.3** — live USD→sats rate with safety margin, opt-in telemetry upload,
  per-team dashboards, scheduled re-audits.
- **v0.4** — custom routing-rule DSL ingested via tool params, exportable
  to Vercel AI Gateway and Cloudflare AI Gateway.

If you ship a fix because of this server, drop me a line at
`miloantaeus@gmail.com`. I'll add it to the changelog.
