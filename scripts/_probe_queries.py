import httpx, json

queries = [
    "How does the planner escalate strategies?",
    "What is the confidence threshold for vector retrieval?",
    "Explain the escalation logic in the planner.",
    "What does the policy evaluator check?",
    "How are chunks embedded?",
]

for q in queries:
    r = httpx.post(
        "http://localhost:8080/query/trace",
        json={"question": q, "department": "engineering"},
        timeout=15,
    )
    d = r.json()
    print(f"Q: {q[:50]}")
    print(f"  outcome={d.get('planner_outcome')} evidence={d.get('evidence_outcome')} strategy={d.get('selected_strategy')} docs={d.get('final_documents_count')}")
    print()
