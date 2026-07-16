"""Verify both credit-context agents (REST tool + MCP tool) reach SQL Server."""
from __future__ import annotations

import asyncio

from app.agents.shared.foundry_runner import foundry_session

PROMPT = ("client_id=CLI-01, buyer_id=BUY-01, invoice_no=INV-2026-1000, "
          "buyer_npwp=01.234.567.8-901.000. Panggil semua tool lalu rangkum konteks kredit.")


async def _run(agent_key: str) -> str:
    with foundry_session(f"TEST-{agent_key}") as (runner, cost):
        return await asyncio.to_thread(runner.run, tool=f"foundry:{agent_key}",
                                       step="enrich", agent_key=agent_key, prompt=PROMPT)


async def main() -> None:
    for key in ("bca-credit-context-rest", "bca-credit-context-mcp"):
        print(f"\n===== {key} =====")
        try:
            out = await _run(key)
            print(out[:700])
            print("... over_limit?" , "over_credit_limit" in out or "1.800" in out or "1800000000" in out)
        except Exception as exc:  # noqa: BLE001
            print("ERROR:", exc)


if __name__ == "__main__":
    asyncio.run(main())
