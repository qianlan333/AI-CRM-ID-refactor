from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import tools.check_phase6c_task_groups_owner_switch_tooling as checker


ROOT = Path(__file__).resolve().parents[1]
PLAN_YAML = ROOT / "docs/development/phase_6c_task_groups_owner_switch_tooling.yaml"


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", report["blockers"]


def test_tooling_is_default_blocked_without_runtime_gate() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert data["tooling"]["runtime_gate_modified"] is False
    assert data["tooling"]["tooling_only"] is True
    assert data["tooling"]["disabled_by_default"] is True
    assert data["default_evidence"]["blocked_by_default"] is True


def test_required_env_and_args_are_declared() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert set(data["required_env_gates"]) == checker.REQUIRED_ENV
    assert set(data["required_args"]) == checker.REQUIRED_ARGS


def test_authorizations_all_false_and_continuity_true() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert all(value is False for value in data["authorizations"].values())
    assert all(value is True for value in data["business_continuity"].values())


def test_default_runner_evidence_is_blocked_and_non_effectful() -> None:
    for runner in checker.RUNNERS:
        proc = subprocess.run([sys.executable, str(runner)], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        data = json.loads(proc.stdout)
        assert data["overall"] == "BLOCKED"
        assert data["owner_switch_executed"] is False
        assert data["production_compat_changed"] is False
        assert data["fallback_removed"] is False
        assert data["timer_execution_triggered"] is False
        assert data["automation_execution_triggered"] is False
        assert data["outbound_send_triggered"] is False
        assert data["delete_ready"] is False


def test_next_bundle_is_phase6d_without_default_execution_authorization() -> None:
    next_bundle = checker.load_yaml(PLAN_YAML)["next_bundle"]
    assert next_bundle["recommended_next_step"] == "phase_6d_internal_metadata_owner_switch_batch_bundle"
    assert next_bundle["owner_switch_execution_allowed_default"] is False
    assert next_bundle["production_compat_change_allowed"] is False
    assert next_bundle["fallback_removal_allowed"] is False
