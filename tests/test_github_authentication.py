#!/usr/bin/env python3
"""
GitHub Token Authentication Guide and Test

This demonstrates how to use GitHub Personal Access Token (PAT) to:
1. Remove rate limiting (up to 5,000 requests/hour vs 60 unauthenticated)
2. Support ingesting private repositories
3. Get better rate-limit diagnostics

## Setup

1. Create a GitHub Personal Access Token (PAT):
   - Go to https://github.com/settings/tokens
   - Click "Generate new token (classic)"
   - Select scopes: `public_repo` (for public repos) or `repo` (for private too)
   - Copy the token

2. Set the environment variable BEFORE starting Docker:
   
   On Linux/macOS:
   ```bash
   export CEKP_GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxx
   docker compose -f docker/docker-compose.yml up -d
   ```
   
   On Windows PowerShell:
   ```powershell
   $env:CEKP_GITHUB_TOKEN = "ghp_xxxxxxxxxxxxxxxxxxxxx"
   docker compose -f docker/docker-compose.yml up -d
   ```
   
   Or, add to your .env file in the project root:
   ```
   CEKP_GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxx
   ```
   Then: `docker compose up -d`

## Benefits

✅ **Higher Rate Limits**: 5,000 requests/hour (vs 60 unauthenticated)
✅ **Private Repos**: Can ingest private repositories you have access to
✅ **Better Diagnostics**: Rate-limit errors include reset time
✅ **Automatic**: No changes to your code - token is used automatically
"""

import requests
import json
from datetime import datetime

def test_github_ingestion(repo: str, branch: str = "main"):
    """Test GitHub ingestion with current token configuration."""
    url = "http://localhost:8080/ingest/github"
    payload = {"repo": repo, "branch": branch}
    headers = {"Content-Type": "application/json"}
    
    print(f"\nTesting GitHub Ingestion")
    print(f"{'='*60}")
    print(f"Repository: {repo}")
    print(f"Branch: {branch}")
    print()
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=60)
        print(f"Status Code: {response.status_code}")
        print(f"Response:")
        print(json.dumps(response.json(), indent=2))
        
        if response.status_code == 200:
            print("\n✅ SUCCESS: Repository ingested successfully!")
            data = response.json()
            if "documents_ingested" in data:
                print(f"   Documents ingested: {data['documents_ingested']}")
        elif response.status_code == 429:
            print("\n⚠️  RATE LIMIT EXCEEDED")
            print("   To fix: Set CEKP_GITHUB_TOKEN environment variable with a GitHub PAT")
            print("   See https://github.com/settings/tokens for creating a token")
        elif response.status_code == 404:
            print(f"\n❌ Repository not found or is private without credentials")
            print("   If this is a private repo, make sure your token includes repo access")
        
    except requests.exceptions.Timeout:
        print("\n⏱️  Request timed out (repo may be very large)")
    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    print(__doc__)
    
    # Example: Test with a public repository
    print("\n" + "="*60)
    print("EXAMPLE 1: Public Repository (no token needed)")
    print("="*60)
    test_github_ingestion("octocat/Hello-World", "master")
    
    # Example: Test with larger public repository
    print("\n" + "="*60)
    print("EXAMPLE 2: Larger Repository (token recommended)")
    print("="*60)
    test_github_ingestion("facebook/react", "main")
