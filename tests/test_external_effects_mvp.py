from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from fastapi.testclient import TestClient

from aicrm_next.admin_jobs.routes import ensure_admin_action_token
from aicrm_next.automation_engine.customer_webhooks import (
    PlanCustomerWebhookDeliveryRetryCommand,
    PlanCustomerWebhookDeliveryRetryDueCommand,
    execute_customer_webhook_command,
)
from aicrm_next.customer_tags.live_mutation import execute_wecom_tag_mutation, reset_wecom_tag_live_mutation_fixture_state
from aicrm_next.customer_tags.mutation_commands import PlanWeComTagMarkCommand, PlanWeComTagUnmarkCommand
from aicrm_next.platform_foundation.command_bus import CommandContext
from aicrm_next.platform_foundation.external_effects import (
    ExternalEffectService,
    WEBHOOK_CUSTOMER_AUTOMATION_RETRY,
    WEBHOOK_CUSTOMER_AUTOMATION_RETRY_DUE,
    WEBHOOK_ORDER_PAID_PUSH,
    WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH,
    WECOM_CONTACT_TAG_MARK,
    WECOM_CONTACT_TAG_UNMARK,
    reset_external_effect_fixture_state,
)
from aicrm_next.platform_foundation.external_effects.repo import InMemoryExternalEffectRepository
from aicrm_next.platform_foundation.external_effects.retry_policy import classify_error_code, retry_delay_seconds
from aicrm_next.platform_foundation.external_effects.worker import ExternalEffectWorker
from aicrm_next.platform_foundation.external_effects.adapters import ExternalEffectAdapterRegistry, WebhookAdapter
from aicrm_next.public_product import h5_wechat_pay
from aicrm_next.public_product.h5_wechat_pay import _apply_transaction
from aicrm_next.questionnaire import external_push
from aicrm_next.questionnaire.repo import build_questionnaire_repository


class _ExternalPushResponse:
    status_code = 200
    text = "ok"


class _AdapterResponse:
    def __init__(self, status_code: int, text: str = "adapter-response"):
        self.status_code = status_code
        self.text = text


class _FakeCursor:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _ApplyTransactionConn:
    def __init__(self):
        self.queries: list[str] = []

    def execute(self, query, params):
        self.queries.append(query)
        if query.strip().startswith("SELECT * FROM wechat_pay_orders"):
            return _FakeCursor({"status": "paying", "trade_state": "NOTPAY"})
        if "UPDATE wechat_pay_orders" in query:
            return _FakeCursor(
                {
                    "id": 7,
                    "out_trade_no": params[-1],
                    "status": "paid",
                    "trade_state": "SUCCESS",
                    "product_code": "subscription_trial_month",
                    "paid_at": "2026-06-13T10:00:00+08:00",
                }
            )
        raise AssertionError(query)


def _service(repo: InMemoryExternalEffectRepository) -> ExternalEffectService:
    return ExternalEffectService(repo)


def _sample_context(trace_id: str = "trace-external-effect") -> CommandContext:
    return CommandContext(
        actor_id="tester",
        actor_type="system",
        request_id="req-external-effect",
        trace_id=trace_id,
        source_route="/tests/external-effects",
    )


def _registry_with_post(fake_post) -> ExternalEffectAdapterRegistry:
    registry = ExternalEffectAdapterRegistry()
    registry._adapters["outbound_webhook"] = WebhookAdapter(http_post=fake_post)  # type: ignore[attr-defined]
    registry._adapters["webhook"] = WebhookAdapter(http_post=fake_post)  # type: ignore[attr-defined]
    return registry


def _queued_webhook_job(
    service: ExternalEffectService,
    *,
    effect_type: str = WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH,
    idempotency_key: str = "queued-webhook-execute",
    payload: dict | None = None,
    max_attempts: int = 5,
) -> dict:
    return service.plan_effect(
        effect_type=effect_type,
        adapter_name="outbound_webhook",
        operation="post",
        target_type="questionnaire_submission" if effect_type == WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH else "wechat_pay_order",
        target_id=idempotency_key,
        business_type="questionnaire" if effect_type == WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH else "commerce_order",
        business_id=idempotency_key,
        payload=payload or {"webhook_url": "https://hooks.example.test/effect", "body": {"id": idempotency_key}},
        context=_sample_context(f"trace-{idempotency_key}"),
        idempotency_key=idempotency_key,
        status="queued",
        execution_mode="execute",
        max_attempts=max_attempts,
    )


