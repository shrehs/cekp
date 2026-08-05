"""
StrategyRegistry: maps StrategyName -> RetrievalStrategy instance.

Uses .get() with a graceful default rather than direct indexing, so
a missing registration doesn't crash the planner -- it's treated the
same as NOT_IMPLEMENTED and the planner moves on to the next ranked
strategy.
"""
from app.planner.enums import StrategyName
from app.planner.strategies import (
    AgenticStrategy,
    GraphStrategy,
    HybridStrategy,
    VectorStrategy,
)
from app.planner.strategy_base import RetrievalStrategy


class StrategyRegistry:
    def __init__(self):
        self._strategies: dict[StrategyName, RetrievalStrategy] = {}

    def register(self, name: StrategyName, strategy: RetrievalStrategy) -> None:
        self._strategies[name] = strategy

    def get(self, name: StrategyName) -> RetrievalStrategy | None:
        return self._strategies.get(name)


def build_default_registry() -> StrategyRegistry:
    registry = StrategyRegistry()
    registry.register(StrategyName.VECTOR, VectorStrategy())
    registry.register(StrategyName.HYBRID, HybridStrategy())
    registry.register(StrategyName.GRAPH, GraphStrategy())
    registry.register(StrategyName.AGENTIC, AgenticStrategy())
    return registry
