# 1 · What is a "Foundry-hosted agent" in this code?

> *"OK — in v1 you told me an agent is just a system prompt handed to a runner. Now you say the
> agents are 'in Foundry'. So what is even left in my code? Did the agents move away?"*

This is the **most important** thing to understand about **v2**. Let's fix the mental model — again.

If you haven't read the v1 explanation yet, read [../docs/01-what-is-an-agent.md](../docs/01-what-is-an-agent.md)
first. This page assumes you understand that in **v1** an "agent" = *name + instructions + tools +
output schema* handed to one reusable runner.

---

## The one change: **where the agent object lives**

**v1 — the agent is built in your process, used once, thrown away:**

```python
# v1: app/workflows/retail_workflow.py  (AgentRunner)
intake = await runner.run(
    step="intake",
    name="IntakeAgent",
    instructions=INTAKE_AGENT,               # ← the prompt is shipped from YOUR code every call
    tools=[get_account_summary, kyc_tool],   # ← tools are wired from YOUR code
    response_format=IntakeResult,
    prompt="Applicant: customer_id=CUST-1001, ...",
)
```

**v2 — the agent already exists in Foundry; your code just *calls* it:**

```python
# v2: app/workflows/retail_foundry_workflow.py  (FoundryAgentRunner)
intake = await asyncio.to_thread(
    runner.run,
    step="intake",
    name="IntakeAgent",
    agent_key="retail-intake",               # ← a NAME that points at a Foundry agent
    prompt="customer_id=CUST-1001, ...",     # ← only the task; NO instructions, NO tools here
)
```

Notice what **disappeared** from the call site in v2: `instructions=` and `tools=`. They are gone
because they now live **inside the agent in Foundry**. Your code no longer carries the agent's
brain or its tools — it only carries the **task** and an **agent name**.

Think of it like the difference between:
- **v1** = writing the function body every time you call it (inline lambda), vs.
- **v2** = calling a function that is already **deployed as a service** — you just pass arguments.

---

## So what is *actually* still in your code?

Everything that makes this a **multi-agent application** rather than a single chatbot:

| Still 100% in your Python code (v2) | Now lives in Foundry (v2) |
|---|---|
| **Orchestration** — order, parallel fan-out, loops, human gates | The agent's **instructions** (system prompt) |
| **Deterministic decisions** — OJK/BI policy, DBR, affordability | The agent's **tools** (MCP + REST) |
| **Governance** — audit log, token/cost, technical log | The **model** binding (gpt-4o-mini) |
| The **prompt/task** for each step | The **tool-calling loop** (runs server-side in Foundry) |

The agent moving to Foundry did **not** move your workflow logic. A "use case" is still a Python
function in `app/workflows/`. That is the same lesson as v1 — the *orchestration is the app*.

---

## Where the "Foundry agents" actually came from

You did **not** hand-write 30 agents in the Foundry portal. One script created them all from the
**same instruction strings you already had** in v1:

```python
# scripts/provision_foundry_agents.py  (abridged)
from app.agents.retail.agents import INTAKE_AGENT   # ← SAME v1 string, reused verbatim

agent = project.agents.create_version(
    agent_name="retail-intake",
    definition=PromptAgentDefinition(
        model="gpt-4o-mini",
        instructions=INTAKE_AGENT,            # ← the v1 prompt becomes the Foundry agent's brain
        tools=[MCPTool(...), OpenApiTool(...)],# ← MCP + REST tools attached here (see doc 04)
    ),
)
```

So there is a **single source of truth** for each agent's persona: the constant in
`app/agents/<use_case>/agents.py`. v1 reads it at runtime; v2 uploaded it to Foundry once. Change
the string and re-run the script → a new **version** of the agent is created in Foundry.

The result of provisioning is a small registry file,
[data/foundry_agents.json](../data/foundry_agents.json):

```json
{
  "project_endpoint": "https://bnsfoundryer3wj7.services.ai.azure.com/api/projects/financing",
  "model": "gpt-4o-mini",
  "agents": {
    "retail-intake":      { "id": "retail-intake:2", "name": "retail-intake", "version": "2", "mcp": ["kyc_aml"], "rest": true },
    "retail-credit-risk": { "id": "retail-credit-risk:1", "name": "retail-credit-risk", "mcp": ["credit_bureau"] }
  }
}
```

`agent_key="retail-intake"` in your workflow is looked up in this file to find the Foundry agent
name to call.

---

## The one runner that runs every v2 agent

Just like v1 had one `AgentRunner`, v2 has one
[`FoundryAgentRunner`](../app/agents/shared/foundry_runner.py). Here is its heart:

```python
class FoundryAgentRunner:
    def run(self, *, step, name, agent_key, prompt) -> str:
        agent_name = self.agent_name(agent_key)               # look up name in the registry
        response = self.openai.responses.create(              # OpenAI Responses API
            input=prompt,
            extra_body={"agent_reference": {"name": agent_name, "type": "agent_reference"}},
        )
        text  = getattr(response, "output_text", None) or ""  # the agent's answer
        usage = getattr(response, "usage", None)              # REAL token usage from Foundry
        in_tok, out_tok = _usage_tokens(usage)
        self.cost.add(in_tok, out_tok)                        # same CostTracker as v1
        self.tech.append({"tool": "foundry:agent", ...})     # technical log entry
        self.audit.record(request_id=self.request_id, ...)   # same audit log as v1
        return text
```

Three things to notice:
1. **`agent_reference`** — this is how the Responses API says *"don't use an inline model; run the
   persistent agent named `retail-intake`"*. The tool-calling (MCP/REST) then happens **server-side
   in Foundry**, not in your process.
2. **`response.usage`** — these are the **real** prompt/completion token counts that Foundry billed
   for the call. v2 governance is built on this (see [doc 07](07-governance-token-cost-foundry.md)).
3. **`self.audit` / `self.cost` / `self.tech`** — the exact same governance objects as v1, so the
   portal's governance panels light up identically.

---

## The session wrapper (auth + client lifetime)

Each v2 request opens one Foundry client via a small context manager:

```python
# app/agents/shared/foundry_runner.py
@contextmanager
def foundry_session(request_id, use_case):
    registry   = load_agent_registry()                       # data/foundry_agents.json
    endpoint   = registry["project_endpoint"]
    cost       = CostTracker(request_id)
    credential = DefaultAzureCredential()                     # az login / managed identity
    project    = AIProjectClient(endpoint=endpoint, credential=credential)
    try:
        yield FoundryAgentRunner(project, request_id, use_case, cost, registry), cost
    finally:
        project.close(); credential.close()
```

- **Auth** is `DefaultAzureCredential` — locally that's your `az login`; in the cloud it's the
  Container App's **managed identity**. That identity needs a Foundry data-plane role (see
  [doc 05](05-provision-and-deploy-foundry.md)).
- **`cost`** is created here and returned so the page can show the token/USD numbers.

---

## Mental model summary

- A **v2 agent** is a **persistent, named object in Foundry** (`instructions + tools + model`),
  created once by the provisioning script from your v1 prompt strings.
- Your code keeps the **orchestration + deterministic decisions + governance**, and calls each agent
  by **name** via the Responses API `agent_reference`.
- **One runner** (`FoundryAgentRunner`) does every call and feeds the **same** audit/token/cost
  pipeline as v1.

Next: [02-architecture-and-flow-foundry.md](02-architecture-and-flow-foundry.md) — see the moved
boundary and a full request trace.
