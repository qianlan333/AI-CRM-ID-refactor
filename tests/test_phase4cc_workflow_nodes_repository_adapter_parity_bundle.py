from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

import tools.check_phase4cc_workflow_nodes_repository_adapter_parity_bundle as checker
import tools.run_phase4cc_workflow_nodes_adapter_parity as harness
from aicrm_next.automation_engine.repo import (
    WORKFLOW_NODE_TEST_DATABASE_URL_ENV,
    InMemoryAutomationRepository,
    build_automation_repository,
)
from aicrm_next.automation_engine.workflow_node_sqlalchemy_repository import SqlAlchemyWorkflowNodeRepository
from aicrm_next.shared.errors import ContractError


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_4cc_workflow_nodes_repository_adapter_parity_bundle.md"
PLAN_YAML = ROOT / "docs/development/phase_4cc_workflow_nodes_repository_adapter_parity_bundle.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
HARNESS = ROOT / "tools/run_phase4cc_workflow_nodes_adapter_parity.py"


def _create_sqlite_workflow_node_db(path: Path) -> str:
    url = f"sqlite+pysqlite:///{path}"
    engine = create_engine(url, future=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE automation_workflow_nodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    program_id INTEGER NOT NULL DEFAULT 0,
                    workflow_id INTEGER NOT NULL DEFAULT 0,
                    node_code TEXT NOT NULL,
                    node_name TEXT NOT NULL,
                    node_type TEXT NOT NULL DEFAULT 'manual',
                    status TEXT NOT NULL DEFAULT 'draft',
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    position_json TEXT NOT NULL DEFAULT '{}',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    config_json TEXT NOT NULL DEFAULT '{}',
                    enabled BOOLEAN NOT NULL DEFAULT 0,
                    created_by TEXT NOT NULL DEFAULT '',
                    updated_by TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    archived_at TEXT,
                    UNIQUE(workflow_id, node_code)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE automation_workflow_node_idempotency (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    route_family TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    operator TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    request_hash TEXT NOT NULL,
                    response_snapshot TEXT NOT NULL DEFAULT '{}',
                    resource_type TEXT NOT NULL DEFAULT 'workflow_node',
                    resource_id INTEGER NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(route_family, operation, operator, idempotency_key)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE automation_workflow_node_audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    route_family TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    operator TEXT NOT NULL,
                    resource_type TEXT NOT NULL DEFAULT 'workflow_node',
                    resource_id INTEGER NULL,
                    before_snapshot TEXT NOT NULL DEFAULT '{}',
                    after_snapshot TEXT NOT NULL DEFAULT '{}',
                    request_payload TEXT NOT NULL DEFAULT '{}',
                    validation_result TEXT NOT NULL DEFAULT '{}',
                    rollback_payload TEXT NOT NULL DEFAULT '{}',
                    side_effect_safety TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO automation_workflow_nodes (
                    program_id, workflow_id, node_code, node_name, node_type, created_by, updated_by
                )
                VALUES (
                    1, 1, 'phase4cc_seed_node', 'Phase 4CC seed node', 'metadata',
                    'fixture', 'fixture'
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
    monkeypatch.delenv("AICRM_WORKFLOW_NODES_REPO_BACKEND", raising=False)
    repo = build_automation_repository()
    assert isinstance(repo, InMemoryAutomationRepository)


def test_sqlalchemy_backend_requires_route_specific_url(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_WORKFLOW_NODES_REPO_BACKEND", "sqlalchemy")
    monkeypatch.delenv("AICRM_WORKFLOW_NODES_TEST_DATABASE_URL", raising=False)
    monkeypatch.delenv("AICRM_WORKFLOW_NODES_STAGING_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///tmp/should_not_be_used.db")
    with pytest.raises(ContractError, match="AICRM_WORKFLOW_NODES_TEST_DATABASE_URL"):
        build_automation_repository()


def test_sqlalchemy_repository_lists_creates_idempotently_and_audits(tmp_path: Path) -> None:
    db_url = _create_sqlite_workflow_node_db(tmp_path / "phase4cc_local_test.db")
    repo = SqlAlchemyWorkflowNodeRepository(create_engine(db_url, future=True))

    rows, total = repo.list_workflow_nodes({"workflow_id": 1, "limit": 10, "offset": 0})
    assert total == 1
    assert rows[0]["node_code"] == "phase4cc_seed_node"

    payload = {
        "program_id": 2,
        "workflow_id": 2,
        "node_name": "Adapter parity",
        "node_code": "adapter_parity",
        "node_type": "metadata",
        "operator": "pytest",
    }
    created = repo.create_workflow_node(payload, idempotency_key="create-1", operator="pytest")
    replay = repo.create_workflow_node(payload, idempotency_key="create-1", operator="pytest")
    audits = repo.list_workflow_node_audit_events()

    assert created["node"]["node_code"] == "adapter_parity"
    assert created["node"]["enabled"] is False
    assert created["idempotent_replay"] is False
    assert created["rollback_payload"]["delete_approved"] is False
    assert replay["idempotent_replay"] is True
    assert replay["node"]["id"] == created["node"]["id"]
    assert audits[0]["resource_type"] == "workflow_node"
    assert audits[0]["external_event_dispatched"] is False
    assert all(value is False for value in audits[0]["side_effect_safety"].values())


def test_sqlalchemy_idempotency_conflict_rejected(tmp_path: Path) -> None:
    db_url = _create_sqlite_workflow_node_db(tmp_path / "phase4cc_conflict_local_test.db")
    repo = SqlAlchemyWorkflowNodeRepository(create_engine(db_url, future=True))
    payload = {"program_id": 3, "workflow_id": 3, "node_name": "Conflict", "node_code": "conflict"}
    repo.create_workflow_node(payload, idempotency_key="same-key", operator="pytest")
    with pytest.raises(ContractError, match="idempotency key conflicts"):
        repo.create_workflow_node({**payload, "node_name": "Conflict changed"}, idempotency_key="same-key", operator="pytest")


def test_harness_missing_env_returns_blocked_not_executed(monkeypatch) -> None:
    monkeypatch.delenv(WORKFLOW_NODE_TEST_DATABASE_URL_ENV, raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://prod.example/master")
    report = harness.run_harness()
    assert report["ok"] is True
    assert report["result_status"] == "not_executed_missing_test_db"
    assert report["adapter_smoke_executed"] is False
    assert report["production_data_used"] is False


def test_harness_refuses_production_looking_url(monkeypatch) -> None:
    monkeypatch.setenv(WORKFLOW_NODE_TEST_DATABASE_URL_ENV, "postgresql://db.example/prod")
    report = harness.run_harness()
    assert report["ok"] is False
    assert report["result_status"] == "blocked_unsafe_test_db_url"
    assert report["adapter_smoke_executed"] is False
    assert "prod" in report["db_url_safety"]["forbidden_hits"]


def test_harness_runs_against_safe_local_sqlite_url(monkeypatch, tmp_path: Path) -> None:
    db_url = _create_sqlite_workflow_node_db(tmp_path / "phase4cc_harness_local_test.db")
    monkeypatch.setenv(WORKFLOW_NODE_TEST_DATABASE_URL_ENV, db_url)
    report = harness.run_harness()
    assert report["ok"] is True
    assert report["result_status"] == "passed"
    assert report["adapter_smoke_executed"] is True
    assert report["production_data_used"] is False
    assert report["route_switch_ready"] is False
    assert {item["name"] for item in report["details"] if item["status"] == "passed"} >= {
        "list_workflow_nodes",
        "create_with_idempotency",
        "idempotency_replay",
        "audit_event_emitted",
        "rollback_payload_present",
        "side_effect_safety_false",
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
    assert data["adapter"]["backend_flag"] == "AICRM_WORKFLOW_NODES_REPO_BACKEND"
    assert set(data["adapter"]["database_url_flags"]) == {"AICRM_WORKFLOW_NODES_TEST_DATABASE_URL", "AICRM_WORKFLOW_NODES_STAGING_DATABASE_URL"}
    assert "DATABASE_URL" in data["adapter"]["forbidden_database_url_fallbacks"]
    assert data["safety"]["production_write_authorized"] is False
    assert data["safety"]["fallback_removal_authorized"] is False
    assert data["safety"]["node_transition_runtime_authorized"] is False
    assert data["next_bundle_recommendation"]["recommended_next_step"] == checker.NEXT_BUNDLE


def test_phase_state_records_completed_adapter_parity() -> None:
    state = checker.load_yaml(STATE)
    assert state["active_candidate"] == checker.TASKS
    assert state["last_merged_pr"] == "#687"
    assert state["last_created_pr"] == "#688"
    assert checker.COMPLETED_STEP in state["completed_steps"]
    readiness = state["workflow_nodes_readiness"]
    assert readiness["repository_adapter_parity_completed"] is True
    assert readiness["no_database_url_fallback"] is True
    assert readiness["default_backend_fixture_local"] is True
    assert readiness["test_db_parity_harness_completed"] is True
    assert readiness["idempotency_audit_rollback_scaffold_completed"] is True
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
