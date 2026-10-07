"""
StrategyHealthMonitor: infers operating state for each retrieval strategy
from a sliding window of recent observations.

Design constraints:
- Deterministic rules only. No LLM, no ML, no Prometheus queries.
- Thread-safe: the planner runs under concurrent load (see test_observability.py).
- Stateless across restarts: the window is in-process memory. A fresh
  process starts every strategy as HEALTHY and learns from live traffic.
  This is intentional -- persisting state across restarts adds complexity
  that isn't justified until the window size and thresholds are validated
  against real traffic patterns.

State transitions (derived from the last `window` observations):

  error_rate >= UNAVAILABLE_ERROR_RATE  ->  UNAVAILABLE
  error_rate >= DEGRADED_ERROR_RATE     ->  DEGRADED
  p95_latency_ms >= DEGRADED_LATENCY_MS ->  DEGRADED  (even if error rate is low)
  otherwise                             ->  HEALTHY

"Error" means StrategyOutcome.ERROR (infrastructure failure). LOW_CONFIDENCE
and NOT_IMPLEMENTED are not errors -- they mean the strategy ran and found
nothing, which is expected behaviour, not a health signal.

The monitor is consulted by the planner BEFORE running a strategy. If the
inferred state is UNAVAILABLE, the planner skips the strategy immediately
and records the intervention in the attempt trace. This makes the skip
visible and auditable rather than silent.
"""
import math
import threading
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from app.planner.enums import StrategyName, StrategyOutcome, StrategyState

# ---------------------------------------------------------------------------
# Thresholds -- single place, easy to tune or move to config later
# ---------------------------------------------------------------------------

_WINDOW = 10           # number of recent attempts to consider
_DEGRADED_ERROR_RATE = 0.3    # >= 30% errors in window -> DEGRADED
_UNAVAILABLE_ERROR_RATE = 0.6  # >= 60% errors in window -> UNAVAILABLE
_DEGRADED_LATENCY_MS = 3_000  # p95 >= 3s -> DEGRADED (even with low error rate)

class ObservationSource(str, Enum):
    RETRIEVAL = "retrieval"
    HEALTH_PROBE = "health_probe"

@dataclass
class _Observation:
    outcome: str        # StrategyOutcome.value
    latency_ms: float | None
    source: ObservationSource = ObservationSource.RETRIEVAL


@dataclass
class StrategyHealthMonitor:
    """
    One instance shared across the lifetime of a Planner. Holds a
    sliding window of observations per strategy and derives state on
    demand. All public methods are thread-safe.
    """
    window: int = _WINDOW
    degraded_error_rate: float = _DEGRADED_ERROR_RATE
    unavailable_error_rate: float = _UNAVAILABLE_ERROR_RATE
    degraded_latency_ms: float = _DEGRADED_LATENCY_MS

    _windows: dict[str, deque] = field(default_factory=dict, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def record(
        self,
        strategy: StrategyName,
        outcome: StrategyOutcome,
        latency_ms: float | None,
        source: ObservationSource = ObservationSource.RETRIEVAL,
    ) -> None:
        """Record an observation into the sliding window."""
        key = strategy.value

        with self._lock:
            if key not in self._windows:
                self._windows[key] = deque(maxlen=self.window)

            self._windows[key].append(
                _Observation(
                    outcome=outcome.value,
                    latency_ms=latency_ms,
                    source=source,
                )
            )

    def state(self, strategy: StrategyName) -> StrategyState:
        """
        Derive the current inferred state from the sliding window.
        Returns HEALTHY if there are no observations yet (fresh start).
        """
        key = strategy.value
        with self._lock:
            observations = list(self._windows.get(key, []))

        if not observations:
            return StrategyState.HEALTHY

        error_count = sum(
            1 for o in observations
            if o.outcome == StrategyOutcome.ERROR.value
        )
        error_rate = error_count / len(observations)

        if error_rate >= self.unavailable_error_rate:
            return StrategyState.UNAVAILABLE

        if error_rate >= self.degraded_error_rate:
            return StrategyState.DEGRADED

        latencies = [o.latency_ms for o in observations if o.latency_ms is not None]
        if latencies:
            latencies.sort()
            # ceil-based index: for n observations, p95 = observation at
            # index ceil(0.95 * n) - 1. This gives the correct upper-bound
            # percentile for small windows (e.g. n=5: ceil(4.75)-1 = 4,
            # the highest value, which is the right conservative choice).
            p95_index = min(math.ceil(0.95 * len(latencies)) - 1, len(latencies) - 1)
            p95 = latencies[p95_index]
            if p95 >= self.degraded_latency_ms:
                return StrategyState.DEGRADED

        return StrategyState.HEALTHY

    # def probe_healthy(self, strategy: StrategyName, n: int = 1) -> None:
        """
        Record n synthetic SUCCESS observations for a strategy.

        Used by health-check probes to break the recovery deadlock:
        when a strategy is UNAVAILABLE, the planner skips it, so no
        real observations flow in and the window never ages out.
        A probe confirms the dependency is reachable and seeds the
        window with successes so the monitor can transition back to
        HEALTHY or DEGRADED on the next real request.

        Only call this after independently confirming the dependency
        is reachable (e.g. a direct Neo4j RETURN 1 check).
        """
        # for _ in range(n):
        #     self.record(strategy, StrategyOutcome.SUCCESS, latency_ms=0.0)

    def snapshot(self) -> dict[str, str]:
        """Return {strategy_name: state_value} for all observed strategies."""
        with self._lock:
            keys = list(self._windows.keys())
        return {k: self.state(StrategyName(k)).value for k in keys}
