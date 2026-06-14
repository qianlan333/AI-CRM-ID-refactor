from __future__ import annotations

from urllib.parse import urlparse

from aicrm_next.platform_foundation.external_effects import (
    GROUP_OPS_MESSAGE_LOOPBACK,
    GROUP_OPS_WEBHOOK_ACTION_LOOPBACK,
    WECOM_MESSAGE_GROUP_SEND,
    ExternalEffectService,
)
from aicrm_next.platform_foundation.external_effects.adapters import DEFAULT_ADAPTER_REGISTRY, WebhookAdapter
from aicrm_next.platform_foundation.external_effects.worker import ExternalEffectWorker
from tests.group_ops_test_helpers import group_ops_api_client


class RecordingQueueGateway:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def enqueue_group_message(self, **kwargs):
        self.calls.append(kwargs)
        return 2300 + len(self.calls)


def _install_recording_gateway(monkeypatch) -> RecordingQueueGateway:
    from aicrm_next.integration_gateway import wecom_group_adapter

    gateway = RecordingQueueGateway()
    monkeypatch.setattr(wecom_group_adapter, "build_group_ops_queue_gateway", lambda: gateway)
    return gateway


def _install_loopback_http_adapter(monkeypatch, client) -> list[dict]:
    calls: list[dict] = []

    def loopback_post(url, *, json, headers, timeout):
        calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        parsed = urlparse(url)
        return client.post(parsed.path, json=json, headers=headers)

    monkeypatch.setitem(DEFAULT_ADAPTER_REGISTRY._adapters, "outbound_webhook", WebhookAdapter(http_post=loopback_post))  # type: ignore[attr-defined]
    monkeypatch.setitem(DEFAULT_ADAPTER_REGISTRY._adapters, "webhook", WebhookAdapter(http_post=loopback_post))  # type: ignore[attr-defined]
    return calls


def _jobs(effect_type: str):
    return ExternalEffectService().list_jobs({"effect_type": effect_type}, limit=20)[0]


def _install_fake_wecom_group_message_adapter(monkeypatch) -> list[dict]:
    calls: list[dict] = []

    class FakeWeComGroupMessageAdapter:
        def create_group_message_task(self, payload, *, idempotency_key=""):
            calls.append({"payload": payload, "idempotency_key": idempotency_key})
            return {
                "ok": True,
                "adapter": "FakeWeComGroupMessageAdapter",
                "mode": "production",
                "operation": "create_group_message_task",
                "audit_id": "audit_fake_group_send",
                "side_effect_executed": True,
                "exact_target_required": True,
                "exact_target_verified": True,
                "requested_chat_ids": list(payload.get("chat_ids") or []),
                "requested_chat_count": len(list(payload.get("chat_ids") or [])),
                "wecom_msgid": "fake_wecom_group_msgid",
                "error_code": "",
                "error_message": "",
            }

    from aicrm_next.integration_gateway import wecom_group_adapter

    monkeypatch.setattr(wecom_group_adapter, "build_wecom_group_message_adapter", lambda: FakeWeComGroupMessageAdapter())
    return calls


def test_group_ops_run_due_preview_does_not_create_external_effect_job(group_ops_api_client, monkeypatch):
    monkeypatch.setenv("AICRM_GROUP_OPS_OUTBOUND_MODE", "shadow")
    gateway = _install_recording_gateway(monkeypatch)

    response = group_ops_api_client.post(
        "/api/admin/automation-conversion/group-ops/plans/1/run-due/preview",
        json={"operator": "pytest", "max_outbound_tasks": 1},
    )
    jobs = _jobs(GROUP_OPS_MESSAGE_LOOPBACK)

    assert response.status_code == 200
    assert response.json()["status"] == "preview"
    assert gateway.calls == []
    assert jobs == []


