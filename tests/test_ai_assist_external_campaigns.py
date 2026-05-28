from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.ai_assist import external_campaigns
from aicrm_next.main import create_app


def test_external_campaign_create_requires_internal_token(monkeypatch) -> None:
    monkeypatch.setenv("AUTOMATION_INTERNAL_API_TOKEN", "internal-token")
    client = TestClient(create_app())

    response = client.post(
        "/api/ai-assist/external/campaigns",
        json={
            "owner_userid": "HuangYouCan",
            "external_userid": "external-1",
            "scheduled_for": "2026-05-28 16:15",
            "message": "咱今天还报名吗？",
        },
    )

    assert response.status_code == 401
    assert response.json()["error"] == "missing_internal_token"


def test_external_campaign_create_route_invokes_creator_after_auth(monkeypatch) -> None:
    monkeypatch.setenv("AUTOMATION_INTERNAL_API_TOKEN", "internal-token")
    captured = {}

    def fake_create(payload):
        captured["payload"] = payload
        return {
            "ok": True,
            "route_owner": "ai_crm_next",
            "created_count": 1,
            "existing_count": 0,
            "campaigns": [{"campaign_code": "camp_ext_test", "status": "created"}],
        }

    monkeypatch.setattr(external_campaigns, "create_external_campaigns", fake_create)
    client = TestClient(create_app())

    response = client.post(
        "/api/ai-assist/external/campaigns",
        headers={"Authorization": "Bearer internal-token"},
        json={
            "owner_userid": "HuangYouCan",
            "external_userid": "external-1",
            "scheduled_for": "2026-05-28 16:15",
            "message": "咱今天还报名吗？",
        },
    )

    assert response.status_code == 200
    assert response.json()["created_count"] == 1
    assert captured["payload"]["owner_userid"] == "HuangYouCan"


def test_external_campaign_status_requires_internal_token(monkeypatch) -> None:
    monkeypatch.setenv("AUTOMATION_INTERNAL_API_TOKEN", "internal-token")
    client = TestClient(create_app())

    response = client.get("/api/ai-assist/external/campaigns/camp_ext_test")

    assert response.status_code == 401
    assert response.json()["error"] == "missing_internal_token"


def test_external_campaign_status_route_invokes_reader_after_auth(monkeypatch) -> None:
    monkeypatch.setenv("AUTOMATION_INTERNAL_API_TOKEN", "internal-token")
    captured = {}

    def fake_get(campaign_code):
        captured["campaign_code"] = campaign_code
        return {
            "ok": True,
            "route_owner": "ai_crm_next",
            "campaign": {"campaign_code": campaign_code},
            "total_members": 1,
            "scheduled_jobs": 1,
        }

    monkeypatch.setattr(external_campaigns, "get_external_campaign_status", fake_get)
    client = TestClient(create_app())

    response = client.get(
        "/api/ai-assist/external/campaigns/camp_ext_test",
        headers={"Authorization": "Bearer internal-token"},
    )

    assert response.status_code == 200
    assert response.json()["campaign"]["campaign_code"] == "camp_ext_test"
    assert captured["campaign_code"] == "camp_ext_test"


def test_external_campaign_normalizes_multi_day_steps() -> None:
    steps = external_campaigns._normalize_step_list(
        [
            {"scheduled_for": "2026-05-28 16:15", "content_text": "D0"},
            {"day_offset": 1, "send_time": "10:30", "content_text": "D1"},
        ],
        {},
        {"external_userid": "external-1"},
        timezone_name="Asia/Shanghai",
    )

    assert steps[0]["day_offset"] == 0
    assert steps[0]["send_time"] == "16:15"
    assert steps[0]["scheduled_for"] == "2026-05-28T16:15:00+08:00"
    assert steps[1]["day_offset"] == 1
    assert steps[1]["send_time"] == "10:30"
