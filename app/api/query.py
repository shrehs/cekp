"""
Query endpoints. /query goes through the Planner and returns the safe,
redacted external response. /query/trace returns the full internal
trace unredacted -- meant for debugging and demos, not the actual end
user asking the question.

The trace endpoint's gate is enforced in code, not just documented:
if settings.trace_endpoint_enabled is False, the route returns 404
(not 403 -- a 403 confirms the endpoint exists, a 404 doesn't, matching
the same no-leakage logic used in build_user_response()).

Audit logging is deliberately non-fatal: the planner has already
computed the answer by the time we try to log it, so a DB or
serialization failure in the audit write should never turn into a 500
for the user. (This is exactly the bug found during integration
validation -- a numpy.bool_ in strategy_attempts broke json
serialization at the audit-log write, which at the time DID crash the
whole request. Root cause fixed at the source in hybrid_search.py and
defensively in planner.py; this try/except is the second, independent
layer -- logging should never be able to take down the response path,
regardless of what future bug might reintroduce a non-serializable
value.)
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.models.db_models import AuditLog
from app.models.schemas import QueryRequest
from app.planner.context import PlannerContext
from app.planner.planner import (
    Planner,
    PlannerResult,
    build_audit_record,
    build_trace_response,
    build_user_response,
)
import time
from app.core.metrics import (
    QUERY_TOTAL,
    QUERY_DURATION,
    ACTIVE_QUERIES,
)
from app.planner.enums import PlannerOutcome, StrategyName, StrategyOutcome
from app.planner.planner import _policy_outcome

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/query", tags=["query"])

# Single shared planner instance -- strategies/registry are cheap to
# hold in memory, no per-request construction needed.
_planner = Planner()


def _plan_and_log(request: QueryRequest, db: Session) -> PlannerResult:
    context = PlannerContext(query=request.question, department=request.department)
    planner_result = _planner.plan(context)

    try:
        db.add(AuditLog(**build_audit_record(planner_result, request.question)))
        db.commit()
    except Exception:
        # Never let an audit-logging failure prevent the user from
        # getting the answer the planner already computed. Roll back so
        # the session isn't left in a broken state for anything else
        # that might use it later in this request.
        logger.exception("Failed to write audit log for query: %r", request.question)
        db.rollback()

    return planner_result


def _log_query_outcome(
    request_id: str | None,
    planner_result: "PlannerResult",
    latency_ms: float,
) -> None:
    """Emit one structured log line per query with all observable dimensions."""
    r = planner_result.result
    if planner_result.outcome == PlannerOutcome.FAILED:
        evidence_outcome = "not_evaluated"
    else:
        evidence_outcome = "evidence_backed" if (r and r.documents) else "no_evidence"

    logger.info(
        "query_outcome",
        extra={
            "request_id": request_id,
            "planner_outcome": planner_result.outcome.value,
            "evidence_outcome": evidence_outcome,
            "policy_outcome": _policy_outcome(planner_result.attempts),
            "selected_strategy": r.strategy_name.value if r else None,
            "ranked_strategies": planner_result.ranked_strategies,
            "final_confidence": float(r.confidence) if r and r.confidence is not None else None,
            "final_documents_count": len(r.documents) if r else 0,
            "latency_ms": round(latency_ms, 2),
        },
    )


@router.post("")
async def query(http_request: Request, request: QueryRequest, db: Session = Depends(get_db)):
    start = time.perf_counter()
    request_id = getattr(http_request.state, "request_id", None)

    QUERY_TOTAL.inc()
    ACTIVE_QUERIES.inc()

    try:
        planner_result = _plan_and_log(request, db)
        latency_ms = (time.perf_counter() - start) * 1000
        _log_query_outcome(request_id, planner_result, latency_ms)
        response = build_user_response(planner_result)
        return {"question": request.question, **response}
    finally:
        QUERY_DURATION.observe(time.perf_counter() - start)
        ACTIVE_QUERIES.dec()


@router.post("/trace")
async def query_trace(
    http_request: Request,
    request: QueryRequest,
    db: Session = Depends(get_db),
):
    if not settings.trace_endpoint_enabled:
        raise HTTPException(status_code=404, detail="Not found")

    start = time.perf_counter()

    QUERY_TOTAL.inc()
    ACTIVE_QUERIES.inc()

    try:
        planner_result = _plan_and_log(request, db)
        latency_ms = (time.perf_counter() - start) * 1000
        _log_query_outcome(getattr(http_request.state, "request_id", None), planner_result, latency_ms)
        trace = build_trace_response(
            planner_result,
            request_id=getattr(http_request.state, "request_id", None),
            http_status=200,
            http_outcome="ok",
            http_latency_ms=latency_ms,
        )
        return {"question": request.question, **trace}
    finally:
        QUERY_DURATION.observe(time.perf_counter() - start)
        ACTIVE_QUERIES.dec()


@router.get("/monitor")
async def monitor_state():
    """
    Return the current inferred state for all observed strategies.
    Gated behind trace_endpoint_enabled -- internal use only.
    """
    if not settings.trace_endpoint_enabled:
        raise HTTPException(status_code=404, detail="Not found")
    return {"inferred_states": _planner.monitor.snapshot()}


@router.post("/monitor/probe")
async def monitor_probe(strategy: str):
    """
    Probe the backing dependency and, if reachable, permit one real retrieval
    trial for an UNAVAILABLE strategy. A dependency probe is not a retrieval
    success and does not alter the health window.
    """
    if not settings.trace_endpoint_enabled:
        raise HTTPException(status_code=404, detail="Not found")
    try:
        strategy_name = StrategyName(strategy)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown strategy: {strategy}")

    if _planner.monitor.state(strategy_name).value != "unavailable":
        raise HTTPException(
            status_code=409,
            detail="A recovery trial is only needed when the strategy is unavailable.",
        )

    try:
        if strategy_name == StrategyName.GRAPH:
            from app.core.graph_store import get_driver

            with get_driver().session() as session:
                result = session.run("RETURN 1 AS healthy").single()
                if result is None or result["healthy"] != 1:
                    raise RuntimeError("Neo4j health query returned no result")
        else:
            # Vector, hybrid, and agentic retrieval depend on Qdrant.
            from app.core.vector_store import get_client

            get_client().get_collections()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Dependency probe failed for {strategy_name.value}; strategy remains unavailable.",
        ) from exc

    granted = _planner.monitor.grant_recovery_trial(strategy_name)
    if not granted:
        raise HTTPException(
            status_code=409,
            detail="A recovery trial is already pending/in flight, or the strategy is no longer unavailable.",
        )

    return {
        "strategy": strategy_name.value,
        "dependency_probe": "ok",
        "recovery_trial_granted": True,
        "state": _planner.monitor.state(strategy_name).value,
        "note": "Health remains unavailable until real retrieval observations update the window.",
    }