def test_group_ops_run_due_shadow_keeps_legacy_queue_and_creates_shadow_job(group_ops_api_client, monkeypatch):
    monkeypatch.setenv("AICRM_GROUP_OPS_OUTBOUND_MODE", "shadow")
    gateway = _install_recording_gateway(monkeypatch)

    response = group_ops_api_client.post(
        "/api/admin/automation-conversion/group-ops/plans/1/run-due",
        json={"operator": "pytest", "allow_node_ids": [1], "max_outbound_tasks": 1},
    )
    jobs = _jobs(GROUP_OPS_MESSAGE_LOOPBACK)

    assert response.status_code == 202
    body = response.json()
    assert body["outbound_mode"] == "shadow"
    assert body["broadcast_job_ids"] == [2301]
    assert body["legacy_broadcast_job_ids"] == [2301]
    assert body["external_effect_job_ids"] == [jobs[0].id]
    assert body["real_external_call_executed"] is False
    assert body["wecom_send_executed"] is False
    assert len(gateway.calls) == 1
    assert jobs[0].status == "planned"
    assert jobs[0].execution_mode == "shadow"
    assert jobs[0].payload_summary_json["chat_count"] == 2


def test_group_ops_run_due_external_effect_skips_legacy_queue_and_creates_queued_job(group_ops_api_client, monkeypatch):
    monkeypatch.setenv("AICRM_GROUP_OPS_OUTBOUND_MODE", "external_effect")
    gateway = _install_recording_gateway(monkeypatch)

    response = group_ops_api_client.post(
        "/api/admin/automation-conversion/group-ops/plans/1/run-due",
        json={"operator": "pytest", "allow_node_ids": [1], "max_outbound_tasks": 1},
    )
    jobs = _jobs(GROUP_OPS_MESSAGE_LOOPBACK)

    assert response.status_code == 202
    body = response.json()
    assert body["outbound_mode"] == "external_effect"
    assert body["broadcast_job_ids"] == []
    assert body["legacy_broadcast_job_ids"] == []
    assert body["external_effect_job_ids"] == [jobs[0].id]
    assert gateway.calls == []
    assert jobs[0].status == "queued"
    assert jobs[0].execution_mode == "execute"


def test_group_ops_webhook_receive_shadow_logs_action_and_creates_external_effect_job(group_ops_api_client, monkeypatch):
    monkeypatch.setenv("AICRM_GROUP_OPS_OUTBOUND_MODE", "shadow")
    calls: list[dict] = []

    class FakeActionPort:
        def dispatch(self, input_data):
            calls.append(input_data)
            return {"ok": True, "status": "queued", "action_ref_id": "job_123", "side_effect_executed": False}

    monkeypatch.setattr(
        "aicrm_next.automation_engine.group_ops.action_port.build_group_ops_action_port",
        lambda: FakeActionPort(),
    )
    created = group_ops_api_client.post(
        "/api/automation/group-ops/plans",
        json={
            "name": "Webhook external effect plan",
            "type": "webhook_receiver",
            "status": "disabled",
            "operatorMemberId": "HuangYouCan",
            "defaultActionType": "send_group_message",
            "allowNoSop": True,
        },
    ).json()
    group_ops_api_client.post(f"/api/automation/group-ops/plans/{created['id']}/enable")

    response = group_ops_api_client.post(
        f"/api/automation/group-ops/webhooks/{created['webhook']['endpointKey']}",
        headers={"Authorization": f"Bearer {created['webhook']['token']}", "X-Idempotency-Key": "pytest-group-action-effect"},
        json={
            "event": "synthetic_group_event",
            "source": "pytest",
            "recipients": [{"group_id": "test_chat_group_ops_001", "external_user_id": "test_external_userid_group_ops_001"}],
            "action": {"action_type": "send_group_message", "content": "synthetic group content"},
        },
    )
    jobs = _jobs(GROUP_OPS_WEBHOOK_ACTION_LOOPBACK)
    logs = group_ops_api_client.get(f"/api/automation/group-ops/plans/{created['id']}/executions")

    assert response.status_code == 202
    assert response.json()["external_effect_job_ids"] == [jobs[0].id]
    assert response.json()["real_external_call_executed"] is False
    assert response.json()["wecom_send_executed"] is False
    assert calls[0]["action"]["action_type"] == "send_group_message"
    assert logs.json()["total"] == 1
    assert jobs[0].status == "planned"
    assert jobs[0].payload_summary_json["chat_count"] == 1


