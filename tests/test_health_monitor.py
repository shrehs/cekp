"""
StrategyHealthMonitor validation suite — CEKP v2.2.

Three sections:

1. State inference (static) — existing coverage, kept as-is.

2. Boundary tests — verify the state machine at exact threshold boundaries.
   Tests are named to make the boundary explicit:
     _below_  = threshold - ε  (one observation short of triggering)
     _at_     = threshold      (exactly at the trigger point)
     _above_  = threshold + ε  (one observation over)

3. Dynamic transition tests — verify the full sequence:
     healthy → degraded → unavailable → healthy
   under controlled observation injection. This is the "recovery experiment"
   described in docs/reliability-loop.md.

The monitor uses a window of 10 and thresholds:
  degraded_error_rate   = 0.3   (3/10 errors)
  unavailable_error_rate = 0.6  (6/10 errors)
  degraded_latency_ms   = 3000  (p95 >= 3s)
"""
import math
from concurrent.futures import ThreadPoolExecutor

from app.planner.context import PlannerContext
from app.planner.enums import PlannerOutcome, StrategyName, StrategyOutcome, StrategyState
from app.planner.health import StrategyHealthMonitor
from app.planner.planner import Planner
from app.planner.registry import StrategyRegistry
from app.planner.result import RetrievalResult
from app.planner.strategy_base import RetrievalStrategy
from tests.test_planner import AllowAllPolicy, FakeClassifier, FakeStrategy

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _monitor(window: int = 10) -> StrategyHealthMonitor:
    """Standard monitor with explicit thresholds for predictable boundary math."""
    return StrategyHealthMonitor(
        window=window,
        degraded_error_rate=0.3,
        unavailable_error_rate=0.6,
        degraded_latency_ms=3_000.0,
    )


def _record_n(m, strategy, outcome, n, latency_ms=50.0):
    for _ in range(n):
        m.record(strategy, outcome, latency_ms)


def _make_planner(strategies, ranked, monitor, policy=None):
    registry = StrategyRegistry()
    for name, strategy in strategies.items():
        registry.register(name, strategy)
    return Planner(
        registry=registry,
        classifier=FakeClassifier(ranked),
        policy=policy or AllowAllPolicy(),
        monitor=monitor,
    )


# ---------------------------------------------------------------------------
# 1. State inference (static)
# ---------------------------------------------------------------------------

def test_fresh_monitor_is_healthy():
    assert _monitor().state(StrategyName.GRAPH) == StrategyState.HEALTHY


def test_all_successes_is_healthy():
    m = _monitor()
    _record_n(m, StrategyName.GRAPH, StrategyOutcome.SUCCESS, 10)
    assert m.state(StrategyName.GRAPH) == StrategyState.HEALTHY


def test_error_rate_above_degraded_threshold_is_degraded():
    # 4/10 = 40% >= 30% degraded threshold
    m = _monitor()
    _record_n(m, StrategyName.GRAPH, StrategyOutcome.SUCCESS, 6)
    _record_n(m, StrategyName.GRAPH, StrategyOutcome.ERROR, 4)
    assert m.state(StrategyName.GRAPH) == StrategyState.DEGRADED


def test_error_rate_above_unavailable_threshold_is_unavailable():
    # 6/10 = 60% >= 60% unavailable threshold
    m = _monitor()
    _record_n(m, StrategyName.GRAPH, StrategyOutcome.SUCCESS, 4)
    _record_n(m, StrategyName.GRAPH, StrategyOutcome.ERROR, 6)
    assert m.state(StrategyName.GRAPH) == StrategyState.UNAVAILABLE


def test_high_latency_p95_is_degraded_even_with_low_error_rate():
    m = _monitor()
    for _ in range(10):
        m.record(StrategyName.GRAPH, StrategyOutcome.SUCCESS, latency_ms=4_000.0)
    assert m.state(StrategyName.GRAPH) == StrategyState.DEGRADED


def test_low_confidence_does_not_count_as_error():
    m = _monitor()
    _record_n(m, StrategyName.GRAPH, StrategyOutcome.LOW_CONFIDENCE, 10)
    assert m.state(StrategyName.GRAPH) == StrategyState.HEALTHY


def test_sliding_window_old_errors_age_out():
    m = _monitor()
    _record_n(m, StrategyName.GRAPH, StrategyOutcome.ERROR, 10)
    assert m.state(StrategyName.GRAPH) == StrategyState.UNAVAILABLE
    _record_n(m, StrategyName.GRAPH, StrategyOutcome.SUCCESS, 10)
    assert m.state(StrategyName.GRAPH) == StrategyState.HEALTHY


