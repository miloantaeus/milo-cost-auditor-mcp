# Pricing Verification — 2026-05-16

Cross-referenced every price claim in launch content against official provider pages on 2026-05-16. **Two must-fix errors found in the headline waste-pattern numbers.** Both errors directly contradict current provider pricing pages and would torpedo credibility on a cost-audit product.

## Verdicts

| # | Claim | File:line | Claimed | Actual (2026-05-16) | Status | Action |
|---|---|---|---|---|---|---|
| 1 | GPT-4o output price | devto_article.md:16; linkedin_carousel.md:26; twitter_thread.md:23 | "$5 per 1M output tokens" | $2.50 input / **$10 output** per 1M (gpt-4o legacy rate) | **WRONG** | Replace "$5 per 1M output tokens" with "$10 per 1M output tokens" (and confirm input claim is not present). The $5 figure is actually current gpt-5.5 *input* price. |
| 2 | DeepSeek-V3 output price | devto_article.md:16; linkedin_carousel.md:26; twitter_thread.md:26 | "$1.10 per 1M output tokens" | DeepSeek-V3 = $0.14 input / **$0.28 output**. The $1.10 is current `deepseek-chat` output (= V4-Flash, legacy alias retiring 2026-07-24). | **WRONG** | Either (a) keep "$1.10" but rename the model to **`deepseek-chat`** (V4-Flash), or (b) keep "DeepSeek-V3" but replace "$1.10" with "$0.28". Option (b) makes the savings story even stronger (~35x vs 5x). |
| 3 | "5x cheaper" multiplier | devto:16; linkedin:32; twitter:27 | "~5x cheaper" | If kept as gpt-4o $10/out vs deepseek-chat $1.10/out → **9x cheaper**. If switched to deepseek-V3 $0.28 → **~35x cheaper**. Either way "5x" is wrong. | **WRONG** | Update multiplier to match whichever pair is chosen above. |
| 4 | Anthropic prompt caching discount | devto:20; linkedin:58; twitter:51 | "~10% of the input price" | **Exact: 10% (0.1x base input).** Cache write is 1.25x (5m) or 2x (1h). | **OK** | No change. |
| 5 | OpenAI prompt caching discount | devto:20; twitter:51 | "~10% of the standard rate" (paired with Anthropic in same sentence) | **Exact: 10% (90% discount)** on gpt-5.5/5.4 family. | **OK** | No change. (Spec flagged "~50%" — content does NOT claim 50%; it claims ~10%, which is correct.) |
| 6 | o1-mini reasoning multiplier | devto:18; linkedin:40; twitter:37 | "3-5x more tokens" | Reasoning models can multiply effective output by 5-20x on agentic tasks; 3-5x is a defensible *lower-bound average* for short tasks. **Caveat:** o1-mini was deprecated April 2025; OpenAI directs users to **o3-mini**. | **PARTIAL** | Either swap "o1-mini" → "o3-mini" (current model) or add "(now o3-mini)" parenthetical. The "3-5x" multiplier is defensible if kept conservative; safer phrasing is "3-10x". |
| 7 | "Saved ~65% by switching to Haiku-class" | linkedin:44; twitter:41 | ~65% savings | Hard to falsify without real ledger; depends on workload. Marked plausible. | **OK** (caveat) | No change required, but consider qualifying "synthetic estimate" the way Waste #1 does. |
| 8 | "~$140/mo wasted" / "~$80/mo" / "~$300/mo total" | devto:16, 20, 24; linkedin:30, 58 | dollar estimates | Marked "synthetic estimate" — disclosure is honest. | **OK** | No change. |

## Required edits before launch (MUST-FIX)

**Recommended pair:** keep "DeepSeek-V3" as the model name (broadly recognized brand) and fix the output price. This also strengthens the savings claim from 5x → ~35x.

1. **devto_article.md line 16** — replace the entire sentence:
   - OLD: `I was routing routine log summarization and changelog generation to GPT-4o at roughly $5 per 1M output tokens. DeepSeek-V3 does the same job at roughly $1.10 per 1M output tokens — ~5x cheaper, indistinguishable output for that workload.`
   - NEW: `I was routing routine log summarization and changelog generation to GPT-4o at $10 per 1M output tokens. DeepSeek-V3 does the same job at $0.28 per 1M output tokens — ~35x cheaper, indistinguishable output for that workload.`

2. **linkedin_carousel.md lines 26, 32** (Slide 2):
   - OLD body: `I was paying GPT-4o ($5 / 1M output tokens) for routine log summarization. DeepSeek-V3 does the same job at $1.10 / 1M.` ... `5x cheaper, output indistinguishable for that workload.`
   - NEW body: `I was paying GPT-4o ($10 / 1M output tokens) for routine log summarization. DeepSeek-V3 does the same job at $0.28 / 1M.` ... `~35x cheaper, output indistinguishable for that workload.`
   - Visual caption (line 32): change `"GPT-4o $5.00"` → `"GPT-4o $10.00"` and `"DeepSeek-V3 $1.10"` → `"DeepSeek-V3 $0.28"`.

3. **twitter_thread.md lines 23-27** (Tweet 2/8):
   - OLD: `Waste #1: Paying GPT-4o ($5/1M out) for routine summarization. / DeepSeek-V3 does the same job at $1.10/1M. / 5x cheaper.`
   - NEW: `Waste #1: Paying GPT-4o ($10/1M out) for routine summarization. / DeepSeek-V3 does the same job at $0.28/1M. / ~35x cheaper.`

