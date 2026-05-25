from __future__ import annotations

import json
from pathlib import Path

import pytest

import tools.check_phase4bu_tasks_fixture_runtime as checker
from aicrm_next.automation_engine.repo import build_automation_repository, reset_automation_fixture_state
from aicrm_next.automation_engine.tasks import normalize_task_create_payload, task_side_effect_safety
from aicrm_next.shared.errors import ContractError


ROOT = Path(__file__).resolve().parents[1]


def _all_real_safety_false(payload: dict) -> bool:
    safety = payload.get("side_effect_safety") or {}
    return bool(safety) and all(value is False for key, value in safety.items() if key.startswith("real_"))


def test_checker_current_repo_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_fixture_repository_lists_seeded_tasks() -> None:
    reset_automation_fixture_state()
    repo = build_automation_repository()

    rows, total = repo.list_tasks({"workflow_id": 1, "include_archived": False, "limit": 50, "offset": 0})

    assert total >= 2
    assert {item["task_code"] for item in rows} >= {"phase4bc_followup_task", "phase4bc_review_task"}
    assert all(item["workflow_id"] == 1 for item in rows)
    assert all(item["enabled"] is False for item in rows)


def test_create_task_is_idempotent_and_audited() -> None:
    reset_automation_fixture_state()
    repo = build_automation_repository()
    payload = {
        "program_id": 7,
        "workflow_id": 9,
        "node_id": 10,
        "group_id": 11,
        "task_name": "Phase 4BU Followup Task",
        "task_code": "phase4bu_followup_task",
        "task_type": "followup",
        "idempotency_key": "task-create",
        "operator": "pytest",
    }

    created = repo.create_task(payload, idempotency_key="task-create", operator="pytest")
    replay = repo.create_task(payload, idempotency_key="task-create", operator="pytest")

    assert created["task"]["task_code"] == "phase4bu_followup_task"
    assert created["task"]["enabled"] is False
    assert created["audit_event"]["resource_type"] == "task"
    assert created["rollback_payload"]["delete_approved"] is False
    assert created["idempotent_replay"] is False
    assert replay["task"]["id"] == created["task"]["id"]
    assert replay["idempotent_replay"] is True


def test_duplicate_task_code_rejected_per_workflow() -> None:
    reset_automation_fixture_state()
    repo = build_automation_repository()
    payload = {"workflow_id": 8, "task_name": "Duplicate", "task_code": "duplicate", "idempotency_key": "task-a"}
    repo.create_task(payload, idempotency_key="task-a", operator="pytest")

    with pytest.raises(ContractError, match="task code already exists"):
        repo.create_task({**payload, "task_name": "Duplicate B"}, idempotency_key="task-b", operator="pytest")


def test_invalid_task_status_rejected() -> None:
    with pytest.raises(ContractError, match="task status"):
        normalize_task_create_payload({"task_name": "Bad Status", "status": "active"})


def test_invalid_task_type_rejected() -> None:
    with pytest.raises(ContractError, match="task type"):
        normalize_task_create_payload({"task_name": "Bad Type", "task_type": "execute"})


def test_dangerous_task_fields_rejected() -> None:
    with pytest.raises(ContractError, match="dangerous task field"):
        normalize_task_create_payload(
            {
                "task_name": "Danger",
                "idempotency_key": "danger",
                "config": {"run_due": True},
            }
        )


def test_timer_task_fields_rejected() -> None:
    with pytest.raises(ContractError, match="dangerous task field"):
        normalize_task_create_payload(
            {
                "task_name": "Timer Danger",
                "idempotency_key": "timer-danger",
                "metadata": {"timer": True},
            }
        )


def test_side_effect_safety_all_false() -> None:
    assert all(value is False for value in task_side_effect_safety().values())


@pytest.fixture()
def client(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from aicrm_next.main import create_app

    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "0")
    monkeypatch.setenv("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", "1")
    reset_automation_fixture_state()
    return TestClient(create_app(), raise_server_exceptions=False)


def test_api_list_and_create_when_fastapi_available(client) -> None:
    list_response = client.get("/api/admin/automation-conversion/tasks?workflow_id=1")
    assert list_response.status_code == 200
    list_body = list_response.json()
    assert list_body["route_owner"] == "ai_crm_next"
    assert list_body["source_status"] == "fixture_local_contract"
    assert list_body["count"] >= 2
    assert _all_real_safety_false(list_body)

    create_response = client.post(
        "/api/admin/automation-conversion/tasks",
        json={
            "program_id": 9,
            "workflow_id": 9,
            "node_id": 9,
            "group_id": 9,
            "task_name": "API Phase 4BU",
            "task_code": "api_phase4bu",
            "task_type": "metadata",
            "idempotency_key": "api-phase4bu",
            "operator": "pytest",
        },
    )
    assert create_response.status_code == 201
    create_body = create_response.json()
    assert create_body["task"]["task_code"] == "api_phase4bu"
    assert create_body["idempotent_replay"] is False
    assert _all_real_safety_false(create_body)


def test_api_blocks_fixture_success_in_production_when_fastapi_available(monkeypatch) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from aicrm_next.main import create_app

    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "0")
    monkeypatch.setenv("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", "1")
    reset_automation_fixture_state()

    response = TestClient(create_app(), raise_server_exceptions=False).post(
        "/api/admin/automation-conversion/tasks",
        json={"program_id": 1, "workflow_id": 1, "task_name": "Prod", "idempotency_key": "prod-key"},
    )

    assert response.status_code == 503
    body = response.json()
    assert body["ok"] is False
    assert body["error_code"] == "production_repository_not_enabled"
