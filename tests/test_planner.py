from app.planner.config import PlannerConfig
from app.planner.context import PlannerContext
from app.planner.enums import PlannerOutcome, StrategyName, StrategyOutcome
from app.planner.planner import Planner, build_trace_response, build_user_response
from app.planner.policy_evaluator import PolicyEvaluator
from app.planner.registry import StrategyRegistry
from app.planner.result import RetrievalResult
from app.planner.strategy_base import RetrievalStrategy
from app.planner.strategies import VectorStrategy


class FakeStrategy(RetrievalStrategy):
    """Test double: returns a fixed RetrievalResult, or raises if configured to."""

    def __init__(
        self, name: StrategyName, outcome: StrategyOutcome, confidence: float, raises: bool = False,
        latency_ms: float | None = None, metadata: dict | None = None,
    ):
        self.name = name
        self.outcome = outcome
        self.confidence = confidence
        self.raises = raises
        self.latency_ms = latency_ms
        self.metadata = metadata or {}

    def retrieve(self, context: PlannerContext) -> RetrievalResult:
        if self.raises:
            raise RuntimeError("simulated infrastructure failure")
        docs = [{"text": "fake"}] if self.outcome == StrategyOutcome.SUCCESS else []
        return RetrievalResult(
            documents=docs,
            confidence=self.confidence,
            strategy_name=self.name,
            outcome=self.outcome,
            latency_ms=self.latency_ms,
            metadata=self.metadata,
        )


class FakeClassifier:
    def __init__(self, ranked: list[StrategyName]):
        self.ranked = ranked

    def classify(self, context: PlannerContext) -> list[StrategyName]:
        return self.ranked


class AllowAllPolicy(PolicyEvaluator):
    def is_authorized(self, strategy_name, context):
        return True


class DenyAllPolicy(PolicyEvaluator):
    def is_authorized(self, strategy_name, context):
        return False


class DenyGraphOnlyPolicy(PolicyEvaluator):
    def is_authorized(self, strategy_name, context):
        return strategy_name != StrategyName.GRAPH


def _ctx() -> PlannerContext:
    return PlannerContext(query="does this matter")


def _make_planner(strategies: dict, ranked: list[StrategyName], policy=None) -> Planner:
    registry = StrategyRegistry()
    for name, strategy in strategies.items():
        registry.register(name, strategy)
    return Planner(
        registry=registry,
        classifier=FakeClassifier(ranked),
        policy=policy or AllowAllPolicy(),
    )


def test_first_strategy_succeeds():
    hybrid = FakeStrategy(StrategyName.HYBRID, StrategyOutcome.SUCCESS, confidence=0.9)
    planner = _make_planner({StrategyName.HYBRID: hybrid}, [StrategyName.HYBRID])

    result = planner.plan(_ctx())

    assert result.outcome == PlannerOutcome.SUCCESS
    assert result.result.strategy_name == StrategyName.HYBRID
    assert result.attempts == [
        {
            "strategy": "hybrid", "outcome": "success", "confidence": 0.9,
            "cleared_threshold": True, "latency_ms": None, "metadata": None,
        }
    ]


def test_second_strategy_succeeds_after_first_is_low_confidence():
    graph = FakeStrategy(StrategyName.GRAPH, StrategyOutcome.LOW_CONFIDENCE, confidence=0.1)
    hybrid = FakeStrategy(StrategyName.HYBRID, StrategyOutcome.SUCCESS, confidence=0.9)
    planner = _make_planner(
        {StrategyName.GRAPH: graph, StrategyName.HYBRID: hybrid},
        [StrategyName.GRAPH, StrategyName.HYBRID],
    )

    result = planner.plan(_ctx())

    assert result.outcome == PlannerOutcome.SUCCESS
    assert result.result.strategy_name == StrategyName.HYBRID
    assert len(result.attempts) == 2
    assert result.attempts[0]["outcome"] == "low_confidence"
    assert result.attempts[1]["outcome"] == "success"


def test_all_strategies_fail_returns_no_evidence():
    graph = FakeStrategy(StrategyName.GRAPH, StrategyOutcome.LOW_CONFIDENCE, confidence=0.1)
    hybrid = FakeStrategy(StrategyName.HYBRID, StrategyOutcome.LOW_CONFIDENCE, confidence=0.2)
    planner = _make_planner(
        {StrategyName.GRAPH: graph, StrategyName.HYBRID: hybrid},
        [StrategyName.GRAPH, StrategyName.HYBRID],
    )

    result = planner.plan(_ctx())

    assert result.outcome == PlannerOutcome.NO_EVIDENCE
    assert result.result is None