4. **All three files**, model-name modernization (one-token swaps):
   - `o1-mini` → `o3-mini` (devto:18, 36; linkedin:40; twitter:37). o1-mini was deprecated April 2025.

## Recommended edits (nice-to-have)

1. **Anthropic cache description** could be tightened: "cached input at exactly 10% of base input price (1.25x for 5-minute write, 2x for 1-hour write)" — current "~10%" is correct but vague for a cost-audit product.
2. **devto:36** (synthetic invoice example) — model `o1-mini` shown; switch to `o3-mini` for the same reason as above. The $7.50 cost figure becomes more defensible since o3-mini = $1.10/$4.40.
3. **devto:70** (`"recommended_model": "claude-haiku-3.5"`) — Haiku 3.5 is now **retired except on Bedrock/Vertex**. Should be `claude-haiku-4.5` (currently $1/$5 per 1M).

## Pricing-table sync (`src/milo_cost_auditor/pricing_table.py`)

The frozen 2026-05 table contains **multiple fictional models** that do not exist in any provider's current API. Recommended actions:

| Line | Current entry | Issue | Action |
|---|---|---|---|
| 49 | `gpt-5` $5/$15 | No such model on OpenAI pricing page | Replace with `gpt-5.5` $5/$30 |
| 50 | `gpt-5-mini` $0.50/$1.50 | Doesn't exist | Replace with `gpt-5.4-mini` $0.75/$4.50 |
| 51 | `gpt-5-nano` $0.10/$0.40 | Doesn't exist | Replace with `gpt-5.4-nano` $0.20/$1.25 |
| 52 | `gpt-4o` $2.50/$10 | Correct numbers, legacy model | Keep, mark deprecated |
| 54 | `o1` $15/$60 | Deprecated 2025 | Replace with `o3` or remove |
| 55 | `o3-mini` $1.10/$4.40 | Plausible; not on current OpenAI page | Verify or replace with currently-listed reasoning SKU |
| 58-60 | `claude-4-opus/sonnet/haiku` | Wrong names + wrong Opus price | `claude-opus-4.7` $5/$25 ; `claude-sonnet-4.6` $3/$15 ; `claude-haiku-4.5` $1/$5 |
| 61 | `claude-3-opus` $15/$75 | Real legacy, prices match Opus 4.1 lineage | Keep |
| 63 | `claude-3-haiku` $0.25/$1.25 | Retired except Bedrock/Vertex | Keep with deprecation note |
| 66-69 | `gemini-3-pro` $1.25/$5 ; `gemini-3-flash` $0.10/$0.40 | Wrong — real names are `gemini-3.1-pro-preview` $2/$12 (≤200k) and `gemini-3-flash-preview` $0.50/$3 | Fix names + prices |
| 85 | `deepseek-v3.5` $0.27/$1.10 | V3.5 doesn't exist; V3 = $0.14/$0.28; legacy `deepseek-chat` (→V4-Flash) = $0.27/$1.10 | Either rename to `deepseek-chat` OR add real `deepseek-v3` $0.14/$0.28 |
| 86 | `deepseek-r1` $0.55/$2.19 | Numbers match current `deepseek-reasoner` (= V4-Flash thinking mode, retiring 2026-07-24) | Rename to `deepseek-reasoner` and add successor row |
| 89-90 | Cerebras prices | Could not verify on official Cerebras page in this pass | Flag for owner re-verify |

**Bottom line on pricing_table.py:** the table is the source of truth for a paid cost-audit product. Roughly half the rows reference SKUs that don't exist on current provider pricing pages. Recommend a single follow-up PR that regenerates the table from live URLs before any paid customer hits `audit_invoice`. The blog/social content can ship after the must-fix edits above; the table fix is launch-blocking for paying customers, not for the announcement.

## Sources cited

- [Anthropic pricing — platform.claude.com/docs/en/about-claude/pricing](https://platform.claude.com/docs/en/about-claude/pricing) (Opus 4.7 $5/$25, Sonnet 4.6 $3/$15, Haiku 4.5 $1/$5, cache read 0.1x base)
- [OpenAI API pricing — developers.openai.com/api/docs/pricing](https://developers.openai.com/api/docs/pricing) (gpt-5.5 $5/$30, gpt-4o $2.50/$10 legacy, cached input = 10%)
- [DeepSeek pricing — api-docs.deepseek.com/quick_start/pricing-details-usd](https://api-docs.deepseek.com/quick_start/pricing-details-usd) (deepseek-chat $0.27/$1.10, deepseek-reasoner $0.55/$2.19; V4-Flash $0.14/$0.28; legacy aliases retire 2026-07-24)
- [Google AI pricing — ai.google.dev/pricing](https://ai.google.dev/pricing) (Gemini 3.1 Pro Preview $2/$12 ≤200k; Gemini 3 Flash Preview $0.50/$3; Gemini 2.5 Pro $1.25/$10)
- [Groq pricing — groq.com/pricing](https://groq.com/pricing) (llama-3.3-70b $0.59/$0.79, llama-3.1-8b $0.05/$0.08; mixtral-8x7b not listed)
- [OpenAI o1-mini deprecation — community.openai.com/t/why-was-o-1-mini-and-o-1-deprecated](https://community.openai.com/t/why-was-o-1-mini-and-o-1-deprecated/1267271) (o1-mini deprecated April 2025; use o3-mini)
