"""
Planner: orchestrates classification -> policy check -> strategy
execution -> escalation -> outcome determination.

Escalation is an iterative loop (not recursion) over the ranked
strategy list, capped at config.max_escalations. Policy is checked
BEFORE a strategy runs (denial never executes the retrieval call),
and a denial is treated the same as a low-confidence result for
escalation purposes -- the planner tries the next strategy in the
ranked list rather than failing the whole request immediately
(see docs/planner.md, "Escalate, Don't Fail").

PlannerOutcome vs StrategyOutcome: see enums.py docstring. The
external response for ACCESS_DENIED is deliberately identical to
NO_EVIDENCE -- see build_user_response() below -- so an unauthorized
user cannot distinguish "nothing exists" from "something exists but
you can't see it." The real reason is always visible internally via
strategy_attempts in the audit log.
"""
from dataclasses import dataclass, field

from app.planner.config import DEFAULT_PLANNER_CONFIG, PlannerConfig
from app.planner.context import PlannerContext
from app.planner.enums import PlannerOutcome, StrategyOutcome
from app.planner.intent_classifier import IntentClassifier
from app.planner.policy_evaluator import PolicyEvaluator
from app.planner.registry import StrategyRegistry, build_default_registry
from app.planner.result import RetrievalResult


@dataclass(frozen=True)
class PlannerResult:
    outcome: PlannerOutcome
    result: RetrievalResult | None
    attempts: list[dict] = field(default_factory=list)
    ranked_strategies: list[str] = field(default_factory=list)


class Planner:
    def __init__(
        self,
        registry: StrategyRegistry | None = None,
        classifier: IntentClassifier | None = None,
        policy: PolicyEvaluator | None = None,
        config: PlannerConfig = DEFAULT_PLANNER_CONFIG,
    ):
        self.registry = registry or build_default_registry()
        self.classifier = classifier or IntentClassifier()
        self.policy = policy or PolicyEvaluator()
        self.config = config

    def plan(self, context: PlannerContext) -> PlannerResult:
        ranked = self.classifier.classify(context)
        ranked = ranked[: self.config.max_escalations]
        ranked_values = [s.value for s in ranked]

        attempts: list[dict] = []

        for strategy_name in ranked:
            if not self.policy.is_authorized(strategy_name, context):
                # confidence=None: retrieval never ran, so there's no
                # confidence value to report -- distinct from a strategy
                # that ran and genuinely returned 0.0 (e.g. GraphStrategy
                # stub before Neo4j exists). Same reasoning for
                # latency_ms/metadata: None means "never ran", not "ran
                # and took 0ms" or "ran with empty metadata".
                attempts.append(
                    {
                        "strategy": strategy_name.value,
                        "outcome": StrategyOutcome.DENIED_BY_POLICY.value,
                        "confidence": None,
                        "cleared_threshold": None,
                        "latency_ms": None,
                        "metadata": None,
                    }
                )
                continue

            strategy = self.registry.get(strategy_name)
            if strategy is None:
                attempts.append(
                    {
                        "strategy": strategy_name.value,
                        "outcome": StrategyOutcome.NOT_IMPLEMENTED.value,
                        "confidence": None,
                        "cleared_threshold": None,
                        "latency_ms": None,
                        "metadata": None,
                    }
                )
                continue

            try:
                result = strategy.retrieve(context)
            except Exception:
                attempts.append(
                    {
                        "strategy": strategy_name.value,
                        "outcome": StrategyOutcome.ERROR.value,
                        "confidence": None,
                        "cleared_threshold": None,
                        "latency_ms": None,
                        "metadata": None,
                    }
                )
                continue

            cleared_threshold = (
                result.outcome == StrategyOutcome.SUCCESS
                and result.confidence >= self.config.threshold_for(strategy_name)
            )
            # Explicit native-type casts here, at the single point every
            # strategy's confidence flows through, rather than trusting
            # each strategy to do it. This is defense-in-depth: hybrid_search.py
            # already casts at its source (see that file's comment for why
            # numpy.bool_ specifically breaks JSON serialization while
            # numpy.float64 silently doesn't), but a future strategy could
            # reintroduce the same bug without a check here.
            safe_confidence = float(result.confidence) if result.confidence is not None else None
            attempts.append(
                {
                    "strategy": strategy_name.value,
                    "outcome": result.outcome.value,
                    "confidence": safe_confidence,
                    # Distinct from "outcome" on purpose: a strategy can
                    # report StrategyOutcome.SUCCESS (it found something)
                    # while still not clearing the PLANNER's threshold for
                    # that strategy -- see docs/confidence.md. Without this
                    # field, the trace looked self-contradictory (a
                    # "success" attempt sitting inside a "no_evidence"
                    # planner_outcome) even though both were individually
                    # correct.
                    "cleared_threshold": bool(cleared_threshold) if safe_confidence is not None else None,
                    # Previously computed by every strategy (RetrievalResult
                    # always carries latency_ms/metadata) but never actually
                    # threaded through to the trace -- fixed here rather than
                    # in each strategy, since this is the one place all of
                    # them already flow through.
                    "latency_ms": result.latency_ms,
                    "metadata": result.metadata or None,
                }
            )

            if cleared_threshold:
                return PlannerResult(
                    outcome=PlannerOutcome.SUCCESS,
                    result=result,
                    attempts=attempts,
                    ranked_strategies=ranked_values,
                )
            # LOW_CONFIDENCE, NOT_IMPLEMENTED, DENIED_BY_POLICY, ERROR, or
            # SUCCESS-but-below-threshold: fall through to next strategy.

        return PlannerResult(
            outcome=self._final_outcome(attempts),
            result=None,
            attempts=attempts,
            ranked_strategies=ranked_values,
        )

    @staticmethod
    def _final_outcome(attempts: list[dict]) -> PlannerOutcome:
        if not attempts:
            return PlannerOutcome.NO_EVIDENCE  # defensive: empty ranked list

        outcomes = {a["outcome"] for a in attempts}

        if outcomes == {StrategyOutcome.DENIED_BY_POLICY.value}:
            return PlannerOutcome.ACCESS_DENIED
        if outcomes == {StrategyOutcome.ERROR.value}:
            return PlannerOutcome.FAILED
        return PlannerOutcome.NO_EVIDENCE


