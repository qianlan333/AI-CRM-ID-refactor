from __future__ import annotations

import json
import subprocess
from pathlib import Path

import tools.check_phase4au_workflows_fixture_native_implementation_owner_decision as checker


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_4au_workflows_fixture_native_implementation_owner_decision.md"
PLAN_YAML = ROOT / "docs/development/phase_4au_workflows_fixture_native_implementation_owner_decision.yaml"
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


def test_workflows_paused_for_owner_decision() -> None:
    data = checker.load_yaml(PLAN_YAML)
    paused = data["paused_candidate"]
    assert paused["route_family"] == checker.WORKFLOWS
    assert paused["owner_approval_required"] is True
    assert paused["current_runtime_owner"] == "production_compat"
    assert paused["production_behavior"] == "legacy_forward"
    assert {
        "phase_4ar_workflows_metadata_planning_completed",
        "phase_4as_workflows_schema_route_surface_confirmation_completed",
        "phase_4at_workflows_fixture_native_contract_planning_completed",
    } <= set(paused["completed_assets"])
    assert checker.REQUIRED_DECISIONS <= set(data["owner_decision_required"])


def test_next_candidate_is_workflow_nodes_planning_only() -> None:
    data = checker.load_yaml(PLAN_YAML)
    next_candidate = data["next_candidate"]
    assert next_candidate["selected_route_family"] == checker.WORKFLOW_NODES
    assert next_candidate["replacement_phase"] == "phase_4_internal_write"
    assert next_candidate["replacement_category"] == "internal_write"
    assert checker.REQUIRED_GUARDRAILS <= set(next_candidate["required_guardrails"])


def test_authorizations_false() -> None:
    data = checker.load_yaml(PLAN_YAML)
    for field in checker.AUTH_FALSE_FIELDS:
        assert data["authorizations"][field] is False


def test_phase_execution_state_selects_workflow_nodes_next() -> None:
    state = checker.load_yaml(STATE)
    assert state["active_candidate"] == checker.WORKFLOW_NODES
    assert "phase_4au_workflows_fixture_native_implementation_owner_decision_completed" in state["completed_steps"]
    assert any(item["route_family"] == checker.WORKFLOWS and item["owner_approval_required"] is True for item in state["paused_candidates"])
    workflows = state["workflows_readiness"]
    assert workflows["owner_decision_required"] is True
    assert workflows["paused"] is True
    assert workflows["runtime_implementation_ready"] is False
    nodes = state["workflow_nodes_readiness"]
    assert nodes["metadata_planning_ready"] is True
    assert isinstance(nodes["metadata_planning_completed"], bool)
    assert nodes["runtime_implementation_ready"] is False
    assert nodes["production_owner_switch_ready"] is False
    assert nodes["production_write_ready"] is False
    assert nodes["fallback_removal_ready"] is False
    assert nodes["delete_ready"] is False


def test_phase_4av_recommendation_does_not_allow_production_work() -> None:
    data = checker.load_yaml(PLAN_YAML)
    rec = data["phase_4av_recommendation"]
    assert rec["recommended_next_step"] == "workflow_nodes_metadata_planning"
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
