from __future__ import annotations

import json
import subprocess
from pathlib import Path

import tools.check_phase4as_workflows_schema_route_surface_confirmation as checker


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_4as_workflows_schema_route_surface_confirmation.md"
PLAN_YAML = ROOT / "docs/development/phase_4as_workflows_schema_route_surface_confirmation.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"


def test_checker_current_repo_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_route_surface_is_legacy_forwarded_for_workflows_only() -> None:
    data = checker.load_yaml(PLAN_YAML)
    routes = data["confirmed_legacy_route_surface"]
    paths = {item["path"] for item in routes}
    assert paths == {
        "/api/admin/automation-conversion/workflows",
        "/api/admin/automation-conversion/workflows/{path:path}",
    }
    for item in routes:
        assert set(item["methods"]) == checker.REQUIRED_METHODS
        assert item["production_behavior"] == "legacy_forward"


def test_primary_workflow_table_columns_and_indexes_confirmed() -> None:
    data = checker.load_yaml(PLAN_YAML)
    table = data["primary_table"]
    assert table["name"] == checker.MAIN_TABLE
    assert checker.REQUIRED_COLUMNS <= set(table["required_columns"])
    assert checker.REQUIRED_INDEXES <= set(table["required_indexes"])


def test_related_runtime_tables_are_deferred() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert checker.DEFERRED_TABLES <= set(data["deferred_related_tables"])
    boundary = data["metadata_only_boundary"]
    for field in checker.BOUNDARY_TRUE_FIELDS:
        assert boundary[field] is True


def test_high_risk_authorizations_and_exclusions_are_false_or_deferred() -> None:
    data = checker.load_yaml(PLAN_YAML)
    for field in checker.AUTH_FALSE_FIELDS:
        assert data["authorizations"][field] is False
    for field in checker.EXCLUDED_TRUE_FIELDS:
        assert data["excluded_scope"][field] is True


def test_phase_execution_state_advances_to_phase_4at() -> None:
    state = checker.load_yaml(STATE)
    assert state["active_candidate"] == checker.ROUTE
    assert "phase_4as_workflows_schema_route_surface_confirmation_completed" in state["completed_steps"]
    readiness = state["workflows_readiness"]
    assert readiness["schema_route_surface_confirmed"] is True
    assert readiness["fixture_native_contract_planning_ready"] is True
    assert readiness["runtime_implementation_ready"] is False
    assert readiness["production_owner_switch_ready"] is False
    assert readiness["production_write_ready"] is False
    assert readiness["fallback_removal_ready"] is False
    assert readiness["delete_ready"] is False


def test_phase_4at_recommendation_does_not_allow_production_work() -> None:
    data = checker.load_yaml(PLAN_YAML)
    rec = data["phase_4at_recommendation"]
    assert rec["recommended_next_step"] == "workflows_fixture_native_contract_planning"
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
