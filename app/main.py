"""CEKP FastAPI entrypoint."""

from fastapi import FastAPI

from app.api import ingestion, query
from app.core.config import settings
from app.core.db import Base, engine
from fastapi import Request
import logging
import time
import uuid
from app.core.logging import configure_logging
from app.core.telemetry import configure_telemetry
from prometheus_fastapi_instrumentator import Instrumentator
from app.core.metrics import HTTP_OUTCOME_TOTAL

configure_logging()

app = FastAPI(
    title=settings.app_name,
    description=(
        "Connecting fragmented enterprise knowledge sources into an "
        "intelligent, explainable, and secure knowledge layer."
    ),
    version="0.1.0",
)
configure_telemetry(app, engine)
Instrumentator().instrument(app).expose(app)
logger = logging.getLogger("cekp")

@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id
    start_time = time.perf_counter()

    try:
        response = await call_next(request)

        duration_ms = round(
            (time.perf_counter() - start_time) * 1000,
            2,
        )

        logger.info(
            "request_completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )

        response.headers["X-Request-ID"] = request_id
        HTTP_OUTCOME_TOTAL.labels(
            outcome="ok" if response.status_code < 400 else "error",
            status_code=str(response.status_code),
        ).inc()

        return response

    except Exception:
        duration_ms = round(
            (time.perf_counter() - start_time) * 1000,
            2,
        )

        logger.exception(
            "request_failed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "duration_ms": duration_ms,
            },
        )
        HTTP_OUTCOME_TOTAL.labels(outcome="error", status_code="500").inc()

        raise


@app.on_event("startup")
def on_startup():
    # v1 uses create_all for simplicity; Alembic migrations are a Month 3 upgrade
    # once the schema stabilizes.
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health():
    """Liveness check: confirms that the API process is running."""
    return {
        "status": "ok",
        "app": settings.app_name,
    }


@app.get("/ready")
def readiness():
    """Readiness check for the API and its required infrastructure."""

    dependencies = {
        "postgres": "unknown",
        "qdrant": "unknown",
        "neo4j": "unknown",
    }

    # PostgreSQL
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")

        dependencies["postgres"] = "ok"

    except Exception:
        dependencies["postgres"] = "error"

    # Qdrant
    try:
        from qdrant_client import QdrantClient

        qdrant = QdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
        )

        qdrant.get_collections()

        dependencies["qdrant"] = "ok"

    except Exception:
        dependencies["qdrant"] = "error"

    # Neo4j
    try:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(
                settings.neo4j_user,
                settings.neo4j_password,
            ),
        )

        with driver.session() as session:
            session.run("RETURN 1").single()

        driver.close()

        dependencies["neo4j"] = "ok"

    except Exception:
        dependencies["neo4j"] = "error"

    ready = all(
        status == "ok"
        for status in dependencies.values()
    )

    return {
        "status": "ready" if ready else "not_ready",
        "app": settings.app_name,
        "dependencies": dependencies,
    }


app.include_router(ingestion.router)
app.include_router(query.router)