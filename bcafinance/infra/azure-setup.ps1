<#
.SYNOPSIS
    Provision bcafinance Azure resources in the SAME resource group as the parent
    finance demo (rg-finance-agenticai), then deploy the portal as a Container App.

.DESCRIPTION
    Creates:
      * Azure AI Document Intelligence (Cognitive Services, kind=FormRecognizer) — Option A
      * Storage account + 2 blob containers (invoices + hot-reloadable config)
      * Container App 'ca-bcafinance-portal' (reuses the parent Container Apps env)
    Assigns the portal's managed identity the roles it needs (Document Intelligence,
    Foundry project, Blob). Re-uses the existing Foundry project 'financing'.

    Edit the variables below, run 'az login', then run this script section by section.
    It is intentionally explicit (no azd/bicep) to mirror the parent repo's az-CLI style.
#>

# ---- Variables (EDIT THESE) ------------------------------------------------
$RG            = "rg-finance-agenticai"                 # SAME resource group as parent
$LOCATION      = "eastus2"
$ACA_ENV       = "<parent-container-apps-env-name>"      # reuse parent env (az containerapp env list)
$ACR           = "<your-acr-name>"                       # existing registry used by parent
$DI_NAME       = "bcafinance-di"                         # Document Intelligence resource
$STORAGE       = "bcafinancesa$((Get-Random -Max 9999))" # must be globally unique, lowercase
$APP_NAME      = "ca-bcafinance-portal"
$FOUNDRY_NAME  = "bnsfoundryer3wj7"                       # existing Foundry (Cognitive Services) resource
$FOUNDRY_PROJECT_ENDPOINT = "https://bnsfoundryer3wj7.services.ai.azure.com/api/projects/financing"

# ---- 0. Login / subscription ----------------------------------------------
az login
$SUB = az account show --query id -o tsv

# ---- 1. Document Intelligence (Option A) ----------------------------------
az cognitiveservices account create `
  --name $DI_NAME --resource-group $RG --location $LOCATION `
  --kind FormRecognizer --sku S0 --custom-domain $DI_NAME --yes
$DI_ENDPOINT = az cognitiveservices account show -n $DI_NAME -g $RG --query properties.endpoint -o tsv

# ---- 2. Storage account + containers (images + config) --------------------
az storage account create -n $STORAGE -g $RG -l $LOCATION --sku Standard_LRS --kind StorageV2
$BLOB_URL = az storage account show -n $STORAGE -g $RG --query primaryEndpoints.blob -o tsv
az storage container create --account-name $STORAGE --name bca-invoices --auth-mode login
az storage container create --account-name $STORAGE --name bca-config    --auth-mode login
# Upload the review rules so they can be hot-edited in the cloud:
az storage blob upload --account-name $STORAGE --container-name bca-config `
  --name review_rules.yaml --file ./config/review_rules.yaml --auth-mode login --overwrite

# ---- 3. Build + push the portal image -------------------------------------
az acr build --registry $ACR --image bcafinance-portal:latest -f Dockerfile.portal .

# ---- 4. Create the Container App (system-assigned identity) ---------------
az containerapp create `
  --name $APP_NAME --resource-group $RG --environment $ACA_ENV `
  --image "$ACR.azurecr.io/bcafinance-portal:latest" `
  --target-port 8501 --ingress external --system-assigned `
  --registry-server "$ACR.azurecr.io" `
  --env-vars `
    FOUNDRY_PROJECT_ENDPOINT=$FOUNDRY_PROJECT_ENDPOINT `
    FOUNDRY_MODEL=gpt-4o-mini `
    DOC_INTELLIGENCE_ENDPOINT=$DI_ENDPOINT `
    BLOB_ACCOUNT_URL=$BLOB_URL `
    BLOB_CONTAINER_CONFIG=bca-config `
    BLOB_CONTAINER_INVOICES=bca-invoices `
    REVIEW_RULES_BLOB=review_rules.yaml `
    ENABLE_INSTRUMENTATION=true

$PID = az containerapp show -n $APP_NAME -g $RG --query identity.principalId -o tsv

# ---- 5. RBAC for the portal's managed identity ----------------------------
# 5a. Document Intelligence (Cognitive Services User)
$DI_ID = az cognitiveservices account show -n $DI_NAME -g $RG --query id -o tsv
az role assignment create --assignee $PID --role "Cognitive Services User" --scope $DI_ID

# 5b. Foundry project (Azure AI Developer + Cognitive Services User)
$FOUNDRY_ID = az cognitiveservices account show -n $FOUNDRY_NAME -g $RG --query id -o tsv
az role assignment create --assignee $PID --role "Azure AI Developer"        --scope $FOUNDRY_ID
az role assignment create --assignee $PID --role "Cognitive Services User"   --scope $FOUNDRY_ID

# 5c. Blob (Storage Blob Data Contributor for config write-back; Reader also ok)
$SA_ID = az storage account show -n $STORAGE -g $RG --query id -o tsv
az role assignment create --assignee $PID --role "Storage Blob Data Contributor" --scope $SA_ID

# ---- 6. Provision the 3 Foundry agents (run once, locally, after az login) -
# python scripts/provision_agents.py

Write-Host "Done. Portal URL:" (az containerapp show -n $APP_NAME -g $RG --query properties.configuration.ingress.fqdn -o tsv)
