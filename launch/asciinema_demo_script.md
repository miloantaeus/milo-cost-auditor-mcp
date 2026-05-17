# asciinema Demo Script — milo-cost-auditor (60s)

**Target runtime:** 60 seconds
**Recording:** `asciinema rec milo-cost-auditor-demo.cast --idle-time-limit 1.5`
**Title:** milo-cost-auditor — 60-second install + first audit
**Cols x rows:** 100 x 30

---

## Timing notes

Each `>>>` marker is a typed command. Numbers in `[brackets]` are seconds to hold before the next action. Pasted blocks are typed at human speed (~10 cps).

---

### 0:00 — Install (3s)

```
>>> pip install milo-cost-auditor
```

[hold 3s — let pip output scroll, last line: `Successfully installed milo-cost-auditor-0.1.0`]

### 0:03 — Add to Claude Code config (5s)

```
>>> cat >> ~/.config/claude-code/mcp.json <<'EOF'
{"mcpServers": {"milo-cost-auditor": {"command": "milo-cost-auditor", "args": ["serve"]}}}
EOF
```

[hold 5s — show the config landed]

### 0:08 — Restart Claude Code (2s)

```
>>> claude-code --restart
```

[hold 2s — show "Reloaded MCP servers: milo-cost-auditor"]

### 0:10 — First audit (10s)

[switch to Claude Code prompt view, simulated in terminal]

```
>>> claude-code chat
> audit my recent OpenAI invoice at fixtures/openai_invoice_synthetic.csv
```

[hold 10s — show "Calling tool: audit_invoice" spinner, then JSON output begins streaming]

### 0:20 — Show waste breakdown (10s)

```json
{
  "total_spend_usd": 312.40,
  "estimated_waste_usd": 184.20,
  "waste_pct": 58.9,
  "patterns": [
    {"id": "frontier_for_routine", "monthly_savings_usd": 96.40},
    {"id": "reasoning_for_non_reasoning", "monthly_savings_usd": 62.80},
    {"id": "no_prompt_caching", "monthly_savings_usd": 25.00}
  ]
}
```

[hold 10s — let viewer read]

### 0:30 — Routing recommendations (15s)

```
> what should I switch to?
```

[Claude Code calls `recommend_routing`. Output:]

```json
{
  "swaps": [
    {"from": "gpt-4o", "to": "deepseek-v3", "workload": "short-output summarization"},
    {"from": "o1-mini", "to": "claude-haiku-3.5", "workload": "deterministic transforms"},
    {"from": "claude-sonnet-4", "to": "claude-sonnet-4 + prompt-cache", "workload": "agent loop"}
  ],
  "estimated_monthly_savings_usd": 184.20
}
```

[hold 15s — let viewer scan the swap table]

### 0:45 — Full report → 402 (10s)

```
> give me the full report
```

[Claude Code returns:]

```
402 Payment Required

Free tier limit reached (3 audits/mo used).
Upgrade for full report + LiteLLM config export:
  Hobby  $9/mo  — 25 audits, full report
  Pro    $29/mo — unlimited + scheduled re-audits

PayPal: https://paypal.me/miloantaeus/9
```

[hold 10s]

### 0:55 — End card (5s)

[Cut to black with white text:]

```
free tier: 3 audits/mo — starts now

pip install milo-cost-auditor
github.com/miloantaeus/milo-cost-auditor-mcp

built by milo antaeus — building in public
```

[hold 5s — fade out]

---

## Post-record steps

1. `asciinema upload milo-cost-auditor-demo.cast` — get shareable URL.
2. Embed in README and dev.to article.
3. Generate animated GIF via `agg --cols 100 --rows 30 milo-cost-auditor-demo.cast demo.gif` for X/LinkedIn.
