from __future__ import annotations

from aicrm_next.platform_foundation.command_bus import CommandContext
from aicrm_next.platform_foundation.external_effects import ExternalEffectService, WECOM_WELCOME_MESSAGE_SEND
from aicrm_next.platform_foundation.external_effects.adapters import ExternalEffectAdapterRegistry, WeComWelcomeMessageAdapter
from aicrm_next.platform_foundation.external_effects.realtime import wake_external_effect_job
from aicrm_next.platform_foundation.external_effects.repo import InMemoryExternalEffectRepository


class _FakeWelcomeAdapter:
    def __init__(self) -> None:
        self.payloads: list[dict] = []

    def send_welcome_msg(self, payload: dict) -> dict:
        self.payloads.append(dict(payload))
        return {"errcode": 0, "errmsg": "ok"}


def _registry(adapter: WeComWelcomeMessageAdapter) -> ExternalEffectAdapterRegistry:
    registry = ExternalEffectAdapterRegistry()
    registry._adapters["wecom_welcome_message"] = adapter  # type: ignore[attr-defined]
    return registry


class _ExplodingAdapter:
    def dispatch(self, job):
        raise RuntimeError("adapter boom")


def _plan_welcome(repo: InMemoryExternalEffectRepository, key: str = "welcome-realtime") -> dict:
    return ExternalEffectService(repo).plan_effect(
        effect_type=WECOM_WELCOME_MESSAGE_SEND,
        adapter_name="wecom_welcome_message",
        operation="send",
        target_type="external_user",
        target_id="wm-realtime",
        business_type="channel_entry",
        business_id="channel-1",
        source_module="channel_entry.application",
        source_event_id="evt-1",
        idempotency_key=key,
        payload={
            "welcome_code": "welcome-code",
            "external_userid": "wm-realtime",
            "follow_user_userid": "HuangYouCan",
            "text": {"content": "欢迎加入"},
        },
        payload_summary={"welcome_code_present": True},
        context=CommandContext(actor_id="pytest", actor_type="system", request_id="req-1", trace_id="trace-1"),
        status="queued",
        execution_mode="execute",
    )


def test_realtime_wakeup_is_disabled_by_default() -> None:
    repo = InMemoryExternalEffectRepository()
    job = _plan_welcome(repo)

    scheduled = wake_external_effect_job(
        job["id"],
        reason="pytest",
        effect_type=WECOM_WELCOME_MESSAGE_SEND,
        repository=repo,
        run_inline=True,
    )

    assert scheduled is False
    assert repo.get_job(job["id"]).status == "queued"  # type: ignore[union-attr]
    assert repo.list_attempts(job["id"]) == []


def test_realtime_wakeup_requires_realtime_allowlist(monkeypatch) -> None:
    repo = InMemoryExternalEffectRepository()
    job = _plan_welcome(repo)
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_REALTIME_ENABLED", "1")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_REALTIME_ALLOWED_TYPES", "wecom.contact.tag.mark")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES", WECOM_WELCOME_MESSAGE_SEND)
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_WECOM_EXECUTE", "1")

    scheduled = wake_external_effect_job(
        job["id"],
        reason="pytest",
        effect_type=WECOM_WELCOME_MESSAGE_SEND,
        repository=repo,
        run_inline=True,
    )

    assert scheduled is False
    assert repo.get_job(job["id"]).status == "queued"  # type: ignore[union-attr]


def test_realtime_wakeup_requires_external_execution_gate(monkeypatch) -> None:
    repo = InMemoryExternalEffectRepository()
    job = _plan_welcome(repo)
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_REALTIME_ENABLED", "1")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_REALTIME_ALLOWED_TYPES", WECOM_WELCOME_MESSAGE_SEND)
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES", WECOM_WELCOME_MESSAGE_SEND)

    scheduled = wake_external_effect_job(
        job["id"],
        reason="pytest",
        effect_type=WECOM_WELCOME_MESSAGE_SEND,
        repository=repo,
        run_inline=True,
    )

    assert scheduled is False
    assert repo.get_job(job["id"]).status == "queued"  # type: ignore[union-attr]


def test_realtime_wakeup_dispatches_allowed_welcome_job(monkeypatch) -> None:
    repo = InMemoryExternalEffectRepository()
    job = _plan_welcome(repo)
    fake = _FakeWelcomeAdapter()
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_REALTIME_ENABLED", "1")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_REALTIME_ALLOWED_TYPES", WECOM_WELCOME_MESSAGE_SEND)
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES", WECOM_WELCOME_MESSAGE_SEND)
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_WECOM_EXECUTE", "1")
    monkeypatch.setattr("aicrm_next.platform_foundation.external_effects.worker._capability_gate_error", lambda job: "")

    scheduled = wake_external_effect_job(
        job["id"],
        reason="pytest",
        effect_type=WECOM_WELCOME_MESSAGE_SEND,
        repository=repo,
        adapter_registry=_registry(WeComWelcomeMessageAdapter(adapter_factory=lambda: fake)),
        run_inline=True,
    )

    updated = repo.get_job(job["id"])
    attempts = repo.list_attempts(job["id"])
    assert scheduled is True
    assert updated is not None
    assert updated.status == "succeeded"
    assert attempts[0].response_summary_json["real_external_call_executed"] is True
    assert fake.payloads == [{"welcome_code": "welcome-code", "text": {"content": "欢迎加入"}}]


def test_realtime_adapter_exception_leaves_job_retryable_for_worker(monkeypatch) -> None:
    repo = InMemoryExternalEffectRepository()
    job = _plan_welcome(repo, key="welcome-realtime-adapter-exception")
    registry = ExternalEffectAdapterRegistry()
    registry._adapters["wecom_welcome_message"] = _ExplodingAdapter()  # type: ignore[attr-defined]
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_REALTIME_ENABLED", "1")
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_REALTIME_ALLOWED_TYPES", WECOM_WELCOME_MESSAGE_SEND)
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES", WECOM_WELCOME_MESSAGE_SEND)
    monkeypatch.setenv("AICRM_EXTERNAL_EFFECT_WECOM_EXECUTE", "1")
    monkeypatch.setattr("aicrm_next.platform_foundation.external_effects.worker._capability_gate_error", lambda job: "")

    scheduled = wake_external_effect_job(
        job["id"],
        reason="pytest",
        effect_type=WECOM_WELCOME_MESSAGE_SEND,
        repository=repo,
        adapter_registry=registry,
        run_inline=True,
    )

    updated = repo.get_job(job["id"])
    attempts = repo.list_attempts(job["id"])
    assert scheduled is True
    assert updated is not None
    assert updated.status == "failed_retryable"
    assert updated.locked_by == ""
    assert updated.locked_at == ""
    assert updated.next_retry_at
    assert attempts[0].error_code == "adapter_exception"
    assert attempts[0].response_summary_json["real_external_call_executed"] is False
