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

    _recovery_trials: set[str] = field(default_factory=set, init=False, repr=False)
    _recovery_trials_in_flight: set[str] = field(default_factory=set, init=False, repr=False)

    def grant_recovery_trial(self, strategy: StrategyName) -> bool:
        """Permit one real retrieval trial after an external dependency probe succeeds.

        This never records a synthetic success or changes inferred health. The
        permission is single-use and only available while the strategy is
        inferred UNAVAILABLE.
        """
        key = strategy.value
        with self._lock:
            if key in self._recovery_trials or key in self._recovery_trials_in_flight:
                return False
            # Compute the unavailable threshold directly under the same lock;
            # calling state() here would attempt to reacquire this non-reentrant lock.
            observations = list(self._windows.get(key, []))
            if not observations:
                return False
            errors = sum(
                1 for item in observations
                if item.outcome == StrategyOutcome.ERROR.value
            )
            if errors / len(observations) < self.unavailable_error_rate:
                return False
            self._recovery_trials.add(key)
            return True

    def consume_recovery_trial(self, strategy: StrategyName) -> bool:
        """Atomically claim the one-shot permission for a real retrieval trial."""
        key = strategy.value
        with self._lock:
            if key not in self._recovery_trials or key in self._recovery_trials_in_flight:
                return False
            self._recovery_trials.remove(key)
            self._recovery_trials_in_flight.add(key)
            return True

    def finish_recovery_trial(self, strategy: StrategyName) -> None:
        """Release the in-flight guard; only a new dependency probe grants another trial."""
        with self._lock:
            self._recovery_trials_in_flight.discard(strategy.value)

    def snapshot(self) -> dict[str, str]:
        """Return {strategy_name: state_value} for all observed strategies."""
        with self._lock:
            keys = list(self._windows.keys())
        return {k: self.state(StrategyName(k)).value for k in keys}
