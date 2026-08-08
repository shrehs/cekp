#!/usr/bin/env python3
"""Test GitHub ingestion endpoint with correct format"""
import requests
import json

test_repos = [
    {"repo": "torvalds/linux", "branch": "master"},
    {"repo": "tensorflow/tensorflow", "branch": "master"},
    {"repo": "python/cpython", "branch": "main"},
]

url = "http://localhost:8080/ingest/github"
headers = {"Content-Type": "application/json"}

print("Testing GitHub ingestion with correct repo format (owner/repo)...\n")

for test in test_repos:
    print(f"Testing: {test['repo']} (branch: {test['branch']})")
    try:
        response = requests.post(url, json=test, headers=headers, timeout=30)
        print(f"  Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, dict):
                num_files = len(data.get("files", []))
                print(f"  ✅ Success! Response received with {num_files} files")
            else:
                print(f"  ✅ Response received: {type(data)}")
        else:
            detail = response.json().get("detail", "Unknown error")
            print(f"  Status: {detail}")
            # Check if it's the missing git error (which we're fixing)
            if "Git is not installed" in str(detail):
                print("     ❌ ERROR: Git binary still missing in container!")
            else:
                print("     (Expected: repo/branch not found on GitHub)")
    except Exception as e:
        print(f"  ❌ Exception: {e}")
    
    print()
