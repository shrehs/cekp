#!/usr/bin/env python3
"""
CEKP Reliability Experiment — v2.3

Runs the full reliability loop against the live stack:

  Phase 0: Baseline
    Send a graph-routed query. Verify Graph is healthy and returns evidence.

  Phase 1: Inject failures
    Pause the Neo4j container. Send graph-routed queries and record the
    actual observed retrieval result. A pause does not imply a particular
    driver exception or timeout.
    The in-process StrategyHealthMonitor records each ERROR.
    After enough failures (>= 60% of window), Graph becomes UNAVAILABLE.

  Phase 2: Observe skip
    Send another graph-routed query.
    The monitor infers UNAVAILABLE. The planner skips Graph.
    Hybrid fallback runs. Verify evidence-backed result.
    Capture the full /query/trace showing the intervention.

  Phase 3: Restore
    Unpause Neo4j. For each request while Graph is UNAVAILABLE, run a
    real Neo4j dependency probe that grants one bounded retrieval trial.
    Only the resulting real retrieval observation updates the health window.

  Phase 4: Verify recovery
    Send a graph-routed query. Verify Graph is attempted again (no skip).

Each phase captures:
  - /query/trace response (full intervention record)
  - Prometheus metric snapshot (strategy_state gauge, recovery counters)
  - Structured log line (query_outcome)

The experiment result is saved to docs/reliability-experiment-<timestamp>.json
and docs/reliability-experiment-<timestamp>.md.

Run (fault injection is deliberately opt-in):
  python scripts/run_reliability_experiment.py --allow-fault-injection --confirm-test-environment

Requires:
  - Full CEKP stack running (docker compose up)
  - Docker available on PATH (for container pause/unpause)
  - /query/trace endpoint enabled
"""

import json
import argparse
import subprocess
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx

API = "http://localhost:8080"
PROMETHEUS = "http://localhost:9090"
NEO4J_CONTAINER = "docker-neo4j-1"

# A query that the intent classifier routes to GRAPH first.
# "What does X import?" matches get_module_imports in GraphStrategy._SUB_PATTERNS.
GRAPH_QUERY = "What does app.main import?"

# A query that routes through Graph first (for skip detection) with Vector fallback.
GRAPH_WITH_FALLBACK_QUERY = "Which functions are defined in app.planner.planner?"

# A query that routes Hybrid and returns evidence -- used in Phase 2 to
# verify the system returns evidence-backed results when Graph is unavailable.
HYBRID_EVIDENCE_QUERY = "How does the planner escalate strategies?"

# Window size and unavailable threshold must match the live monitor defaults.
# StrategyHealthMonitor defaults: window=10, unavailable_error_rate=0.6
# So 6 errors in 10 observations -> UNAVAILABLE.
# We send 10 failures to be safe (fills the window completely).
FAILURES_TO_INJECT = 10

@dataclass(frozen=True)
class ExperimentConfig:
    api_base_url: str = API
    neo4j_container: str = NEO4J_CONTAINER
    failure_mode: str = "pause"
    experiment_mode: str = "full"
    warmup_count: int = 0
    repeated_failure_count: int = FAILURES_TO_INJECT
    measurement_sample_count: int = 1
    output_directory: Path = Path("docs")
    prometheus_url: str = PROMETHEUS
    allow_fault_injection: bool = False
    confirm_test_environment: bool = False


CONFIG = ExperimentConfig()
_FAULT_CONTAINER_PAUSED = False


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class PhaseResult:
    phase: str
    description: str
    measurement_boundary: str = "not_measured"
    evaluation: dict = field(default_factory=dict)
    queries: list[dict] = field(default_factory=list)
    metrics_snapshot: dict = field(default_factory=dict)
    observations: list[str] = field(default_factory=list)
    passed: bool = False


@dataclass
class ExperimentResult:
    timestamp: str
    phases: list[PhaseResult] = field(default_factory=list)
    configuration: dict = field(default_factory=dict)
    cleanup_attempted: bool = False
    cleanup_succeeded: bool | None = None
    cleanup_error: str | None = None
    recovery_milestones: dict[str, bool | None] = field(default_factory=dict)
    error: str | None = None
    conclusion: str = ""
    passed: bool = False


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def query_trace(question: str, department: str = "engineering") -> dict:
    """POST /query/trace and return the full trace dict."""
    try:
        r = httpx.post(
            f"{CONFIG.api_base_url}/query/trace",
            json={"question": question, "department": department},
            timeout=30.0,
        )
        r.raise_for_status()
        return r.json()
    except httpx.TimeoutException:
        return {"_error": "timeout", "planner_outcome": "failed", "evidence_outcome": "not_evaluated",
                "attempts": [], "interventions": [], "inferred_states": {}}
    except Exception as e:
        return {"_error": str(e), "planner_outcome": "failed", "evidence_outcome": "not_evaluated",
                "attempts": [], "interventions": [], "inferred_states": {}}


