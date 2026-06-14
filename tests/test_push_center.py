from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.platform_foundation.command_bus import CommandContext
from aicrm_next.platform_foundation.external_effects import (
    AI_ASSIST_CAMPAIGN_MESSAGE_LOOPBACK,
    WECOM_MESSAGE_GROUP_SEND,
    WECOM_MESSAGE_PRIVATE_SEND,
    WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH,
    ExternalEffectService,
    reset_external_effect_fixture_state,
)
from aicrm_next.platform_foundation.external_effects.repo import build_external_effect_repository
from aicrm_next.platform_foundation.push_center.section_mapper import effect_types_for_section, label_for_section, section_for_job
from tests.group_ops_test_helpers import group_ops_api_client


class _RecordingQueueGateway:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def enqueue_group_message(self, **kwargs):
        self.calls.append(kwargs)
        return 9001


def _install_recording_group_gateway(monkeypatch) -> _RecordingQueueGateway:
    from aicrm_next.integration_gateway import wecom_group_adapter

    gateway = _RecordingQueueGateway()
    monkeypatch.setattr(wecom_group_adapter, "build_group_ops_queue_gateway", lambda: gateway)
    return gateway


def _context(trace_id: str = "trace-push-center", source_route: str = "/pytest/push-center") -> CommandContext:
    return CommandContext(actor_id="pytest", actor_type="system", request_id=trace_id, trace_id=trace_id, source_route=source_route)


def _plan_job(
    *,
    effect_type: str,
    business_type: str,
    business_id: str,
    target_type: str = "external_user",
    target_id: str = "wm_fixture_a",
    status: str = "queued",
    execution_mode: str = "execute",
    payload: dict | None = None,
    payload_summary: dict | None = None,
    trace_id: str = "trace-push-center",
    idempotency_key: str = "",
) -> dict:
    return ExternalEffectService().plan_effect(
        effect_type=effect_type,
        adapter_name="wecom_private_message" if effect_type == WECOM_MESSAGE_PRIVATE_SEND else "outbound_webhook",
        operation="send" if effect_type == WECOM_MESSAGE_PRIVATE_SEND else "post",
        target_type=target_type,
        target_id=target_id,
        business_type=business_type,
        business_id=business_id,
        payload=payload or {"owner_userid": "HuangYouCan", "external_userids": [target_id], "token": "secret-token"},
        payload_summary=payload_summary or {"owner_userid": "HuangYouCan", "external_userid": target_id, "token": "secret-token"},
        context=_context(trace_id=trace_id),
        source_module="pytest.push_center",
        source_event_id=business_id,
        source_command_id=idempotency_key or business_id,
        risk_level="medium",
        execution_mode=execution_mode,
        status=status,
        idempotency_key=idempotency_key or f"push-center:{effect_type}:{business_id}:{target_id}",
    )


def test_section_mapper_routes_effect_types_by_business_type() -> None:
    reset_external_effect_fixture_state()
    ai_job = _plan_job(effect_type=WECOM_MESSAGE_PRIVATE_SEND, business_type="ai_assist_campaign", business_id="camp_1")
    private_job = _plan_job(effect_type=WECOM_MESSAGE_PRIVATE_SEND, business_type="private_broadcast", business_id="broadcast_1", target_id="wm_fixture_b")
    group_job = _plan_job(
        effect_type=WECOM_MESSAGE_GROUP_SEND,
        business_type="group_ops_plan",
        business_id="12",
        target_type="group_ops_webhook_event",
        target_id="17",
        payload={"owner_userid": "HuangYouCan", "webhook_key": "测试运营计划-ce2519", "chat_ids": ["chat_1"]},
        payload_summary={"owner_userid": "HuangYouCan", "webhook_key": "测试运营计划-ce2519", "chat_count": 1},
    )

    assert section_for_job(ai_job) == "ai_assist"
    assert section_for_job(private_job) == "private_broadcast"
    assert section_for_job(group_job) == "group_ops"
    assert WECOM_MESSAGE_GROUP_SEND in effect_types_for_section("group_ops")
    assert label_for_section("questionnaire") == "问卷外推"


