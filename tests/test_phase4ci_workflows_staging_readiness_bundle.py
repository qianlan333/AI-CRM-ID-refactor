from __future__ import annotations

import json
from pathlib import Path

import tools.check_phase4ci_workflows_staging_readiness_bundle as checker
import tools.run_phase4ci_workflows_staging_readiness as runner


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_4ci_workflows_staging_readiness_bundle.md"
PLAN_YAML = ROOT / "docs/development/phase_4ci_workflows_staging_readiness_bundle.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
RUNNER = ROOT / "tools/run_phase4ci_workflows_staging_readiness.py"


def test_checker_current_repo_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)
    assert report["autopilot_deliverable"] is True


def test_default_missing_staging_env_returns_blocked_evidence(monkeypatch) -> None:
    monkeypatch.delenv("AICRM_WORKFLOWS_STAGING_DATABASE_URL", raising=False)
    monkeypatch.delenv("AICRM_WORKFLOWS_REPO_BACKEND", raising=False)
    monkeypatch.delenv("AICRM_PHASE4CI_STAGING_SMOKE_APPROVED", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://prod.example/master")
    report = runner.run_preflight()
    assert report["ok"] is True
    assert report["result_status"] == "not_executed_missing_staging_db"
    assert report["staging_smoke_executed"] is False
    assert report["db_connection_attempted"] is False
    assert report["ready_for_staging_smoke_execution"] is False


def test_runner_refuses_production_looking_url(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_WORKFLOWS_STAGING_DATABASE_URL", "postgresql://db.example/prod")
    report = runner.run_preflight()
    assert report["ok"] is False
    assert report["result_status"] == "not_executed_db_url_safety_failed"
    assert "prod" in report["db_url_safety"]["forbidden_hits"]
    assert report["staging_smoke_executed"] is False


def test_runner_requires_backend_and_approval(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_WORKFLOWS_STAGING_DATABASE_URL", "sqlite+pysqlite:////tmp/phase4ci_stage.db")
    monkeypatch.delenv("AICRM_WORKFLOWS_REPO_BACKEND", raising=False)
    report = runner.run_preflight()
    assert report["result_status"] == "not_executed_missing_repo_backend"
    monkeypatch.setenv("AICRM_WORKFLOWS_REPO_BACKEND", "sqlalchemy")
    monkeypatch.delenv("AICRM_PHASE4CI_STAGING_SMOKE_APPROVED", raising=False)
    report = runner.run_preflight()
    assert report["result_status"] == "not_executed_missing_staging_approval"


def test_runner_write_request_requires_write_approval(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_WORKFLOWS_STAGING_DATABASE_URL", "sqlite+pysqlite:////tmp/phase4ci_stage.db")
    monkeypatch.setenv("AICRM_WORKFLOWS_REPO_BACKEND", "sqlalchemy")
    monkeypatch.setenv("AICRM_PHASE4CI_STAGING_SMOKE_APPROVED", "1")
    monkeypatch.delenv("AICRM_PHASE4CI_STAGING_WRITE_APPROVED", raising=False)
    report = runner.run_preflight(execute_writes=True)
    assert report["ok"] is True
    assert report["result_status"] == "not_executed_write_approval_missing"
    assert report["staging_write_executed"] is False


def test_runner_can_report_ready_without_execution_when_flags_present(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_WORKFLOWS_STAGING_DATABASE_URL", "sqlite+pysqlite:////tmp/phase4ci_stage.db")
    monkeypatch.setenv("AICRM_WORKFLOWS_REPO_BACKEND", "sqlalchemy")
    monkeypatch.setenv("AICRM_PHASE4CI_STAGING_SMOKE_APPROVED", "1")
    report = runner.run_preflight()
    assert report["ok"] is True
    assert report["result_status"] == "staging_readiness_preflight_passed_no_execution"
    assert report["ready_for_staging_smoke_execution"] is True
    assert report["staging_smoke_executed"] is False
    assert report["db_connection_attempted"] is False


def test_runner_never_uses_database_url_or_test_db_fallback() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    assert 'os.getenv("DATABASE_URL"' not in text
    assert 'os.environ.get("DATABASE_URL"' not in text
    assert 'os.getenv("AICRM_WORKFLOWS_TEST_DATABASE_URL"' not in text
    assert 'os.environ.get("AICRM_WORKFLOWS_TEST_DATABASE_URL"' not in text


def test_yaml_records_staging_safety_and_next_bundle() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert data["bundle"]["type"] == "staging_readiness_bundle"
    assert data["staging_readiness"]["staging_database_url_flag"] == "AICRM_WORKFLOWS_STAGING_DATABASE_URL"
    assert data["staging_readiness"]["db_connection_attempted_by_default"] is False
    assert data["staging_readiness"]["staging_smoke_executed_by_default"] is False
    assert data["staging_readiness"]["staging_write_executed_by_default"] is False
    assert data["safety"]["production_write_authorized"] is False
    assert data["safety"]["fallback_removal_authorized"] is False
    assert data["next_bundle_recommendation"]["recommended_next_step"] == checker.NEXT_BUNDLE


def test_phase_state_records_completed_staging_readiness() -> None:
    state = checker.load_yaml(STATE)
    assert state["active_candidate"] == checker.WORKFLOW_NODES
    assert state["last_merged_pr"] == "#694"
    assert state["last_created_pr"] == "#695"
    assert checker.COMPLETED_STEP in state["completed_steps"]
    assert any(item["route_family"] == checker.WORKFLOWS for item in state["staging_readiness_slices"])
    readiness = state["workflows_readiness"]
    assert readiness["staging_readiness_bundle_completed"] is True
    assert readiness["staging_smoke_executed"] is False
    assert readiness["production_repository_route_enablement_ready"] is False


def test_docs_do_not_claim_forbidden_states() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    for phrase in checker.FORBIDDEN_CLAIMS:
        assert phrase not in text
