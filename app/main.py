"""CEKP FastAPI entrypoint."""
from fastapi import FastAPI

from app.api import ingestion, query
from app.core.config import settings
from app.core.db import Base, engine

app = FastAPI(
    title=settings.app_name,
    description="Connecting fragmented enterprise knowledge sources into an "
    "intelligent, explainable, and secure knowledge layer.",
    version="0.1.0",
)


@app.on_event("startup")
def on_startup():
    # v1 uses create_all for simplicity; Alembic migrations are a Month 3 upgrade
    # once the schema stabilizes.
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health():
    return {"status": "ok", "app": settings.app_name}


app.include_router(ingestion.router)
app.include_router(query.router)
