"""Technical call log — captures the real service calls per request.

Populated by the workflow (Document Intelligence OCR, Foundry agent invocations,
Blob config reads). Stored per request so the portal can show concrete proof of
which Azure services were actually called, with endpoints and latency.
"""
from __future__ import annotations

_STORE: dict[str, list[dict]] = {}

# logical tool -> (protocol, human label)
_ENDPOINT = {
    "doc_intelligence:analyze": ("REST POST", "Azure AI Document Intelligence (prebuilt-invoice)"),
    "tools:upload-image": ("REST POST", "bcafinance tools service · /images"),
    "foundry:extractor-di": ("FOUNDRY", "Foundry agent · bca-invoice-extractor-di"),
    "foundry:extractor-di-agentic": ("FOUNDRY", "Foundry agent · bca-invoice-extractor-di-agentic (calls DI tool)"),
    "foundry:extractor-vision": ("FOUNDRY", "Foundry agent · bca-invoice-extractor-vision"),
    "foundry:reviewer": ("FOUNDRY", "Foundry agent · bca-invoice-reviewer"),
    "foundry:credit-context-rest": ("FOUNDRY", "Foundry agent · bca-credit-context-rest (SQL via REST tool)"),
    "foundry:credit-context-mcp": ("FOUNDRY", "Foundry agent · bca-credit-context-mcp (SQL via MCP tool)"),
    "blob:read-rules": ("BLOB GET", "Blob Storage · review_rules.yaml (hot-reload)"),
    "rules:evaluate": ("LOCAL", "Deterministic rules engine (config-driven)"),
}


def save(request_id: str, entries: list[dict]) -> None:
    _STORE[request_id] = list(entries)


def get(request_id: str) -> list[dict]:
    return _STORE.get(request_id, [])


def endpoint_for(tool: str) -> tuple[str, str]:
    return _ENDPOINT.get(tool, ("TOOL", tool))
