"""Per-request token & cost budget tracking (governance guardrail).

Agent Framework reports token usage on each response. We accumulate usage per
financing request, enforce a hard budget, and expose a cost estimate. Exceeding
the budget raises BudgetExceededError so a runaway request is stopped.
"""
from __future__ import annotations

import threading

from app.core.config import get_settings

# Indicative gpt-4o-mini pricing (USD per 1M tokens) — for demo cost display.
_USD_PER_1M_INPUT = 0.15
_USD_PER_1M_OUTPUT = 0.60


class BudgetExceededError(RuntimeError):
    """Raised when a request exceeds its token budget."""


class CostTracker:
    """Tracks token usage for a single financing request."""

    def __init__(self, request_id: str, budget: int | None = None) -> None:
        self.request_id = request_id
        self.budget = budget or get_settings().token_budget_per_request
        self.input_tokens = 0
        self.output_tokens = 0
        self._lock = threading.Lock()

    def add(self, input_tokens: int = 0, output_tokens: int = 0) -> None:
        with self._lock:
            self.input_tokens += max(0, input_tokens)
            self.output_tokens += max(0, output_tokens)
        if self.total_tokens > self.budget:
            raise BudgetExceededError(
                f"Request {self.request_id} exceeded token budget "
                f"({self.total_tokens} > {self.budget})."
            )

    def add_usage(self, usage) -> None:
        """Accept an Agent Framework usage object or dict."""
        if usage is None:
            return
        inp = getattr(usage, "input_token_count", None) or getattr(usage, "prompt_tokens", None)
        out = getattr(usage, "output_token_count", None) or getattr(usage, "completion_tokens", None)
        if isinstance(usage, dict):
            inp = usage.get("input_token_count") or usage.get("prompt_tokens")
            out = usage.get("output_token_count") or usage.get("completion_tokens")
        self.add(int(inp or 0), int(out or 0))

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def estimated_cost_usd(self) -> float:
        return round(
            self.input_tokens / 1_000_000 * _USD_PER_1M_INPUT
            + self.output_tokens / 1_000_000 * _USD_PER_1M_OUTPUT,
            6,
        )

    def summary(self) -> dict:
        return {
            "request_id": self.request_id,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "budget": self.budget,
            "budget_used_pct": round(100 * self.total_tokens / self.budget, 1) if self.budget else 0,
            "estimated_cost_usd": self.estimated_cost_usd,
        }
