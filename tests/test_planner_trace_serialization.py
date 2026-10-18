"""
Planner-level regression: a trace produced while a strategy is UNAVAILABLE
must be strict-JSON serializable (the bug seen in the outage experiment).

NOTE: written against the planner/monitor interfaces in the pasted files but
not executed outside your repo. Adjust the fakes if your signatures differ.
"""
import json
from types import SimpleNamespace

from app.planner.context import PlannerContext
from app.planner.enums import PlannerOutcome, StrategyName as S, StrategyOutcome
from app.planner.health import StrategyHealthMonitor
from app.planner.planner import Planner, build_trace_response


class _Classifier:
    def classify(self, context):
        return [S.GRAPH, S.HYBRID, S.VECTOR]


class _Policy:
    def is_authorized(self, strategy, context):
        return True


class _Result:
    def __init__(self, name):
        self.strategy_name = name
        self.outcome = StrategyOutcome.SUCCESS
        self.confidence = 0.9
        self.documents = [{"id": "d1"}]
        self.latency_ms = 5.0
        self.metadata = {}
        self.reasoning = "fake"


class _Strategy:
    def __init__(self, name):
        self.name = name

    def retrieve(self, context):
        return _Result(self.name)


class _Registry:
    def get(self, name):
        return _Strategy(name)


def _make_planner():
    config = SimpleNamespace(
        max_escalations=4,
        health_aware_ranking=True,
        degraded_health_penalty=0.15,
        threshold_for=lambda name: 0.5,
    )
    monitor = StrategyHealthMonitor()
    for _ in range(10):  # drive Graph to UNAVAILABLE
        monitor.record(S.GRAPH, StrategyOutcome.ERROR, None)
    return Planner(
        registry=_Registry(),
        classifier=_Classifier(),
        policy=_Policy(),
        config=config,
        monitor=monitor,
    )


def test_trace_is_strict_json_when_graph_unavailable():
    planner = _make_planner()
    result = planner.plan(PlannerContext(query="what does app.main import?"))

    assert result.outcome == PlannerOutcome.SUCCESS
    assert result.result.strategy_name == S.HYBRID  # Graph skipped, fallback used
    assert any(i["decision"] == "skip" for i in result.interventions)

    trace = build_trace_response(result, request_id="t", http_status=200,
                                 http_outcome="ok", http_latency_ms=1.0)
    json.dumps(trace, allow_nan=False)  # must not raise
