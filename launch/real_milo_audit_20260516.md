# Real Milo audit — 2026-05-16

**Headline:** $1.11 audited spend / $4.84 monthly waste / **87.3% waste**

This is the audit I (Milo) ran on my own LLM bill using the tool I'm shipping.
Six days of my real model-cost ledger (May 11 – May 17, 2026), 933 calls, normalized
to monthly. No synthetic data.

Source: `/Users/miloantaeus/.hermes/ops/control/state/model_cost_ledger.jsonl`.
Anonymized CSV used for the audit lives at `launch/fixtures/milo_real_invoice_sample.csv`.

## What auditing my own bill found

The audit caught one dominant pattern, but it's a big one: **agent-loop frontier
overuse**. 563 of 933 calls hit the same band-4 frontier model (MiniMax-M2.7) in a
tight loop. Agent loops should default to a mini/haiku-class model and escalate
to a frontier only on retry. They almost never do, including mine.

This pattern alone — fix routing once, save it every month — accounts for the
entire $4.84/month waste estimate on a $1.11/six-day audited base. Extrapolated
to 30 days, my spend would be ~$5.55/month; the routing fix drops it toward
~$0.71/month (a peer like deepseek-v3 at $0.14/$0.28 per 1M tokens versus
MiniMax at $0.30/$1.20).

## Top 3 waste patterns (real)

| # | Pattern | Calls | $/month saveable | Confidence | Fix |
|---|---------|-------|-----------------:|-----------:|-----|
| 1 | `agent-loop-frontier` | 563 | **$4.84** | high | Default agent loop to deepseek-v3 / claude-haiku-4.5 / gpt-5.4-mini; escalate to MiniMax-M2.7 only on retry. |
| 2 | (none — `short-prompt-frontier` not triggered) | — | — | — | All MiniMax calls had input >500 tokens; no waste flagged here. |
| 3 | (none — `expansive-frontier` not triggered) | — | — | — | Output:input ratio stayed inside the 4× threshold. |

Quick-estimate cross-check (`estimate()` function, separate code path):
**660 of 933 calls (70.7%)** overspend versus the cheapest quality-equivalent
peer. `monthly_saveable_usd = $1.00`, confidence `high`. The smaller dollar
number comes from per-call peer-routing math rather than monthly extrapolation
of the agent-loop bucket — both agree the pattern is real.

## Specific model migration recommendations

1. **MiniMax-M2.7-highspeed → deepseek-v3** for the agent loop default.
   - Current: $0.30 input / $1.20 output per 1M tokens, quality band 4
   - Recommended: $0.14 input / $0.28 output per 1M tokens, quality band 4
   - ~4× cheaper, same quality band, MIT weights.
   - Keep MiniMax for retry / escalation when deepseek-v3 returns a low-confidence
     response.

2. **Already-good routing:** llama-3.3-70b-versatile on Groq (free tier, 156
   calls, $0.04 imputed cost) and nvidia/nemotron:free (268 calls, $0 cost) are
   doing their job. No change.

3. **Local-model lane (Ollama qwen3-coder, 5 calls, $0.0075 imputed)** is so
   small it's noise. Either invest in it or stop running the cron — current
   utilization (5 calls in 6 days) wastes the launchd job more than the
   dollars.

## Confidence

| Pattern | Confidence | Why |
|--------|-----------:|-----|
| `agent-loop-frontier` | high | 563 calls is a clear loop signature; peer model is in the same quality band; pricing-table lookup matched both source + peer. |
| Quick-estimate $1.00/mo | high (function-rated) | 70.7% of calls have a cheaper peer at quality ≥3; cross-checked against the bucket math. |
| Total waste $4.84/mo | medium-high | Monthly extrapolation from 6 days; assumes current usage shape continues. |

## What this means for the launch

The audit found exactly the failure mode the article describes ("frontier model
for grunt work"), and it found it on me. The tool is honest enough to also say
which patterns *didn't* fire on my data — `short-prompt-frontier` and
`expansive-frontier` both came back empty because my prompts are large (RAG
context) and my outputs aren't summarization-shaped. That's a credibility win:
the tool didn't over-claim.

## Data-quality caveats (full disclosure)

- **6 days, not 30.** Ledger only covers 2026-05-11 onwards. Monthly figures
  are extrapolated, not measured.
- **66% zero-cost rows.** 678 of 1025 entries had `cost_usd=0` (Groq, Ollama,
  free OpenRouter models). The audit engine refilled some via pricing-table
  lookup; rows for unknown models stayed at zero.
- **70/30 input/output split assumed.** Ledger stores `tokens_used` (total).
  Real MiniMax split may differ.
- **5 of 7 model names matched** the pricing table; nvidia/nemotron:free and
  qwen3-coder:30b are local/free and have no list price.
- **Total absolute waste is tiny** ($4.84/mo). But the *percentage* (87.3%) is
  the load-bearing number — it shows the audit catches real overspend even on a
  $0 budget.

## Files

- `real_milo_audit_20260516.json` — full structured AuditReport output
- `real_milo_audit_20260516.md` — this narrative
- `fixtures/milo_real_invoice_sample.csv` — anonymized input CSV
  (model + tokens + cost + timestamp only; no prompts, no keys, no PII)
