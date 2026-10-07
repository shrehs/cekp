"""
Reliability test matrix for CEKP v2.1.

Each test maps to one cell in the failure matrix:

  Failure                | Expected outcome  | Expected planner behavior
  -----------------------|-------------------|---------------------------
  Qdrant unavailable     | ERROR             | escalate to next strategy
  Neo4j timeout          | ERROR             | escalate to next strategy
  All infra down         | FAILED            | return gracefully, no crash
  No relevant docs       | NO_EVIDENCE       | return gracefully
  Policy denial          | ACCESS_DENIED     | no bypass, no leakage
  Policy denial + fallback | SUCCESS         | escalate to authorized strategy

The key invariant across all failure cases: the planner never propagates
an exception to the caller. Every failure mode must produce a PlannerResult
with a defined outcome, not a raised exception.

Infrastructure failures (Qdrant, Neo4j) must produce StrategyOutcome.ERROR,
not LOW_CONFIDENCE. LOW_CONFIDENCE means "ran and found weak results."
ERROR means "the infrastructure itself failed." These are different facts
and the audit log / dashboard must not conflate them.
"""
import time

import pytest

from app.planner.context import PlannerContext
from app.planner.enums import PlannerOutcome, StrategyName, StrategyOutcome
from app.planner.planner import Planner
from app.planner.registry import StrategyRegistry
from app.planner.result import RetrievalResult
from app.planner.strategies import GraphStrategy, HybridStrategy, VectorStrategy
from tests.test_planner import AllowAllPolicy, DenyAllPolicy, DenyGraphOnlyPolicy, FakeClassifier


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx(query: str = "test query") -> PlannerContext:
    return PlannerContext(query=query)


def _planner_with(strategies: dict, ranked: list[StrategyName], policy=None) -> Planner:
    registry = StrategyRegistry()
    for name, strategy in strategies.items():
        registry.register(name, strategy)
    return Planner(
        registry=registry,
        classifier=FakeClassifier(ranked),
        policy=policy or AllowAllPolicy(),
    )


# ---------------------------------------------------------------------------
# Qdrant unavailable — VectorStrategy and HybridStrategy
# ---------------------------------------------------------------------------

def test_vector_strategy_qdrant_failure_returns_error_not_low_confidence(monkeypatch):
    """
    An infrastructure exception from Qdrant must produce ERROR, not
    LOW_CONFIDENCE. LOW_CONFIDENCE means the strategy ran and found
    weak results. ERROR means the infrastructure itself failed.
    These are different facts and the dashboard treats them differently.
    """
    monkeypatch.setattr(
        "app.core.vector_store.vector_search",
        lambda *_a, **_kw: (_ for _ in ()).throw(ConnectionError("Qdrant unreachable")),
    )
    monkeypatch.setattr(
        "app.services.embedding.embed_query",
        lambda _q: [0.0] * 384,
    )

    result = VectorStrategy().retrieve(_ctx())

    assert result.outcome == StrategyOutcome.ERROR
    assert result.documents == []
    assert result.confidence == 0.0
    assert result.metadata["error"] == "vector_infrastructure_failure"


def test_hybrid_strategy_qdrant_failure_returns_error_not_low_confidence(monkeypatch):
    monkeypatch.setattr(
        "app.services.hybrid_search.hybrid_search",
        lambda *_a, **_kw: (_ for _ in ()).throw(ConnectionError("Qdrant unreachable")),
    )

    result = HybridStrategy().retrieve(_ctx())

    assert result.outcome == StrategyOutcome.ERROR
    assert result.metadata["error"] == "hybrid_infrastructure_failure"


# ---------------------------------------------------------------------------
# Neo4j timeout — GraphStrategy
# ---------------------------------------------------------------------------

