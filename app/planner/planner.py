"""
Planner: orchestrates classification -> health inference -> routing
-> policy check -> strategy execution -> escalation -> outcome determination.

v2.3 adds health-aware strategy ranking.

Important invariants:
- The classifier remains the source of baseline strategy ordering.
- routing_score represents the classifier's baseline preference.
- health adjustment ONLY changes routing order.
- retrieval scores/confidence are never modified by health.
- UNAVAILABLE strategies are skipped.
- DEGRADED strategies may be demoted.
- HEALTHY strategies receive no penalty.
- With health_aware_ranking=False, behaviour matches v2.2 ordering.
- Every routing decision is exposed in the internal trace.
- routing_candidates is the single source of truth for execution order.
- interventions record routing decisions (skip); attempts record what the
  planner did per candidate. Skipped-unavailable entries live in attempts so
  _final_outcome() can distinguish FAILED from NO_EVIDENCE.
"""

import logging
import time
from dataclasses import dataclass, field

from opentelemetry import trace

from app.core.metrics import (
    EVIDENCE_OUTCOME_TOTAL,
    PLANNER_CONFIDENCE,
    POLICY_OUTCOME_TOTAL,
    QUERY_OUTCOME_TOTAL,
    RECOVERY_ATTEMPTS_TOTAL,
    RECOVERY_DURATION,
    RECOVERY_SUCCESS_TOTAL,
    RETRIEVAL_ATTEMPTS_TOTAL,
    RETRIEVAL_DURATION,
    RETRIEVAL_STRATEGY_TOTAL,
    RETRIEVED_DOCUMENTS,
    STRATEGY_STATE,
)
from app.planner.config import DEFAULT_PLANNER_CONFIG, PlannerConfig
from app.planner.context import PlannerContext
from app.planner.enums import PlannerOutcome, StrategyOutcome, StrategyState
from app.planner.health import StrategyHealthMonitor
from app.planner.intent_classifier import IntentClassifier
from app.planner.policy_evaluator import PolicyEvaluator
from app.planner.ranking import rank_candidates
from app.planner.registry import StrategyRegistry, build_default_registry
from app.planner.result import RetrievalResult

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("cekp.planner")

