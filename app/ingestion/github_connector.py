"""
GitHub ingestion connector. v1 pulls files from a public repo's default
branch via the REST API (no GitHub App/webhook push flow yet -- that's
the natural upgrade for the n8n-driven event pipeline in the full
architecture, Section 5.1).

GithubIngestionError / RepoNotFoundError: expected, recoverable failure
modes -- mapped to a clean 4xx at the API layer, never a raw 500.

Note: GitHub's API returns 404 for both a genuinely nonexistent repo
AND a private repo you don't have credentials for -- it does not
distinguish the two. That's GitHub's own no-leakage design (the same
principle used in this codebase's PolicyEvaluator/build_user_response:
don't confirm the existence of something the caller can't access), and
this connector doesn't try to un-conflate it.
"""
import base64

import httpx

from app.core.config import settings

# Extensions worth ingesting as knowledge -- skip binaries/lockfiles/etc.
TEXT_EXTENSIONS = {".md", ".mdx", ".txt", ".py", ".js", ".ts", ".yaml", ".yml", ".json"}


class GithubIngestionError(Exception):
    """Base class for expected GitHub ingestion failures -- always mapped to a 4xx/5xx, never a raw 500."""


class RepoNotFoundError(GithubIngestionError):
    """
    Repo or branch not found, OR a private repo without credentials --
    GitHub's API returns 404 for both; this connector can't and doesn't
    try to distinguish them (see module docstring).
    """


def _should_ingest(path: str, path_filter: str | None) -> bool:
    if path_filter and path_filter not in path:
        return False
    return any(path.endswith(ext) for ext in TEXT_EXTENSIONS)


def list_repo_files(repo: str, branch: str = "main") -> list[dict]:
    """Returns the full recursive file tree for a repo branch."""
    url = f"{settings.github_api_base}/repos/{repo}/git/trees/{branch}?recursive=1"
    try:
        resp = httpx.get(url, timeout=30)
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise RepoNotFoundError(
                f"'{repo}' (branch '{branch}') not found, or is private without credentials."
            ) from e
        raise GithubIngestionError(f"GitHub API error for {repo}: {e}") from e
    except httpx.HTTPError as e:
        raise GithubIngestionError(f"Network error reaching GitHub API for {repo}: {e}") from e

    tree = resp.json().get("tree", [])
    return [item for item in tree if item.get("type") == "blob"]


def fetch_file_content(repo: str, path: str, branch: str = "main") -> str:
    url = f"{settings.github_api_base}/repos/{repo}/contents/{path}?ref={branch}"
    resp = httpx.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if data.get("encoding") != "base64":
        raise ValueError(f"Unexpected encoding for {path}: {data.get('encoding')}")
    return base64.b64decode(data["content"]).decode("utf-8", errors="replace")


def fetch_repo_documents(repo: str, branch: str = "main", path_filter: str | None = None) -> list[dict]:
    """
    Returns a list of {"path": ..., "text": ...} for every ingestible file
    in the repo. Caller is responsible for chunking/embedding/storing.
    Raises RepoNotFoundError / GithubIngestionError for repo-level
    failures (see list_repo_files); individual unreadable files within
    an otherwise-valid repo are skipped, not fatal.
    """
    files = list_repo_files(repo, branch)  # raises here propagate to the caller
    documents = []
    for f in files:
        path = f["path"]
        if not _should_ingest(path, path_filter):
            continue
        try:
            text = fetch_file_content(repo, path, branch)
        except Exception:
            continue  # skip unreadable/binary files rather than failing the whole ingest
        if text.strip():
            documents.append({"path": path, "text": text})
    return documents
