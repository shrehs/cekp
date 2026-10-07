import httpx, json, subprocess, time

subprocess.run(["docker", "pause", "docker-neo4j-1"])
time.sleep(1)

r = httpx.post(
    "http://localhost:8080/query/trace",
    json={"question": "What does app.main import?", "department": "engineering"},
    timeout=15,
)
print(json.dumps(r.json(), indent=2))

subprocess.run(["docker", "unpause", "docker-neo4j-1"])
