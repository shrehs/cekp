# scripts/validate_graph_feature.ps1
#
# Live validation of the complete graph feature, end to end, per the
# 5-step plan: ingest CEKP itself, run the four canonical graph
# questions, verify planner traces, verify evidence, verify confidence
# thresholds. Everything here hits the real running API -- nothing in
# this script was (or could be) run by Claude; this is the actual
# confirmation.
#
# Prerequisites:
#   docker compose -f docker/docker-compose.yml up -d --build
#   (picks up /ingest/local, which needs the ../app:/app/app mount
#   that's already in docker-compose.yml)
#
# Usage:
#   .\scripts\validate_graph_feature.ps1
#   .\scripts\validate_graph_feature.ps1 -BaseUrl http://localhost:8080

param(
    [string]$BaseUrl = "http://localhost:8080"
)

$ErrorActionPreference = "Stop"
$pass = 0
$fail = 0

function Write-Check($description, $condition) {
    if ($condition) {
        Write-Host "  PASS  $description" -ForegroundColor Green
        $script:pass++
    } else {
        Write-Host "  FAIL  $description" -ForegroundColor Red
        $script:fail++
    }
}

function Write-Info($text) {
    Write-Host "  INFO  $text" -ForegroundColor Yellow
}

# ============================================================
# Step 1: Ingest CEKP itself
# ============================================================
Write-Host "`n=== Step 1: Ingest CEKP (local-path, self-referential) ===" -ForegroundColor Cyan

$ingestBody = @{ path = "/app/app"; repo_name = "cekp" } | ConvertTo-Json
$ingestResponse = Invoke-RestMethod -Uri "$BaseUrl/ingest/local" -Method Post -Body $ingestBody -ContentType "application/json"

Write-Host "  documents_ingested: $($ingestResponse.documents_ingested)"
Write-Host "  graph_status: $($ingestResponse.graph_status)"
if ($ingestResponse.graph_error) {
    Write-Host "  graph_error: $($ingestResponse.graph_error)" -ForegroundColor Red
}

Write-Check "Documents were ingested (> 0)" ($ingestResponse.documents_ingested -gt 0)
Write-Check "Graph was persisted (not skipped/failed)" ($ingestResponse.graph_status -eq "persisted")

if ($ingestResponse.graph_status -ne "persisted") {
    Write-Host "`nGraph persistence did not succeed -- steps 2-5 will likely fail for that reason," -ForegroundColor Red
    Write-Host "not because the queries themselves are wrong. Check the API container logs:" -ForegroundColor Red
    Write-Host "  docker compose -f docker/docker-compose.yml logs api --tail 50" -ForegroundColor Red
}

# ============================================================
# Steps 2-5: The four canonical graph questions
# ============================================================
# Each grounded in VERIFIED real structure of this repo (not generic
# placeholders) -- see the response text for how each was confirmed
# to exist before being used here.
$canonicalQuestions = @(
    @{
        Label = "Which modules import app.core.config?"
        Question = "Which modules import app.core.config?"
        ExpectedMethod = "get_importers_of"
    },
    @{
        Label = "Where is Planner defined?"
        Question = "Where is Planner defined?"
        ExpectedMethod = "find_class (via find_symbol)"
    },
    @{
        Label = "Which functions call _module_qualified_name?"
        Question = "Which functions call _module_qualified_name?"
        ExpectedMethod = "get_callers_of"
    },
    @{
        Label = "What classes are defined in neo4j_repository?"
        Question = "What classes are defined in neo4j_repository?"
        ExpectedMethod = "get_classes_defined_in"
    }
)

$results = @()

$allLatencies = @()  # for the aggregate baseline at the end

