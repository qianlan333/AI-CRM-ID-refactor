from __future__ import annotations

from urllib.parse import urlparse

from fastapi.testclient import TestClient

from aicrm_next.cloud_orchestrator.campaigns_read import reset_campaign_read_fixture_state
from aicrm_next.cloud_orchestrator.run_due import (
    PlanCloudCampaignRunDueCommand,
    PreviewCloudCampaignRunDueCommand,
    execute_cloud_campaign_run_due_command,
    reset_run_due_fixture_state,
)
from aicrm_next.platform_foundation.external_effects import (
    AI_ASSIST_CAMPAIGN_MESSAGE_LOOPBACK,
    WEBHOOK_ORDER_PAID_PUSH,
    ExternalEffectService,
    reset_external_effect_fixture_state,
)
from aicrm_next.platform_foundation.external_effects.adapters import DEFAULT_ADAPTER_REGISTRY, WebhookAdapter
from aicrm_next.platform_foundation.external_effects.worker import ExternalEffectWorker


def _reset_fixture_state() -> None:
    reset_campaign_read_fixture_state()
    reset_run_due_fixture_state()
    reset_external_effect_fixture_state()


def _install_loopback_http_adapter(monkeypatch, client: TestClient) -> list[dict]:
    calls: list[dict] = []

    def loopback_post(url, *, json, headers, timeout):
        calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        parsed = urlparse(url)
        return client.post(parsed.path, json=json, headers=headers)

    monkeypatch.setitem(DEFAULT_ADAPTER_REGISTRY._adapters, "outbound_webhook", WebhookAdapter(http_post=loopback_post))  # type: ignore[attr-defined]
    monkeypatch.setitem(DEFAULT_ADAPTER_REGISTRY._adapters, "webhook", WebhookAdapter(http_post=loopback_post))  # type: ignore[attr-defined]
    return calls


def test_ai_assist_campaign_run_due_preview_lists_candidates_without_external_effect_jobs() -> None:
    _reset_fixture_state()

    result = execute_cloud_campaign_run_due_command(
        PreviewCloudCampaignRunDueCommand(
            batch_size=1,
            source_route="/api/admin/cloud-orchestrator/campaigns/run-due/preview",
        )
    )
    items, total = ExternalEffectService().list_jobs({"effect_type": AI_ASSIST_CAMPAIGN_MESSAGE_LOOPBACK})

    assert result["ok"] is True
    assert result["source_status"] == "next_run_due_preview"
    assert result["candidate_count"] == 1
    assert result["external_effect_job_ids"] == []
    assert result["planned_count"] == 0
    assert result["real_external_call_executed"] is False
    assert result["wecom_send_executed"] is False
    assert total == 0
    assert items == []


def test_ai_assist_campaign_run_due_plan_creates_shadow_external_effect_jobs_without_wecom_send() -> None:
    _reset_fixture_state()

    result = execute_cloud_campaign_run_due_command(
        PlanCloudCampaignRunDueCommand(
            batch_size=2,
            source_route="/api/admin/cloud-orchestrator/campaigns/run-due",
            idempotency_key="ai-assist-run-due-shadow-plan",
            trace_id="trace_ai_assist_shadow_plan",
        )
    )
    service = ExternalEffectService()
    items, total = service.list_jobs({"effect_type": AI_ASSIST_CAMPAIGN_MESSAGE_LOOPBACK, "business_type": "ai_assist_campaign"})

    assert result["ok"] is True
    assert result["source_status"] == "next_run_due_plan"
    assert result["candidate_count"] == 2
    assert result["planned_count"] == 2
    assert result["external_effect_planned_count"] == 2
    assert len(result["external_effect_job_ids"]) == 2
    assert result["real_external_call_executed"] is False
    assert result["wecom_send_executed"] is False
    assert total == 2
    assert {item.status for item in items} == {"planned"}
    assert {item.execution_mode for item in items} == {"shadow"}
    assert all(item.adapter_name == "outbound_webhook" for item in items)
    assert all(item.target_type == "campaign_member" for item in items)
    assert all(item.payload_summary_json["webhook_url_present"] is False for item in items)


