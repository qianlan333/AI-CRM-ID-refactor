from __future__ import annotations

import json
import subprocess
from pathlib import Path

import tools.check_phase4bj_agent_outputs_schema_route_surface_confirmation as checker


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_4bj_agent_outputs_schema_route_surface_confirmation.md"
PLAN_YAML = ROOT / "docs/development/phase_4bj_agent_outputs_schema_route_surface_confirmation.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"


def test_checker_current_repo_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_route_surface_confirms_list_detail_and_defers_export() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert data["status"] == "phase_4bj_agent_outputs_schema_route_surface_confirmation_no_runtime_change"
    assert data["route_family"] == checker.ROUTE
    assert data["current_runtime_owner"] == "production_compat"
    assert data["production_behavior"] == "legacy_forward"
    surface = data["confirmed_route_surface"]
    assert checker.REQUIRED_PRODUCTION_COMPAT_PATTERNS <= set(surface["production_compat_patterns"])
    assert checker.REQUIRED_LEGACY_ROUTES <= checker._legacy_route_pairs(surface["legacy_api_routes"])


def test_schema_surface_confirms_metadata_table_and_response_keys() -> None:
    data = checker.load_yaml(PLAN_YAML)
    schema = data["confirmed_schema_surface"]
    assert schema["metadata_table"] == "automation_agent_output"
    assert checker.REQUIRED_READ_MODEL_COLUMNS <= set(schema["read_model_columns"])
    assert checker.REQUIRED_LIST_RESPONSE_KEYS <= set(schema["legacy_response_keys"]["list"])
    assert checker.REQUIRED_DETAIL_RESPONSE_KEYS <= set(schema["legacy_response_keys"]["detail"])
    assert checker.REQUIRED_RELATED_RUNTIME_TABLES <= set(schema["related_runtime_tables_deferred"])


def test_native_boundary_keeps_export_download_and_runtime_out() -> None:
    data = checker.load_yaml(PLAN_YAML)
    boundary = data["native_contract_boundary"]
    assert checker.REQUIRED_FIRST_NATIVE_SUBSET <= set(boundary["first_native_subset"])
    assert checker.REQUIRED_NEXT_REQUIREMENTS <= set(boundary["next_contract_planning_requirements"])
    assert checker.REQUIRED_DEFERRED_SCOPE <= set(boundary["deferred_to_separate_pr"])


def test_authorizations_false() -> None:
    data = checker.load_yaml(PLAN_YAML)
    for field in checker.AUTH_FALSE_FIELDS:
        assert data["authorizations"][field] is False


def test_phase_execution_state_advances_to_phase_4bk() -> None:
    state = checker.load_yaml(STATE)
    assert state["active_candidate"] == checker.ROUTE
    assert state["last_merged_pr"] == "#666"
    assert state["last_attempted_action"] == "phase_4bj_agent_outputs_schema_route_surface_confirmation"
    assert state["last_created_pr"] == "#667"
    assert state["recommended_next_pr"] == "phase_4bk_agent_outputs_fixture_native_contract_planning"
    assert state["owner_approval_required"] is False
    assert state["next_allowed_actions"] == ["phase_4bk_agent_outputs_fixture_native_contract_planning"]
    assert "phase_4bj_agent_outputs_schema_route_surface_confirmation_completed" in state["completed_steps"]


def test_agent_outputs_readiness_is_ready_for_fixture_contract_only() -> None:
    readiness = checker.load_yaml(STATE)["agent_outputs_readiness"]
    assert readiness["metadata_planning_ready"] is True
    assert readiness["metadata_planning_completed"] is True
    assert readiness["schema_route_surface_confirmation_ready"] is True
    assert readiness["schema_route_surface_confirmed"] is True
    assert readiness["fixture_native_contract_planning_ready"] is True
    assert readiness["export_job_creation_excluded"] is True
    assert readiness["file_download_excluded"] is True
    assert readiness["agent_run_execution_excluded"] is True
    assert readiness["llm_generation_excluded"] is True
    assert readiness["external_call_excluded"] is True
    assert readiness["runtime_implementation_ready"] is False
    assert readiness["production_owner_switch_ready"] is False
    assert readiness["production_write_ready"] is False
    assert readiness["fallback_removal_ready"] is False
    assert readiness["delete_ready"] is False


def test_phase_4bk_recommendation_does_not_allow_production_actions() -> None:
    rec = checker.load_yaml(PLAN_YAML)["phase_4bk_recommendation"]
    assert rec["recommended_next_step"] == "agent_outputs_fixture_native_contract_planning"
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
