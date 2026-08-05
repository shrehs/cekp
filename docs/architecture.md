# Connected Enterprise Knowledge Platform (CEKP)
### Connecting Fragmented Enterprise Knowledge Sources into an Intelligent, Explainable, and Secure Knowledge Layer

*Architecture & Design Document*

**Version:** 1.0
**Status:** Design phase
**Related projects:** LLM Security Gateway · RAG Benchmark Suite

---

## 1. Executive Summary

CEKP is a production-oriented platform that connects an organization's fragmented knowledge sources — code repos, wikis, tickets, contracts, spreadsheets, databases — into a single intelligent, explainable, and secure knowledge layer. The enterprise challenge it solves is fragmentation and unification; natural-language Q&A, retrieval, and the Adaptive Retrieval Planner are capabilities the platform exposes, not the platform's identity.

It is the third piece of a three-project arc:

| Project | Demonstrates |
|---|---|
| LLM Security Gateway | Securing enterprise AI systems |
| RAG Benchmark Suite | Evaluating and justifying retrieval architecture choices |
| **Connected Enterprise Knowledge Platform (CEKP)** | **Unifying fragmented enterprise knowledge into one intelligent, explainable, secure system** |

CEKP is not "a chatbot with RAG." Its distinguishing feature is an **Adaptive Retrieval Planner** that inspects each incoming question and decides, at runtime, which retrieval strategy (vector, hybrid, graph, or agentic multi-hop) is appropriate — using the evaluation methodology already built in the RAG Benchmark Suite as its decision backbone. Security posture from the Gateway project (RBAC, JWT, guardrails) is inherited rather than rebuilt.

This document describes the full target architecture. **v1 is deliberately narrower** (Section 10) — the hiring signal comes from five things done exceptionally well, not from every box in the diagram being implemented:
1. Ingest heterogeneous data.
2. Route queries through the Adaptive Retrieval Planner.
3. Enforce RBAC before retrieval.
4. Return explainable answers with provenance.
5. Measure and visualize the system.

---

## 2. Problem Statement

Enterprises don't have a retrieval problem. They have a **fragmentation** problem:

- Knowledge lives in 6-10 disconnected systems (Confluence, Jira, GitHub, SharePoint, Snowflake, PDFs on a shared drive).
- The right retrieval strategy differs by question type — a single fixed pipeline (e.g., "always do GraphRAG" or "always do vector search") is either wasteful or wrong for a large share of queries.
- Documents go stale, get superseded, and carry different trust levels, but most RAG systems treat every chunk as equally authoritative and equally fresh.
- Answers without provenance are not usable in regulated or high-stakes environments — an answer has to show *why* it was retrieved, not just *what* it says.

CEKP addresses all four: unification, adaptive strategy selection, freshness/trust-aware retrieval, and explainability.

---

## 3. Goals & Non-Goals

**Goals**
- Ingest heterogeneous sources into a unified retrieval layer (vector + graph + relational metadata).
- Route each query to the cheapest retrieval strategy that will answer it correctly, using a rule-based planner in v1, evolving toward data-driven in v2.
- Attach provenance, confidence, and freshness to every answer.
- Reuse the Security Gateway's RBAC/guardrail layer and the Benchmark Suite's evaluation harness rather than reinventing either.
- Be demoable end-to-end on a laptop/single VM with Docker Compose, while the design scales conceptually to Kubernetes/cloud.

**Non-Goals** (explicitly out of scope for v1)
- Full enterprise SSO/Okta/Azure AD integration — RBAC model is real, but auth provider is mocked/simplified.
- Fine-tuning any LLM — the platform is orchestration and retrieval, not model training.
- OCR — v1 sources are digital PDFs only; OCR is future work, added only if a real source demands it.
- Supporting every possible enterprise connector — **v1 is GitHub + digital PDFs only.** Confluence, Jira, SharePoint, and Snowflake are future work, not because they're hard but because they add integration surface without adding architectural signal.
- Multi-tenant SaaS concerns (billing, tenant isolation at the infra level).

---