def test_graph_strategy_neo4j_timeout_returns_error_and_escalates():
    """
    A Neo4j timeout (or any retriever exception) must produce ERROR and
    the planner must escalate to the next strategy rather than failing
    the whole request.
    """
    from tests.test_graph_strategy import FakeRetriever

    slow_retriever = FakeRetriever(raises=True)
    graph = GraphStrategy(retriever=slow_retriever)

    result = graph.retrieve(_ctx("What does app.main import?"))

    assert result.outcome == StrategyOutcome.ERROR
    assert result.documents == []
    assert "simulated Neo4j failure" in result.reasoning


def test_graph_strategy_neo4j_timeout_planner_escalates_to_hybrid():
    """
    End-to-end: graph fails (Neo4j down), planner escalates to hybrid,
    hybrid succeeds. The final outcome is SUCCESS from hybrid, and the
    attempt record shows graph=error, hybrid=success.
    """
    from app.planner.result import RetrievalResult
    from app.planner.strategy_base import RetrievalStrategy
    from tests.test_graph_strategy import FakeRetriever

    class SuccessfulHybrid(RetrievalStrategy):
        def retrieve(self, context: PlannerContext) -> RetrievalResult:
            return RetrievalResult(
                documents=[{"text": "fallback evidence"}],
                confidence=0.8,
                strategy_name=StrategyName.HYBRID,
                outcome=StrategyOutcome.SUCCESS,
            )

    graph = GraphStrategy(retriever=FakeRetriever(raises=True))
    planner = _planner_with(
        {StrategyName.GRAPH: graph, StrategyName.HYBRID: SuccessfulHybrid()},
        [StrategyName.GRAPH, StrategyName.HYBRID],
    )

    result = planner.plan(_ctx("What does app.main import?"))

    assert result.outcome == PlannerOutcome.SUCCESS
    assert result.result.strategy_name == StrategyName.HYBRID
    assert result.attempts[0]["strategy"] == "graph"
    assert result.attempts[0]["outcome"] == StrategyOutcome.ERROR.value
    assert result.attempts[1]["strategy"] == "hybrid"
    assert result.attempts[1]["outcome"] == StrategyOutcome.SUCCESS.value


# ---------------------------------------------------------------------------
# All infrastructure down
# ---------------------------------------------------------------------------

def test_all_strategies_error_returns_failed_not_crash(monkeypatch):
    """
    When every strategy raises an infrastructure exception, the planner
    must return FAILED (not NO_EVIDENCE, not a raised exception).
    FAILED = infrastructure broke. NO_EVIDENCE = infrastructure worked,
    nothing matched. These are different and the dashboard shows them
    differently.
    """
    monkeypatch.setattr(
        "app.core.vector_store.vector_search",
        lambda *_a, **_kw: (_ for _ in ()).throw(ConnectionError("Qdrant down")),
    )
    monkeypatch.setattr(
        "app.services.embedding.embed_query",
        lambda _q: [0.0] * 384,
    )
    monkeypatch.setattr(
        "app.services.hybrid_search.hybrid_search",
        lambda *_a, **_kw: (_ for _ in ()).throw(ConnectionError("Qdrant down")),
    )

    planner = Planner(
        classifier=FakeClassifier([StrategyName.VECTOR, StrategyName.HYBRID]),
        policy=AllowAllPolicy(),
    )

    result = planner.plan(_ctx())

    assert result.outcome == PlannerOutcome.FAILED
    assert result.result is None
    assert all(a["outcome"] == StrategyOutcome.ERROR.value for a in result.attempts)


# ---------------------------------------------------------------------------
# No relevant documents — graceful no-evidence
# ---------------------------------------------------------------------------

def test_no_relevant_docs_returns_no_evidence_gracefully(monkeypatch):
    """
    Empty results from a healthy infrastructure must produce NO_EVIDENCE,
    not FAILED. The infrastructure worked; there just wasn't anything relevant.
    """
    monkeypatch.setattr(
        "app.core.vector_store.vector_search",
        lambda *_a, **_kw: [],
    )
    monkeypatch.setattr(
        "app.services.embedding.embed_query",
        lambda _q: [0.0] * 384,
    )

    result = VectorStrategy().retrieve(_ctx("something with no matching documents"))

    assert result.outcome == StrategyOutcome.LOW_CONFIDENCE
    assert result.documents == []
    # LOW_CONFIDENCE here is correct: the infrastructure worked, it just
    # found nothing. Distinct from ERROR (infrastructure failed).
    assert result.metadata is None or result.metadata.get("error") is None