def test_ai_assist_campaign_loopback_execute_succeeds_with_test_receiver(next_client: TestClient, monkeypatch) -> None:
    _reset_fixture_state()
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_TEST_RECEIVER_ENABLED", "1")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_TEST_EXECUTION_ONLY", "1")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_WEBHOOK_EXECUTE", "1")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES", AI_ASSIST_CAMPAIGN_MESSAGE_LOOPBACK)
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_WEBHOOK_SIGNING_SECRET", "ai-assist-loopback-secret")
    calls = _install_loopback_http_adapter(monkeypatch, next_client)

    plan = execute_cloud_campaign_run_due_command(
        PlanCloudCampaignRunDueCommand(
            batch_size=1,
            source_route="/api/admin/cloud-orchestrator/campaigns/run-due",
            idempotency_key="ai-assist-loopback-plan",
            trace_id="trace_ai_assist_loopback",
            test_only=True,
            test_receiver_base_url="https://crm.example.test",
            receiver_response_status=200,
        )
    )
    job_id = plan["external_effect_job_ids"][0]
    service = ExternalEffectService()
    job = service.get(job_id)
    assert job is not None
    assert job.status == "queued"
    assert job.execution_mode == "execute"
    assert job.payload_json["execution_scope"] == "test_loopback"
    assert job.payload_json["webhook_url"].startswith("https://crm.example.test/api/external-effects/test-receiver/")

    preview = ExternalEffectWorker().preview_due(batch_size=1, effect_types=[AI_ASSIST_CAMPAIGN_MESSAGE_LOOPBACK], test_only=True)
    dry_run = ExternalEffectWorker().run_due(batch_size=1, dry_run=True, effect_types=[AI_ASSIST_CAMPAIGN_MESSAGE_LOOPBACK], test_only=True)
    receipts_before, total_before = service.list_test_receipts({"job_id": job_id}, limit=10)
    executed = ExternalEffectWorker().run_due(batch_size=1, dry_run=False, effect_types=[AI_ASSIST_CAMPAIGN_MESSAGE_LOOPBACK], test_only=True)
    updated = service.get(job_id)
    attempts = service.list_attempts(job_id)
    receipts, total = service.list_test_receipts({"job_id": job_id}, limit=10)

    assert preview["counts"]["candidate_count"] == 1
    assert dry_run["real_external_call_executed"] is False
    assert receipts_before == []
    assert total_before == 0
    assert executed["real_external_call_executed"] is True
    assert updated is not None
    assert updated.status == "succeeded"
    assert attempts[0].status == "succeeded"
    assert attempts[0].response_summary_json["real_external_call_executed"] is True
    assert len(calls) == 1
    assert total == 1
    assert receipts[0].effect_type == AI_ASSIST_CAMPAIGN_MESSAGE_LOOPBACK
    assert receipts[0].trace_id == job.trace_id
    assert receipts[0].signature_valid is True
    assert receipts[0].payload_hash == job.payload_json["expected_payload_hash"]


def test_ai_assist_campaign_run_due_api_injects_current_host_loopback_url(next_client: TestClient, monkeypatch) -> None:
    _reset_fixture_state()
    monkeypatch.setenv("AUTOMATION_INTERNAL_API_TOKEN", "timer-token")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_TEST_RECEIVER_ENABLED", "1")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_TEST_EXECUTION_ONLY", "1")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_WEBHOOK_EXECUTE", "1")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES", AI_ASSIST_CAMPAIGN_MESSAGE_LOOPBACK)

    response = next_client.post(
        "/api/admin/cloud-orchestrator/campaigns/run-due",
        headers={
            "Authorization": "Bearer timer-token",
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Host": "crm.example.test",
        },
        json={
            "batch_size": 1,
            "test_only": True,
            "webhook_url": "https://attacker.example.com/should-not-be-used",
        },
    )
    body = response.json()
    job = ExternalEffectService().get(body["external_effect_job_ids"][0])

    assert response.status_code == 200
    assert body["ok"] is True
    assert body["real_external_call_executed"] is False
    assert body["wecom_send_executed"] is False
    assert job is not None
    assert job.payload_json["webhook_url"].startswith("https://crm.example.test/api/external-effects/test-receiver/")
    assert "attacker.example.com" not in job.payload_json["webhook_url"]