## 4. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                              SOURCES                                 │
│   GitHub · Confluence/Wiki · Jira · SharePoint · PDFs · SQL/Snowflake│
└───────────────────────────────┬───────────────────────────────────────┘
                                 ▼
                    ┌─────────────────────────┐
                    │   Ingestion Pipeline      │
                    │   (n8n + Python workers)  │
                    └────────────┬──────────────┘
                                 ▼
                    ┌─────────────────────────┐
                    │  Document Processing      │
                    │  OCR · Chunking · Entity   │
                    │  Extraction · Classification│
                    └────────────┬──────────────┘
                                 ▼
        ┌──────────────────────────────────────────────────────────┐
        │                   Unified Knowledge Layer                   │
        │   Neo4j (graph) · Qdrant (vector) · Postgres                │
        │   (metadata/RBAC) · Blob Storage (raw docs)                 │
        └────────────────────────────┬───────────────────────────────┘
                                 ▼
        ┌──────────────────────────────────────────────────────────┐
        │           Knowledge Connection & Retrieval Layer             │
        │   Vector Search · Hybrid Search · Graph Traversal            │
        │   · Metadata/Trust Filtering                                 │
        └────────────────────────────┬───────────────────────────────┘
                                 ▼
        ┌────────────────────────────────────────────────┐
        │              Adaptive Retrieval Planner           │
        │   Intent Classification → Strategy Selection      │
        │   → Tool Calling → Multi-hop Retrieval             │
        └────────────────────────┬─────────────────────────┘
                                 ▼
        ┌────────────────────────────────────────────────┐
        │   LLM Gateway (inherits Security Gateway project) │
        │   RBAC · JWT · Prompt Guardrails · Rate Limiting  │
        └────────────────────────┬─────────────────────────┘
                                 ▼
        ┌────────────────────────────────────────────────┐
        │   Evaluation Layer (inherits Benchmark Suite)     │
        │   Latency · Hallucination Score · Cost · Confidence│
        └────────────────────────┬─────────────────────────┘
                                 ▼
                    ┌─────────────────────────┐
                    │  Observability Dashboard  │
                    └─────────────────────────┘
```

---

## 5. Component Breakdown

### 5.1 Ingestion Pipeline
- **Trigger:** file upload, webhook (GitHub push, Jira ticket update), or scheduled pull (SharePoint, Snowflake).
- **Orchestrator:** n8n handles the *operational* workflow (not the AI reasoning) — moving a document from "just arrived" to "queryable."
- **Flow:** source event → n8n workflow → Python worker (FastAPI microservice) → processing pipeline → storage writes → Slack/webhook notification → dashboard refresh.

### 5.2 Document Processing Pipeline
| Stage | Purpose |
|---|---|
| OCR *(future work — not in v1)* | Scanned PDFs / images → text; skipped while sources are digital PDFs + GitHub |
| Chunking | Semantic or structure-aware splitting (headers, code blocks, tables kept intact) |
| Metadata extraction | Author, department, doc type, timestamps, source system |
| Entity extraction | People, systems, projects, policy IDs → feeds the graph |
| Classification | Sensitivity level, document type (policy/spec/ticket/code) |

### 5.3 Unified Knowledge Layer
- **Neo4j** — entities and relationships (e.g., `Policy -[SUPERSEDES]-> Policy`, `Person -[OWNS]-> Document`, `Service -[DEPENDS_ON]-> Service`).
- **Qdrant** (or pgvector for simpler deploys) — chunk embeddings + metadata payload for filtering.
- **PostgreSQL** — users, roles, permissions, document lifecycle state, audit log.
- **Blob storage** — original files, for citation/download and re-processing.

### 5.4 Knowledge Connection & Retrieval Layer
Four retrieval primitives, each exposed as a callable tool:
- **Vector search** — semantic similarity, best for open-ended/FAQ-style questions.
- **Hybrid search** — vector + BM25/keyword, best when exact terms (error codes, IDs, names) matter.
- **Graph traversal** — best for multi-hop/relational questions ("which services depend on the auth service, and who owns them?").
- **Metadata/trust filtering** — applied on top of any of the above (recency, owner, confidence threshold).

### 5.5 Adaptive Retrieval Planner — *the differentiator*
Instead of a fixed pipeline, each query passes through:

1. **Intent classification** — is this factual lookup, exact-match, relational/multi-hop, or open-ended planning?
2. **Strategy selection** — chooses one or more of {vector, hybrid, graph, agentic} based on classification + confidence.
3. **Tool calling** — planner invokes the chosen retrieval tool(s), can escalate (e.g., vector search returns low-confidence → fall back to graph).
4. **Multi-hop retrieval** — for relational questions, the planner chains graph queries (find owner → find owner's other docs → check freshness).

```
Question ──▶ Intent Classifier
                 │
   ┌─────────────┼────────────────┬───────────────┐
   ▼             ▼                ▼               ▼
