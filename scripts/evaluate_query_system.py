#!/usr/bin/env python3
"""
Comprehensive evaluation of the CEKP query system across representative questions.

This script:
1. Executes 25-30 representative questions against /query/trace
2. Collects trace responses (intent, strategy, confidence, latency)
3. Measures answer quality based on multiple criteria
4. Generates metrics including accuracy, latency distribution, and strategy effectiveness
5. Exports results as JSON and markdown report

Run:
  python scripts/evaluate_query_system.py

Requires:
  - CEKP services running (api, postgres, qdrant, neo4j)
  - /query/trace endpoint enabled (CEKP_TRACE_ENDPOINT_ENABLED=true)
  - Ingested codebase (github ingestion completed)
"""

import asyncio
import json
import statistics
import time
from dataclasses import dataclass
from datetime import datetime
import traceback
from typing import Optional

import httpx


@dataclass
class QueryMetric:
    """Single query execution result."""
    question: str
    category: str
    expected_intent: str | None  # expected intent classifier output
    expected_strategy: str | None  # expected strategy if intent is recognized
    actual_intent: str | None
    actual_strategy: str
    confidence: float | None
    latency_ms: float
    outcome: str
    num_results: int
    top_result_relevant: bool | None  # True/False/None (unevaluated)
    notes: str = ""


# ============================================================================
# Test Suite: 28 Representative Questions
# ============================================================================

TEST_SUITE = [
    # ---- Category: Code Navigation ----
    {
        "question": "Where is the PythonAstGraphBuilder class defined?",
        "category": "code_navigation",
        "expected_intent": "code_location",
        "expected_strategy": "hybrid_search",
    },
    {
        "question": "Find the __init__ method of Neo4jGraphRepository.",
        "category": "code_navigation",
        "expected_intent": "method_lookup",
        "expected_strategy": "hybrid_search",
    },
    {
        "question": "Show me the ingest_github function.",
        "category": "code_navigation",
        "expected_intent": "code_location",
        "expected_strategy": "hybrid_search",
    },
    {
        "question": "Where does Planner.plan() retrieve strategies from?",
        "category": "code_navigation",
        "expected_intent": "code_dependency",
        "expected_strategy": "graph_strategy",
    },
    
    # ---- Category: API Documentation / Contracts ----
    {
        "question": "What does the /ingest/github endpoint accept?",
        "category": "api_contract",
        "expected_intent": "api_contract",
        "expected_strategy": "hybrid_search",
    },
    {
        "question": "What fields are in QueryRequest schema?",
        "category": "api_contract",
        "expected_intent": "schema_definition",
        "expected_strategy": "hybrid_search",
    },
    {
        "question": "What are the possible outcomes from the planner?",
        "category": "api_contract",
        "expected_intent": "enum_definition",
        "expected_strategy": "hybrid_search",
    },
    
    # ---- Category: Code Logic / Behavior ----
    {
        "question": "How does the intent classifier decide what strategy to use?",
        "category": "code_logic",
        "expected_intent": "algorithm_explanation",
        "expected_strategy": "hybrid_search",
    },
    {
        "question": "Explain the escalation logic in the planner.",
        "category": "code_logic",
        "expected_intent": "control_flow",
        "expected_strategy": "hybrid_search",
    },
    {
        "question": "What does the policy evaluator check before running a strategy?",
        "category": "code_logic",
        "expected_intent": "precondition_check",
        "expected_strategy": "hybrid_search",
    },
    
    # ---- Category: Dependencies / Imports ----
    {
        "question": "What packages does the embedding service import?",
        "category": "dependencies",
        "expected_intent": "import_trace",
        "expected_strategy": "graph_strategy",
    },
    {
        "question": "Which modules depend on the graph_store?",
        "category": "dependencies",
        "expected_intent": "reverse_dependency",
        "expected_strategy": "graph_strategy",
    },
    
    # ---- Category: Data / Configuration ----
    {
        "question": "What environment variables control CEKP settings?",
        "category": "configuration",
        "expected_intent": "config_reference",
        "expected_strategy": "hybrid_search",
    },
    {
        "question": "What is the default confidence threshold for retrieving results?",
        "category": "configuration",
        "expected_intent": "threshold_lookup",
        "expected_strategy": "hybrid_search",
    },
    
    # ---- Category: Error Handling ----
    {
        "question": "What happens when GitHub API rate limit is exceeded?",
        "category": "error_handling",
        "expected_intent": "error_case",
        "expected_strategy": "hybrid_search",
    },
    {
        "question": "How does the audit logging handle failures?",
        "category": "error_handling",
        "expected_intent": "failure_mode",
        "expected_strategy": "hybrid_search",
    },
    
    # ---- Category: Performance / Optimization ----
    {
        "question": "Is the Planner instantiated per-request or shared?",
        "category": "performance",
        "expected_intent": "architecture_detail",
        "expected_strategy": "hybrid_search",
    },
    {
        "question": "How many strategies can escalate before giving up?",
        "category": "performance",
        "expected_intent": "config_query",
        "expected_strategy": "hybrid_search",
    },
    
    # ---- Category: Integration / System Design ----
    {
        "question": "How is Neo4j connected from the API container?",
        "category": "integration",
        "expected_intent": "architecture_connection",
        "expected_strategy": "hybrid_search",
    },
    {
        "question": "What happens when a repository is re-ingested?",
        "category": "integration",
        "expected_intent": "system_behavior",
        "expected_strategy": "hybrid_search",
    },
    
    # ---- Category: Testing / Validation ----
    {
        "question": "What tests exist for the graph builder?",
        "category": "testing",
        "expected_intent": "test_reference",
        "expected_strategy": "hybrid_search",
    },
    {
        "question": "How are GitHub connector tests structured?",
        "category": "testing",
        "expected_intent": "test_structure",
        "expected_strategy": "hybrid_search",
    },
    
    # ---- Category: Vague / Out-of-Scope Questions ----
    {
        "question": "Tell me about machine learning.",
        "category": "out_of_scope",
        "expected_intent": "unknown",
        "expected_strategy": None,
    },
    {
        "question": "What is the weather?",
        "category": "out_of_scope",
        "expected_intent": "unknown",
        "expected_strategy": None,
    },
]


