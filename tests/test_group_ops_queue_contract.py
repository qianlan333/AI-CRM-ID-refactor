from __future__ import annotations


class DummyApp:
    def app_context(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_queue_gateway_uses_broadcast_jobs_with_empty_targets_allowed():
    from aicrm_next.integration_gateway.wecom_group_adapter import LegacyBroadcastJobQueueGateway

    captured: dict = {}

    def fake_enqueue_job(**kwargs):
        captured.update(kwargs)
        return 321

    gateway = LegacyBroadcastJobQueueGateway(
        legacy_app_factory=lambda: DummyApp(),
        enqueue_job_fn=fake_enqueue_job,
    )
    job_id = gateway.enqueue_group_message(
        plan_id=2,
        source_id="2:webhook:5",
        scheduled_at="2026-05-25T20:00:00+08:00",
        owner_userid="owner_001",
        chat_ids=["wrOgAAA001", "wrOgAAA002"],
        content_payload={"text": {"content": "hello"}},
        content_summary="hello",
        created_by="pytest",
    )

    assert job_id == 321
    assert captured["source_type"] == "workflow"
    assert captured["source_table"] == "automation_group_ops_plans"
    assert captured["source_id"] == "2:webhook:5"
    assert captured["business_domain"] == "group_ops"
    assert captured["channel"] == "wecom_customer_group"
    assert captured["target_kind"] == "chat_id"
    assert captured["target_external_userids"] == []
    assert captured["allow_empty_targets"] is True
    assert captured["content_type"] == "wecom_customer_group"
    assert captured["content_payload"]["channel"] == "wecom_customer_group"
    assert captured["content_payload"]["chat_ids"] == ["wrOgAAA001", "wrOgAAA002"]
    assert captured["content_payload"]["sender"] == "owner_001"


def test_wecom_group_adapter_default_disabled_does_not_call_wecom(monkeypatch):
    from aicrm_next.integration_gateway.wecom_group_adapter import WeComGroupMessageAdapter

    def fail_if_called():
        raise AssertionError("real WeCom client must not be constructed")

    monkeypatch.setattr(
        "wecom_ability_service.wecom_client.WeComClient.from_app",
        fail_if_called,
    )
    result = WeComGroupMessageAdapter(mode="disabled").create_group_message_task(
        {"sender": "owner_001", "chat_ids": ["wrOgAAA001"], "text": {"content": "hello"}},
        idempotency_key="pytest-disabled",
    )

    assert result["ok"] is False
    assert result["side_effect_executed"] is False
    assert result["error_code"] == "wecom_group_message_disabled"


def test_wecom_group_adapter_staging_blocks_real_send(monkeypatch):
    from aicrm_next.integration_gateway.wecom_group_adapter import WeComGroupMessageAdapter

    monkeypatch.setenv("AICRM_ENABLE_REAL_WECOM_GROUP_MESSAGE", "true")
    result = WeComGroupMessageAdapter(mode="staging").create_group_message_task(
        {"sender": "owner_001", "chat_ids": ["wrOgAAA001"], "text": {"content": "hello"}},
        idempotency_key="pytest-staging",
    )

    assert result["ok"] is False
    assert result["side_effect_executed"] is False
    assert result["error_code"] == "wecom_group_message_disabled"


def test_wecom_group_adapter_production_without_guard_is_blocked(monkeypatch):
    from aicrm_next.integration_gateway.wecom_group_adapter import WeComGroupMessageAdapter

    monkeypatch.delenv("AICRM_ENABLE_REAL_WECOM_GROUP_MESSAGE", raising=False)

    result = WeComGroupMessageAdapter(mode="production").create_group_message_task(
        {"sender": "owner_001", "chat_ids": ["wrOgAAA001"], "text": {"content": "hello"}},
        idempotency_key="pytest-production-guard",
    )

    assert result["ok"] is False
    assert result["side_effect_executed"] is False
    assert result["error_code"] == "production_guard_failed"


def test_group_sync_adapter_fake_filters_owner_without_real_wecom(monkeypatch):
    from aicrm_next.integration_gateway.wecom_group_adapter import WeComGroupChatSyncAdapter

    def fail_if_called():
        raise AssertionError("real WeCom client must not be constructed")

    monkeypatch.setattr("wecom_ability_service.wecom_client.WeComClient.from_app", fail_if_called)
    result = WeComGroupChatSyncAdapter(mode="fake").list_group_chats(owner_userid="owner_001", limit=10)

    assert result["ok"] is True
    assert result["side_effect_executed"] is False
    assert {item["owner_userid"] for item in result["groups"]} == {"owner_001"}

    detail = WeComGroupChatSyncAdapter(mode="fake").get_group_chat("wrOgAAA001", owner_userid="owner_001")
    assert detail["ok"] is True
    assert detail["side_effect_executed"] is False
    assert detail["group"]["chat_id"] == "wrOgAAA001"


def test_group_sync_adapter_production_without_guard_is_blocked(monkeypatch):
    from aicrm_next.integration_gateway.wecom_group_adapter import WeComGroupChatSyncAdapter

    monkeypatch.delenv("AICRM_ENABLE_REAL_WECOM_GROUP_SYNC", raising=False)
    result = WeComGroupChatSyncAdapter(mode="production").list_group_chats(owner_userid="owner_001", limit=10)

    assert result["ok"] is False
    assert result["side_effect_executed"] is False
    assert result["error_code"] == "production_guard_failed"


def test_group_sync_adapter_production_uses_legacy_app_context(monkeypatch):
    from aicrm_next.integration_gateway.wecom_group_adapter import WeComGroupChatSyncAdapter

    context = {"active": False, "list_called": False, "detail_called": False}

    class ContextApp(DummyApp):
        def __enter__(self):
            context["active"] = True
            return self

        def __exit__(self, exc_type, exc, tb):
            context["active"] = False
            return False

    class FakeClient:
        def list_group_chats(self, payload):
            assert context["active"] is True
            context["list_called"] = True
            assert payload["owner_filter"] == {"userid_list": ["owner_live"]}
            return {"group_chat_list": [{"chat_id": "live_chat_001"}], "next_cursor": ""}

        def get_group_chat(self, chat_id, need_name=1):
            assert context["active"] is True
            context["detail_called"] = True
            assert chat_id == "live_chat_001"
            assert need_name == 1
            return {
                "group_chat": {
                    "chat_id": "live_chat_001",
                    "name": "真实客户群",
                    "owner": "owner_live",
                    "member_list": [{"userid": "owner_live", "type": 1}, {"external_userid": "wm_live", "type": 2}],
                }
            }

    monkeypatch.setenv("AICRM_ENABLE_REAL_WECOM_GROUP_SYNC", "true")
    monkeypatch.setattr("aicrm_next.integration_gateway.legacy_flask_facade._legacy_app", lambda: ContextApp())
    monkeypatch.setattr("aicrm_next.integration_gateway.legacy_flask_facade.legacy_wecom_client_from_app", lambda: FakeClient())

    result = WeComGroupChatSyncAdapter(mode="production").list_group_chats(owner_userid="owner_live", limit=10)

    assert result["ok"] is True
    assert result["side_effect_executed"] is True
    assert context["list_called"] is True
    assert context["detail_called"] is True
    assert result["groups"] == [
        {
            "chat_id": "live_chat_001",
            "group_name": "真实客户群",
            "owner_userid": "owner_live",
            "owner_name": "owner_live",
            "internal_member_count": 1,
            "external_member_count": 1,
            "status": "active",
        }
    ]


def test_group_ops_queue_stats_counts_only_group_ops_jobs():
    from aicrm_next.integration_gateway.wecom_group_adapter import LegacyGroupOpsQueueStatsGateway

    gateway = LegacyGroupOpsQueueStatsGateway(
        legacy_app_factory=lambda: DummyApp(),
        list_jobs_fn=lambda: [
            {"id": 1, "source_table": "automation_group_ops_plans", "content_payload": {"channel": "wecom_customer_group"}},
            {"id": 2, "source_table": "other", "content_payload": {"channel": "text"}},
        ],
    )

    assert gateway.count_group_ops_queue() == 1


def test_broadcast_handler_reuses_existing_outbound_intent_without_dispatch(monkeypatch):
    from wecom_ability_service.domains.broadcast_jobs.handlers import execute_job

    def fail_dispatch(*args, **kwargs):
        raise AssertionError("existing outbound intent must not dispatch again")

    monkeypatch.setattr(
        "wecom_ability_service.domains.tasks.service.dispatch_wecom_group_task_with_intent",
        fail_dispatch,
    )
    result = execute_job(
        {
            "id": 66,
            "source_type": "workflow",
            "outbound_task_id": 778,
            "content_payload": {
                "channel": "wecom_customer_group",
                "sender": "owner_001",
                "chat_ids": ["wrOgAAA001", "wrOgAAA002"],
                "text": {"content": "hello"},
            },
        }
    )

    assert result["ok"] is True
    assert result["outbound_task_id"] == 778
    assert result["sent_count"] == 2


def test_broadcast_handler_dispatches_group_channel_once(monkeypatch):
    from wecom_ability_service.domains.broadcast_jobs.handlers import execute_job

    calls: list[dict] = []

    def fake_dispatch(task_type, payload, **kwargs):
        calls.append({"task_type": task_type, "payload": payload, **kwargs})
        return {"task_id": 779}

    monkeypatch.setattr(
        "wecom_ability_service.domains.tasks.service.dispatch_wecom_group_task_with_intent",
        fake_dispatch,
    )
    result = execute_job(
        {
            "id": 67,
            "source_type": "workflow",
            "content_payload": {
                "channel": "wecom_customer_group",
                "sender": "owner_001",
                "chat_ids": ["wrOgAAA001"],
                "text": {"content": "hello"},
            },
        }
    )

    assert result["ok"] is True
    assert result["outbound_task_id"] == 779
    assert len(calls) == 1
    assert calls[0]["task_type"] == "broadcast_job/group_ops"
    assert calls[0]["broadcast_job_id"] == 67


def test_group_ops_worker_fake_mode_marks_sent_without_side_effect(app, monkeypatch):
    import json
    import sys
    from datetime import datetime, timedelta, timezone
    from pathlib import Path

    from wecom_ability_service.db import get_db
    from wecom_ability_service.domains.broadcast_jobs import service as queue_service

    scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    import run_broadcast_queue_worker as worker  # type: ignore[import-not-found]

    monkeypatch.setenv("AICRM_WECOM_GROUP_ADAPTER_MODE", "fake")
    monkeypatch.delenv("AICRM_ENABLE_REAL_WECOM_GROUP_MESSAGE", raising=False)

    with app.app_context():
        job_id = queue_service.enqueue_job(
            source_type="workflow",
            source_id="1:node:10:due:20260528T0200Z:groups:test",
            source_table="automation_group_ops_plans",
            scheduled_for=datetime.now(timezone.utc) - timedelta(minutes=1),
            target_external_userids=[],
            target_summary="1 customer groups",
            content_type="wecom_customer_group",
            content_payload={
                "channel": "wecom_customer_group",
                "sender": "owner_001",
                "chat_ids": ["wrOgAAA001"],
                "text": {"content": "hello"},
            },
            content_summary="hello",
            allow_empty_targets=True,
        )

        summary = worker.run(batch_size=1)
        job = queue_service.get_job(job_id)
        outbound = get_db().execute(
            "SELECT response_payload FROM outbound_tasks WHERE id = ?",
            (int(job["outbound_task_id"]),),
        ).fetchone()
        payload = outbound["response_payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)

    assert summary["sent_ok"] == 1
    assert job["status"] == "sent"
    assert payload["mode"] == "fake"
    assert payload["side_effect_executed"] is False
