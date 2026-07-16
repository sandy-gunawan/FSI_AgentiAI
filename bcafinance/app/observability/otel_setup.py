"""OpenTelemetry / Azure Monitor wiring for the invoice-review demo.

Points telemetry at:
  * Azure Application Insights  (when APPLICATIONINSIGHTS_CONNECTION_STRING set)
  * a local OTLP endpoint / Aspire dashboard (when OTEL_EXPORTER_OTLP_ENDPOINT set)

Call ``setup_observability()`` once at process startup. Foundry-side traces are
recorded automatically by the Foundry project (Traces/Monitor tab) in addition
to this app-level telemetry.
"""
from __future__ import annotations

import logging

from app.core.config import get_settings

_CONFIGURED = False
logger = logging.getLogger("bca.observability")


def setup_observability() -> None:
    """Idempotently configure telemetry based on environment settings."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    settings = get_settings()
    if not settings.enable_instrumentation:
        _CONFIGURED = True
        return

    # Azure Application Insights (production monitoring).
    if settings.applicationinsights_connection_string:
        try:
            from azure.monitor.opentelemetry import configure_azure_monitor

            configure_azure_monitor(
                connection_string=settings.applicationinsights_connection_string,
                enable_live_metrics=True,
            )
            logger.info("Azure Monitor (App Insights) telemetry enabled.")
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to configure Azure Monitor: %s", exc)

    # Local OTLP / Aspire dashboard (best-effort).
    if settings.otel_exporter_otlp_endpoint:
        try:
            from opentelemetry import trace
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            provider = TracerProvider(resource=Resource.create(
                {"service.name": settings.otel_service_name}))
            provider.add_span_processor(BatchSpanProcessor(
                OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint, insecure=True)))
            trace.set_tracer_provider(provider)
            logger.info("OTLP exporter enabled -> %s", settings.otel_exporter_otlp_endpoint)
        except Exception as exc:  # pragma: no cover
            logger.warning("Failed to configure OTLP exporter: %s", exc)

    _CONFIGURED = True
