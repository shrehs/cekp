# CEKP — Connected Enterprise Knowledge Platform

Connecting fragmented enterprise knowledge sources into an intelligent, explainable, and secure knowledge layer.

CEKP is an enterprise code/document intelligence platform that combines vector, hybrid, and graph retrieval behind an adaptive retrieval planner with policy-aware strategy selection, confidence-based escalation, audit logging, and production observability.

## Architecture

```text
Enterprise Sources
       │
       ▼
    Ingestion
       │
       ├───────────────┐
       ▼               ▼
   Qdrant          Neo4j Graph
   Vectors          Relationships
       │               │
       └───────┬───────┘
               ▼
       Adaptive Planner
               │
       ├── Vector
       ├── Hybrid
       └── Graph
               │
               ▼
        Evidence / Context
               │
               ▼
        Answer Generation
               │
               ▼
       FastAPI Query API
               │
       ┌───────┼────────┐
       ▼       ▼        ▼
    Metrics  Traces   Audit Logs
       │       │        │
       ▼       ▼        ▼
 Prometheus  OTel   PostgreSQL
       │
       ▼
    Grafana
```

- **Sources:** GitHub (public repo files) + digital PDFs
- **Storage:** Qdrant (vectors) + PostgreSQL (metadata/RBAC) — Neo4j added in Month 2
- **Retrieval:** Hybrid search (vector + keyword) in Month 1; Adaptive Planner in Month 2
- **No OCR, no Confluence/Jira/SharePoint/Snowflake** — deliberately deferred (see architecture doc §10)

## Current v1 Scope
- Sources
  GitHub repository files
  Digital PDFs
- Storage
  Qdrant — vector retrieval
  Neo4j — graph/code relationships
  PostgreSQL — metadata, audit records, and RBAC context
- Retrieval
  Vector retrieval
  Hybrid retrieval
  Graph retrieval
  Adaptive retrieval planner
  Confidence-based escalation
  Policy-aware strategy authorization
- API
  FastAPI
  /query
  /query/trace
  /health
  /ready
  /metrics
- Observability
  Structured JSON logging
  Request IDs
  OpenTelemetry instrumentation
  Prometheus metrics
  Grafana dashboards
- Deployment
  Docker Compose
  Containerized API
  Qdrant
  PostgreSQL
  Neo4j
  Prometheus
  Grafana

## Quickstart
```bash
docker compose -f docker/docker-compose.yml up -d --build
```
The API is available at:
```bash
http://localhost:8080
```
Swagger documentation:
```bash
http://localhost:8080/docs
```
Prometheus:
```bash
http://localhost:9090
```
Grafana:
```bash
http://localhost:3000
```

## Local Tests

The project is currently validated with Python 3.13 and the pinned dependencies in
`requirements.txt`. Create or activate the virtual environment, install the
dependencies, and run:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
```

The automated suite currently reports **145 passed**. `pytest.ini` limits discovery
to the application tests and excludes live endpoint smoke scripts that require the
Docker stack to be running. Those scripts remain manual checks.

## Health & Readiness
Health check:
``` bash
GET /health
```
Dependency readiness:
```bash
GET /ready
```
/ready verifies connectivity to the core infrastructure including PostgreSQL, Qdrant, and Neo4j.

## Query System

The /query endpoint routes questions through the adaptive retrieval planner.

The planner:

1. Classifies the query intent.
2. Ranks applicable retrieval strategies.
3. Applies strategy-level authorization.
4. Executes retrieval.
5. Evaluates confidence.
6. Escalates when the result does not clear the configured threshold.
7. Returns evidence only when the planner has sufficient confidence.

Example flow:
```text
Question
   │
   ▼
Intent Classification
   │
   ▼
Strategy Ranking
   │
   ▼
Policy Check
   │
   ├── denied ──────────► next strategy
   │
   ▼
Retrieval
   │
   ▼
Confidence Evaluation
   │
   ├── below threshold ─► escalate
   │
   ▼
