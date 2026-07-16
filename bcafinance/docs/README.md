# bcafinance docs — start here

Newbie-friendly guides for the agentic invoice-financing review demo. Read in order.

| # | Doc | What you'll learn |
|---|-----|-------------------|
| 01 | [What is this & what is an agent](01-what-is-this.md) | The use case, plain-English agent definition |
| 02 | [Architecture & flow](02-architecture-and-flow.md) | Every component + end-to-end sequence diagram |
| 03 | [The three extraction modes](03-the-two-options.md) | DI direct vs DI agentic vs Multimodal, pros/cons |
| 04 | [Azure services used](04-azure-services.md) | What each Azure service does here, and why |
| 05 | [Provision & deploy](05-provision-and-deploy.md) | Step-by-step, same resource group |
| 06 | [Code walkthrough](06-code-walkthrough.md) | File-by-file, following one request |
| 07 | [Config hot-reload (2 layers)](07-config-hot-reload.md) | Change the review "on the fly" |
| 08 | [Observability](08-observability.md) | Logs in code + Foundry Traces |
| 09 | [Structured data: SQL Server, REST vs MCP](09-sql-structured-data.md) | How an agent reads SQL; LLM params → tools; REST vs MCP (newbie) |
| 10 | [MCP deep-dive (what/why/how/connect/code)](10-mcp-deep-dive.md) | Everything about MCP: connection, defining tools, code skeleton (newbie) |
| 11 | [The database inside the container](11-database-in-container.md) | Where the DB lives, lifecycle, 4 ways to view it, full schema (newbie) |
**Golden rule of this demo:** the LLM agents *reason and narrate*; the **binding
decision is deterministic** (config-driven rules) — so it stays auditable and
regulator-safe.
