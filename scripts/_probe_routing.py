import httpx, json

queries = [
    "Which functions are defined in app.planner.planner?",
    "What does app.planner.planner import?",
    "How does the planner escalate strategies?",
    "Explain the escalation logic in the planner.",
]

for q in queries:
    r = httpx.post(
        "http://localhost:8080/query/trace",
        json={"question": q, "department": "engineering"},
        timeout=15,
    )
    d = r.json()
    ranked = d.get("ranked_strategies", [])
    attempts = d.get("attempts", [])
    print(f"Q: {q[:55]}")
    print(f"  ranked={ranked}")
    print(f"  attempts={[(a['strategy'], a['outcome']) for a in attempts]}")
    print(f"  outcome={d.get('planner_outcome')} evidence={d.get('evidence_outcome')} docs={d.get('final_documents_count')}")
    print()
