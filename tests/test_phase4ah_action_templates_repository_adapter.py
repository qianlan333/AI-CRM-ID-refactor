from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

import tools.check_phase4ah_action_templates_repository_adapter as checker

from aicrm_next.automation_engine.action_template_repository import (
    ACTION_TEMPLATE_BACKEND_ENV,
    ACTION_TEMPLATE_DATABASE_URL_ENV,
    ActionTemplateIdempotencyConflict,
    InMemoryActionTemplateRepository,
    build_action_template_repository,
)
from aicrm_next.automation_engine.action_template_sqlalchemy_repository import SqlAlchemyActionTemplateRepository
from aicrm_next.shared.errors import ContractError
from aicrm_next.shared.repository_provider import RepositoryProviderError


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_4ah_action_templates_repository_adapter.md"
ADAPTER = ROOT / "aicrm_next/automation_engine/action_template_sqlalchemy_repository.py"
FACTORY = ROOT / "aicrm_next/automation_engine/action_template_repository.py"
API = ROOT / "aicrm_next/automation_engine/api.py"
MAIN = ROOT / "aicrm_next/main.py"
PRODUCTION_COMPAT = ROOT / "aicrm_next/production_compat/api.py"


def _all_real_safety_false(payload: dict) -> bool:
    safety = payload.get("side_effect_safety") or {}
    return bool(safety) and all(value is False for key, value in safety.items() if key.startswith("real_"))


def _sqlite_engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE automation_operation_templates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    template_code TEXT NOT NULL UNIQUE,
                    template_name TEXT NOT NULL DEFAULT '',
                    template_source TEXT NOT NULL DEFAULT 'crm_local',
                    category TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'active',
                    default_config_json TEXT NOT NULL DEFAULT '{}',
                    ui_schema_json TEXT NOT NULL DEFAULT '{}',
                    workflow_blueprint_json TEXT NOT NULL DEFAULT '{}',
                    node_blueprints_json TEXT NOT NULL DEFAULT '[]',
                    created_by TEXT NOT NULL DEFAULT '',
                    updated_by TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    archived_at TEXT
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE automation_operation_template_idempotency (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    route_family TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    operator TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    request_hash TEXT NOT NULL,
                    response_snapshot TEXT NOT NULL DEFAULT '{}',
                    resource_type TEXT NOT NULL DEFAULT 'action_template',
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
                CREATE TABLE automation_operation_template_audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    route_family TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    operator TEXT NOT NULL,
                    resource_type TEXT NOT NULL DEFAULT 'action_template',
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
    return engine


def test_checker_current_repo_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report.get("blockers", []), ensure_ascii=False, indent=2)


def test_default_backend_remains_fixture(monkeypatch) -> None:
    monkeypatch.delenv(ACTION_TEMPLATE_BACKEND_ENV, raising=False)
    monkeypatch.delenv(ACTION_TEMPLATE_DATABASE_URL_ENV, raising=False)

    repo = build_action_template_repository()

    assert isinstance(repo, InMemoryActionTemplateRepository)


def test_explicit_sqlalchemy_backend_requires_flag_and_database_url(monkeypatch) -> None:
    monkeypatch.setenv(ACTION_TEMPLATE_BACKEND_ENV, "sqlalchemy")
    monkeypatch.delenv(ACTION_TEMPLATE_DATABASE_URL_ENV, raising=False)

    with pytest.raises(RepositoryProviderError):
        build_action_template_repository()

    repo = build_action_template_repository(engine=_sqlite_engine())
    assert isinstance(repo, SqlAlchemyActionTemplateRepository)


def test_no_database_url_fallback(monkeypatch) -> None:
    monkeypatch.setenv(ACTION_TEMPLATE_BACKEND_ENV, "sqlalchemy")
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.delenv(ACTION_TEMPLATE_DATABASE_URL_ENV, raising=False)

    with pytest.raises(RepositoryProviderError):
        build_action_template_repository()

    factory_text = FACTORY.read_text(encoding="utf-8")
    assert 'os.getenv("DATABASE_URL"' not in factory_text
    assert 'os.environ.get("DATABASE_URL"' not in factory_text


def test_production_fixture_post_success_blocked(monkeypatch) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from aicrm_next.automation_engine.action_template_repository import reset_action_template_fixture_state
    from aicrm_next.main import create_app

    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv(ACTION_TEMPLATE_BACKEND_ENV, raising=False)
    monkeypatch.delenv(ACTION_TEMPLATE_DATABASE_URL_ENV, raising=False)
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "0")
    monkeypatch.setenv("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", "1")
    reset_action_template_fixture_state()

    response = TestClient(create_app(), raise_server_exceptions=False).post(
        "/api/admin/automation-conversion/action-templates",
        json={
            "template_name": "Prod Guard",
            "template_code": "prod_guard",
            "idempotency_key": "prod-guard",
            "operator": "pytest",
        },
    )

    assert response.status_code == 503
    body = response.json()
    assert body["ok"] is False
    assert body["error_code"] == "production_repository_not_enabled"


