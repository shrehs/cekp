"""
PlannerConfig: named, per-strategy confidence thresholds.

Confidence is NOT comparable across strategies (docs/confidence.md),
so each strategy gets its own threshold rather than one global cutoff.
These are plain constants in v1; the values live in one place so they
can move to env vars / a config file / a feature-flag service later
without touching planner logic.
"""
from dataclasses import dataclass

from app.planner.enums import StrategyName


@dataclass(frozen=True)
class PlannerConfig:
    thresholds: dict[StrategyName, float]
    max_escalations: int = 4

    def threshold_for(self, strategy_name: StrategyName) -> float:
        return self.thresholds.get(strategy_name, 0.5)


DEFAULT_PLANNER_CONFIG = PlannerConfig(
    thresholds={
        StrategyName.VECTOR: 0.55,
        StrategyName.HYBRID: 0.50,
        StrategyName.GRAPH: 0.60,
        StrategyName.AGENTIC: 0.45,
    },
    max_escalations=4,
)
