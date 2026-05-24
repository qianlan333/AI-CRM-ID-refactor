from __future__ import annotations

import json
import subprocess
from pathlib import Path

import tools.check_phase4ar_workflows_metadata_plan as checker


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_4ar_workflows_metadata_plan.md"
PLAN_YAML = ROOT / "docs/development/phase_4ar_workflows_metadata_plan.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"


def test_checker_current_repo_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_workflows_candidate_is_metadata_planning_only() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert data["route_family"] == checker.ROUTE
    assert data["current_runtime_owner"] == "production_compat"
    assert data["production_behavior"] == "legacy_forward"
    assert data["legacy_fallback_retained"] is True
    selected = data["selected_candidate"]
    assert selected["route_family"] == checker.ROUTE
    assert selected["replacement_phase"] == "phase_4_internal_write"
    assert selected["replacement_category"] == "internal_write"


def test_previous_task_groups_candidate_remains_paused() -> None:
    data = checker.load_yaml(PLAN_YAML)
    previous = data["previous_candidate"]
    assert previous["route_family"] == checker.TASK_GROUPS
    assert previous["paused_by_pr"] == "#648"
    assert previous["owner_approval_required"] is True


def test_scope_guardrails_and_exclusions_are_complete() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert checker.REQUIRED_SCOPE <= set(data["planned_contract_scope"])
    assert checker.REQUIRED_GUARDRAILS <= set(data["required_guardrails"])
    for field in checker.EXCLUDED_TRUE_FIELDS:
        assert data["excluded_scope"][field] is True


def test_high_risk_authorizations_are_false() -> None:
    data = checker.load_yaml(PLAN_YAML)
    for field in checker.AUTH_FALSE_FIELDS:
        assert data["authorizations"][field] is False


def test_phase_execution_state_keeps_phase_4ar_complete_after_later_progress() -> None:
    state = checker.load_yaml(STATE)
    assert state["active_candidate"] == checker.ROUTE
    assert "phase_4ar_workflows_metadata_planning_completed" in state["completed_steps"]
    workflows = state["workflows_readiness"]
    assert workflows["metadata_planning_completed"] is True
    assert workflows["schema_route_surface_confirmation_ready"] is True
    assert workflows["runtime_implementation_ready"] is False
    assert workflows["production_owner_switch_ready"] is False
    assert workflows["production_write_ready"] is False
    assert workflows["fallback_removal_ready"] is False
    assert workflows["delete_ready"] is False


def test_phase_4as_recommendation_does_not_allow_production_work() -> None:
    data = checker.load_yaml(PLAN_YAML)
    rec = data["phase_4as_recommendation"]
    assert rec["recommended_next_step"] == "workflows_schema_route_surface_confirmation"
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
