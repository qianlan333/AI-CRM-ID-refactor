from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from aicrm_next.automation_engine.repo import _sqlalchemy_database_url
from aicrm_next.main import app


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "aicrm_next" / "frontend_compat" / "templates" / "admin_console" / "_automation_operation_orchestration_panel.html"
OPERATION_JS = ROOT / "aicrm_next" / "frontend_compat" / "static" / "admin_console" / "automation_operation_orchestration_panel.js"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_operation_setup_panel_exposes_next_native_task_and_group_controls() -> None:
    template = _read(TEMPLATE)
    script = _read(OPERATION_JS)

    assert "data-create-task" in template
    assert "data-create-group" in template
    assert "data-delete-group" in template
    assert 'data-field="trigger_type"' in template
    assert 'data-field="target_stage_code"' in template
    assert 'data-field="behavior_filter"' in template
    assert "(() => {" not in template

    assert "/setup/operation-tasks" in script
    assert "/setup/operation-task-groups" in script
    assert "operation_task_base" in script
    assert "task_group_detail_base" in script
    assert 'data-task-action="copy"' in script
    assert "preview-audience" in script
    assert "collectOperationTaskPayload" in script


def test_operation_setup_uses_psycopg3_sqlalchemy_urls() -> None:
    assert _sqlalchemy_database_url("postgres://u:p@db.local:5432/app") == "postgresql+psycopg://u:p@db.local:5432/app"
    assert _sqlalchemy_database_url("postgresql://u:p@db.local:5432/app") == "postgresql+psycopg://u:p@db.local:5432/app"
    assert _sqlalchemy_database_url("postgresql+psycopg://u:p@db.local:5432/app") == "postgresql+psycopg://u:p@db.local:5432/app"


def test_operation_setup_next_api_creates_groups_tasks_and_status_actions() -> None:
    client = TestClient(app)

    group_response = client.post(
        "/api/admin/automation-conversion/programs/1/setup/operation-task-groups",
        json={"group_name": "首日触达"},
    )
    assert group_response.status_code == 200
    group = group_response.json()["group"]
    assert group["group_name"] == "首日触达"

    task_response = client.post(
        "/api/admin/automation-conversion/programs/1/setup/operation-tasks",
        json={
            "task_name": "新运营任务",
            "group_id": group["id"],
            "status": "draft",
            "trigger_type": "scheduled_daily",
            "send_time": "10:00",
            "target_stage_code": "operating",
            "target_audience_code": "operating",
            "audience_day_offset": 1,
            "behavior_filter": "none",
            "content_mode": "unified",
            "unified_content_json": {"content_text": "欢迎"},
        },
    )
    assert task_response.status_code == 200
    task = task_response.json()["task"]
    assert task["task_name"] == "新运营任务"
    assert task["group_id"] == group["id"]
    assert task["target_audience_code"] == "operating"
    assert task["content_mode"] == "unified"

    update_response = client.put(
        f"/api/admin/automation-conversion/programs/1/setup/operation-tasks/{task['id']}",
        json={**task, "trigger_type": "audience_entered", "target_stage_code": "converted", "behavior_filter": "gte_10"},
    )
    assert update_response.status_code == 200
    updated = update_response.json()["task"]
    assert updated["trigger_type"] == "audience_entered"
    assert updated["target_audience_code"] == "converted"
    assert updated["behavior_filter"] == "gte_10"

    activate_response = client.post(f"/api/admin/automation-conversion/programs/1/setup/operation-tasks/{task['id']}/activate")
    assert activate_response.status_code == 200
    assert activate_response.json()["task"]["status"] == "active"

    copy_response = client.post(f"/api/admin/automation-conversion/programs/1/setup/operation-tasks/{task['id']}/copy")
    assert copy_response.status_code == 200
    assert "复制" in copy_response.json()["task"]["task_name"]

    archive_response = client.delete(f"/api/admin/automation-conversion/programs/1/setup/operation-tasks/{task['id']}")
    assert archive_response.status_code == 200
    assert archive_response.json()["task"]["status"] == "archived"


def test_operation_setup_send_content_routes_bind_to_operation_task() -> None:
    client = TestClient(app)

    task_response = client.post(
        "/api/admin/automation-conversion/programs/1/setup/operation-tasks",
        json={"task_name": "内容任务", "content_mode": "unified"},
    )
    task = task_response.json()["task"]
    content_response = client.put(
        f"/api/admin/automation-conversion/programs/1/setup/operation-tasks/{task['id']}/send-content/unified",
        json={"content_package": {"content_text": "统一话术", "image_library_ids": [1]}},
    )
    assert content_response.status_code == 200
    updated = content_response.json()["task"]
    assert updated["content_mode"] == "unified"
    assert updated["unified_content_json"]["content_text"] == "统一话术"
    assert updated["unified_content_json"]["image_library_ids"] == [1]
