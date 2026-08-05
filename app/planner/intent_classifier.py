"""
IntentClassifier: rule-based, returns a RANKED LIST of StrategyName
rather than a single choice. This makes escalation trivial (the
planner just walks the list) and sidesteps having to pick a single
winner when a question matches more than one rule set.

Rule priority (checked in this order, first match determines the
primary strategy; VECTOR is always appended last as the universal
fallback):

  1. Relational / multi-hop language -> GRAPH first. Two families of
     patterns here (see GRAPH_PATTERNS comments): org-dependency
     questions ("which services depend on X") and code-structure
     questions ("what does X import"). Only the latter has an
     implemented GraphStrategy in v1 -- see docs/graph-schema.md for
     why both pattern families are kept regardless.
  2. Exact-match language (IDs, error codes, tickets) -> HYBRID first
  3. Open-ended / comparative language -> AGENTIC first
  4. Everything else -> VECTOR only

This is intentionally simple for v1 -- see docs/planner.md,
Known v1 Limitations, for what a learned classifier would change.
"""
import re

from app.planner.context import PlannerContext
from app.planner.enums import StrategyName

# Org-dependency patterns (architecture.md's original schema -- deferred,
# requires entity extraction that doesn't exist yet; see docs/graph-schema.md).
# Kept, not removed: these should keep matching so a query like "which
# services depend on X" correctly routes to GRAPH and gets NOT_IMPLEMENTED
# (honest) rather than silently falling to HYBRID (misleading -- the
# system would look like it just doesn't have graph capability at all,
# instead of "this specific kind of graph question isn't built yet").
#
# Exposed as its own named list (not just folded into GRAPH_PATTERNS) so
# GraphStrategy (app/planner/strategies.py) can import and reuse it
# directly -- GraphStrategy needs to recognize these SPECIFICALLY as
# "recognized but not implemented" (NOT_IMPLEMENTED), distinct from
# "couldn't parse this at all" (LOW_CONFIDENCE), now that it's a real
# implementation rather than an unconditional stub.
ORG_DEPENDENCY_PATTERNS = [
    r"\bdepends? on\b",
    r"\brelationship\b",
    r"\bowner\b",
    r"\bconnected to\b",
    r"\bwho owns\b",
    r"\bwhich (services?|systems?|documents?)\b.*\b(depend|relate|connect)",
]

# Code-structure patterns (v1's actual GraphStrategy target -- see
# docs/graph-schema.md). These match questions the graph CAN answer
# now that GraphStrategy is implemented against the code-structure schema.
CODE_STRUCTURE_PATTERNS = [
    r"\bimports?\b",
    r"\bcalls?\b",
    r"\bdefined in\b",
    r"\bwhich functions?\b",
    r"\bwhich class(es)?\b",
    r"\bwhat does .* (import|call)\b",
    r"\bwhere\s+is\b.*\bdefined\b",  # "Where is X defined?" -- matches GraphStrategy's find_symbol sub-pattern
]

GRAPH_PATTERNS = ORG_DEPENDENCY_PATTERNS + CODE_STRUCTURE_PATTERNS

HYBRID_PATTERNS = [
    r"\berror code\b",
    r"\bticket\b",
    r"\bid\s*[:#]?\s*\d",
    r"\bexact(ly)?\b",
]

AGENTIC_PATTERNS = [
    r"\bcompare\b",
    r"\bsummarize\b",
    r"\brecommend\b",
    r"\bpros and cons\b",
    r"\btrade-?offs?\b",
]


def _matches_any(patterns: list[str], text: str) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


class IntentClassifier:
    def classify(self, context: PlannerContext) -> list[StrategyName]:
        query = context.query or ""

        if not query.strip():
            # Empty query: nothing to classify meaningfully -- fall back
            # to the universal default rather than special-casing it
            # through the whole pipeline.
            return [StrategyName.VECTOR]

        ranked: list[StrategyName] = []

        # Checked in priority order; a query matching multiple rule sets
        # gets all matching strategies, ordered by priority, before the
        # universal VECTOR fallback.
        if _matches_any(GRAPH_PATTERNS, query):
            ranked.append(StrategyName.GRAPH)
        if _matches_any(HYBRID_PATTERNS, query):
            ranked.append(StrategyName.HYBRID)
        if _matches_any(AGENTIC_PATTERNS, query):
            ranked.append(StrategyName.AGENTIC)

        if not ranked:
            # No rule matched -- default to hybrid before vector, since
            # hybrid is a strict superset of vector's signal (vector +
            # keyword) and rarely does worse.
            ranked.append(StrategyName.HYBRID)

        if StrategyName.VECTOR not in ranked:
            ranked.append(StrategyName.VECTOR)  # universal fallback, always last

        return ranked