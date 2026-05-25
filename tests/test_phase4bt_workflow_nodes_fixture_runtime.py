from __future__ import annotations

import json
from pathlib import Path

import pytest

import tools.check_phase4bt_workflow_nodes_fixture_runtime as checker
from aicrm_next.automation_engine.repo import build_automation_repository, reset_automation_fixture_state
from aicrm_next.automation_engine.workflow_nodes import (
    normalize_workflow_node_create_payload,
    workflow_node_side_effect_safety,
)
from aicrm_next.shared.errors import ContractError


ROOT = Path(__file__).resolve().parents[1]


def _all_real_safety_false(payload: dict) -> bool:
    safety = payload.get("side_effect_safety") or {}
    return bool(safety) and all(value is False for key, value in safety.items() if key.startswith("real_"))


def test_checker_current_repo_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_fixture_repository_lists_seeded_workflow_nodes() -> None:
    reset_automation_fixture_state()
    repo = build_automation_repository()

    rows, total = repo.list_workflow_nodes({"workflow_id": 1, "include_archived": False, "limit": 50, "offset": 0})

    assert total >= 2
    assert {item["node_code"] for item in rows} >= {"phase4ax_entry_node", "phase4ax_followup_node"}
    assert all(item["workflow_id"] == 1 for item in rows)
    assert all(item["enabled"] is False for item in rows)


def test_create_workflow_node_is_idempotent_and_audited() -> None:
    reset_automation_fixture_state()
    repo = build_automation_repository()
    payload = {
        "program_id": 7,
        "workflow_id": 9,
        "node_name": "Phase 4BT Followup Node",
        "node_code": "phase4bt_followup_node",
        "node_type": "metadata",
        "idempotency_key": "node-create",
        "operator": "pytest",
    }

    created = repo.create_workflow_node(payload, idempotency_key="node-create", operator="pytest")
    replay = repo.create_workflow_node(payload, idempotency_key="node-create", operator="pytest")

    assert created["node"]["node_code"] == "phase4bt_followup_node"
    assert created["node"]["enabled"] is False
    assert created["audit_event"]["resource_type"] == "workflow_node"
    assert created["rollback_payload"]["delete_approved"] is False
    assert created["idempotent_replay"] is False
    assert replay["node"]["id"] == created["node"]["id"]
    assert replay["idempotent_replay"] is True


def test_duplicate_workflow_node_code_rejected_per_workflow() -> None:
    reset_automation_fixture_state()
    repo = build_automation_repository()
    payload = {"workflow_id": 8, "node_name": "Duplicate", "node_code": "duplicate", "idempotency_key": "node-a"}
    repo.create_workflow_node(payload, idempotency_key="node-a", operator="pytest")

    with pytest.raises(ContractError, match="workflow node code already exists"):
        repo.create_workflow_node({**payload, "node_name": "Duplicate B"}, idempotency_key="node-b", operator="pytest")


def test_invalid_workflow_node_status_rejected() -> None:
    with pytest.raises(ContractError, match="workflow node status"):
        normalize_workflow_node_create_payload({"node_name": "Bad Status", "status": "active"})


def test_invalid_workflow_node_type_rejected() -> None:
    with pytest.raises(ContractError, match="workflow node type"):
        normalize_workflow_node_create_payload({"node_name": "Bad Type", "node_type": "execute"})


def test_dangerous_workflow_node_fields_rejected() -> None:
    with pytest.raises(ContractError, match="dangerous workflow node field"):
        normalize_workflow_node_create_payload(
            {
                "node_name": "Danger",
                "idempotency_key": "danger",
                "config": {"timer": True},
            }
        )


def test_side_effect_safety_all_false() -> None:
    assert all(value is False for value in workflow_node_side_effect_safety().values())


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
    list_response = client.get("/api/admin/automation-conversion/workflow-nodes?workflow_id=1")
    assert list_response.status_code == 200
    list_body = list_response.json()
    assert list_body["route_owner"] == "ai_crm_next"
    assert list_body["source_status"] == "fixture_local_contract"
    assert list_body["count"] >= 2
    assert _all_real_safety_false(list_body)

    create_response = client.post(
        "/api/admin/automation-conversion/workflow-nodes",
        json={
            "program_id": 9,
            "workflow_id": 9,
            "node_name": "API Phase 4BT",
            "node_code": "api_phase4bt",
            "node_type": "metadata",
            "idempotency_key": "api-phase4bt",
            "operator": "pytest",
        },
    )
    assert create_response.status_code == 201
    create_body = create_response.json()
    assert create_body["node"]["node_code"] == "api_phase4bt"
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
        "/api/admin/automation-conversion/workflow-nodes",
        json={"program_id": 1, "workflow_id": 1, "node_name": "Prod", "idempotency_key": "prod-key"},
    )

    assert response.status_code == 503
    body = response.json()
    assert body["ok"] is False
    assert body["error_code"] == "production_repository_not_enabled"
