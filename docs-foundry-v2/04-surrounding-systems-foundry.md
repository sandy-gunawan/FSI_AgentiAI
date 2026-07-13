# 4 · Surrounding Systems — attached to Foundry agents (v2)

In v1, your Python code opened MCP/REST tools and passed them into `runner.run(tools=[...])`. In v2,
the **same systems** are reached — but the tools are **attached to the agent inside Foundry**, and
Foundry runs the tool-calling loop **server-side**. This page shows exactly how that wiring is done.

For what the systems *are* (URLs, data, why one container), read the v1 doc:
[../docs/04-surrounding-systems.md](../docs/04-surrounding-systems.md). This page is only about the
**v2 attachment**.

---

## The systems (unchanged) — one Container App

All systems live in one deployed app, `ca-bns-systems`:

| System | Kind | Path | Used by which Foundry agents |
|--------|------|------|------------------------------|
| Credit Bureau | **MCP** | `/mcp/credit-bureau/` | retail-credit-risk, servicing-limit-increase, restructure-proposer, aml-investigator, magentic-worker |
| KYC / AML | **MCP** | `/mcp/kyc-aml/` | retail-intake, sme-aml-fraud-agent, aml-investigator, magentic-worker |
| Policy Rules | **MCP** | `/mcp/policy-rules/` | sme-underwriting-orchestrator, restructure-evaluator, committee-compliance |
| Core banking / collateral / financials / loans / monitoring / pricing | **REST (OpenAPI)** | `/` | any agent with `rest=True` |

> **Trailing slash matters** for the MCP paths. A browser `GET` on an MCP path returns "Not Found"
> by design — MCP is a POST/stream protocol, not a web page.

---

## How MCP tools are attached (in the provisioning script)

```python
# scripts/provision_foundry_agents.py
from azure.ai.projects.models import MCPTool

MCPTool(
    server_label="kyc_aml",
    server_url="https://ca-bns-systems…/mcp/kyc-aml/",   # REST_BASE_URL + path
    require_approval="never",   # demo posture: the mock systems have no auth
)
```

`_MCP_PATHS` maps a label to its path:

```python
_MCP_PATHS = {
    "credit_bureau": "/mcp/credit-bureau/",
    "kyc_aml":       "/mcp/kyc-aml/",
    "policy_rules":  "/mcp/policy-rules/",
}
```

When the Foundry agent decides to call a tool, **Foundry** (not your code) opens the MCP stream to
`ca-bns-systems`. That is why the v2 workflow does **not** wrap MCP tools anymore.

---

## How the REST back-office is attached (OpenAPI tool)

The REST API is exposed to the agent as an **OpenAPI tool**. Foundry reads the OpenAPI spec and lets
the agent call any operation in it:

```python
# scripts/provision_foundry_agents.py
from azure.ai.projects.models import OpenApiTool, OpenApiFunctionDefinition, OpenApiAnonymousAuthDetails

OpenApiTool(
    openapi=OpenApiFunctionDefinition(
        name="bns_rest_backoffice",
        spec=rest_spec,                         # the fetched + cleaned OpenAPI JSON
        description="BNS mock back-office REST API: accounts, transactions, collateral, financials, …",
        auth=OpenApiAnonymousAuthDetails(),     # no auth for the demo systems
    )
)
```

### Two important spec fixes (`_fetch_rest_openapi`)

FastAPI's raw `/openapi.json` is **not** directly Foundry-tool-safe. The script fixes two things:

```python
def _fetch_rest_openapi(base_url):
    spec = httpx.get(f"{base_url}/openapi.json").json()
    spec = json.loads(jsonref.dumps(jsonref.replace_refs(spec)))  # 1) resolve $ref → self-contained
    for methods in spec.get("paths", {}).values():
        for op in methods.values():
            if isinstance(op, dict):
                op.get("responses", {}).pop("422", None)           # 2a) drop 422 (uses anyOf)
    spec.pop("components", None)                                    # 2b) drop unused components
    spec["servers"] = [{"url": base_url}]                          # 3) inject public server URL
    return spec
```

- **Why drop `422`?** FastAPI's auto validation-error schema uses `anyOf`, which the Foundry OpenAPI
  tool validator rejects ("Invalid tool schema"). Removing the 422 responses + unused `components`
  makes the spec pass validation.
- **Why inject `servers`?** FastAPI omits the public URL, so the agent wouldn't know where to send
  the request. We set it to the deployed `ca-bns-systems` URL.

---

## Which tools each agent gets (`_build_tools`)

The roster in `AGENTS` declares, per agent, which MCP labels and whether REST is attached:

```python
AgentSpec("retail-intake",        INTAKE_AGENT,      mcp=["kyc_aml"],       rest=True)
AgentSpec("sme-financial-analyst",FINANCIAL_ANALYST,                        rest=True)
AgentSpec("restructure-evaluator",EVALUATOR_AGENT,   mcp=["policy_rules"])
AgentSpec("committee-chair",      CHAIR_AGENT)   # no tools — pure reasoning
```

`_build_tools` turns that into the actual tool objects (MCPTool per label + one OpenApiTool if
`rest=True`). You can see the final attachment per agent in
[data/foundry_agents.json](../data/foundry_agents.json) (`"mcp": [...]`, `"rest": true`).

---

## Local vs cloud (a gotcha)

Foundry runs **in the cloud**, so the agents' tools must point at a **publicly reachable** systems
URL — Foundry cannot reach your `localhost`. The provisioning script enforces this:

```python
if mcp_base.startswith("http://localhost") or mcp_base.startswith("http://127."):
    raise SystemExit("REST_BASE_URL is local … point it at the deployed ca-bns-systems URL first.")
```

So `REST_BASE_URL` must be the deployed `ca-bns-systems` URL before you provision.

---

## What your Python still calls directly (not via the agent)

- **Deterministic reads** for ratios (financials, collateral) — facts, not reasoning.
- **A2A** in syndication — `a2a_client.a2a_send(...)` to the partner bank agent (agent-to-agent,
  cross-org). That is a different protocol from MCP and stays in your code.

Next: [05-provision-and-deploy-foundry.md](05-provision-and-deploy-foundry.md) — create the agents
and deploy.
