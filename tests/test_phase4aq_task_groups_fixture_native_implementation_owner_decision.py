from __future__ import annotations

import json
import subprocess
from pathlib import Path

import tools.check_phase4aq_task_groups_fixture_native_implementation_owner_decision as checker


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_4aq_task_groups_fixture_native_implementation_owner_decision.md"
PLAN_YAML = ROOT / "docs/development/phase_4aq_task_groups_fixture_native_implementation_owner_decision.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"


def test_checker_current_repo_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_owner_decision_package_is_docs_only_and_pauses_task_groups() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert data["decision_package"]["docs_tools_tests_state_only"] is True
    assert data["decision_package"]["runtime_implementation_included"] is False
    assert data["decision_package"]["auto_merge_under_throughput_allowed"] is True
    paused = data["paused_candidate"]
    assert paused["route_family"] == checker.TASK_GROUPS
    assert paused["owner_approval_required"] is True
    assert paused["current_runtime_owner"] == "production_compat"
    assert paused["production_behavior"] == "legacy_forward"


def test_owner_decision_list_is_complete() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert checker.REQUIRED_DECISIONS <= set(data["owner_decision_required"])


def test_next_candidate_is_workflows_planning_only() -> None:
    data = checker.load_yaml(PLAN_YAML)
    candidate = data["next_candidate"]
    assert candidate["selected_route_family"] == checker.WORKFLOWS
    assert candidate["capability_owner"] == "aicrm_next.automation_engine"
    assert candidate["replacement_phase"] == "phase_4_internal_write"
    assert candidate["replacement_category"] == "internal_write"
    assert checker.REQUIRED_GUARDRAILS <= set(candidate["required_guardrails"])


def test_high_risk_authorizations_are_false() -> None:
    data = checker.load_yaml(PLAN_YAML)
    for field in checker.AUTH_FALSE_FIELDS:
        assert data["authorizations"][field] is False


def test_phase_execution_state_marks_task_groups_paused_and_workflows_active() -> None:
    state = checker.load_yaml(STATE)
    assert state["active_candidate"] == checker.WORKFLOWS
    assert state["last_merged_pr"] == "#647"
    assert state["last_attempted_action"] == "phase_4aq_task_groups_fixture_native_implementation_owner_decision"
    assert state["recommended_next_pr"] == "phase_4ar_workflows_metadata_planning"
    assert state["owner_approval_required"] is False
    assert "phase_4aq_task_groups_fixture_native_implementation_owner_decision_completed" in state["completed_steps"]
    assert state["next_allowed_actions"] == ["phase_4ar_workflows_metadata_planning"]
    assert any(
        item["route_family"] == checker.TASK_GROUPS and item["owner_approval_required"] is True
        for item in state["paused_candidates"]
    )
    workflows = state["workflows_readiness"]
    assert workflows["metadata_planning_ready"] is True
    assert workflows["runtime_implementation_ready"] is False
    assert workflows["production_owner_switch_ready"] is False
    assert workflows["production_write_ready"] is False
    assert workflows["fallback_removal_ready"] is False
    assert workflows["delete_ready"] is False


def test_phase_4ar_recommendation_does_not_allow_production_work() -> None:
    data = checker.load_yaml(PLAN_YAML)
    rec = data["phase_4ar_recommendation"]
    assert rec["recommended_next_step"] == "workflows_metadata_planning"
    assert rec["production_write_allowed"] is False
    assert rec["production_route_switch_allowed"] is False
    assert rec["fallback_removal_allowed"] is False
    assert rec["production_write_canary_allowed"] is False


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
