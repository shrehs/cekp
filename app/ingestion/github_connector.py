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
import json
import time
from http import HTTPStatus

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


class GitHubRateLimitError(GithubIngestionError):
    """Rate limit exceeded. Includes diagnostic information."""
    def __init__(self, remaining: int, reset_timestamp: int | None = None):
        self.remaining = remaining
        self.reset_timestamp = reset_timestamp
        reset_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(reset_timestamp)) if reset_timestamp else "unknown"
        message = f"GitHub API rate limit exceeded. Remaining: {remaining}. Resets at: {reset_time}"
        super().__init__(message)


def _get_github_headers() -> dict[str, str]:
    """Build headers for GitHub API requests, including authentication if configured."""
    headers = {"Accept": "application/vnd.github+json"}
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"
    return headers


def _handle_github_error(response: httpx.Response, repo: str) -> None:
    """Analyze GitHub error response and raise appropriate exception."""
    status = response.status_code
    remaining = response.headers.get("X-RateLimit-Remaining", "unknown")
    reset = response.headers.get("X-RateLimit-Reset")
    
    if status == 404:
        raise RepoNotFoundError(
            f"'{repo}' not found, or is private without credentials."
        )
    
    if status == 403:
        # Check if it's a rate limit error
        if "rate limit" in response.text.lower() or remaining == "0":
            reset_ts = int(reset) if reset else None
            raise GitHubRateLimitError(remaining=int(remaining) if remaining != "unknown" else 0, reset_timestamp=reset_ts)
        # Other 403 errors (e.g., insufficient permissions)
        raise GithubIngestionError(f"GitHub API access forbidden (403): {response.text[:200]}")
    
    raise GithubIngestionError(f"GitHub API error for {repo}: HTTP {status}: {response.text[:200]}")


def _should_ingest(path: str, path_filter: str | None) -> bool:
    if path_filter and path_filter not in path:
        return False
    return any(path.endswith(ext) for ext in TEXT_EXTENSIONS)


def normalize_repo(repo: str) -> str:
    """Normalize repo format to owner/repo.
    
    Accepts both:
    - Full GitHub URLs: https://github.com/owner/repo.git
    - Short form: owner/repo
    
    Returns: owner/repo
    """
    repo = repo.strip()
    
    if repo.startswith("https://github.com/"):
        repo = repo[len("https://github.com/"):]
    
    if repo.endswith(".git"):
        repo = repo[:-4]
    
    return repo


def list_repo_files(repo: str, branch: str = "main") -> list[dict]:
    """Returns the full recursive file tree for a repo branch.
    
    If a GitHub token is configured, uses authenticated requests (higher rate limits).
    Otherwise uses unauthenticated requests (60 requests/hour).
    """
    repo = normalize_repo(repo)
    url = f"{settings.github_api_base}/repos/{repo}/git/trees/{branch}?recursive=1"
    headers = _get_github_headers()
    
    try:
        resp = httpx.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
    except FileNotFoundError as e:
        raise GithubIngestionError(
            "Git is not installed in the API container. Install git in the Docker image before running GitHub ingestion."
        ) from e
    except httpx.HTTPStatusError as e:
        _handle_github_error(e.response, repo)
    except httpx.HTTPError as e:
        raise GithubIngestionError(f"Network error reaching GitHub API for {repo}: {e}") from e

    tree = resp.json().get("tree", [])
    return [item for item in tree if item.get("type") == "blob"]


def fetch_file_content(repo: str, path: str, branch: str = "main") -> str:
    """Fetch file content from GitHub repository with optional authentication."""
    repo = normalize_repo(repo)
    url = f"{settings.github_api_base}/repos/{repo}/contents/{path}?ref={branch}"
    headers = _get_github_headers()
    
    try:
        resp = httpx.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        _handle_github_error(e.response, repo)
    except httpx.HTTPError as e:
        raise GithubIngestionError(f"Network error reaching GitHub API for {repo}: {e}") from e
    
    data = resp.json()
    if data.get("encoding") != "base64":
        raise ValueError(f"Unexpected encoding for {path}: {data.get('encoding')}")
    return base64.b64decode(data["content"]).decode("utf-8", errors="replace")


def fetch_repo_documents(repo: str, branch: str = "main", path_filter: str | None = None) -> list[dict]:
    """
    Returns a list of {"path": ..., "text": ...} for every ingestible file
    
    Repo can be provided in multiple formats:
    - owner/repo (short form)
    - https://github.com/owner/repo.git (full GitHub URL)
    - https://github.com/owner/repo (GitHub URL without .git)
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
