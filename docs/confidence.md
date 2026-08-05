# Confidence Scores — Design Rationale

Every `RetrievalResult` carries a `confidence` float. This document explains what that number means for each strategy, and — more importantly — what it does **not** mean.

## Confidence values are strategy-local heuristics

They are **not directly comparable across retrieval methods.** A confidence of `0.6` from `VectorStrategy` and a confidence of `0.6` from `HybridStrategy` are not the same thing measured on the same scale — they're two different heuristics that happen to share a numeric range.

| Strategy | What `confidence` actually is |
|---|---|
| Vector | Raw cosine similarity of the top hit. |
| Hybrid | Weighted combination of cosine similarity and normalized BM25 score for the top result (see `app/services/hybrid_search.py`: `VECTOR_WEIGHT = 0.6`, `BM25_WEIGHT = 0.4`). |
| Graph | Not yet implemented — always `0.0` (see `planner.md`, Known v1 Limitations). Once implemented, the natural heuristic is something like "was a traversal path found at all," which is a fundamentally different kind of signal (near-binary) than a similarity score. |
| Agentic | v1 placeholder: average of the top-3 combined hybrid scores. Explicitly conservative since this isn't true multi-hop decomposition yet. |

## Why this matters

In v1, `confidence` is used for exactly one thing: **deciding whether a given strategy's result clears its own threshold** (`PlannerConfig.threshold_for(strategy_name)`), which determines whether the planner returns that result or escalates to the next strategy in the ranked list. Thresholds are set per strategy precisely because the numbers aren't comparable — there's no single global cutoff that would be equally meaningful for a cosine similarity and a graph-traversal heuristic.

What `confidence` is **not** used for: ranking strategies against each other, deciding which strategy to try first (that's the classifier's job), or being shown to end users as a calibrated probability of correctness. It is an internal escalation signal, not a user-facing accuracy metric.

## Future calibration

A meaningful next step — not done in v1 — would be calibrating each strategy's confidence heuristic against actual correctness on a labeled evaluation set (reusing the RAG Benchmark Suite's methodology), so that thresholds are chosen empirically rather than as reasonable-looking defaults. Until that exists, treat every threshold in `PlannerConfig` as a starting point, not a validated cutoff.