def test_empty_ranked_list_returns_no_evidence_not_a_crash():
    planner = _make_planner({}, [])
    result = planner.plan(_ctx())

    assert result.outcome == PlannerOutcome.NO_EVIDENCE
    assert result.result is None
    assert result.attempts == []


def test_registry_missing_strategy_records_not_implemented_and_continues():
    hybrid = FakeStrategy(StrategyName.HYBRID, StrategyOutcome.SUCCESS, confidence=0.9)
    # GRAPH is ranked first but never registered
    planner = _make_planner({StrategyName.HYBRID: hybrid}, [StrategyName.GRAPH, StrategyName.HYBRID])

    result = planner.plan(_ctx())

    assert result.outcome == PlannerOutcome.SUCCESS
    assert result.attempts[0] == {
        "strategy": "graph",
        "outcome": "not_implemented",
        "confidence": None,
        "cleared_threshold": None,
        "latency_ms": None,
        "metadata": None,
    }
    assert result.result.strategy_name == StrategyName.HYBRID


def test_confidence_is_none_when_never_invoked_vs_zero_when_actually_returned():
    """
    A strategy that never ran (denied/missing) should record confidence=None,
    distinct from a strategy that ran and genuinely returned confidence=0.0
    (e.g. the real GraphStrategy stub before Neo4j exists).
    """
    zero_conf_graph = FakeStrategy(StrategyName.GRAPH, StrategyOutcome.NOT_IMPLEMENTED, confidence=0.0)
    hybrid = FakeStrategy(StrategyName.HYBRID, StrategyOutcome.SUCCESS, confidence=0.9)
    planner = _make_planner(
        {StrategyName.GRAPH: zero_conf_graph, StrategyName.HYBRID: hybrid},
        [StrategyName.GRAPH, StrategyName.HYBRID],
    )

    result = planner.plan(_ctx())

    # Graph actually ran and returned 0.0 -- confidence should be 0.0, not None.
    assert result.attempts[0]["confidence"] == 0.0

    # Now compare against a registry miss, where Graph never ran at all.
    planner_missing = _make_planner({StrategyName.HYBRID: hybrid}, [StrategyName.GRAPH, StrategyName.HYBRID])
    result_missing = planner_missing.plan(_ctx())
    assert result_missing.attempts[0]["confidence"] is None


def test_ranked_strategies_propagated_to_result():
    hybrid = FakeStrategy(StrategyName.HYBRID, StrategyOutcome.SUCCESS, confidence=0.9)
    planner = _make_planner(
        {StrategyName.GRAPH: FakeStrategy(StrategyName.GRAPH, StrategyOutcome.LOW_CONFIDENCE, 0.1),
         StrategyName.HYBRID: hybrid},
        [StrategyName.GRAPH, StrategyName.HYBRID],
    )

    result = planner.plan(_ctx())

    assert result.ranked_strategies == ["graph", "hybrid"]


def test_trace_response_shows_access_denied_plainly_unlike_user_response():
    graph = FakeStrategy(StrategyName.GRAPH, StrategyOutcome.SUCCESS, confidence=0.9)
    planner = _make_planner({StrategyName.GRAPH: graph}, [StrategyName.GRAPH], policy=DenyAllPolicy())

    planner_result = planner.plan(_ctx())

    trace = build_trace_response(planner_result)
    user_response = build_user_response(planner_result)

    assert trace["planner_outcome"] == "access_denied"
    assert trace["trace_version"] == "2"
    assert trace["evidence_outcome"] == "no_evidence"
    assert trace["policy_outcome"] == "denied"
    assert trace["selected_strategy"] is None
    assert trace["attempts"][0]["outcome"] == "denied_by_policy"
    # But the user-facing response never says so:
    assert user_response["answer_available"] is False
    assert "denied" not in user_response.get("message", "").lower()


def test_strategy_exception_is_caught_and_recorded_as_error():
    broken = FakeStrategy(StrategyName.HYBRID, StrategyOutcome.SUCCESS, confidence=0.9, raises=True)
    vector = FakeStrategy(StrategyName.VECTOR, StrategyOutcome.SUCCESS, confidence=0.7)
    planner = _make_planner(
        {StrategyName.HYBRID: broken, StrategyName.VECTOR: vector},
        [StrategyName.HYBRID, StrategyName.VECTOR],
    )

    result = planner.plan(_ctx())

    assert result.attempts[0]["outcome"] == "error"
    assert result.outcome == PlannerOutcome.SUCCESS
    assert result.result.strategy_name == StrategyName.VECTOR


