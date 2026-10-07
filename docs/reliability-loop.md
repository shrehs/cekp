# CEKP Reliability Loop — Architecture and Validation

## The question this answers

Collecting telemetry is not the same as understanding system state.

CEKP v2.1 added structured logs, Prometheus metrics, and Jaeger traces across
eight dimensions: HTTP, planner, evidence, policy, strategy, documents,
confidence, and latency. That answered "what happened."

v2.2 asks the next question: **can the system infer a useful operating state
from its observations, and act on it?**

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
indefinitely. That is the correct behaviour — if no requests are flowing,
there is nothing to recover from.

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

```
inject 10 Graph errors → UNAVAILABLE
planner skips Graph → intervention recorded
Hybrid fallback → evidence-backed result
restore Graph (10 successes) → HEALTHY
next request → Graph attempted, no skip
```

Each step is a separate assertion. A failure pinpoints exactly which part
of the loop broke.

---

## What DEGRADED does not yet do

`DEGRADED` is currently observable but not actionable. The planner attempts
a degraded strategy the same as a healthy one.

The next step (v2.3) is to let `DEGRADED` influence strategy ranking:

```
Normal ranking:    Graph 0.91 > Hybrid 0.84 > Vector 0.71
Graph is DEGRADED: Graph 0.61 > Hybrid 0.84 > Vector 0.71
                              ↑ health penalty applied
Effective ranking: Hybrid 0.84 > Vector 0.71 > Graph 0.61
```

This is when inferred system state starts influencing the AI decision itself —
not as a hard skip, but as a soft preference signal that the planner can
override if no better option exists.

That is a more meaningful controllability experiment than adding more fallback
code, because it makes the system's reasoning about its own health part of the
retrieval decision.

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
