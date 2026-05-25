from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, text


def _create_group_ops_sqlite_db(path: Path) -> str:
    url = f"sqlite+pysqlite:///{path}"
    engine = create_engine(url, future=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE automation_group_ops_plans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plan_code TEXT NOT NULL DEFAULT '',
                    plan_name TEXT NOT NULL,
                    plan_type TEXT NOT NULL,
                    owner_userid TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'draft',
                    webhook_key TEXT NOT NULL DEFAULT '',
                    webhook_token_hash TEXT NOT NULL DEFAULT '',
                    created_by TEXT NOT NULL DEFAULT '',
                    updated_by TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    archived_at TEXT
                )
                """
            )
        )
        conn.execute(text("CREATE UNIQUE INDEX uq_group_ops_plan_code ON automation_group_ops_plans(plan_code) WHERE plan_code <> ''"))
        conn.execute(
            text(
                """
                CREATE TABLE automation_group_ops_plan_groups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plan_id INTEGER NOT NULL,
                    chat_id TEXT NOT NULL,
                    group_name_snapshot TEXT NOT NULL DEFAULT '',
                    owner_userid_snapshot TEXT NOT NULL DEFAULT '',
                    internal_member_count_snapshot INTEGER NOT NULL DEFAULT 0,
                    external_member_count_snapshot INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    removed_at TEXT
                )
                """
            )
        )
        conn.execute(text("CREATE UNIQUE INDEX uq_group_ops_plan_groups ON automation_group_ops_plan_groups(plan_id, chat_id)"))
        conn.execute(
            text(
                """
                CREATE TABLE automation_group_ops_plan_nodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plan_id INTEGER NOT NULL,
                    day_index INTEGER NOT NULL DEFAULT 1,
                    trigger_time_label TEXT NOT NULL DEFAULT '',
                    action_title TEXT NOT NULL DEFAULT '',
                    text_content TEXT NOT NULL DEFAULT '',
                    attachments_json TEXT NOT NULL DEFAULT '[]',
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE automation_group_ops_webhook_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plan_id INTEGER NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    request_payload TEXT NOT NULL DEFAULT '{}',
                    normalized_content_payload TEXT NOT NULL DEFAULT '{}',
                    scheduled_at TEXT,
                    status TEXT NOT NULL DEFAULT 'accepted',
                    broadcast_job_ids_json TEXT NOT NULL DEFAULT '[]',
                    error_message TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.execute(text("CREATE UNIQUE INDEX uq_group_ops_webhook_events ON automation_group_ops_webhook_events(plan_id, idempotency_key)"))
        conn.execute(
            text(
                """
                CREATE TABLE wecom_group_chat_snapshots (
                    chat_id TEXT PRIMARY KEY,
                    group_name TEXT NOT NULL DEFAULT '',
                    owner_userid TEXT NOT NULL DEFAULT '',
                    owner_name TEXT NOT NULL DEFAULT '',
                    internal_member_count INTEGER NOT NULL DEFAULT 0,
                    external_member_count INTEGER NOT NULL DEFAULT 0,
                    synced_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    status TEXT NOT NULL DEFAULT 'active'
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO wecom_group_chat_snapshots (
                    chat_id, group_name, owner_userid, owner_name,
                    internal_member_count, external_member_count, status
                )
                VALUES
                    ('wrOgAAA001', '体验课 01 群', 'owner_001', '王小明', 12, 150, 'active'),
                    ('wrOgAAA002', '体验课 02 群', 'owner_001', '王小明', 10, 160, 'active'),
                    ('wrOgBBB001', '成交陪跑 01 群', 'owner_002', '李小红', 8, 88, 'active')
                """
            )
        )
    return url


def test_postgres_group_ops_repository_lists_and_binds_with_sql_backend(tmp_path: Path) -> None:
    from aicrm_next.automation_engine.group_ops.postgres_repo import PostgresGroupOpsRepository

    db_url = _create_group_ops_sqlite_db(tmp_path / "group_ops_repo.db")
    repo = PostgresGroupOpsRepository(create_engine(db_url, future=True))

    plan = repo.create_plan(
        {
            "plan_name": "体验课 7 日群运营",
            "plan_type": "standard",
            "owner_userid": "owner_001",
            "status": "active",
            "operator": "pytest",
        }
    )
    group = repo.get_group_asset("wrOgAAA001")
    assert group and group["owner_userid"] == "owner_001"
    binding = repo.bind_group(plan["id"], group)

    plans, total = repo.list_plans({"limit": 50, "offset": 0})
    groups = repo.list_bound_groups(plan["id"])
    group_assets, group_total = repo.list_group_assets({"bind_status": "bound", "limit": 50, "offset": 0})

    assert total == 1
    assert plans[0]["owner_name"] == "王小明"
    assert binding["group_name_snapshot"] == "体验课 01 群"
    assert groups[0]["external_member_count_snapshot"] == 150
    assert group_total == 1
    assert group_assets[0]["plan_name"] == "体验课 7 日群运营"


def test_group_ops_api_uses_sql_repository_in_production_data_mode(monkeypatch, tmp_path: Path) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from aicrm_next.main import create_app

    db_url = _create_group_ops_sqlite_db(tmp_path / "group_ops_api.db")
    monkeypatch.setenv("DATABASE_URL", "postgresql://prod.example/aicrm")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.setenv("AICRM_GROUP_OPS_DATABASE_URL", db_url)
    monkeypatch.delenv("AICRM_NEXT_ALLOW_FIXTURE_REPO_IN_PROD", raising=False)

    client = TestClient(create_app(), raise_server_exceptions=False)
    response = client.get("/api/admin/automation-conversion/group-ops/plans")
    body = response.json()

    assert response.status_code == 200
    assert body["ok"] is True
    assert body["source_status"] == "postgres_group_ops_repository"
    assert body["items"] == []
