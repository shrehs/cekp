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

Sources: GitHub (public repo files) + digital PDFs

Storage: Qdrant (vectors) + PostgreSQL (metadata/RBAC) — Neo4j added in Month 2

Retrieval: Hybrid search (vector + keyword) in Month 1; Adaptive Planner in Month 2

No OCR, no Confluence/Jira/SharePoint/Snowflake — deliberately deferred (see architecture doc §10)

### Current v1 Scope

#### Sources
GitHub repository files
Digital PDFs

#### Storage
Qdrant — vector retrieval
Neo4j — graph/code relationships
PostgreSQL — metadata, audit records, and RBAC context

#### Retrieval
Vector retrieval
Hybrid retrieval
Graph retrieval
Adaptive retrieval planner
Confidence-based escalation
Policy-aware strategy authorization

#### API
FastAPI
/query
/query/trace
/health
/ready
/metrics

#### Observability
Structured JSON logging
Request IDs
OpenTelemetry instrumentation
Prometheus metrics
Grafana dashboards

#### Deployment
Docker Compose
Containerized API
Qdrant
PostgreSQL
Neo4j
Prometheus
Grafana

## Quickstart
```powershell
docker compose -f docker/docker-compose.yml up -d --build
```
The API is available at:
```powershell
http://localhost:8080
```
Swagger documentation:
```powershell
http://localhost:8080/docs
```
Prometheus:
```powershell
http://localhost:9090
```
Grafana:
```powershell
http://localhost:3000
```
CEKP dashboard:
```powershell
http://localhost:3000/d/cekp-overview/cekp-overview
```
The dashboard covers request volume, p50/p95 query latency, non-success rate,
retrieval strategy usage, and query outcomes.

## Local Tests

The project is currently validated with Python 3.13 and the pinned dependencies in
requirements.txt. Create or activate the virtual environment, install the
dependencies, and run:

```bash
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
```

The automated suite currently reports 204 passed, 2 xfailed. pytest.ini limits discovery
to the application tests and excludes live endpoint smoke scripts that require the
Docker stack to be running. Those scripts remain manual checks.

Evaluation results use separate HTTP, planner, evidence, policy, retrieval, and
latency dimensions. The evaluator records p50/p95/p99 latency and distinguishes a
strategy-level success from an evidence-backed final answer.

### Health & Readiness

Health check:
```bash
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

Classifies the query intent.

Produces a ranked set of applicable retrieval strategies.

Infers the current health state of each strategy.

Adjusts routing order when health-aware ranking is enabled.

Applies strategy-level authorization.

Executes live strategies in health-aware routing order.

Evaluates confidence and evidence.

Escalates when the result does not clear the configured threshold.

Records routing decisions, interventions, and outcomes in the trace.

Health changes routing order, not the underlying retrieval score. The original routing_score is preserved and a separate adjusted_score is used for health-aware decisions.

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
```text
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

- Current v1 evaluation:

21 / 24 successful cases
87.5% success rate
~195 ms average reported latency

The remaining cases include intentional out-of-scope/no-evidence behavior and a dependency query where Graph access is denied when no authorized department context is supplied.

The evaluation is therefore treated as a baseline rather than optimized purely for a higher benchmark score.

## Run the evaluator:
```bash
.\.venv\Scripts\python.exe scripts\evaluate_query_system.py
```
## Metrics

