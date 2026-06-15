from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.admin_config.repository import AdminConfigRepository
from aicrm_next.admin_jobs.routes import ensure_admin_action_token
from aicrm_next.platform_foundation.command_bus import CommandContext
from aicrm_next.platform_foundation.external_effects import (
    WECOM_MESSAGE_PRIVATE_SEND,
    WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH,
    ExternalEffectDispatchResult,
    ExternalEffectService,
    reset_external_effect_fixture_state,
)
from aicrm_next.platform_foundation.external_effects.adapters import ExternalEffectAdapterRegistry
from aicrm_next.platform_foundation.external_effects.worker import ExternalEffectWorker
from aicrm_next.platform_foundation.push_center.capability_registry import PUSH_CAPABILITIES
from aicrm_next.platform_foundation.push_center.section_mapper import all_sections, effect_types_for_section, label_for_section


class _SucceedingAdapter:
    def __init__(self) -> None:
        self.calls = 0

    def dispatch(self, job):
        self.calls += 1
        return ExternalEffectDispatchResult(
            status="succeeded",
            adapter_mode="execute",
            request_summary={"effect_type": job.effect_type},
            response_summary={"ok": True, "real_external_call_executed": False},
            real_external_call_executed=False,
        )


def _set_setting(key: str, value: str) -> None:
    AdminConfigRepository().upsert_app_setting(key=key, value=value)


def _context(trace_id: str) -> CommandContext:
    return CommandContext(actor_id="pytest", actor_type="system", request_id=trace_id, trace_id=trace_id, source_route="/pytest/push-capabilities")


def _plan_job(
    *,
    effect_type: str,
    business_type: str,
    business_id: str,
    adapter_name: str = "outbound_webhook",
    target_type: str = "questionnaire_submission",
    target_id: str = "sub-1",
    idempotency_key: str,
) -> dict:
    return ExternalEffectService().plan_effect(
        effect_type=effect_type,
        adapter_name=adapter_name,
        operation="send" if effect_type == WECOM_MESSAGE_PRIVATE_SEND else "post",
        target_type=target_type,
        target_id=target_id,
        business_type=business_type,
        business_id=business_id,
        payload={"owner_userid": "HuangYouCan", "external_userids": [target_id], "channel": "wecom_private", "content_text": "hello"},
        context=_context(f"trace-{idempotency_key}"),
        source_module="pytest.push_capabilities",
        source_event_id=business_id,
        idempotency_key=idempotency_key,
        status="queued",
        execution_mode="execute",
    )


def _registry(adapter: _SucceedingAdapter) -> ExternalEffectAdapterRegistry:
    registry = ExternalEffectAdapterRegistry()
    registry._adapters["outbound_webhook"] = adapter  # type: ignore[attr-defined]
    registry._adapters["wecom_private_message"] = adapter  # type: ignore[attr-defined]
    return registry


def test_push_capabilities_get_hides_raw_engineering_settings_and_sensitive_values(next_client: TestClient) -> None:
    _set_setting("OPENCLAW_FOCUS_MESSAGE_WEBHOOK_TOKEN", "super-secret-openclaw")
    _set_setting("QUESTIONNAIRE_SUBMIT_WEBHOOK_TOKEN", "super-secret-questionnaire")
    _set_setting("AICRM_EXTERNAL_EFFECT_WEBHOOK_SIGNING_SECRET", "super-secret-signing")

    response = next_client.get("/api/admin/config/push-capabilities")
    body = response.json()
    text = response.text

    assert response.status_code == 200
    assert body["ok"] is True
    keys = {item["key"] for item in body["capabilities"]}
    assert {
        "questionnaire_external_push",
        "order_paid_push",
        "ai_assist_push",
        "private_broadcast",
        "group_ops_push",
    } <= keys
    assert body["summary"]["total"] == 8
    assert all(item["push_center_href"].startswith("/admin/push-center?section=") for item in body["capabilities"])
    assert "super-secret" not in text
    assert "Authorization" not in text
    assert "access_token" not in text
    assert "OPENCLAW_FOCUS_MESSAGE_WEBHOOK_TIMEOUT_SECONDS" not in text
    assert "OUTBOUND_WEBHOOK_RETRY_MAX_ATTEMPTS" not in text
    assert "AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES" not in text


def test_push_capability_toggle_updates_business_setting_and_derived_gates(next_client: TestClient) -> None:
    token = ensure_admin_action_token()
    disabled = next_client.patch(
        "/api/admin/config/push-capabilities/questionnaire_external_push",
        headers={"X-Admin-Action-Token": token},
        json={"enabled": False},
    )
    assert disabled.status_code == 200
    assert disabled.json()["capability"]["enabled"] is False
    assert WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH not in disabled.json()["derived_gates"]["allowed_effect_types"]
    assert AdminConfigRepository().get_app_setting("AICRM_PUSH_CAPABILITY_QUESTIONNAIRE_EXTERNAL_PUSH_ENABLED")["value"] == "false"
    assert WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH not in (AdminConfigRepository().get_app_setting("AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES")["value"] or "")

    enabled = next_client.patch(
        "/api/admin/config/push-capabilities/questionnaire_external_push",
        headers={"X-Admin-Action-Token": token},
        json={"enabled": True},
    )
    assert enabled.status_code == 200
    assert enabled.json()["capability"]["enabled"] is True
    assert WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH in enabled.json()["derived_gates"]["allowed_effect_types"]

    readonly = next_client.patch(
        "/api/admin/config/push-capabilities/group_broadcast",
        headers={"X-Admin-Action-Token": token},
        json={"enabled": True},
    )
    rejected = next_client.patch("/api/admin/config/push-capabilities/order_paid_push", json={"enabled": True})

    assert readonly.status_code == 409
    assert readonly.json()["error"] == "push_capability_not_toggleable"
    assert rejected.status_code == 401