def test_external_effect_service_idempotency_filters_retry_and_cancel() -> None:
    repo = InMemoryExternalEffectRepository()
    service = _service(repo)

    first = service.plan_effect(
        effect_type=WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH,
        adapter_name="outbound_webhook",
        operation="post",
        target_type="questionnaire_submission",
        target_id="sub-1",
        business_type="questionnaire",
        business_id="q-1",
        payload={"token": "secret", "value": 1},
        context=_sample_context(),
        idempotency_key="same-shadow-job",
        status="blocked",
    )
    second = service.plan_effect(
        effect_type=WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH,
        adapter_name="outbound_webhook",
        operation="post",
        target_type="questionnaire_submission",
        target_id="sub-1",
        business_type="questionnaire",
        business_id="q-1",
        payload={"value": 2},
        context=_sample_context(),
        idempotency_key="same-shadow-job",
    )

    assert first["id"] == second["id"]
    items, total = service.list_jobs(
        {
            "effect_type": WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH,
            "status": "blocked",
            "target_type": "questionnaire_submission",
            "target_id": "sub-1",
            "business_type": "questionnaire",
            "trace_id": "trace-external-effect",
        }
    )
    assert total == 1
    assert items[0].payload_summary_json["token"] == "[redacted]"

    retried = service.retry(first["id"])
    assert retried is not None
    assert retried.status == "queued"
    cancelled = service.cancel(first["id"])
    assert cancelled is not None
    assert cancelled.status == "cancelled"


def test_external_effect_migration_contract_contains_required_tables_indexes_and_idempotency() -> None:
    source = Path("migrations/versions/0039_external_effect_queue.py").read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS external_effect_job" in source
    assert "CREATE TABLE IF NOT EXISTS external_effect_attempt" in source
    assert "uq_external_effect_job_tenant_idempotency" in source
    assert "ON external_effect_job (tenant_id, idempotency_key)" in source
    for index_name in [
        "idx_external_effect_job_due",
        "idx_external_effect_job_target",
        "idx_external_effect_job_business",
        "idx_external_effect_job_trace",
        "idx_external_effect_job_effect_type",
        "idx_external_effect_attempt_job",
        "idx_external_effect_attempt_trace",
    ]:
        assert index_name in source


def test_retry_policy_classifies_retryable_terminal_and_blocked_errors() -> None:
    assert classify_error_code("timeout") == "retryable"
    assert classify_error_code("", status_code=503) == "retryable"
    assert classify_error_code("", status_code=403) == "terminal"
    assert classify_error_code("payload_invalid") == "terminal"
    assert classify_error_code("adapter_blocked") == "blocked"
    assert retry_delay_seconds(0) == 60
    assert retry_delay_seconds(3) == 3600


def test_run_due_preview_dry_run_and_disabled_adapter_do_not_execute_real_call() -> None:
    repo = InMemoryExternalEffectRepository()
    service = _service(repo)
    job = service.plan_effect(
        effect_type=WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH,
        adapter_name="outbound_webhook",
        operation="post",
        target_type="questionnaire_submission",
        target_id="sub-queued",
        payload={"webhook_url": "https://hooks.example.invalid/shadow"},
        context=_sample_context("trace-run-due"),
        idempotency_key="queued-shadow-job",
        status="queued",
        execution_mode="execute",
    )
    worker = ExternalEffectWorker(repo)

    preview = worker.preview_due(batch_size=10)
    dry_run = worker.run_due(batch_size=10)
    blocked = worker.run_due(batch_size=10, dry_run=False)

    assert preview["counts"]["candidate_count"] == 1
    assert dry_run["dry_run"] is True
    assert dry_run["real_external_call_executed"] is False
    assert blocked["counts"]["blocked_count"] == 1
    assert blocked["real_external_call_executed"] is False
    updated = repo.get_job(job["id"])
    assert updated is not None
    assert updated.status == "blocked"
    assert repo.list_attempts(job["id"])[0].error_code == "execution_disabled"


