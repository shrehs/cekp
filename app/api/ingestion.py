"""Ingestion endpoints: PDF upload, GitHub repo pull, and local-path pull."""
import logging
import os
import shutil
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.graph_store import get_driver
from app.graph.ast_builder import PythonAstGraphBuilder
from app.graph.models import SourceFile
from app.graph.neo4j_repository import Neo4jGraphRepository
from app.ingestion.github_connector import fetch_repo_documents, GithubIngestionError, RepoNotFoundError, GitHubRateLimitError, TEXT_EXTENSIONS
from app.ingestion.pdf_connector import extract_pdf_text, PdfIngestionError
from app.ingestion.pipeline import ingest_document
from app.models.schemas import IngestGithubRequest, IngestLocalPathRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingest", tags=["ingestion"])

UPLOAD_DIR = "/app/data/uploads"

# Local-path ingestion reads from the container's filesystem with no
# auth yet -- restricted to these roots specifically (not arbitrary
# paths) so the endpoint can't be used to read anything else on disk.
# /app/data covers repos git-cloned on the host into ./data (matching
# scripts/validate_graph_builder.py's convention); /app/app covers
# ingesting CEKP's own source for self-referential dogfooding.
ALLOWED_LOCAL_ROOTS = ["/app/data", "/app/app"]

SKIP_DIRS = {".git", "__pycache__", "node_modules", "venv", ".venv", "build", "dist", "egg-info"}


