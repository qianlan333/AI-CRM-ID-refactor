from __future__ import annotations

import json
from pathlib import Path

import pytest

import tools.check_phase4bx_agent_runs_fixture_runtime as checker
from aicrm_next.automation_engine.agent_runs import agent_run_side_effect_safety, normalize_agent_run_filters
from aicrm_next.automation_engine.dto import AgentRunDetailRequest, AgentRunListRequest
from aicrm_next.automation_engine.repo import build_automation_repository, reset_automation_fixture_state
from aicrm_next.shared.errors import ContractError


ROOT = Path(__file__).resolve().parents[1]


def _all_real_safety_false(payload: dict) -> bool:
    safety = payload.get("side_effect_safety") or {}
    return bool(safety) and all(value is False for key, value in safety.items() if key.startswith("real_"))


def test_checker_current_repo_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_fixture_repository_lists_seeded_agent_runs() -> None:
    reset_automation_fixture_state()
    repo = build_automation_repository()

    rows, total, filters = repo.list_agent_runs({"page": 1, "page_size": 50})

    assert total >= 2
    assert filters["page"] == 1
    assert filters["page_size"] == 50
    assert {item["run_id"] for item in rows} >= {"phase4bo_run_completed_metadata", "phase4bo_run_failed_metadata"}
    assert all(item["visibility"] == "masked" for item in rows)
    assert all(str(item["external_contact_id"]).startswith("***") for item in rows)


def test_fixture_repository_filters_agent_runs_without_side_effects() -> None:
    reset_automation_fixture_state()
    repo = build_automation_repository()

    rows, total, filters = repo.list_agent_runs(
        {
            "agent_code": "phase4bg_review_agent",
            "run_status": "completed",
            "trigger_source": "fixture",
            "task_id": 1,
            "workflow_id": 1,
            "has_error": False,
            "visibility": "console",
        }
    )

    assert total == 1
    assert filters["visibility"] == "console"
    assert rows[0]["run_id"] == "phase4bo_run_completed_metadata"
    assert rows[0]["external_contact_id"] == "wm_external_001"
    assert rows[0]["userid"] == "user_phase4_fixture"


def test_fixture_repository_detail_returns_agent_run_metadata() -> None:
    reset_automation_fixture_state()
    repo = build_automation_repository()

    run = repo.get_agent_run("phase4bo_run_failed_metadata", {"visibility": "console"})

    assert run is not None
    assert run["run_id"] == "phase4bo_run_failed_metadata"
    assert run["run_status"] == "failed"
    assert run["error_code"] == "fixture_agent_run_failed"
    assert run["output_count"] == 0


def test_application_queries_list_and_detail() -> None:
    pytest.importorskip("fastapi")
    from aicrm_next.automation_engine.application import GetAgentRunDetailQuery, ListAgentRunsQuery

    reset_automation_fixture_state()
    list_body = ListAgentRunsQuery()(AgentRunListRequest(agent_code="phase4bg_followup_agent"))
    detail_body = GetAgentRunDetailQuery()(AgentRunDetailRequest(run_id="phase4bo_run_failed_metadata"))

    assert list_body["route_owner"] == "ai_crm_next"
    assert list_body["count"] == 1
    assert list_body["rows"][0]["run_id"] == "phase4bo_run_failed_metadata"
    assert detail_body["run"]["run_id"] == "phase4bo_run_failed_metadata"
    assert _all_real_safety_false(detail_body)


def test_application_detail_not_found_raises() -> None:
    pytest.importorskip("fastapi")
    from aicrm_next.automation_engine.application import GetAgentRunDetailQuery
    from aicrm_next.shared.errors import NotFoundError

    reset_automation_fixture_state()

    with pytest.raises(NotFoundError, match="agent run not found"):
        GetAgentRunDetailQuery()(AgentRunDetailRequest(run_id="missing"))


def test_dangerous_agent_run_filter_fields_rejected() -> None:
    with pytest.raises(ContractError, match="dangerous agent run field"):
        normalize_agent_run_filters({"run_execution": True})

    with pytest.raises(ContractError, match="dangerous agent run field"):
        normalize_agent_run_filters({"filters": {"orchestration": True}})


def test_invalid_agent_run_filters_rejected() -> None:
    with pytest.raises(ContractError, match="run_status"):
        normalize_agent_run_filters({"run_status": "generated"})

    with pytest.raises(ContractError, match="trigger_source"):
        normalize_agent_run_filters({"trigger_source": "openclaw"})

    with pytest.raises(ContractError, match="visibility"):
        normalize_agent_run_filters({"visibility": "raw"})


def test_side_effect_safety_all_false() -> None:
    assert all(value is False for value in agent_run_side_effect_safety().values())


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


def test_api_list_and_detail_when_fastapi_available(client) -> None:
    list_response = client.get("/api/admin/automation-conversion/agent-runs?agent_code=phase4bg_review_agent")
    assert list_response.status_code == 200
    list_body = list_response.json()
    assert list_body["route_owner"] == "ai_crm_next"
    assert list_body["source_status"] == "fixture_local_contract"
    assert list_body["count"] == 1
    assert list_body["rows"][0]["run_id"] == "phase4bo_run_completed_metadata"
    assert _all_real_safety_false(list_body)

    detail_response = client.get("/api/admin/automation-conversion/agent-runs/phase4bo_run_failed_metadata")
    assert detail_response.status_code == 200
    detail_body = detail_response.json()
    assert detail_body["run"]["run_id"] == "phase4bo_run_failed_metadata"
    assert _all_real_safety_false(detail_body)


def test_api_detail_not_found_when_fastapi_available(client) -> None:
    response = client.get("/api/admin/automation-conversion/agent-runs/missing")
    assert response.status_code == 404


def test_api_blocks_fixture_success_in_production_when_fastapi_available(monkeypatch) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from aicrm_next.main import create_app

    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "0")
    monkeypatch.setenv("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", "1")
    reset_automation_fixture_state()

    response = TestClient(create_app(), raise_server_exceptions=False).get(
        "/api/admin/automation-conversion/agent-runs"
    )

    assert response.status_code == 503
    body = response.json()
    assert body["ok"] is False
    assert body["error_code"] == "production_repository_not_enabled"