def test_push_center_jobs_filters_and_payload_redaction(next_client: TestClient) -> None:
    reset_external_effect_fixture_state()
    _plan_job(effect_type=WECOM_MESSAGE_PRIVATE_SEND, business_type="ai_assist_campaign", business_id="camp_1", trace_id="trace-ai")
    _plan_job(
        effect_type=WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH,
        business_type="questionnaire",
        business_id="q_1",
        target_type="questionnaire_submission",
        target_id="sub_1",
        trace_id="trace-questionnaire",
        status="planned",
        execution_mode="shadow",
    )

    response = next_client.get("/api/admin/push-center/jobs?section=ai_assist&external_userid=wm_fixture_a")
    body = response.json()

    assert response.status_code == 200
    assert body["ok"] is True
    assert body["total"] == 1
    assert body["items"][0]["section"] == "ai_assist"
    assert body["items"][0]["business_id"] == "camp_1"
    assert body["items"][0]["payload_summary"]["token"] == "[redacted]"
    assert "payload_json" not in body["items"][0]


def test_push_center_detail_includes_attempts_without_full_payload(next_client: TestClient) -> None:
    reset_external_effect_fixture_state()
    job = _plan_job(effect_type=AI_ASSIST_CAMPAIGN_MESSAGE_LOOPBACK, business_type="ai_assist_campaign", business_id="camp_loop", status="blocked", execution_mode="shadow")
    repo = build_external_effect_repository()
    job_obj = repo.get_job(job["id"])
    assert job_obj is not None
    repo.record_attempt(
        job=job_obj,
        status="blocked",
        adapter_mode="shadow",
        request_summary={"Authorization": "Bearer secret", "effect_type": job_obj.effect_type},
        response_summary={"access_token": "secret", "blocked": True},
        error_code="shadow_only",
        error_message="blocked by test",
    )

    response = next_client.get(f"/api/admin/push-center/jobs/{job['id']}")
    body = response.json()

    assert response.status_code == 200
    assert body["job"]["id"] == job["id"]
    assert "payload_json" not in body["job"]
    assert body["attempts"][0]["request_summary"]["Authorization"] == "[redacted]"
    assert body["attempts"][0]["response_summary"]["access_token"] == "[redacted]"


def test_push_center_sections_stats_retry_cancel_auth(next_client: TestClient, monkeypatch) -> None:
    reset_external_effect_fixture_state()
    failed = _plan_job(
        effect_type=WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH,
        business_type="questionnaire",
        business_id="q_failed",
        target_type="questionnaire_submission",
        target_id="sub_failed",
        status="failed_retryable",
        execution_mode="execute",
        trace_id="trace-failed",
    )
    queued = _plan_job(
        effect_type=WECOM_MESSAGE_GROUP_SEND,
        business_type="group_ops_plan",
        business_id="12",
        target_type="group_ops_webhook_event",
        target_id="17",
        status="queued",
        execution_mode="execute",
        trace_id="trace-group",
        payload={"owner_userid": "HuangYouCan", "webhook_key": "测试运营计划-ce2519", "chat_ids": ["chat_1"]},
        payload_summary={"owner_userid": "HuangYouCan", "webhook_key": "测试运营计划-ce2519", "chat_count": 1},
    )
    monkeypatch.setenv("AUTOMATION_INTERNAL_API_TOKEN", "pytest-internal-token")

    sections = next_client.get("/api/admin/push-center/sections").json()
    stats = next_client.get("/api/admin/push-center/stats").json()
    rejected = next_client.post(f"/api/admin/push-center/jobs/{failed['id']}/retry", json={})
    retried = next_client.post(
        f"/api/admin/push-center/jobs/{failed['id']}/retry",
        headers={"Authorization": "Bearer pytest-internal-token"},
        json={},
    )
    cancelled = next_client.post(
        f"/api/admin/push-center/jobs/{queued['id']}/cancel",
        headers={"Authorization": "Bearer pytest-internal-token"},
        json={},
    )

    assert any(item["key"] == "questionnaire" and item["count"] == 1 for item in sections["sections"])
    assert stats["counts"]["failed"] == 1
    assert rejected.status_code == 401
    assert retried.status_code == 200
    assert retried.json()["job"]["status"] == "queued"
    assert cancelled.status_code == 200
    assert cancelled.json()["job"]["status"] == "cancelled"