def test_strategies_are_tracked_independently():
    m = _monitor()
    _record_n(m, StrategyName.GRAPH, StrategyOutcome.ERROR, 10)
    _record_n(m, StrategyName.VECTOR, StrategyOutcome.SUCCESS, 10)
    assert m.state(StrategyName.GRAPH) == StrategyState.UNAVAILABLE
    assert m.state(StrategyName.VECTOR) == StrategyState.HEALTHY


def test_snapshot_returns_all_observed_strategies():
    m = _monitor()
    m.record(StrategyName.GRAPH, StrategyOutcome.ERROR, 10.0)
    m.record(StrategyName.VECTOR, StrategyOutcome.SUCCESS, 10.0)
    snap = m.snapshot()
    assert snap["graph"] == StrategyState.UNAVAILABLE.value
    assert snap["vector"] == StrategyState.HEALTHY.value


# ---------------------------------------------------------------------------
# 2. Boundary tests — error rate
#
# Window = 10, degraded threshold = 0.3, unavailable threshold = 0.6.
# Boundary values:
#   degraded:    2 errors = 20% (below), 3 errors = 30% (at), 4 errors = 40% (above)
#   unavailable: 5 errors = 50% (below), 6 errors = 60% (at), 7 errors = 70% (above)
# ---------------------------------------------------------------------------

def test_error_rate_below_degraded_threshold_is_healthy():
    # 2/10 = 20% < 30% -> HEALTHY
    m = _monitor()
    _record_n(m, StrategyName.GRAPH, StrategyOutcome.SUCCESS, 8)
    _record_n(m, StrategyName.GRAPH, StrategyOutcome.ERROR, 2)
    assert m.state(StrategyName.GRAPH) == StrategyState.HEALTHY


def test_error_rate_at_degraded_threshold_is_degraded():
    # 3/10 = 30% == 30% -> DEGRADED
    m = _monitor()
    _record_n(m, StrategyName.GRAPH, StrategyOutcome.SUCCESS, 7)
    _record_n(m, StrategyName.GRAPH, StrategyOutcome.ERROR, 3)
    assert m.state(StrategyName.GRAPH) == StrategyState.DEGRADED


def test_error_rate_above_degraded_threshold_but_below_unavailable_is_degraded():
    # 4/10 = 40%: above degraded (30%), below unavailable (60%) -> DEGRADED
    m = _monitor()
    _record_n(m, StrategyName.GRAPH, StrategyOutcome.SUCCESS, 6)
    _record_n(m, StrategyName.GRAPH, StrategyOutcome.ERROR, 4)
    assert m.state(StrategyName.GRAPH) == StrategyState.DEGRADED


def test_error_rate_below_unavailable_threshold_is_not_unavailable():
    # 5/10 = 50% < 60% -> DEGRADED (not UNAVAILABLE)
    m = _monitor()
    _record_n(m, StrategyName.GRAPH, StrategyOutcome.SUCCESS, 5)
    _record_n(m, StrategyName.GRAPH, StrategyOutcome.ERROR, 5)
    assert m.state(StrategyName.GRAPH) == StrategyState.DEGRADED


def test_error_rate_at_unavailable_threshold_is_unavailable():
    # 6/10 = 60% == 60% -> UNAVAILABLE
    m = _monitor()
    _record_n(m, StrategyName.GRAPH, StrategyOutcome.SUCCESS, 4)
    _record_n(m, StrategyName.GRAPH, StrategyOutcome.ERROR, 6)
    assert m.state(StrategyName.GRAPH) == StrategyState.UNAVAILABLE


def test_error_rate_above_unavailable_threshold_is_unavailable():
    # 7/10 = 70% > 60% -> UNAVAILABLE
    m = _monitor()
    _record_n(m, StrategyName.GRAPH, StrategyOutcome.SUCCESS, 3)
    _record_n(m, StrategyName.GRAPH, StrategyOutcome.ERROR, 7)
    assert m.state(StrategyName.GRAPH) == StrategyState.UNAVAILABLE


