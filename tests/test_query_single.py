#!/usr/bin/env python3
import httpx
import json

response = httpx.post(
    "http://localhost:8080/query/trace",
    json={
        "question": "Where is the PythonAstGraphBuilder class defined?",
        "top_k": 5,
        "department": None
    }
)

print(f"Status: {response.status_code}")
print(f"Response:\n{json.dumps(response.json(), indent=2)}")
