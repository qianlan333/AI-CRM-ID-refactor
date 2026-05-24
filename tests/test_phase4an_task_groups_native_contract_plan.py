from __future__ import annotations

import json
import subprocess
from pathlib import Path

import tools.check_phase4an_task_groups_native_contract_plan as checker


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_4an_task_groups_native_contract_plan.md"
PLAN_YAML = ROOT / "docs/development/phase_4an_task_groups_native_contract_plan.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"


def test_checker_current_repo_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_plan_selects_task_groups_candidate() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert data["route_family"] == "/api/admin/automation-conversion/task-groups*"
    assert data["capability_owner"] == "aicrm_next.automation_engine"
    assert data["current_runtime_owner"] == "production_compat"
    assert data["production_behavior"] == "legacy_forward"
    assert data["legacy_fallback_retained"] is True
    assert data["selected_candidate"]["replacement_phase"] == "phase_4_internal_write"
    assert data["selected_candidate"]["replacement_category"] == "internal_write"


def test_action_templates_paused_by_owner_decision_package() -> None:
    data = checker.load_yaml(PLAN_YAML)
    previous = data["previous_candidate"]
    assert previous["route_family"] == "/api/admin/automation-conversion/action-templates*"
    assert previous["paused_by_pr"] == "#644"
    assert previous["owner_approval_required"] is True


def test_all_high_risk_authorizations_false() -> None:
    data = checker.load_yaml(PLAN_YAML)
    for field in checker.AUTH_FALSE_FIELDS:
        assert data["authorizations"][field] is False


def test_contract_scope_and_guardrails_complete() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert checker.REQUIRED_SCOPE <= set(data["planned_contract_scope"])
    assert checker.REQUIRED_GUARDRAILS <= set(data["required_guardrails"])
    for field in checker.EXCLUDED_TRUE_FIELDS:
        assert data["excluded_scope"][field] is True


def test_phase_execution_state_matches_phase_4an_transition() -> None:
    state = checker.load_yaml(STATE)
    assert state["active_candidate"] == "/api/admin/automation-conversion/task-groups*"
    assert state["owner_approval_required"] is False
    assert "phase_4an_task_groups_native_contract_planning_completed" in state["completed_steps"]
    assert state["action_templates_readiness"]["paused"] is True
    assert state["action_templates_readiness"]["paused_by_pr"] == "#644"
    assert state["task_groups_readiness"]["native_contract_planning_completed"] is True
    assert state["task_groups_readiness"]["production_owner_switch_ready"] is False
    assert state["task_groups_readiness"]["production_write_ready"] is False
    assert state["task_groups_readiness"]["fallback_removal_ready"] is False
    assert state["task_groups_readiness"]["delete_ready"] is False


def test_phase_4ao_recommendation_keeps_production_locked() -> None:
    data = checker.load_yaml(PLAN_YAML)
    rec = data["phase_4ao_recommendation"]
    assert rec["recommended_next_step"] == "task_groups_schema_route_surface_confirmation"
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