def test_group_ops_legacy_bundle_shadow_keeps_broadcast_job_and_creates_shadow_job(group_ops_api_client, monkeypatch):
    monkeypatch.setenv("AICRM_GROUP_OPS_OUTBOUND_MODE", "shadow")
    gateway = _install_recording_gateway(monkeypatch)

    response = group_ops_api_client.post(
        "/api/automation/group-ops/webhooks/daily-lesson-8f3a",
        headers={"Authorization": "Bearer fixture-webhook-token"},
        json={
            "idempotency_key": "daily-lesson-external-effect",
            "send_mode": "queued",
            "scheduled_at": "2026-05-25T20:00:00+08:00",
            "content": {"text": "synthetic daily lesson", "attachments": []},
        },
    )
    jobs = _jobs(GROUP_OPS_MESSAGE_LOOPBACK)

    assert response.status_code == 202
    assert response.json()["broadcast_job_ids"] == [2301]
    assert response.json()["legacy_broadcast_job_ids"] == [2301]
    assert response.json()["external_effect_job_ids"] == [jobs[0].id]
    assert len(gateway.calls) == 1
    assert jobs[0].status == "planned"
    assert jobs[0].execution_mode == "shadow"


def test_group_ops_legacy_bundle_external_effect_creates_wecom_group_job_without_legacy_gateway(group_ops_api_client, monkeypatch):
    monkeypatch.setenv("AICRM_GROUP_OPS_OUTBOUND_MODE", "external_effect")
    monkeypatch.setenv("AICRM_GROUP_OPS_EXTERNAL_EFFECT_SEND_MODE", "wecom_group")
    gateway = _install_recording_gateway(monkeypatch)

    response = group_ops_api_client.post(
        "/api/automation/group-ops/webhooks/daily-lesson-8f3a",
        headers={"Authorization": "Bearer fixture-webhook-token"},
        json={
            "idempotency_key": "daily-lesson-wecom-group-effect",
            "send_mode": "queued",
            "scheduled_at": "2026-05-25T20:00:00+08:00",
            "content": {"text": "synthetic real group effect", "attachments": []},
        },
    )
    jobs = _jobs(WECOM_MESSAGE_GROUP_SEND)

    assert response.status_code == 202
    body = response.json()
    assert body["broadcast_job_ids"] == []
    assert body["legacy_broadcast_job_ids"] == []
    assert body["external_effect_job_ids"] == [jobs[0].id]
    assert body["outbound_mode"] == "external_effect"
    assert body["external_effect_send_mode"] == "wecom_group"
    assert body["real_external_call_executed"] is False
    assert body["wecom_send_executed"] is False
    assert gateway.calls == []
    assert jobs[0].effect_type == WECOM_MESSAGE_GROUP_SEND
    assert jobs[0].adapter_name == "wecom_group_message"
    assert jobs[0].operation == "send_group_message"
    assert jobs[0].status == "queued"
    assert jobs[0].execution_mode == "execute"
    assert jobs[0].business_type == "group_ops_plan"
    assert jobs[0].payload_json["webhook_key"] == "daily-lesson-8f3a"
    assert jobs[0].payload_json["owner_userid"] == "owner_001"
    assert jobs[0].payload_json["mention_all"] is False
    assert jobs[0].payload_json["chat_ids"] == ["wrOgAAA001"]


