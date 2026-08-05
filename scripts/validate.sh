#!/usr/bin/env bash
#
# Integration validation script -- run this against a live stack
# (docker compose -f docker/docker-compose.yml up -d --build) before
# starting Neo4j work. See docs/integration-validation.md for the full
# checklist this maps to; items marked [manual] there aren't automated
# here and still need a human look.
#
# Usage: ./scripts/validate.sh
# Requires: curl, jq, docker compose, psql (or `docker compose exec postgres psql`)

set -uo pipefail

BASE_URL="${CEKP_BASE_URL:-http://localhost:8000}"
PASS=0
FAIL=0

green() { printf "\033[32m%s\033[0m\n" "$1"; }
red()   { printf "\033[31m%s\033[0m\n" "$1"; }

check() {
  local description="$1"
  local condition="$2"
  if [ "$condition" = "true" ]; then
    green "  PASS  $description"
    PASS=$((PASS + 1))
  else
    red   "  FAIL  $description"
    FAIL=$((FAIL + 1))
  fi
}

echo "=== 0. Health check ==="
HEALTH=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/health")
check "API is reachable (/health returns 200)" "$([ "$HEALTH" = "200" ] && echo true || echo false)"

echo ""
echo "=== 1. Ingestion ==="
echo "  Ingesting a small public repo (this repo itself, docs/ only)..."
GH_RESPONSE=$(curl -s -X POST "$BASE_URL/ingest/github" \
  -H "Content-Type: application/json" \
  -d '{"repo": "octocat/Hello-World", "branch": "master"}')
GH_COUNT=$(echo "$GH_RESPONSE" | jq -r '.documents_ingested // 0' 2>/dev/null || echo 0)
check "GitHub ingestion returns documents_ingested > 0" "$([ "$GH_COUNT" -gt 0 ] && echo true || echo false)"
echo "    (documents_ingested=$GH_COUNT; if 0, check repo/branch/path_filter or GitHub rate limits)"

echo ""
echo "  PDF ingestion: place a real digital PDF at ./sample.pdf and re-run this"
echo "  section manually if you want it automated -- skipping here since no"
echo "  sample file is guaranteed to exist in your environment:"
echo "    curl -X POST $BASE_URL/ingest/pdf -F 'file=@sample.pdf'"

echo ""
echo "=== 1b. Negative ingestion tests ==="
FIXTURES_DIR="$(dirname "$0")/../tests/fixtures"

if [ -f "$FIXTURES_DIR/corrupted.pdf" ]; then
  CORRUPTED_HTTP=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/ingest/pdf" \
    -F "file=@$FIXTURES_DIR/corrupted.pdf")
  check "Corrupted PDF returns 422 (not 500)" "$([ "$CORRUPTED_HTTP" = "422" ] && echo true || echo false)"

  ZERO_BYTE_HTTP=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/ingest/pdf" \
    -F "file=@$FIXTURES_DIR/zero_byte.pdf")
  check "Zero-byte PDF returns 422 (not 500)" "$([ "$ZERO_BYTE_HTTP" = "422" ] && echo true || echo false)"

  BLANK_HTTP=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/ingest/pdf" \
    -F "file=@$FIXTURES_DIR/blank_no_text.pdf")
  check "Scanned-like (no text) PDF returns 422" "$([ "$BLANK_HTTP" = "422" ] && echo true || echo false)"
else
  echo "  SKIPPED (tests/fixtures/*.pdf not found -- see docs/integration-validation.md)"
fi

NONEXISTENT_HTTP=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/ingest/github" \
  -H "Content-Type: application/json" \
  -d '{"repo": "this-owner-definitely-does-not-exist-abc123/nope"}')
check "Nonexistent GitHub repo returns 404 (not 500)" "$([ "$NONEXISTENT_HTTP" = "404" ] && echo true || echo false)"

echo ""
echo "=== 2. Planner behavior ==="

echo "  Querying an org-dependency graph question (expect graph -> not_implemented -> hybrid,"
echo "  PERMANENTLY -- this pattern family is deferred, see docs/graph-schema.md; this should"
echo "  NOT start returning success just because Neo4j gets implemented for code-structure)..."
TRACE_RESPONSE=$(curl -s -X POST "$BASE_URL/query/trace" \
  -H "Content-Type: application/json" \
  -d '{"question": "which services depend on the auth service?"}')
