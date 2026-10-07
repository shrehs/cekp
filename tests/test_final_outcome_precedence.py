"""
_final_outcome() precedence tests — CEKP v2.3.

Two kinds of tests live here:

1. CHARACTERIZATION tests pin what the planner does today. If one fails, the
   behavior changed; decide whether that was intentional.

2. XFAIL tests mark combinations where the correct answer is still undecided.
   They are strict, so the day the implementation changes they will XPASS and
   fail the suite, which is the signal to decide the precedence rule and turn
   them into normal tests with an explicit expected outcome.

Open question (see TODO in docs/reliability-loop.md):
    When no strategy actually executed, and the attempts are a mix of
    skipped_unavailable and denied_by_policy, should the planner report
    FAILED, ACCESS_DENIED, or NO_EVIDENCE? Today it reports NO_EVIDENCE, which
    implies "we searched and found nothing" even though nothing was searched.

Note: build_user_response() renders ACCESS_DENIED and NO_EVIDENCE identically,
so this only affects the internal trace and metrics, not what a user sees.
"""
import pytest

from app.planner.context import PlannerContext
from app.planner.enums import PlannerOutcome, StrategyName, StrategyOutcome
from app.planner.health import StrategyHealthMonitor
from app.planner.planner import Planner, build_user_response
from app.planner.policy_evaluator import PolicyEvaluator
from app.planner.registry import StrategyRegistry
from tests.test_planner import AllowAllPolicy, FakeClassifier, FakeStrategy

SKIPPED = "skipped_unavailable"
ERROR = StrategyOutcome.ERROR.value
DENIED = StrategyOutcome.DENIED_BY_POLICY.value
LOW_CONF = StrategyOutcome.LOW_CONFIDENCE.value
NOT_IMPL = StrategyOutcome.NOT_IMPLEMENTED.value


def _attempts(*outcomes: str) -> list[dict]:
    return [{"outcome": o} for o in outcomes]


def _final(*outcomes: str) -> PlannerOutcome:
    return Planner._final_outcome(_attempts(*outcomes))


# ---------------------------------------------------------------------------
# 1. Characterization: current, uncontroversial behavior
# ---------------------------------------------------------------------------

def test_no_attempts_is_no_evidence():
    assert _final() == PlannerOutcome.NO_EVIDENCE


def test_only_denied_is_access_denied():
    assert _final(DENIED, DENIED) == PlannerOutcome.ACCESS_DENIED


def test_only_errors_is_failed():
    assert _final(ERROR, ERROR) == PlannerOutcome.FAILED


def test_only_skipped_unavailable_is_failed():
    assert _final(SKIPPED) == PlannerOutcome.FAILED


def test_skipped_and_error_is_failed():
    assert _final(SKIPPED, ERROR) == PlannerOutcome.FAILED


def test_only_low_confidence_is_no_evidence():
    assert _final(LOW_CONF, LOW_CONF) == PlannerOutcome.NO_EVIDENCE


# ---------------------------------------------------------------------------
# 2. Characterization: current behavior that may be revisited
#
# These pin today's answer without claiming it is the right one. If you change
# the precedence rule, update these deliberately.
# ---------------------------------------------------------------------------

def test_error_then_low_confidence_is_currently_no_evidence():
    # One strategy errored, another genuinely ran and found nothing usable.
    # NO_EVIDENCE is defensible here (a search did happen). If you widen FAILED
    # to "any infrastructure error", this is the test that will change.
    assert _final(ERROR, LOW_CONF) == PlannerOutcome.NO_EVIDENCE


def test_skipped_then_not_implemented_is_currently_no_evidence():
    # Nothing executed, same shape of ambiguity as skipped+denied.
    assert _final(SKIPPED, NOT_IMPL) == PlannerOutcome.NO_EVIDENCE


def test_denied_then_error_is_currently_no_evidence():
    assert _final(DENIED, ERROR) == PlannerOutcome.NO_EVIDENCE


# ---------------------------------------------------------------------------
# 3. Undecided: skipped_unavailable + denied_by_policy
#
# The assertion states only what we are confident about: this is not a genuine
# "searched and found nothing" situation. It does NOT choose between FAILED and
# ACCESS_DENIED. Once decided, replace `!=` with `==` and drop the xfail.
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    strict=True,
    reason="precedence undecided: skipped_unavailable + denied_by_policy currently falls through to NO_EVIDENCE",
)
def test_unavailable_then_policy_denied_does_not_return_no_evidence():
    assert _final(SKIPPED, DENIED) != PlannerOutcome.NO_EVIDENCE


class _DenyHybridOnlyPolicy(PolicyEvaluator):
    def is_authorized(self, strategy_name, context):
        return strategy_name != StrategyName.HYBRID


@pytest.mark.xfail(
    strict=True,
    reason="precedence undecided: end-to-end version of the skipped + denied case",
)
def test_planner_graph_unavailable_and_hybrid_denied_does_not_return_no_evidence():
    monitor = StrategyHealthMonitor(
        window=10,
        degraded_error_rate=0.3,
        unavailable_error_rate=0.6,
        degraded_latency_ms=3_000.0,
    )
    for _ in range(10):
        monitor.record(StrategyName.GRAPH, StrategyOutcome.ERROR, 50.0)

    registry = StrategyRegistry()
    registry.register(StrategyName.GRAPH, FakeStrategy(StrategyName.GRAPH, StrategyOutcome.SUCCESS, 0.9))
    registry.register(StrategyName.HYBRID, FakeStrategy(StrategyName.HYBRID, StrategyOutcome.SUCCESS, 0.9))

    planner = Planner(
        registry=registry,
        classifier=FakeClassifier([StrategyName.GRAPH, StrategyName.HYBRID]),
        policy=_DenyHybridOnlyPolicy(),
        monitor=monitor,
    )

    result = planner.plan(PlannerContext(query="test"))

    assert result.outcome != PlannerOutcome.NO_EVIDENCE


def test_skipped_plus_denied_user_response_is_unchanged_whatever_the_outcome():
    """
    Guardrail for when the precedence rule is decided: whichever of FAILED or
    ACCESS_DENIED is chosen, the external response must stay identical to the
    plain no-evidence response. The no-leakage guarantee must not depend on
    this internal classification.
    """
    from app.planner.planner import PlannerResult

    external = {
        "answer_available": False,
        "message": "I don't have enough evidence to answer this confidently.",
        "confidence": 0.0,
        "documents": [],
    }
    for outcome in (PlannerOutcome.FAILED, PlannerOutcome.ACCESS_DENIED, PlannerOutcome.NO_EVIDENCE):
        assert build_user_response(PlannerResult(outcome=outcome, result=None)) == external