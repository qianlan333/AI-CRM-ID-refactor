from __future__ import annotations

import json
import subprocess
from pathlib import Path

import tools.check_phase4bh_agents_fixture_native_implementation_owner_decision as checker


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_4bh_agents_fixture_native_implementation_owner_decision.md"
PLAN_YAML = ROOT / "docs/development/phase_4bh_agents_fixture_native_implementation_owner_decision.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"


def test_checker_current_repo_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_decision_package_is_docs_only_deferral() -> None:
    data = checker.load_yaml(PLAN_YAML)
    decision = data["decision_package"]
    assert decision["type"] == "owner_decision_and_candidate_deferral"
    assert decision["auto_merge_under_throughput_allowed"] is True
    assert decision["docs_tools_tests_state_only"] is True
    assert decision["runtime_implementation_included"] is False


def test_agents_paused_for_owner_decision() -> None:
    data = checker.load_yaml(PLAN_YAML)
    paused = data["paused_candidate"]
    assert paused["route_family"] == checker.AGENTS
    assert paused["owner_approval_required"] is True
    assert paused["current_runtime_owner"] == "production_compat"
    assert paused["production_behavior"] == "legacy_forward"
    assert {
        "phase_4be_agents_metadata_planning_completed",
        "phase_4bf_agents_schema_route_surface_confirmation_completed",
        "phase_4bg_agents_fixture_native_contract_planning_completed",
    } <= set(paused["completed_assets"])
    assert checker.REQUIRED_DECISIONS <= set(data["owner_decision_required"])
    assert checker.REQUIRED_SAFE_OPTIONS <= set(data["safe_next_options"])


def test_rejected_actions_and_authorizations() -> None:
    data = checker.load_yaml(PLAN_YAML)
    for field in checker.REJECTED_TRUE_FIELDS:
        assert data["rejected_actions"][field] is True
    for field in checker.AUTH_FALSE_FIELDS:
        assert data["authorizations"][field] is False


def test_next_candidate_selects_agent_outputs_metadata_planning() -> None:
    data = checker.load_yaml(PLAN_YAML)
    selected = data["next_candidate"]
    assert selected["selected_route_family"] == checker.AGENT_OUTPUTS
    assert selected["replacement_phase"] == "phase_4_internal_write"
    assert selected["replacement_category"] == "internal_write"
    assert selected["current_runtime_owner"] == "production_compat"
    assert selected["production_behavior"] == "legacy_forward"
    assert checker.REQUIRED_AGENT_OUTPUTS_GUARDRAILS <= set(selected["required_guardrails"])
    assert checker.REQUIRED_PHASE_4BI_SCOPE <= set(selected["phase_4bi_scope"])


def test_phase_execution_state_pauses_agents_and_advances_to_agent_outputs() -> None:
    state = checker.load_yaml(STATE)
    assert state["active_candidate"] == checker.AGENT_OUTPUTS
    assert state["last_merged_pr"] == "#664"
    assert state["last_attempted_action"] == "phase_4bh_agents_fixture_native_implementation_owner_decision"
    assert state["last_created_pr"] == "#665"
    assert state["recommended_next_pr"] == "phase_4bi_agent_outputs_metadata_planning"
    assert state["owner_approval_required"] is False
    assert state["next_allowed_actions"] == ["phase_4bi_agent_outputs_metadata_planning"]
    assert "phase_4bh_agents_fixture_native_implementation_owner_decision_completed" in state["completed_steps"]
    assert any(item["route_family"] == checker.AGENTS and item["owner_approval_required"] is True for item in state["paused_candidates"])


def test_agents_readiness_paused_without_runtime_readiness() -> None:
    readiness = checker.load_yaml(STATE)["agents_readiness"]
    assert readiness["paused"] is True
    assert readiness["owner_decision_required"] is True
    assert readiness["runtime_implementation_ready"] is False
    assert readiness["production_owner_switch_ready"] is False
    assert readiness["production_write_ready"] is False
    assert readiness["fallback_removal_ready"] is False
    assert readiness["delete_ready"] is False


def test_agent_outputs_readiness_is_planning_only() -> None:
    readiness = checker.load_yaml(STATE)["agent_outputs_readiness"]
    assert readiness["metadata_planning_ready"] is True
    assert readiness["metadata_planning_completed"] is False
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


def test_phase_4bi_recommendation_does_not_allow_production_work() -> None:
    data = checker.load_yaml(PLAN_YAML)
    rec = data["phase_4bi_recommendation"]
    assert rec["recommended_next_step"] == "agent_outputs_metadata_planning"
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
