# Integration Validation — Milestone Checklist

**Purpose:** validate the Month 1 + Planner (Month 2 core) work against a live stack. Nothing new gets built in this milestone — only validated. If something here fails, fix it before Neo4j, don't add Neo4j around a broken foundation.

Run `scripts/validate.sh` (same repo) to execute most of this automatically. Items that need manual eyeballing are marked **[manual]**.

## Automated baseline

As of 2026-10-01, the repository test suite passes with **150 tests passed** using
Python 3.13 and the project virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Pytest is configured in `pytest.ini` to collect only the application suite. The
manual files `tests/test_ingestion_endpoint.py`,
`tests/test_github_authentication.py`, `tests/test_query_single.py`, and
`tests/test_final.py` make live HTTP calls or serve as endpoint demonstrations and
are intentionally excluded from automated collection.

---

Live monitoring validation on 2026-10-01 completed successfully: API readiness
returned PostgreSQL/Qdrant/Neo4j `ok`, Prometheus reported the `api:8000/metrics`
target as `up`, Grafana loaded the Prometheus datasource and the `CEKP Overview`
dashboard, and a traced query produced Prometheus samples plus OpenTelemetry
trace IDs in API logs. The fresh no-cache API image build completed with the
CPU-only Torch wheel, and the rebuilt API exported query spans to Jaeger.

---

## Planner

- [x] **Correct strategy ordering** — unit coverage verifies graph-pattern ranking and code-structure classification. Live `/query/trace` confirmation remains a Docker-stack check.
  - **Note:** this specific query tests the *org-dependency* pattern family. It should correctly rank `graph` first and then show `not_implemented` **even after Neo4j exists** — the org-dependency graph is a separate, still-deferred schema (see `docs/graph-schema.md`). Don't "fix" this into a success case; if it ever stops returning `not_implemented`, something regressed.
  - Once the code-structure `GraphStrategy` is implemented, also check a *code-structure* query — e.g. `"what does app/api/query.py import?"` — which should show `graph → success` (see `docs/graph-schema.md` for the schema this answers against).
- [x] **Escalation behaves correctly** — automated planner and graph strategy tests cover direct graph success, low confidence, policy denial, and the still-deferred org-dependency path.
- [x] **Policy decisions logged** — automated coverage verifies department authorization and the live trace returned the expected graph classification before fallback.
- [x] **PlannerOutcome correct** — automated coverage verifies planner outcomes; the live trace returned `no_evidence` after graph `not_implemented` and vector success below threshold.
- [ ] **Code-structure graph questions actually work** — after ingesting a repo with `/ingest/github`, run all four of the originally-targeted example questions against `/query/trace` and confirm each resolves via `graph` with `outcome: "success"`, not an escalation to `hybrid`:
  - "Which modules import `<something known to be imported>`?" → `get_importers_of`
  - "Where is `<a real class name>` defined?" → `find_function`/`find_class`
  - "Which functions call `<a real function name>`?" → `get_callers_of`
  - "What classes are defined in `<a real module>`?" → `get_classes_defined_in`

  If any of these instead show `graph → low_confidence → hybrid`, check `GraphStrategy._classify()`'s sub-patterns in `app/planner/strategies.py` against the actual phrasing used — the regex is deliberately simple (not real NLU) and may need a pattern tweak for phrasings it wasn't written to expect.

## Retrieval

- [ ] **GitHub repository ingests** — `POST /ingest/github` against a small public repo returns `documents_ingested > 0`.
- [ ] **PDF ingests** — `POST /ingest/pdf` with a real digital (non-scanned) PDF returns `status: ingested`; a scanned PDF with no text layer returns HTTP 422 with the `UnextractablePdfError` message, not a silent empty ingest.
- [ ] **[manual]** Hybrid retrieval returns expected documents — pick 2-3 questions you know the answer to from ingested content, confirm the returned `documents[].text` actually contains the relevant passage, not just topically-adjacent noise.

### Negative ingestion tests

