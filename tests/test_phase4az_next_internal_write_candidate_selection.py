from __future__ import annotations

import json
import subprocess
from pathlib import Path

import tools.check_phase4az_next_internal_write_candidate_selection as checker


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_4az_next_internal_write_candidate_selection.md"
PLAN_YAML = ROOT / "docs/development/phase_4az_next_internal_write_candidate_selection.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"


def test_checker_current_repo_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_selection_package_is_docs_only() -> None:
    data = checker.load_yaml(PLAN_YAML)
    package = data["selection_package"]
    assert package["type"] == "next_low_risk_internal_write_candidate_selection"
    assert package["docs_tools_tests_state_only"] is True
    assert package["runtime_implementation_included"] is False


def test_previous_candidate_paused_by_656() -> None:
    data = checker.load_yaml(PLAN_YAML)
    previous = data["previous_candidate"]
    assert previous["route_family"] == checker.WORKFLOW_NODES
    assert previous["paused_by_pr"] == "#656"
    assert previous["owner_approval_required"] is True


def test_tasks_selected_with_guardrails() -> None:
    data = checker.load_yaml(PLAN_YAML)
    selected = data["selected_candidate"]
    assert selected["selected_route_family"] == checker.TASKS
    assert selected["replacement_phase"] == "phase_4_internal_write"
    assert selected["replacement_category"] == "internal_write"
    assert selected["current_runtime_owner"] == "production_compat"
    assert selected["production_behavior"] == "legacy_forward"
    assert checker.REQUIRED_GUARDRAILS <= set(selected["required_guardrails"])
    assert checker.REQUIRED_SCOPE <= set(selected["phase_4ba_scope"])


def test_authorizations_false() -> None:
    data = checker.load_yaml(PLAN_YAML)
    for field in checker.AUTH_FALSE_FIELDS:
        assert data["authorizations"][field] is False


def test_phase_execution_state_advances_to_tasks_metadata_planning() -> None:
    state = checker.load_yaml(STATE)
    assert state["active_candidate"] == checker.TASKS
    assert state["last_merged_pr"] == "#656"
    assert state["last_attempted_action"] == "phase_4az_next_internal_write_candidate_selection"
    assert state["recommended_next_pr"] == "phase_4ba_tasks_metadata_planning"
    assert state["owner_approval_required"] is False
    assert state["next_allowed_actions"] == ["phase_4ba_tasks_metadata_planning"]
    assert "phase_4az_next_internal_write_candidate_selection_completed" in state["completed_steps"]
    readiness = state["tasks_readiness"]
    assert readiness["metadata_planning_ready"] is True
    assert readiness["run_due_excluded"] is True
    assert readiness["task_execution_excluded"] is True
    assert readiness["workflow_execution_excluded"] is True
    assert readiness["timer_execution_excluded"] is True
    assert readiness["outbound_send_excluded"] is True
    assert readiness["runtime_implementation_ready"] is False
    assert readiness["production_owner_switch_ready"] is False
    assert readiness["production_write_ready"] is False
    assert readiness["fallback_removal_ready"] is False
    assert readiness["delete_ready"] is False


def test_docs_do_not_claim_forbidden_states() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    for phrase in checker.FORBIDDEN_DOC_CLAIMS:
        assert phrase not in text


def test_no_runtime_files_changed_if_git_diff_available() -> None:
    proc = subprocess.run(
        ["git", "diff", "--name-only", "origin/main...HEAD"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        return
    changed = {line.strip() for line in proc.stdout.splitlines() if line.strip()}
    assert not any(path.startswith("aicrm_next/") for path in changed)
    assert not any(path.startswith("wecom_ability_service/") for path in changed)
    assert not any(path.startswith("migrations/") for path in changed)
    assert not any(path.startswith("deploy/") for path in changed)