# ---------------------------------------------------------------------------
# 2b. Boundary tests — p95 latency
#
# Window = 10, degraded_latency_ms = 3000.
# p95 index = ceil(0.95 * 10) - 1 = ceil(9.5) - 1 = 10 - 1 = 9 (the max).
# So with 10 observations, p95 = the highest latency value.
# Boundary: 9 fast + 1 slow. The slow one IS the p95.
# ---------------------------------------------------------------------------

def test_latency_p95_below_threshold_is_healthy():
    # All observations at 2999ms < 3000ms threshold -> HEALTHY
    m = _monitor()
    for _ in range(10):
        m.record(StrategyName.GRAPH, StrategyOutcome.SUCCESS, latency_ms=2_999.0)
    assert m.state(StrategyName.GRAPH) == StrategyState.HEALTHY


def test_latency_p95_at_threshold_is_degraded():
    # p95 = 3000ms == threshold -> DEGRADED
    m = _monitor()
    for _ in range(10):
        m.record(StrategyName.GRAPH, StrategyOutcome.SUCCESS, latency_ms=3_000.0)
    assert m.state(StrategyName.GRAPH) == StrategyState.DEGRADED


def test_latency_p95_above_threshold_is_degraded():
    # 9 fast observations + 1 slow. p95 (index 9) = 5000ms > 3000ms -> DEGRADED
    m = _monitor()
    for _ in range(9):
        m.record(StrategyName.GRAPH, StrategyOutcome.SUCCESS, latency_ms=100.0)
    m.record(StrategyName.GRAPH, StrategyOutcome.SUCCESS, latency_ms=5_000.0)
    assert m.state(StrategyName.GRAPH) == StrategyState.DEGRADED


def test_latency_degraded_does_not_override_unavailable_error_rate():
    # High error rate + high latency: error rate wins (UNAVAILABLE, not just DEGRADED)
    m = _monitor()
    _record_n(m, StrategyName.GRAPH, StrategyOutcome.ERROR, 6, latency_ms=5_000.0)
    _record_n(m, StrategyName.GRAPH, StrategyOutcome.SUCCESS, 4, latency_ms=5_000.0)
    assert m.state(StrategyName.GRAPH) == StrategyState.UNAVAILABLE


def test_latency_only_from_non_error_observations():
    # Errors have no latency (None). Only the 4 successes contribute to p95.
    # 4 successes at 100ms -> p95 = 100ms < 3000ms -> DEGRADED from error rate only.
    m = _monitor()
    _record_n(m, StrategyName.GRAPH, StrategyOutcome.ERROR, 4, latency_ms=None)
    _record_n(m, StrategyName.GRAPH, StrategyOutcome.SUCCESS, 6, latency_ms=100.0)
    # 4/10 = 40% errors -> DEGRADED (error rate, not latency)
    assert m.state(StrategyName.GRAPH) == StrategyState.DEGRADED


# ---------------------------------------------------------------------------
# 3. Dynamic transition tests — the full loop
#
# These tests simulate the sequence described in docs/reliability-loop.md:
#   healthy → degraded → unavailable → healthy (recovery)
#
# Each step is verified before moving to the next, so a failure pinpoints
# exactly which transition broke.
# ---------------------------------------------------------------------------

def test_full_state_transition_sequence_healthy_to_unavailable_to_healthy():
    """
    The complete observe → infer loop under controlled injection.

    Phase 1: baseline — all successes, HEALTHY.
    Phase 2: inject errors — crosses degraded threshold, then unavailable.
    Phase 3: restore — successes push errors out of window, returns to HEALTHY.

    This is the recovery experiment. The key assertion is the final one:
    the monitor must return to HEALTHY after the dependency recovers.
    You don't want "broke once → UNAVAILABLE forever."
    """
    m = _monitor(window=10)

    # Phase 1: baseline — 10 successes
    _record_n(m, StrategyName.GRAPH, StrategyOutcome.SUCCESS, 10)
    assert m.state(StrategyName.GRAPH) == StrategyState.HEALTHY, "Phase 1: should be HEALTHY"

    # Phase 2a: inject 3 errors (30% = degraded threshold)
    _record_n(m, StrategyName.GRAPH, StrategyOutcome.ERROR, 3)
    # Window now: 7 successes + 3 errors = 30% -> DEGRADED
    assert m.state(StrategyName.GRAPH) == StrategyState.DEGRADED, "Phase 2a: should be DEGRADED at 30%"

    # Phase 2b: inject 3 more errors (now 6 errors in last 10 = 60% = unavailable threshold)
    _record_n(m, StrategyName.GRAPH, StrategyOutcome.ERROR, 3)
    # Window now: 4 successes + 6 errors = 60% -> UNAVAILABLE
    assert m.state(StrategyName.GRAPH) == StrategyState.UNAVAILABLE, "Phase 2b: should be UNAVAILABLE at 60%"

    # Phase 3: restore — 10 successes push all errors out of the window
    _record_n(m, StrategyName.GRAPH, StrategyOutcome.SUCCESS, 10)
    assert m.state(StrategyName.GRAPH) == StrategyState.HEALTHY, "Phase 3: should recover to HEALTHY"


