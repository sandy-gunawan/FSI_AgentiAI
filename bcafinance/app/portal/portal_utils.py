"""Shared helpers for the bcafinance Streamlit portal."""
from __future__ import annotations

import asyncio
from typing import Awaitable, TypeVar

T = TypeVar("T")


def run_async(coro: Awaitable[T]) -> T:
    """Run an async workflow from Streamlit's synchronous context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():  # pragma: no cover
            import nest_asyncio  # type: ignore

            nest_asyncio.apply()
            return loop.run_until_complete(coro)  # type: ignore[arg-type]
    except RuntimeError:
        pass
    return asyncio.run(coro)  # type: ignore[arg-type]


def rupiah(amount) -> str:
    if amount is None:
        return "-"
    try:
        return f"Rp {int(amount):,}".replace(",", ".")
    except Exception:
        return str(amount)
