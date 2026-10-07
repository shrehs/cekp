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
import logging
import time
from dataclasses import dataclass, field
from opentelemetry import trace

from app.planner.config import DEFAULT_PLANNER_CONFIG, PlannerConfig
from app.planner.context import PlannerContext
from app.planner.enums import PlannerOutcome, StrategyOutcome, StrategyState
from app.planner.health import StrategyHealthMonitor
from app.planner.intent_classifier import IntentClassifier
from app.planner.policy_evaluator import PolicyEvaluator
from app.planner.registry import StrategyRegistry, build_default_registry
from app.planner.result import RetrievalResult

from app.core.metrics import (
    QUERY_OUTCOME_TOTAL,
    RETRIEVAL_STRATEGY_TOTAL,
    RETRIEVAL_ATTEMPTS_TOTAL,
    RETRIEVAL_DURATION,
    RETRIEVED_DOCUMENTS,
    PLANNER_CONFIDENCE,
    EVIDENCE_OUTCOME_TOTAL,
    POLICY_OUTCOME_TOTAL,
    RECOVERY_ATTEMPTS_TOTAL,
    RECOVERY_SUCCESS_TOTAL,
    RECOVERY_DURATION,
    STRATEGY_STATE,
)

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("cekp.planner")


@dataclass(frozen=True)
class PlannerResult:
    outcome: PlannerOutcome
    result: RetrievalResult | None
    attempts: list[dict] = field(default_factory=list)
    ranked_strategies: list[str] = field(default_factory=list)
    inferred_states: dict[str, str] = field(default_factory=dict)   # strategy -> StrategyState.value
    interventions: list[dict] = field(default_factory=list)          # skips due to UNAVAILABLE state


