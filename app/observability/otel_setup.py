"""OpenTelemetry / Azure Monitor wiring for the agentic financing demo.

Agent Framework emits GenAI-semantic-convention traces, metrics and logs. This
module turns them on and points them at:
  * Azure Application Insights  (when APPLICATIONINSIGHTS_CONNECTION_STRING set)
  * a local OTLP endpoint / Aspire dashboard (when OTEL_EXPORTER_OTLP_ENDPOINT set)

Call `setup_observability()` once at process startup.
"""
from __future__ import annotations

import logging

from app.core.config import get_settings

_CONFIGURED = False
logger = logging.getLogger("bns.observability")


def setup_observability() -> None:
    """Idempotently configure telemetry based on environment settings."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    settings = get_settings()
    if not settings.enable_instrumentation:
        logger.info("Instrumentation disabled (ENABLE_INSTRUMENTATION=false).")
        _CONFIGURED = True
        return

    try:
        from agent_framework.observability import configure_otel_providers, enable_instrumentation
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("agent_framework.observability unavailable: %s", exc)
        _CONFIGURED = True
        return

    # 1) Azure Application Insights (production monitoring).
    if settings.applicationinsights_connection_string:
        try:
            from azure.monitor.opentelemetry import configure_azure_monitor

            from agent_framework.observability import create_resource

            configure_azure_monitor(
                connection_string=settings.applicationinsights_connection_string,
                resource=create_resource(),
                enable_live_metrics=True,
            )
            enable_instrumentation()
            logger.info("Azure Monitor (App Insights) telemetry enabled.")
        except Exception as exc:  # pragma: no cover
            logger.warning("Failed to configure Azure Monitor: %s", exc)

    # 2) Local OTLP / Aspire dashboard (best-effort; skip if collector absent).
    if settings.otel_exporter_otlp_endpoint:
        try:
            configure_otel_providers()
            logger.info("OTLP exporter enabled -> %s", settings.otel_exporter_otlp_endpoint)
        except Exception as exc:  # pragma: no cover
            logger.warning("Failed to configure OTLP exporter: %s", exc)

    _CONFIGURED = True
