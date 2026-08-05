"""
RetrievalResult: the return type every RetrievalStrategy must produce.

Frozen deliberately -- a strategy builds up documents/confidence/timing
internally, then constructs this in one shot as its return value. It
should never be mutated after construction (e.g. by the planner
appending to it mid-escalation); the planner instead builds its own
list of attempts alongside these.

`confidence` is a STRATEGY-LOCAL heuristic, not comparable across
strategies -- see docs/confidence.md.
"""
from dataclasses import dataclass, field

from app.planner.enums import StrategyName, StrategyOutcome


@dataclass(frozen=True)
class RetrievalResult:
    documents: list[dict]
    confidence: float
    strategy_name: StrategyName
    outcome: StrategyOutcome
    latency_ms: float | None = None
    reasoning: str = ""
    metadata: dict = field(default_factory=dict)