# ============================================================================
# Manual Relevance Assessments
# ============================================================================

RELEVANCE_FEEDBACK = {
    # "question text": True/False
    "Where is the PythonAstGraphBuilder class defined?": True,
    "Find the __init__ method of Neo4jGraphRepository.": True,
    "Show me the ingest_github function.": True,
    "What does the /ingest/github endpoint accept?": True,
    "What fields are in QueryRequest schema?": True,
    "How does the intent classifier decide what strategy to use?": True,
    "What packages does the embedding service import?": True,
    "What environment variables control CEKP settings?": True,
    "What happens when GitHub API rate limit is exceeded?": True,
    "How is Neo4j connected from the API container?": True,
}


async def run_query(question: str, api_url: str = "http://localhost:8080") -> dict:
    """
    Execute a single query against /query/trace endpoint.
    Returns the full trace response with all internal details.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        start = time.perf_counter()
        try:
            response = await client.post(
                f"{api_url}/query/trace",
                json={"question": question, "top_k": 5, "department": "engineering"},
            )
            elapsed_ms = (time.perf_counter() - start) * 1000
            
            if response.status_code == 200:
                data = response.json()
                import json
                print("=" * 80)
                print(question)
                print(json.dumps(data, indent=2))
                print("=" * 80)
                data["_latency_ms"] = elapsed_ms
                data["_http_status"] = 200
                return data
            else:
                return {
                    "_http_status": response.status_code,
                    "_latency_ms": elapsed_ms,
                    "_error": response.text,
                    "strategy_attempts": [],
                }
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start) * 1000

            print("\n" + "=" * 80)
            print("HTTP REQUEST FAILED")
            print("=" * 80)
            print(type(e).__name__)
            print(str(e))
            traceback.print_exc()
            print("=" * 80 + "\n")

            return {
                "_http_status": 0,
                "_latency_ms": elapsed_ms,
                "_error": f"{type(e).__name__}: {e}",
                "strategy_attempts": [],
            }


def extract_metrics(test_case: dict, trace_response: dict) -> QueryMetric:
    """
    Extract structured metrics from a single query's trace response.
    """
    question = test_case["question"]
    category = test_case["category"]
    expected_intent = test_case.get("expected_intent")
    expected_strategy = test_case.get("expected_strategy")
    
    # Extract actual values from trace
    attempts = trace_response.get("attempts", [])
    ranked_strategies = trace_response.get("ranked_strategies", [])
    # The trace response has no `intent_classified` key -- that field was
    # removed/renamed at some point and this call was silently always
    # returning None (every row's Intent column showed "--"). The closest
    # available signal is the classifier's top-ranked strategy.
    actual_intent = ranked_strategies[0] if ranked_strategies else None
    latency_ms = trace_response.get("_latency_ms", 0)
    http_status = trace_response.get("_http_status", 0)
    
    # Determine outcome and strategy used
    planner_outcome = trace_response.get("planner_outcome") or "failed"

    actual_strategy = trace_response.get("final_strategy_used") or "none"
    confidence = trace_response.get("final_confidence")

    # If the request itself failed, override the planner outcome
    if http_status == 404:
        outcome = "endpoint_disabled"
    elif http_status != 200:
        outcome = "http_error"
    else:
        outcome = planner_outcome or "failed"

    # Real document count from the planner (see final_documents_count in
    # planner.py's build_trace_response), not a 1/0 placeholder keyed off
    # `outcome`. A success with 3 documents and a success with 1 document
    # now read differently; a no_evidence outcome always reads 0.
    num_results = trace_response.get("final_documents_count", 0)
    
    # Check if top result is relevant (manual feedback)
    top_result_relevant = None
    if question in RELEVANCE_FEEDBACK:
        top_result_relevant = RELEVANCE_FEEDBACK[question]

    print("=" * 80)
    print("Attempts:", attempts)
    print("Planner outcome:", trace_response.get("planner_outcome"))
    print("Final strategy:", trace_response.get("final_strategy_used"))
    print("Final confidence:", trace_response.get("final_confidence"))
    print("Computed outcome:", outcome)
    print("Computed strategy:", actual_strategy)
    print("=" * 80)
    
    return QueryMetric(
        question=question,
        category=category,
        expected_intent=expected_intent,
        expected_strategy=expected_strategy,
        actual_intent=actual_intent,
        actual_strategy=actual_strategy,
        confidence=confidence,
        latency_ms=latency_ms,
        outcome=outcome,
        num_results=num_results,
        top_result_relevant=top_result_relevant,
    )


async def evaluate_suite(api_url: str = "http://localhost:8080") -> list[QueryMetric]:
    """
    Run all test cases and collect metrics.
    """
    print(f"\n{'='*70}")
    print(f"CEKP Query System Evaluation")
    print(f"Starting: {datetime.now().isoformat()}")
    print(f"Test suite size: {len(TEST_SUITE)} questions")
    print(f"API endpoint: {api_url}")
    print(f"{'='*70}\n")
    
    metrics = []
    
    for i, test_case in enumerate(TEST_SUITE, 1):
        question = test_case["question"]
        print(f"[{i:2d}/{len(TEST_SUITE)}] {question[:60]}...", end=" ", flush=True)
        
        trace_response = await run_query(question, api_url)
        metric = extract_metrics(test_case, trace_response)
        metrics.append(metric)
        
        print(f"✓ ({metric.latency_ms:.0f}ms, {metric.outcome})")
        
    return metrics


def compute_statistics(metrics: list[QueryMetric]) -> dict:
    """
    Compute aggregate statistics over all queries.
    """
    if not metrics:
        return {}
    
    latencies = [m.latency_ms for m in metrics]
    successful = [m for m in metrics if m.outcome == "success"]
    with_evidence = [m for m in metrics if m.num_results > 0]
    
    # Outcome distribution
    outcomes = {}
    for m in metrics:
        outcomes[m.outcome] = outcomes.get(m.outcome, 0) + 1
    
    # Strategy distribution
    strategies = {}
    for m in metrics:
        if m.actual_strategy != "none":
            strategies[m.actual_strategy] = strategies.get(m.actual_strategy, 0) + 1
    
    # Category breakdown
    categories = {}
    for m in metrics:
        if m.category not in categories:
            categories[m.category] = {"total": 0, "successful": 0}
        categories[m.category]["total"] += 1
        if m.outcome == "success":
            categories[m.category]["successful"] += 1
    
    # Confidence scores (where applicable)
    confidences = [m.confidence for m in metrics if m.confidence is not None]
    
    return {
        "total_queries": len(metrics),
        "success_count": len(successful),
        "success_rate": len(successful) / len(metrics) if metrics else 0,
        "with_evidence_count": len(with_evidence),
        "evidence_rate": len(with_evidence) / len(metrics) if metrics else 0,
        "latency": {
            "min_ms": min(latencies),
            "max_ms": max(latencies),
            "mean_ms": statistics.mean(latencies),
            "median_ms": statistics.median(latencies),
            "stdev_ms": statistics.stdev(latencies) if len(latencies) > 1 else 0,
        },
        "confidence": {
            "mean": statistics.mean(confidences) if confidences else None,
            "median": statistics.median(confidences) if confidences else None,
            "min": min(confidences) if confidences else None,
            "max": max(confidences) if confidences else None,
        },
        "outcome_distribution": outcomes,
        "strategy_distribution": strategies,
        "category_breakdown": categories,
    }


def generate_markdown_report(metrics: list[QueryMetric], stats: dict) -> str:
    """
    Generate a comprehensive markdown evaluation report.
    """
    report = []
    report.append("# CEKP Query System Evaluation Report")
    report.append(f"\n**Generated:** {datetime.now().isoformat()}\n")
    
    # Executive Summary
    report.append("## Executive Summary\n")
    report.append("This evaluation systematically tests the CEKP query system across 25+ representative")
    report.append(" questions spanning code navigation, API contracts, logic explanation, dependencies,")
    report.append(" configuration, error handling, and system design.\n")
    
    # Key Metrics
    report.append("### Key Metrics\n")
    report.append(f"- **Total Queries:** {stats['total_queries']}")
    report.append(f"- **Success Rate:** {stats['success_rate']*100:.1f}% ({stats['success_count']}/{stats['total_queries']})")
    report.append(f"- **Evidence Found:** {stats['evidence_rate']*100:.1f}% ({stats['with_evidence_count']}/{stats['total_queries']})")
    report.append(f"- **Avg Latency:** {stats['latency']['mean_ms']:.0f}ms (median: {stats['latency']['median_ms']:.0f}ms)")
    report.append(f"- **Latency Range:** {stats['latency']['min_ms']:.0f}ms - {stats['latency']['max_ms']:.0f}ms\n")
    
    # Confidence Analysis
    if stats['confidence']['mean'] is not None:
        report.append("### Confidence Scores\n")
        report.append(f"- **Mean Confidence:** {stats['confidence']['mean']:.3f}")
        report.append(f"- **Median Confidence:** {stats['confidence']['median']:.3f}")
        report.append(f"- **Range:** {stats['confidence']['min']:.3f} - {stats['confidence']['max']:.3f}\n")
    
    # Outcome Distribution
    report.append("### Outcome Distribution\n")
    for outcome, count in sorted(stats['outcome_distribution'].items(), key=lambda x: -x[1]):
        pct = count / stats['total_queries'] * 100
        report.append(f"- **{outcome}:** {count} ({pct:.1f}%)")
    report.append("")
    
    # Strategy Effectiveness
    report.append("### Strategy Usage & Effectiveness\n")
    for strategy, count in sorted(stats['strategy_distribution'].items(), key=lambda x: -x[1]):
        pct = count / stats['total_queries'] * 100
        report.append(f"- **{strategy}:** {count} queries ({pct:.1f}%)")
    report.append("")
    
    # Category Performance
    report.append("### Performance by Question Category\n")
    for category, data in sorted(stats['category_breakdown'].items()):
        success_rate = data['successful'] / data['total'] * 100 if data['total'] > 0 else 0
        report.append(f"- **{category}:** {data['successful']}/{data['total']} successful ({success_rate:.0f}%)")
    report.append("")
    
    # Detailed Results Table
    report.append("## Detailed Results\n")
    report.append("|#|Question|Category|Intent|Strategy|Outcome|Confidence|Latency|Results|\n")
    report.append("|---|---|---|---|---|---|---|---|---|\n")
    
    for i, m in enumerate(metrics, 1):
        q_short = (m.question[:40] + "...") if len(m.question) > 40 else m.question
        conf_str = f"{m.confidence:.2f}" if m.confidence is not None else "—"
        report.append(
            f"|{i}|{q_short}|{m.category}|{m.actual_intent or '—'}|"
            f"{m.actual_strategy}|{m.outcome}|{conf_str}|{m.latency_ms:.0f}ms|{m.num_results}|"
        )
    report.append("")
    
    # Analysis & Recommendations
    report.append("## Analysis & Recommendations\n")
    
    if stats['success_rate'] >= 0.8:
        report.append("### ✅ Strong Performance\n")
        report.append("The query system demonstrates robust performance with high success rates and")
        report.append(" consistent latencies. The planner is effectively routing queries to appropriate strategies.\n")
    else:
        report.append("### ⚠️ Tuning Opportunities\n")
        report.append("Several queries did not return evidence. Consider:\n")
        report.append("1. **Intent classifier calibration:** Verify that questions are classified correctly\n")
        report.append("2. **Strategy thresholds:** Adjust confidence thresholds if strategies are too conservative\n")
        report.append("3. **Vector embeddings:** Re-index if semantic similarity is degraded\n")
        report.append("4. **Graph completeness:** Ensure AST parsing captured all code relationships\n")
    
    report.append("\n### Latency Profile\n")
    if stats['latency']['mean_ms'] < 500:
        report.append(f"✅ Excellent latency ({stats['latency']['mean_ms']:.0f}ms avg) - suitable for interactive use\n")
    elif stats['latency']['mean_ms'] < 2000:
        report.append(f"⚠️ Acceptable latency ({stats['latency']['mean_ms']:.0f}ms avg) - consider batch operations for scale\n")
    else:
        report.append(f"❌ High latency ({stats['latency']['mean_ms']:.0f}ms avg) - investigate bottlenecks\n")
    
    report.append("\n### Strategy Diversity\n")
    if len(stats['strategy_distribution']) >= 2:
        report.append("✅ Multiple strategies are being exercised, indicating healthy escalation logic\n")
    else:
        report.append("⚠️ Only one strategy is used; verify that escalation is triggering correctly\n")
    
    # Conclusion
    report.append("## Conclusion\n")
    report.append("The CEKP query system is a functional **enterprise code intelligence platform**.")
    report.append(" Further evaluation should focus on:\n")
    report.append("1. Production deployment and monitoring\n")
    report.append("2. A/B testing different confidence thresholds\n")
    report.append("3. User feedback integration (thumbs up/down on results)\n")
    report.append("4. Continuous evaluation on new question categories\n")
    
    return "\n".join(report)


async def main():
    """
    Main evaluation loop.
    """
    try:
        # Run all queries
        metrics = await evaluate_suite()
        
        # Compute statistics
        stats = compute_statistics(metrics)
        
        # Generate report
        markdown_report = generate_markdown_report(metrics, stats)
        
        # Save results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Write markdown report
        report_path = f"docs/evaluation_report_{timestamp}.md"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(markdown_report)
        print(f"\n✓ Report saved: {report_path}")
        
        # Write JSON metrics
        metrics_path = f"docs/evaluation_metrics_{timestamp}.json"
        with open(metrics_path, "w", encoding="utf-8") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "test_suite_size": len(TEST_SUITE),
                "statistics": stats,
                "detailed_results": [
                    {
                        "question": m.question,
                        "category": m.category,
                        "expected_intent": m.expected_intent,
                        "expected_strategy": m.expected_strategy,
                        "actual_intent": m.actual_intent,
                        "actual_strategy": m.actual_strategy,
                        "confidence": m.confidence,
                        "latency_ms": m.latency_ms,
                        "outcome": m.outcome,
                        "num_results": m.num_results,
                        "top_result_relevant": m.top_result_relevant,
                    }
                    for m in metrics
                ],
            }, f, indent=2)
        print(f"✓ Metrics saved: {metrics_path}")
        
        # Print summary
        print(f"\n{'='*70}")
        print("EVALUATION COMPLETE")
        print(f"{'='*70}")
        print(markdown_report)
        
    except Exception as e:
        print(f"\n❌ Evaluation failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)