# CEKP Telemetry Diagnosis: Before and After Internal Planner Spans

**Date:** 2026-10-01
**Query:** `Which services depend on the auth service?`

## Query Result

The query was sent to `/query/trace` with an engineering department context. The API returned HTTP 200 with:

- ranked strategies: `graph`, `vector`
- graph outcome: `not_implemented`
- vector outcome: `success`
- vector confidence: `0.28747344`
- vector threshold: `0.55`
- final planner outcome: `no_evidence`
- final documents: `0`

The vector strategy returned five candidates, but its confidence did not clear the planner threshold, so the candidates were not exposed as an answer.

## Before Instrumentation

The earlier trace was:

- Jaeger trace ID: `e3d749b47bdaae102115041f60f71aa0`
- span count: `8`
- overall `POST /query/trace`: approximately `102.55 ms`

It showed the API request lifecycle and database activity:

- HTTP receive/send
- `POST /query/trace`
- PostgreSQL connection
- audit-log `INSERT`

It did not show:

- intent classification
- ranked strategy selection
- policy authorization
- individual retrieval strategy execution
- confidence threshold evaluation
- document counts per strategy

## After Instrumentation

The repeated query produced:

- Jaeger trace ID: `7f2652d4ef132f344707da41cd58f600`
- span count: `13`
- overall request duration: approximately `192.66 s`

The new internal spans were:

| Span | Important attributes |
|---|---|
| `planner.intent_classification` | `ranked_strategies=graph,vector`, query length `42` |
| `planner.policy_check` | graph authorized, vector authorized |
| `retrieval.strategy.graph` | `outcome=not_implemented`, confidence `0`, documents `0` |
| `planner.confidence_evaluation` | graph confidence `0`, threshold `0.6`, cleared `false` |
| `retrieval.strategy.vector` | `outcome=success`, confidence `0.28747344`, documents `5` |
| `planner.confidence_evaluation` | vector confidence `0.28747344`, threshold `0.55`, cleared `false` |
| PostgreSQL `INSERT cekp` | audit record persisted |

The long vector span, approximately `192.59 s`, identifies a cold-start/model-loading cost in this run. The trace makes that latency visible, but does not break model loading into separate spans.

## Prometheus Comparison

Prometheus reported approximately two query events in the ten-minute window, including the earlier and repeated demonstrations:

- query count increase: approximately `2`
- `no_evidence` outcome increase: approximately `2`
- graph `not_implemented` attempt increase: approximately `2`
- vector `success` attempt increase: approximately `2`
- final retrieval strategy increase: none
- final planner confidence observations: none
- final retrieved-document observations: none

The absence of final strategy/confidence/document metrics is consistent with the trace: the vector strategy returned candidates, but no strategy cleared the planner threshold and became the final answer.

The counters are aggregate time-series values. They confirm the outcome pattern but cannot identify one request without an external before/after sample or request-labeled telemetry.

## Diagnosis

This is a retrieval-quality limitation, not a service outage:

1. The classifier correctly recognized a graph-shaped query.
2. The organization-dependency graph capability is not implemented.
3. The planner escalated to vector retrieval.
4. Vector retrieval returned candidates, but confidence was only `0.287`.
5. The `0.55` threshold rejected the candidates.
6. The planner correctly returned `no_evidence` rather than an unsupported answer.

## What Telemetry Reveals

- The selected strategy order and authorization decisions.
- Which strategies actually ran and their outcomes.
- Per-strategy confidence, threshold, and document counts.
- API and database latency.
- Whether an audit record was written.
- Aggregate query, outcome, and attempt metrics.
- The cold-start cost of the vector path in this run.

## What Telemetry Still Cannot Tell Us

- Which exact document text caused or failed to cause the confidence score.
- Whether the five vector candidates were semantically relevant.
- The internal model operations contributing to the 192-second vector span.
- A direct request-ID join between Jaeger spans and Prometheus samples; the request ID is currently in API logs, not a span attribute or Prometheus label.
- A per-request Prometheus latency value; histograms remain aggregate by design.

The next useful improvement would be to add the request ID as a low-cardinality Jaeger span attribute and add narrower embedding/model-load spans, while keeping request IDs out of Prometheus labels to avoid metric-cardinality growth.
