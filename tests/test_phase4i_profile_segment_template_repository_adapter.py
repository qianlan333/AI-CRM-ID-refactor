from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from aicrm_next.automation_engine.profile_segment_repository import (
    ProfileSegmentTemplateIdempotencyConflict,
    SqlAlchemyProfileSegmentTemplateRepository,
    build_profile_segment_template_repository,
)
from aicrm_next.automation_engine.repo import FixtureAutomationRepository
from aicrm_next.shared.errors import ContractError, NotFoundError
from aicrm_next.shared.repository_provider import RepositoryProviderError


ROOT = Path(__file__).resolve().parents[1]


def _setup_sqlite_repo() -> SqlAlchemyProfileSegmentTemplateRepository:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE automation_profile_segment_template (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    program_id INTEGER,
                    template_code TEXT NOT NULL UNIQUE,
                    template_name TEXT NOT NULL DEFAULT '',
                    questionnaire_id INTEGER,
                    segmentation_question_id INTEGER,
                    description TEXT NOT NULL DEFAULT '',
                    enabled BOOLEAN NOT NULL DEFAULT 1,
                    version INTEGER NOT NULL DEFAULT 1,
                    created_by TEXT NOT NULL DEFAULT '',
                    updated_by TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE automation_profile_segment_category (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    template_id INTEGER NOT NULL,
                    category_key TEXT NOT NULL DEFAULT '',
                    category_name TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    enabled BOOLEAN NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE automation_profile_segment_option_mapping (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    template_id INTEGER NOT NULL,
                    category_id INTEGER NOT NULL,
                    question_id INTEGER NOT NULL,
                    option_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE automation_profile_segment_template_idempotency (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    route_family TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    operator TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    request_hash TEXT NOT NULL,
                    response_snapshot TEXT NOT NULL DEFAULT '{}',
                    resource_type TEXT NOT NULL DEFAULT 'profile_segment_template',
                    resource_id INTEGER,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (route_family, operation, operator, idempotency_key)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE automation_profile_segment_template_audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    route_family TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    operator TEXT NOT NULL,
                    resource_type TEXT NOT NULL DEFAULT 'profile_segment_template',
                    resource_id INTEGER,
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
    return SqlAlchemyProfileSegmentTemplateRepository(engine)


def _create_payload(name: str = "Phase 4I 模板", key: str = "phase4i") -> dict:
    return {
        "name": name,
        "code": key,
        "description": "bounded metadata only",
        "status": "active",
        "rules": {
            "categories": [
                {
                    "category_key": "high",
                    "category_name": "高意向",
                    "sort_order": 1,
                    "option_mappings": [{"question_id": 101, "option_id": 201}],
                }
            ]
        },
        "conditions": {},
    }


def test_factory_default_remains_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND", raising=False)
    monkeypatch.delenv("PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    repo = build_profile_segment_template_repository()
    assert isinstance(repo, FixtureAutomationRepository)


def test_sqlalchemy_adapter_create_replay_conflict_and_duplicate() -> None:
    repo = _setup_sqlite_repo()
    created = repo.create_profile_segment_template(_create_payload(), idempotency_key="idem-1", operator="owner-a")
    assert created["source_status"] == "sql_alchemy_profile_segment_repository"
    assert created["template"]["code"] == "phase4i"
    assert created["idempotent_replay"] is False
    assert created["rollback"]["created_template_id"] == created["template"]["id"]
    assert all(value is False for value in created["audit_event"]["side_effect_safety"].values())

    replay = repo.create_profile_segment_template(_create_payload(), idempotency_key="idem-1", operator="owner-a")
    assert replay["idempotent_replay"] is True
    assert replay["template"]["id"] == created["template"]["id"]
    assert len(repo.list_profile_segment_templates()[0]) == 1

    with pytest.raises(ProfileSegmentTemplateIdempotencyConflict):
        repo.create_profile_segment_template(
            _create_payload(name="Other name", key="other-code"),
            idempotency_key="idem-1",
            operator="owner-a",
        )

    with pytest.raises(ContractError):
        repo.create_profile_segment_template(_create_payload(), idempotency_key="idem-2", operator="owner-a")


def test_sqlalchemy_adapter_list_detail_update_and_audit() -> None:
    repo = _setup_sqlite_repo()
    created = repo.create_profile_segment_template(_create_payload(), idempotency_key="idem-1", operator="owner-a")
    template_id = created["template"]["id"]

    rows, total = repo.list_profile_segment_templates(enabled_only=True)
    assert total == 1
    assert rows[0]["rules"]["categories"][0]["option_mappings"][0]["question_id"] == 101
    assert repo.get_profile_segment_template(template_id)["name"] == "Phase 4I 模板"
    assert repo.profile_segment_template_catalog()["total"] == 1

    updated = repo.update_profile_segment_template(
        template_id,
        {
            "name": "Phase 4I 模板更新",
            "status": "inactive",
            "rules": {"categories": [{"category_key": "low", "category_name": "低意向", "sort_order": 2}]},
        },
        operator="owner-b",
    )
    assert updated["template"]["name"] == "Phase 4I 模板更新"
    assert updated["rollback"]["before"]["name"] == "Phase 4I 模板"
    assert updated["rollback"]["after"]["name"] == "Phase 4I 模板更新"
    assert updated["audit_event"]["operation"] == "update"
    assert len(repo.list_profile_segment_template_audit_events()) == 2

    with pytest.raises(NotFoundError):
        repo.update_profile_segment_template(9999, {"name": "missing"}, operator="owner-b")


def test_production_fixture_backend_is_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://phase4i:phase4i@127.0.0.1:1/aicrm_phase4i_probe")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.delenv("AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND", raising=False)
    with pytest.raises(RepositoryProviderError):
        build_profile_segment_template_repository()


def test_production_sqlalchemy_missing_db_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://phase4i:phase4i@127.0.0.1:1/aicrm_phase4i_probe")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.setenv("AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND", "sqlalchemy")
    repo = build_profile_segment_template_repository()
    with pytest.raises(RepositoryProviderError):
        repo.list_profile_segment_templates()


def test_no_main_or_production_compat_changes_if_git_available() -> None:
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
