# 01 · What is this, and what is an "agent"?

## The business problem (real Indonesia use case)

**Invoice financing** (Indonesian: *anjak piutang* / invoice discounting). A company
has sold goods and issued an invoice to a buyer, but the buyer will only pay in 30–90
days. The seller needs cash *now*, so it brings the invoice to **BCA Finance**, which
advances (say) **80%** of the invoice value immediately and collects from the buyer later.

Before advancing money, the financier must check the invoice:
- Is it **complete** (all required fields present and legible)?
- Does it **satisfy policy** (within the facility limit, within the max term, valid NPWP)?
- Is the **math consistent** (subtotal + PPN = total)?

Doing this by hand for thousands of invoices is slow. That's what this demo automates.

## What is an "agent" (plain English)?

An **agent** is an LLM (large language model) given:
1. a **role/instructions** ("you are the invoice reviewer…"),
2. an **input** (the invoice image or its extracted fields),
3. and a **defined output** (structured JSON).

It *reasons* over the input and produces the output. In this demo the core pipeline uses
**two agents** (plus an optional third for SQL enrichment):

| Agent | Job | Input | Output |
|-------|-----|-------|--------|
| **Agent 1 — Extractor** | Turn a picture into structured data | invoice image / OCR result | canonical JSON (fields + confidence) |
| **Agent 2 — Reviewer** | Judge completeness + policy | Agent 1's JSON + current policy | review JSON (flags, gaps, recommendation) |
| **Agent 3 — Credit context** *(optional)* | Read structured facts from **SQL Server** (buyer credit, facility, duplicates, watchlist) | invoice ids | enrichment JSON (see [doc 09](09-sql-structured-data.md)) |

> **Important:** the agents do **not** make the final yes/no. A small, boring, 100%
> predictable **rules engine** (plain Python, reads a config file) makes the *binding*
> decision. The agent writes the human-readable explanation. This keeps the system
> auditable — an LLM can never "approve" a loan that breaks a hard rule.

## Where the agents live

Both agents are **hosted in Microsoft Foundry** as *prompt agents* — created once by a
provisioning script, then called by reference. They are **not** built in code at runtime.
Your Python code only orchestrates (calls them in order) and governs (logs tokens, audit).

## What "3 modes" means

The only thing that changes between the three modes is **how Agent 1 sees the invoice**:

- **Mode A — DI direct** — Azure **Document Intelligence** does the OCR first (deterministic,
  gives confidence scores); the orchestrator (Python) calls it, then Agent 1 tidies it up.
- **Mode A+ — DI agentic** — **Agent 1 itself** calls Document Intelligence as a *tool*.
- **Mode B — Multimodal** — a **multimodal** model (that can *see* images) reads the picture directly.

Agent 2 and the rules engine are identical in all three. See [03](03-the-two-options.md).

Next → [02 · Architecture & flow](02-architecture-and-flow.md)