def test_wecom_group_external_effect_adapter_gates_and_success_path(group_ops_api_client, monkeypatch):
    monkeypatch.setenv("AICRM_GROUP_OPS_OUTBOUND_MODE", "external_effect")
    monkeypatch.setenv("AICRM_GROUP_OPS_EXTERNAL_EFFECT_SEND_MODE", "wecom_group")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES", WECOM_MESSAGE_GROUP_SEND)
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_ALLOWED_GROUP_OPS_WEBHOOK_KEYS", "daily-lesson-8f3a")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_ALLOWED_OWNER_USERIDS", "owner_001")
    _install_recording_gateway(monkeypatch)
    wecom_calls = _install_fake_wecom_group_message_adapter(monkeypatch)

    response = group_ops_api_client.post(
        "/api/automation/group-ops/webhooks/daily-lesson-8f3a",
        headers={"Authorization": "Bearer fixture-webhook-token"},
        json={
            "idempotency_key": "daily-lesson-wecom-gated-disabled",
            "send_mode": "queued",
            "content": {"text": "synthetic disabled group effect", "attachments": []},
        },
    )
    disabled_job = ExternalEffectService().get(response.json()["external_effect_job_ids"][0])
    disabled = ExternalEffectWorker().run_due(batch_size=1, dry_run=False, effect_types=[WECOM_MESSAGE_GROUP_SEND], test_only=False)
    disabled_updated = ExternalEffectService().get(disabled_job.id if disabled_job else 0)

    assert disabled["counts"]["blocked_count"] == 1
    assert disabled["real_external_call_executed"] is False
    assert disabled_updated is not None
    assert disabled_updated.status == "blocked"
    assert disabled_updated.last_error_code == "execution_disabled"
    assert wecom_calls == []

    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_WECOM_EXECUTE", "1")
    response = group_ops_api_client.post(
        "/api/automation/group-ops/webhooks/daily-lesson-8f3a",
        headers={"Authorization": "Bearer fixture-webhook-token"},
        json={
            "idempotency_key": "daily-lesson-wecom-gated-success",
            "send_mode": "queued",
            "content": {"text": "synthetic successful group effect", "attachments": []},
        },
    )
    job = ExternalEffectService().get(response.json()["external_effect_job_ids"][0])
    preview = ExternalEffectWorker().run_due(batch_size=1, dry_run=True, effect_types=[WECOM_MESSAGE_GROUP_SEND], test_only=False)
    dry_run = ExternalEffectWorker().run_due(batch_size=1, dry_run=True, effect_types=[WECOM_MESSAGE_GROUP_SEND], test_only=False)
    executed = ExternalEffectWorker().run_due(batch_size=1, dry_run=False, effect_types=[WECOM_MESSAGE_GROUP_SEND], test_only=False)
    updated = ExternalEffectService().get(job.id if job else 0)

    assert preview["real_external_call_executed"] is False
    assert dry_run["real_external_call_executed"] is False
    assert executed["counts"]["succeeded_count"] == 1
    assert executed["real_external_call_executed"] is True
    assert updated is not None
    assert updated.status == "succeeded"
    assert len(wecom_calls) == 1
    assert wecom_calls[0]["payload"]["sender"] == "owner_001"
    assert wecom_calls[0]["payload"]["chat_ids"] == ["wrOgAAA001"]
    assert executed["items"][0]["attempt"]["response_summary_json"]["wecom_send_executed"] is True


def test_wecom_group_external_effect_requires_batch_size_one(group_ops_api_client, monkeypatch):
    monkeypatch.setenv("AICRM_GROUP_OPS_OUTBOUND_MODE", "external_effect")
    monkeypatch.setenv("AICRM_GROUP_OPS_EXTERNAL_EFFECT_SEND_MODE", "wecom_group")

    group_ops_api_client.post(
        "/api/automation/group-ops/webhooks/daily-lesson-8f3a",
        headers={"Authorization": "Bearer fixture-webhook-token"},
        json={
            "idempotency_key": "daily-lesson-wecom-batch-size",
            "send_mode": "queued",
            "content": {"text": "synthetic batch blocked group effect", "attachments": []},
        },
    )
    result = ExternalEffectWorker().run_due(batch_size=2, dry_run=False, effect_types=[WECOM_MESSAGE_GROUP_SEND], test_only=False)

    assert result["ok"] is False
    assert result["error"] == "batch_size_one_required"
    assert result["real_external_call_executed"] is False


