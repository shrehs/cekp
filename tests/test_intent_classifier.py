from app.planner.context import PlannerContext
from app.planner.enums import StrategyName
from app.planner.intent_classifier import IntentClassifier

classifier = IntentClassifier()


def _ctx(query: str) -> PlannerContext:
    return PlannerContext(query=query)


def test_graph_query_ranks_graph_first():
    ranked = classifier.classify(_ctx("Which services depend on the auth service?"))
    assert ranked[0] == StrategyName.GRAPH
    assert ranked[-1] == StrategyName.VECTOR  # universal fallback always last


def test_hybrid_query_ranks_hybrid_first():
    ranked = classifier.classify(_ctx("What does error code 503 mean?"))
    assert ranked[0] == StrategyName.HYBRID


def test_vector_query_falls_back_to_hybrid_then_vector():
    # No rule matches -- default is HYBRID before VECTOR (see intent_classifier.py rationale)
    ranked = classifier.classify(_ctx("How do I set up my dev environment?"))
    assert ranked[0] == StrategyName.HYBRID
    assert StrategyName.VECTOR in ranked


def test_multiple_rule_match_orders_by_priority():
    # Matches both graph ("depends on") and hybrid ("error code") patterns
    ranked = classifier.classify(
        _ctx("Which service depends on the payment service and threw error code 500?")
    )
    assert ranked[0] == StrategyName.GRAPH
    assert StrategyName.HYBRID in ranked
    assert ranked.index(StrategyName.GRAPH) < ranked.index(StrategyName.HYBRID)


def test_unknown_query_still_returns_a_ranked_list():
    ranked = classifier.classify(_ctx("asdkfjaslkdfj"))
    assert len(ranked) >= 1
    assert StrategyName.VECTOR in ranked


def test_empty_query_returns_vector_only():
    ranked = classifier.classify(_ctx(""))
    assert ranked == [StrategyName.VECTOR]

    ranked_whitespace = classifier.classify(_ctx("   "))
    assert ranked_whitespace == [StrategyName.VECTOR]


def test_code_structure_import_query_ranks_graph_first():
    """New pattern, added when GraphStrategy's v1 target became the
    code-structure graph rather than the org-dependency graph."""
    ranked = classifier.classify(_ctx("What does app/main.py import?"))
    assert ranked[0] == StrategyName.GRAPH


def test_code_structure_calls_query_ranks_graph_first():
    ranked = classifier.classify(_ctx("What calls build_user_response?"))
    assert ranked[0] == StrategyName.GRAPH


def test_code_structure_which_functions_query_ranks_graph_first():
    ranked = classifier.classify(_ctx("Which functions are defined in planner.py?"))
    assert ranked[0] == StrategyName.GRAPH


def test_org_dependency_patterns_still_match_graph_despite_being_unimplemented():
    """
    Regression: the original org-dependency patterns must keep matching
    GRAPH, even though that graph isn't built. Silently falling through
    to HYBRID for these would misrepresent "this kind of graph question
    isn't built yet" as "no graph capability exists at all."
    """
    ranked = classifier.classify(_ctx("Which services depend on the auth service?"))
    assert ranked[0] == StrategyName.GRAPH


def test_where_is_x_defined_routes_to_graph():
    """
    Regression test: found via tracing the four canonical graph
    questions end to end before trusting a validation script built on
    top of them. GraphStrategy's own sub-classifier already handled
    "where is X defined" phrasing, but IntentClassifier never routed
    it to GRAPH in the first place -- so GraphStrategy never even got
    the chance to run for this exact phrasing.
    """
    ranked = classifier.classify(_ctx("Where is Planner defined?"))
    assert ranked[0] == StrategyName.GRAPH