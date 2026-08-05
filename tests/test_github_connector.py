"""
Tests for the GitHub ingestion connector's error boundaries. Mocks
httpx.get() directly rather than hitting the real GitHub API, so these
run offline and don't depend on rate limits or a specific repo staying
public.
"""
from unittest.mock import Mock, patch

import httpx
import pytest

from app.ingestion.github_connector import (
    GithubIngestionError,
    RepoNotFoundError,
    list_repo_files,
)


def _mock_response(status_code: int, json_data: dict | None = None) -> Mock:
    resp = Mock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"{status_code} error", request=Mock(), response=resp
        )
    else:
        resp.raise_for_status.return_value = None
    return resp


def test_nonexistent_repo_raises_repo_not_found_not_a_raw_exception():
    with patch("httpx.get", return_value=_mock_response(404)):
        with pytest.raises(RepoNotFoundError):
            list_repo_files("nonexistent-owner/nonexistent-repo")


def test_private_repo_without_credentials_raises_repo_not_found():
    """
    GitHub returns 404 (not 403) for private repos without credentials --
    same code path as a genuinely nonexistent repo, deliberately (see
    module docstring in github_connector.py).
    """
    with patch("httpx.get", return_value=_mock_response(404)):
        with pytest.raises(RepoNotFoundError):
            list_repo_files("some-org/some-private-repo")


def test_other_api_error_raises_generic_ingestion_error_not_repo_not_found():
    """A 500 from GitHub's side (or a rate limit 403) shouldn't be misreported as 'not found'."""
    with patch("httpx.get", return_value=_mock_response(500)):
        with pytest.raises(GithubIngestionError) as exc_info:
            list_repo_files("some-org/some-repo")
        assert not isinstance(exc_info.value, RepoNotFoundError)


def test_empty_repository_returns_empty_list_not_an_error():
    """An empty repo (valid, just no files) should return [], not raise."""
    with patch("httpx.get", return_value=_mock_response(200, {"tree": []})):
        result = list_repo_files("some-org/empty-repo")
        assert result == []


def test_successful_listing_filters_to_blobs_only():
    tree = {
        "tree": [
            {"path": "README.md", "type": "blob"},
            {"path": "src", "type": "tree"},  # a directory, not a file -- must be excluded
            {"path": "src/main.py", "type": "blob"},
        ]
    }
    with patch("httpx.get", return_value=_mock_response(200, tree)):
        result = list_repo_files("some-org/some-repo")
        assert len(result) == 2
        assert all(item["type"] == "blob" for item in result)
