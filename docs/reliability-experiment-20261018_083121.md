# CEKP Reliability Experiment Report

**Run:** 2026-10-18T08:30:45.524449

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

## Phase Baseline — FAILED

_Verify Graph is healthy and the system is in a known good state._

**Observations:**

- planner_outcome: no_evidence
- evidence_outcome: no_evidence
- graph inferred_state: unavailable
- graph attempted (not skipped): False
- selected_strategy: None
- documents: 0

**Prometheus snapshot:**

- `strategy_state_graph`: 2.0
- `strategy_state_hybrid`: 0.0
- `recovery_attempts_graph`: 41.0
- `recovery_success_graph_hybrid`: None
- `retrieval_attempts_graph_error`: 6.0
- `retrieval_attempts_graph_skipped`: 41.0

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
      "reason": "inferred_unavailable",
      "routing_score": 1.0,
      "health_penalty": 0.0,
      "adjusted_score": null
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
      "latency_ms": 51.80459800067183
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

- `strategy_state_graph`: 2.0
- `strategy_state_hybrid`: 0.0
- `recovery_attempts_graph`: 41.0
- `recovery_success_graph_hybrid`: None
- `retrieval_attempts_graph_error`: 6.0
- `retrieval_attempts_graph_skipped`: 52.0

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
      "reason": "inferred_unavailable",
      "routing_score": 1.0,
      "health_penalty": 0.0,
      "adjusted_score": null
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
      "latency_ms": 22.079956000197853
    }
  ],
  "_error": null
}
```

## Phase Observe Skip — PASSED

_Verify Graph is skipped (UNAVAILABLE) and fallback returns evidence._

**Observations:**

- skip query: Which functions are defined in app.planner.planner?
- graph inferred_state: unavailable
- graph skipped: True
- intervention recorded: True
- intervention detail: {"strategy": "graph", "inferred_state": "unavailable", "decision": "skip", "reason": "inferred_unavailable", "routing_score": 1.0, "health_penalty": 0.0, "adjusted_score": null}
- fallback query: How does the planner escalate strategies?
- fallback strategy: hybrid
- planner_outcome: success
- evidence_outcome: evidence_backed
- documents: 5

**Prometheus snapshot:**

- `strategy_state_graph`: 2.0
- `strategy_state_hybrid`: 0.0
- `recovery_attempts_graph`: 52.0
- `recovery_success_graph_hybrid`: None
- `retrieval_attempts_graph_error`: 6.0
- `retrieval_attempts_graph_skipped`: 52.0

**Trace (last query in phase):**

```json
{
  "planner_outcome": "success",
  "evidence_outcome": "evidence_backed",
  "selected_strategy": "hybrid",
  "final_documents_count": 5,
  "final_confidence": 0.6962,
  "final_latency_ms": 22.78985199973249,
  "inferred_states": {
    "graph": "unavailable",
    "vector": "healthy",
    "hybrid": "healthy"
  },
  "interventions": [],
  "attempts": [
    {
      "strategy": "hybrid",
      "outcome": "success",
      "confidence": 0.6962,
      "latency_ms": 22.78985199973249
    }
  ],
  "_error": null
}
```

## Phase Restore — PASSED

_Unpause Neo4j and verify recovery through bounded real retrieval trials._

**Observations:**

- Neo4j container unpaused: docker-neo4j-1
- Neo4j reachable via /ready: True
- restore queries sent: 20
- graph non-error outcomes: 20/20
- Dependency probes do not write synthetic retrieval successes.

**Prometheus snapshot:**

- `strategy_state_graph`: 2.0
- `strategy_state_hybrid`: 0.0
- `recovery_attempts_graph`: 53.0
- `recovery_success_graph_hybrid`: None
- `retrieval_attempts_graph_error`: 6.0
- `retrieval_attempts_graph_skipped`: 53.0

**Trace (last query in phase):**

```json
{
  "planner_outcome": "success",
  "evidence_outcome": "evidence_backed",
  "selected_strategy": "graph",
  "final_documents_count": 4,
  "final_confidence": 0.85,
  "final_latency_ms": 9.699509999336442,
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
      "latency_ms": 9.699509999336442
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

- `strategy_state_graph`: 2.0
- `strategy_state_hybrid`: 0.0
- `recovery_attempts_graph`: 53.0
- `recovery_success_graph_hybrid`: None
- `retrieval_attempts_graph_error`: 6.0
- `retrieval_attempts_graph_skipped`: 53.0

**Trace (last query in phase):**

```json
{
  "planner_outcome": "success",
  "evidence_outcome": "evidence_backed",
  "selected_strategy": "graph",
  "final_documents_count": 4,
  "final_confidence": 0.85,
  "final_latency_ms": 9.415657999852556,
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
      "latency_ms": 9.415657999852556
    }
  ],
  "_error": null
}
```

---

## Conclusion

Partial pass — see individual phase results.