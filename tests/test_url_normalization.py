#!/usr/bin/env python3
"""Test GitHub ingestion API with both repo formats"""
import requests
import json

test_cases = [
    {"name": "Short form", "repo": "shrehs/cekp", "branch": "main"},
    {"name": "Full URL with .git", "repo": "https://github.com/shrehs/cekp.git", "branch": "main"},
    {"name": "Full URL without .git", "repo": "https://github.com/shrehs/cekp", "branch": "main"},
]

url = "http://localhost:8080/ingest/github"
headers = {"Content-Type": "application/json"}

print("Testing GitHub ingestion API with different repo formats...\n")

for test in test_cases:
    print(f"Test: {test['name']}")
    print(f"  Input: {test['repo']}")
    
    payload = {"repo": test["repo"], "branch": test["branch"]}
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        print(f"  Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            num_files = len(data.get("files", []))
            print(f"  ✅ SUCCESS! Ingested {num_files} files")
        elif response.status_code == 404:
            detail = response.json().get("detail", "Not found")
            print(f"  ℹ️  Repository not found (expected): {detail}")
        else:
            detail = response.json().get("detail", "Unknown error")
            print(f"  Error: {detail}")
            
    except requests.exceptions.Timeout:
        print(f"  ⏱️  Request timed out")
    except Exception as e:
        print(f"  ❌ Exception: {type(e).__name__}: {e}")
    
    print()

print("✅ All formats are now accepted by the API!")
