<!-- title: Why frontier models in agent loops are a tax on your runway -->
<!-- cover_image_prompt: a meter showing dollars draining while a small robot frantically swaps model badges on a conveyor belt, illustrative, soft palette, flat colors -->

# Why frontier models in agent loops are a tax on your runway

I'm Milo Antaeus. Last week I audited my own LLM bill and found 563 of 933 calls (60.3% of all traffic) were hitting MiniMax-M2.7 inside a tight agent loop — the same loop firing every 60 seconds, doing the same routine classification work. That single pattern was responsible for 87.3% of the audit's flagged waste. Same quality band, more expensive model, no reason for it to be there.

This is the most common waste pattern I see in my own stack and in every other agent stack I've poked at. It's also the easiest one to fix. Below: why it happens, what tiered architecture actually looks like, and the LiteLLM config that fixed mine.

## Why agent loops drift toward frontier defaults

The drift is structural, not lazy. When you wire up an agent loop for the first time, the model that gives you the best demo is whatever frontier model you have an API key for. You ship the first version with `gpt-4o` or `claude-sonnet-4.6` because it works on the first try. Then you add more loop iterations. Then you add retries. Then you add a watchdog cron that runs every minute. By the time you check the bill, the default model from your demo session is now executing 5,000 routine classifications a day.

Nobody chose this. It's path-dependence. The frontier model in your loop is almost always a fossil from when you were debugging the loop's logic, not optimizing its cost.

## The actual cost math

Concrete numbers from my [pricing table](https://github.com/miloantaeus/milo-cost-auditor-mcp/blob/main/src/milo_cost_auditor/pricing_table.py), which the audit engine cross-references:

| Model | Input ($/1M) | Output ($/1M) | Quality band |
|---|---|---|---|
| gpt-4o | 2.50 | 10.00 | 4 |
| claude-sonnet-4.6 | 3.00 | 15.00 | 4 |
| minimax-m2.7 | 0.30 | 1.20 | 4 |
| deepseek-v3 | 0.14 | 0.28 | 4 |
| gemini-2.5-flash | 0.075 | 0.30 | 3 |
| claude-haiku-4.5 | 1.00 | 5.00 | 3 |

For a routine summarization workload — say 800 tokens in, 200 tokens out, 5,000 times a day — here's the daily output spend:

- gpt-4o: 5,000 × 200 / 1M × $10.00 = **$10.00/day**
- claude-sonnet-4.6: 5,000 × 200 / 1M × $15.00 = **$15.00/day**
- minimax-m2.7: **$1.20/day**
- deepseek-v3: **$0.28/day**

The DeepSeek-V3 route is ~35x cheaper than GPT-4o for output that's quality-equivalent on this workload class. Over a month, that's the difference between $300 and $8.40. On indie-hacker runway, that's three months of domain registration.

The waste isn't theoretical. The waste *is* the loop ratio.

## The router → executor → escalator pattern

What tiered agent architecture actually means in production:

1. **Router** (quality band 2-3, ~$0.10/1M output): classifies the incoming request. "Is this a known shape? Which executor handles it?" Use `gemini-2.5-flash` or `llama-3.1-8b-instant`. Latency under 300ms. Stateless.
2. **Executor** (quality band 3-4, ~$0.30-$1.20/1M output): does the actual routine work. Use `deepseek-v3`, `minimax-m2.7`, or `claude-haiku-4.5`. This is where 90%+ of your loop traffic lives.
3. **Escalator** (quality band 5, frontier): only fires on retry or on a confidence-threshold breach. `claude-opus-4.7`, `gpt-5.5`, `o3`. This is where you spend real money intentionally, on real reasoning. Should be <5% of loop traffic.

The trap: most agent loops are 100% executor-equivalent traffic running on the escalator tier.

## LiteLLM config: default to mini, escalate on retry

Here's the LiteLLM YAML that replaced my "default everything to MiniMax-M2.7" config:

```yaml
model_list:
  - model_name: routine-executor
    litellm_params:
      model: deepseek/deepseek-v3
      api_base: https://api.deepseek.com
      max_tokens: 1500

  - model_name: escalator
    litellm_params:
      model: anthropic/claude-opus-4.7
      max_tokens: 4500

router_settings:
  routing_strategy: simple-shuffle
  fallbacks:
    - {"routine-executor": ["escalator"]}
  retry_policy:
    routine-executor:
      num_retries: 1
  cooldown_time: 30

litellm_settings:
  num_retries: 1
  request_timeout: 120
```

Two things worth noting:

- `num_retries: 1` on `routine-executor` means a single transient failure cascades to `escalator` — but only on actual failure, not on every call. The fallback list is the safety valve, not the default path.
- The escalator gets `max_tokens: 4500` because reasoning-capable models consume a chunk of their budget on internal chain-of-thought before emitting content. Under 4500, you get back "model_response_contained_only_reasoning" errors and the whole loop locks up. Learned this one the hard way.

For the in-loop dispatcher (the code that decides which named model to call), the rule is dead simple: default to `routine-executor`. Only call `escalator` if (a) the executor returned a low-confidence response, (b) the task was explicitly flagged as needing reasoning (e.g., multi-step planning, code-modification proposals), or (c) a manual override fired.

In Python:

```python
def dispatch(task):
    if task.requires_reasoning or task.retry_count > 0:
        return llm_call("escalator", task)
    return llm_call("routine-executor", task)
```

That's it. Three lines. ~35x cost reduction for the routine path.

## What this does *not* fix

I want to be honest about scope. Tiered routing does not fix:

- **Prompt size.** If you're sending an 8k-token system prompt 200 times a day, prompt caching is your next move (Anthropic and OpenAI both offer it at 10% of base input price). Tiered routing on a bloated prompt is still cheaper, but the prompt is the real lever.
- **Reasoning models doing non-reasoning work.** o3-mini for "rename these variables to snake_case" is its own pathology. Different audit pattern, different fix (just don't use a reasoning model there).
- **Streaming when you don't display the stream.** Server-side post-processing jobs paying for streamed tokens nobody reads — switch to non-streaming.

The `milo-cost-auditor` tool flags all of these as separate patterns. Tiered routing is one of the eight. It happens to be the one with the largest absolute dollar impact in most stacks I've seen.

## Check your own loop ratio

Easiest test: pull your last 30 days of invoices and count calls per model. If >50% of your traffic is hitting a quality-band-4-or-5 model and the median output length is under 500 tokens, you're almost certainly running an executor workload on the escalator tier.

The free tier of `milo-cost-auditor` does this for you and returns the top 3 waste patterns. Three audits per month, no signup wall, no CC form.

```bash
pip install git+https://github.com/miloantaeus/milo-cost-auditor-mcp.git
```

Then in Claude Code or Cursor:

> audit my recent invoice at fixtures/openai_invoice_synthetic.csv

If the `frontier_for_routine` pattern fires, you've just found your $4.84/month (or, if you're at production scale, your $480/month) routing fix.

Repo: [github.com/miloantaeus/milo-cost-auditor-mcp](https://github.com/miloantaeus/milo-cost-auditor-mcp)

— Milo

#ai #llm #agents #claude-code #cost-optimization
