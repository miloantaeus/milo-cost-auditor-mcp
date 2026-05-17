"""
LLM pricing table — frozen at 2026-05 list prices.

Units: USD per 1,000,000 input tokens / USD per 1,000,000 output tokens.
Source: each provider's public pricing page as of May 2026.

Quality bands are my (Milo's) opinion based on shipped task-completion rates
across my own routing layer. Treat them as a starting point, not a benchmark.
Quality band scale:
  5 = frontier (Opus, GPT-5, Gemini 3 Ultra-class)
  4 = strong (Sonnet, GPT-4o-class)
  3 = capable (Haiku, gpt-4o-mini, Llama-3.3-70b)
  2 = small-task (Groq Llama-3.1-8b, gpt-3.5-class)
  1 = embedding/cheap-throughput

If you spot a stale price, file an issue at
https://github.com/miloantaeus/milo-cost-auditor/issues — I'll refresh.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class ModelPrice:
    """One row of the pricing table."""

    provider: str
    model: str
    input_per_million: float   # USD per 1M input tokens
    output_per_million: float  # USD per 1M output tokens
    context_window: int
    quality_band: int          # 1..5
    notes: str = ""

    def cost_for(self, input_tokens: int, output_tokens: int) -> float:
        """Cost in USD for a given call shape."""
        return (
            (input_tokens / 1_000_000.0) * self.input_per_million
            + (output_tokens / 1_000_000.0) * self.output_per_million
        )


# Frozen snapshot — 2026-05.
PRICING_TABLE: List[ModelPrice] = [
    # ---- OpenAI ----
    ModelPrice("openai", "gpt-5",               5.00, 15.00, 256_000, 5, "Flagship reasoning model"),
    ModelPrice("openai", "gpt-5-mini",          0.50,  1.50, 256_000, 4, "Mini reasoning, default for 80% of tasks"),
    ModelPrice("openai", "gpt-5-nano",          0.10,  0.40, 128_000, 3, "Cheap, fast, good for routing/classify"),
    ModelPrice("openai", "gpt-4o",              2.50, 10.00, 128_000, 4, "Legacy flagship — usually overspend"),
    ModelPrice("openai", "gpt-4o-mini",         0.15,  0.60, 128_000, 3, "Legacy mini, getting deprecated"),
    ModelPrice("openai", "o1",                 15.00, 60.00, 200_000, 5, "Reasoning — very expensive per token"),
    ModelPrice("openai", "o3-mini",             1.10,  4.40, 200_000, 4, "Cheaper reasoning"),

    # ---- Anthropic ----
    ModelPrice("anthropic", "claude-4-opus",   15.00, 75.00, 200_000, 5, "Frontier; reserve for high-stakes reasoning"),
    ModelPrice("anthropic", "claude-4-sonnet",  3.00, 15.00, 200_000, 4, "Default for serious coding/writing"),
    ModelPrice("anthropic", "claude-4-haiku",   0.80,  4.00, 200_000, 3, "Cheap and fast; routine tasks"),
    ModelPrice("anthropic", "claude-3-opus",   15.00, 75.00, 200_000, 5, "Legacy frontier — Sonnet 4 usually better"),
    ModelPrice("anthropic", "claude-3-sonnet",  3.00, 15.00, 200_000, 4, "Legacy Sonnet"),
    ModelPrice("anthropic", "claude-3-haiku",   0.25,  1.25, 200_000, 2, "Legacy Haiku"),

    # ---- Google ----
    ModelPrice("google", "gemini-3-pro",        1.25,  5.00, 2_000_000, 5, "Huge context, frontier reasoning"),
    ModelPrice("google", "gemini-3-flash",      0.10,  0.40, 1_000_000, 3, "Default cheap option, very fast"),
    ModelPrice("google", "gemini-2.5-pro",      1.25,  5.00, 2_000_000, 4, "Legacy pro"),
    ModelPrice("google", "gemini-2.5-flash",    0.075, 0.30, 1_000_000, 3, "Legacy flash, still cheapest"),

    # ---- MiniMax ----
    ModelPrice("minimax", "minimax-m2.7",       0.30,  1.20, 256_000, 4, "Strong reasoning, Anthropic-compatible API"),
    ModelPrice("minimax", "minimax-m2.7-highspeed", 0.30, 1.20, 256_000, 4, "Same model, larger free quota (15k req/5hr Starter)"),
    ModelPrice("minimax", "abab-7-chat",        0.20,  0.80, 245_000, 3, "Legacy chat"),

    # ---- Groq (hosting OSS models, ultra-low-latency inference) ----
    ModelPrice("groq", "llama-3.3-70b-versatile", 0.59, 0.79, 131_000, 3, "Fast OSS, great for routing"),
    ModelPrice("groq", "llama-3.1-8b-instant",   0.05, 0.08, 131_000, 2, "Cheapest fast inference"),
    ModelPrice("groq", "mixtral-8x7b",           0.24, 0.24, 32_000,  2, "Mixture of experts"),

    # ---- OpenRouter (broker; quotes mid-2026 averages, varies by route) ----
    ModelPrice("openrouter", "openrouter/auto",  1.00, 4.00, 128_000, 3, "Aggregator; price depends on selected route"),

    # ---- DeepSeek ----
    ModelPrice("deepseek", "deepseek-v3.5",      0.27,  1.10, 128_000, 4, "Strong coder, MIT-licensed weights"),
    ModelPrice("deepseek", "deepseek-r1",        0.55,  2.19, 128_000, 4, "Reasoning model"),

    # ---- Cerebras ----
    ModelPrice("cerebras", "llama-3.3-70b",      0.60,  0.85, 128_000, 3, "Ultra-fast wafer-scale inference"),
    ModelPrice("cerebras", "llama-3.1-8b",       0.10,  0.15, 128_000, 2, "Cheapest+fastest small model"),
]


# ------------- lookup helpers ----------------------------------------------

def _normalize(name: str) -> str:
    """Lowercase + strip provider prefix + collapse separators."""
    s = name.lower().strip()
    if "/" in s:
        s = s.split("/", 1)[1]
    s = s.replace("_", "-")
    return s


def lookup(model: str) -> Optional[ModelPrice]:
    """Look up a model by name (case-insensitive, accepts provider/model form)."""
    needle = _normalize(model)
    for entry in PRICING_TABLE:
        if _normalize(entry.model) == needle:
            return entry
    # second pass: prefix match (e.g. "gpt-4o-2024-08-06" -> "gpt-4o")
    for entry in PRICING_TABLE:
        norm = _normalize(entry.model)
        if needle.startswith(norm) or norm.startswith(needle):
            return entry
    return None


def by_provider(provider: str) -> List[ModelPrice]:
    """All models for a given provider."""
    return [m for m in PRICING_TABLE if m.provider == provider.lower()]


def cheaper_than(model: ModelPrice, min_quality: int = 0) -> List[ModelPrice]:
    """Return all models cheaper than the reference, ranked by avg cost ascending,
    optionally filtered by minimum quality band."""
    ref_avg = (model.input_per_million + model.output_per_million) / 2.0
    out: List[ModelPrice] = []
    for entry in PRICING_TABLE:
        if entry.model == model.model:
            continue
        if entry.quality_band < min_quality:
            continue
        avg = (entry.input_per_million + entry.output_per_million) / 2.0
        if avg < ref_avg:
            out.append(entry)
    out.sort(key=lambda m: (m.input_per_million + m.output_per_million) / 2.0)
    return out


# Default per-task-pattern quality requirements.
TASK_QUALITY_REQUIREMENT: Dict[str, int] = {
    "code-completion":     3,
    "summarization":       3,
    "routine-synthesis":   3,
    "deep-reasoning":      4,
    "creative-writing":    4,
    "extraction":          2,
    "classification":      2,
    "translation":         3,
    "agent-loop":          3,
}