def test_wecom_group_external_effect_blocks_allowlist_and_mention_all(group_ops_api_client, monkeypatch):
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_WECOM_EXECUTE", "1")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES", WECOM_MESSAGE_GROUP_SEND)
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_ALLOWED_GROUP_OPS_WEBHOOK_KEYS", "other-webhook")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_ALLOWED_OWNER_USERIDS", "owner_001")
    service = ExternalEffectService()
    job = service.plan_effect(
        effect_type=WECOM_MESSAGE_GROUP_SEND,
        adapter_name="wecom_group_message",
        operation="send_group_message",
        target_type="group_ops_webhook_event",
        target_id="event_1",
        business_type="group_ops_plan",
        business_id="2",
        payload={
            "webhook_key": "daily-lesson-8f3a",
            "owner_userid": "owner_001",
            "chat_ids": ["wrOgAAA001"],
            "content_payload": {"text": {"content": "blocked content"}, "attachments": []},
            "mention_all": False,
        },
        payload_summary={"chat_count": 1},
        execution_mode="execute",
        status="queued",
        idempotency_key="group-ops-wecom-not-allowed",
    )
    blocked = ExternalEffectWorker().run_due(batch_size=1, dry_run=False, effect_types=[WECOM_MESSAGE_GROUP_SEND], test_only=False)
    blocked_job = ExternalEffectService().get(job["id"])

    assert blocked["counts"]["blocked_count"] == 1
    assert blocked["real_external_call_executed"] is False
    assert blocked_job is not None
    assert blocked_job.last_error_code == "group_ops_webhook_key_not_allowed"

    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_ALLOWED_GROUP_OPS_WEBHOOK_KEYS", "daily-lesson-8f3a")
    service.plan_effect(
        effect_type=WECOM_MESSAGE_GROUP_SEND,
        adapter_name="wecom_group_message",
        operation="send_group_message",
        target_type="group_ops_webhook_event",
        target_id="event_2",
        business_type="group_ops_plan",
        business_id="2",
        payload={
            "webhook_key": "daily-lesson-8f3a",
            "owner_userid": "owner_001",
            "chat_ids": ["wrOgAAA001"],
            "content_payload": {"text": {"content": "blocked mention all"}, "attachments": []},
            "mention_all": True,
        },
        payload_summary={"chat_count": 1},
        execution_mode="execute",
        status="queued",
        idempotency_key="group-ops-wecom-mention-all",
    )
    mention_blocked = ExternalEffectWorker().run_due(batch_size=1, dry_run=False, effect_types=[WECOM_MESSAGE_GROUP_SEND], test_only=False)
    assert mention_blocked["counts"]["blocked_count"] == 1
    assert mention_blocked["items"][0]["attempt"]["error_code"] == "mention_all_blocked"


def test_group_ops_loopback_2xx_succeeds_with_receipt(group_ops_api_client, monkeypatch):
    monkeypatch.setenv("AICRM_GROUP_OPS_OUTBOUND_MODE", "external_effect")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_TEST_RECEIVER_ENABLED", "1")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_TEST_EXECUTION_ONLY", "1")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_WEBHOOK_EXECUTE", "1")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES", GROUP_OPS_MESSAGE_LOOPBACK)
    calls = _install_loopback_http_adapter(monkeypatch, group_ops_api_client)
    gateway = _install_recording_gateway(monkeypatch)

    response = group_ops_api_client.post(
        "/api/admin/automation-conversion/group-ops/plans/1/run-due",
        headers={"X-Forwarded-Proto": "https", "X-Forwarded-Host": "crm.example.test"},
        json={
            "operator": "pytest",
            "allow_node_ids": [1],
            "max_outbound_tasks": 1,
            "external_effect_test_loopback": True,
            "test_receiver_response_status": 200,
        },
    )
    job = ExternalEffectService().get(response.json()["external_effect_job_ids"][0])
    preview = ExternalEffectWorker().run_due(batch_size=1, dry_run=True, effect_types=[GROUP_OPS_MESSAGE_LOOPBACK], test_only=True)
    dry_run = ExternalEffectWorker().run_due(batch_size=1, dry_run=True, effect_types=[GROUP_OPS_MESSAGE_LOOPBACK], test_only=True)
    executed = ExternalEffectWorker().run_due(batch_size=1, dry_run=False, effect_types=[GROUP_OPS_MESSAGE_LOOPBACK], test_only=True)
    updated = ExternalEffectService().get(job.id if job else 0)
    receipts, total = ExternalEffectService().list_test_receipts({"job_id": job.id if job else 0}, limit=10)

    assert response.status_code == 202
    assert gateway.calls == []
    assert job is not None
    assert job.payload_json["webhook_url"].startswith("https://crm.example.test/api/external-effects/test-receiver/")
    assert preview["real_external_call_executed"] is False
    assert dry_run["real_external_call_executed"] is False
    assert executed["real_external_call_executed"] is True
    assert executed["counts"]["succeeded_count"] == 1
    assert updated is not None
    assert updated.status == "succeeded"
    assert len(calls) == 1
    assert total == 1
    assert receipts[0].payload_hash == job.payload_json["expected_payload_hash"]
    assert receipts[0].signature_valid is True


