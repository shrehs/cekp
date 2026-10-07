# CEKP Reliability Experiment Report

**Run:** 2026-10-07T05:55:34.511572

**Overall result:** FAILED

---

## What this experiment tests

The full reliability loop from `docs/reliability-loop.md`:

```
Observation  →  State inference  →  Decision  →  Intervention  →  Outcome  →  Verification
```

Concretely:

```
Graph healthy (baseline)
  ↓ Neo4j paused
Graph errors accumulate in sliding window
  ↓ error rate >= 60%
Monitor infers UNAVAILABLE
  ↓ planner consults monitor
Graph skipped — intervention recorded
  ↓ planner tries Hybrid
Hybrid returns evidence-backed result
  ↓ Neo4j unpaused, successes flow in
Monitor returns to HEALTHY
  ↓ next request
Graph attempted again — no skip
```

---

## Phase Baseline — PASSED

_Verify Graph is healthy and the system is in a known good state._

**Observations:**

- planner_outcome: success
- evidence_outcome: evidence_backed
- graph inferred_state: healthy
- graph attempted (not skipped): True
- selected_strategy: graph
- documents: 4

**Prometheus snapshot:**

- `strategy_state_graph`: 0.0
- `strategy_state_hybrid`: 0.0
- `recovery_attempts_graph`: 9.0
- `recovery_success_graph_hybrid`: None
- `retrieval_attempts_graph_error`: 2.0
- `retrieval_attempts_graph_skipped`: 9.0

**Trace (last query in phase):**

```json
{
  "planner_outcome": "success",
  "evidence_outcome": "evidence_backed",
  "selected_strategy": "graph",
  "final_documents_count": 4,
  "final_confidence": 0.85,
  "final_latency_ms": 16.461605000586133,
  "inferred_states": {
    "graph": "healthy",
    "vector": "healthy",
    "hybrid": "healthy"
  },
  "interventions": [],
  "attempts": [
    {
      "strategy": "graph",
      "outcome": "success",
      "confidence": 0.85,
      "latency_ms": 16.461605000586133
    }
  ],
  "_error": null
}
```

## Phase Inject Failures — PASSED

_Pause Neo4j, send 10 graph queries to drive monitor to UNAVAILABLE._

**Observations:**

- Neo4j container paused: docker-neo4j-1
- queries sent: 10
- graph error/skip outcomes: 10/10

**Prometheus snapshot:**

- `strategy_state_graph`: None
- `strategy_state_hybrid`: None
- `recovery_attempts_graph`: None
- `recovery_success_graph_hybrid`: None
- `retrieval_attempts_graph_error`: None
- `retrieval_attempts_graph_skipped`: None

**Trace (last query in phase):**

```json
{
  "planner_outcome": "failed",
  "evidence_outcome": "not_evaluated",
  "selected_strategy": null,
  "final_documents_count": 0,
  "final_confidence": null,
  "final_latency_ms": null,
  "inferred_states": {},
  "interventions": [],
  "attempts": [],
  "_error": "timeout"
}
```

## Phase Observe Skip — FAILED

_Verify Graph is skipped (UNAVAILABLE) and fallback returns evidence._

**Observations:**

- skip query: Which functions are defined in app.planner.planner?
- graph inferred_state: unknown
- graph skipped: False
- intervention recorded: False
- fallback query: How does the planner escalate strategies?
- fallback strategy: None
- planner_outcome: failed
- evidence_outcome: not_evaluated
- documents: 0

**Prometheus snapshot:**

- `strategy_state_graph`: None
- `strategy_state_hybrid`: None
- `recovery_attempts_graph`: None
- `recovery_success_graph_hybrid`: None
- `retrieval_attempts_graph_error`: None
- `retrieval_attempts_graph_skipped`: None

**Trace (last query in phase):**

```json
{
  "planner_outcome": "failed",
  "evidence_outcome": "not_evaluated",
  "selected_strategy": null,
  "final_documents_count": 0,
  "final_confidence": null,
  "final_latency_ms": null,
  "inferred_states": {},
  "interventions": [],
  "attempts": [],
  "_error": "timeout"
}
```

## Phase Restore — PASSED

_Unpause Neo4j, probe monitor with successes, verify Graph returns to HEALTHY._

**Observations:**

- Neo4j container unpaused: docker-neo4j-1
- Neo4j reachable via /ready: True
- probe result: {'strategy': 'graph', 'probed_successes': 10, 'state': 'healthy'}
- restore queries sent: 20
- graph non-error outcomes: 20/20

**Prometheus snapshot:**

- `strategy_state_graph`: 1.0
- `strategy_state_hybrid`: 0.0
- `recovery_attempts_graph`: 9.0
- `recovery_success_graph_hybrid`: None
- `retrieval_attempts_graph_error`: 7.0
- `retrieval_attempts_graph_skipped`: 9.0

**Trace (last query in phase):**

```json
{
  "planner_outcome": "success",
  "evidence_outcome": "evidence_backed",
  "selected_strategy": "graph",
  "final_documents_count": 4,
  "final_confidence": 0.85,
  "final_latency_ms": 10.000228000535571,
  "inferred_states": {
    "graph": "healthy",
    "vector": "healthy",
    "hybrid": "healthy"
  },
  "interventions": [],
  "attempts": [
    {
      "strategy": "graph",
      "outcome": "success",
      "confidence": 0.85,
      "latency_ms": 10.000228000535571
    }
  ],
  "_error": null
}
```

## Phase Verify Recovery — PASSED

_Verify Graph is HEALTHY again and attempted without intervention._

**Observations:**

- graph inferred_state: healthy
- graph attempted (not skipped): True
- no intervention: True
- planner_outcome: success
- evidence_outcome: evidence_backed
- selected_strategy: graph

**Prometheus snapshot:**

- `strategy_state_graph`: 1.0
- `strategy_state_hybrid`: 0.0
- `recovery_attempts_graph`: 9.0
- `recovery_success_graph_hybrid`: None
- `retrieval_attempts_graph_error`: 7.0
- `retrieval_attempts_graph_skipped`: 9.0

**Trace (last query in phase):**

```json
{
  "planner_outcome": "success",
  "evidence_outcome": "evidence_backed",
  "selected_strategy": "graph",
  "final_documents_count": 4,
  "final_confidence": 0.85,
  "final_latency_ms": 7.736599000054412,
  "inferred_states": {
    "graph": "healthy",
    "vector": "healthy",
    "hybrid": "healthy"
  },
  "interventions": [],
  "attempts": [
    {
      "strategy": "graph",
      "outcome": "success",
      "confidence": 0.85,
      "latency_ms": 7.736599000054412
    }
  ],
  "_error": null
}
```

---

## Conclusion

Fallback did not work as expected. Either the monitor did not reach UNAVAILABLE (not enough errors recorded) or the Hybrid strategy did not return evidence. Check the phase 2 trace for details.