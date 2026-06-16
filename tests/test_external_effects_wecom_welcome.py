from __future__ import annotations

from aicrm_next.platform_foundation.command_bus import CommandContext
from aicrm_next.platform_foundation.external_effects import (
    ExternalEffectService,
    WECOM_WELCOME_MESSAGE_SEND,
    reset_external_effect_fixture_state,
)
from aicrm_next.platform_foundation.external_effects.adapters import (
    ExternalEffectAdapterRegistry,
    WeComWelcomeMessageAdapter,
    wecom_execution_settings,
)
from aicrm_next.platform_foundation.external_effects.repo import build_external_effect_repository
from aicrm_next.platform_foundation.external_effects.worker import ExternalEffectWorker


class _FakeWelcomeAdapter:
    def __init__(self) -> None:
        self.payloads: list[dict] = []

    def send_welcome_msg(self, payload: dict) -> dict:
        self.payloads.append(dict(payload))
        return {"errcode": 0, "errmsg": "ok"}


def _context(trace_id: str = "trace-wecom-welcome") -> CommandContext:
    return CommandContext(
        actor_id="pytest",
        actor_type="system",
        request_id=trace_id,
        trace_id=trace_id,
        source_route="/pytest/wecom-welcome",
    )


def _plan_welcome_job(*, repo=None, key: str = "welcome-key", execution_mode: str = "execute") -> dict:
    service = ExternalEffectService(repo)
    return service.plan_effect(
        effect_type=WECOM_WELCOME_MESSAGE_SEND,
        adapter_name="wecom_welcome_message",
        operation="send",
        target_type="external_user",
        target_id="wm_welcome_target",
        business_type="channel_entry",
        business_id="channel-1",
        source_module="channel_entry.application",
        source_event_id="evt-1",
        idempotency_key=key,
        payload={
            "welcome_code": "welcome-code",
            "external_userid": "wm_welcome_target",
            "follow_user_userid": "HuangYouCan",
            "text": {"content": "欢迎加入"},
        },
        payload_summary={
            "welcome_code_present": True,
            "external_userid": "wm_welcome_target",
            "follow_user_userid": "HuangYouCan",
            "text_present": True,
        },
        context=_context(),
        status="queued",
        execution_mode=execution_mode,
    )


def _registry(adapter: WeComWelcomeMessageAdapter) -> ExternalEffectAdapterRegistry:
    registry = ExternalEffectAdapterRegistry()
    registry._adapters["wecom_welcome_message"] = adapter  # type: ignore[attr-defined]
    return registry


def test_wecom_welcome_adapter_is_registered_and_advertised() -> None:
    registry = ExternalEffectAdapterRegistry()

    assert registry.get("wecom_welcome_message").__class__.__name__ == "WeComWelcomeMessageAdapter"
    assert WECOM_WELCOME_MESSAGE_SEND in wecom_execution_settings()["supported_types"]


def test_wecom_welcome_default_gates_block_real_send(monkeypatch) -> None:
    reset_external_effect_fixture_state()
    monkeypatch.setattr("aicrm_next.platform_foundation.external_effects.adapters._enabled", lambda name: False)
    monkeypatch.setattr("aicrm_next.platform_foundation.external_effects.adapters._csv_env", lambda name: set())
    monkeypatch.setattr("aicrm_next.platform_foundation.external_effects.worker._capability_gate_error", lambda job: "")
    repo = build_external_effect_repository()
    _plan_welcome_job(repo=repo)
    fake = _FakeWelcomeAdapter()

    result = ExternalEffectWorker(
        repo,
        adapter_registry=_registry(WeComWelcomeMessageAdapter(adapter_factory=lambda: fake)),
    ).run_due(batch_size=1, dry_run=False, effect_types=[WECOM_WELCOME_MESSAGE_SEND])

    assert result["counts"]["failed_count"] == 1
    assert result["items"][0]["attempt"]["error_code"] == "execution_disabled"
    assert result["real_external_call_executed"] is False
    assert fake.payloads == []


def test_wecom_welcome_executes_through_external_effect_worker(monkeypatch) -> None:
    reset_external_effect_fixture_state()
    monkeypatch.setattr("aicrm_next.platform_foundation.external_effects.adapters._enabled", lambda name: name == "AICRM_EXTERNAL_EFFECT_WECOM_EXECUTE")
    monkeypatch.setattr("aicrm_next.platform_foundation.external_effects.adapters._csv_env", lambda name: {WECOM_WELCOME_MESSAGE_SEND} if name == "AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES" else set())
    monkeypatch.setattr("aicrm_next.platform_foundation.external_effects.worker._capability_gate_error", lambda job: "")
    repo = build_external_effect_repository()
    job = _plan_welcome_job(repo=repo)
    fake = _FakeWelcomeAdapter()

    result = ExternalEffectWorker(
        repo,
        adapter_registry=_registry(WeComWelcomeMessageAdapter(adapter_factory=lambda: fake)),
    ).dispatch_one(job["id"])

    assert result["job"]["status"] == "succeeded"
    assert result["attempt"]["status"] == "succeeded"
    assert result["real_external_call_executed"] is True
    assert fake.payloads == [{"welcome_code": "welcome-code", "text": {"content": "欢迎加入"}}]
    assert result["attempt"]["request_summary_json"]["welcome_code_present"] is True
    assert "welcome-code" not in str(result["attempt"]["request_summary_json"])
