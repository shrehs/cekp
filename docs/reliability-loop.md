# CEKP Reliability Loop — Architecture and Validation

## The question this answers

Collecting telemetry is not the same as understanding system state.

CEKP v2.1 added structured logs, Prometheus metrics, and Jaeger traces across
eight dimensions: HTTP, planner, evidence, policy, strategy, documents,
confidence, and latency. That answered "what happened."

The v2.2 reliability loop introduced inferred per-strategy health and
UNAVAILABLE skipping. v2.3 adds health-aware ranking for DEGRADED strategies
and bounded, probe-gated recovery trials: **can inferred operating state
change routing, and can a skipped strategy be tested safely for recovery?**

---

## The loop

```
Observation
     ↓
State inference
     ↓
Decision
     ↓
Intervention
     ↓
Outcome
     ↓
Verification
```

Each step is explicit, traceable, and testable. No step is implicit or
delegated to an LLM.

---

## State model

Three states per retrieval strategy, derived from a sliding window of recent
observations (default window = 10):

```
HEALTHY      error rate < 30%  AND  p95 latency < 3s
DEGRADED     error rate >= 30% OR   p95 latency >= 3s
UNAVAILABLE  error rate >= 60%
```

"Error" means `StrategyOutcome.ERROR` — an infrastructure failure (timeout,
connection refused, exception). `LOW_CONFIDENCE` and `NOT_IMPLEMENTED` are
not health signals; they mean the strategy ran and found nothing, which is
expected behaviour.

The thresholds are constants in `app/planner/health.py`, in one place, easy
to move to config. The state is derived on demand from the window — there is
no stored state, no timer, no external dependency.

### Why three states, not two

`DEGRADED` is the important middle state. It means "still attempting, but the
planner has evidence of problems." The current planner only acts on
`UNAVAILABLE` (skip). `DEGRADED` is visible in the trace and the
`cekp_strategy_state` Prometheus gauge, which means it can drive future
decisions — for example, penalising a degraded strategy's ranking — without
requiring changes to the monitor.

### Why a sliding window, not a circuit breaker

A circuit breaker has three states (closed / open / half-open) and a
timer-based reset. The sliding window has no timer: it recovers automatically
as new observations arrive. This means:

- Recovery is proportional to traffic, not to wall-clock time.
- The state is always derived from real recent observations, not from a
  timer that may have fired while the dependency was still broken.
- There is no half-open state to reason about or test.

The tradeoff: under zero traffic, a broken dependency stays UNAVAILABLE
indefinitely. Recovery therefore uses an explicit, bounded trial mechanism:
a real dependency probe can grant one retrieval trial, but it does not write
a synthetic success or change inferred state. The trial must pass the normal
policy gate, and only its real retrieval outcome enters the sliding window.
A failed trial remains an infrastructure error; another trial requires a
fresh successful dependency probe. Concurrent trials for the same strategy
are prevented within this process.

---

## Decision rules

```
HEALTHY      → attempt (normal planner flow)
DEGRADED     → attempt (visible in trace, influences future ranking — v2.3)
UNAVAILABLE  → skip (intervention recorded, fallback attempted)
```

The decision is made before policy check and before retrieval. A skipped
strategy never reaches the retriever.

---

## Intervention trace

A `/query/trace` response for a request where Graph was UNAVAILABLE and
Hybrid was the fallback:

```json
{
  "ranked_strategies": ["graph", "hybrid"],
  "inferred_states": {
    "graph": "unavailable",
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
      "latency_ms": null,
      "metadata": { "inferred_state": "unavailable" }
    },
    {
      "strategy": "hybrid",
      "outcome": "success",
      "confidence": 0.82,
      "cleared_threshold": true,
      "latency_ms": 210.4
    }
  ],
  "planner_outcome": "success",
  "evidence_outcome": "evidence_backed",
  "selected_strategy": "hybrid",
  "final_documents_count": 4
}
```

Every field in this response is a direct answer to a question:

| Field | Question answered |
|---|---|
| `inferred_states.graph` | What did the monitor think about Graph at request time? |
| `interventions[0].decision` | What did the planner decide to do about it? |
| `attempts[0].outcome` | Was the skip recorded in the attempt log? |
| `attempts[1].outcome` | Did the fallback actually run? |
| `evidence_outcome` | Did the intervention preserve result quality? |
| `final_documents_count` | How many documents came back? |

---

## Verification semantics

Verification uses the frozen outcome semantics established in v1:

```
planner_outcome: success | no_evidence | access_denied | failed
evidence_outcome: evidence_backed | no_evidence | not_evaluated
documents: list (non-empty = evidence-backed)
confidence: float (above strategy threshold = cleared)
latency_ms: float (end-to-end)
```

A recovery is **successful** if:
- `planner_outcome == success`
- `evidence_outcome == evidence_backed`
- `selected_strategy != skipped_strategy`

A recovery is **failed** if:
- `planner_outcome == failed` (all strategies skipped or errored)
- or `evidence_outcome == no_evidence` (fallback ran but found nothing)

---

## Recovery metrics