def test_webhook_adapter_default_config_dry_run_and_allowlist_gate_never_send(monkeypatch) -> None:
    repo = InMemoryExternalEffectRepository()
    service = _service(repo)
    _queued_webhook_job(service, idempotency_key="webhook-gates-default")
    calls: list[dict] = []

    def fake_post(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        return _AdapterResponse(204)

    registry = _registry_with_post(fake_post)
    monkeypatch.delenv("AICRM_EXTERNAL_EFFECT_WEBHOOK_EXECUTE", raising=False)
    monkeypatch.delenv("AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES", raising=False)

    dry_run = ExternalEffectWorker(repo, registry).run_due(batch_size=10, dry_run=True)
    blocked = ExternalEffectWorker(repo, registry).run_due(batch_size=10, dry_run=False)

    assert dry_run["real_external_call_executed"] is False
    assert blocked["real_external_call_executed"] is False
    assert calls == []
    assert repo.list_attempts(1)[0].error_code == "execution_disabled"

    repo = InMemoryExternalEffectRepository()
    service = _service(repo)
    _queued_webhook_job(service, idempotency_key="webhook-gates-allowlist")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_WEBHOOK_EXECUTE", "1")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES", WEBHOOK_ORDER_PAID_PUSH)
    not_allowed = ExternalEffectWorker(repo, registry).run_due(batch_size=10, dry_run=False)

    assert not_allowed["real_external_call_executed"] is False
    assert calls == []
    assert repo.list_attempts(1)[0].error_code == "effect_type_not_allowed"


def test_webhook_adapter_enabled_allowlisted_2xx_succeeds_and_records_attempt(monkeypatch) -> None:
    repo = InMemoryExternalEffectRepository()
    service = _service(repo)
    job = _queued_webhook_job(
        service,
        idempotency_key="webhook-2xx",
        payload={
            "webhook_url": "https://hooks.example.test/success",
            "body": {"event": "ok"},
            "signature_secret": "test-secret",
        },
    )
    calls: list[dict] = []

    def fake_post(url, *, json, headers, timeout):
        calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return _AdapterResponse(204, "")

    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_WEBHOOK_EXECUTE", "1")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES", WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH)
    result = ExternalEffectWorker(repo, _registry_with_post(fake_post)).run_due(batch_size=10, dry_run=False)
    attempts = repo.list_attempts(job["id"])
    updated = repo.get_job(job["id"])

    assert result["real_external_call_executed"] is True
    assert updated is not None
    assert updated.status == "succeeded"
    assert len(calls) == 1
    assert calls[0]["url"] == "https://hooks.example.test/success"
    assert calls[0]["json"] == {"event": "ok"}
    assert calls[0]["headers"]["X-AICRM-External-Effect-Signature"]
    assert attempts[0].status == "succeeded"
    assert attempts[0].request_summary_json["signature_configured"] is True
    assert attempts[0].response_summary_json["real_external_call_executed"] is True


def test_webhook_adapter_retryable_statuses_and_timeout_set_next_retry(monkeypatch) -> None:
    for status_code, error_code in [(500, "http_5xx"), (429, "http_429")]:
        repo = InMemoryExternalEffectRepository()
        service = _service(repo)
        job = _queued_webhook_job(service, idempotency_key=f"webhook-retryable-{status_code}")

        def fake_post(url, *, json, headers, timeout, _status_code=status_code):
            return _AdapterResponse(_status_code, "retry later")

        monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_WEBHOOK_EXECUTE", "1")
        monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES", WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH)
        ExternalEffectWorker(repo, _registry_with_post(fake_post)).run_due(batch_size=10, dry_run=False)
        updated = repo.get_job(job["id"])
        attempts = repo.list_attempts(job["id"])

        assert updated is not None
        assert updated.status == "failed_retryable"
        assert updated.next_retry_at
        assert datetime.fromisoformat(updated.next_retry_at.replace("Z", "+00:00"))
        assert attempts[0].error_code == error_code
        assert attempts[0].response_summary_json["status_code"] == status_code

    repo = InMemoryExternalEffectRepository()
    service = _service(repo)
    job = _queued_webhook_job(service, idempotency_key="webhook-timeout")

    def timeout_post(url, *, json, headers, timeout):
        raise requests.Timeout("slow hook")

    ExternalEffectWorker(repo, _registry_with_post(timeout_post)).run_due(batch_size=10, dry_run=False)
    updated = repo.get_job(job["id"])
    attempts = repo.list_attempts(job["id"])

    assert updated is not None
    assert updated.status == "failed_retryable"
    assert updated.next_retry_at
    assert attempts[0].error_code == "timeout"
    assert attempts[0].response_summary_json["real_external_call_executed"] is True