Simple FAQ   Exact match     Multi-hop        Complex/
             (ID, code)      relational       ambiguous
   │             │                │               │
   ▼             ▼                ▼               ▼
 Vector        Hybrid           Graph          Agentic
 Search        Search          Traversal      (multi-tool,
                                                iterative)
```

This reuses the RAG Benchmark Suite directly: the planner's strategy choices are validated against the same latency/accuracy/cost metrics already built there, so "why did the planner pick graph over vector for this question" has a quantified answer, not a hand-wave.

**Failure path / graceful degradation.** Real queries don't always resolve on the first try. The planner escalates rather than returning a bad answer:

```
Vector search
    │ confidence low?
    ▼
Hybrid search
    │ still low?
    ▼
Graph traversal
    │ still low?
    ▼
Agentic decomposition (break question into sub-questions)
    │ still low?
    ▼
"I don't have enough evidence to answer this confidently."
```

Showing this path in the demo — a query that visibly escalates through two or three strategies before answering — is more convincing than a happy-path demo where everything resolves in one hop.

**v1 → v2: from rule-based to data-driven.** v1 ships with a rule-based classifier (keyword/heuristic-driven intent detection is enough to prove the concept). The natural evolution, and the reason this project reuses the Benchmark Suite rather than just referencing it once, is a feedback loop:

```
Question → Features → Intent classifier → Historical benchmark scores
   → Choose strategy → Record outcome → Improve future decisions
```

Every query resolved in production becomes a new data point the planner can eventually learn from — turning the Benchmark Suite from a one-time evaluation artifact into an actively-used decision input.

### 5.6 LLM Gateway
Inherited from the Security Gateway project: JWT-based auth, role/department-scoped permissions, clearance-level document filtering, prompt-injection guardrails, rate limiting. CEKP's job here is *integration*, not rebuilding — the design doc should reference the Gateway's existing API contract rather than duplicate it.

### 5.7 AI Query Trace — the observability centerpiece
Grafana/Prometheus are the plumbing; they are not what makes a demo memorable. The actual differentiator is a **per-query trace view**, shown for every answer the system returns:

```
User Question
  → Planner Decision (which strategy, and why)
  → Retrieved Documents (with freshness/trust score)
  → Graph Traversal Path (if applicable)
  → LLM Reasoning Summary
  → Final Answer (with inline citations)
  → Latency · Cost · Confidence
```

This is the artifact a hiring manager remembers after the demo ends — not the Grafana dashboard behind it.

**Architecture Replay.** Because the Benchmark Suite already knows how to run the same question through multiple strategies, expose that as a toggle on the trace view: take the question the planner just answered, replay it through the *other* three strategies, and show the comparison side by side —

```
Question: "What services depend on the Auth Service?"
Planner chose: Graph Retrieval

Replay with → Vector | Hybrid | Graph | Agentic
Compare → Latency · Cost · Evidence · Answer
```

This turns "trust me, the planner made a good choice" into something the user can verify themselves, on demand — and it's essentially free to build since it's just re-invoking retrieval tools that already exist.

### 5.8 Dashboard (secondary, not the centerpiece)
Aggregate view over the trace data: strategy distribution over time, regression alerts, cost trends. Useful for an ops audience; the AI Query Trace is what you demo first.

---

## 6. Data Model

### 6.1 Neo4j Graph Schema (core nodes/relationships)
```
(:Document {id, title, type, source_system, sensitivity, created_at, updated_at})
(:Person {id, name, department, role})
(:Policy {id, version, status})
(:System {id, name})

