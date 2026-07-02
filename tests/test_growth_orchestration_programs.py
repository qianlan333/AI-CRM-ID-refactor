from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.growth_orchestration.application import list_growth_programs
from aicrm_next.growth_orchestration.dto import GrowthProgram
from aicrm_next.growth_orchestration.repository import GROWTH_PROGRAMS_SQL, InMemoryGrowthProgramRepository
from aicrm_next.main import create_app


def _client(monkeypatch) -> TestClient:
    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "0")
    monkeypatch.setenv("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", "1")
    return TestClient(create_app(), raise_server_exceptions=False)


def test_growth_orchestration_programs_api_returns_empty_without_database(monkeypatch) -> None:
    response = _client(monkeypatch).get("/api/admin/growth-orchestration/programs")

    assert response.status_code == 200
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert response.json() == {"ok": True, "items": [], "limit": 50, "offset": 0}


def test_growth_orchestration_programs_application_lists_all_active_program_types() -> None:
    repo = InMemoryGrowthProgramRepository(
        [
            GrowthProgram(
                program_key="campaign:c-1",
                program_type="campaign",
                title="Campaign",
                status="running",
                owner_userid="owner-1",
                member_count=10,
                active_member_count=8,
                task_count=3,
                source_table="campaigns",
                source_id="1",
            ),
            GrowthProgram(
                program_key="group_ops:g-1",
                program_type="group_ops",
                title="Group Ops",
                status="active",
                owner_userid="owner-2",
                member_count=20,
                active_member_count=20,
                task_count=5,
                source_table="automation_group_ops_plans",
                source_id="2",
            ),
            GrowthProgram(
                program_key="cloud_plan:plan-3",
                program_type="cloud_plan",
                title="Cloud Plan",
                status="active",
                member_count=7,
                active_member_count=6,
                task_count=4,
                source_table="cloud_broadcast_plans",
                source_id="plan-3",
            ),
            GrowthProgram(
                program_key="ai_audience_package:pkg",
                program_type="ai_audience_package",
                title="AI Audience",
                status="active",
                member_count=11,
                active_member_count=10,
                source_table="ai_audience_package",
                source_id="4",
            ),
        ]
    )

    payload = list_growth_programs(repo=repo)

    assert {item["program_type"] for item in payload["items"]} == {
        "campaign",
        "group_ops",
        "cloud_plan",
        "ai_audience_package",
    }
    assert {item["source_table"] for item in payload["items"]} == {
        "campaigns",
        "automation_group_ops_plans",
        "cloud_broadcast_plans",
        "ai_audience_package",
    }


def test_growth_orchestration_program_sql_uses_only_active_unionid_safe_sources() -> None:
    assert "automation_workflow" not in GROWTH_PROGRAMS_SQL
    assert "automation_program" not in GROWTH_PROGRAMS_SQL
    assert "automation_membership_v2" not in GROWTH_PROGRAMS_SQL
    assert "automation_task_plan_v2" not in GROWTH_PROGRAMS_SQL
    assert "external_userid" not in GROWTH_PROGRAMS_SQL
    assert "cloud_broadcast_plans" in GROWTH_PROGRAMS_SQL
    assert "campaigns" in GROWTH_PROGRAMS_SQL