def test_vector_strategy_returns_error_when_qdrant_is_unreachable(monkeypatch):
    def boom(_query):
        raise ConnectionError("[Errno 11001] getaddrinfo failed")

    monkeypatch.setattr("app.services.embedding.embed_query", boom)
    monkeypatch.setattr("app.core.vector_store.vector_search", lambda *_args, **_kwargs: (_ for _ in ()).throw(ConnectionError("[Errno 11001] getaddrinfo failed")))

    result = VectorStrategy().retrieve(_ctx())

    assert result.outcome == StrategyOutcome.ERROR
    assert result.documents == []
    assert result.confidence == 0.0


def test_policy_denial_escalates_to_next_authorized_strategy():
    graph = FakeStrategy(StrategyName.GRAPH, StrategyOutcome.SUCCESS, confidence=0.9)
    hybrid = FakeStrategy(StrategyName.HYBRID, StrategyOutcome.SUCCESS, confidence=0.8)
    planner = _make_planner(
        {StrategyName.GRAPH: graph, StrategyName.HYBRID: hybrid},
        [StrategyName.GRAPH, StrategyName.HYBRID],
        policy=DenyGraphOnlyPolicy(),
    )

    result = planner.plan(_ctx())

    assert result.outcome == PlannerOutcome.SUCCESS
    assert result.result.strategy_name == StrategyName.HYBRID
    assert result.attempts[0] == {
        "strategy": "graph",
        "outcome": "denied_by_policy",
        "confidence": None,
        "cleared_threshold": None,
        "latency_ms": None,
        "metadata": None,
    }


def test_all_strategies_denied_by_policy_returns_access_denied():
    graph = FakeStrategy(StrategyName.GRAPH, StrategyOutcome.SUCCESS, confidence=0.9)
    hybrid = FakeStrategy(StrategyName.HYBRID, StrategyOutcome.SUCCESS, confidence=0.9)
    planner = _make_planner(
        {StrategyName.GRAPH: graph, StrategyName.HYBRID: hybrid},
        [StrategyName.GRAPH, StrategyName.HYBRID],
        policy=DenyAllPolicy(),
    )

    result = planner.plan(_ctx())

    assert result.outcome == PlannerOutcome.ACCESS_DENIED
    assert all(a["outcome"] == "denied_by_policy" for a in result.attempts)


def test_access_denied_and_no_evidence_render_identically_to_the_user():
    """
    The core no-leakage guarantee: an unauthorized user and a user whose
    question genuinely has no answer must see the exact same response shape.
    """
    graph = FakeStrategy(StrategyName.GRAPH, StrategyOutcome.SUCCESS, confidence=0.9)
    denied_planner = _make_planner(
        {StrategyName.GRAPH: graph}, [StrategyName.GRAPH], policy=DenyAllPolicy()
    )
    no_evidence_planner = _make_planner(
        {StrategyName.GRAPH: FakeStrategy(StrategyName.GRAPH, StrategyOutcome.LOW_CONFIDENCE, confidence=0.1)},
        [StrategyName.GRAPH],
    )

    denied_response = build_user_response(denied_planner.plan(_ctx()))
    no_evidence_response = build_user_response(no_evidence_planner.plan(_ctx()))

    assert denied_response == no_evidence_response


def test_escalation_respects_max_escalations_cap():
    strategies = {
        StrategyName.GRAPH: FakeStrategy(StrategyName.GRAPH, StrategyOutcome.LOW_CONFIDENCE, 0.1),
        StrategyName.HYBRID: FakeStrategy(StrategyName.HYBRID, StrategyOutcome.LOW_CONFIDENCE, 0.1),
        StrategyName.VECTOR: FakeStrategy(StrategyName.VECTOR, StrategyOutcome.LOW_CONFIDENCE, 0.1),
        StrategyName.AGENTIC: FakeStrategy(StrategyName.AGENTIC, StrategyOutcome.SUCCESS, 0.9),
    }
    # AGENTIC would succeed, but it's 5th in a list where max_escalations=4 (default),
    # so it should never be tried if placed beyond the cap.
    ranked = [StrategyName.GRAPH, StrategyName.HYBRID, StrategyName.VECTOR, StrategyName.GRAPH, StrategyName.AGENTIC]
    planner = _make_planner(strategies, ranked)

    result = planner.plan(_ctx())

    assert len(result.attempts) == 4  # capped, AGENTIC never attempted
    assert result.outcome == PlannerOutcome.NO_EVIDENCE