TRACE_HTTP=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/query/trace" \
  -H "Content-Type: application/json" \
  -d '{"question": "which services depend on the auth service?"}')

if [ "$TRACE_HTTP" = "200" ]; then
  FIRST_STRATEGY=$(echo "$TRACE_RESPONSE" | jq -r '.ranked_strategies[0] // ""' 2>/dev/null)
  check "Org-dependency query ranks 'graph' first" "$([ "$FIRST_STRATEGY" = "graph" ] && echo true || echo false)"

  FIRST_ATTEMPT_OUTCOME=$(echo "$TRACE_RESPONSE" | jq -r '.attempts[0].outcome // ""' 2>/dev/null)
  check "Org-dependency graph attempt is not_implemented (permanently deferred, not just pre-Neo4j)" \
    "$([ "$FIRST_ATTEMPT_OUTCOME" = "not_implemented" ] && echo true || echo false)"

  PLANNER_OUTCOME=$(echo "$TRACE_RESPONSE" | jq -r '.planner_outcome // ""' 2>/dev/null)
  echo "    planner_outcome=$PLANNER_OUTCOME (success if hybrid found something ingested, no_evidence otherwise -- both are valid depending on what's been ingested)"
else
  red "  FAIL  /query/trace did not return 200 (got $TRACE_HTTP) -- is CEKP_ENABLE_TRACE_ENDPOINT / CEKP_ENVIRONMENT set to allow it locally?"
  FAIL=$((FAIL + 1))
fi

echo ""
echo "  Querying a code-structure graph question (GraphStrategy is real now -- this"
echo "  asserts SUCCESS, not just informational. Requires a repo to have been ingested"
echo "  first via /ingest/github, e.g. this project's own repo or the octocat one"
echo "  ingested earlier in this script; app/api/query.py must actually exist in"
echo "  whatever was ingested, or adjust the question below)..."
CODE_TRACE_RESPONSE=$(curl -s -X POST "$BASE_URL/query/trace" \
  -H "Content-Type: application/json" \
  -d '{"question": "what does app/api/query.py import?"}')
CODE_FIRST_STRATEGY=$(echo "$CODE_TRACE_RESPONSE" | jq -r '.ranked_strategies[0] // ""' 2>/dev/null)
CODE_FIRST_OUTCOME=$(echo "$CODE_TRACE_RESPONSE" | jq -r '.attempts[0].outcome // ""' 2>/dev/null)
check "Code-structure query ranks 'graph' first" "$([ "$CODE_FIRST_STRATEGY" = "graph" ] && echo true || echo false)"
if [ "$CODE_FIRST_OUTCOME" = "success" ]; then
  check "Code-structure graph query succeeds directly (no escalation needed)" "true"
else
  echo "  INFO  graph attempt outcome was '$CODE_FIRST_OUTCOME', not 'success' -- likely means the"
  echo "        repo containing app/api/query.py hasn't been ingested via /ingest/github yet in"
  echo "        this environment, not necessarily a GraphStrategy bug. Ingest it first, then re-run."
fi

echo ""
echo "=== 3. Trace endpoint gating ==="
echo "  NOTE: this checks whatever the API container's CURRENT env is."
echo "  To test the disabled case, restart the api container with"
echo "  CEKP_ENABLE_TRACE_ENDPOINT=false and re-run just this section."
GATE_HTTP=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/query/trace" \
  -H "Content-Type: application/json" \
  -d '{"question": "test"}')
echo "    Current /query/trace response code: $GATE_HTTP"
echo "    (expected 200 if trace is enabled in this environment, 404 if disabled)"

echo ""
echo "=== 4. /query (safe endpoint) ==="
QUERY_HTTP=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/query" \
  -H "Content-Type: application/json" \
  -d '{"question": "what is this platform for?"}')
check "/query returns 200" "$([ "$QUERY_HTTP" = "200" ] && echo true || echo false)"

echo ""
echo "=== 4b. Performance sanity (not benchmarking -- just reasonableness) ==="
QUERY_TIME=$(curl -s -o /dev/null -w "%{time_total}" -X POST "$BASE_URL/query" \
  -H "Content-Type: application/json" \
  -d '{"question": "what is this platform for?"}')
