# bcafinance docs — start here

Newbie-friendly guides for the agentic invoice-financing review demo. Read in order.

| # | Doc | What you'll learn |
|---|-----|-------------------|
| 01 | [What is this & what is an agent](01-what-is-this.md) | The use case, plain-English agent definition |
| 02 | [Architecture & flow](02-architecture-and-flow.md) | Every component + end-to-end sequence diagram |
| 03 | [The two options (A vs B)](03-the-two-options.md) | Document Intelligence vs Multimodal, pros/cons |
| 04 | [Azure services used](04-azure-services.md) | What each Azure service does here, and why |
| 05 | [Provision & deploy](05-provision-and-deploy.md) | Step-by-step, same resource group |
| 06 | [Code walkthrough](06-code-walkthrough.md) | File-by-file, following one request |
| 07 | [Config hot-reload (2 layers)](07-config-hot-reload.md) | Change the review "on the fly" |
| 08 | [Observability](08-observability.md) | Logs in code + Foundry Traces |

**Golden rule of this demo:** the LLM agents *reason and narrate*; the **binding
decision is deterministic** (config-driven rules) — so it stays auditable and
regulator-safe.