@router.post("/pdf")
async def ingest_pdf(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="File must have a name")
    
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    temp_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()}_{file.filename}")

    with open(temp_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        text = extract_pdf_text(temp_path)
    except PdfIngestionError as e:
        raise HTTPException(status_code=422, detail=str(e))
    finally:
        os.remove(temp_path)

    document = ingest_document(
        db,
        title=file.filename,
        source_system="pdf",
        source_ref=file.filename,
        raw_text=text,
    )
    return {"document_id": document.id, "title": document.title, "status": "ingested"}


def _validate_local_path(path: str) -> str:
    resolved = os.path.abspath(path)
    if not any(resolved == root or resolved.startswith(root + os.sep) for root in ALLOWED_LOCAL_ROOTS):
        raise HTTPException(
            status_code=403,
            detail=f"Path must be under one of: {ALLOWED_LOCAL_ROOTS} (got resolved path {resolved})",
        )
    if not os.path.isdir(resolved):
        raise HTTPException(status_code=404, detail=f"Directory not found: {resolved}")
    return resolved


def _load_local_documents(local_path: str, path_filter: str | None) -> list[dict]:
    documents = []
    for root, dirs, filenames in os.walk(local_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.endswith(".egg-info")]
        for filename in filenames:
            if not any(filename.endswith(ext) for ext in TEXT_EXTENSIONS):
                continue
            full_path = os.path.join(root, filename)
            rel_path = os.path.relpath(full_path, local_path).replace(os.sep, "/")
            if path_filter and path_filter not in rel_path:
                continue
            try:
                with open(full_path, encoding="utf-8", errors="replace") as f:
                    text = f.read()
            except OSError:
                continue  # skip unreadable files rather than failing the whole ingest
            if text.strip():
                documents.append({"path": rel_path, "text": text})
    return documents


def _ingest_documents_and_graph(
    db: Session,
    documents: list[dict],
    *,
    source_system: str,
    source_prefix: str,
    repo_id: str,
    repo_name: str,
    source_ref: str,
) -> dict:
    """
    Shared by /ingest/github and /ingest/local: chunk+embed every
    document into Qdrant, then build and persist the code-structure
    graph from whatever's Python. One code path so the two ingestion
    sources can't silently drift apart from each other.
    """
    ingested = []
    for doc in documents:
        result = ingest_document(
            db,
            title=doc["path"],
            source_system=source_system,
            source_ref=f"{source_prefix}/{doc['path']}",
            raw_text=doc["text"],
        )
        ingested.append({"document_id": result.id, "title": result.title})

    # Graph building + persistence. Deliberately non-fatal: chunking/
    # embedding above already succeeded, and a graph-side problem
    # (Neo4j down, a bad parse) shouldn't undo or block the
    # vector-search ingestion that already completed -- same principle
    # as audit logging being non-fatal in app/api/query.py.
    graph_status = "skipped"
    graph_error = None
    try:
        source_files = [SourceFile(path=doc["path"], text=doc["text"]) for doc in documents]
        build_result = PythonAstGraphBuilder().build(
            source_files, repo_id=repo_id, repo_name=repo_name, source_ref=source_ref
        )

        repository = Neo4jGraphRepository(get_driver())
        repository.create_constraints()
        repository.clear_repository(repo_id)  # re-ingesting a changed repo shouldn't leave stale graph data
        repository.persist(build_result.graph)

        graph_status = "persisted"
        logger.info(
            "Graph persisted for %s: %d nodes, %d edges (%d skipped, %d parse errors)",
            source_ref, len(build_result.graph.nodes), len(build_result.graph.edges),
            len(build_result.skipped_files), len(build_result.parse_errors),
        )
    except Exception as e:
        graph_status = "failed"
        graph_error = str(e)
        logger.exception("Graph persistence failed for %s (vector ingestion still succeeded)", source_ref)

    return {
        "documents_ingested": len(ingested),
        "documents": ingested,
        "graph_status": graph_status,  # "persisted" | "skipped" | "failed"
        **({"graph_error": graph_error} if graph_error else {}),
    }


@router.post("/github")
async def ingest_github(request: IngestGithubRequest, db: Session = Depends(get_db)):
    try:
        documents = fetch_repo_documents(
            request.repo, branch=request.branch, path_filter=request.path_filter
        )
    except RepoNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except GitHubRateLimitError as e:
        # Rate limit exceeded. Return diagnostic info.
        raise HTTPException(
            status_code=429,
            detail={
                "error": "GitHub API rate limit exceeded",
                "message": str(e),
                "rate_limit_remaining": e.remaining,
                "rate_limit_resets_at": e.reset_timestamp,
            },
        )
    except GithubIngestionError as e:
        # Other upstream (GitHub API) failure -- network issue, unexpected response shape, etc.
        # 502, not 500: this is a dependency failing, not a bug in our code.
        raise HTTPException(status_code=502, detail=str(e))

    if not documents:
        raise HTTPException(
            status_code=404,
            detail=f"No ingestible files found in {request.repo} (check repo name, branch, and path_filter).",
        )

    result = _ingest_documents_and_graph(
        db, documents,
        source_system="github",
        source_prefix=request.repo,
        repo_id=request.repo.replace("/", "_"),
        repo_name=request.repo.split("/")[-1],
        source_ref=request.repo,
    )
    return {"repo": request.repo, **result}


@router.post("/local")
async def ingest_local(request: IngestLocalPathRequest, db: Session = Depends(get_db)):
    """
    Ingest from a local filesystem path already present in the container
    (see ALLOWED_LOCAL_ROOTS) instead of via the GitHub API -- for repos
    not (yet) pushed to GitHub, including CEKP's own source for
    self-referential validation.
    """
    resolved_path = _validate_local_path(request.path)
    documents = _load_local_documents(resolved_path, request.path_filter)

    if not documents:
        raise HTTPException(
            status_code=404,
            detail=f"No ingestible files found under {resolved_path} (check path and path_filter).",
        )

    repo_name = request.repo_name or os.path.basename(resolved_path.rstrip("/"))
    result = _ingest_documents_and_graph(
        db, documents,
        source_system="local",
        source_prefix=repo_name,
        repo_id=repo_name.replace("/", "_"),
        repo_name=repo_name,
        source_ref=resolved_path,
    )
    return {"path": resolved_path, "repo_name": repo_name, **result}