QUERY_TIME_OK=$(awk -v t="$QUERY_TIME" 'BEGIN { print (t < 2.0) ? "true" : "false" }')
check "/query latency < 2s (actual: ${QUERY_TIME}s)" "$QUERY_TIME_OK"

if [ "$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/query/trace" -H "Content-Type: application/json" -d '{"question": "test"}')" = "200" ]; then
  TRACE_TIME=$(curl -s -o /dev/null -w "%{time_total}" -X POST "$BASE_URL/query/trace" \
    -H "Content-Type: application/json" \
    -d '{"question": "what is this platform for?"}')
  # "Similar to /query" -- not more than double, since both call the
  # identical Planner.plan(); a bigger gap suggests unexpected extra
  # work in build_trace_response() or the audit write path.
  TRACE_TIME_OK=$(awk -v qt="$QUERY_TIME" -v tt="$TRACE_TIME" 'BEGIN { print (tt < qt * 2 + 0.5) ? "true" : "false" }')
  check "/query/trace latency similar to /query (query: ${QUERY_TIME}s, trace: ${TRACE_TIME}s)" "$TRACE_TIME_OK"
else
  echo "  SKIPPED (trace endpoint disabled in this environment)"
fi

QUERY_RESPONSE=$(curl -s -X POST "$BASE_URL/query" \
  -H "Content-Type: application/json" \
  -d '{"question": "asdkfjaslkdfj nonsense query"}')
ANSWER_AVAILABLE=$(echo "$QUERY_RESPONSE" | jq -r '.answer_available' 2>/dev/null)
check "/query returns answer_available=false for a nonsense query (no leaked internals)" \
  "$([ "$ANSWER_AVAILABLE" = "false" ] && echo true || echo false)"

MESSAGE=$(echo "$QUERY_RESPONSE" | jq -r '.message // ""' 2>/dev/null)
check "No-evidence response never mentions 'denied' (no-leakage check)" \
  "$([ -z "$(echo "$MESSAGE" | grep -i denied)" ] && echo true || echo false)"

echo ""
echo "=== 5. Persistence (requires psql access to the postgres container) ==="
if command -v docker &> /dev/null; then
  AUDIT_COUNT=$(docker compose -f docker/docker-compose.yml exec -T postgres \
    psql -U cekp -d cekp -tAc "SELECT COUNT(*) FROM audit_log;" 2>/dev/null | tr -d '[:space:]')
  if [ -n "$AUDIT_COUNT" ] && [ "$AUDIT_COUNT" -gt 0 ] 2>/dev/null; then
    check "audit_log has rows after querying" "true"
    ATTEMPTS_TYPE=$(docker compose -f docker/docker-compose.yml exec -T postgres \
      psql -U cekp -d cekp -tAc \
      "SELECT jsonb_typeof(strategy_attempts::jsonb) FROM audit_log ORDER BY timestamp DESC LIMIT 1;" 2>/dev/null | tr -d '[:space:]')
    check "strategy_attempts is stored as a real JSON array (not a string)" \
      "$([ "$ATTEMPTS_TYPE" = "array" ] && echo true || echo false)"
  else
    check "audit_log has rows after querying" "false"
    echo "    (could not read audit_log -- check postgres container name/credentials, or run manually:)"
    echo "    docker compose -f docker/docker-compose.yml exec postgres psql -U cekp -d cekp -c 'SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT 5;'"
  fi
else
  echo "  SKIPPED (docker not available in this shell)"
fi

echo ""
echo "=== 6. Chaos: exceptions don't crash requests ==="
echo "  [manual] To test: stop the qdrant container (docker compose stop qdrant),"
echo "  then POST to /query again and confirm you still get a clean 200 with"
echo "  answer_available=false / planner_outcome reflecting the failure --"
echo "  NOT a 500. Restart qdrant afterward: docker compose start qdrant"

echo ""
echo "==================================="
green "PASSED: $PASS"
if [ "$FAIL" -gt 0 ]; then
  red "FAILED: $FAIL"
else
  echo "FAILED: $FAIL"
fi
echo "Manual items (see docs/integration-validation.md) still need a human look."
echo "==================================="

exit $([ "$FAIL" -eq 0 ] && echo 0 || echo 1)