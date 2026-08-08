# CEKP — Connected Enterprise Knowledge Platform

Connecting fragmented enterprise knowledge sources into an intelligent, explainable, and secure knowledge layer.

This repo is the v1 implementation described in `docs/architecture.md`. v1 scope:

- **Sources:** GitHub (public repo files) + digital PDFs
- **Storage:** Qdrant (vectors) + PostgreSQL (metadata/RBAC) — Neo4j added in Month 2
- **Retrieval:** Hybrid search (vector + keyword) in Month 1; Adaptive Planner in Month 2
- **No OCR, no Confluence/Jira/SharePoint/Snowflake** — deliberately deferred (see architecture doc §10)

## Quickstart

```bash
docker compose -f docker/docker-compose.yml up -d --build
```

This starts:
- `api` — FastAPI app on `http://localhost:8080` (docs at `/docs`)
- `qdrant` — vector store on `http://localhost:6333`
- `postgres` — metadata store on `localhost:5432`

## Integration Validation

Before touching Neo4j, validate everything built so far against a live stack — see `docs/integration-validation.md` for the full checklist and `scripts/validate.sh` for an automated runner:

```bash
docker compose -f docker/docker-compose.yml up -d --build
./scripts/validate.sh
```

The script covers ingestion, planner escalation behavior, the trace endpoint (both enabled and how to test disabled), `/query`, and audit persistence. A few items are marked `[manual]` in the checklist — PDF ingestion (needs a real sample file), log readability, and the chaos test (stopping Qdrant mid-request) — and need a human to actually look, not just a script exit code.

## Project layout

```
app/
  api/          FastAPI routers (ingestion, query endpoints)
  core/         config, DB clients, shared settings
  ingestion/    source connectors + processing pipeline (PDF, GitHub)
  models/       Pydantic + DB models
  planner/      Adaptive Retrieval Planner (see docs/planner.md, docs/confidence.md)
  services/     business logic (chunking, embedding, retrieval)
docker/         Dockerfile + docker-compose.yml
docs/           architecture.md, planner.md, confidence.md
tests/          unit tests
```

## Status

Month 1 (Foundation) — done:
- [x] Repo scaffold
- [x] Config + DB clients (Qdrant, Postgres)
- [x] PDF ingestion connector — **error boundaries hardened**: corrupted/zero-byte PDFs now return a clean `422` (`CorruptedPdfError`) instead of an unguarded `pypdf` exception crashing to `500`
- [x] GitHub ingestion connector — **error boundaries hardened**: nonexistent/private-without-credentials repos now return a clean `404` (`RepoNotFoundError`) instead of an unguarded `httpx.HTTPStatusError` crashing to `500`
- [x] Chunking + embedding service
- [x] Hybrid search service

Month 2 (Adaptive Retrieval Planner) — core logic done, integrated:
- [x] `PlannerContext`, `StrategyName`/`StrategyOutcome`/`PlannerOutcome` enums, `RetrievalResult`
- [x] `RetrievalStrategy` interface + `VectorStrategy`, `HybridStrategy`, `AgenticStrategy` (placeholder), `GraphStrategy` (stub, `NOT_IMPLEMENTED`)
- [x] `StrategyRegistry`, `IntentClassifier` (rule-based, ranked list), `PolicyEvaluator` (department-gated placeholder)
- [x] `Planner` — escalation loop, policy checks, no-leakage response for denied vs. no-evidence
- [x] `/query` now routes through the planner instead of calling `hybrid_search` directly
- [x] `strategy_attempts` includes per-attempt `confidence` (`None` when a strategy never actually ran vs. a real `0.0` when it did)
- [x] `/query/trace` — full unredacted internal trace (ranked strategies, every attempt, planner outcome) for debugging/demos. **Gated in code** via `settings.trace_endpoint_enabled` (enabled by default only in `local`/`development`, returns 404 — not 403 — when disabled, so its existence isn't confirmed elsewhere).
- [x] `build_audit_record()` — audit-log field extraction now lives in one place (`app/planner/planner.py`), consumed by `query.py` instead of being duplicated inline.
- [x] Unit tests: classifier, registry, policy evaluator, planner, chaos scenarios (28 tests, run without live infra — see note below)
- [ ] Neo4j graph layer (real `GraphStrategy` implementation)
- [ ] AI Query Trace view
- [ ] Data-driven classifier (v2)

Run tests: `pytest tests/` (requires the full stack, since `VectorStrategy`/`HybridStrategy` import live Qdrant/embedding clients even though the planner/classifier/policy tests use fakes and don't need them at runtime).

## Note
.gitignore "`ndocs/evaluation_metrics_*.json`ndocs/evaluation_report_.md"
git rm --cached docs/evaluation_metrics_*.json docs/evaluation_report_.md

## Known Limitations

- **Graph query phrasing:** Graph queries such as "classes/functions defined in X" currently require the word "defined"; queries such as "list classes in X" may fall back to hybrid search.