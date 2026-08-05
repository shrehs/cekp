from app.planner.enums import StrategyName
from app.planner.registry import StrategyRegistry, build_default_registry
from app.planner.strategies import VectorStrategy


def test_register_and_get_returns_the_same_instance():
    registry = StrategyRegistry()
    strategy = VectorStrategy()
    registry.register(StrategyName.VECTOR, strategy)

    assert registry.get(StrategyName.VECTOR) is strategy


def test_missing_registration_returns_none_not_an_exception():
    registry = StrategyRegistry()
    assert registry.get(StrategyName.GRAPH) is None


def test_default_registry_has_all_four_strategies_registered():
    registry = build_default_registry()
    for name in StrategyName:
        assert registry.get(name) is not None