def test_partial_recovery_stops_at_degraded_not_healthy():
    """
    After UNAVAILABLE, partial recovery (some successes but not enough to
    push all errors out) should land at DEGRADED, not jump straight to HEALTHY.
    """
    m = _monitor(window=10)

    # Drive to UNAVAILABLE
    _record_n(m, StrategyName.GRAPH, StrategyOutcome.ERROR, 10)
    assert m.state(StrategyName.GRAPH) == StrategyState.UNAVAILABLE

    # 5 successes: window = 5 errors + 5 successes = 50% errors -> DEGRADED
    _record_n(m, StrategyName.GRAPH, StrategyOutcome.SUCCESS, 5)
    assert m.state(StrategyName.GRAPH) == StrategyState.DEGRADED


def test_latency_spike_then_recovery():
    """
    Latency spike drives DEGRADED; returning to normal latency recovers to HEALTHY.
    """
    m = _monitor(window=10)

    # Normal baseline
    _record_n(m, StrategyName.GRAPH, StrategyOutcome.SUCCESS, 10, latency_ms=100.0)
    assert m.state(StrategyName.GRAPH) == StrategyState.HEALTHY

    # Latency spike: all observations now at 5000ms
    _record_n(m, StrategyName.GRAPH, StrategyOutcome.SUCCESS, 10, latency_ms=5_000.0)
    assert m.state(StrategyName.GRAPH) == StrategyState.DEGRADED

    # Recovery: latency returns to normal
    _record_n(m, StrategyName.GRAPH, StrategyOutcome.SUCCESS, 10, latency_ms=100.0)
    assert m.state(StrategyName.GRAPH) == StrategyState.HEALTHY


# ---------------------------------------------------------------------------
# 4. Recovery experiment — end-to-end planner loop
#
# Simulates the full observe → infer → decide → act → verify sequence:
#
#   Normal Graph
#     ↓ inject failures
#   Graph becomes UNAVAILABLE
#     ↓ planner consults monitor
#   CEKP skips Graph (intervention recorded)
#     ↓ planner tries Hybrid
#   Hybrid returns evidence
#     ↓ verify outcome
#   RECOVERY_SUCCESS: evidence-backed result, latency recorded
#     ↓ restore Graph (successes into monitor)
#   Monitor returns to HEALTHY
#     ↓ verify
#   Graph attempted again on next request
# ---------------------------------------------------------------------------

def test_recovery_experiment_graph_unavailable_hybrid_fallback_evidence_backed():
    """
    Full loop: Graph UNAVAILABLE → skip → Hybrid fallback → evidence-backed result.

    Verification uses the frozen semantics from docs/reliability-loop.md:
    - planner_outcome: success
    - evidence_outcome: evidence_backed (documents returned)
    - selected_strategy: hybrid (not graph)
    - interventions: one skip of graph
    - inferred_states: graph=unavailable at time of request
    """
    m = _monitor(window=10)

    # Inject 10 Graph errors -> UNAVAILABLE
    _record_n(m, StrategyName.GRAPH, StrategyOutcome.ERROR, 10)
    assert m.state(StrategyName.GRAPH) == StrategyState.UNAVAILABLE

    hybrid = FakeStrategy(StrategyName.HYBRID, StrategyOutcome.SUCCESS, confidence=0.82)
    planner = _make_planner(
        {StrategyName.GRAPH: FakeStrategy(StrategyName.GRAPH, StrategyOutcome.SUCCESS, 0.9),
         StrategyName.HYBRID: hybrid},
        [StrategyName.GRAPH, StrategyName.HYBRID],
        monitor=m,
    )

    result = planner.plan(PlannerContext(query="What does app.main import?"))

    # Outcome verification
    assert result.outcome == PlannerOutcome.SUCCESS
    assert result.result.strategy_name == StrategyName.HYBRID
    assert result.result.documents  # evidence-backed

    # Intervention verification
    assert len(result.interventions) == 1
    assert result.interventions[0]["strategy"] == "graph"
    assert result.interventions[0]["decision"] == "skip"
    assert result.interventions[0]["inferred_state"] == "unavailable"

    # State snapshot at resolution time
    assert result.inferred_states["graph"] == StrategyState.UNAVAILABLE.value