CEKP exposes application-level Prometheus metrics including:
```text
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

Requests include:
```text
timestamp
log level
logger
request ID
HTTP method
path
status code
duration
OpenTelemetry
```
FastAPI and SQLAlchemy are instrumented for distributed tracing.

Docker Compose exports spans through OTLP HTTP to Jaeger at
http://jaeger:4318/v1/traces. Jaeger UI is available at:
```powershell
http://localhost:16686
```
The console exporter remains the fallback when CEKP_OTLP_ENDPOINT is unset.
Live validation confirmed a query trace persisted in Jaeger with eight spans.

### Prometheus + Grafana

Prometheus scrapes the API metrics endpoint and Grafana provides the operational dashboard layer.
The evaluator also reports evidence-backed success separately from raw planner
success, so a successful strategy with zero returned documents cannot inflate
retrieval quality.

## Reliability Loop

CEKP extends observability into an explicit reliability loop:

Observation → State Inference → Decision → Intervention → Outcome → Verification

The retrieval planner maintains a sliding window of strategy observations and
in­fers three operational states:

HEALTHY — infrastructure error rate and latency remain within healthy thresholds.

DEGRADED — error rate or p95 latency has crossed the degraded threshold.

UNAVAILABLE — infrastructure error rate has crossed the unavailable threshold.

UNAVAILABLE strategies are removed from live execution and recorded as an
explicit skip before fallback. DEGRADED strategies remain executable but can
be demoted when health-aware ranking is enabled.

## Health-aware routing
```text
routing_score
      │
      ▼
health adjustment
      │
      ▼
adjusted_score
      │
      ▼
decision
```
The trace exposes routing_score, health_state, health_penalty,
adjusted_score, and the routing decision (selected, kept, demoted,
or skipped_unavailable). This keeps operational reliability separate from
retrieval quality while allowing the planner to adapt strategy ordering.

## Recovery

Recovery is request-driven rather than dependent on a manual reset endpoint. A
non-healthy strategy can be probed through the real dependency path. For an
unavailable strategy, a successful probe permits a real retrieval attempt; that
retrieval result verifies whether the strategy has actually recovered.

A live reliability experiment verified the complete loop: injected Neo4j failure
→ Graph became UNAVAILABLE → Graph was skipped → Hybrid produced an
evidence-backed fallback → Neo4j was restored → Graph recovered to HEALTHY
→ Graph became eligible again.

The system is intentionally explicit and auditable rather than claiming
autonomous recovery beyond what has been implemented.

## Project Layout
```text
app/
  api/              FastAPI routers
  core/             configuration, clients, logging, telemetry, metrics
  ingestion/        source connectors and processing pipeline
  models/           Pydantic and database models
  planner/          adaptive retrieval planner, health, ranking, and policies
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
  reliability-loop.md
  integration-validation.md

scripts/
  evaluation and validation utilities

tests/
  unit and planner tests
Validation
```
Start the complete local stack:
```bash
docker compose -f docker/docker-compose.yml up -d --build
```
Run the validation script:
```bash
./scripts/validate.sh
```
Run the Python test suite:
```powershell
pytest tests/
```
## Current Engineering Status

### Completed

- FastAPI API
- GitHub and PDF ingestion
- Chunking and embeddings
- Vector, hybrid, and Neo4j graph retrieval
- Adaptive retrieval planner and confidence-based escalation
- Strategy-level policy authorization and audit logging
- `/query/trace`
- Health and readiness checks
- Structured JSON logging and request IDs
- OpenTelemetry, Prometheus, and Grafana integration
- Docker Compose deployment
- Evaluation harness and graph navigation tests
- Retrieval latency instrumentation
- Strategy health monitoring
- Health-aware strategy ranking
- Failure-aware fallback and request-driven recovery probing
- Reliability-loop integration tests and live dependency-failure recovery experiment

### v2.3 validation

```text
204 passed
2 xfailed
```
The two expected failures document an unresolved outcome-precedence edge case
when an unavailable strategy is skipped and the remaining executable strategy
is denied by policy. This is intentionally left explicit for the next semantics
change rather than hidden by weakening the tests.

## Next

Further health-aware ranking calibration
Load testing and capacity characterization
AWS deployment
CI/CD pipeline
Persistent production tracing backend
Data-driven intent classification
User feedback signals
Further policy/RBAC integration

The reliability loop is deliberately deterministic and auditable. More advanced
autonomous recovery, dynamic ranking policies, and broader control mechanisms
remain future work.

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
health-aware routing
explicit recovery and verification

Kubernetes/EKS and other distributed infrastructure are deliberately deferred until the workload and operational requirements justify them.