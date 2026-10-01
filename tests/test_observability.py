from concurrent.futures import ThreadPoolExecutor
from time import perf_counter, sleep

from app.planner.context import PlannerContext
from app.planner.enums import PlannerOutcome, StrategyName, StrategyOutcome
from app.planner.planner import Planner
from app.planner.registry import StrategyRegistry
from app.planner.result import RetrievalResult
from app.planner.strategy_base import RetrievalStrategy
from tests.test_planner import AllowAllPolicy, FakeClassifier


class TimedStrategy(RetrievalStrategy):
    def __init__(self, name: StrategyName = StrategyName.VECTOR, delay: float = 0.0, raises: bool = False):
        self.name = name
        self.delay = delay
        self.raises = raises

    def retrieve(self, context: PlannerContext) -> RetrievalResult:
        start = perf_counter()
        sleep(self.delay)
        if self.raises:
            raise RuntimeError("simulated retrieval outage")
        return RetrievalResult(
            documents=[{"text": "evidence"}],
            confidence=0.9,
            strategy_name=self.name,
            outcome=StrategyOutcome.SUCCESS,
            latency_ms=(perf_counter() - start) * 1000,
        )


def make_planner(strategy: RetrievalStrategy) -> Planner:
    registry = StrategyRegistry()
    registry.register(StrategyName.VECTOR, strategy)
    return Planner(
        registry=registry,
        classifier=FakeClassifier([StrategyName.VECTOR]),
        policy=AllowAllPolicy(),
    )


def test_latency_is_recorded_for_a_slow_strategy():
    result = make_planner(TimedStrategy(delay=0.01)).plan(
        PlannerContext(query="latency check")
    )

    assert result.outcome == PlannerOutcome.SUCCESS
    assert result.attempts[0]["latency_ms"] >= 10


def test_retrieval_failure_escalates_without_crashing():
    registry = StrategyRegistry()
    registry.register(StrategyName.VECTOR, TimedStrategy(raises=True))
    registry.register(StrategyName.HYBRID, TimedStrategy(name=StrategyName.HYBRID))
    planner = Planner(
        registry=registry,
        classifier=FakeClassifier([StrategyName.VECTOR, StrategyName.HYBRID]),
        policy=AllowAllPolicy(),
    )

    result = planner.plan(PlannerContext(query="failure check"))

    assert result.outcome == PlannerOutcome.SUCCESS
    assert result.attempts[0]["outcome"] == "error"
    assert result.result.strategy_name == StrategyName.HYBRID


def test_planner_handles_concurrent_load():
    planner = make_planner(TimedStrategy())
    start = perf_counter()

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(
            executor.map(
                lambda index: planner.plan(PlannerContext(query=f"load {index}")),
                range(32),
            )
        )

    elapsed = perf_counter() - start
    assert len(results) == 32
    assert all(result.outcome == PlannerOutcome.SUCCESS for result in results)
    assert elapsed < 5