def test_ai_assist_campaign_run_due_api_env_test_mode_injects_loopback_url(next_client: TestClient, monkeypatch) -> None:
    _reset_fixture_state()
    monkeypatch.setenv("AUTOMATION_INTERNAL_API_TOKEN", "timer-token")
    monkeypatch.setenv("AI_ASSIST_EXTERNAL_EFFECT_TEST_MODE", "1")

    response = next_client.post(
        "/api/admin/cloud-orchestrator/campaigns/run-due",
        headers={
            "Authorization": "Bearer timer-token",
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Host": "crm.example.test",
        },
        json={"batch_size": 1},
    )
    body = response.json()
    job = ExternalEffectService().get(body["external_effect_job_ids"][0])

    assert response.status_code == 200
    assert body["real_external_call_executed"] is False
    assert body["wecom_send_executed"] is False
    assert job is not None
    assert job.status == "queued"
    assert job.execution_mode == "execute"
    assert job.payload_json["execution_scope"] == "test_loopback"
    assert job.payload_json["webhook_url"].startswith("https://crm.example.test/api/external-effects/test-receiver/")


def test_ai_assist_campaign_loopback_allowlist_miss_blocks_without_receipt(next_client: TestClient, monkeypatch) -> None:
    _reset_fixture_state()
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_TEST_RECEIVER_ENABLED", "1")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_TEST_EXECUTION_ONLY", "1")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_WEBHOOK_EXECUTE", "1")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES", WEBHOOK_ORDER_PAID_PUSH)
    calls = _install_loopback_http_adapter(monkeypatch, next_client)

    plan = execute_cloud_campaign_run_due_command(
        PlanCloudCampaignRunDueCommand(
            batch_size=1,
            source_route="/api/admin/cloud-orchestrator/campaigns/run-due",
            idempotency_key="ai-assist-loopback-allowlist-miss",
            test_only=True,
            test_receiver_base_url="https://crm.example.test",
        )
    )
    job_id = plan["external_effect_job_ids"][0]
    blocked = ExternalEffectWorker().run_due(batch_size=1, dry_run=False, effect_types=[AI_ASSIST_CAMPAIGN_MESSAGE_LOOPBACK], test_only=True)
    service = ExternalEffectService()
    updated = service.get(job_id)
    attempts = service.list_attempts(job_id)
    receipts, total = service.list_test_receipts({"job_id": job_id}, limit=10)

    assert blocked["counts"]["blocked_count"] == 1
    assert blocked["real_external_call_executed"] is False
    assert updated is not None
    assert updated.status == "blocked"
    assert attempts[0].error_code == "effect_type_not_allowed"
    assert calls == []
    assert receipts == []
    assert total == 0


def test_ai_assist_campaign_loopback_test_only_false_is_rejected(monkeypatch) -> None:
    _reset_fixture_state()
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_TEST_EXECUTION_ONLY", "1")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_WEBHOOK_EXECUTE", "1")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES", AI_ASSIST_CAMPAIGN_MESSAGE_LOOPBACK)

    plan = execute_cloud_campaign_run_due_command(
        PlanCloudCampaignRunDueCommand(
            batch_size=1,
            source_route="/api/admin/cloud-orchestrator/campaigns/run-due",
            idempotency_key="ai-assist-loopback-test-only-required",
            test_only=True,
            test_receiver_base_url="https://crm.example.test",
        )
    )
    rejected = ExternalEffectWorker().run_due(batch_size=1, dry_run=False, effect_types=[AI_ASSIST_CAMPAIGN_MESSAGE_LOOPBACK], test_only=False)
    receipts, total = ExternalEffectService().list_test_receipts({"job_id": plan["external_effect_job_ids"][0]}, limit=10)

    assert rejected["ok"] is False
    assert rejected["error"] == "test_only_required"
    assert rejected["real_external_call_executed"] is False
    assert receipts == []
    assert total == 0