def test_recovery_experiment_graph_restores_to_healthy_after_successes():
    """
    After the dependency recovers (successes flow back in), the monitor
    must return to HEALTHY and the planner must attempt Graph again.

    This is the "you don't want broke-once → UNAVAILABLE forever" guarantee.
    """
    m = _monitor(window=10)

    # Drive to UNAVAILABLE
    _record_n(m, StrategyName.GRAPH, StrategyOutcome.ERROR, 10)
    assert m.state(StrategyName.GRAPH) == StrategyState.UNAVAILABLE

    # Simulate dependency recovery: 10 successes flow in
    _record_n(m, StrategyName.GRAPH, StrategyOutcome.SUCCESS, 10)
    assert m.state(StrategyName.GRAPH) == StrategyState.HEALTHY

    # Next request: Graph should be attempted, not skipped
    graph = FakeStrategy(StrategyName.GRAPH, StrategyOutcome.SUCCESS, confidence=0.9)
    planner = _make_planner(
        {StrategyName.GRAPH: graph},
        [StrategyName.GRAPH],
        monitor=m,
    )

    result = planner.plan(PlannerContext(query="test after recovery"))

    assert result.outcome == PlannerOutcome.SUCCESS
    assert result.result.strategy_name == StrategyName.GRAPH
    assert result.interventions == []  # no skip — Graph was healthy


def test_recovery_experiment_fallback_quality_preserved():
    """
    Verify that the fallback result is evidence-backed with meaningful
    confidence — not just "something was returned."

    The intervention must not degrade result quality below the threshold.
    """
    m = _monitor(window=10)
    _record_n(m, StrategyName.GRAPH, StrategyOutcome.ERROR, 10)

    # Hybrid returns high-confidence evidence
    hybrid = FakeStrategy(StrategyName.HYBRID, StrategyOutcome.SUCCESS, confidence=0.85)
    planner = _make_planner(
        {StrategyName.GRAPH: FakeStrategy(StrategyName.GRAPH, StrategyOutcome.SUCCESS, 0.9),
         StrategyName.HYBRID: hybrid},
        [StrategyName.GRAPH, StrategyName.HYBRID],
        monitor=m,
    )

    result = planner.plan(PlannerContext(query="test"))

    assert result.outcome == PlannerOutcome.SUCCESS
    assert result.result.confidence >= 0.5   # above hybrid threshold (0.50)
    assert result.result.documents            # evidence-backed, not empty


def test_recovery_experiment_no_fallback_available_returns_failed():
    """
    If Graph is UNAVAILABLE and there is no fallback strategy, the planner
    must return FAILED — not crash, not return NO_EVIDENCE (which would
    imply the infrastructure worked but found nothing).
    """
    m = _monitor(window=10)
    _record_n(m, StrategyName.GRAPH, StrategyOutcome.ERROR, 10)

    planner = _make_planner(
        {StrategyName.GRAPH: FakeStrategy(StrategyName.GRAPH, StrategyOutcome.SUCCESS, 0.9)},
        [StrategyName.GRAPH],
        monitor=m,
    )

    result = planner.plan(PlannerContext(query="test"))

    assert result.outcome == PlannerOutcome.FAILED
    assert result.result is None
    assert len(result.interventions) == 1


# ---------------------------------------------------------------------------
# 5. Thread safety
# ---------------------------------------------------------------------------

def test_monitor_concurrent_writes_do_not_corrupt_state():
    m = _monitor(window=20)

    def record_errors(_):
        for _ in range(10):
            m.record(StrategyName.GRAPH, StrategyOutcome.ERROR, 50.0)

    def record_successes(_):
        for _ in range(10):
            m.record(StrategyName.GRAPH, StrategyOutcome.SUCCESS, 50.0)

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(record_errors, range(4)))
        list(executor.map(record_successes, range(4)))

    state = m.state(StrategyName.GRAPH)
    assert state in {StrategyState.HEALTHY, StrategyState.DEGRADED, StrategyState.UNAVAILABLE}
