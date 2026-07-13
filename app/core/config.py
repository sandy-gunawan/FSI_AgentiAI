"""Central configuration for the BNS agentic financing demo.

Loads settings from environment variables (and a local .env file). All secrets
stay in .env (gitignored); production uses Azure managed identity + App Config.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Agent Framework does NOT auto-load .env — do it explicitly, once.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


class Settings(BaseSettings):
    """Strongly-typed application settings."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ---- Microsoft Foundry (LLM backend) ----
    foundry_project_endpoint: str = Field(default="", alias="FOUNDRY_PROJECT_ENDPOINT")
    foundry_model: str = Field(default="gpt-4o-mini", alias="FOUNDRY_MODEL")

    # ---- AI Gateway (Azure API Management) — optional, OFF by default ----
    # When enabled (and configured), agent calls are routed THROUGH APIM so the
    # gateway can enforce token limits, emit token metrics, cache, etc. The toggle is
    # additive: if not configured, the app transparently falls back to the direct path.
    route_via_apim: bool = Field(default=False, alias="ROUTE_VIA_APIM")
    apim_gateway_url: str = Field(default="", alias="APIM_GATEWAY_URL")  # e.g. https://<apim>.azure-api.net
    apim_subscription_key: str = Field(default="", alias="APIM_SUBSCRIPTION_KEY")
    apim_responses_path: str = Field(default="", alias="APIM_RESPONSES_PATH")  # v2 agents/responses base suffix
    apim_chat_path: str = Field(default="", alias="APIM_CHAT_PATH")  # v1 chat-completions base suffix
    apim_api_version: str = Field(default="2024-10-21", alias="APIM_API_VERSION")

    # ---- Observability ----
    enable_instrumentation: bool = Field(default=False, alias="ENABLE_INSTRUMENTATION")
    otel_exporter_otlp_endpoint: str = Field(default="", alias="OTEL_EXPORTER_OTLP_ENDPOINT")
    otel_service_name: str = Field(default="bns-financing-agents", alias="OTEL_SERVICE_NAME")
    applicationinsights_connection_string: str = Field(
        default="", alias="APPLICATIONINSIGHTS_CONNECTION_STRING"
    )

    # ---- Content Safety ----
    content_safety_endpoint: str = Field(default="", alias="CONTENT_SAFETY_ENDPOINT")
    content_safety_key: str = Field(default="", alias="CONTENT_SAFETY_KEY")

    # ---- Mock surrounding systems (one combined REST service) ----
    rest_base_url: str = Field(default="http://localhost:8080", alias="REST_BASE_URL")

    # ---- A2A partner bank (Agent2Agent protocol) ----
    partner_a2a_url: str = Field(default="http://localhost:8090", alias="PARTNER_A2A_URL")
    bns_single_obligor_cap_idr: int = Field(
        default=5_000_000_000, alias="BNS_SINGLE_OBLIGOR_CAP_IDR"
    )

    # ---- Governance ----
    token_budget_per_request: int = Field(default=60000, alias="TOKEN_BUDGET_PER_REQUEST")
    auto_approve_ceiling_idr: int = Field(default=100_000_000, alias="AUTO_APPROVE_CEILING_IDR")

    # ---- App state ----
    audit_db_path: str = Field(default="data/audit.db", alias="AUDIT_DB_PATH")
    checkpoint_dir: str = Field(default=".checkpoints", alias="CHECKPOINT_DIR")

    @property
    def audit_db_abspath(self) -> Path:
        p = PROJECT_ROOT / self.audit_db_path
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def checkpoint_abspath(self) -> Path:
        p = PROJECT_ROOT / self.checkpoint_dir
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def data_dir(self) -> Path:
        return PROJECT_ROOT / "mock_services" / "data"


@lru_cache
def get_settings() -> Settings:
    return Settings()
