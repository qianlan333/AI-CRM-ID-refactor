from __future__ import annotations

import json
from pathlib import Path

import pytest

import tools.check_phase4bw_agent_outputs_fixture_runtime as checker
from aicrm_next.automation_engine.agent_outputs import agent_output_side_effect_safety, normalize_agent_output_filters
from aicrm_next.automation_engine.dto import AgentOutputDetailRequest, AgentOutputListRequest
from aicrm_next.automation_engine.repo import build_automation_repository, reset_automation_fixture_state
from aicrm_next.shared.errors import ContractError


ROOT = Path(__file__).resolve().parents[1]


def _all_real_safety_false(payload: dict) -> bool:
    safety = payload.get("side_effect_safety") or {}
    return bool(safety) and all(value is False for key, value in safety.items() if key.startswith("real_"))


def test_checker_current_repo_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_fixture_repository_lists_seeded_agent_outputs() -> None:
    reset_automation_fixture_state()
    repo = build_automation_repository()

    rows, total, filters = repo.list_agent_outputs({"page": 1, "page_size": 50})

    assert total >= 2
    assert filters["page"] == 1
    assert filters["page_size"] == 50
    assert {item["output_id"] for item in rows} >= {"phase4bk_output_reply_draft", "phase4bk_output_route_decision"}
    assert all(item["visibility"] == "masked" for item in rows)
    assert all(str(item["external_contact_id"]).startswith("***") for item in rows)


def test_fixture_repository_filters_agent_outputs_without_side_effects() -> None:
    reset_automation_fixture_state()
    repo = build_automation_repository()

    rows, total, filters = repo.list_agent_outputs(
        {
            "agent_code": "phase4bg_review_agent",
            "output_type": "reply_draft",
            "applied_status": "pending_review",
            "min_confidence": 0.8,
            "max_confidence": 0.9,
            "visibility": "console",
        }
    )

    assert total == 1
    assert filters["visibility"] == "console"
    assert rows[0]["output_id"] == "phase4bk_output_reply_draft"
    assert rows[0]["external_contact_id"] == "wm_external_001"
    assert rows[0]["userid"] == "user_phase4_fixture"


def test_fixture_repository_detail_returns_run_projection() -> None:
    reset_automation_fixture_state()
    repo = build_automation_repository()

    output = repo.get_agent_output("phase4bk_output_reply_draft", {"visibility": "console"})

    assert output is not None
    assert output["output_id"] == "phase4bk_output_reply_draft"
    assert output["run_id"] == "phase4bo_run_draft"
    assert output["output_type"] == "reply_draft"


def test_application_queries_list_and_detail() -> None:
    pytest.importorskip("fastapi")
    from aicrm_next.automation_engine.application import GetAgentOutputDetailQuery, ListAgentOutputsQuery

    reset_automation_fixture_state()
    list_body = ListAgentOutputsQuery()(AgentOutputListRequest(agent_code="phase4bg_followup_agent"))
    detail_body = GetAgentOutputDetailQuery()(AgentOutputDetailRequest(output_id="phase4bk_output_route_decision"))

    assert list_body["route_owner"] == "ai_crm_next"
    assert list_body["count"] == 1
    assert list_body["rows"][0]["output_id"] == "phase4bk_output_route_decision"
    assert detail_body["output"]["output_id"] == "phase4bk_output_route_decision"
    assert detail_body["run"]["execution_enabled"] is False
    assert detail_body["run"]["generation_enabled"] is False
    assert _all_real_safety_false(detail_body)


def test_application_detail_not_found_raises() -> None:
    pytest.importorskip("fastapi")
    from aicrm_next.automation_engine.application import GetAgentOutputDetailQuery
    from aicrm_next.shared.errors import NotFoundError

    reset_automation_fixture_state()

    with pytest.raises(NotFoundError, match="agent output not found"):
        GetAgentOutputDetailQuery()(AgentOutputDetailRequest(output_id="missing"))


def test_dangerous_agent_output_filter_fields_rejected() -> None:
    with pytest.raises(ContractError, match="dangerous agent output field"):
        normalize_agent_output_filters({"export": True})

    with pytest.raises(ContractError, match="dangerous agent output field"):
        normalize_agent_output_filters({"filters": {"llm_generation": True}})


def test_invalid_agent_output_filters_rejected() -> None:
    with pytest.raises(ContractError, match="output_type"):
        normalize_agent_output_filters({"output_type": "llm"})

    with pytest.raises(ContractError, match="visibility"):
        normalize_agent_output_filters({"visibility": "raw"})

    with pytest.raises(ContractError, match="min_confidence"):
        normalize_agent_output_filters({"min_confidence": 0.9, "max_confidence": 0.1})


def test_side_effect_safety_all_false() -> None:
    assert all(value is False for value in agent_output_side_effect_safety().values())


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
    list_response = client.get("/api/admin/automation-conversion/agent-outputs?agent_code=phase4bg_review_agent")
    assert list_response.status_code == 200
    list_body = list_response.json()
    assert list_body["route_owner"] == "ai_crm_next"
    assert list_body["source_status"] == "fixture_local_contract"
    assert list_body["count"] == 1
    assert list_body["rows"][0]["output_id"] == "phase4bk_output_reply_draft"
    assert _all_real_safety_false(list_body)

    detail_response = client.get("/api/admin/automation-conversion/agent-outputs/phase4bk_output_reply_draft")
    assert detail_response.status_code == 200
    detail_body = detail_response.json()
    assert detail_body["output"]["output_id"] == "phase4bk_output_reply_draft"
    assert detail_body["run"]["execution_enabled"] is False
    assert _all_real_safety_false(detail_body)


def test_api_detail_not_found_when_fastapi_available(client) -> None:
    response = client.get("/api/admin/automation-conversion/agent-outputs/missing")
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
        "/api/admin/automation-conversion/agent-outputs"
    )

    assert response.status_code == 503
    body = response.json()
    assert body["ok"] is False
    assert body["error_code"] == "production_repository_not_enabled"
