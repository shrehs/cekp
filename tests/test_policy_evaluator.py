from app.planner.context import PlannerContext
from app.planner.enums import StrategyName
from app.planner.policy_evaluator import PolicyEvaluator

policy = PolicyEvaluator()


def test_engineering_department_authorized_for_graph():
    ctx = PlannerContext(query="q", department="engineering")
    assert policy.is_authorized(StrategyName.GRAPH, ctx) is True


def test_unlisted_department_denied_for_graph():
    ctx = PlannerContext(query="q", department="marketing")
    assert policy.is_authorized(StrategyName.GRAPH, ctx) is False


def test_missing_department_denied_for_graph_not_assumed_authorized():
    ctx = PlannerContext(query="q", department=None)
    assert policy.is_authorized(StrategyName.GRAPH, ctx) is False


def test_non_graph_strategies_are_open_regardless_of_department():
    ctx = PlannerContext(query="q", department="marketing")
    assert policy.is_authorized(StrategyName.VECTOR, ctx) is True
    assert policy.is_authorized(StrategyName.HYBRID, ctx) is True
    assert policy.is_authorized(StrategyName.AGENTIC, ctx) is True