def prometheus_query(promql: str) -> float | None:
    """Run an instant PromQL query and return the scalar value."""
    try:
        r = httpx.get(
            f"{CONFIG.prometheus_url}/api/v1/query",
            params={"query": promql},
            timeout=5.0,
        )
        data = r.json()
        results = data.get("data", {}).get("result", [])
        if results:
            return float(results[0]["value"][1])
        return None
    except Exception:
        return None


def metric_snapshot() -> dict:
    """Capture the current values of all recovery-related metrics."""
    return {
        "strategy_state_graph": prometheus_query('cekp_strategy_state{strategy="graph"}'),
        "strategy_state_hybrid": prometheus_query('cekp_strategy_state{strategy="hybrid"}'),
        "recovery_attempts_graph": prometheus_query('cekp_recovery_attempts_total{strategy="graph"}'),
        "recovery_success_graph_hybrid": prometheus_query(
            'cekp_recovery_success_total{skipped_strategy="graph",fallback_strategy="hybrid"}'
        ),
        "retrieval_attempts_graph_error": prometheus_query(
            'cekp_retrieval_attempts_total{strategy="graph",outcome="error"}'
        ),
        "retrieval_attempts_graph_skipped": prometheus_query(
            'cekp_retrieval_attempts_total{strategy="graph",outcome="skipped_unavailable"}'
        ),
    }


def _probe_monitor(strategy: str) -> dict:
    """Probe the real backing dependency and request one bounded retrieval trial."""
    try:
        r = httpx.post(
            f"{CONFIG.api_base_url}/query/monitor/probe",
            params={"strategy": strategy},
            timeout=5.0,
        )
        return r.json()
    except Exception as e:
        return {"_error": str(e)}


def _get_monitor_state() -> dict:
    """GET /query/monitor to read current inferred states."""
    try:
        r = httpx.get(f"{CONFIG.api_base_url}/query/monitor", timeout=5.0)
        return r.json().get("inferred_states", {})
    except Exception:
        return {}