Final Evidence / Answer
```

## Policy Model

Graph retrieval is currently department-gated.

The v1 policy evaluator allows Graph strategy access for:
``` bash
engineering
admin
```
Unknown departments are denied by default rather than being implicitly authorized.

This is intentionally a strategy-level authorization layer. Document-level sensitivity filtering remains inside the underlying retrieval/storage layer.

## Evaluation

The automated test suite and the live evaluation benchmark measure different
surfaces. The test suite covers parser, ingestion, graph, planner, policy, and
retrieval contracts without requiring external services. The benchmark below is
the latest recorded query-system evaluation and requires the running stack.

The current evaluation set contains 24 representative queries covering:

- code navigation
- API contracts
- code logic
- dependencies
- configuration
- error handling
- performance
- integration
- testing
- out-of-scope questions

## Current v1 evaluation:
```text
21 / 24 successful cases
87.5% success rate
~195 ms average reported latency
```

The remaining cases include intentional out-of-scope/no-evidence behavior and a dependency query where Graph access is denied when no authorized department context is supplied.

The evaluation is therefore treated as a baseline rather than optimized purely for a higher benchmark score.

Run the evaluator:
```bash
.\.venv\Scripts\python.exe scripts\evaluate_query_system.py
```
## Metrics

CEKP exposes application-level Prometheus metrics including:
```bash
cekp_queries_total
cekp_query_outcomes_total
cekp_query_duration_seconds
cekp_retrieval_strategy_total
cekp_retrieval_attempts_total
cekp_retrieval_duration_seconds
cekp_retrieved_documents
cekp_planner_confidence
cekp_active_queries
```
These complement the standard FastAPI/HTTP metrics exposed by the application.

## Observability
Structured Logging

# Requests include:

timestamp
log level
logger
request ID
HTTP method
path
status code
duration
OpenTelemetry

FastAPI and SQLAlchemy are instrumented for distributed tracing.

The local environment currently exports spans through the OpenTelemetry console exporter.

Prometheus + Grafana

Prometheus scrapes the API metrics endpoint and Grafana provides the operational dashboard layer.

## Project Layout
``` bash
app/
  api/              FastAPI routers
  core/             configuration, clients, logging, telemetry, metrics
  ingestion/        source connectors and processing pipeline
  models/           Pydantic and database models
  planner/          adaptive retrieval planner and policies
  services/         chunking, embedding, retrieval, graph services

docker/
  Dockerfile
  docker-compose.yml
  prometheus/
  grafana/

docs/
  architecture.md
  planner.md
  confidence.md
  integration-validation.md

scripts/
  evaluation and validation utilities

tests/
  unit and planner tests
Validation

Start the complete local stack:

docker compose -f docker/docker-compose.yml up -d --build
```

Run the validation script:
```bash
./scripts/validate.sh
```
Run the Python test suite:
```bash
pytest tests/
Current Engineering Status
Completed
 FastAPI API
 GitHub ingestion
 PDF ingestion
 Chunking and embeddings
 Vector retrieval
 Hybrid retrieval
 Neo4j graph retrieval
 Adaptive retrieval planner
 Strategy ranking
 Confidence-based escalation
 Strategy-level policy authorization
 Audit logging
 /query/trace
 Health and readiness checks
 Structured JSON logging
 Request IDs
 OpenTelemetry instrumentation
 Prometheus metrics
 Grafana infrastructure
 Docker Compose deployment
 Evaluation harness
 Graph navigation tests
 Retrieval latency instrumentation
 ```
## Next
```bash
 Load testing and capacity characterization
 AWS deployment
 CI/CD pipeline
 Persistent production tracing backend
 Data-driven intent classification
 User feedback signals
 Further policy/RBAC integration
 ```

## Known Limitations
Graph strategy authorization currently requires an authorized department context.
The v1 policy evaluator uses a placeholder department-based authorization model.
The intent classifier is rule-based.
Some graph queries depend on supported query phrasing.
The local OpenTelemetry setup currently uses console span export rather than a persistent tracing backend.
Production deployment and load characteristics have not yet been fully characterized.

## Design Principles

CEKP intentionally favors incremental productionization over unnecessary infrastructure complexity.

The current system prioritizes:

explicit retrieval strategies
explainable planner decisions
policy-aware escalation
observable APIs
reproducible local deployment
measurable performance
graceful failure and no-leakage behavior

Kubernetes/EKS and other distributed infrastructure are deliberately deferred until the workload and operational requirements justify them.