def test_webhook_adapter_terminal_statuses_and_max_attempts(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_WEBHOOK_EXECUTE", "1")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES", WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH)
    for status_code in [400, 401, 403, 404]:
        repo = InMemoryExternalEffectRepository()
        service = _service(repo)
        job = _queued_webhook_job(service, idempotency_key=f"webhook-terminal-{status_code}")

        def fake_post(url, *, json, headers, timeout, _status_code=status_code):
            return _AdapterResponse(_status_code, "terminal")

        ExternalEffectWorker(repo, _registry_with_post(fake_post)).run_due(batch_size=10, dry_run=False)
        updated = repo.get_job(job["id"])
        attempts = repo.list_attempts(job["id"])

        assert updated is not None
        assert updated.status == "failed_terminal"
        assert attempts[0].error_code == f"http_{status_code}"

    repo = InMemoryExternalEffectRepository()
    service = _service(repo)
    job = _queued_webhook_job(service, idempotency_key="webhook-max-attempts", max_attempts=1)

    def retryable_post(url, *, json, headers, timeout):
        return _AdapterResponse(500, "final retry")

    ExternalEffectWorker(repo, _registry_with_post(retryable_post)).run_due(batch_size=10, dry_run=False)
    updated = repo.get_job(job["id"])

    assert updated is not None
    assert updated.status == "failed_terminal"
    assert updated.last_error_code == "http_5xx"


def test_cancelled_job_is_not_scanned_by_run_due_preview() -> None:
    repo = InMemoryExternalEffectRepository()
    service = _service(repo)
    job = _queued_webhook_job(service, idempotency_key="webhook-cancelled-not-due")
    cancelled = service.cancel(job["id"])
    preview = ExternalEffectWorker(repo).preview_due(batch_size=10)

    assert cancelled is not None
    assert cancelled.status == "cancelled"
    assert preview["counts"]["candidate_count"] == 0


