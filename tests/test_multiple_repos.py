#!/usr/bin/env python3
"""Test GitHub ingestion endpoint with different repos"""
import requests
import json

test_repos = [
    {"repo": "https://github.com/torvalds/linux.git", "branch": "master"},
    {"repo": "https://github.com/tensorflow/tensorflow.git", "branch": "master"},
    {"repo": "https://github.com/python/cpython.git", "branch": "main"},
]

url = "http://localhost:8080/ingest/github"
headers = {"Content-Type": "application/json"}

print("Testing GitHub ingestion with various public repos...\n")

for test in test_repos:
    print(f"Testing: {test['repo']} (branch: {test['branch']})")
    try:
        response = requests.post(url, json=test, headers=headers, timeout=30)
        print(f"  Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, dict) and "files" in data:
                print(f"  ✅ Success! Found {len(data['files'])} files")
            else:
                print(f"  ✅ Response received: {type(data)}")
        else:
            detail = response.json().get("detail", "Unknown error")
            print(f"  ❌ Error: {detail}")
            # Check if it's the missing git error (which we're fixing)
            if "Git is not installed" in str(detail):
                print("     ERROR: Git binary still missing in container!")
    except Exception as e:
        print(f"  ❌ Exception: {e}")
    
    print()
