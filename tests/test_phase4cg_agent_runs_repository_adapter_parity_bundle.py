from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

import tools.check_phase4cg_agent_runs_repository_adapter_parity_bundle as checker
import tools.run_phase4cg_agent_runs_adapter_parity as harness
from aicrm_next.automation_engine.agent_run_sqlalchemy_repository import SqlAlchemyAgentRunRepository
from aicrm_next.automation_engine.repo import (
    AGENT_RUN_TEST_DATABASE_URL_ENV,
    InMemoryAutomationRepository,
    build_automation_repository,
)
from aicrm_next.shared.errors import ContractError


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_4cg_agent_runs_repository_adapter_parity_bundle.md"
PLAN_YAML = ROOT / "docs/development/phase_4cg_agent_runs_repository_adapter_parity_bundle.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
HARNESS = ROOT / "tools/run_phase4cg_agent_runs_adapter_parity.py"


def _create_sqlite_agent_run_db(path: Path) -> str:
    url = f"sqlite+pysqlite:///{path}"
    engine = create_engine(url, future=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE automation_agent_runs (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL UNIQUE,
                    request_id TEXT NOT NULL,
                    userid TEXT NOT NULL,
                    external_contact_id TEXT NOT NULL,
                    agent_code TEXT NOT NULL,
                    run_status TEXT NOT NULL DEFAULT 'completed',
                    trigger_source TEXT NOT NULL DEFAULT 'fixture',
                    task_id INTEGER NOT NULL DEFAULT 0,
                    workflow_id INTEGER NOT NULL DEFAULT 0,
                    started_at TEXT NOT NULL DEFAULT '',
                    finished_at TEXT NOT NULL DEFAULT '',
                    duration_ms INTEGER NOT NULL DEFAULT 0,
                    error_code TEXT NOT NULL DEFAULT '',
                    error_message TEXT NOT NULL DEFAULT '',
                    output_count INTEGER NOT NULL DEFAULT 0,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO automation_agent_runs (
                    id, run_id, request_id, userid, external_contact_id,
                    agent_code, run_status, trigger_source, task_id, workflow_id,
                    started_at, finished_at, duration_ms, output_count, metadata_json, created_at, updated_at
                )
                VALUES (
                    'phase4cg_run_completed_metadata',
                    'phase4cg_run_completed_metadata',
                    'req_phase4cg_reply',
                    'user_phase4_fixture',
                    'wm_external_001',
                    'phase4bg_review_agent',
                    'completed',
                    'fixture',
                    1,
                    1,
                    '2026-05-20T10:00:00Z',
                    '2026-05-20T10:01:00Z',
                    60000,
                    1,
                    '{"source":"phase4cg"}',
                    '2026-05-20T10:05:00Z',
                    '2026-05-20T10:05:00Z'
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO automation_agent_runs (
                    id, run_id, request_id, userid, external_contact_id,
                    agent_code, run_status, trigger_source, task_id, workflow_id,
                    started_at, finished_at, duration_ms, output_count, error_code, error_message, metadata_json, created_at, updated_at
                )
                VALUES (
                    'phase4cg_run_failed_metadata',
                    'phase4cg_run_failed_metadata',
                    'req_phase4cg_error',
                    'user_phase4_fixture',
                    'wm_external_002',
                    'phase4bg_followup_agent',
                    'failed',
                    'fixture',
                    2,
                    1,
                    '2026-05-20T10:02:00Z',
                    '2026-05-20T10:03:00Z',
                    30000,
                    0,
                    'adapter_sample_error',
                    'metadata-only error sample',
                    '{"source":"phase4cg"}',
                    '2026-05-20T10:06:00Z',
                    '2026-05-20T10:06:00Z'
                )
                """
            )
        )
    return url


def test_checker_current_repo_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)
    assert report["autopilot_deliverable"] is True


def test_default_repository_remains_fixture(monkeypatch) -> None:
    monkeypatch.delenv("AICRM_AGENT_RUNS_REPO_BACKEND", raising=False)
    repo = build_automation_repository()
    assert isinstance(repo, InMemoryAutomationRepository)


def test_sqlalchemy_backend_requires_route_specific_url(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_AGENT_RUNS_REPO_BACKEND", "sqlalchemy")
    monkeypatch.delenv("AICRM_AGENT_RUNS_TEST_DATABASE_URL", raising=False)
    monkeypatch.delenv("AICRM_AGENT_RUNS_STAGING_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///tmp/should_not_be_used.db")
    with pytest.raises(ContractError, match="AICRM_AGENT_RUNS_TEST_DATABASE_URL"):
        build_automation_repository()


def test_sqlalchemy_repository_lists_filters_and_gets_detail(tmp_path: Path) -> None:
    db_url = _create_sqlite_agent_run_db(tmp_path / "phase4cg_local_test.db")
    repo = SqlAlchemyAgentRunRepository(create_engine(db_url, future=True))

    rows, total, filters = repo.list_agent_runs(
        {
            "agent_code": "phase4bg_review_agent",
            "run_status": "completed",
            "trigger_source": "fixture",
            "task_id": 1,
            "visibility": "console",
        }
    )
    detail = repo.get_agent_run("phase4cg_run_completed_metadata", {"visibility": "console"})
    error_rows, error_total, _ = repo.list_agent_runs({"has_error": True, "visibility": "console"})

    assert total == 1
    assert filters["visibility"] == "console"
    assert rows[0]["run_id"] == "phase4cg_run_completed_metadata"
    assert rows[0]["external_contact_id"] == "wm_external_001"
    assert rows[0]["metadata"] == {"source": "phase4cg"}
    assert detail is not None
    assert detail["run_id"] == "phase4cg_run_completed_metadata"
    assert error_total == 1
    assert error_rows[0]["run_id"] == "phase4cg_run_failed_metadata"


def test_build_repository_selects_agent_run_adapter_with_explicit_engine(tmp_path: Path) -> None:
    db_url = _create_sqlite_agent_run_db(tmp_path / "phase4cg_build_local_test.db")
    engine = create_engine(db_url, future=True)
    repo = build_automation_repository(agent_run_backend="sqlalchemy", agent_run_engine=engine)
    rows, total, _ = repo.list_agent_runs({"visibility": "console"})
    assert total == 2
    assert {row["run_id"] for row in rows} == {"phase4cg_run_completed_metadata", "phase4cg_run_failed_metadata"}


def test_harness_missing_env_returns_blocked_not_executed(monkeypatch) -> None:
    monkeypatch.delenv(AGENT_RUN_TEST_DATABASE_URL_ENV, raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://prod.example/master")
    report = harness.run_harness()
    assert report["ok"] is True
    assert report["result_status"] == "not_executed_missing_test_db"
    assert report["adapter_smoke_executed"] is False
    assert report["production_data_used"] is False


def test_harness_refuses_production_looking_url(monkeypatch) -> None:
    monkeypatch.setenv(AGENT_RUN_TEST_DATABASE_URL_ENV, "postgresql://db.example/prod")
    report = harness.run_harness()
    assert report["ok"] is False
    assert report["result_status"] == "blocked_unsafe_test_db_url"
    assert report["adapter_smoke_executed"] is False
    assert "prod" in report["db_url_safety"]["forbidden_hits"]


def test_harness_runs_against_safe_local_sqlite_url(monkeypatch, tmp_path: Path) -> None:
    db_url = _create_sqlite_agent_run_db(tmp_path / "phase4cg_harness_local_test.db")
    monkeypatch.setenv(AGENT_RUN_TEST_DATABASE_URL_ENV, db_url)
    report = harness.run_harness()
    assert report["ok"] is True
    assert report["result_status"] == "passed"
    assert report["adapter_smoke_executed"] is True
    assert report["production_data_used"] is False
    assert report["route_switch_ready"] is False
    assert {item["name"] for item in report["details"] if item["status"] == "passed"} >= {
        "list_agent_runs",
        "get_agent_run_detail",
        "missing_detail_returns_none",
    }


def test_harness_and_repo_never_use_database_url_fallback() -> None:
    assert 'os.getenv("DATABASE_URL"' not in HARNESS.read_text(encoding="utf-8")
    assert 'os.environ.get("DATABASE_URL"' not in HARNESS.read_text(encoding="utf-8")
    repo_text = (ROOT / "aicrm_next/automation_engine/repo.py").read_text(encoding="utf-8")
    assert 'os.getenv("DATABASE_URL"' not in repo_text
    assert 'os.environ.get("DATABASE_URL"' not in repo_text


def test_yaml_records_adapter_safety_and_next_bundle() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert data["bundle"]["type"] == "repository_adapter_parity_bundle"
    assert data["adapter"]["backend_flag"] == "AICRM_AGENT_RUNS_REPO_BACKEND"
    assert set(data["adapter"]["database_url_flags"]) == {
        "AICRM_AGENT_RUNS_TEST_DATABASE_URL",
        "AICRM_AGENT_RUNS_STAGING_DATABASE_URL",
    }
    assert data["adapter"]["write_operations_added"] == []
    assert "DATABASE_URL" in data["adapter"]["forbidden_database_url_fallbacks"]
    assert data["safety"]["production_write_authorized"] is False
    assert data["safety"]["fallback_removal_authorized"] is False
    assert data["safety"]["run_creation_authorized"] is False
    assert data["safety"]["replay_orchestration_authorized"] is False
    assert data["safety"]["agent_output_generation_authorized"] is False
    assert data["safety"]["agent_run_execution_authorized"] is False
    assert data["next_bundle_recommendation"]["recommended_next_step"] == checker.NEXT_BUNDLE


def test_phase_state_records_completed_adapter_parity() -> None:
    state = checker.load_yaml(STATE)
    assert state["active_candidate"] == checker.TASK_GROUPS
    assert state["last_merged_pr"] == "#691"
    assert state["last_created_pr"] == "#692"
    assert checker.COMPLETED_STEP in state["completed_steps"]
    readiness = state["agent_runs_readiness"]
    assert readiness["repository_adapter_parity_completed"] is True
    assert readiness["repository_adapter_backend_flag"] == "AICRM_AGENT_RUNS_REPO_BACKEND"
    assert readiness["repository_adapter_test_db_url_flag"] == "AICRM_AGENT_RUNS_TEST_DATABASE_URL"
    assert readiness["repository_adapter_staging_db_url_flag"] == "AICRM_AGENT_RUNS_STAGING_DATABASE_URL"
    assert readiness["no_database_url_fallback"] is True
    assert readiness["default_backend_fixture_local"] is True
    assert readiness["test_db_parity_harness_completed"] is True
    assert readiness["idempotency_audit_rollback_scaffold_completed"] is False
    assert readiness["production_repository_route_enablement_ready"] is False


def test_docs_do_not_claim_forbidden_states() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    for phrase in checker.FORBIDDEN_CLAIMS:
        assert phrase not in text


def test_no_forbidden_paths_changed_if_git_diff_available() -> None:
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
    assert "aicrm_next/main.py" not in changed
