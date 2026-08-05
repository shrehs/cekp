"""
PolicyEvaluator: answers exactly one question -- "can this user/context
execute this strategy?" -- and nothing else. Kept deliberately separate
from the Planner so the real Security Gateway can plug in here later
without the planner's orchestration logic changing at all.

v1 policy is a placeholder: GRAPH access requires an explicit
department allowlist (dependency/relationship data is treated as more
sensitive than plain document text); every other strategy is open.
This is NOT a real RBAC implementation -- it's a seam for one to plug
into. See docs/planner.md, Known v1 Limitations.
"""
from app.planner.context import PlannerContext
from app.planner.enums import StrategyName

# Placeholder policy: departments allowed to use GraphStrategy.
# Replace with a real call into the Security Gateway's RBAC model.
GRAPH_ALLOWED_DEPARTMENTS = {"engineering", "admin"}


class PolicyEvaluator:
    def is_authorized(self, strategy_name: StrategyName, context: PlannerContext) -> bool:
        if strategy_name == StrategyName.GRAPH:
            if context.department is None:
                return False  # unknown department -> deny, don't assume
            return context.department.lower() in GRAPH_ALLOWED_DEPARTMENTS

        # VECTOR, HYBRID, AGENTIC: open in v1. Real document-level
        # sensitivity filtering still happens inside each strategy's
        # underlying retrieval call (Qdrant payload / Postgres metadata),
        # this evaluator only gates *strategy* access, not document access.
        return True
