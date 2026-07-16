"""Central configuration for the bcafinance invoice-review demo.

Loads settings from environment variables (and a local .env). Secrets stay in
.env (gitignored); production uses Azure Managed Identity + Blob-hosted config.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


class Settings(BaseSettings):
    """Strongly-typed application settings."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ---- Microsoft Foundry (hosts the 3 prompt agents) ----
    foundry_project_endpoint: str = Field(default="", alias="FOUNDRY_PROJECT_ENDPOINT")
    foundry_model: str = Field(default="gpt-4o-mini", alias="FOUNDRY_MODEL")

    # ---- Option A: Azure AI Document Intelligence ----
    doc_intelligence_endpoint: str = Field(default="", alias="DOC_INTELLIGENCE_ENDPOINT")
    doc_intelligence_key: str = Field(default="", alias="DOC_INTELLIGENCE_KEY")

    # ---- Option 1 (agentic): the tools service the extractor agent calls ----
    tools_service_url: str = Field(default="", alias="TOOLS_SERVICE_URL")

    # ---- Blob Storage (images + hot-reloadable review rules) ----
    blob_account_url: str = Field(default="", alias="BLOB_ACCOUNT_URL")
    blob_container_config: str = Field(default="bca-config", alias="BLOB_CONTAINER_CONFIG")
    blob_container_invoices: str = Field(default="bca-invoices", alias="BLOB_CONTAINER_INVOICES")
    review_rules_blob: str = Field(default="review_rules.yaml", alias="REVIEW_RULES_BLOB")

    # ---- Observability ----
    enable_instrumentation: bool = Field(default=False, alias="ENABLE_INSTRUMENTATION")
    applicationinsights_connection_string: str = Field(
        default="", alias="APPLICATIONINSIGHTS_CONNECTION_STRING"
    )
    otel_exporter_otlp_endpoint: str = Field(default="", alias="OTEL_EXPORTER_OTLP_ENDPOINT")
    otel_service_name: str = Field(default="bcafinance-invoice-review", alias="OTEL_SERVICE_NAME")

    # ---- Governance ----
    token_budget_per_request: int = Field(default=60_000, alias="TOKEN_BUDGET_PER_REQUEST")
    audit_db_path: str = Field(default="data/audit.db", alias="AUDIT_DB_PATH")

    # ---- Derived paths ----
    @property
    def audit_db_abspath(self) -> Path:
        p = PROJECT_ROOT / self.audit_db_path
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def local_rules_path(self) -> Path:
        return PROJECT_ROOT / "config" / "review_rules.yaml"

    @property
    def agents_registry_path(self) -> Path:
        return PROJECT_ROOT / "data" / "agents.json"

    @property
    def sample_invoices_dir(self) -> Path:
        p = PROJECT_ROOT / "data" / "sample_invoices"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def doc_intelligence_configured(self) -> bool:
        return bool(self.doc_intelligence_endpoint)

    @property
    def tools_service_configured(self) -> bool:
        return bool(self.tools_service_url)

    @property
    def blob_configured(self) -> bool:
        return bool(self.blob_account_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()