def build_trace_response(planner_result: PlannerResult) -> dict:
    """
    Full internal trace -- deliberately NOT redacted (shows ACCESS_DENIED
    plainly, unlike build_user_response()). This is meant for debugging,
    demos, and the future dashboard, not for exposing to the end user
    whose query it is. In v1 the /query/trace endpoint that calls this
    has no auth of its own -- lock it down before any real deployment
    (see docs/planner.md, Known v1 Limitations).

    `final_documents_count` added so callers (e.g. the evaluation script)
    can measure "how many documents came back" directly, instead of
    guessing from `attempts` -- attempts counts strategies TRIED, which
    is a different number and was previously being used as a stand-in
    for this by mistake.
    """
    return {
        "ranked_strategies": planner_result.ranked_strategies,
        "attempts": planner_result.attempts,
        "planner_outcome": planner_result.outcome.value,
        "final_strategy_used": (
            planner_result.result.strategy_name.value if planner_result.result else None
        ),
        "final_confidence": planner_result.result.confidence if planner_result.result else None,
        "final_reasoning": planner_result.result.reasoning if planner_result.result else None,
        "final_latency_ms": planner_result.result.latency_ms if planner_result.result else None,
        "final_metadata": (planner_result.result.metadata or None) if planner_result.result else None,
        "final_documents_count": (
            len(planner_result.result.documents) if planner_result.result else 0
        ),
    }


def build_audit_record(planner_result: PlannerResult, query_text: str) -> dict:
    """
    Fields for AuditLog construction. Exists so the extraction logic
    (final strategy, if any) isn't duplicated between here and
    build_user_response()/build_trace_response() -- all three now
    consume only PlannerResult, nothing else leaves the planner.
    """
    return {
        "query": query_text,
        "strategy_used": (
            planner_result.result.strategy_name.value if planner_result.result else None
        ),
        "strategy_attempts": planner_result.attempts,
        "planner_outcome": planner_result.outcome.value,
        "result_summary": f"{len(planner_result.attempts)} strategies attempted",
    }


def build_user_response(planner_result: PlannerResult) -> dict:
    """
    Renders the EXTERNAL response. ACCESS_DENIED and NO_EVIDENCE are
    deliberately indistinguishable here -- see module docstring.
    """
    if planner_result.outcome == PlannerOutcome.SUCCESS and planner_result.result is not None:
        return {
            "answer_available": True,
            "strategy_used": planner_result.result.strategy_name.value,
            "confidence": planner_result.result.confidence,
            "documents": planner_result.result.documents,
            "reasoning": planner_result.result.reasoning,
        }

    return {
        "answer_available": False,
        "message": "I don't have enough evidence to answer this confidently.",
        "confidence": 0.0,
        "documents": [],
    }