import json

import pytest

from app.planner.enums import StrategyName as S, StrategyState as St
from app.planner.ranking import finite_or_none, rank_candidates

ORDER = [S.GRAPH, S.HYBRID, S.VECTOR]
UNAVAILABLE_GRAPH = {S.GRAPH: St.UNAVAILABLE, S.HYBRID: St.HEALTHY, S.VECTOR: St.HEALTHY}
DEGRADED_GRAPH = {S.GRAPH: St.DEGRADED, S.HYBRID: St.HEALTHY, S.VECTOR: St.HEALTHY}


def _rank(states=UNAVAILABLE_GRAPH, penalty=0.15):
    return rank_candidates(ORDER, states, health_aware=True, degraded_penalty=penalty)


def _graph(ranked):
    return next(c for c in ranked if c.strategy == S.GRAPH)


def test_unavailable_keeps_neg_inf_internally():
    g = _graph(_rank())
    assert g.adjusted_score == float("-inf")
    assert g.decision == "skipped_unavailable"


def test_unavailable_serializes_as_none():
    assert _graph(_rank()).to_dict()["adjusted_score"] is None


def test_finite_scores_unchanged():
    h = next(c for c in _rank() if c.strategy == S.HYBRID).to_dict()
    assert h["adjusted_score"] == pytest.approx(0.9)
    assert h["routing_score"] == pytest.approx(0.9)


def test_trace_with_unavailable_candidate_and_intervention_is_strict_json():
    ranked = _rank()
    g = _graph(ranked)
    intervention = {
        "strategy": g.strategy.value,
        "decision": "skip",
        "routing_score": g.routing_score,
        "health_penalty": g.health_penalty,
        "adjusted_score": finite_or_none(g.adjusted_score),
    }
    trace = {
        "routing_candidates": [c.to_dict() for c in ranked],
        "interventions": [intervention],
    }
    json.dumps(trace, allow_nan=False)  # must not raise


def test_raw_neg_inf_reproduces_original_bug():
    with pytest.raises(ValueError):
        json.dumps({"adjusted_score": float("-inf")}, allow_nan=False)


def test_penalty_equal_to_rank_step_does_not_demote():
    # routing scores step by 0.10, so a 0.10 penalty ties and original order wins
    assert _rank(DEGRADED_GRAPH, penalty=0.10)[0].strategy == S.GRAPH
    assert _rank(DEGRADED_GRAPH, penalty=0.15)[0].strategy == S.HYBRID