def test_external_effect_worker_blocks_disabled_capability_before_adapter_and_allows_enabled() -> None:
    reset_external_effect_fixture_state()
    _set_setting("AICRM_PUSH_CAPABILITY_QUESTIONNAIRE_EXTERNAL_PUSH_ENABLED", "false")
    job = _plan_job(
        effect_type=WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH,
        business_type="questionnaire",
        business_id="q-disabled",
        idempotency_key="capability-disabled-questionnaire",
    )
    adapter = _SucceedingAdapter()

    blocked = ExternalEffectWorker(adapter_registry=_registry(adapter)).run_due(
        batch_size=1,
        dry_run=False,
        effect_types=[WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH],
    )

    assert blocked["counts"]["blocked_count"] == 1
    assert blocked["items"][0]["attempt"]["error_code"] == "push_capability_disabled"
    assert blocked["real_external_call_executed"] is False
    assert adapter.calls == 0

    _set_setting("AICRM_PUSH_CAPABILITY_QUESTIONNAIRE_EXTERNAL_PUSH_ENABLED", "true")
    _plan_job(
        effect_type=WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH,
        business_type="questionnaire",
        business_id="q-enabled",
        idempotency_key="capability-enabled-questionnaire",
    )
    executed = ExternalEffectWorker(adapter_registry=_registry(adapter)).run_due(
        batch_size=1,
        dry_run=False,
        effect_types=[WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH],
    )

    assert executed["counts"]["succeeded_count"] == 1
    assert adapter.calls == 1
    assert job["id"] != executed["items"][0]["job"]["id"]


def test_shared_wecom_effect_type_is_gated_by_business_section() -> None:
    reset_external_effect_fixture_state()
    _set_setting("AICRM_PUSH_CAPABILITY_AI_ASSIST_PUSH_ENABLED", "true")
    _set_setting("AICRM_PUSH_CAPABILITY_PRIVATE_BROADCAST_ENABLED", "false")
    adapter = _SucceedingAdapter()

    _plan_job(
        effect_type=WECOM_MESSAGE_PRIVATE_SEND,
        adapter_name="wecom_private_message",
        business_type="ai_assist_campaign",
        business_id="camp-1",
        target_type="external_user",
        target_id="wm-ai",
        idempotency_key="wecom-ai-assist-enabled",
    )
    _plan_job(
        effect_type=WECOM_MESSAGE_PRIVATE_SEND,
        adapter_name="wecom_private_message",
        business_type="private_broadcast",
        business_id="broadcast-1",
        target_type="external_user",
        target_id="wm-private",
        idempotency_key="wecom-private-disabled",
    )

    ai_result = ExternalEffectWorker(adapter_registry=_registry(adapter)).run_due(
        batch_size=1,
        dry_run=False,
        effect_types=[WECOM_MESSAGE_PRIVATE_SEND],
    )
    private_result = ExternalEffectWorker(adapter_registry=_registry(adapter)).run_due(
        batch_size=1,
        dry_run=False,
        effect_types=[WECOM_MESSAGE_PRIVATE_SEND],
    )

    assert ai_result["items"][0]["job"]["business_type"] == "ai_assist_campaign"
    assert ai_result["counts"]["succeeded_count"] == 1
    assert private_result["items"][0]["job"]["business_type"] == "private_broadcast"
    assert private_result["items"][0]["attempt"]["error_code"] == "push_capability_disabled"
    assert adapter.calls == 1


def test_webhooks_push_page_is_push_capability_entry(next_client: TestClient) -> None:
    response = next_client.get("/admin/config/detail/webhooks_push")

    assert response.status_code == 200
    assert "推送能力配置" in response.text
    assert "外推总状态" in response.text
    assert "已开启能力" in response.text
    assert "异常任务" in response.text
    assert "旧链路状态" in response.text
    assert "业务推送能力" in response.text
    assert "capabilityTbody" in response.text
    assert "advancedPanel" in response.text
    assert "暂无推送能力数据" in response.text
    assert "缺少操作令牌" in response.text
    assert "data-action=\"toggle\"" in response.text
    assert "readonly_reason" in response.text
    assert "push_center_href" in response.text
    assert "timeout" not in response.text.lower()
    assert "retry" not in response.text.lower()
    assert "allowed_types" not in response.text
    assert "raw token" not in response.text.lower()
    assert "secret" not in response.text.lower()
    assert "Authorization" not in response.text
    assert "access_token" not in response.text
    assert "/api/admin/config/push-capabilities" in response.text
    assert "/api/admin/push-center/stats" in response.text
    assert "/api/admin/push-center/legacy-deprecations" in response.text
    assert "/api/admin/push-center?section=questionnaire" not in response.text


def test_push_center_sections_match_capability_registry_metadata() -> None:
    sections = {item["key"]: item for item in all_sections()}
    for capability in PUSH_CAPABILITIES:
        section = sections[capability.section]
        assert section["label"] == capability.section_label
        assert label_for_section(capability.section) == capability.section_label
        assert set(effect_types_for_section(capability.section)) == set(capability.effect_types)
