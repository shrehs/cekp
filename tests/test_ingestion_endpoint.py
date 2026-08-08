#!/usr/bin/env python3
"""Test GitHub ingestion endpoint"""
import requests
import json
import sys

def test_github_ingestion():
    """Test the GitHub ingestion endpoint"""
    url = "http://localhost:8080/ingest/github"
    payload = {
        "repo": "https://github.com/shrehs/cekp.git",
        "branch": "main"
    }
    headers = {"Content-Type": "application/json"}
    
    print(f"Testing GitHub ingestion endpoint:")
    print(f"  URL: {url}")
    print(f"  Payload: {json.dumps(payload, indent=2)}")
    print()
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        print(f"Response Status: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        print(f"Response Body:")
        print(json.dumps(response.json(), indent=2))
        
        if response.status_code == 200:
            print("\n✅ SUCCESS: GitHub ingestion endpoint works!")
            return True
        else:
            print(f"\n❌ FAILED: Got status code {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("❌ ERROR: Failed to connect to http://localhost:8080")
        print("   Make sure Docker services are running")
        return False
    except Exception as e:
        print(f"❌ ERROR: {type(e).__name__}: {e}")
        return False

if __name__ == "__main__":
    success = test_github_ingestion()
    sys.exit(0 if success else 1)