foreach ($case in $canonicalQuestions) {
    Write-Host "`n=== Canonical question: `"$($case.Question)`" ===" -ForegroundColor Cyan
    Write-Host "  Expected retriever method: $($case.ExpectedMethod)"

    $traceBody = @{ question = $case.Question } | ConvertTo-Json
    $trace = Invoke-RestMethod -Uri "$BaseUrl/query/trace" -Method Post -Body $traceBody -ContentType "application/json"

    # --- Step 3: verify planner trace ---
    $rankedFirst = $trace.ranked_strategies[0]
    $firstAttempt = $trace.attempts[0]

    Write-Host "  ranked_strategies: $($trace.ranked_strategies -join ', ')"
    Write-Host "  attempts[0]: outcome=$($firstAttempt.outcome) confidence=$($firstAttempt.confidence) cleared_threshold=$($firstAttempt.cleared_threshold)"
    Write-Host "  planner_outcome: $($trace.planner_outcome)"
    Write-Host "  final_strategy_used: $($trace.final_strategy_used)"
    Write-Host "  final_confidence: $($trace.final_confidence)"

    # --- Escalation-chain diagnosis: distinguish retrieval-quality
    # issues (graph ran, wasn't confident, escalated) from
    # infrastructure issues (graph never even ran). This is the exact
    # distinction requested: seeing GRAPH -> LOW_CONFIDENCE -> VECTOR
    # means the graph feature itself has a matching/quality problem,
    # not that something's broken end to end. ---
    if ($firstAttempt.outcome -eq "success") {
        Write-Check "attempts[0].outcome == 'success' (graph answered directly, no escalation)" $true
    } else {
        $chain = ($trace.attempts | ForEach-Object { "$($_.outcome)" }) -join " -> "
        Write-Host "  ESCALATION CHAIN: graph:$($firstAttempt.outcome) -> $chain" -ForegroundColor Red
        if ($firstAttempt.outcome -eq "not_implemented") {
            Write-Host "  DIAGNOSIS: graph strategy never ran for this question -- likely a routing/classification" -ForegroundColor Red
            Write-Host "  issue (check IntentClassifier / GraphStrategy._classify() patterns), or this question" -ForegroundColor Red
            Write-Host "  matched the org-dependency category, which is deliberately unimplemented." -ForegroundColor Red
        } else {
            Write-Host "  DIAGNOSIS: this is a RETRIEVAL-QUALITY issue, not an infrastructure issue." -ForegroundColor Red
            Write-Host "  Graph ran ($($firstAttempt.outcome)) but didn't return usable results for this specific" -ForegroundColor Red
            Write-Host "  phrasing. Check: did Step 1's ingest actually cover the referenced symbol? Does the" -ForegroundColor Red
            Write-Host "  extracted reference (see metadata.reference below) match what's actually in the graph?" -ForegroundColor Red
        }
        Write-Check "attempts[0].outcome == 'success' (graph answered directly, no escalation)" $false
    }

    Write-Check "planner_outcome == 'success'" ($trace.planner_outcome -eq "success")
    Write-Check "final_strategy_used == 'graph'" ($trace.final_strategy_used -eq "graph")

    # --- Step 5: verify confidence threshold behavior ---
    # GraphStrategy's confidence heuristic is 0.85 when it found
    # something (see app/planner/strategies.py); PlannerConfig's graph
    # threshold is 0.60 (see app/planner/config.py) -- 0.85 should
    # clear it every time results exist, which is exactly what
    # cleared_threshold is checking.
    Write-Check "attempts[0].cleared_threshold == true" ($firstAttempt.cleared_threshold -eq $true)
    Write-Check "confidence (0.85 expected) actually clears the 0.60 graph threshold" ($firstAttempt.confidence -ge 0.60)

    # --- Latency baseline ---
    # metadata carries classification_ms/retrieval_ms/formatting_ms
    # from GraphStrategy (see app/planner/strategies.py). retrieval_ms
    # bundles network round-trip + server-side Cypher execution --
    # can't be cleanly separated client-side without server-side query
    # profiling, so this doesn't claim more precision than it has.
    if ($firstAttempt.metadata) {
        $m = $firstAttempt.metadata
        Write-Host "  Latency breakdown:" -ForegroundColor Cyan
        Write-Host "    Classification:  $([math]::Round($m.classification_ms, 2)) ms"
        Write-Host "    Graph retrieval: $([math]::Round($m.retrieval_ms, 2)) ms  (network + server-side Cypher, combined)"
        Write-Host "    Formatting:      $([math]::Round($m.formatting_ms, 2)) ms"
        Write-Host "    Total GraphStrategy: $([math]::Round($firstAttempt.latency_ms, 2)) ms"
        if ($m.retrieval_ms) { $allLatencies += $m.retrieval_ms }
    } else {
        Write-Info "No metadata on attempts[0] -- graph strategy likely didn't run far enough to record timing."
    }

    # --- Step 4: verify evidence ---
    if ($trace.final_reasoning) {
        Write-Host "  reasoning: $($trace.final_reasoning)"
    }
    Write-Info "Evidence (eyeball this -- does it actually look right for the question asked?):"
    # /query/trace's build_trace_response doesn't currently echo documents
    # directly; cross-check against /query (the redacted endpoint) for the
    # user-facing view of the same evidence.
    $queryBody = @{ question = $case.Question } | ConvertTo-Json
    $queryResult = Invoke-RestMethod -Uri "$BaseUrl/query" -Method Post -Body $queryBody -ContentType "application/json"
    if ($queryResult.documents -and $queryResult.documents.Count -gt 0) {
        foreach ($doc in $queryResult.documents) {
            Write-Host "    - $($doc.text)" -ForegroundColor Gray
        }
        Write-Check "Evidence returned (documents non-empty)" $true
    } else {
        Write-Check "Evidence returned (documents non-empty)" $false
    }

    $results += [PSCustomObject]@{
        Question = $case.Question
        Strategy = $rankedFirst
        Outcome = $firstAttempt.outcome
        Confidence = $firstAttempt.confidence
        ClearedThreshold = $firstAttempt.cleared_threshold
        PlannerOutcome = $trace.planner_outcome
        EvidenceCount = $queryResult.documents.Count
        LatencyMs = $firstAttempt.latency_ms
    }
}

# ============================================================
# Summary
# ============================================================
Write-Host "`n=== Summary ===" -ForegroundColor Cyan
$results | Format-Table -AutoSize

if ($allLatencies.Count -gt 0) {
    Write-Host "=== Latency baseline (graph retrieval, network + Cypher combined) ===" -ForegroundColor Cyan
    $stats = $allLatencies | Measure-Object -Minimum -Maximum -Average
    Write-Host ("  Min: {0:N2} ms  Max: {1:N2} ms  Avg: {2:N2} ms  (n={3})" -f `
        $stats.Minimum, $stats.Maximum, $stats.Average, $stats.Count)
    Write-Host "  Record this baseline now -- it's the number to compare against once the graph" -ForegroundColor Yellow
    Write-Host "  grows to thousands of files, to catch regressions before they're a production problem." -ForegroundColor Yellow
}

Write-Host "`nPASSED: $pass" -ForegroundColor Green
if ($fail -gt 0) {
    Write-Host "FAILED: $fail" -ForegroundColor Red
} else {
    Write-Host "FAILED: $fail"
}

if ($fail -eq 0) {
    Write-Host "`nAll checks passed. Per the plan: the graph feature is complete for its" -ForegroundColor Green
    Write-Host "planned v1 scope. Move on to the next major capability." -ForegroundColor Green
    exit 0
} else {
    Write-Host "`nSome checks failed. Before assuming a GraphStrategy bug, check whether" -ForegroundColor Yellow
    Write-Host "graph_status was 'persisted' in Step 1 -- most failures here trace back" -ForegroundColor Yellow
    Write-Host "to that, not to the retrieval logic itself." -ForegroundColor Yellow
    exit 1
}