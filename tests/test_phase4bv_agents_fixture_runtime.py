from __future__ import annotations

import json
from pathlib import Path

import pytest

import tools.check_phase4bv_agents_fixture_runtime as checker
from aicrm_next.automation_engine.agents import agent_side_effect_safety, normalize_agent_create_payload
from aicrm_next.automation_engine.repo import build_automation_repository, reset_automation_fixture_state
from aicrm_next.shared.errors import ContractError


ROOT = Path(__file__).resolve().parents[1]


def _all_real_safety_false(payload: dict) -> bool:
    safety = payload.get("side_effect_safety") or {}
    return bool(safety) and all(value is False for key, value in safety.items() if key.startswith("real_"))


def test_checker_current_repo_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_fixture_repository_lists_seeded_agents() -> None:
    reset_automation_fixture_state()
    repo = build_automation_repository()

    rows, total = repo.list_agents({"workflow_id": 1, "include_archived": False, "limit": 50, "offset": 0})

    assert total >= 2
    assert {item["agent_code"] for item in rows} >= {"phase4bg_review_agent", "phase4bg_followup_agent"}
    assert all(item["workflow_id"] == 1 for item in rows)
    assert all(item["enabled"] is False for item in rows)


def test_create_agent_is_idempotent_and_audited() -> None:
    reset_automation_fixture_state()
    repo = build_automation_repository()
    payload = {
        "program_id": 7,
        "workflow_id": 9,
        "node_id": 10,
        "task_id": 11,
        "agent_name": "Phase 4BV Review Agent",
        "agent_code": "phase4bv_review_agent",
        "agent_type": "reviewer",
        "idempotency_key": "agent-create",
        "operator": "pytest",
    }

    created = repo.create_agent(payload, idempotency_key="agent-create", operator="pytest")
    replay = repo.create_agent(payload, idempotency_key="agent-create", operator="pytest")

    assert created["agent"]["agent_code"] == "phase4bv_review_agent"
    assert created["agent"]["enabled"] is False
    assert created["audit_event"]["resource_type"] == "agent"
    assert created["rollback_payload"]["delete_approved"] is False
    assert created["idempotent_replay"] is False
    assert replay["agent"]["id"] == created["agent"]["id"]
    assert replay["idempotent_replay"] is True


def test_duplicate_agent_code_rejected_per_workflow() -> None:
    reset_automation_fixture_state()
    repo = build_automation_repository()
    payload = {"workflow_id": 8, "agent_name": "Duplicate", "agent_code": "duplicate", "idempotency_key": "agent-a"}
    repo.create_agent(payload, idempotency_key="agent-a", operator="pytest")

    with pytest.raises(ContractError, match="agent code already exists"):
        repo.create_agent({**payload, "agent_name": "Duplicate B"}, idempotency_key="agent-b", operator="pytest")


def test_invalid_agent_status_rejected() -> None:
    with pytest.raises(ContractError, match="agent status"):
        normalize_agent_create_payload({"agent_name": "Bad Status", "status": "active"})


def test_invalid_agent_type_rejected() -> None:
    with pytest.raises(ContractError, match="agent type"):
        normalize_agent_create_payload({"agent_name": "Bad Type", "agent_type": "llm"})


def test_dangerous_agent_config_fields_rejected() -> None:
    with pytest.raises(ContractError, match="dangerous agent field"):
        normalize_agent_create_payload(
            {
                "agent_name": "Danger",
                "idempotency_key": "danger",
                "config": {"llm": True},
            }
        )


def test_dangerous_agent_metadata_fields_rejected() -> None:
    with pytest.raises(ContractError, match="dangerous agent field"):
        normalize_agent_create_payload(
            {
                "agent_name": "MCP Danger",
                "idempotency_key": "mcp-danger",
                "metadata": {"openclaw": True},
            }
        )


def test_side_effect_safety_all_false() -> None:
    assert all(value is False for value in agent_side_effect_safety().values())


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
    list_response = client.get("/api/admin/automation-conversion/agents?workflow_id=1")
    assert list_response.status_code == 200
    list_body = list_response.json()
    assert list_body["route_owner"] == "ai_crm_next"
    assert list_body["source_status"] == "fixture_local_contract"
    assert list_body["count"] >= 2
    assert _all_real_safety_false(list_body)

    create_response = client.post(
        "/api/admin/automation-conversion/agents",
        json={
            "program_id": 9,
            "workflow_id": 9,
            "node_id": 9,
            "task_id": 9,
            "agent_name": "API Phase 4BV",
            "agent_code": "api_phase4bv",
            "agent_type": "metadata",
            "idempotency_key": "api-phase4bv",
            "operator": "pytest",
        },
    )
    assert create_response.status_code == 201
    create_body = create_response.json()
    assert create_body["agent"]["agent_code"] == "api_phase4bv"
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
        "/api/admin/automation-conversion/agents",
        json={"program_id": 1, "workflow_id": 1, "agent_name": "Prod", "idempotency_key": "prod-key"},
    )

    assert response.status_code == 503
    body = response.json()
    assert body["ok"] is False
    assert body["error_code"] == "production_repository_not_enabled"
