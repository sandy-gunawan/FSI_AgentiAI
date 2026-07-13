# 05 — Deploy This Demo to Azure (Beginner Step-by-Step)

> This guide is intentionally written for first-timers.
> It shows how to deploy/update this exact project to Azure Container Apps,
> how to set the key environment variables, and how to verify all live URLs.

> 🚧 **Optional AI Gateway:** after the app is deployed you can add an **APIM AI Gateway** and set the
> `APIM_*` env vars on the portal to enable the per-transaction **Route via APIM** toggle (per-agent
> token metrics + limits, v1 & v2). Full setup: [../docs-foundry-v2/10-apim-implementation-reference.md](../docs-foundry-v2/10-apim-implementation-reference.md) §5.

---

## 0) What will be deployed

This repo deploys as **three container apps**:

1. `<your-portal-app-name>` (Streamlit UI + agent orchestration)
2. `<your-systems-app-name>` (surrounding systems: REST + MCP)
3. `<your-partner-app-name>` (external partner bank agent via A2A)

All three are in:

- Resource group: `<your-resource-group>`
- Region: `<your-region>`
- Container Apps environment: `<your-containerapps-env>`
- Container registry: `<your-acr-name>`

---

## 1) Prerequisites (install once)

You need:

1. Azure subscription with permission to push images and update Container Apps.
2. Azure CLI installed (`az`).
3. Optional but helpful: `jq` for pretty JSON in shell outputs.

Check quickly:

```powershell
az version
az account show
```

If not logged in:

```powershell
az login
az account set --subscription <your-subscription-id>
```

---

## 2) Set variables (copy-paste)

Run these in PowerShell from repo root:

```powershell
$SUB = "<your-subscription-id>"
$RG = "<your-resource-group>"
$LOC = "<your-region>"                 # example: eastus2
$ACR = "<your-acr-name>"
$ENV = "<your-containerapps-env>"

$PORTAL_APP = "<your-portal-app-name>"
$SYSTEMS_APP = "<your-systems-app-name>"
$PARTNER_APP = "<your-partner-app-name>"

$PORTAL_IMAGE = "bns-portal:v16"
$SYSTEMS_IMAGE = "bns-systems:v5"
$PARTNER_IMAGE = "bns-partner:v3"

$SYSTEMS_URL = "https://<your-systems-app-fqdn>"
$PARTNER_URL = "https://<your-partner-app-fqdn>"
```

You can change the image tags (`v16`, `v5`, `v3`) if you want newer versions.

---

## 3) Build and push container images to ACR

`az acr build` builds in Azure (no local Docker daemon required).

```powershell
az acr build -r $ACR -t $PORTAL_IMAGE  -f Dockerfile.portal  .
az acr build -r $ACR -t $SYSTEMS_IMAGE -f Dockerfile.systems .
az acr build -r $ACR -t $PARTNER_IMAGE -f Dockerfile.partner .
```

Expected result: each command ends with success and image pushed into `<your-acr-name>.azurecr.io`.

---

## 4) Update the three Container Apps

### 4.1 Update surrounding systems app

```powershell
az containerapp update `
  -g $RG -n $SYSTEMS_APP `
  --image "$ACR.azurecr.io/$SYSTEMS_IMAGE"
```

### 4.2 Update partner A2A app

```powershell
az containerapp update `
  -g $RG -n $PARTNER_APP `
  --image "$ACR.azurecr.io/$PARTNER_IMAGE"
```

### 4.3 Update portal app and key env vars

```powershell
az containerapp update `
  -g $RG -n $PORTAL_APP `
  --image "$ACR.azurecr.io/$PORTAL_IMAGE" `
  --set-env-vars REST_BASE_URL=$SYSTEMS_URL PARTNER_A2A_URL=$PARTNER_URL
```

Why these env vars matter:

- `REST_BASE_URL` tells portal agents where the surrounding systems (REST + MCP) live.
- `PARTNER_A2A_URL` tells the A2A client where partner bank Agent Card and `/a2a` endpoint live.

---

## 5) Verify deployment health (must do)

### 5.1 Check active revisions/images

```powershell
az containerapp revision list -g $RG -n $PORTAL_APP  --query "[?properties.active].{running:properties.runningState,image:properties.template.containers[0].image}" -o table
az containerapp revision list -g $RG -n $SYSTEMS_APP --query "[?properties.active].{running:properties.runningState,image:properties.template.containers[0].image}" -o table
az containerapp revision list -g $RG -n $PARTNER_APP --query "[?properties.active].{running:properties.runningState,image:properties.template.containers[0].image}" -o table
```

You want `running = Running` and image tags matching what you just pushed.

### 5.2 Verify public URLs

- Portal: `https://<your-portal-app-fqdn>`
- Systems root: `https://<your-systems-app-fqdn>`
- Systems health: `https://<your-systems-app-fqdn>/health`
- Partner health: `https://<your-partner-app-fqdn>/health`

Smoke test commands:

```powershell
curl "https://<your-systems-app-fqdn>/health"
curl "https://<your-partner-app-fqdn>/health"
curl "https://<your-partner-app-fqdn>/.well-known/agent-card.json"
```

---

## 6) Surrounding system URLs (for external callers)

### 6.1 REST endpoints

Base:

- `https://<your-systems-app-fqdn>`

Examples:

- `/core-banking/customers/CUST-1001/accounts`
- `/core-banking/customers/CUST-1001/transactions?months=6`
- `/collateral/COL-9001`
- `/financials/companies/SME-5001?years=3`
- `/servicing/loans/CUST-1006`
- `/monitoring/alerts/CUST-1001`
- `/pricing/products`
- `POST /pricing/quote?amount_idr=50000000&tenor_months=24&risk_grade=B&product_code=KTA-STD`

### 6.2 MCP endpoints (Streamable HTTP)

- `https://<your-systems-app-fqdn>/mcp/credit-bureau/`
- `https://<your-systems-app-fqdn>/mcp/kyc-aml/`
- `https://<your-systems-app-fqdn>/mcp/policy-rules/`

### 6.3 A2A partner endpoints

- Agent Card: `https://<your-partner-app-fqdn>/.well-known/agent-card.json`
- JSON-RPC: `https://<your-partner-app-fqdn>/a2a`

---

## 7) Authentication and secrets

Current demo mode:

- Surrounding systems: **no API key / no username-password**
- Partner A2A: **no auth**
- Data is synthetic and public for demo/testing only

For production, add at least:

1. Private ingress or API gateway.
2. AuthN/AuthZ (OAuth2/JWT/mTLS).
3. Key Vault-managed secrets.
4. Rate limits and WAF rules.
5. PII controls and retention policies.

---

## 8) Troubleshooting quick checklist

1. Wrong image tag
- Symptom: old behavior after update.
- Check revision image with `az containerapp revision list ...`.

2. Portal cannot reach systems
- Symptom: tool call failures in UI/logs.
- Ensure `REST_BASE_URL` is set to the systems HTTPS URL.

3. A2A errors (discover/send)
- Symptom: syndication use case fails.
- Ensure `PARTNER_A2A_URL` points to partner base URL and Agent Card works.

4. Build failures
- Run one `az acr build` at a time and read the first failing layer.

---

## 9) Local vs Azure mapping (mental model)

- Local:
  - Portal: `http://localhost:8501`
  - Systems: `http://localhost:8080`
  - Partner: `http://localhost:8090`

- Azure:
  - Portal: `https://<your-portal-app-fqdn>`
  - Systems: `https://<your-systems-app-fqdn>`
  - Partner: `https://<your-partner-app-fqdn>`

If local works but Azure fails, compare this mapping first.
