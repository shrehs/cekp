# Adaptive Retrieval Planner — Design Rationale

This document explains *why* the planner is built the way it is, not just what it does. It's the artifact meant to answer the "why did you choose X" questions in an architecture review.

## Why the Strategy pattern

Each retrieval method (vector, hybrid, graph, agentic) has a different implementation but the same job: take a `PlannerContext`, return a `RetrievalResult`. The `RetrievalStrategy` ABC lets the planner call `strategy.retrieve(context)` without knowing which concrete strategy it's talking to. Adding a new strategy (e.g. RAPTOR, a re-ranking strategy) means writing one new class and registering it — no changes to the planner's orchestration logic.

## Why a ranked list, not a single classification

`IntentClassifier.classify()` returns `list[StrategyName]`, not one winner. Two reasons:

1. A question can legitimately match more than one rule set (e.g. "which service depends on the auth service with error code 500" matches both graph and hybrid patterns). A ranked list lets both be tried, in priority order, instead of forcing a single arbitrary choice.
2. It makes escalation trivial: the planner just walks the list. There's no separate "what do I try if the first choice fails" logic — it's the same list.

## Why escalation uses a loop, not recursion

The escalation chain is capped (`PlannerConfig.max_escalations`, default 4) and has no need to unwind a call stack — a `for` loop over the ranked list is simpler, safer, and has no recursion-depth concern, however deep the ranked list gets.

## Escalate, don't fail (the policy/escalation decision)

When a strategy is denied by policy (`PolicyEvaluator.is_authorized()` returns `False`), the planner does **not** stop the request. It records the denial and tries the next strategy in the ranked list. Rationale: if a user isn't authorized for graph traversal but hybrid search over documents they *are* allowed to read can still answer their question, refusing outright would reduce usability without improving security — the underlying documents are still permission-filtered at the strategy level regardless of which strategy answers.

Denial and low confidence are recorded as different `StrategyOutcome` values (`DENIED_BY_POLICY` vs `LOW_CONFIDENCE`) so the audit trail never conflates "the system chose not to try this" with "the system tried and it didn't work."

## No information leakage on access denial

If every strategy in the ranked list comes back `DENIED_BY_POLICY`, the planner's outcome is `PlannerOutcome.ACCESS_DENIED` — but `build_user_response()` renders this **identically** to `PlannerOutcome.NO_EVIDENCE`: the same "I don't have enough evidence to answer this confidently" message. An unauthorized user should not be able to distinguish "nothing exists for this query" from "something exists but you can't see it" — the second case is itself a minor information leak in a security-conscious system. The real reason is always visible internally, via `strategy_attempts` in the audit log, for anyone with legitimate access to review it.

## Why `StrategyOutcome` and `PlannerOutcome` are separate enums

A strategy can succeed (`StrategyOutcome.SUCCESS`) while the planner still doesn't return that result to the user — e.g. confidence was below threshold, or a later step in a longer pipeline rejects it. Keeping strategy-level and planner-level outcomes as separate enums avoids overloading one enum for two different jobs, and keeps `RetrievalStrategy` implementations honest about only reporting what actually happened at their layer.

## Why GraphStrategy returns `NOT_IMPLEMENTED` for org-dependency questions specifically

`GraphStrategy` is real now — implemented against the code-structure graph (see `docs/graph-schema.md`). But org-dependency questions ("which services depend on X") are a *different*, still-unbuilt capability (needs entity extraction that doesn't exist), and `GraphStrategy` checks for that category first, returning `NOT_IMPLEMENTED` before even attempting a graph query. "This specific capability doesn't exist" and "this ran and wasn't confident" (or "couldn't parse this question at all," which genuinely-unparseable text gets — `LOW_CONFIDENCE`) are different facts, and the audit log shouldn't conflate them. `StrategyRegistry.get()` returning `None` for an unregistered strategy is handled the same way, for the same reason.

## Why `PolicyEvaluator` is separate from `Planner`

The planner's job is orchestration (which strategy, in what order, with what fallback). Authorization is a different concern with a different owner (eventually, the LLM Security Gateway project). Keeping them separate means the Gateway can plug in as a drop-in replacement for `PolicyEvaluator` without any change to `Planner`'s escalation logic.

## Known v1 Limitations

- **Rule-based intent classification.** Keyword/regex patterns, not a learned classifier. A future version could log `(query, chosen_strategy, outcome)` pairs and train a real classifier on accumulated data.
- **Strategy-specific confidence heuristics, not calibrated across strategies.** See `docs/confidence.md`.
- **Graph retrieval returns `NOT_IMPLEMENTED`** until Neo4j integration (Phase 3 of the roadmap).
- **Agentic strategy is a placeholder** — a single hybrid-search call with a conservative confidence heuristic, not true multi-hop decomposition.
- **Planner decisions are deterministic** — no learned routing policy yet.
- **`PlannerContext.history` is reserved, not read.** Nothing in v1 does multi-turn retrieval; the field exists so multi-turn support doesn't require a signature change later.
- **`PolicyEvaluator`'s v1 policy is a placeholder** (department allowlist for `GRAPH` only) — not a real RBAC implementation, just the seam the Security Gateway will plug into.

## `StrategyOutcome.SUCCESS` vs. clearing the planner's threshold

Found during integration validation, worth documenting explicitly: `StrategyOutcome.SUCCESS` means *the strategy produced a result* (e.g. `VectorStrategy` found at least one hit) — it does **not** mean that result was confident enough for the planner to use. That judgment is separate, made by comparing `result.confidence` against `PlannerConfig.threshold_for(strategy_name)`.

A strategy can legitimately return `SUCCESS` with a low confidence (e.g. `0.38` against a `0.55` threshold for vector). The planner correctly treats this as "not good enough, keep escalating" — but the first version of `strategy_attempts` recorded only `outcome: "success"` for this case, making the trace look self-contradictory: an attempt says `success` while `planner_outcome` says `no_evidence`. Both facts were individually correct; only their presentation together was misleading.

Fixed by adding `cleared_threshold` (`true` / `false` / `null`) to each attempt entry, independent of `outcome`:
- `outcome: "success", cleared_threshold: true` — the strategy found something *and* the planner is using it.
- `outcome: "success", cleared_threshold: false` — the strategy found something, but not confidently enough; the planner escalates to the next strategy.
- `cleared_threshold: null` — the strategy never ran at all (denied, missing, or errored), so there's nothing to have cleared a threshold against.

This was a genuine gap, not a design flaw: `PlannerOutcome`/`StrategyOutcome` were always computing correctly (verified by tracing through the exact numbers from the failing case); the trace just wasn't exposing enough information to show *why* a "success" didn't win.