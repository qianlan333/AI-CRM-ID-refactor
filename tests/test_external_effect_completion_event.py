from __future__ import annotations

from aicrm_next.platform_foundation.external_effects.adapters import ExternalEffectAdapterRegistry
from aicrm_next.platform_foundation.external_effects.completion_events import (
    EXTERNAL_EFFECT_COMPLETED_EVENT_TYPE,
    external_effect_completion_consumer,
)
from aicrm_next.platform_foundation.external_effects.continuations import (
    ExternalEffectContinuation,
    ExternalEffectContinuationRegistry,
)
from aicrm_next.platform_foundation.external_effects.models import (
    WEBHOOK_GENERIC_PUSH,
    ExternalEffectDispatchResult,
)
from aicrm_next.platform_foundation.external_effects.repo import InMemoryExternalEffectRepository
from aicrm_next.platform_foundation.external_effects.service import ExternalEffectService
from aicrm_next.platform_foundation.external_effects.worker import ExternalEffectWorker
from aicrm_next.platform_foundation.internal_events.models import InternalEvent, InternalEventConsumerRun


class _SuccessAdapter:
    def dispatch(self, _job) -> ExternalEffectDispatchResult:
        return ExternalEffectDispatchResult(
            status="succeeded",
            adapter_mode="execute",
            request_summary={"operation": "post"},
            response_summary={"status_code": 200},
            real_external_call_executed=True,
            provider_result_received=True,
        )


def _completed_job(repo: InMemoryExternalEffectRepository):
    job = ExternalEffectService(repo).plan_effect(
        effect_type=WEBHOOK_GENERIC_PUSH,
        adapter_name="completion_test",
        operation="post",
        target_type="test_target",
        target_id="completion-target",
        idempotency_key="external-effect-completion-consumer",
        status="queued",
        execution_mode="execute",
    )
    adapters = ExternalEffectAdapterRegistry()
    adapters._adapters["completion_test"] = _SuccessAdapter()  # type: ignore[attr-defined]
    result = ExternalEffectWorker(repo, adapters).dispatch_one(job["id"])
    return result["job"], result["attempt"], repo.list_completion_events()[0]


def test_completion_consumer_failure_does_not_change_provider_truth() -> None:
    repo = InMemoryExternalEffectRepository()
    job, attempt, event_payload = _completed_job(repo)
    calls: list[int] = []
    continuations = ExternalEffectContinuationRegistry(
        (
            ExternalEffectContinuation(
                name="failing_projection",
                matches=lambda _job, _result: True,
                run=lambda current_job, _result: calls.append(current_job.id) or {"ok": False, "error": "projection unavailable"},
            ),
        )
    )
    event = InternalEvent(
        event_id="iev_external_effect_completion",
        event_type=EXTERNAL_EFFECT_COMPLETED_EVENT_TYPE,
        aggregate_type="external_effect_job",
        aggregate_id=str(job["id"]),
        payload_json=dict(event_payload["payload"]),
    )
    run = InternalEventConsumerRun(
        id=1,
        event_id=event.event_id,
        consumer_name="external_effect_completion_continuation_consumer",
    )

    result = external_effect_completion_consumer(
        event,
        run,
        repository_factory=lambda: repo,
        continuation_registry_factory=lambda: continuations,
    )

    assert calls == [job["id"]]
    assert result.status == "failed_retryable"
    assert result.error_code == "external_effect_continuation_failed"
    assert repo.get_job(job["id"]).status == "succeeded"  # type: ignore[union-attr]
    assert repo.get_attempt(attempt["attempt_id"]).status == "succeeded"  # type: ignore[union-attr]


def test_completion_consumer_no_match_is_a_successful_noop() -> None:
    repo = InMemoryExternalEffectRepository()
    job, _attempt, event_payload = _completed_job(repo)
    event = InternalEvent(
        event_id="iev_external_effect_completion_noop",
        event_type=EXTERNAL_EFFECT_COMPLETED_EVENT_TYPE,
        aggregate_type="external_effect_job",
        aggregate_id=str(job["id"]),
        payload_json=dict(event_payload["payload"]),
    )
    run = InternalEventConsumerRun(
        id=2,
        event_id=event.event_id,
        consumer_name="external_effect_completion_continuation_consumer",
    )

    result = external_effect_completion_consumer(
        event,
        run,
        repository_factory=lambda: repo,
        continuation_registry_factory=ExternalEffectContinuationRegistry,
    )

    assert result.status == "succeeded"
    assert result.response_summary["continuation"]["applicable"] is False
