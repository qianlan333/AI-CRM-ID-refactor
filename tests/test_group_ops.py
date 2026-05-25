from __future__ import annotations

import pytest


@pytest.fixture()
def group_ops_runtime(monkeypatch):
    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "0")
    from aicrm_next.automation_engine.group_ops.repo import InMemoryGroupOpsRepository

    return InMemoryGroupOpsRepository()


def test_group_ops_fastapi_routes_list_plans_without_next_action(group_ops_runtime, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from aicrm_next.automation_engine.group_ops import api as group_ops_api
    from aicrm_next.automation_engine.group_ops.application import ListGroupOpsPlansQuery
    from aicrm_next.main import create_app

    repo = group_ops_runtime

    class BoundListGroupOpsPlansQuery:
        def __call__(self, request):
            return ListGroupOpsPlansQuery(repo)(request)

    monkeypatch.setattr(group_ops_api, "ListGroupOpsPlansQuery", BoundListGroupOpsPlansQuery)
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.get("/api/admin/automation-conversion/group-ops/plans")
    assert response.status_code == 200
    assert response.headers.get("X-AICRM-Route-Owner") == "ai_crm_next"
    body = response.json()
    assert body["ok"] is True
    assert body["items"]
    assert "next_action" not in body["items"][0]
    assert body["items"][0]["bound_group_count"] == 2
    assert body["items"][0]["today_estimated_reach"] == 332


def test_group_ops_rejects_binding_group_owned_by_other_operator(group_ops_runtime):
    from aicrm_next.automation_engine.group_ops.application import AddGroupOpsPlanGroupCommand
    from aicrm_next.automation_engine.group_ops.dto import GroupOpsBindGroupRequest
    from aicrm_next.shared.errors import ContractError

    with pytest.raises(ContractError, match="owner_userid"):
        AddGroupOpsPlanGroupCommand(group_ops_runtime)(
            1,
            GroupOpsBindGroupRequest(chat_id="wrOgBBB001", operator="pytest"),
        )


def test_group_ops_node_validation_reuses_private_message_builder(group_ops_runtime):
    from aicrm_next.automation_engine.group_ops.application import CreateGroupOpsNodeCommand
    from aicrm_next.automation_engine.group_ops.dto import GroupOpsNodeRequest
    from aicrm_next.shared.errors import ContractError

    result = CreateGroupOpsNodeCommand(group_ops_runtime)(
        1,
        GroupOpsNodeRequest(
            day_index=1,
            trigger_time_label="20:00",
            action_title="课程入口",
            text_content="今晚课程已更新",
            attachments=[
                {
                    "msgtype": "miniprogram",
                    "miniprogram": {
                        "appid": "wx123",
                        "page": "/pages/course/today",
                        "title": "课程入口",
                        "pic_media_id": "MEDIA_ID",
                    },
                }
            ],
        ),
    )
    assert result["status_code"] == 201
    assert result["item"]["attachments"][0]["miniprogram"]["appid"] == "wx123"

    with pytest.raises(ContractError, match="pic_media_id"):
        CreateGroupOpsNodeCommand(group_ops_runtime)(
            1,
            GroupOpsNodeRequest(
                day_index=1,
                trigger_time_label="20:00",
                action_title="坏的小程序",
                text_content="",
                attachments=[{"msgtype": "miniprogram", "miniprogram": {"appid": "wx123", "page": "/p", "title": "t"}}],
            ),
        )


def test_group_ops_webhook_auth_idempotency_and_queue_payload(group_ops_runtime):
    from aicrm_next.automation_engine.group_ops.application import ReceiveGroupOpsWebhookCommand
    from aicrm_next.automation_engine.group_ops.dto import GroupOpsWebhookReceiveRequest

    captured: dict = {}

    class FakeQueueGateway:
        def enqueue_group_message(self, **kwargs):
            captured.update(kwargs)
            return 901

    payload = GroupOpsWebhookReceiveRequest(
        idempotency_key="daily-lesson-2026-05-25",
        send_mode="queued",
        scheduled_at="2026-05-25T20:00:00+08:00",
        content={"text": "今天的日课已经更新。", "attachments": []},
    )
    command = ReceiveGroupOpsWebhookCommand(group_ops_runtime, FakeQueueGateway())
    result = command("daily-lesson-8f3a", payload, authorization="Bearer fixture-webhook-token")

    assert result["status_code"] == 202
    assert result["status"] == "queued"
    assert result["broadcast_job_ids"] == [901]
    assert captured["owner_userid"] == "owner_001"
    assert captured["chat_ids"] == ["wrOgAAA001"]
    assert captured["content_payload"]["sender"] == "owner_001"
    assert captured["content_payload"]["text"]["content"] == "今天的日课已经更新。"

    duplicate = command("daily-lesson-8f3a", payload, authorization="Bearer fixture-webhook-token")
    assert duplicate["status"] == "duplicate"
    assert duplicate["broadcast_job_ids"] == [901]


def test_group_ops_webhook_rejects_bad_token(group_ops_runtime):
    from aicrm_next.automation_engine.group_ops.application import ReceiveGroupOpsWebhookCommand, UnauthorizedError
    from aicrm_next.automation_engine.group_ops.dto import GroupOpsWebhookReceiveRequest

    with pytest.raises(UnauthorizedError):
        ReceiveGroupOpsWebhookCommand(group_ops_runtime, None)(
            "daily-lesson-8f3a",
            GroupOpsWebhookReceiveRequest(
                idempotency_key="bad-token",
                content={"text": "hello"},
            ),
            authorization="Bearer wrong",
        )


def test_broadcast_worker_routes_group_ops_channel(monkeypatch):
    from wecom_ability_service.domains.broadcast_jobs.handlers import execute_job

    captured: dict = {}

    def fake_dispatch(task_type, payload, **kwargs):
        captured["task_type"] = task_type
        captured["payload"] = payload
        captured["broadcast_job_id"] = kwargs.get("broadcast_job_id")
        return {"task_id": 778}

    monkeypatch.setattr(
        "wecom_ability_service.domains.tasks.service.dispatch_wecom_group_task_with_intent",
        fake_dispatch,
    )

    result = execute_job(
        {
            "id": 66,
            "source_type": "workflow",
            "target_count": 0,
            "content_payload": {
                "channel": "wecom_customer_group",
                "sender": "owner_001",
                "chat_ids": ["wrOgAAA001", "wrOgAAA002"],
                "text": {"content": "hello"},
            },
        }
    )

    assert result["ok"] is True
    assert result["sent_count"] == 2
    assert result["outbound_task_id"] == 778
    assert captured["task_type"] == "broadcast_job/group_ops"
    assert captured["broadcast_job_id"] == 66