def test_push_center_page_smoke(next_client: TestClient) -> None:
    reset_external_effect_fixture_state()
    _plan_job(effect_type=WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH, business_type="questionnaire", business_id="q_page", target_type="questionnaire_submission", target_id="sub_page")

    response = next_client.get("/admin/push-center")

    assert response.status_code == 200
    assert "推送中心" in response.text
    assert 'id="statsGrid"' in response.text
    assert 'id="sectionTabs"' in response.text
    assert 'id="filterForm"' in response.text
    assert 'id="pushCenterTable"' in response.text
    assert 'id="detailPanel"' in response.text
    assert 'class="push-center-header"' not in response.text
    assert "push-center-title" not in response.text
    assert 'href="#refresh"' in response.text
    assert 'href="#export"' in response.text
    assert "<colgroup>" in response.text
    assert "push-center-col-section" in response.text
    assert "push-center-section-label" in response.text
    assert "push-center-ellipsis" in response.text
    assert "STATUS_LABELS" in response.text
    assert "EFFECT_TYPE_LABELS" in response.text
    assert "TARGET_TYPE_LABELS" in response.text
    assert "BUSINESS_TYPE_LABELS" in response.text
    assert "/api/admin/push-center/stats" in response.text
    assert "/api/admin/push-center/jobs" in response.text
    assert 'data-action="retry"' in response.text
    assert 'data-action="cancel"' in response.text
    assert "问卷外推" in response.text
    assert "外部动作队列" not in response.text
    assert "payload_json" not in response.text
    assert "token" not in response.text.lower()
    assert "secret" not in response.text.lower()
    assert "Authorization" not in response.text
    assert "access_token" not in response.text
    assert "secret-token" not in response.text


def test_questionnaire_default_external_push_is_queue_first(client: TestClient, monkeypatch) -> None:
    from aicrm_next.questionnaire import external_push
    from aicrm_next.questionnaire.repo import build_questionnaire_repository

    monkeypatch.delenv("AICRM_QUESTIONNAIRE_EXTERNAL_PUSH_MODE", raising=False)
    repo = build_questionnaire_repository()
    questionnaire = repo._questionnaires[0]  # type: ignore[attr-defined]
    questionnaire["external_push_config"] = {"enabled": True, "webhook_url": "https://hooks.example.com/should-not-send"}
    questionnaire["questions"] = [{"id": "phone", "type": "mobile", "title": "手机号", "required": True, "options": []}]
    calls: list[dict] = []

    def fake_post(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        raise AssertionError("legacy external push must be disabled by default")

    monkeypatch.setattr(external_push.requests, "post", fake_post)
    response = client.post(
        "/api/h5/questionnaires/hxc-activation-v1/submit",
        json={"answers": {"phone": "test_phone_default_queue"}},
        headers={"Idempotency-Key": "push-center-questionnaire-default-queue"},
    )
    body = response.json()

    assert response.status_code == 200
    assert body["external_push_mode"] == "queue"
    assert body["external_push"]["legacy_outbound_disabled"] is True
    assert body["external_push"]["external_effect_required"] is True
    assert body["real_external_call_executed"] is False
    assert body["external_effect_job_status"] == "queued"
    assert calls == []


def test_group_ops_default_webhook_uses_external_effect_not_legacy_gateway(group_ops_api_client, monkeypatch) -> None:
    monkeypatch.delenv("AICRM_GROUP_OPS_OUTBOUND_MODE", raising=False)
    monkeypatch.delenv("AICRM_GROUP_OPS_EXTERNAL_EFFECT_SEND_MODE", raising=False)
    gateway = _install_recording_group_gateway(monkeypatch)
    response = group_ops_api_client.post(
        "/api/automation/group-ops/webhooks/daily-lesson-8f3a",
        headers={"Authorization": "Bearer fixture-webhook-token"},
        json={
            "idempotency_key": "push-center-default-group-ops-external-effect",
            "send_mode": "queued",
            "content": {"text": "synthetic group ops default external effect", "attachments": []},
        },
    )
    body = response.json()

    assert response.status_code == 202
    assert body["outbound_mode"] == "external_effect"
    assert body["legacy_outbound_disabled"] is True
    assert body["external_effect_required"] is True
    assert body["broadcast_job_ids"] == []
    assert body["legacy_broadcast_job_ids"] == []
    assert body["external_effect_job_ids"]
    assert gateway.calls == []