class Planner:
    def __init__(
        self,
        registry: StrategyRegistry | None = None,
        classifier: IntentClassifier | None = None,
        policy: PolicyEvaluator | None = None,
        config: PlannerConfig = DEFAULT_PLANNER_CONFIG,
        monitor: StrategyHealthMonitor | None = None,
    ):
        self.registry = registry or build_default_registry()
        self.classifier = classifier or IntentClassifier()
        self.policy = policy or PolicyEvaluator()
        self.config = config
        self.monitor = monitor or StrategyHealthMonitor()

    def plan(self, context: PlannerContext) -> PlannerResult:
        with tracer.start_as_current_span("planner.intent_classification") as span:
            ranked = self.classifier.classify(context)
            span.set_attribute("cekp.query_length", len(context.query or ""))
            span.set_attribute("cekp.ranked_strategy_count", len(ranked))
            span.set_attribute("cekp.ranked_strategies", ",".join(s.value for s in ranked))

        ranked = ranked[: self.config.max_escalations]
        ranked_values = [s.value for s in ranked]

        attempts: list[dict] = []
        interventions: list[dict] = []
        # strategy_name of the first UNAVAILABLE skip, for recovery tracking
        first_skipped: str | None = None
        recovery_start: float | None = None

        for strategy_name in ranked:
            # --- State inference: consult monitor before policy/retrieval ---
            inferred = self.monitor.state(strategy_name)
            _state_gauge_value = {StrategyState.HEALTHY: 0, StrategyState.DEGRADED: 1, StrategyState.UNAVAILABLE: 2}
            STRATEGY_STATE.labels(strategy=strategy_name.value).set(_state_gauge_value[inferred])

            if inferred == StrategyState.UNAVAILABLE:
                intervention = {
                    "strategy": strategy_name.value,
                    "inferred_state": inferred.value,
                    "decision": "skip",
                    "reason": "inferred_unavailable",
                }
                interventions.append(intervention)
                attempts.append({
                    "strategy": strategy_name.value,
                    "outcome": "skipped_unavailable",
                    "confidence": None,
                    "cleared_threshold": None,
                    "latency_ms": None,
                    "metadata": {"inferred_state": inferred.value},
                })
                RECOVERY_ATTEMPTS_TOTAL.labels(strategy=strategy_name.value).inc()
                RETRIEVAL_ATTEMPTS_TOTAL.labels(
                    strategy=strategy_name.value,
                    outcome="skipped_unavailable",
                ).inc()
                logger.warning(
                    "strategy_skipped_unavailable",
                    extra={"strategy": strategy_name.value, "inferred_state": inferred.value},
                )
                if first_skipped is None:
                    first_skipped = strategy_name.value
                    recovery_start = time.perf_counter()
                continue

            with tracer.start_as_current_span("planner.policy_check") as span:
                authorized = self.policy.is_authorized(strategy_name, context)
                span.set_attribute("cekp.strategy", strategy_name.value)
                span.set_attribute("cekp.authorized", authorized)

            if not authorized:
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
                RETRIEVAL_ATTEMPTS_TOTAL.labels(
                    strategy=strategy_name.value,
                    outcome=StrategyOutcome.DENIED_BY_POLICY.value,
                ).inc()
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
                RETRIEVAL_ATTEMPTS_TOTAL.labels(
                    strategy=strategy_name.value,
                    outcome=StrategyOutcome.NOT_IMPLEMENTED.value,
                ).inc()
                continue

            try:
                with tracer.start_as_current_span(
                    f"retrieval.strategy.{strategy_name.value}"
                ) as span:
                    span.set_attribute("cekp.strategy", strategy_name.value)
                    span.set_attribute("cekp.inferred_state", inferred.value)
                    result = strategy.retrieve(context)
                    span.set_attribute("cekp.outcome", result.outcome.value)
                    span.set_attribute("cekp.confidence", float(result.confidence))
                    span.set_attribute("cekp.documents_count", len(result.documents))
            except Exception:
                logger.exception(
                    "Strategy %s failed for query: %r",
                    strategy_name,
                    context.query,
                )
                self.monitor.record(strategy_name, StrategyOutcome.ERROR, None)
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
                RETRIEVAL_ATTEMPTS_TOTAL.labels(
                    strategy=strategy_name.value,
                    outcome=StrategyOutcome.ERROR.value,
                ).inc()
                continue

            # Record outcome into the monitor for future state inference
            self.monitor.record(strategy_name, result.outcome, result.latency_ms)

            with tracer.start_as_current_span("planner.confidence_evaluation") as span:
                threshold = self.config.threshold_for(strategy_name)
                cleared_threshold = (
                    result.outcome == StrategyOutcome.SUCCESS
                    and result.confidence >= threshold
                )
                span.set_attribute("cekp.strategy", strategy_name.value)
                span.set_attribute("cekp.confidence", float(result.confidence))
                span.set_attribute("cekp.threshold", float(threshold))
                span.set_attribute("cekp.cleared_threshold", bool(cleared_threshold))

            safe_confidence = float(result.confidence) if result.confidence is not None else None
            attempts.append(
                {
                    "strategy": strategy_name.value,
                    "outcome": result.outcome.value,
                    "confidence": safe_confidence,
                    "cleared_threshold": bool(cleared_threshold) if safe_confidence is not None else None,
                    "latency_ms": result.latency_ms,
                    "metadata": result.metadata or None,
                }
            )

            RETRIEVAL_ATTEMPTS_TOTAL.labels(
                strategy=strategy_name.value,
                outcome=result.outcome.value,
            ).inc()

            if result.latency_ms is not None:
                RETRIEVAL_DURATION.labels(
                    strategy=strategy_name.value
                ).observe(float(result.latency_ms) / 1000.0)

            if cleared_threshold:
                RETRIEVAL_STRATEGY_TOTAL.labels(
                    strategy=result.strategy_name.value
                ).inc()
                QUERY_OUTCOME_TOTAL.labels(
                    outcome=PlannerOutcome.SUCCESS.value
                ).inc()
                if result.confidence is not None:
                    PLANNER_CONFIDENCE.observe(float(result.confidence))
                RETRIEVED_DOCUMENTS.observe(len(result.documents))
                EVIDENCE_OUTCOME_TOTAL.labels(
                    outcome="evidence_backed" if result.documents else "no_evidence"
                ).inc()
                POLICY_OUTCOME_TOTAL.labels(
                    outcome=_policy_outcome(attempts)
                ).inc()

                # Recovery: a skip happened earlier and this strategy succeeded
                if first_skipped is not None and recovery_start is not None:
                    RECOVERY_SUCCESS_TOTAL.labels(
                        skipped_strategy=first_skipped,
                        fallback_strategy=result.strategy_name.value,
                    ).inc()
                    RECOVERY_DURATION.observe(time.perf_counter() - recovery_start)

                return PlannerResult(
                    outcome=PlannerOutcome.SUCCESS,
                    result=result,
                    attempts=attempts,
                    ranked_strategies=ranked_values,
                    inferred_states=self.monitor.snapshot(),
                    interventions=interventions,
                )

        final_outcome = self._final_outcome(attempts)

        QUERY_OUTCOME_TOTAL.labels(outcome=final_outcome.value).inc()
        EVIDENCE_OUTCOME_TOTAL.labels(
            outcome="not_evaluated" if final_outcome == PlannerOutcome.FAILED else "no_evidence"
        ).inc()
        POLICY_OUTCOME_TOTAL.labels(outcome=_policy_outcome(attempts)).inc()

        return PlannerResult(
            outcome=final_outcome,
            result=None,
            attempts=attempts,
            ranked_strategies=ranked_values,
            inferred_states=self.monitor.snapshot(),
            interventions=interventions,
        )

    @staticmethod
    def _final_outcome(attempts: list[dict]) -> PlannerOutcome:
        if not attempts:
            return PlannerOutcome.NO_EVIDENCE  # defensive: empty ranked list

        outcomes = {a["outcome"] for a in attempts}

        if outcomes == {StrategyOutcome.DENIED_BY_POLICY.value}:
            return PlannerOutcome.ACCESS_DENIED
        if outcomes <= {StrategyOutcome.ERROR.value, "skipped_unavailable"}:
            return PlannerOutcome.FAILED
        return PlannerOutcome.NO_EVIDENCE


