from __future__ import annotations

import json
import subprocess
from pathlib import Path

import tools.check_phase4bi_agent_outputs_metadata_plan as checker


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_4bi_agent_outputs_metadata_plan.md"
PLAN_YAML = ROOT / "docs/development/phase_4bi_agent_outputs_metadata_plan.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"


def test_checker_current_repo_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_plan_is_agent_outputs_metadata_readonly() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert data["status"] == "phase_4bi_agent_outputs_metadata_planning_no_runtime_change"
    assert data["route_family"] == checker.AGENT_OUTPUTS
    assert data["current_runtime_owner"] == "production_compat"
    assert data["production_behavior"] == "legacy_forward"
    assert data["legacy_fallback_retained"] is True
    assert data["planning_scope"]["selected_subset"] == "agent_outputs_metadata_readonly"
    assert set(data["planning_scope"]["allowed_methods_for_future_contract_planning"]) == {"GET"}


def test_included_and_excluded_routes_cover_safe_boundary() -> None:
    data = checker.load_yaml(PLAN_YAML)
    included = {
        (item["method"], item["path"], item["status"])
        for item in data["planning_scope"]["included_routes"]
    }
    assert checker.REQUIRED_INCLUDED_ROUTES <= included
    assert checker.REQUIRED_EXCLUDED_ROUTES <= set(data["planning_scope"]["excluded_routes"])
    assert checker.REQUIRED_EXCLUDED_BEHAVIORS <= set(data["planning_scope"]["excluded_behaviors"])


def test_metadata_model_and_contract_planning_complete() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert checker.REQUIRED_METADATA_FIELDS <= set(data["candidate_metadata_model"]["required_fields"])
    assert checker.REQUIRED_DEFERRED_TABLES <= set(data["candidate_metadata_model"]["related_tables_deferred"])
    for field in checker.REQUIRED_CONTRACT_TRUE:
        assert data["contract_planning"][field] is True
    assert data["contract_planning"]["production_data_allowed"] is False


def test_authorizations_false() -> None:
    data = checker.load_yaml(PLAN_YAML)
    for field in checker.AUTH_FALSE_FIELDS:
        assert data["authorizations"][field] is False


def test_phase_execution_state_advances_to_phase_4bj() -> None:
    state = checker.load_yaml(STATE)
    assert state["active_candidate"] == checker.AGENT_OUTPUTS
    assert state["last_merged_pr"] == "#665"
    assert state["last_attempted_action"] == "phase_4bi_agent_outputs_metadata_planning"
    assert state["last_created_pr"] == "#666"
    assert state["recommended_next_pr"] == "phase_4bj_agent_outputs_schema_route_surface_confirmation"
    assert state["owner_approval_required"] is False
    assert state["next_allowed_actions"] == ["phase_4bj_agent_outputs_schema_route_surface_confirmation"]
    assert "phase_4bi_agent_outputs_metadata_planning_completed" in state["completed_steps"]


def test_agent_outputs_readiness_is_planning_only_without_runtime_readiness() -> None:
    readiness = checker.load_yaml(STATE)["agent_outputs_readiness"]
    assert readiness["metadata_planning_ready"] is True
    assert readiness["metadata_planning_completed"] is True
    assert readiness["schema_route_surface_confirmation_ready"] is True
    assert readiness["export_job_creation_excluded"] is True
    assert readiness["file_download_excluded"] is True
    assert readiness["agent_run_execution_excluded"] is True
    assert readiness["llm_generation_excluded"] is True
    assert readiness["external_call_excluded"] is True
    assert readiness["fixture_native_contract_planning_ready"] is False
    assert readiness["runtime_implementation_ready"] is False
    assert readiness["production_owner_switch_ready"] is False
    assert readiness["production_write_ready"] is False
    assert readiness["fallback_removal_ready"] is False
    assert readiness["production_repository_route_enablement_ready"] is False
    assert readiness["delete_ready"] is False


def test_phase_4bj_recommendation_does_not_allow_production_actions() -> None:
    rec = checker.load_yaml(PLAN_YAML)["phase_4bj_recommendation"]
    assert rec["recommended_next_step"] == "agent_outputs_schema_route_surface_confirmation"
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
