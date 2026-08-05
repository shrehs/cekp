"""
PlannerContext: the single object threaded through classification,
policy evaluation, and retrieval.

Deliberately does NOT hold a user object, JWT, or raw request --
those belong to the auth layer, not the planner. Every field here
has a concrete consumer today except `history`, which is reserved
for future multi-turn retrieval and is not read by anything in v1
(see docs/planner.md, Known v1 Limitations).
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class PlannerContext:
    query: str
    department: str | None = None
    role: str | None = None
    filters: dict = field(default_factory=dict)
    history: list[str] | None = None
