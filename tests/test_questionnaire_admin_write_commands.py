from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse

from aicrm_next.main import create_app
import aicrm_next.questionnaire.api as questionnaire_api
from aicrm_next.questionnaire.admin_write import get_questionnaire_admin_write_audit_events


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    return TestClient(create_app())


def _payload(title: str = "测试问卷") -> dict:
    return {
        "title": title,
        "description": "测试描述",
        "questions": [
            {
                "id": "q1",
                "type": "single_choice",
                "title": "是否激活",
                "required": True,
                "options": [{"id": "yes", "label": "是", "value": "yes"}],
            }
        ],
    }


def _assert_command(body: dict, command_name: str, status: str) -> None:
    assert body["ok"] is True
    assert body["command_name"] == command_name
    assert body["source_status"] == "next_command"
    assert body["write_model_status"] == status
    assert body["route_owner"] == "ai_crm_next"
    assert body["fallback_used"] is False
    assert body["real_external_call_executed"] is False
    assert body["audit_recorded"] is True
    assert body["command_id"]
    assert body["questionnaire_id"]


def test_questionnaire_admin_write_routes_execute_next_commandbus(client: TestClient) -> None:
    create = client.post("/api/admin/questionnaires", json=_payload(), headers={"Idempotency-Key": "qw-create"})
    assert create.status_code == 200
    _assert_command(create.json(), "questionnaire.admin.create", "created")
    questionnaire_id = create.json()["questionnaire_id"]

    update = client.put(
        f"/api/admin/questionnaires/{questionnaire_id}",
        json=_payload("测试问卷更新"),
        headers={"Idempotency-Key": "qw-update"},
    )
    assert update.status_code == 200
    _assert_command(update.json(), "questionnaire.admin.update", "updated")
    assert update.json()["questionnaire"]["title"] == "测试问卷更新"

    duplicate = client.post(
        f"/api/admin/questionnaires/{questionnaire_id}/duplicate",
        json={"title": "测试问卷复制"},
        headers={"Idempotency-Key": "qw-duplicate"},
    )
    assert duplicate.status_code == 200
    _assert_command(duplicate.json(), "questionnaire.admin.duplicate", "duplicated")
    assert duplicate.json()["source_questionnaire_id"] == questionnaire_id
    assert duplicate.json()["questionnaire"]["is_disabled"] is True

    publish = client.post(
        f"/api/admin/questionnaires/{questionnaire_id}/publish",
        json={},
        headers={"Idempotency-Key": "qw-publish"},
    )
    assert publish.status_code == 200
    _assert_command(publish.json(), "questionnaire.admin.publish", "published")
    assert publish.json()["side_effect_plan"]["adapter_mode"] == "real_blocked"

    disable = client.post(
        f"/api/admin/questionnaires/{questionnaire_id}/disable",
        json={},
        headers={"Idempotency-Key": "qw-disable"},
    )
    assert disable.status_code == 200
    _assert_command(disable.json(), "questionnaire.admin.disable", "disabled")
    assert disable.json()["questionnaire"]["is_disabled"] is True

    enable = client.post(
        f"/api/admin/questionnaires/{questionnaire_id}/enable",
        json={},
        headers={"Idempotency-Key": "qw-enable"},
    )
    assert enable.status_code == 200
    _assert_command(enable.json(), "questionnaire.admin.enable", "enabled")
    assert enable.json()["questionnaire"]["is_disabled"] is False

    delete = client.delete(
        f"/api/admin/questionnaires/{questionnaire_id}",
        headers={"Idempotency-Key": "qw-delete"},
    )
    assert delete.status_code == 200
    _assert_command(delete.json(), "questionnaire.admin.delete", "soft_deleted")
    assert delete.json()["delete_mode"] == "soft_delete_disable"

    audit_events = get_questionnaire_admin_write_audit_events()
    command_ids = {event["command_id"] for event in audit_events}
    for response in [create, update, duplicate, publish, disable, enable, delete]:
        assert response.json()["command_id"] in command_ids


def test_questionnaire_admin_write_routes_return_controlled_errors(client: TestClient) -> None:
    missing_title = client.post("/api/admin/questionnaires", json={"description": "no title"})
    assert missing_title.status_code == 400
    assert missing_title.json()["source_status"] == "input_error"
    assert missing_title.json()["fallback_used"] is False

    missing_questionnaire = client.post("/api/admin/questionnaires/9999/publish", json={})
    assert missing_questionnaire.status_code == 404
    assert missing_questionnaire.json()["source_status"] == "not_found"


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("post", "/api/admin/questionnaires", _payload()),
        ("put", "/api/admin/questionnaires/11", _payload("生产更新")),
        ("post", "/api/admin/questionnaires/11/disable", {"is_disabled": True}),
        ("post", "/api/admin/questionnaires/11/enable", {}),
        ("delete", "/api/admin/questionnaires/11", {}),
    ],
)
def test_questionnaire_admin_write_production_uses_legacy_fallback(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
    body: dict,
) -> None:
    forwarded: list[tuple[str, str]] = []

    async def fake_forward_to_legacy_flask(request):
        forwarded.append((request.method, request.url.path))
        return JSONResponse(
            {"ok": True, "questionnaire": {"id": 11, "title": "legacy"}, "fallback_used": True},
            headers={"X-AICRM-Compatibility-Facade": "legacy_flask_facade"},
        )

    monkeypatch.setattr(questionnaire_api, "production_data_ready", lambda: True)
    monkeypatch.setattr(questionnaire_api, "forward_to_legacy_flask", fake_forward_to_legacy_flask)

    client = TestClient(create_app())
    request = getattr(client, method)
    kwargs = {"json": body} if method != "delete" else {}
    response = request(path, **kwargs)

    assert response.status_code == 200
    assert forwarded == [(method.upper(), path)]
    body = response.json()
    assert body["ok"] is True
    assert response.headers["x-aicrm-compatibility-facade"] == "legacy_flask_facade"
