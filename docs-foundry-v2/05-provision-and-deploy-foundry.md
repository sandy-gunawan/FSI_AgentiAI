# 5 · Provision the Foundry Agents & Deploy (v2) — newbie step-by-step

This is the v2 companion to [../docs/05-deploy-to-azure.md](../docs/05-deploy-to-azure.md). It covers
the **two extra things** v2 needs on top of the normal deploy:

1. **Provision** the ~30 prompt agents into Foundry (once).
2. Make sure the **identity** that calls Foundry (you locally, or the Container App in the cloud) has
   the right **role**.

Everything else (building images, updating Container Apps) is the same as v1.

---

## 0 · Prerequisites

- `az login` succeeds (you have `DefaultAzureCredential`).
- Python venv with deps: `pip install -r requirements.txt` (needs `azure-ai-projects>=2.1.0`,
  `jsonref`, `httpx`).
- `.env` has:
  - `FOUNDRY_PROJECT_ENDPOINT` = `https://bnsfoundryer3wj7.services.ai.azure.com/api/projects/financing`
  - `FOUNDRY_MODEL` = `gpt-4o-mini`
  - `REST_BASE_URL` = the **deployed** `ca-bns-systems` URL (NOT localhost — Foundry can't reach it).

---

## 1 · Provision the agents (once)

```powershell
az login
python scripts/provision_foundry_agents.py
```

What it does (see [scripts/provision_foundry_agents.py](../scripts/provision_foundry_agents.py)):

1. Reads the **same instruction strings** from `app/agents/*/agents.py` (single source of truth).
2. Fetches + cleans the REST OpenAPI spec (see [doc 04](04-surrounding-systems-foundry.md)).
3. For each of the ~30 roles, calls `project.agents.create_version(...)` with a
   `PromptAgentDefinition(model, instructions, tools)`.
4. Writes every created agent's id/name/version to
   [data/foundry_agents.json](../data/foundry_agents.json).

Expected tail of the output:

```
Project : https://bnsfoundryer3wj7.services.ai.azure.com/api/projects/financing
Model   : gpt-4o-mini
Systems : https://ca-bns-systems…azurecontainerapps.io
Agents  : 30
…
✅ wrote data/foundry_agents.json (30 agents)
```

> Re-running the script creates a **new version** of each agent (e.g. `retail-intake:2`). That is
> how you roll out an instruction change — edit the string in `app/agents/…/agents.py`, re-run.

---

## 2 · RBAC — let the caller invoke Foundry

The identity calling Foundry needs a **data-plane** role on the Foundry project. Two identities:

| When | Identity | Role needed |
|------|----------|-------------|
| **Provisioning / local run** | your `az login` user | `Azure AI Developer` (or higher) on the project |
| **Cloud portal** | `ca-bns-portal` **managed identity** | `Azure AI Developer` + `Cognitive Services User` on the Foundry resource |

Check / assign (example for the portal's managed identity):

```powershell
# get the portal's managed identity principalId
$pid = az containerapp show -n ca-bns-portal -g rg-finance-agenticai `
  --query identity.principalId -o tsv

# Foundry resource id
$foundry = az cognitiveservices account show -n bnsfoundryer3wj7 -g rg-finance-agenticai `
  --query id -o tsv

az role assignment create --assignee $pid --role "Cognitive Services User" --scope $foundry
az role assignment create --assignee $pid --role "Azure AI Developer"      --scope $foundry
```

> If a v2 page shows a **403 from Foundry**, this role assignment is almost always what's missing.

---

## 3 · Point the portal at Foundry (env vars)

The portal container needs the same Foundry settings as `.env`:

```powershell
az containerapp update -n ca-bns-portal -g rg-finance-agenticai --set-env-vars `
  FOUNDRY_PROJECT_ENDPOINT="https://bnsfoundryer3wj7.services.ai.azure.com/api/projects/financing" `
  FOUNDRY_MODEL="gpt-4o-mini"
```

The v2 runner falls back to a **synthetic registry** built from `FOUNDRY_PROJECT_ENDPOINT` if
`data/foundry_agents.json` wasn't shipped in the image (agent names equal their keys), so the cloud
portal works as long as the endpoint is set and the agents exist.

---

## 4 · Build & deploy the portal image (same as v1)

```powershell
# cloud build (no local Docker needed)
az acr build --registry acrbnsfin6zpbi --image bns-portal:v18 --file Dockerfile.portal .

# roll out
az containerapp update -n ca-bns-portal -g rg-finance-agenticai `
  --image acrbnsfin6zpbi.azurecr.io/bns-portal:v18
```

Verify:

```powershell
curl -s -o NUL -w "status:%{http_code}`n" `
  https://ca-bns-portal.delightfulisland-5bc416ad.eastus2.azurecontainerapps.io/_stcore/health
# → status:200
```

Then open the portal and look for the **🟣 Hosted di Foundry (v2)** nav group with all 8 pages.

---

## 5 · Smoke-test the workflows (optional but recommended)

```powershell
$env:PYTHONPATH="."; $env:PYTHONIOENCODING="utf-8"
.\.venv\Scripts\python.exe -m scripts.smoke_foundry_v2
```

Expected: 7 lines of `✅ <use_case> decision=… tokens=…`. `syndication` returns `REFER` locally
(the partner A2A service isn't running on your machine) but works in the cloud where `ca-bns-partner`
is deployed.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `403` from Foundry on a v2 page | caller lacks data-plane role | assign `Azure AI Developer` + `Cognitive Services User` (step 2) |
| `FoundryAgentsNotProvisioned` error on page | no registry + no endpoint | set `FOUNDRY_PROJECT_ENDPOINT` or run the provisioning script |
| Provisioning: "Invalid tool schema" | raw FastAPI OpenAPI has `anyOf` | already handled by `_fetch_rest_openapi` (drops 422 + components) |
| Provisioning: "REST_BASE_URL is local" | Foundry can't reach localhost | set `REST_BASE_URL` to the deployed `ca-bns-systems` URL |
| Agent tool call 404 | agent called a wrong endpoint (e.g. company vs individual) | prompt already steers this (magentic); wrap risky calls in `try/except` |

Next: [06-use-case-code-walkthrough-foundry.md](06-use-case-code-walkthrough-foundry.md) — line-level
trace per use case.
