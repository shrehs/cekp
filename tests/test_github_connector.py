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
    GitHubRateLimitError,
    list_repo_files,
    normalize_repo,
)


def _mock_response(status_code: int, json_data: dict | None = None) -> Mock:
    resp = Mock()
    resp.status_code = status_code
    resp.text = "Mock error response"  # Default error text
    resp.json.return_value = json_data or {}
    resp.headers = {}  # Default empty headers
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"{status_code} error", request=Mock(), response=resp
        )
    else:
        resp.raise_for_status.return_value = None
    return resp


# Tests for normalize_repo function
def test_normalize_repo_short_form():
    """Short form (owner/repo) should pass through unchanged."""
    assert normalize_repo("owner/repo") == "owner/repo"


def test_normalize_repo_full_url_with_git_suffix():
    """Full GitHub URL with .git suffix should be normalized."""
    assert normalize_repo("https://github.com/owner/repo.git") == "owner/repo"


def test_normalize_repo_full_url_without_git_suffix():
    """Full GitHub URL without .git suffix should still be normalized."""
    assert normalize_repo("https://github.com/owner/repo") == "owner/repo"


def test_normalize_repo_with_whitespace():
    """Whitespace should be stripped."""
    assert normalize_repo("  https://github.com/owner/repo.git  ") == "owner/repo"
    assert normalize_repo("  owner/repo  ") == "owner/repo"


def test_normalize_repo_handles_real_world_examples():
    """Test common real-world input formats."""
    assert normalize_repo("https://github.com/shrehs/cekp.git") == "shrehs/cekp"
    assert normalize_repo("https://github.com/torvalds/linux.git") == "torvalds/linux"
    assert normalize_repo("torvalds/linux") == "torvalds/linux"


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


def test_missing_runtime_dependency_raises_clear_ingestion_error():
    with patch("httpx.get", side_effect=FileNotFoundError("git")):
        with pytest.raises(GithubIngestionError, match="Git is not installed"):
            list_repo_files("some-org/some-repo")


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


def test_list_repo_files_accepts_full_github_url():
    """Verify that list_repo_files accepts and normalizes full GitHub URLs."""
    tree = {"tree": [{"path": "README.md", "type": "blob"}]}
    with patch("httpx.get", return_value=_mock_response(200, tree)) as mock_get:
        result = list_repo_files("https://github.com/owner/repo.git")
        assert len(result) == 1
        # Verify the normalized form was used in the API call
        mock_get.assert_called_once()
        url = mock_get.call_args[0][0]
        assert "owner/repo" in url
        assert "https://github.com/" not in url  # URL should not contain the GitHub prefix


def test_list_repo_files_both_formats_produce_same_api_call():
    """Verify that both input formats result in the same GitHub API call."""
    tree = {"tree": [{"path": "README.md", "type": "blob"}]}
    
    with patch("httpx.get", return_value=_mock_response(200, tree)) as mock_get:
        list_repo_files("owner/repo")
        short_form_call = mock_get.call_args[0][0]
    
    with patch("httpx.get", return_value=_mock_response(200, tree)) as mock_get:
        list_repo_files("https://github.com/owner/repo.git")
        full_url_call = mock_get.call_args[0][0]
    
    assert short_form_call == full_url_call


# Tests for rate-limit error handling
def test_rate_limit_error_is_raised_on_403():
    """HTTP 403 with rate limit headers should raise GitHubRateLimitError."""
    resp = Mock()
    resp.status_code = 403
    resp.json.return_value = {}
    resp.text = "API rate limit exceeded"
    resp.headers = {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1234567890"}
    resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "403 Forbidden", request=Mock(), response=resp
    )
    
    with patch("httpx.get", return_value=resp):
        with pytest.raises(GitHubRateLimitError) as exc_info:
            list_repo_files("some-org/some-repo")
        
        assert exc_info.value.remaining == 0
        assert exc_info.value.reset_timestamp == 1234567890


def test_rate_limit_error_includes_diagnostic_message():
    """GitHubRateLimitError message should be user-friendly and include reset time."""
    error = GitHubRateLimitError(remaining=0, reset_timestamp=1234567890)
    assert "rate limit exceeded" in str(error).lower()
    assert "0" in str(error)  # remaining count
    assert "resets at" in str(error).lower()  # human-readable reset time


def test_rate_limit_error_handles_missing_reset_time():
    """GitHubRateLimitError should gracefully handle missing reset timestamp."""
    error = GitHubRateLimitError(remaining=0, reset_timestamp=None)
    assert "rate limit exceeded" in str(error).lower()
    assert "unknown" in str(error).lower()


def test_authenticated_requests_include_auth_header():
    """If CEKP_GITHUB_TOKEN is set, requests should include Authorization header."""
    from app.core.config import Settings
    from unittest.mock import patch as mock_patch
    
    tree = {"tree": [{"path": "README.md", "type": "blob"}]}
    
    # Mock settings with a token
    with mock_patch("app.ingestion.github_connector.settings") as mock_settings:
        mock_settings.github_token = "ghp_test_token_123"
        mock_settings.github_api_base = "https://api.github.com"
        
        with patch("httpx.get", return_value=_mock_response(200, tree)) as mock_get:
            list_repo_files("owner/repo")
            
            # Verify Authorization header was passed
            mock_get.assert_called_once()
            headers = mock_get.call_args[1]["headers"]
            assert "Authorization" in headers
            assert headers["Authorization"] == "Bearer ghp_test_token_123"


def test_unauthenticated_requests_no_auth_header():
    """If CEKP_GITHUB_TOKEN is not set, requests should not include Authorization header."""
    from unittest.mock import patch as mock_patch
    
    tree = {"tree": [{"path": "README.md", "type": "blob"}]}
    
    # Mock settings without a token
    with mock_patch("app.ingestion.github_connector.settings") as mock_settings:
        mock_settings.github_token = None
        mock_settings.github_api_base = "https://api.github.com"
        
        with patch("httpx.get", return_value=_mock_response(200, tree)) as mock_get:
            list_repo_files("owner/repo")
            
            # Verify Authorization header was NOT passed
            mock_get.assert_called_once()
            headers = mock_get.call_args[1]["headers"]
            assert "Authorization" not in headers or headers.get("Authorization") is None
