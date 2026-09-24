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

from fastapi import APIRouter, Depends, HTTPException
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


@router.post("")
async def query(request: QueryRequest, db: Session = Depends(get_db)):
    start = time.perf_counter()

    QUERY_TOTAL.inc()
    ACTIVE_QUERIES.inc()

    try:
        planner_result = _plan_and_log(request, db)
        response = build_user_response(planner_result)
        return {"question": request.question, **response}
    finally:
        QUERY_DURATION.observe(time.perf_counter() - start)
        ACTIVE_QUERIES.dec()


@router.post("/trace")
async def query_trace(request: QueryRequest, db: Session = Depends(get_db)):
    if not settings.trace_endpoint_enabled:
        raise HTTPException(status_code=404, detail="Not found")

    start = time.perf_counter()

    QUERY_TOTAL.inc()
    ACTIVE_QUERIES.inc()

    try:
        planner_result = _plan_and_log(request, db)
        trace = build_trace_response(planner_result)
        return {"question": request.question, **trace}
    finally:
        QUERY_DURATION.observe(time.perf_counter() - start)
        ACTIVE_QUERIES.dec()