def test_threshold_of_one_escalates_through_everything_and_still_terminates():
    """
    Chaos test: an impossible-to-clear threshold (1.0) should not cause
    an infinite loop or a crash -- every strategy is tried once, in
    order, then the planner terminates with NO_EVIDENCE.
    """
    impossible_config = PlannerConfig(
        thresholds={name: 1.0 for name in StrategyName},
        max_escalations=4,
    )
    strategies = {
        StrategyName.GRAPH: FakeStrategy(StrategyName.GRAPH, StrategyOutcome.SUCCESS, confidence=0.95),
        StrategyName.HYBRID: FakeStrategy(StrategyName.HYBRID, StrategyOutcome.SUCCESS, confidence=0.99),
        StrategyName.VECTOR: FakeStrategy(StrategyName.VECTOR, StrategyOutcome.SUCCESS, confidence=0.90),
    }
    registry = StrategyRegistry()
    for name, strategy in strategies.items():
        registry.register(name, strategy)

    planner = Planner(
        registry=registry,
        classifier=FakeClassifier([StrategyName.GRAPH, StrategyName.HYBRID, StrategyName.VECTOR]),
        policy=AllowAllPolicy(),
        config=impossible_config,
    )

    result = planner.plan(_ctx())

    # Terminates cleanly rather than looping -- every strategy tried exactly once.
    assert len(result.attempts) == 3
    assert result.outcome == PlannerOutcome.NO_EVIDENCE
    assert result.result is None
    # Confirm every one of them actually ran and "succeeded" at the strategy
    # level, just never cleared the impossible planner-level threshold.
    assert all(a["outcome"] == "success" for a in result.attempts)


def test_completely_empty_registry_does_not_crash():
    """
    Chaos test: not just one missing strategy, but a registry with zero
    registrations at all. Every ranked strategy should come back
    NOT_IMPLEMENTED, and the planner should still terminate cleanly.
    """
    empty_registry = StrategyRegistry()
    planner = Planner(
        registry=empty_registry,
        classifier=FakeClassifier([StrategyName.GRAPH, StrategyName.HYBRID, StrategyName.VECTOR]),
        policy=AllowAllPolicy(),
    )

    result = planner.plan(_ctx())

    assert len(result.attempts) == 3
    assert all(a["outcome"] == "not_implemented" and a["confidence"] is None for a in result.attempts)
    assert result.outcome == PlannerOutcome.NO_EVIDENCE
    assert result.result is None


def test_success_below_threshold_does_not_terminate_and_is_marked_clearly():
    """
    Regression test for the exact scenario found during integration
    validation: a strategy can return StrategyOutcome.SUCCESS (it found
    something) while its confidence is still below the planner's
    threshold for that strategy. The planner must NOT treat this as a
    final answer -- but the attempt record must also not look like a
    plain unqualified "success", or the trace becomes self-contradictory
    (an attempt says success while planner_outcome says no_evidence).
    """
    low_conf_vector = FakeStrategy(StrategyName.VECTOR, StrategyOutcome.SUCCESS, confidence=0.38)
    planner = _make_planner({StrategyName.VECTOR: low_conf_vector}, [StrategyName.VECTOR])
    # Default VECTOR threshold is 0.55 (see PlannerConfig.DEFAULT_PLANNER_CONFIG)

    result = planner.plan(_ctx())

    assert result.outcome == PlannerOutcome.NO_EVIDENCE
    assert result.result is None
    assert result.attempts[0]["outcome"] == "success"          # strategy-level: it did find something
    assert result.attempts[0]["cleared_threshold"] is False     # planner-level: not good enough to use
    assert result.attempts[0]["confidence"] == 0.38


def test_success_above_threshold_is_marked_cleared_and_terminates():
    high_conf_vector = FakeStrategy(StrategyName.VECTOR, StrategyOutcome.SUCCESS, confidence=0.9)
    planner = _make_planner({StrategyName.VECTOR: high_conf_vector}, [StrategyName.VECTOR])

    result = planner.plan(_ctx())

    assert result.outcome == PlannerOutcome.SUCCESS
    assert result.attempts[0]["cleared_threshold"] is True


