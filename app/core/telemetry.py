"""OpenTelemetry configuration for CEKP."""

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor


def configure_telemetry(app, engine) -> None:
    """Configure tracing for CEKP."""

    resource = Resource.create(
        {
            "service.name": "cekp-api",
            "service.version": "0.1.0",
            "deployment.environment": "local",
        }
    )

    provider = TracerProvider(resource=resource)

    provider.add_span_processor(
        SimpleSpanProcessor(
            ConsoleSpanExporter()
        )
    )

    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app)

    SQLAlchemyInstrumentor().instrument(
        engine=engine
    )