def test_external_effect_admin_api_lists_previews_retries_and_cancels(next_client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("AUTOMATION_INTERNAL_API_TOKEN", "effect-token")
    service = ExternalEffectService()
    job = service.plan_effect(
        effect_type=WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH,
        adapter_name="outbound_webhook",
        operation="post",
        target_type="questionnaire_submission",
        target_id="api-sub-1",
        business_type="questionnaire",
        business_id="api-q-1",
        payload={},
        context=_sample_context("trace-api"),
        idempotency_key="api-external-effect-job",
        status="blocked",
    )

    listed = next_client.get("/api/admin/external-effects/jobs", params={"effect_type": WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH})
    detail = next_client.get(f"/api/admin/external-effects/jobs/{job['id']}")
    unauthorized = next_client.post("/api/admin/external-effects/run-due/preview", json={"batch_size": 10})
    preview = next_client.post(
        "/api/admin/external-effects/run-due/preview",
        headers={"Authorization": "Bearer effect-token"},
        json={"batch_size": 10},
    )
    dry_run = next_client.post(
        "/api/admin/external-effects/run-due",
        headers={"Authorization": "Bearer effect-token"},
        json={"batch_size": 10},
    )
    retried = next_client.post(
        f"/api/admin/external-effects/jobs/{job['id']}/retry",
        json={"admin_action_token": ensure_admin_action_token()},
    )
    cancelled = next_client.post(
        f"/api/admin/external-effects/jobs/{job['id']}/cancel",
        json={"admin_action_token": ensure_admin_action_token()},
    )
    unauthorized_cancel = next_client.post(f"/api/admin/external-effects/jobs/{job['id']}/cancel", json={})
    diagnostics = next_client.get("/api/admin/external-effects/diagnostics")

    assert listed.status_code == 200
    assert listed.json()["route_owner"] == "ai_crm_next"
    assert listed.json()["total"] >= 1
    assert detail.status_code == 200
    assert detail.json()["job"]["id"] == job["id"]
    assert unauthorized.status_code == 401
    assert preview.status_code == 200
    assert preview.json()["real_external_call_executed"] is False
    assert dry_run.status_code == 200
    assert dry_run.json()["dry_run"] is True
    assert retried.status_code == 200
    assert retried.json()["job"]["status"] == "queued"
    assert cancelled.status_code == 200
    assert cancelled.json()["job"]["status"] == "cancelled"
    assert unauthorized_cancel.status_code == 401
    assert diagnostics.status_code == 200
    assert diagnostics.json()["schema_contract"]["idempotency_constraint"] == "UNIQUE (tenant_id, idempotency_key)"
    assert diagnostics.json()["real_external_call_executed"] is False
    assert diagnostics.json()["webhook_execution"]["enabled"] is False
    assert diagnostics.json()["real_execution_enabled"] is False
    assert diagnostics.json()["execution_mode"] == "disabled"


def test_external_effect_diagnostics_metrics_execution_mode_and_allowed_types(next_client: TestClient, monkeypatch) -> None:
    monkeypatch.delenv("AICRM_EXTERNAL_EFFECT_WEBHOOK_EXECUTE", raising=False)
    monkeypatch.delenv("AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES", raising=False)
    service = ExternalEffectService()
    old = datetime.now(timezone.utc) - timedelta(seconds=180)
    for status, suffix in [
        ("queued", "queued"),
        ("dispatching", "dispatching"),
        ("failed_retryable", "retryable"),
        ("failed_terminal", "terminal"),
    ]:
        service.plan_effect(
            effect_type=WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH,
            adapter_name="outbound_webhook",
            operation="post",
            target_type="questionnaire_submission",
            target_id=f"diag-{suffix}",
            business_type="questionnaire",
            business_id=f"diag-{suffix}",
            payload={"webhook_url": "https://hooks.example.test/diag", "body": {"id": suffix}},
            context=_sample_context(f"trace-diag-{suffix}"),
            idempotency_key=f"diag-{suffix}",
            status=status,
            execution_mode="execute",
            scheduled_at=old,
        )

    disabled = next_client.get("/api/admin/external-effects/diagnostics")
    body = disabled.json()
    assert disabled.status_code == 200
    assert body["real_execution_enabled"] is False
    assert body["execution_mode"] == "disabled"
    assert body["allowed_effect_types"] == []
    assert body["eligible_due_count"] == 2
    assert body["dispatching_count"] == 1
    assert body["failed_retryable_count"] == 1
    assert body["failed_terminal_count"] == 1
    assert body["oldest_queued_age_seconds"] >= 120
    assert body["oldest_failed_retryable_age_seconds"] >= 120
    assert body["queue_metrics"]["eligible_due_count"] == 2

    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_WEBHOOK_EXECUTE", "1")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES", WEBHOOK_ORDER_PAID_PUSH)
    enabled = next_client.get("/api/admin/external-effects/diagnostics")
    enabled_body = enabled.json()

    assert enabled_body["real_execution_enabled"] is True
    assert enabled_body["execution_mode"] == "executable"
    assert enabled_body["allowed_effect_types"] == [WEBHOOK_ORDER_PAID_PUSH]