def test_group_ops_loopback_500_retryable_allowlist_miss_and_test_only_gate(group_ops_api_client, monkeypatch):
    monkeypatch.setenv("AICRM_GROUP_OPS_OUTBOUND_MODE", "external_effect")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_TEST_RECEIVER_ENABLED", "1")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_TEST_EXECUTION_ONLY", "1")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_WEBHOOK_EXECUTE", "1")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES", GROUP_OPS_MESSAGE_LOOPBACK)
    calls = _install_loopback_http_adapter(monkeypatch, group_ops_api_client)
    _install_recording_gateway(monkeypatch)

    retry_response = group_ops_api_client.post(
        "/api/admin/automation-conversion/group-ops/plans/1/run-due",
        headers={"X-Forwarded-Proto": "https", "X-Forwarded-Host": "crm.example.test"},
        json={
            "operator": "pytest",
            "allow_node_ids": [1],
            "max_outbound_tasks": 1,
            "external_effect_test_loopback": True,
            "test_receiver_response_status": 500,
        },
    )
    retry_job = ExternalEffectService().get(retry_response.json()["external_effect_job_ids"][0])
    retry_result = ExternalEffectWorker().run_due(batch_size=1, dry_run=False, effect_types=[GROUP_OPS_MESSAGE_LOOPBACK], test_only=True)
    retry_updated = ExternalEffectService().get(retry_job.id if retry_job else 0)

    assert retry_result["counts"]["failed_count"] == 1
    assert retry_updated is not None
    assert retry_updated.status == "failed_retryable"
    assert retry_updated.next_retry_at
    assert len(calls) == 1

    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES", "")
    blocked_response = group_ops_api_client.post(
        "/api/admin/automation-conversion/group-ops/plans/1/run-due",
        headers={"X-Forwarded-Proto": "https", "X-Forwarded-Host": "crm.example.test"},
        json={
            "operator": "pytest",
            "allow_node_ids": [1],
            "max_outbound_tasks": 1,
            "external_effect_test_loopback": True,
            "test_receiver_response_status": 200,
            "scheduled_at": "allowlist-miss",
        },
    )
    blocked_job = ExternalEffectService().get(blocked_response.json()["external_effect_job_ids"][0])
    blocked = ExternalEffectWorker().run_due(batch_size=1, dry_run=False, effect_types=[GROUP_OPS_MESSAGE_LOOPBACK], test_only=True)
    blocked_updated = ExternalEffectService().get(blocked_job.id if blocked_job else 0)

    assert blocked["counts"]["blocked_count"] == 1
    assert blocked["real_external_call_executed"] is False
    assert blocked_updated is not None
    assert blocked_updated.status == "blocked"
    assert blocked_updated.last_error_code == "effect_type_not_allowed"
    assert len(calls) == 1

    rejected = ExternalEffectWorker().run_due(batch_size=1, dry_run=False, effect_types=[GROUP_OPS_MESSAGE_LOOPBACK], test_only=False)
    assert rejected["ok"] is False
    assert rejected["error"] == "test_only_required"
