"""
OpenTelemetry tracing configuration for the DNA Toolkit backend.

Environment variables:
  OTEL_EXPORTER_OTLP_ENDPOINT  — OTLP HTTP endpoint (e.g. http://localhost:4318).
                                  When absent, a no-op tracer is used (zero overhead).
  OTEL_SERVICE_NAME            — Override the service name (default: dna-toolkit-backend).
  OTEL_CONSOLE_EXPORT          — Set to "true" to print spans to stdout (dev/debugging).

Usage:
  from backend.core.telemetry import get_tracer
  tracer = get_tracer(__name__)

  with tracer.start_as_current_span("my-operation") as span:
      span.set_attribute("some.key", value)
      ...
"""

import logging
import os

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

logger = logging.getLogger(__name__)

_configured = False


def configure_telemetry() -> None:
    """Configure the global OpenTelemetry TracerProvider.

    Safe to call multiple times — subsequent calls are no-ops.
    When neither OTEL_EXPORTER_OTLP_ENDPOINT nor OTEL_CONSOLE_EXPORT is set,
    the default no-op provider remains in place (opentelemetry-api does this
    automatically) so all downstream `tracer.start_as_current_span` calls are
    harmless zero-cost no-ops.
    """
    global _configured
    if _configured:
        return
    _configured = True

    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    console_export = os.getenv("OTEL_CONSOLE_EXPORT", "").lower() == "true"

    if not otlp_endpoint and not console_export:
        logger.info("OpenTelemetry: no exporter configured — tracing disabled (set OTEL_EXPORTER_OTLP_ENDPOINT to enable)")
        return

    service_name = os.getenv("OTEL_SERVICE_NAME", "dna-toolkit-backend")
    resource = Resource.create({SERVICE_NAME: service_name})
    provider = TracerProvider(resource=resource)

    if otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter  # type: ignore[import]
            exporter = OTLPSpanExporter(endpoint=f"{otlp_endpoint.rstrip('/')}/v1/traces")
            provider.add_span_processor(BatchSpanProcessor(exporter))
            logger.info(f"OpenTelemetry: OTLP trace export → {otlp_endpoint}")
        except Exception as exc:
            logger.warning(f"OpenTelemetry: could not initialise OTLP exporter: {exc}")

    if console_export:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        logger.info("OpenTelemetry: console span export enabled")

    trace.set_tracer_provider(provider)


def get_tracer(name: str) -> trace.Tracer:
    """Return a Tracer for the given instrumentation scope (typically ``__name__``)."""
    return trace.get_tracer(name)
