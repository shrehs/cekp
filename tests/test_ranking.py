from app.planner.enums import StrategyName, StrategyState
from app.planner.ranking import rank_candidates


def test_healthy_ranking_preserves_classifier_order():
    strategies = [
        StrategyName.GRAPH,
        StrategyName.HYBRID,
        StrategyName.VECTOR,
    ]

    states = {
        StrategyName.GRAPH: StrategyState.HEALTHY,
        StrategyName.HYBRID: StrategyState.HEALTHY,
        StrategyName.VECTOR: StrategyState.HEALTHY,
    }

    ranked = rank_candidates(
        strategies,
        states,
        health_aware=True,
        degraded_penalty=0.11,
    )

    assert [candidate.strategy for candidate in ranked] == [
        StrategyName.GRAPH,
        StrategyName.HYBRID,
        StrategyName.VECTOR,
    ]

    assert ranked[0].decision == "selected"
    assert ranked[1].decision == "kept"
    assert ranked[2].decision == "kept"

    assert ranked[0].routing_score == 1.0
    assert ranked[1].routing_score == 0.9
    assert ranked[2].routing_score == 0.8


def test_degraded_graph_is_demoted_below_healthy_hybrid():
    strategies = [
        StrategyName.GRAPH,
        StrategyName.HYBRID,
        StrategyName.VECTOR,
    ]

    states = {
        StrategyName.GRAPH: StrategyState.DEGRADED,
        StrategyName.HYBRID: StrategyState.HEALTHY,
        StrategyName.VECTOR: StrategyState.HEALTHY,
    }

    ranked = rank_candidates(
        strategies,
        states,
        health_aware=True,
        degraded_penalty=0.11,
    )

    assert ranked[0].strategy == StrategyName.HYBRID
    assert ranked[0].decision == "selected"

    graph = next(
        candidate
        for candidate in ranked
        if candidate.strategy == StrategyName.GRAPH
    )

    assert graph.routing_score == 1.0
    assert graph.health_penalty == 0.11
    assert graph.adjusted_score == 0.89
    assert graph.decision == "demoted"


def test_degraded_strategy_can_still_win_if_score_gap_is_large():
    strategies = [
        StrategyName.GRAPH,
        StrategyName.HYBRID,
    ]

    states = {
        StrategyName.GRAPH: StrategyState.DEGRADED,
        StrategyName.HYBRID: StrategyState.HEALTHY,
    }

    ranked = rank_candidates(
        strategies,
        states,
        health_aware=True,
        degraded_penalty=0.05,
    )

    assert ranked[0].strategy == StrategyName.GRAPH
    assert ranked[0].decision == "selected"

    assert ranked[0].routing_score == 1.0
    assert ranked[0].health_penalty == 0.05
    assert ranked[0].adjusted_score == 0.95


def test_unavailable_strategy_is_skipped():
    strategies = [
        StrategyName.GRAPH,
        StrategyName.HYBRID,
        StrategyName.VECTOR,
    ]

    states = {
        StrategyName.GRAPH: StrategyState.UNAVAILABLE,
        StrategyName.HYBRID: StrategyState.HEALTHY,
        StrategyName.VECTOR: StrategyState.HEALTHY,
    }

    ranked = rank_candidates(
        strategies,
        states,
        health_aware=True,
        degraded_penalty=0.10,
    )

    assert ranked[0].strategy == StrategyName.HYBRID
    assert ranked[0].decision == "selected"

    assert ranked[-1].strategy == StrategyName.GRAPH
    assert ranked[-1].decision == "skipped_unavailable"
    assert ranked[-1].adjusted_score == float("-inf")


def test_health_aware_ranking_disabled_matches_baseline():
    strategies = [
        StrategyName.GRAPH,
        StrategyName.HYBRID,
        StrategyName.VECTOR,
    ]

    states = {
        StrategyName.GRAPH: StrategyState.DEGRADED,
        StrategyName.HYBRID: StrategyState.HEALTHY,
        StrategyName.VECTOR: StrategyState.HEALTHY,
    }

    ranked = rank_candidates(
        strategies,
        states,
        health_aware=False,
        degraded_penalty=0.10,
    )

    assert [candidate.strategy for candidate in ranked] == [
        StrategyName.GRAPH,
        StrategyName.HYBRID,
        StrategyName.VECTOR,
    ]

    graph = ranked[0]

    assert graph.routing_score == 1.0
    assert graph.health_penalty == 0.0
    assert graph.adjusted_score == 1.0
    assert graph.decision == "selected"


def test_tie_break_preserves_original_classifier_order():
    strategies = [
        StrategyName.GRAPH,
        StrategyName.HYBRID,
    ]

    states = {
        StrategyName.GRAPH: StrategyState.DEGRADED,
        StrategyName.HYBRID: StrategyState.HEALTHY,
    }

    ranked = rank_candidates(
        strategies,
        states,
        health_aware=True,
        degraded_penalty=0.10,
    )

    # Graph: 1.00 - 0.10 = 0.90
    # Hybrid: 0.90
    # Equal adjusted scores -> original classifier order wins.
    assert ranked[0].strategy == StrategyName.GRAPH
    assert ranked[0].decision == "selected"

    assert ranked[1].strategy == StrategyName.HYBRID
    assert ranked[1].decision == "kept"