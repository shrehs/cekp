"""
RetrievalStrategy: the interface every retrieval strategy implements.

Every strategy, including GraphStrategy (currently a stub), satisfies
this exact contract -- that's what makes the planner able to escalate
through a ranked list without knowing which concrete strategy it's
calling.
"""
from abc import ABC, abstractmethod

from app.planner.context import PlannerContext
from app.planner.result import RetrievalResult


class RetrievalStrategy(ABC):
    @abstractmethod
    def retrieve(self, context: PlannerContext) -> RetrievalResult:
        """
        Execute this strategy for the given context and return a
        RetrievalResult. Must never raise for the "no results found"
        case -- that's LOW_CONFIDENCE or NOT_IMPLEMENTED, not an
        exception. Only raise for genuine infrastructure errors, and
        even then the planner will catch it and record StrategyOutcome.ERROR.
        """
        raise NotImplementedError