```
cekp_recovery_attempts_total{strategy}
    How often a strategy was skipped due to inferred UNAVAILABLE state.

cekp_recovery_success_total{skipped_strategy, fallback_strategy}
    How often the fallback succeeded after a skip.
    Labelled with both strategies so you can see which fallback works.

cekp_recovery_duration_seconds
    Time from first skip to successful fallback resolution.

cekp_strategy_state{strategy}
    Current inferred state as a gauge: 0=healthy, 1=degraded, 2=unavailable.
    Queryable in Grafana without parsing log fields.
```

These answer the reliability questions:

- How often do we recover? → `recovery_success / recovery_attempts`
- How quickly? → `recovery_duration` p50/p95
- Which fallback works? → `recovery_success_total` by `fallback_strategy`
- Are we unnecessarily skipping? → `strategy_state` gauge over time

---

## Validation — what the tests prove

### Boundary tests (`test_health_monitor.py`)

The state machine is tested at exact threshold boundaries:

| Condition | Expected state |
|---|---|
| error rate = 20% (below 30%) | HEALTHY |
| error rate = 30% (at threshold) | DEGRADED |
| error rate = 40% (above, below 60%) | DEGRADED |
| error rate = 50% (below 60%) | DEGRADED |
| error rate = 60% (at threshold) | UNAVAILABLE |
| error rate = 70% (above) | UNAVAILABLE |
| p95 latency = 2999ms (below 3000ms) | HEALTHY |
| p95 latency = 3000ms (at threshold) | DEGRADED |
| p95 latency = 5000ms (above) | DEGRADED |
| high latency + high error rate | UNAVAILABLE (error rate wins) |

### Dynamic transition tests

The full sequence is tested as a single controlled experiment:

```
Phase 1: 10 successes          → HEALTHY    ✓
Phase 2a: +3 errors (30%)      → DEGRADED   ✓
Phase 2b: +3 more errors (60%) → UNAVAILABLE ✓
Phase 3: 10 successes          → HEALTHY    ✓
```

Partial recovery is also tested: 5 successes after UNAVAILABLE lands at
DEGRADED, not HEALTHY. The monitor does not jump states.

### Recovery experiment

The recovery path deliberately separates dependency reachability from
retrieval health:

```
inject Graph infrastructure errors → UNAVAILABLE
planner skips Graph → intervention recorded; fallback is attempted
restore Neo4j
real Neo4j RETURN 1 probe succeeds → one trial permission (state stays UNAVAILABLE)
normal planner policy gate → one bounded Graph retrieval trial
real retrieval outcome enters the sliding window
repeat probe + trial only while still UNAVAILABLE
enough real non-error retrieval observations displace old errors → state recovers
```

A successful dependency probe is not evidence that retrieval itself works.
It only permits one real retrieval attempt. The trial still passes through
the normal authorization check. A retrieval `ERROR` is recorded as an error;
`LOW_CONFIDENCE` and `NOT_IMPLEMENTED` remain non-infrastructure outcomes and
are not mislabelled as errors. The frozen planner/evidence outcome semantics
are unchanged.

The `/query/monitor/probe` endpoint is an internal diagnostic endpoint gated
by `trace_endpoint_enabled`. It probes Neo4j for Graph, and Qdrant for Vector,
Hybrid, and Agentic strategies. It returns `503` if the dependency probe fails,
`409` if a trial is not applicable or already pending/in flight, and otherwise
grants a single-use trial. It does not directly modify the observation window.
The endpoint should remain disabled outside local/development environments.

The automated tests cover monitor permission semantics and the planner's
one-trial path using fake strategy/dependency components. The live Docker
experiment script is an integration experiment and must be run against a
running stack before claiming measured recovery time or end-to-end recovery.

---

## DEGRADED routing and current limits

In v2.3, `DEGRADED` is actionable through a configurable routing penalty.
The penalty changes candidate order only; it does not change retrieval scores,
confidence, authorization, or evidence semantics.

```
Normal ranking:    Graph 0.91 > Hybrid 0.84 > Vector 0.71
Graph is DEGRADED: Graph 0.61 > Hybrid 0.84 > Vector 0.71
Effective ranking: Hybrid 0.84 > Vector 0.71 > Graph 0.61
```

This is a soft preference signal, not a proof that the alternative will
produce better evidence. The planner still evaluates candidates through its
normal policy and evidence flow. The recovery trial mechanism is separate:
it temporarily permits one real attempt for an UNAVAILABLE strategy after a
successful dependency probe, while preserving the inferred state until real
retrieval observations update the window.

---

## Design principles this reflects

From the CEKP architecture:

> explicit retrieval strategies  
> explainable planner decisions  
> policy-aware escalation  
> observable APIs  
> measurable performance  
> graceful failure and no-leakage behavior

The reliability loop adds one more: **explainable recovery**. When CEKP
falls back from Graph to Hybrid, the reason is recorded in the trace, the
intervention is counted in metrics, and the outcome is verified against the
same frozen semantics used everywhere else in the system.

The system does not pretend to be autonomous. It observes, infers, decides,
acts, and verifies — and every step is auditable.
