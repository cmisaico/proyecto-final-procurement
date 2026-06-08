"""
OpenTelemetry distributed tracing setup — Fase 3 LLMOps.
"""
import os
from contextlib import contextmanager
from typing import Optional

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.propagate import set_global_textmap
from opentelemetry.propagators.b3 import B3MultiFormat

from app.core.logging import get_logger

logger = get_logger(__name__)

_tracer: Optional[trace.Tracer] = None


def setup_tracing(service_name: str = "procurement-api") -> None:
    global _tracer

    resource = Resource.create({SERVICE_NAME: service_name})
    provider = TracerProvider(resource=resource)

    otel_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    if otel_endpoint:
        try:
            otlp_exporter = OTLPSpanExporter(endpoint=otel_endpoint, insecure=True)
            provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
            logger.info("OTel OTLP exporter configured", extra={"endpoint": otel_endpoint})
        except Exception as e:
            logger.warning("OTel OTLP exporter failed, falling back to console", extra={"error": str(e)})
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    else:
        # Development fallback: no-op (don't pollute logs)
        pass

    trace.set_tracer_provider(provider)
    set_global_textmap(B3MultiFormat())
    _tracer = trace.get_tracer(service_name)

    # Auto-instrument httpx (used by Ollama client)
    HTTPXClientInstrumentor().instrument()

    logger.info("OpenTelemetry tracing initialized", extra={"service": service_name})


def get_tracer() -> trace.Tracer:
    if _tracer is None:
        return trace.get_tracer("procurement-api")
    return _tracer


def instrument_fastapi(app) -> None:
    FastAPIInstrumentor.instrument_app(app)


def get_current_trace_id() -> str:
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx and ctx.trace_id:
        return format(ctx.trace_id, "032x")
    return ""


def get_current_span_id() -> str:
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx and ctx.span_id:
        return format(ctx.span_id, "016x")
    return ""


@contextmanager
def span(name: str, attributes: dict = None):
    """Context manager for creating a manual OTel span."""
    tracer = get_tracer()
    with tracer.start_as_current_span(name) as s:
        if attributes:
            for k, v in attributes.items():
                s.set_attribute(k, str(v))
        yield s