def test_external_effect_admin_page_shows_counts_filters_list_detail_and_attempts(next_client: TestClient) -> None:
    service = ExternalEffectService()
    job = service.plan_effect(
        effect_type=WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH,
        adapter_name="outbound_webhook",
        operation="post",
        target_type="questionnaire_submission",
        target_id="page-sub-1",
        business_type="questionnaire",
        business_id="page-q-1",
        payload={},
        context=_sample_context("trace-page"),
        idempotency_key="page-external-effect-job",
        status="queued",
    )
    for effect_type, target_type, target_id, business_type, business_id in [
        (WEBHOOK_ORDER_PAID_PUSH, "wechat_pay_order", "page-order-1", "commerce_order", "page-order-1"),
        (WEBHOOK_CUSTOMER_AUTOMATION_RETRY, "customer_automation_webhook_delivery", "page-delivery-1", "customer_automation_webhook", "page-delivery-1"),
        (WECOM_CONTACT_TAG_MARK, "external_user", "page-wx-ext-1", "wecom_tag", "page-wx-ext-1"),
    ]:
        service.plan_effect(
            effect_type=effect_type,
            adapter_name="outbound_webhook" if effect_type.startswith("webhook.") else "wecom",
            operation="post",
            target_type=target_type,
            target_id=target_id,
            business_type=business_type,
            business_id=business_id,
            payload={},
            context=_sample_context(f"trace-{target_id}"),
            idempotency_key=f"page-{effect_type}-{target_id}",
            status="planned",
        )
    worker = ExternalEffectWorker()
    worker.run_due(batch_size=10, dry_run=False, effect_types=[WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH])
    service.plan_effect(
        effect_type=WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH,
        adapter_name="outbound_webhook",
        operation="post",
        target_type="questionnaire_submission",
        target_id="page-backlog-sub",
        business_type="questionnaire",
        business_id="page-backlog-q",
        payload={},
        context=_sample_context("trace-page-backlog"),
        idempotency_key="page-backlog-external-effect-job",
        status="queued",
    )
    service.plan_effect(
        effect_type=WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH,
        adapter_name="outbound_webhook",
        operation="post",
        target_type="questionnaire_submission",
        target_id="page-failed-retryable",
        business_type="questionnaire",
        business_id="page-failed-retryable",
        payload={},
        context=_sample_context("trace-page-failed-retryable"),
        idempotency_key="page-failed-retryable-job",
        status="failed_retryable",
    )
    service.plan_effect(
        effect_type=WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH,
        adapter_name="outbound_webhook",
        operation="post",
        target_type="questionnaire_submission",
        target_id="page-failed-terminal",
        business_type="questionnaire",
        business_id="page-failed-terminal",
        payload={},
        context=_sample_context("trace-page-failed-terminal"),
        idempotency_key="page-failed-terminal-job",
        status="failed_terminal",
    )

    response = next_client.get(
        "/admin/external-effects",
        params={"job_id": job["id"]},
    )

    assert response.status_code == 200
    html = response.text
    for text in [
        "总任务",
        "任务列表",
        "任务详情",
        "执行尝试",
        "Run-due Preview",
        "Run-due Dry-run",
        "real_external_call_executed=<code>false</code>",
        "执行防护",
        "当前执行模式",
        "disabled",
        "当前没有真实外部调用",
        "Allowed effect types",
        "队列积压提示",
        "eligible_due_count=",
        "failed_retryable_count=",
        "failed_terminal_count=",
        "external-effects-row--retryable",
        "external-effects-row--terminal",
        "Retry",
        "Cancel",
        WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH,
        WEBHOOK_ORDER_PAID_PUSH,
        WEBHOOK_CUSTOMER_AUTOMATION_RETRY,
        WECOM_CONTACT_TAG_MARK,
        "page-sub-1",
        "page-q-1",
        "trace-page",
        "page-external-effect-job",
        "shadow_only",
    ]:
        assert text in html


def test_external_effect_gray_runbook_documents_disabled_preview_dry_run_real_batch_and_rollback() -> None:
    source = Path("docs/queue/external-effect-queue-gray-runbook.md").read_text(encoding="utf-8")

    for text in [
        "Default Disabled Configuration",
        "AICRM_EXTERNAL_EFFECT_WEBHOOK_EXECUTE=0",
        "AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES",
        "Run-Due Preview",
        '"dry_run": true',
        "Batch Size 1 Real Execution",
        '"batch_size": 1',
        "Rollback To Disabled",
        "Manual Retry",
        "Manual Cancel",
        "Do not enable real execution for WeCom",
    ]:
        assert text in source


def test_questionnaire_submit_keeps_external_push_and_creates_shadow_job(client: TestClient, monkeypatch) -> None:
    repo = build_questionnaire_repository()
    questionnaire = repo._questionnaires[0]  # type: ignore[attr-defined]
    questionnaire["external_push_config"] = {"enabled": True, "webhook_url": "https://hooks.example.com/questionnaire"}
    questionnaire["questions"] = [{"id": "phone", "type": "mobile", "title": "手机号", "required": True, "options": []}]

    def fake_post(url: str, **kwargs):
        return _ExternalPushResponse()

    monkeypatch.setattr(external_push.requests, "post", fake_post)

    response = client.post(
        "/api/h5/questionnaires/hxc-activation-v1/submit",
        json={"answers": {"phone": "13770938680"}},
        headers={"Idempotency-Key": "questionnaire-shadow-effect"},
    )

    body = response.json()
    assert response.status_code == 200
    assert body["external_push"]["status"] == "success"
    assert body["real_external_call_executed"] is True
    assert body["external_effect_job"]["effect_type"] == WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH
    assert body["external_effect_job"]["execution_mode"] == "shadow"
    assert body["external_effect_job_id"]