These were added after finding two real bugs: `extract_pdf_text` and `list_repo_files` both had unguarded calls that let a malformed input crash to a raw 500 instead of failing cleanly. Both are now fixed (`app/ingestion/pdf_connector.py`, `app/ingestion/github_connector.py`) and covered by `tests/test_pdf_connector.py` / `tests/test_github_connector.py` — but the checklist below is the live-stack confirmation that the fix actually holds through the full API layer, not just at the unit level.

**PDF:**
- [ ] Corrupted PDF (not a valid PDF file at all) → `422`, not `500`. Fixture: `tests/fixtures/corrupted.pdf`.
- [ ] Zero-byte PDF → `422`, not `500`. Fixture: `tests/fixtures/zero_byte.pdf`.
- [ ] Scanned PDF (valid file, no text layer) → `422` with the "likely scanned" message. Fixture: `tests/fixtures/blank_no_text.pdf` (a real zero-text PDF, not an actual scan, but exercises the identical code path).

**GitHub:**
- [ ] Nonexistent repository → `404`, not `500`.
- [ ] Private repository without credentials → `404` (GitHub's API can't distinguish this from nonexistent — see `github_connector.py` docstring — so this is the same case as above, not a separate code path to test differently).
- [ ] Empty repository (valid, zero ingestible files) → `404` with the "no ingestible files found" message, distinct from the repo-not-found message above.

## API

- [x] **`/query` works** — the live `/query/trace` path returned `200` with a complete trace and `no_evidence` result. An evidence-positive query still depends on ingested source data.
- [ ] **`/query/trace` returns 404 when disabled** — with `CEKP_ENABLE_TRACE_ENDPOINT=false` (or `CEKP_ENVIRONMENT=production`), the route returns `404`.
- [x] **`/query/trace` returns trace when enabled** — the rebuilt API returned `200` with ranked strategies, attempts, planner outcome, confidence, latency, and metadata.

## Persistence

- [ ] **Audit records saved** — after any `/query` call, a new row exists in `audit_log`.
- [ ] **`strategy_attempts` JSON persisted correctly** — the JSON column round-trips as a real list of `{strategy, outcome, confidence}` objects, not a stringified blob.
- [ ] **`planner_outcome` persisted correctly** — matches the value returned in the API response for the same request.

## Observability

- [x] **[manual]** Logs readable — live API logs include request IDs, status, duration, and OpenTelemetry trace/span IDs.
- [x] **[manual]** Trace understandable — the live `/query/trace` response exposed ranked strategies, attempts, confidence, and planner outcome.
- [x] **Prometheus scrape** — Prometheus target `cekp-api` reported `up` for `http://api:8000/metrics`.
- [x] **Grafana datasource and dashboard** — Grafana queried Prometheus successfully and loaded all five CEKP Overview panels.
- [x] **Persistent traces** — OTLP HTTP exports to Jaeger; the live query trace was found through Jaeger's query API with eight spans.
- [ ] **Exceptions don't crash requests** — temporarily break something on purpose (see `scripts/validate.sh`'s chaos section: point `CEKP_QDRANT_HOST` at a nonexistent host and restart just the `api` container), confirm `/query` still returns a clean `200` with `no_evidence` rather than a `500`.

---

## Performance sanity (not benchmarking — just reasonableness)

No precise numbers needed yet; these are "does it behave reasonably" checks, not SLA targets.

| Check | Target |
|---|---|
| `/query` latency | < 2 seconds |
| `/query/trace` latency | Similar to `/query` (it does the same planning work, just returns more of it) |
| PDF ingestion | Completes without crash, reasonable time for a normal-sized document |
| GitHub ingestion | Completes without crash for a small-to-medium repo |

If `/query/trace` is *meaningfully* slower than `/query`, that's worth investigating — they call the identical `Planner.plan()`, so a large gap likely means something in `build_trace_response()` or the audit write path is doing unexpected extra work, not an inherent cost of tracing.

## Exit criteria

All boxes checked → move to Neo4j. If any box fails, that's the next task — not a new feature, a fix to what's already claimed as "done" in the README.