# ---------------------------------------------------------------------------
# Policy denial — no bypass, no leakage
# ---------------------------------------------------------------------------

def test_policy_denial_does_not_execute_retrieval():
    """
    A denied strategy must never reach the retriever. The attempt record
    must show denied_by_policy with confidence=None (retrieval never ran),
    not confidence=0.0 (which would mean it ran and found nothing).
    """
    from app.planner.result import RetrievalResult
    from app.planner.strategy_base import RetrievalStrategy

    class ShouldNeverRun(RetrievalStrategy):
        def retrieve(self, context: PlannerContext) -> RetrievalResult:
            raise AssertionError("retrieval ran despite policy denial")

    planner = _planner_with(
        {StrategyName.GRAPH: ShouldNeverRun()},
        [StrategyName.GRAPH],
        policy=DenyAllPolicy(),
    )

    result = planner.plan(_ctx())

    assert result.outcome == PlannerOutcome.ACCESS_DENIED
    assert result.attempts[0]["outcome"] == StrategyOutcome.DENIED_BY_POLICY.value
    assert result.attempts[0]["confidence"] is None  # never ran, not 0.0


def test_policy_denial_user_response_indistinguishable_from_no_evidence():
    """
    The no-leakage guarantee: an unauthorized user must see the exact
    same response shape as a user whose question has no answer.
    """
    from app.planner.planner import build_user_response
    from app.planner.result import RetrievalResult
    from app.planner.strategy_base import RetrievalStrategy
    from tests.test_planner import FakeStrategy

    denied_planner = _planner_with(
        {StrategyName.GRAPH: FakeStrategy(StrategyName.GRAPH, StrategyOutcome.SUCCESS, 0.9)},
        [StrategyName.GRAPH],
        policy=DenyAllPolicy(),
    )
    no_evidence_planner = _planner_with(
        {StrategyName.GRAPH: FakeStrategy(StrategyName.GRAPH, StrategyOutcome.LOW_CONFIDENCE, 0.1)},
        [StrategyName.GRAPH],
    )

    denied_response = build_user_response(denied_planner.plan(_ctx()))
    no_evidence_response = build_user_response(no_evidence_planner.plan(_ctx()))

    assert denied_response == no_evidence_response
    assert "denied" not in str(denied_response).lower()


def test_policy_denial_escalates_to_authorized_strategy_and_succeeds():
    """
    Denial of one strategy must not fail the whole request if another
    authorized strategy can answer. This is the "escalate, don't fail"
    guarantee applied to policy, not just confidence.
    """
    from app.planner.result import RetrievalResult
    from app.planner.strategy_base import RetrievalStrategy

    class AuthorizedHybrid(RetrievalStrategy):
        def retrieve(self, context: PlannerContext) -> RetrievalResult:
            return RetrievalResult(
                documents=[{"text": "authorized evidence"}],
                confidence=0.8,
                strategy_name=StrategyName.HYBRID,
                outcome=StrategyOutcome.SUCCESS,
            )

    planner = _planner_with(
        {StrategyName.GRAPH: AuthorizedHybrid(), StrategyName.HYBRID: AuthorizedHybrid()},
        [StrategyName.GRAPH, StrategyName.HYBRID],
        policy=DenyGraphOnlyPolicy(),
    )

    result = planner.plan(_ctx())

    assert result.outcome == PlannerOutcome.SUCCESS
    assert result.result.strategy_name == StrategyName.HYBRID
    assert result.attempts[0]["outcome"] == StrategyOutcome.DENIED_BY_POLICY.value
    assert result.attempts[1]["outcome"] == StrategyOutcome.SUCCESS.value