# ---------------------------------------------------------------------------
# Planner result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlannerResult:
    outcome: PlannerOutcome
    result: RetrievalResult | None
    attempts: list[dict] = field(default_factory=list)

    # Baseline/routing order exposed for compatibility.
    ranked_strategies: list[str] = field(default_factory=list)

    # v2.2
    inferred_states: dict[str, str] = field(default_factory=dict)
    interventions: list[dict] = field(default_factory=list)

    # v2.3
    routing_candidates: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------


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

        # ---------------------------------------------------------------
        # 1. Intent classification
        # ---------------------------------------------------------------

        with tracer.start_as_current_span(
            "planner.intent_classification"
        ) as span:

            classified = self.classifier.classify(context)

            span.set_attribute(
                "cekp.query_length",
                len(context.query or ""),
            )

            span.set_attribute(
                "cekp.classifier_strategy_count",
                len(classified),
            )

            span.set_attribute(
                "cekp.classifier_strategies",
                ",".join(strategy.value for strategy in classified),
            )

        # Apply the max escalation cap to the classifier list.
        classified = classified[: self.config.max_escalations]

        # ---------------------------------------------------------------
        # 2. Health inference
        # ---------------------------------------------------------------

        inferred_states: dict[str, str] = {}

        state_gauge_value = {
            StrategyState.HEALTHY: 0,
            StrategyState.DEGRADED: 1,
            StrategyState.UNAVAILABLE: 2,
        }

        for strategy_name in classified:
            state = self.monitor.state(strategy_name)

            inferred_states[strategy_name.value] = state.value

            STRATEGY_STATE.labels(
                strategy=strategy_name.value
            ).set(state_gauge_value[state])

        # ---------------------------------------------------------------
        # 3. v2.3 health-aware routing
        # ---------------------------------------------------------------

        states = {
            strategy: self.monitor.state(strategy)
            for strategy in classified
        }

        routing_candidates = rank_candidates(
            classified,
            states,
            health_aware=self.config.health_aware_ranking,
            degraded_penalty=self.config.degraded_health_penalty,
        )

        routing_candidate_dicts = [
            candidate.to_dict()
            for candidate in routing_candidates
        ]

        ranked_values = [
            candidate.strategy.value
            for candidate in routing_candidates
        ]

        # ---------------------------------------------------------------
        # 4a. Record routing decisions for UNAVAILABLE candidates
        #
        # This loop ONLY touches UNAVAILABLE candidates. It never executes
        # anything: an unavailable strategy is not attempted, it is skipped.
        # ---------------------------------------------------------------

        attempts: list[dict] = []
        interventions: list[dict] = []

        # First strategy skipped due to UNAVAILABLE (for recovery tracking).
        first_skipped: str | None = None
        recovery_start: float | None = None

        for candidate in routing_candidates:
            if candidate.health_state != StrategyState.UNAVAILABLE:
                continue

            skipped_name = candidate.strategy

            interventions.append(
                {
                    "strategy": skipped_name.value,
                    "inferred_state": candidate.health_state.value,
                    "decision": "skip",
                    "reason": "inferred_unavailable",
                    "routing_score": candidate.routing_score,
                    "health_penalty": candidate.health_penalty,
                    "adjusted_score": candidate.adjusted_score,
                }
            )

            attempts.append(
                {
                    "strategy": skipped_name.value,
                    "outcome": "skipped_unavailable",
                    "confidence": None,
                    "cleared_threshold": None,
                    "latency_ms": None,
                    "metadata": {
                        "inferred_state": candidate.health_state.value,
                    },
                }
            )

            RECOVERY_ATTEMPTS_TOTAL.labels(
                strategy=skipped_name.value
            ).inc()

            RETRIEVAL_ATTEMPTS_TOTAL.labels(
                strategy=skipped_name.value,
                outcome="skipped_unavailable",
            ).inc()

            logger.warning(
                "strategy_skipped_unavailable",
                extra={
                    "strategy": skipped_name.value,
                    "inferred_state": candidate.health_state.value,
                    "routing_score": candidate.routing_score,
                    "adjusted_score": candidate.adjusted_score,
                },
            )

            if first_skipped is None:
                first_skipped = skipped_name.value
                recovery_start = time.perf_counter()

        # ---------------------------------------------------------------
        # 4b. Execute LIVE candidates only, in health-adjusted order
        # ---------------------------------------------------------------

        for candidate in routing_candidates:
            if candidate.health_state == StrategyState.UNAVAILABLE:
                continue

            strategy_name = candidate.strategy

            # -----------------------------------------------------------
            # 5. Policy
            # -----------------------------------------------------------

            with tracer.start_as_current_span(
                "planner.policy_check"
            ) as span:

                authorized = self.policy.is_authorized(
                    strategy_name,
                    context,
                )

                span.set_attribute(
                    "cekp.strategy",
                    strategy_name.value,
                )

                span.set_attribute(
                    "cekp.authorized",
                    authorized,
                )

                span.set_attribute(
                    "cekp.health_state",
                    candidate.health_state.value,
                )

                span.set_attribute(
                    "cekp.routing_score",
                    candidate.routing_score,
                )

                span.set_attribute(
                    "cekp.adjusted_score",
                    candidate.adjusted_score,
                )

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

            # -----------------------------------------------------------
            # 6. Registry lookup
            # -----------------------------------------------------------

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

            # -----------------------------------------------------------
            # 7. Retrieval
            # -----------------------------------------------------------

            try:

                with tracer.start_as_current_span(
                    f"retrieval.strategy.{strategy_name.value}"
                ) as span:

                    span.set_attribute(
                        "cekp.strategy",
                        strategy_name.value,
                    )

                    span.set_attribute(
                        "cekp.inferred_state",
                        candidate.health_state.value,
                    )

                    span.set_attribute(
                        "cekp.routing_score",
                        candidate.routing_score,
                    )

                    span.set_attribute(
                        "cekp.health_penalty",
                        candidate.health_penalty,
                    )

                    span.set_attribute(
                        "cekp.adjusted_score",
                        candidate.adjusted_score,
                    )

                    span.set_attribute(
                        "cekp.routing_decision",
                        candidate.decision,
                    )

                    result = strategy.retrieve(context)

                    span.set_attribute(
                        "cekp.outcome",
                        result.outcome.value,
                    )

                    span.set_attribute(
                        "cekp.confidence",
                        float(result.confidence),
                    )

                    span.set_attribute(
                        "cekp.documents_count",
                        len(result.documents),
                    )

            except Exception:

                logger.exception(
                    "Strategy %s failed for query: %r",
                    strategy_name,
                    context.query,
                )

                self.monitor.record(
                    strategy_name,
                    StrategyOutcome.ERROR,
                    None,
                )

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

            # -----------------------------------------------------------
            # 8. Record real retrieval observation
            # -----------------------------------------------------------

            self.monitor.record(
                strategy_name,
                result.outcome,
                result.latency_ms,
            )

            # -----------------------------------------------------------
            # 9. Confidence evaluation
            # -----------------------------------------------------------

            with tracer.start_as_current_span(
                "planner.confidence_evaluation"
            ) as span:

                threshold = self.config.threshold_for(
                    strategy_name
                )

                cleared_threshold = (
                    result.outcome == StrategyOutcome.SUCCESS
                    and result.confidence >= threshold
                )

                span.set_attribute(
                    "cekp.strategy",
                    strategy_name.value,
                )

                span.set_attribute(
                    "cekp.confidence",
                    float(result.confidence),
                )

                span.set_attribute(
                    "cekp.threshold",
                    float(threshold),
                )

                span.set_attribute(
                    "cekp.cleared_threshold",
                    bool(cleared_threshold),
                )

            safe_confidence = (
                float(result.confidence)
                if result.confidence is not None
                else None
            )

            attempts.append(
                {
                    "strategy": strategy_name.value,
                    "outcome": result.outcome.value,
                    "confidence": safe_confidence,
                    "cleared_threshold": (
                        bool(cleared_threshold)
                        if safe_confidence is not None
                        else None
                    ),
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
                ).observe(
                    float(result.latency_ms) / 1000.0
                )

            # -----------------------------------------------------------
            # 10. Successful evidence-backed result
            # -----------------------------------------------------------

            if cleared_threshold:

                RETRIEVAL_STRATEGY_TOTAL.labels(
                    strategy=result.strategy_name.value
                ).inc()

                QUERY_OUTCOME_TOTAL.labels(
                    outcome=PlannerOutcome.SUCCESS.value
                ).inc()

                if result.confidence is not None:
                    PLANNER_CONFIDENCE.observe(
                        float(result.confidence)
                    )

                RETRIEVED_DOCUMENTS.observe(
                    len(result.documents)
                )

                EVIDENCE_OUTCOME_TOTAL.labels(
                    outcome=(
                        "evidence_backed"
                        if result.documents
                        else "no_evidence"
                    )
                ).inc()

                POLICY_OUTCOME_TOTAL.labels(
                    outcome=_policy_outcome(attempts)
                ).inc()

                # -------------------------------------------------------
                # Recovery verification
                # -------------------------------------------------------

                if (
                    first_skipped is not None
                    and recovery_start is not None
                ):

                    # Recovery is only considered successful when the
                    # fallback produced actual evidence.
                    if result.documents:

                        RECOVERY_SUCCESS_TOTAL.labels(
                            skipped_strategy=first_skipped,
                            fallback_strategy=result.strategy_name.value,
                        ).inc()

                        RECOVERY_DURATION.observe(
                            time.perf_counter()
                            - recovery_start
                        )

                return PlannerResult(
                    outcome=PlannerOutcome.SUCCESS,
                    result=result,
                    attempts=attempts,
                    ranked_strategies=ranked_values,
                    inferred_states=self.monitor.snapshot(),
                    interventions=interventions,
                    routing_candidates=routing_candidate_dicts,
                )

        # ---------------------------------------------------------------
        # 11. Nothing succeeded
        # ---------------------------------------------------------------

        final_outcome = self._final_outcome(attempts)

        QUERY_OUTCOME_TOTAL.labels(
            outcome=final_outcome.value
        ).inc()

        EVIDENCE_OUTCOME_TOTAL.labels(
            outcome=(
                "not_evaluated"
                if final_outcome == PlannerOutcome.FAILED
                else "no_evidence"
            )
        ).inc()

        POLICY_OUTCOME_TOTAL.labels(
            outcome=_policy_outcome(attempts)
        ).inc()

        return PlannerResult(
            outcome=final_outcome,
            result=None,
            attempts=attempts,
            ranked_strategies=ranked_values,
            inferred_states=self.monitor.snapshot(),
            interventions=interventions,
            routing_candidates=routing_candidate_dicts,
        )

    # -------------------------------------------------------------------
    # Outcome determination
    # -------------------------------------------------------------------

    @staticmethod
    def _final_outcome(
        attempts: list[dict],
    ) -> PlannerOutcome:

        if not attempts:
            return PlannerOutcome.NO_EVIDENCE

        outcomes = {
            attempt["outcome"]
            for attempt in attempts
        }

        # Every attempted strategy was denied.
        if outcomes == {
            StrategyOutcome.DENIED_BY_POLICY.value
        }:
            return PlannerOutcome.ACCESS_DENIED

        # Only infrastructure failures / unavailable strategies occurred.
        if outcomes <= {
            StrategyOutcome.ERROR.value,
            "skipped_unavailable",
        }:
            return PlannerOutcome.FAILED

        return PlannerOutcome.NO_EVIDENCE


# ---------------------------------------------------------------------------
# Policy outcome helper
# ---------------------------------------------------------------------------


def _policy_outcome(attempts: list[dict]) -> str:

    if not attempts:
        return "not_evaluated"

    denied_count = sum(
        attempt["outcome"]
        == StrategyOutcome.DENIED_BY_POLICY.value
        for attempt in attempts
    )

    if denied_count == len(attempts):
        return "denied"

    if denied_count:
        return "mixed"

    return "allowed"


# ---------------------------------------------------------------------------
# Trace response
# ---------------------------------------------------------------------------


def build_trace_response(
    planner_result: PlannerResult,
    request_id: str | None = None,
    http_status: int | None = None,
    http_outcome: str | None = None,
    http_latency_ms: float | None = None,
) -> dict:
    """
    Full internal trace.

    v2.3 adds routing_candidates so the trace can explain:

        baseline routing score
        -> health state
        -> health penalty
        -> adjusted score
        -> routing decision

    The raw retrieval confidence remains separate.
    """

    attempts = planner_result.attempts

    denied_count = sum(
        attempt["outcome"]
        == StrategyOutcome.DENIED_BY_POLICY.value
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
            if (
                planner_result.result is not None
                and planner_result.result.documents
            )
            else "no_evidence"
        )

    return {
        "trace_version": "2.3",

        "request_id": request_id,

        "http_status": http_status,
        "http_outcome": http_outcome,
        "http_latency_ms": http_latency_ms,

        # Baseline classifier order.
        "ranked_strategies": planner_result.ranked_strategies,

        # v2.2 state inference.
        "inferred_states": planner_result.inferred_states,

        # v2.3 routing explanation.
        "routing_candidates": planner_result.routing_candidates,

        # v2.2 interventions.
        "interventions": planner_result.interventions,

        # Execution attempts.
        "attempts": attempts,

        "planner_outcome": planner_result.outcome.value,

        "evidence_outcome": evidence_outcome,

        "policy_outcome": policy_outcome,

        "selected_strategy": (
            planner_result.result.strategy_name.value
            if planner_result.result
            else None
        ),

        "final_strategy_used": (
            planner_result.result.strategy_name.value
            if planner_result.result
            else None
        ),

        "final_confidence": (
            planner_result.result.confidence
            if planner_result.result
            else None
        ),

        "final_reasoning": (
            planner_result.result.reasoning
            if planner_result.result
            else None
        ),

        "final_latency_ms": (
            planner_result.result.latency_ms
            if planner_result.result
            else None
        ),

        "final_metadata": (
            planner_result.result.metadata or None
            if planner_result.result
            else None
        ),

        "final_documents_count": (
            len(planner_result.result.documents)
            if planner_result.result
            else 0
        ),
    }


# ---------------------------------------------------------------------------
# Audit record
# ---------------------------------------------------------------------------


def build_audit_record(
    planner_result: PlannerResult,
    query_text: str,
) -> dict:
    """
    Fields for AuditLog construction.
    """

    return {
        "query": query_text,

        "strategy_used": (
            planner_result.result.strategy_name.value
            if planner_result.result
            else None
        ),

        "strategy_attempts": planner_result.attempts,

        "planner_outcome": planner_result.outcome.value,

        "result_summary": (
            f"{len(planner_result.attempts)} strategies attempted"
        ),

        # v2.3 routing explanation.
        "routing_candidates": planner_result.routing_candidates,
    }


# ---------------------------------------------------------------------------
# User response
# ---------------------------------------------------------------------------


def build_user_response(
    planner_result: PlannerResult,
) -> dict:
    """
    Renders the EXTERNAL response.

    ACCESS_DENIED and NO_EVIDENCE remain deliberately indistinguishable.
    """

    if (
        planner_result.outcome == PlannerOutcome.SUCCESS
        and planner_result.result is not None
    ):
        return {
            "answer_available": True,
            "strategy_used": (
                planner_result.result.strategy_name.value
            ),
            "confidence": planner_result.result.confidence,
            "documents": planner_result.result.documents,
            "reasoning": planner_result.result.reasoning,
        }

    return {
        "answer_available": False,
        "message": (
            "I don't have enough evidence to answer this confidently."
        ),
        "confidence": 0.0,
        "documents": [],
    }