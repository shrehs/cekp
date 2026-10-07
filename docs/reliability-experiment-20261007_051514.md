# CEKP Reliability Experiment Report

**Run:** 2026-10-07T05:11:28.414815

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

- `strategy_state_graph`: None
- `strategy_state_hybrid`: None
- `recovery_attempts_graph`: None
- `recovery_success_graph_hybrid`: None
- `retrieval_attempts_graph_error`: None
- `retrieval_attempts_graph_skipped`: None

**Trace (last query in phase):**

```json
{
  "planner_outcome": "success",
  "evidence_outcome": "evidence_backed",
  "selected_strategy": "graph",
  "final_documents_count": 4,
  "final_confidence": 0.85,
  "final_latency_ms": 219.78762300022936,
  "inferred_states": {
    "graph": "healthy"
  },
  "interventions": [],
  "attempts": [
    {
      "strategy": "graph",
      "outcome": "success",
      "confidence": 0.85,
      "latency_ms": 219.78762300022936
    }
  ],
  "_error": null
}
```

## Phase Inject Failures — FAILED

_Pause Neo4j, send 10 graph queries to drive monitor to UNAVAILABLE._

**Observations:**

- Neo4j container paused: docker-neo4j-1
- queries sent: 10
- graph error/skip outcomes: 4/10

**Prometheus snapshot:**

- `strategy_state_graph`: 2.0
- `strategy_state_hybrid`: None
- `recovery_attempts_graph`: 4.0
- `recovery_success_graph_hybrid`: None
- `retrieval_attempts_graph_error`: 2.0
- `retrieval_attempts_graph_skipped`: 4.0

**Trace (last query in phase):**

```json
{
  "planner_outcome": "no_evidence",
  "evidence_outcome": "no_evidence",
  "selected_strategy": null,
  "final_documents_count": 0,
  "final_confidence": null,
  "final_latency_ms": null,
  "inferred_states": {
    "graph": "unavailable",
    "vector": "degraded"
  },
  "interventions": [
    {
      "strategy": "graph",
      "inferred_state": "unavailable",
      "decision": "skip",
      "reason": "inferred_unavailable"
    }
  ],
  "attempts": [
    {
      "strategy": "graph",
      "outcome": "skipped_unavailable",
      "confidence": null,
      "latency_ms": null
    },
    {
      "strategy": "vector",
      "outcome": "success",
      "confidence": 0.3629806,
      "latency_ms": 23.68368699990242
    }
  ],
  "_error": null
}
```

## Phase Observe Skip — FAILED

_Verify Graph is skipped (UNAVAILABLE) and Hybrid fallback returns evidence._

**Observations:**

- query: How does the intent classifier decide what strategy to use?
- graph inferred_state: unavailable
- graph skipped: False
- intervention recorded: False
- fallback strategy: hybrid
- planner_outcome: success
- evidence_outcome: evidence_backed
- documents: 5

**Prometheus snapshot:**

- `strategy_state_graph`: 2.0
- `strategy_state_hybrid`: None
- `recovery_attempts_graph`: 4.0
- `recovery_success_graph_hybrid`: None
- `retrieval_attempts_graph_error`: 2.0
- `retrieval_attempts_graph_skipped`: 4.0

**Trace (last query in phase):**

```json
{
  "planner_outcome": "success",
  "evidence_outcome": "evidence_backed",
  "selected_strategy": "hybrid",
  "final_documents_count": 5,
  "final_confidence": 0.8359,
  "final_latency_ms": 109.69495800054574,
  "inferred_states": {
    "graph": "unavailable",
    "vector": "degraded",
    "hybrid": "healthy"
  },
  "interventions": [],
  "attempts": [
    {
      "strategy": "hybrid",
      "outcome": "success",
      "confidence": 0.8359,
      "latency_ms": 109.69495800054574
    }
  ],
  "_error": null
}
```

## Phase Restore — FAILED

_Unpause Neo4j, send 10 successful graph queries to restore HEALTHY state._

**Observations:**

- Neo4j container unpaused: docker-neo4j-1
- restore queries sent: 10
- graph non-error outcomes: 0/10

**Prometheus snapshot:**

- `strategy_state_graph`: 2.0
- `strategy_state_hybrid`: 0.0
- `recovery_attempts_graph`: 8.0
- `recovery_success_graph_hybrid`: None
- `retrieval_attempts_graph_error`: 2.0
- `retrieval_attempts_graph_skipped`: 8.0

**Trace (last query in phase):**

```json
{
  "planner_outcome": "no_evidence",
  "evidence_outcome": "no_evidence",
  "selected_strategy": null,
  "final_documents_count": 0,
  "final_confidence": null,
  "final_latency_ms": null,
  "inferred_states": {
    "graph": "unavailable",
    "vector": "healthy",
    "hybrid": "healthy"
  },
  "interventions": [
    {
      "strategy": "graph",
      "inferred_state": "unavailable",
      "decision": "skip",
      "reason": "inferred_unavailable"
    }
  ],
  "attempts": [
    {
      "strategy": "graph",
      "outcome": "skipped_unavailable",
      "confidence": null,
      "latency_ms": null
    },
    {
      "strategy": "vector",
      "outcome": "success",
      "confidence": 0.3629806,
      "latency_ms": 22.17840299999807
    }
  ],
  "_error": null
}
```

## Phase Verify Recovery — FAILED

_Verify Graph is HEALTHY again and attempted without intervention._

**Observations:**

- graph inferred_state: unavailable
- graph attempted (not skipped): False
- no intervention: False
- planner_outcome: no_evidence
- evidence_outcome: no_evidence
- selected_strategy: None

**Prometheus snapshot:**

- `strategy_state_graph`: 2.0
- `strategy_state_hybrid`: 0.0
- `recovery_attempts_graph`: 8.0
- `recovery_success_graph_hybrid`: None
- `retrieval_attempts_graph_error`: 2.0
- `retrieval_attempts_graph_skipped`: 8.0

**Trace (last query in phase):**

```json
{
  "planner_outcome": "no_evidence",
  "evidence_outcome": "no_evidence",
  "selected_strategy": null,
  "final_documents_count": 0,
  "final_confidence": null,
  "final_latency_ms": null,
  "inferred_states": {
    "graph": "unavailable",
    "vector": "healthy",
    "hybrid": "healthy"
  },
  "interventions": [
    {
      "strategy": "graph",
      "inferred_state": "unavailable",
      "decision": "skip",
      "reason": "inferred_unavailable"
    }
  ],
  "attempts": [
    {
      "strategy": "graph",
      "outcome": "skipped_unavailable",
      "confidence": null,
      "latency_ms": null
    },
    {
      "strategy": "vector",
      "outcome": "success",
      "confidence": 0.3629806,
      "latency_ms": 47.14370700003201
    }
  ],
  "_error": null
}
```

---

## Conclusion

Fallback did not work as expected. Either the monitor did not reach UNAVAILABLE (not enough errors recorded) or the Hybrid strategy did not return evidence. Check the phase 2 trace for details.