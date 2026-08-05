# Integration Validation — Milestone Checklist

**Purpose:** validate the Month 1 + Planner (Month 2 core) work against a live stack. Nothing new gets built in this milestone — only validated. If something here fails, fix it before Neo4j, don't add Neo4j around a broken foundation.

Run `scripts/validate.sh` (same repo) to execute most of this automatically. Items that need manual eyeballing are marked **[manual]**.

---

## Planner

- [ ] **Correct strategy ordering** — a graph-pattern query (`"which services depend on the auth service?"`) returns `ranked_strategies` starting with `graph`, in the `/query/trace` response.
  - **Note:** this specific query tests the *org-dependency* pattern family. It should correctly rank `graph` first and then show `not_implemented` **even after Neo4j exists** — the org-dependency graph is a separate, still-deferred schema (see `docs/graph-schema.md`). Don't "fix" this into a success case; if it ever stops returning `not_implemented`, something regressed.
  - Once the code-structure `GraphStrategy` is implemented, also check a *code-structure* query — e.g. `"what does app/api/query.py import?"` — which should show `graph → success` (see `docs/graph-schema.md` for the schema this answers against).
- [ ] **Escalation behaves correctly** — a code-structure query ("which functions are defined in `app/main.py`?") shows `attempts[0].outcome == "success"` on the `graph` attempt directly (no escalation needed) — `GraphStrategy` is real now, not a stub. An org-dependency query ("which services depend on the auth service?") still shows `graph → not_implemented → hybrid`, since that's a genuinely different, still-unbuilt capability (see `docs/graph-schema.md`).
- [ ] **Policy decisions logged** — a query with `department` set to something outside `GRAPH_ALLOWED_DEPARTMENTS` (see `policy_evaluator.py`) on a graph-pattern question shows `attempts[0].outcome == "denied_by_policy"`, not `not_implemented`.
- [ ] **PlannerOutcome correct** — `planner_outcome` in `/query/trace` matches the actual result: `success` when an answer came back, `no_evidence` when nothing did, `access_denied` only when every attempt was `denied_by_policy`.
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

- [ ] **`/query` works** — returns `200` with `answer_available` set correctly for both a question with real evidence and one with none.
- [ ] **`/query/trace` returns 404 when disabled** — with `CEKP_ENABLE_TRACE_ENDPOINT=false` (or `CEKP_ENVIRONMENT=production`), the route returns `404`.
- [ ] **`/query/trace` returns trace when enabled** — default local config, route returns `200` with the full trace shape (`ranked_strategies`, `attempts`, `planner_outcome`, `final_strategy_used`, `final_confidence`, `final_reasoning`).

## Persistence

- [ ] **Audit records saved** — after any `/query` call, a new row exists in `audit_log`.
- [ ] **`strategy_attempts` JSON persisted correctly** — the JSON column round-trips as a real list of `{strategy, outcome, confidence}` objects, not a stringified blob.
- [ ] **`planner_outcome` persisted correctly** — matches the value returned in the API response for the same request.

## Observability

- [ ] **[manual]** Logs readable — `docker compose logs api` shows something a stranger could follow (request in, strategy tried, outcome, response out) without needing to read the source.
- [ ] **[manual]** Trace understandable — hand `/query/trace`'s raw JSON output to someone unfamiliar with the codebase; can they explain what happened without you narrating it?
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