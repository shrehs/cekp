"""
Enums for the Adaptive Retrieval Planner (architecture-v1).

Two outcome enums exist at two different layers, deliberately:

- StrategyOutcome: what happened when ONE strategy was tried.
- PlannerOutcome: what the PLANNER ultimately decided for the whole
  request, after possibly trying several strategies in sequence.

A strategy can SUCCEED while the planner still doesn't return that
result (e.g. a downstream policy conflict); keeping these separate
avoids overloading one enum for two different jobs.
"""
from enum import Enum


class StrategyName(str, Enum):
    VECTOR = "vector"
    HYBRID = "hybrid"
    GRAPH = "graph"
    AGENTIC = "agentic"


class StrategyOutcome(str, Enum):
    SUCCESS = "success"
    LOW_CONFIDENCE = "low_confidence"
    DENIED_BY_POLICY = "denied_by_policy"
    NOT_IMPLEMENTED = "not_implemented"
    ERROR = "error"


class PlannerOutcome(str, Enum):
    SUCCESS = "success"
    NO_EVIDENCE = "no_evidence"
    ACCESS_DENIED = "access_denied"
    FAILED = "failed"
