#!/usr/bin/env python3
"""Test GitHub ingestion endpoint with smaller repos"""
import requests
import json

# Use smaller repos for testing
test_repos = [
    {"repo": "shrehs/cekp", "branch": "main"},  # The actual project
]

url = "http://localhost:8080/ingest/github"
headers = {"Content-Type": "application/json"}

print("Testing GitHub ingestion endpoint...\n")

for test in test_repos:
    print(f"Testing: {test['repo']} (branch: {test['branch']})")
    print(f"Timeout: 120 seconds")
    try:
        response = requests.post(url, json=test, headers=headers, timeout=120)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, dict):
                num_files = len(data.get("files", []))
                print(f"✅ SUCCESS! Response received with {num_files} files")
                if num_files > 0:
                    print(f"Sample files: {data['files'][:3]}")
            else:
                print(f"✅ Response received: {type(data)}")
        else:
            detail = response.json().get("detail", "Unknown error")
            print(f"Response: {detail}")
            # Check if it's the missing git error (which would indicate our fix didn't work)
            if "Git is not installed" in str(detail):
                print("❌ ERROR: Git binary still missing in container!")
                
    except requests.exceptions.Timeout:
        print("⚠️  Request timed out after 120 seconds (repo may be too large)")
    except requests.exceptions.ConnectionError as e:
        print(f"❌ Connection error: {e}")
    except Exception as e:
        print(f"❌ Exception: {type(e).__name__}: {e}")
    
    print()