def docker_pause(container: str) -> bool:
    try:
        result = subprocess.run(
            ["docker", "pause", container],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return False
    inspected = _docker_inspect(container)
    paused = bool(inspected and inspected.get("State", {}).get("Paused"))
    return inspected is not None and paused


def docker_unpause(container: str) -> bool:
    try:
        result = subprocess.run(
            ["docker", "unpause", container],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return False
    inspected = _docker_inspect(container)
    still_paused = bool(inspected and inspected.get("State", {}).get("Paused"))
    return inspected is not None and result.returncode == 0 and not still_paused


def _docker_inspect(container: str) -> dict | None:
    try:
        result = subprocess.run(
            [
                "docker",
                "inspect",
                "--format",
                "{{json .}}",
                container,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def verify_fault_target(config: ExperimentConfig) -> tuple[bool, list[str]]:
    """Verify that destructive injection targets the intended local Compose Neo4j."""
    problems = []
    parsed = urlparse(config.api_base_url)
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        problems.append("fault injection requires an API URL on the local machine")
        return False, problems

    inspected = _docker_inspect(config.neo4j_container)
    if inspected is None:
        problems.append(f"container does not exist or Docker inspect failed: {config.neo4j_container}")
        return False, problems

    labels = inspected.get("Config", {}).get("Labels") or {}
    state = inspected.get("State", {})
    if labels.get("com.docker.compose.service") != "neo4j":
        problems.append("target container is not labeled as the Compose neo4j service")
    if state.get("Status") != "running":
        problems.append(f"target container is not running: {state.get('Status')}")
    if state.get("Paused"):
        problems.append("target container is already paused")
    return not problems, problems


def preflight(config: ExperimentConfig) -> tuple[bool, list[str]]:
    """Check API, Neo4j readiness, and internal monitoring endpoints."""
    problems = []
    try:
        health = httpx.get(f"{config.api_base_url}/health", timeout=5.0)
        if health.status_code != 200:
            problems.append(f"/health returned HTTP {health.status_code}")
    except Exception as exc:
        problems.append(f"API is unreachable: {exc}")

    try:
        ready = httpx.get(f"{config.api_base_url}/ready", timeout=5.0)
        body = ready.json()
        if ready.status_code != 200 or body.get("status") != "ready":
            problems.append(f"/ready is not ready: {body}")
        elif body.get("dependencies", {}).get("neo4j") != "ok":
            problems.append("Neo4j is not ready according to /ready")
    except Exception as exc:
        problems.append(f"Neo4j readiness check failed: {exc}")

    try:
        monitor = httpx.get(f"{config.api_base_url}/query/monitor", timeout=5.0)
        if monitor.status_code != 200:
            problems.append(f"/query/monitor returned HTTP {monitor.status_code}")
    except Exception as exc:
        problems.append(f"monitor endpoint is unreachable: {exc}")

    try:
        trace = httpx.get(f"{config.api_base_url}/query/trace", timeout=5.0)
        if trace.status_code == 404:
            problems.append("/query/trace is disabled")
        elif trace.status_code not in {200, 405}:
            problems.append(f"/query/trace returned unexpected HTTP {trace.status_code}")
    except Exception as exc:
        problems.append(f"trace endpoint is unreachable: {exc}")

    try:
        metrics = httpx.get(f"{config.api_base_url}/metrics", timeout=5.0)
        if metrics.status_code != 200:
            problems.append(f"/metrics returned HTTP {metrics.status_code}")
    except Exception as exc:
        problems.append(f"metrics endpoint is unreachable: {exc}")

    return not problems, problems


def _trace_summary(trace: dict) -> dict:
    """Extract the fields that matter for the experiment record."""
    return {
        "request_id": trace.get("request_id"),
        "planner_outcome": trace.get("planner_outcome"),
        "evidence_outcome": trace.get("evidence_outcome"),
        "retrieval_succeeded": trace.get("retrieval_succeeded"),
        "evidence_backed": trace.get("evidence_backed"),
        "selected_strategy": trace.get("selected_strategy"),
        "final_documents_count": trace.get("final_documents_count", 0),
        "final_confidence": trace.get("final_confidence"),
        "final_latency_ms": trace.get("final_latency_ms"),
        "inferred_states": trace.get("inferred_states", {}),
        "interventions": trace.get("interventions", []),
        "attempts": [
            {
                "strategy": a.get("strategy"),
                "outcome": a.get("outcome"),
                "confidence": a.get("confidence"),
                "latency_ms": a.get("latency_ms"),
            }
            for a in trace.get("attempts", [])
        ],
        "_error": trace.get("_error"),
    }


def _evidence_backed(summary: dict) -> bool:
    """Require the validated outcome contract, not merely HTTP/planner success."""
    return (
        summary.get("evidence_outcome") == "evidence_backed"
        and summary.get("evidence_backed") is not False
        and summary.get("final_documents_count", 0) > 0
    )


# ---------------------------------------------------------------------------
# Experiment phases
# ---------------------------------------------------------------------------

def phase_0_baseline() -> PhaseResult:
    """
    Verify the system is healthy before injecting failures.
    Graph should be attempted and return evidence (or at least be attempted).
    """
    phase = PhaseResult(
        phase="0_baseline",
        description="Verify Graph is healthy and the system is in a known good state.",
        measurement_boundary="baseline",
    )
    print("\n[Phase 0] Baseline — verifying healthy state")

    for i in range(CONFIG.warmup_count):
        query_trace(GRAPH_QUERY)
        print(f"  warm-up {i + 1}/{CONFIG.warmup_count}")

    summaries = []
    for i in range(CONFIG.measurement_sample_count):
        trace = query_trace(GRAPH_QUERY)
        summary = _trace_summary(trace)
        summaries.append(summary)
        phase.queries.append({"question": GRAPH_QUERY, "trace": summary})
        print(f"  sample {i + 1}/{CONFIG.measurement_sample_count}")

    summary = summaries[-1]
    phase.metrics_snapshot = metric_snapshot()

    graph_state = summary["inferred_states"].get("graph", "healthy")  # fresh = healthy
    graph_attempted = any(
        a["strategy"] == "graph" and a["outcome"] != "skipped_unavailable"
        for a in summary["attempts"]
    )

    phase.observations.append(f"planner_outcome: {summary['planner_outcome']}")
    phase.observations.append(f"evidence_outcome: {summary['evidence_outcome']}")
    phase.observations.append(f"graph inferred_state: {graph_state}")
    phase.observations.append(f"graph attempted (not skipped): {graph_attempted}")
    phase.observations.append(f"selected_strategy: {summary['selected_strategy']}")
    phase.observations.append(f"documents: {summary['final_documents_count']}")

    # Baseline passes if Graph was attempted (not skipped) and planner didn't fail
    phase.passed = graph_attempted and _evidence_backed(summary)
    print(f"  planner_outcome: {summary['planner_outcome']}")
    print(f"  graph attempted: {graph_attempted}")
    print(f"  passed: {phase.passed}")
    return phase


def phase_1_isolated_fault() -> PhaseResult:
    """Inject one confirmed pause and record the actual single-request result."""
    phase = PhaseResult(
        phase="1_isolated_fault",
        description=(
            f"Injected fault: pause {CONFIG.neo4j_container}; execute one graph "
            "request and record the observed driver/API outcome."
        ),
        measurement_boundary="isolated_fault",
    )
    print(f"\n[Phase 1] Isolated fault — pausing {CONFIG.neo4j_container}")

    global _FAULT_CONTAINER_PAUSED
    paused = docker_pause(CONFIG.neo4j_container)
    _FAULT_CONTAINER_PAUSED = paused
    phase.observations.append(f"container pause confirmed: {paused}")
    if not paused:
        phase.observations.append("No request executed because pause was not confirmed.")
        return phase

    summary = _trace_summary(query_trace(GRAPH_QUERY))
    phase.queries.append({"question": GRAPH_QUERY, "trace": summary})
    graph_attempt = next(
        (attempt for attempt in summary["attempts"] if attempt["strategy"] == "graph"),
        None,
    )
    observed_outcome = graph_attempt["outcome"] if graph_attempt else summary.get("_error", "no_attempt")
    phase.observations.extend(
        [
            f"request_id: {summary['request_id']}",
            f"observed_graph_outcome: {observed_outcome}",
            f"planner_outcome: {summary['planner_outcome']}",
            f"evidence_outcome: {summary['evidence_outcome']}",
            f"fallback_selected_strategy: {summary['selected_strategy']}",
            f"documents: {summary['final_documents_count']}",
        ]
    )
    # This phase validates observation, not recovery. A graph attempt or an
    # explicit API failure is sufficient; the observed classification is not
    # guessed from the injected pause.
    phase.passed = bool(graph_attempt or summary.get("_error"))
    return phase


def phase_1_inject_failures() -> PhaseResult:
    """
    Pause Neo4j and send graph-routed queries. Record the observed driver/API
    result; a paused container does not guarantee a specific exception type.
    After enough observed errors in the monitor window, Graph becomes
    UNAVAILABLE.
    """
    phase = PhaseResult(
        phase="1_inject_failures",
        description=(
            f"Injected fault: {CONFIG.failure_mode} on {CONFIG.neo4j_container}; "
            f"send {CONFIG.repeated_failure_count} graph queries and record observed outcomes."
        ),
        measurement_boundary="injected_fault",
    )
    print(f"\n[Phase 1] Injecting failures — {CONFIG.failure_mode} {CONFIG.neo4j_container}")

    if CONFIG.failure_mode != "pause":
        raise RuntimeError(f"Unsupported failure mode: {CONFIG.failure_mode}")

    global _FAULT_CONTAINER_PAUSED
    paused = docker_pause(CONFIG.neo4j_container)
    _FAULT_CONTAINER_PAUSED = paused
    if not paused:
        phase.observations.append(f"WARNING: could not pause {CONFIG.neo4j_container}")
        print(f"  WARNING: docker pause failed — continuing anyway")
    else:
        phase.observations.append(f"Neo4j container paused: {CONFIG.neo4j_container}")
        print(f"  Neo4j paused")

    if not paused:
        phase.observations.append(
            "Fault injection did not confirm a paused container; no measurements were taken."
        )
        phase.passed = False
        return phase

    # Send queries and record the actual observed result. A paused container
    # does not guarantee a particular driver exception or timeout.
    error_count = 0
    for i in range(CONFIG.repeated_failure_count):
        print(f"  failure query {i+1}/{CONFIG.repeated_failure_count}...", end=" ", flush=True)
        trace = query_trace(GRAPH_QUERY)
        summary = _trace_summary(trace)
        phase.queries.append({"question": GRAPH_QUERY, "trace": summary})

        graph_attempt = next(
            (a for a in summary["attempts"] if a["strategy"] == "graph"), None
        )
        if graph_attempt:
            outcome = graph_attempt["outcome"]
        elif summary.get("_error"):  # API timed out = graph ran and failed inside the API
            outcome = "api_timeout_counted_as_error"
        else:
            outcome = "no_attempt"

        if outcome in ("error", "skipped_unavailable", "api_timeout_counted_as_error"):
            error_count += 1
        print(f"{outcome}")

    phase.metrics_snapshot = metric_snapshot()
    phase.observations.append(f"queries sent: {CONFIG.repeated_failure_count}")
    phase.observations.append(
        f"graph error/skip outcomes: {error_count}/{CONFIG.repeated_failure_count}"
    )

    # Phase passes if we got enough errors to drive the monitor toward UNAVAILABLE
    phase.passed = error_count >= 6
    print(f"  error/skip count: {error_count}/{CONFIG.repeated_failure_count}")
    print(f"  passed: {phase.passed}")
    return phase


def phase_2_observe_skip() -> PhaseResult:
    """
    With Neo4j still paused:
    - Send a graph-routed query to observe the skip and intervention.
    - Send a hybrid-routed query to verify evidence-backed fallback.

    These are two separate queries because no single query routes through
    Graph first AND has strong enough Hybrid/Vector fallback content.
    The skip observation and the fallback evidence verification are
    distinct claims and are tested separately.
    """
    phase = PhaseResult(
        phase="2_observe_skip",
        description="Verify Graph is skipped (UNAVAILABLE) and fallback returns evidence.",
        measurement_boundary="fault_observation",
    )
    print("\n[Phase 2] Observing skip -- Graph should be UNAVAILABLE")

    # Query 1: graph-routed, observe the skip
    print(f"  skip query: {GRAPH_WITH_FALLBACK_QUERY[:55]}")
    trace_skip = query_trace(GRAPH_WITH_FALLBACK_QUERY)
    summary_skip = _trace_summary(trace_skip)
    phase.queries.append({"question": GRAPH_WITH_FALLBACK_QUERY, "trace": summary_skip})

    graph_skipped = any(
        a["strategy"] == "graph" and a["outcome"] == "skipped_unavailable"
        for a in summary_skip["attempts"]
    )
    intervention_recorded = len(summary_skip["interventions"]) > 0
    graph_state = summary_skip["inferred_states"].get("graph", "unknown")

    print(f"  graph_state: {graph_state}")
    print(f"  graph_skipped: {graph_skipped}")
    print(f"  intervention_recorded: {intervention_recorded}")

    # Query 2: hybrid-routed, verify evidence-backed fallback
    print(f"  fallback query: {HYBRID_EVIDENCE_QUERY[:55]}")
    trace_fallback = query_trace(HYBRID_EVIDENCE_QUERY)
    summary_fallback = _trace_summary(trace_fallback)
    phase.queries.append({"question": HYBRID_EVIDENCE_QUERY, "trace": summary_fallback})

    fallback_strategy = summary_fallback["selected_strategy"]
    evidence_backed = summary_fallback["evidence_outcome"] == "evidence_backed"

    print(f"  fallback strategy: {fallback_strategy}")
    print(f"  evidence_backed: {evidence_backed}")
    print(f"  documents: {summary_fallback['final_documents_count']}")

    phase.metrics_snapshot = metric_snapshot()
    phase.observations.append(f"skip query: {GRAPH_WITH_FALLBACK_QUERY}")
    phase.observations.append(f"graph inferred_state: {graph_state}")
    phase.observations.append(f"graph skipped: {graph_skipped}")
    phase.observations.append(f"intervention recorded: {intervention_recorded}")
    if summary_skip["interventions"]:
        phase.observations.append(f"intervention detail: {json.dumps(summary_skip['interventions'][0])}")
    phase.observations.append(f"fallback query: {HYBRID_EVIDENCE_QUERY}")
    phase.observations.append(f"fallback strategy: {fallback_strategy}")
    phase.observations.append(f"planner_outcome: {summary_fallback['planner_outcome']}")
    phase.observations.append(f"evidence_outcome: {summary_fallback['evidence_outcome']}")
    phase.observations.append(f"documents: {summary_fallback['final_documents_count']}")

    phase.passed = graph_skipped and intervention_recorded and evidence_backed
    print(f"  passed: {phase.passed}")
    return phase


def phase_3_restore() -> PhaseResult:
    """
    Unpause Neo4j. While Graph is UNAVAILABLE, each request first performs a
    real dependency probe that grants at most one real retrieval trial.
    Only real retrieval observations age out errors in the sliding window.
    """
    phase = PhaseResult(
        phase="3_restore",
        description="Restore Neo4j and verify recovery through bounded real retrieval trials.",
        measurement_boundary="post_recovery",
    )
    print(f"\\n[Phase 3] Restoring -- unpausing {CONFIG.neo4j_container}")

    unpaused = docker_unpause(CONFIG.neo4j_container)
    if not unpaused:
        phase.observations.append(f"WARNING: could not unpause {CONFIG.neo4j_container}")
        print("  WARNING: docker unpause failed")
    else:
        phase.observations.append(f"Neo4j container unpaused: {CONFIG.neo4j_container}")
        print("  Neo4j unpaused")
        global _FAULT_CONTAINER_PAUSED
        _FAULT_CONTAINER_PAUSED = False

    print("  waiting 10s for Neo4j to accept connections...")
    time.sleep(10)

    try:
        r = httpx.get(f"{CONFIG.api_base_url}/ready", timeout=5.0)
        deps = r.json().get("dependencies", {})
        neo4j_ok = deps.get("neo4j") == "ok"
    except Exception:
        neo4j_ok = False

    phase.observations.append(f"Neo4j reachable via /ready: {neo4j_ok}")
    print(f"  Neo4j reachable: {neo4j_ok}")

    graph_retrieval_count = 0
    evidence_backed_count = 0
    for i in range(max(5, CONFIG.measurement_sample_count)):
        if _get_monitor_state().get("graph") == "unavailable":
            probe_result = _probe_monitor("graph")
            phase.queries.append({"recovery_probe": probe_result})
        restore_count = max(5, CONFIG.measurement_sample_count)
        print(f"  restore query {i+1}/{restore_count}...", end=" ", flush=True)
        trace = query_trace(GRAPH_QUERY)
        summary = _trace_summary(trace)
        phase.queries.append({"question": GRAPH_QUERY, "trace": summary})

        graph_attempt = next(
            (a for a in summary["attempts"] if a["strategy"] == "graph"), None
        )
        outcome = graph_attempt["outcome"] if graph_attempt else "no_attempt"
        if outcome not in ("error", "skipped_unavailable", "no_attempt"):
            graph_retrieval_count += 1
        if _evidence_backed(summary):
            evidence_backed_count += 1
        print(f"{outcome} (planner: {summary['planner_outcome']})")

    phase.metrics_snapshot = metric_snapshot()
    phase.observations.append(f"restore queries sent: {max(5, CONFIG.measurement_sample_count)}")
    restore_count = max(5, CONFIG.measurement_sample_count)
    phase.observations.append(f"Neo4j readiness probe succeeded: {neo4j_ok}")
    phase.observations.append(
        f"graph retrieval requests with non-error attempts: "
        f"{graph_retrieval_count}/{restore_count}"
    )
    phase.observations.append(
        f"evidence-backed graph retrievals: {evidence_backed_count}/{restore_count}"
    )
    phase.observations.append("Dependency probes do not write synthetic retrieval successes.")
    final_monitor_state = _get_monitor_state().get("graph", "unknown")
    phase.evaluation = {
        "infrastructure_recovered": neo4j_ok,
        "retrieval_recovered": evidence_backed_count >= 5,
        "health_monitor_state_after_trials": final_monitor_state,
        "health_monitor_recovered": final_monitor_state == "healthy",
    }
    phase.observations.append(f"graph health monitor state after trials: {final_monitor_state}")
    phase.observations.append(
        f"health monitor recovered: {phase.evaluation['health_monitor_recovered']}"
    )
    phase.passed = (
        phase.evaluation["infrastructure_recovered"]
        and phase.evaluation["retrieval_recovered"]
    )
    print(f"  graph retrieval attempts: {graph_retrieval_count}/{restore_count}")
    print(f"  evidence-backed retrievals: {evidence_backed_count}/{restore_count}")
    print(f"  passed: {phase.passed}")
    return phase


def phase_4_verify_recovery() -> PhaseResult:
    """
    Send one final query. Graph should be HEALTHY again and attempted normally.
    No skip, no intervention.
    """
    phase = PhaseResult(
        phase="4_verify_recovery",
        description="Verify Graph is HEALTHY again and attempted without intervention.",
        measurement_boundary="post_recovery_verification",
    )
    print("\n[Phase 4] Verifying recovery — Graph should be HEALTHY")

    summary = None
    for i in range(CONFIG.measurement_sample_count):
        trace = query_trace(GRAPH_QUERY)
        summary = _trace_summary(trace)
        phase.queries.append({"question": GRAPH_QUERY, "trace": summary})
        print(f"  recovery sample {i + 1}/{CONFIG.measurement_sample_count}")

    assert summary is not None
    phase.metrics_snapshot = metric_snapshot()

    graph_state = summary["inferred_states"].get("graph", "healthy")
    graph_attempted = any(
        a["strategy"] == "graph" and a["outcome"] != "skipped_unavailable"
        for a in summary["attempts"]
    )
    no_intervention = len(summary["interventions"]) == 0

    phase.observations.append(f"graph inferred_state: {graph_state}")
    phase.observations.append(f"graph attempted (not skipped): {graph_attempted}")
    phase.observations.append(f"no intervention: {no_intervention}")
    phase.observations.append(f"planner_outcome: {summary['planner_outcome']}")
    phase.observations.append(f"evidence_outcome: {summary['evidence_outcome']}")
    phase.observations.append(f"selected_strategy: {summary['selected_strategy']}")

    print(f"  graph_state: {graph_state}")
    print(f"  graph_attempted: {graph_attempted}")
    print(f"  no_intervention: {no_intervention}")
    print(f"  planner_outcome: {summary['planner_outcome']}")

    final_monitor_state = summary["inferred_states"].get("graph", "unknown")
    phase.evaluation = {
        "infrastructure_recovered": None,
        "retrieval_recovered": _evidence_backed(summary),
        "health_monitor_state": final_monitor_state,
        "health_monitor_recovered": final_monitor_state == "healthy",
    }
    phase.observations.append(f"graph health monitor state: {final_monitor_state}")
    phase.observations.append(
        f"retrieval recovered: {phase.evaluation['retrieval_recovered']}"
    )
    phase.observations.append(
        f"health monitor recovered: {phase.evaluation['health_monitor_recovered']}"
    )

    phase.passed = (
        graph_attempted
        and no_intervention
        and phase.evaluation["retrieval_recovered"]
    )
    print(f"  passed: {phase.passed}")
    return phase


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_markdown(result: ExperimentResult) -> str:
    lines = [
        "# CEKP Reliability Experiment Report",
        f"\n**Run:** {result.timestamp}",
        f"\n**Overall result:** {'PASSED' if result.passed else 'FAILED'}",
        f"\n**Configuration:** `{json.dumps(result.configuration, sort_keys=True)}`",
        f"\n**Cleanup:** {'PASSED' if result.cleanup_succeeded else 'FAILED'}",
        "\n## Recovery milestones\n",
        *[
            f"- **{milestone.replace('_', ' ').title()}:** {achieved}"
            for milestone, achieved in result.recovery_milestones.items()
        ],
        "\n---\n",
        "## What this experiment tests",
        "",
        "The full reliability loop from `docs/reliability-loop.md`:",
        "",
        "```",
        "Observation  →  State inference  →  Decision  →  Intervention  →  Outcome  →  Verification",
        "```",
        "",
        "Concretely:",
        "",
        "```",
        "Graph healthy (baseline)",
        "  ↓ Neo4j paused",
        "Observed graph failures accumulate in sliding window",
        "  ↓ error rate >= 60%",
        "Monitor infers UNAVAILABLE",
        "  ↓ planner consults monitor",
        "Graph skipped — intervention recorded",
        "  ↓ planner tries Hybrid",
        "Hybrid returns evidence-backed result",
        "  ↓ Neo4j unpaused, successes flow in",
        "Monitor returns to HEALTHY",
        "  ↓ next request",
        "Graph attempted again — no skip — evidence verified",
        "```",
        "",
        "---\n",
    ]

    for phase in result.phases:
        status = "PASSED" if phase.passed else "FAILED"
        lines.append(f"## Phase {phase.phase.split('_', 1)[1].replace('_', ' ').title()} — {status}")
        lines.append(f"\n_{phase.description}_\n")
        lines.append(f"**Measurement boundary:** `{phase.measurement_boundary}`\n")

        if phase.observations:
            lines.append("**Observations:**\n")
            for obs in phase.observations:
                lines.append(f"- {obs}")
            lines.append("")

        if phase.metrics_snapshot:
            lines.append("**Prometheus snapshot:**\n")
            for k, v in phase.metrics_snapshot.items():
                lines.append(f"- `{k}`: {v}")
            lines.append("")

        # Show the key trace for the last query in each phase
        trace_queries = [query for query in phase.queries if "trace" in query]
        if trace_queries:
            last = trace_queries[-1]["trace"]
            lines.append("**Trace (last query in phase):**\n")
            lines.append("```json")
            lines.append(json.dumps(last, indent=2))
            lines.append("```\n")

    lines.append("---\n")
    lines.append(f"## Conclusion\n\n{result.conclusion}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> ExperimentConfig:
    parser = argparse.ArgumentParser(
        description="Run the CEKP live Neo4j reliability experiment safely."
    )
    parser.add_argument("--api-base-url", default=API)
    parser.add_argument("--neo4j-container", default=NEO4J_CONTAINER)
    parser.add_argument(
        "--experiment-mode",
        choices=("full", "isolated"),
        default="full",
        help="Run the repeated-failure loop or one isolated fault request.",
    )
    parser.add_argument(
        "--failure-mode",
        choices=("pause",),
        default="pause",
        help="Destructive fault mechanism. Only Docker pause is currently supported.",
    )
    parser.add_argument("--warm-up-count", type=int, default=0)
    parser.add_argument("--repeated-failure-count", type=int, default=FAILURES_TO_INJECT)
    parser.add_argument("--measurement-sample-count", type=int, default=1)
    parser.add_argument("--output-directory", type=Path, default=Path("docs"))
    parser.add_argument("--prometheus-url", default=PROMETHEUS)
    parser.add_argument(
        "--allow-fault-injection",
        action="store_true",
        help="Explicitly allow pausing the target Neo4j container.",
    )
    parser.add_argument(
        "--confirm-test-environment",
        action="store_true",
        help="Confirm that the local Docker Compose Neo4j target is disposable test infrastructure.",
    )
    args = parser.parse_args()

    for name in ("repeated_failure_count", "measurement_sample_count"):
        if getattr(args, name) < 1:
            parser.error(f"--{name.replace('_', '-')} must be at least 1")
    if args.experiment_mode == "full" and args.repeated_failure_count < 6:
        parser.error("--repeated-failure-count must be at least 6 to reach the monitor threshold")
    if args.warm_up_count < 0:
        parser.error("--warm-up-count cannot be negative")

    return ExperimentConfig(
        api_base_url=args.api_base_url.rstrip("/"),
        neo4j_container=args.neo4j_container,
        failure_mode=args.failure_mode,
        experiment_mode=args.experiment_mode,
        warmup_count=args.warm_up_count,
        repeated_failure_count=args.repeated_failure_count,
        measurement_sample_count=args.measurement_sample_count,
        output_directory=args.output_directory,
        prometheus_url=args.prometheus_url.rstrip("/"),
        allow_fault_injection=args.allow_fault_injection,
        confirm_test_environment=args.confirm_test_environment,
    )


def main():
    global CONFIG, _FAULT_CONTAINER_PAUSED
    CONFIG = parse_args()
    _FAULT_CONTAINER_PAUSED = False

    print("=" * 70)
    print("CEKP Reliability Experiment")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 70)

    ready_ok, preflight_problems = preflight(CONFIG)
    if not ready_ok:
        print("Preflight failed:")
        for problem in preflight_problems:
            print(f"  - {problem}")
        return 1
    print("Preflight passed: API, Neo4j, and monitoring endpoints are reachable.")

    if not CONFIG.allow_fault_injection or not CONFIG.confirm_test_environment:
        print(
            "Refusing destructive fault injection. Both "
            "--allow-fault-injection and --confirm-test-environment are required."
        )
        return 2

    target_ok, target_problems = verify_fault_target(CONFIG)
    if not target_ok:
        print("Fault target verification failed:")
        for problem in target_problems:
            print(f"  - {problem}")
        return 2
    print(f"Fault target verified: local Compose neo4j container {CONFIG.neo4j_container}")

    result = ExperimentResult(
        timestamp=datetime.now().isoformat(),
        configuration={
            "api_base_url": CONFIG.api_base_url,
            "neo4j_container": CONFIG.neo4j_container,
            "failure_mode": CONFIG.failure_mode,
            "experiment_mode": CONFIG.experiment_mode,
            "warmup_count": CONFIG.warmup_count,
            "repeated_failure_count": CONFIG.repeated_failure_count,
            "measurement_sample_count": CONFIG.measurement_sample_count,
            "output_directory": str(CONFIG.output_directory),
        },
    )
    try:
        p0 = phase_0_baseline()
        result.phases.append(p0)

        p1 = (
            phase_1_isolated_fault()
            if CONFIG.experiment_mode == "isolated"
            else phase_1_inject_failures()
        )
        result.phases.append(p1)

        if CONFIG.experiment_mode == "full":
            p2 = phase_2_observe_skip()
            result.phases.append(p2)

        p3 = phase_3_restore()
        result.phases.append(p3)
        if not _FAULT_CONTAINER_PAUSED and result.cleanup_succeeded is None:
            result.cleanup_attempted = True
            result.cleanup_succeeded = True

        p4 = phase_4_verify_recovery()
        result.phases.append(p4)

    except KeyboardInterrupt:
        result.error = "Experiment interrupted by operator."
        print("\nExperiment interrupted.")
    except Exception as e:
        result.error = str(e)
        print(f"\nExperiment error: {e}")
    finally:
        if _FAULT_CONTAINER_PAUSED:
            result.cleanup_attempted = True
            print(f"\n[Cleanup] Ensuring {CONFIG.neo4j_container} is unpaused")
            result.cleanup_succeeded = docker_unpause(CONFIG.neo4j_container)
            if not result.cleanup_succeeded:
                result.cleanup_error = (
                    f"Failed to unpause {CONFIG.neo4j_container}; "
                    "manual operator intervention is required."
                )
                print(f"  CLEANUP FAILURE: {result.cleanup_error}")
            else:
                print("  Cleanup succeeded")

    restore_evaluation = next(
        (phase.evaluation for phase in result.phases if phase.phase == "3_restore"),
        {},
    )
    verification_evaluation = next(
        (
            phase.evaluation
            for phase in result.phases
            if phase.phase == "4_verify_recovery"
        ),
        {},
    )
    result.recovery_milestones = {
        "infrastructure_restored": restore_evaluation.get("infrastructure_recovered"),
        "retrieval_recovered": (
            restore_evaluation.get("retrieval_recovered")
            if restore_evaluation.get("retrieval_recovered") is not None
            else verification_evaluation.get("retrieval_recovered")
        ),
        "monitor_recovered": (
            verification_evaluation.get("health_monitor_recovered")
            if verification_evaluation.get("health_monitor_recovered") is not None
            else restore_evaluation.get("health_monitor_recovered")
        ),
        "cleanup_verified": result.cleanup_succeeded,
    }

    # Evaluate overall result
    expected_phase_count = 4 if CONFIG.experiment_mode == "isolated" else 5
    all_passed = (
        len(result.phases) == expected_phase_count
        and result.error is None
        and all(p.passed for p in result.phases)
        and result.cleanup_succeeded is True
    )
    result.passed = all_passed

    fallback_worked = len(result.phases) > 2 and result.phases[2].passed
    recovery_confirmed = len(result.phases) > 4 and result.phases[4].passed

    if result.error is not None:
        result.conclusion = (
            f"The experiment did not complete: {result.error} "
            "See the phase results and cleanup status."
        )
    elif all_passed:
        result.conclusion = (
            "The full reliability loop executed correctly. "
            "Graph became UNAVAILABLE after injected failures, "
            "the planner skipped it and fell back to Hybrid with an evidence-backed result, "
            "and Graph recovered to HEALTHY after Neo4j was restored. "
            "The monitor does not leave a strategy UNAVAILABLE forever."
        )
    elif fallback_worked and not recovery_confirmed:
        result.conclusion = (
            "Fallback worked correctly (Graph skipped, Hybrid returned evidence) "
            "but recovery to HEALTHY was not confirmed. "
            "The sliding window may need more successful observations, "
            "or Neo4j took longer than expected to accept connections after unpause."
        )
    elif not fallback_worked:
        result.conclusion = (
            "Fallback did not work as expected. "
            "Either the monitor did not reach UNAVAILABLE (not enough errors recorded) "
            "or the Hybrid strategy did not return evidence. "
            "Check the phase 2 trace for details."
        )
    else:
        result.conclusion = "Partial pass — see individual phase results."
    if result.cleanup_succeeded is not True:
        result.conclusion += " Cleanup did not complete successfully; manual restoration is required."

    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    CONFIG.output_directory.mkdir(parents=True, exist_ok=True)
    json_path = CONFIG.output_directory / f"reliability-experiment-{timestamp}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(asdict(result), f, indent=2)
    print(f"\nJSON saved: {json_path}")

    md_path = CONFIG.output_directory / f"reliability-experiment-{timestamp}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(generate_markdown(result))
    print(f"Report saved: {md_path}")

    print(f"\n{'='*70}")
    print(f"RESULT: {'PASSED' if result.passed else 'FAILED'}")
    for phase_number, phase in enumerate(result.phases):
        print(f"  Phase {phase_number}: {'PASS' if phase.passed else 'FAIL'}")
    print(f"\n{result.conclusion}")
    print("=" * 70)

    return 0 if result.passed else 1


if __name__ == "__main__":
    exit(main())