def test_adapter_maps_expected_tables() -> None:
    text_body = ADAPTER.read_text(encoding="utf-8")
    for table in (
        "automation_operation_templates",
        "automation_operation_template_idempotency",
        "automation_operation_template_audit_log",
    ):
        assert table in text_body


def test_create_method_idempotency_replay_and_conflict() -> None:
    repo = SqlAlchemyActionTemplateRepository(_sqlite_engine())
    payload = {
        "template_name": "SQL Create",
        "template_code": "sql_create",
        "operator": "pytest",
        "default_config": {"channel": "local"},
    }

    created = repo.create_action_template(payload, idempotency_key="sql-key", operator="pytest")
    replay = repo.create_action_template(payload, idempotency_key="sql-key", operator="pytest")

    assert created["idempotent_replay"] is False
    assert replay["idempotent_replay"] is True
    assert replay["template"]["template_code"] == "sql_create"

    with pytest.raises(ActionTemplateIdempotencyConflict):
        repo.create_action_template({**payload, "template_name": "SQL Changed"}, idempotency_key="sql-key", operator="pytest")


def test_duplicate_template_code_rejected_by_adapter() -> None:
    repo = SqlAlchemyActionTemplateRepository(_sqlite_engine())
    payload = {"template_name": "SQL Duplicate", "template_code": "sql_duplicate", "operator": "pytest"}

    repo.create_action_template(payload, idempotency_key="dup-1", operator="pytest")

    with pytest.raises(ContractError):
        repo.create_action_template({**payload, "template_name": "SQL Duplicate B"}, idempotency_key="dup-2", operator="pytest")


def test_audit_event_and_rollback_payload_logic_covered() -> None:
    repo = SqlAlchemyActionTemplateRepository(_sqlite_engine())
    created = repo.create_action_template(
        {"template_name": "SQL Audit", "template_code": "sql_audit", "operator": "pytest"},
        idempotency_key="audit-1",
        operator="pytest",
    )
    events = repo.list_action_template_audit_events({"resource_id": created["template"]["id"]})

    assert created["audit_event"]["operation"] == "create"
    assert created["audit_event"]["before_snapshot"] == {}
    assert created["audit_event"]["after_snapshot"]["template_code"] == "sql_audit"
    assert created["rollback_payload"]["created_template_id"] == created["template"]["id"]
    assert events and events[0]["rollback_payload"]["template_code"] == "sql_audit"


def test_side_effect_safety_false() -> None:
    repo = SqlAlchemyActionTemplateRepository(_sqlite_engine())
    created = repo.create_action_template(
        {"template_name": "SQL Safety", "template_code": "sql_safety", "operator": "pytest"},
        idempotency_key="safety-1",
        operator="pytest",
    )

    assert _all_real_safety_false(created["audit_event"])


def test_generate_from_workflow_update_delete_routes_remain_excluded() -> None:
    api_text = API.read_text(encoding="utf-8")
    adapter_text = ADAPTER.read_text(encoding="utf-8")

    assert "action-templates/generate" not in api_text
    assert "action-templates/from-workflow" not in api_text
    assert "@router.put(\"/api/admin/automation-conversion/action-templates" not in api_text
    assert "@router.delete(\"/api/admin/automation-conversion/action-templates" not in api_text
    for method in checker.EXCLUDED_METHODS:
        assert f"def {method}" not in adapter_text


def test_production_compat_main_unchanged() -> None:
    changed, _warnings = checker._changed_files_from_git()

    assert str(MAIN.relative_to(ROOT)) not in changed
    assert str(PRODUCTION_COMPAT.relative_to(ROOT)) not in changed


def test_no_runtime_files_changed_outside_allowed_scope_if_git_available() -> None:
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
    assert "aicrm_next/production_compat/api.py" not in changed
    assert not any(path.startswith("wecom_ability_service/") for path in changed)
    assert not any(path.startswith("migrations/") for path in changed)


def test_docs_do_not_claim_forbidden_states() -> None:
    text_body = DOC.read_text(encoding="utf-8").lower()
    forbidden_patterns = [
        r"production route owner switched",
        r"fallback removal authorized",
        r"production write as route owner authorized",
        r"external calls enabled",
        r"production approved",
        r"canary approved",
        r"delete_ready\s+true",
    ]

    for pattern in forbidden_patterns:
        assert re.search(pattern, text_body) is None, pattern


def test_optional_safe_local_db_probe_guard() -> None:
    url = os.getenv("AICRM_ACTION_TEMPLATES_TEST_DATABASE_URL", "")
    if not url:
        pytest.skip("AICRM_ACTION_TEMPLATES_TEST_DATABASE_URL not set")
    assert any(marker in url.lower() for marker in ("test", "local", "dev", "127.0.0.1", "localhost"))