(:Document)-[:AUTHORED_BY]->(:Person)
(:Document)-[:OWNED_BY]->(:Person)
(:Policy)-[:SUPERSEDES]->(:Policy)
(:Document)-[:MENTIONS]->(:System)
(:System)-[:DEPENDS_ON]->(:System)
(:Person)-[:MEMBER_OF]->(:Department)
```

### 6.2 Vector Store Payload (per chunk)
```json
{
  "chunk_id": "uuid",
  "document_id": "uuid",
  "text": "...",
  "embedding": [ ... ],
  "source_system": "confluence",
  "department": "engineering",
  "sensitivity": "internal",
  "trust_score": 0.82,
  "last_updated": "2026-05-01",
  "expires_at": null
}
```

### 6.3 Postgres Schema (relational/metadata)
```
users(id, email, role_id, department_id, clearance_level)
roles(id, name, permissions_json)
documents(id, source_system, version, status, owner_id, confidence, last_reviewed_at, expiry_at)
audit_log(id, user_id, query, strategy_used, timestamp, result_summary)
```

---

## 7. Cross-Cutting Concerns

### 7.1 Authentication & RBAC
- JWT issued at login carries `role`, `department`, `clearance_level`.
- Retrieval layer applies clearance/department filters *before* documents reach the LLM context — permission enforcement happens at retrieval time, not by trusting the model to withhold information.
- Design references the Security Gateway's existing RBAC contract; v1 implementation can mock the identity provider while keeping the permission model real.

### 7.2 Document Versioning & Freshness
- Every document has a `status` (`current`, `superseded`, `draft`) and a `SUPERSEDES` graph edge to prior versions.
- Retrieval defaults to `current` unless the query explicitly asks for history ("what did the old policy say?").
- Freshness score = function of `last_reviewed_at`, `expires_at`, and owner-confirmed accuracy; surfaced to the user and factored into ranking.

### 7.3 Trust Score
Combines: source reliability (e.g., official policy doc > Slack export), recency, and owner-confidence rating. Used both for ranking and for flagging low-trust answers explicitly in the response.

---

## 8. Technology Stack

| Layer | Technology |
|---|---|
| Backend API | FastAPI |
| Orchestration (AI) | LangChain or LlamaIndex |
| LLM routing | LiteLLM (OpenAI / Groq / Ollama) |
| Graph DB | Neo4j |
| Vector DB | Qdrant (pgvector as lighter alternative) |
| Relational DB | PostgreSQL |
| Cache/queue | Redis |
| Workflow automation | n8n |
| Evaluation | RAGAS, DeepEval, Phoenix (Arize), Langfuse |
| Deployment | Docker, GitHub Actions, Azure Container Apps / AWS ECS |
| Monitoring | Prometheus, Grafana, OpenTelemetry |

---

## 9. CI/CD & Quality Gates

```
PR opened
  → Run RAG Benchmark Suite regression tests
  → Run evaluation (RAGAS/DeepEval) on golden question set
  → Compare against baseline — fail on regression beyond threshold
  → Generate report (posted as PR comment)
  → On merge: build image → deploy to staging → smoke test → promote
```

This demonstrates CI/CD discipline applied to an AI system, not just to application code — regressions in retrieval quality are caught the same way a broken unit test would be.

---

## 10. Roadmap — 3-Month Plan

Full scope (Section 4) is a multi-month build. This is the realistic, shippable version, scoped to v1 (GitHub + digital PDFs, rule-based planner):

**Month 1 — Foundation**
- Ingestion for GitHub + digital PDFs (no OCR)
- Chunking, embedding, Qdrant storage
- Hybrid search (vector + keyword)

**Month 2 — Graph & Planner**
- Neo4j schema + entity extraction
- Rule-based Adaptive Retrieval Planner, including the failure/escalation path (§5.6)
- Explainability trace — first version of the AI Query Trace view (§5.7)

**Month 3 — Security, Evaluation, Polish**
- Integrate RBAC/JWT from the Security Gateway project
- Wire in Benchmark Suite metrics at the per-query level
- GitHub Actions regression pipeline
- Dashboard (secondary — built after the trace view, not instead of it)

A working demo after Month 2 already tells the full story — planner + trace view is the core signal. Month 3 is what separates "cool demo" from "designed like production."

**Deferred to v2+ (not because they're hard, but because they don't add architectural signal to v1):**
- Confluence, Jira, SharePoint, Snowflake connectors
- OCR
- Data-driven planner (§5.6, "v1 → v2")
- Architecture Replay UI (§5.7) — cheap to add once the trace view exists, but not required for the core demo
- Kubernetes/cloud deployment (Docker Compose is enough for v1)

---

## 11. Success Criteria

| Dimension | Metric |
|---|---|
| Correctness | Answer accuracy on a golden question set (reusing Benchmark Suite methodology) |
| Efficiency | Planner reduces average retrieval cost/latency vs. always-graph baseline |
| Explainability | 100% of answers include retrieval strategy + provenance trace |
| Security | Zero unauthorized document exposure in permission test suite |
| Freshness | Superseded documents never surface as `current` in test queries |

---

## 12. How This Ties the Trilogy Together

- **Security Gateway** proved you can secure an enterprise AI system.
- **RAG Benchmark Suite** proved you can evaluate and justify retrieval architecture choices with data.
- **CEKP** proves you can take both of those and design the production system that needs them — using the Gateway as its security layer and the Benchmark Suite as its evaluation and planner-decision backbone, rather than treating them as three disconnected projects.