def test_numpy_confidence_is_cast_to_native_types_not_left_as_numpy_scalars():
    """
    Regression test for the exact integration-validation bug: a strategy
    that leaks a numpy.float64 confidence (as HybridStrategy did, via
    rank_bm25.get_scores() returning a numpy array) must not produce a
    numpy.bool_ in cleared_threshold -- numpy.float64 subclasses Python's
    float (so it silently "works" almost everywhere, including
    json.dumps), but numpy.bool_ does NOT subclass bool, and broke JSON
    serialization specifically at the audit-log write.

    This test constructs a genuine numpy.float64 confidence (not a
    simulation) to prove the planner's defensive cast actually converts
    it, independent of the source-level fix already applied in
    hybrid_search.py.
    """
    import json

    import numpy as np

    numpy_confidence = np.float64(0.9)  # deliberately NOT pre-cast, simulating the leak
    assert type(numpy_confidence) is np.float64  # confirm it's genuinely numpy, not a plain float
    assert isinstance(numpy_confidence, float)    # ...even though it subclasses float (part of why the bug was subtle)

    leaky_strategy = FakeStrategy(StrategyName.HYBRID, StrategyOutcome.SUCCESS, confidence=numpy_confidence)
    planner = _make_planner({StrategyName.HYBRID: leaky_strategy}, [StrategyName.HYBRID])

    result = planner.plan(_ctx())

    recorded_confidence = result.attempts[0]["confidence"]
    recorded_cleared = result.attempts[0]["cleared_threshold"]

    assert type(recorded_confidence) is float, f"expected native float, got {type(recorded_confidence)}"
    assert type(recorded_cleared) is bool, f"expected native bool, got {type(recorded_cleared)}"

    # The actual failure mode from the traceback: this must not raise.
    json.dumps(result.attempts)


def test_planner_level_regression_real_classifier_routes_code_structure_query_to_graph():
    """
    Planner-level regression test, not just an intent-classifier-level
    one -- uses the REAL IntentClassifier (not FakeClassifier), so a
    future change to classifier patterns that accidentally stops
    routing code-structure questions to GRAPH will fail here, not just
    in test_intent_classifier.py. GraphStrategy itself is still faked
    (real one doesn't exist yet), since this test is about routing,
    not about graph retrieval correctness.
    """
    from app.planner.intent_classifier import IntentClassifier

    graph_stub = FakeStrategy(StrategyName.GRAPH, StrategyOutcome.NOT_IMPLEMENTED, confidence=0.0)
    vector = FakeStrategy(StrategyName.VECTOR, StrategyOutcome.SUCCESS, confidence=0.9)
    registry = StrategyRegistry()
    registry.register(StrategyName.GRAPH, graph_stub)
    registry.register(StrategyName.VECTOR, vector)

    planner = Planner(registry=registry, classifier=IntentClassifier(), policy=AllowAllPolicy())

    result = planner.plan(PlannerContext(query="Which functions are defined in requests/sessions.py?"))

    # Real classifier behavior for this query: GRAPH matches, HYBRID/AGENTIC
    # patterns don't, so ranked_strategies is [graph, vector] -- HYBRID is
    # only appended when NOTHING matches, not as a general second choice.
    assert result.ranked_strategies == ["graph", "vector"]
    assert result.attempts[0]["outcome"] == "not_implemented"  # honest: real GraphStrategy isn't built yet
    assert result.outcome == PlannerOutcome.SUCCESS
    assert result.result.strategy_name == StrategyName.VECTOR  # falls through correctly


def test_latency_and_metadata_are_threaded_through_to_the_attempt():
    """
    Regression test: RetrievalResult.latency_ms/metadata were computed
    by every strategy but never actually surfaced into attempts[] --
    fixed alongside adding a latency baseline to /query/trace. This
    confirms the positive case (a strategy that DOES set them), not
    just that the None-default cases still pass.
    """
    strategy = FakeStrategy(
        StrategyName.HYBRID, StrategyOutcome.SUCCESS, confidence=0.9,
        latency_ms=12.5, metadata={"classification_ms": 1.0, "retrieval_ms": 10.0},
    )
    planner = _make_planner({StrategyName.HYBRID: strategy}, [StrategyName.HYBRID])

    result = planner.plan(_ctx())

    assert result.attempts[0]["latency_ms"] == 12.5
    assert result.attempts[0]["metadata"] == {"classification_ms": 1.0, "retrieval_ms": 10.0}


def test_empty_metadata_dict_normalizes_to_none_not_empty_dict():
    """{} and None both mean 'nothing here' -- keep the trace consistent rather than showing an empty {} sometimes and None other times."""
    strategy = FakeStrategy(StrategyName.HYBRID, StrategyOutcome.SUCCESS, confidence=0.9, metadata={})
    planner = _make_planner({StrategyName.HYBRID: strategy}, [StrategyName.HYBRID])

    result = planner.plan(_ctx())

    assert result.attempts[0]["metadata"] is None