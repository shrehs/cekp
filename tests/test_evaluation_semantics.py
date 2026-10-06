from scripts.evaluate_query_system import QueryMetric, compute_statistics, percentile
import pytest


def _metric(
    *,
    latency_ms: float,
    planner_outcome: str,
    evidence_outcome: str,
    policy_outcome: str = "allowed",
    http_outcome: str = "ok",
    documents: int = 0,
):
    return QueryMetric(
        question="test",
        category="test",
        expected_intent=None,
        expected_strategy=None,
        actual_intent="vector",
        actual_strategy="vector" if planner_outcome == "success" else "none",
        confidence=0.8 if documents else None,
        latency_ms=latency_ms,
        http_status=200 if http_outcome == "ok" else 500,
        http_outcome=http_outcome,
        planner_outcome=planner_outcome,
        evidence_outcome=evidence_outcome,
        policy_outcome=policy_outcome,
        outcome=planner_outcome if http_outcome == "ok" else "not_evaluated",
        num_results=documents,
        strategy_attempts=["vector"],
        evidence_backed_success=(
            planner_outcome == "success" and evidence_outcome == "evidence_backed"
        ),
        top_result_relevant=None,
    )


def test_percentile_and_frozen_outcome_dimensions_are_reported():
    metrics = [
        _metric(latency_ms=10, planner_outcome="success", evidence_outcome="evidence_backed", documents=2),
        _metric(latency_ms=20, planner_outcome="no_evidence", evidence_outcome="no_evidence"),
        _metric(latency_ms=100, planner_outcome="access_denied", evidence_outcome="no_evidence", policy_outcome="denied"),
        _metric(latency_ms=200, planner_outcome="failed", evidence_outcome="not_evaluated", http_outcome="http_error"),
    ]

    stats = compute_statistics(metrics)

    assert percentile([10, 20, 100, 200], 0.50) == 60
    assert stats["planner_success_rate"] == 0.25
    assert stats["evidence_backed_success_rate"] == 0.25
    assert stats["no_evidence_count"] == 2
    assert stats["policy_denied_count"] == 1
    assert stats["http_error_count"] == 1
    assert stats["latency"]["p95_ms"] == pytest.approx(185)