def test_payment_paid_keeps_outbox_and_runtime_and_creates_order_paid_shadow_job(monkeypatch) -> None:
    reset_external_effect_fixture_state()
    outbox_calls: list[dict] = []
    runtime_calls: list[dict] = []

    def fake_enqueue(conn, order):
        outbox_calls.append(dict(order))
        return {"id": 9}

    def fake_runtime(*, order, transaction):
        runtime_calls.append({"order": dict(order), "transaction": dict(transaction)})

    monkeypatch.setattr(h5_wechat_pay, "enqueue_transaction_paid_outbox", fake_enqueue)
    monkeypatch.setattr("aicrm_next.automation_runtime_v2.bridge.process_payment_succeeded_event", fake_runtime)

    order = _apply_transaction(
        _ApplyTransactionConn(),
        {
            "out_trade_no": "WXP_SHADOW_PAID",
            "trade_state": "SUCCESS",
            "transaction_id": "wx_tx_shadow",
            "success_time": "2026-06-13T10:00:00+08:00",
            "amount": {"payer_total": 990},
            "payer": {"openid": "openid_shadow"},
        },
    )

    items, total = ExternalEffectService().list_jobs({"effect_type": WEBHOOK_ORDER_PAID_PUSH, "business_id": "WXP_SHADOW_PAID"})
    assert order["status"] == "paid"
    assert len(outbox_calls) == 1
    assert len(runtime_calls) == 1
    assert total == 1
    assert items[0].target_type == "wechat_pay_order"
    assert items[0].execution_mode == "shadow"


def test_customer_webhook_retry_and_retry_due_create_shadow_jobs() -> None:
    reset_external_effect_fixture_state()
    retry = execute_customer_webhook_command(
        PlanCustomerWebhookDeliveryRetryCommand(
            idempotency_key="customer-webhook-retry-shadow",
            source_route="/api/customers/automation/webhook-deliveries/12/retry",
            delivery_id=12,
        )
    )
    retry_due = execute_customer_webhook_command(
        PlanCustomerWebhookDeliveryRetryDueCommand(
            idempotency_key="customer-webhook-retry-due-shadow",
            source_route="/api/customers/automation/webhook-deliveries/retry-due",
            limit=3,
        )
    )

    assert retry["outbound_webhook_executed"] is False
    assert retry["external_effect_job"]["effect_type"] == WEBHOOK_CUSTOMER_AUTOMATION_RETRY
    assert retry["external_effect_job"]["status"] == "blocked"
    assert retry_due["external_effect_job"]["effect_type"] == WEBHOOK_CUSTOMER_AUTOMATION_RETRY_DUE
    assert retry_due["external_effect_job"]["execution_mode"] == "shadow"


def test_wecom_tag_mark_and_unmark_create_shadow_jobs() -> None:
    reset_external_effect_fixture_state()
    reset_wecom_tag_live_mutation_fixture_state()
    mark = execute_wecom_tag_mutation(
        PlanWeComTagMarkCommand(
            idempotency_key="wecom-tag-mark-shadow",
            external_userid="wx_ext_tag_001",
            tag_ids=["tag_a"],
            source_route="/api/admin/customer-tags/live/mark",
        )
    )
    unmark = execute_wecom_tag_mutation(
        PlanWeComTagUnmarkCommand(
            idempotency_key="wecom-tag-unmark-shadow",
            external_userid="wx_ext_tag_001",
            tag_ids=["tag_a"],
            source_route="/api/admin/customer-tags/live/unmark",
        )
    )

    assert mark["real_external_call_executed"] is False
    assert mark["wecom_api_called"] is False
    assert mark["external_effect_job"]["effect_type"] == WECOM_CONTACT_TAG_MARK
    assert unmark["external_effect_job"]["effect_type"] == WECOM_CONTACT_TAG_UNMARK
    assert unmark["external_effect_job"]["execution_mode"] == "shadow"