def _policy_outcome(attempts: list[dict]) -> str:
    if not attempts:
        return "not_evaluated"
    denied_count = sum(
        attempt["outcome"] == StrategyOutcome.DENIED_BY_POLICY.value
        for attempt in attempts
    )
    if denied_count == len(attempts):
        return "denied"
    if denied_count:
        return "mixed"
    return "allowed"


def build_trace_response(
    planner_result: PlannerResult,
    request_id: str | None = None,
    http_status: int | None = None,
    http_outcome: str | None = None,
    http_latency_ms: float | None = None,
) -> dict:
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
    attempts = planner_result.attempts
    denied_count = sum(
        attempt["outcome"] == StrategyOutcome.DENIED_BY_POLICY.value
        for attempt in attempts
    )
    if not attempts:
        policy_outcome = "not_evaluated"
    elif denied_count == len(attempts):
        policy_outcome = "denied"
    elif denied_count:
        policy_outcome = "mixed"
    else:
        policy_outcome = "allowed"

    if planner_result.outcome == PlannerOutcome.FAILED:
        evidence_outcome = "not_evaluated"
    else:
        evidence_outcome = (
            "evidence_backed"
            if planner_result.result is not None and planner_result.result.documents
            else "no_evidence"
        )

    return {
        "trace_version": "2",
        "request_id": request_id,
        "http_status": http_status,
        "http_outcome": http_outcome,
        "http_latency_ms": http_latency_ms,
        "ranked_strategies": planner_result.ranked_strategies,
        "inferred_states": planner_result.inferred_states,
        "interventions": planner_result.interventions,
        "attempts": attempts,
        "planner_outcome": planner_result.outcome.value,
        "evidence_outcome": evidence_outcome,
        "policy_outcome": _policy_outcome(attempts),
        "selected_strategy": (
            planner_result.result.strategy_name.value if planner_result.result else None
        ),
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