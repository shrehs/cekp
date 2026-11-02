"""Safety-path regression tests for the live reliability experiment harness."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import run_reliability_experiment as experiment


def _args(monkeypatch, *extra: str) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_reliability_experiment.py", *extra],
    )


def _config(tmp_path: Path, **overrides) -> experiment.ExperimentConfig:
    values = {
        "output_directory": tmp_path,
        "allow_fault_injection": True,
        "confirm_test_environment": True,
    }
    values.update(overrides)
    return experiment.ExperimentConfig(**values)


def test_missing_opt_in_flags_rejects_before_docker_pause(monkeypatch):
    _args(monkeypatch)
    monkeypatch.setattr(experiment, "preflight", lambda config: (True, []))
    monkeypatch.setattr(
        experiment,
        "verify_fault_target",
        lambda config: pytest.fail("target verification must not run"),
    )
    monkeypatch.setattr(
        experiment,
        "docker_pause",
        lambda container: pytest.fail("Docker pause must not run"),
    )

    assert experiment.main() == 2


def test_non_local_api_url_is_rejected(monkeypatch):
    config = _config(Path("docs"), api_base_url="https://shared.example.test")
    monkeypatch.setattr(experiment, "_docker_inspect", lambda container: pytest.fail("must reject URL first"))

    valid, problems = experiment.verify_fault_target(config)

    assert not valid
    assert "local machine" in problems[0]


@pytest.mark.parametrize(
    "inspection",
    [
        {"Config": {"Labels": {"com.docker.compose.service": "postgres"}}, "State": {"Status": "running"}},
        {"Config": {"Labels": {"com.docker.compose.service": "neo4j"}}, "State": {"Status": "paused", "Paused": True}},
    ],
)
def test_invalid_docker_target_is_rejected_without_pause(monkeypatch, inspection):
    config = _config(Path("docs"))
    monkeypatch.setattr(experiment, "_docker_inspect", lambda container: inspection)
    monkeypatch.setattr(
        experiment,
        "docker_pause",
        lambda container: pytest.fail("invalid target must not be paused"),
    )

    valid, problems = experiment.verify_fault_target(config)

    assert not valid
    assert problems


def test_readiness_failure_aborts_before_fault_injection(monkeypatch):
    config = _config(Path("docs"))
    monkeypatch.setattr(experiment.httpx, "get", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("offline")))
    monkeypatch.setattr(
        experiment,
        "docker_pause",
        lambda container: pytest.fail("preflight failure must prevent pause"),
    )

    valid, problems = experiment.preflight(config)

    assert not valid
    assert any("unreachable" in problem for problem in problems)


def test_experiment_failure_attempts_cleanup_and_writes_reports(monkeypatch, tmp_path):
    _args(
        monkeypatch,
        "--allow-fault-injection",
        "--confirm-test-environment",
        "--output-directory",
        str(tmp_path),
    )
    monkeypatch.setattr(experiment, "preflight", lambda config: (True, []))
    monkeypatch.setattr(experiment, "verify_fault_target", lambda config: (True, []))
    monkeypatch.setattr(experiment, "phase_0_baseline", lambda: experiment.PhaseResult("0_baseline", "ok", passed=True))
    def fail_after_pause():
        experiment._FAULT_CONTAINER_PAUSED = True
        raise RuntimeError("injected test failure")

    monkeypatch.setattr(experiment, "phase_1_inject_failures", fail_after_pause)
    cleanup_calls = []
    monkeypatch.setattr(experiment, "docker_unpause", lambda container: cleanup_calls.append(container) or True)

    assert experiment.main() == 1

    assert cleanup_calls == [experiment.NEO4J_CONTAINER]
    reports = list(tmp_path.glob("reliability-experiment-*"))
    assert {path.suffix for path in reports} == {".json", ".md"}
    report = next(path for path in reports if path.suffix == ".json")
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["error"] == "injected test failure"
    assert data["cleanup_attempted"] is True
    assert data["cleanup_succeeded"] is True
    assert data["passed"] is False


def test_operator_interruption_attempts_cleanup_and_records_run(monkeypatch, tmp_path):
    _args(
        monkeypatch,
        "--allow-fault-injection",
        "--confirm-test-environment",
        "--output-directory",
        str(tmp_path),
    )
    monkeypatch.setattr(experiment, "preflight", lambda config: (True, []))
    monkeypatch.setattr(experiment, "verify_fault_target", lambda config: (True, []))
    monkeypatch.setattr(experiment, "phase_0_baseline", lambda: experiment.PhaseResult("0_baseline", "ok", passed=True))
    def interrupt_after_pause():
        experiment._FAULT_CONTAINER_PAUSED = True
        raise KeyboardInterrupt()

    monkeypatch.setattr(experiment, "phase_1_inject_failures", interrupt_after_pause)
    cleanup_calls = []
    monkeypatch.setattr(experiment, "docker_unpause", lambda container: cleanup_calls.append(container) or True)

    assert experiment.main() == 1
    assert cleanup_calls == [experiment.NEO4J_CONTAINER]
    report = next(tmp_path.glob("reliability-experiment-*.json"))
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["error"] == "Experiment interrupted by operator."
    assert data["cleanup_succeeded"] is True


def test_failure_after_injection_records_cleanup_failure(monkeypatch, tmp_path):
    _args(
        monkeypatch,
        "--allow-fault-injection",
        "--confirm-test-environment",
        "--output-directory",
        str(tmp_path),
    )
    monkeypatch.setattr(experiment, "preflight", lambda config: (True, []))
    monkeypatch.setattr(experiment, "verify_fault_target", lambda config: (True, []))
    monkeypatch.setattr(experiment, "phase_0_baseline", lambda: experiment.PhaseResult("0_baseline", "ok", passed=True))
    def fail_after_pause():
        experiment._FAULT_CONTAINER_PAUSED = True
        raise RuntimeError("phase failed")

    monkeypatch.setattr(experiment, "phase_1_inject_failures", fail_after_pause)
    monkeypatch.setattr(experiment, "docker_unpause", lambda container: False)

    assert experiment.main() == 1
    report = next(tmp_path.glob("reliability-experiment-*.json"))
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["cleanup_attempted"] is True
    assert data["cleanup_succeeded"] is False
    assert "manual operator intervention" in data["cleanup_error"]
    assert data["recovery_milestones"]["cleanup_verified"] is False
    assert data["passed"] is False


def test_successful_restore_records_cleanup_completion(monkeypatch, tmp_path):
    _args(
        monkeypatch,
        "--experiment-mode",
        "isolated",
        "--allow-fault-injection",
        "--confirm-test-environment",
        "--output-directory",
        str(tmp_path),
    )
    monkeypatch.setattr(experiment, "preflight", lambda config: (True, []))
    monkeypatch.setattr(experiment, "verify_fault_target", lambda config: (True, []))
    monkeypatch.setattr(
        experiment,
        "phase_0_baseline",
        lambda: experiment.PhaseResult("0_baseline", "ok", passed=True),
    )

    def inject_fault():
        experiment._FAULT_CONTAINER_PAUSED = True
        return experiment.PhaseResult(
            "1_isolated_fault",
            "fault",
            passed=True,
        )

    def restore_fault():
        experiment._FAULT_CONTAINER_PAUSED = False
        return experiment.PhaseResult(
            "3_restore",
            "restore",
            evaluation={
                "infrastructure_recovered": True,
                "retrieval_recovered": True,
                "health_monitor_recovered": False,
            },
            passed=True,
        )

    monkeypatch.setattr(experiment, "phase_1_isolated_fault", inject_fault)
    monkeypatch.setattr(experiment, "phase_3_restore", restore_fault)
    monkeypatch.setattr(
        experiment,
        "phase_4_verify_recovery",
        lambda: experiment.PhaseResult(
            "4_verify_recovery",
            "verify",
            evaluation={
                "retrieval_recovered": True,
                "health_monitor_recovered": True,
            },
            passed=True,
        ),
    )

    assert experiment.main() == 0
    report = next(tmp_path.glob("reliability-experiment-*.json"))
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["cleanup_attempted"] is True
    assert data["cleanup_succeeded"] is True
    assert data["recovery_milestones"] == {
        "infrastructure_restored": True,
        "retrieval_recovered": True,
        "monitor_recovered": True,
        "cleanup_verified": True,
    }
    assert data["passed"] is True
    markdown = next(tmp_path.glob("reliability-experiment-*.md")).read_text(
        encoding="utf-8"
    )
    assert "## Recovery milestones" in markdown
    assert "- **Infrastructure Restored:** True" in markdown
    assert "- **Retrieval Recovered:** True" in markdown
    assert "- **Monitor Recovered:** True" in markdown
    assert "- **Cleanup Verified:** True" in markdown


def test_invalid_failure_count_is_rejected_before_external_state_changes(monkeypatch):
    _args(monkeypatch, "--repeated-failure-count", "5")
    with pytest.raises(SystemExit) as exc_info:
        experiment.parse_args()
    assert exc_info.value.code == 2


def test_http_success_without_evidence_is_not_recovery():
    summary = {
        "evidence_outcome": "no_evidence",
        "evidence_backed": False,
        "final_documents_count": 0,
    }

    assert experiment._evidence_backed(summary) is False


def test_evidence_backed_recovery_requires_documents():
    summary = {
        "evidence_outcome": "evidence_backed",
        "evidence_backed": True,
        "final_documents_count": 1,
    }

    assert experiment._evidence_backed(summary) is True


def test_phase_boundaries_are_explicit():
    assert experiment.phase_0_baseline.__name__ == "phase_0_baseline"
    assert experiment.PhaseResult("0", "baseline", "baseline").measurement_boundary == "baseline"
    assert experiment.PhaseResult("1", "fault", "injected_fault").measurement_boundary == "injected_fault"
    assert experiment.PhaseResult("3", "recovery", "post_recovery").measurement_boundary == "post_recovery"


def test_pause_requires_confirmed_paused_state(monkeypatch):
    monkeypatch.setattr(
        experiment.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1),
    )
    monkeypatch.setattr(
        experiment,
        "_docker_inspect",
        lambda container: {"State": {"Paused": True}},
    )

    assert experiment.docker_pause("neo4j-test") is True


def test_pause_success_without_confirmed_state_does_not_arm_cleanup(monkeypatch):
    monkeypatch.setattr(
        experiment.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0),
    )
    monkeypatch.setattr(experiment, "_docker_inspect", lambda container: None)

    assert experiment.docker_pause("neo4j-test") is False


def test_isolated_mode_allows_single_failure_without_full_threshold(monkeypatch):
    _args(monkeypatch, "--experiment-mode", "isolated", "--repeated-failure-count", "1")

    config = experiment.parse_args()

    assert config.experiment_mode == "isolated"
    assert config.repeated_failure_count == 1


def test_trace_summary_preserves_request_correlation():
    summary = experiment._trace_summary(
        {
            "request_id": "req-isolated",
            "retrieval_succeeded": False,
            "evidence_backed": False,
            "evidence_outcome": "not_evaluated",
            "attempts": [],
        }
    )

    assert summary["request_id"] == "req-isolated"
    assert summary["retrieval_succeeded"] is False
    assert summary["evidence_backed"] is False


def test_recovery_dimensions_are_independent():
    phase = experiment.PhaseResult(
        "3_restore",
        "restore",
        "post_recovery",
        evaluation={
            "infrastructure_recovered": True,
            "retrieval_recovered": True,
            "health_monitor_recovered": False,
        },
    )

    assert phase.evaluation["infrastructure_recovered"] is True
    assert phase.evaluation["retrieval_recovered"] is True
    assert phase.evaluation["health_monitor_recovered"] is False
