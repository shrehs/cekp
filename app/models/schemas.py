"""API-facing Pydantic schemas -- kept separate from DB models."""
from pydantic import BaseModel


class IngestGithubRequest(BaseModel):
    repo: str          # "owner/name"
    path_filter: str | None = None  # e.g. only ".md" or "docs/"
    branch: str = "main"


class IngestLocalPathRequest(BaseModel):
    path: str          # must resolve under an ALLOWED_LOCAL_ROOTS entry (see app/api/ingestion.py)
    repo_name: str | None = None  # defaults to the path's basename
    path_filter: str | None = None


class QueryRequest(BaseModel):
    question: str
    top_k: int = 5
    department: str | None = None  # used for RBAC filtering later


class RetrievedChunk(BaseModel):
    chunk_id: str
    document_id: str
    document_title: str
    text: str
    score: float
    source_system: str


class QueryResponse(BaseModel):
    question: str
    strategy_used: str
    results: list[RetrievedChunk]