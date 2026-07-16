from __future__ import annotations

from dataclasses import dataclass

import pytest

from aicrm_next.platform_foundation.execution_runtime.cutover import (
    CANONICAL_RUNTIME_SERVICES,
    PR3_LEGACY_PERSISTENT_SERVICES,
    PR3_LEGACY_TIMER_OWNERS,
    REQUIRED_RUNTIME_HEARTBEATS,
    GenerationActivation,
    GenerationState,
    QueueRuntimeCutoverCoordinator,
    QueueRuntimeCutoverRequest,
)
from scripts.ci.check_queue_runtime_cutover_kernel import collect_errors
from scripts.ops import cutover_queue_runtime_generation
from scripts.ops import check_ai_audience_refresh_owner


@dataclass
class _FakeRepository:
    events: list[str]
    ready_after: int = 1
    ready_calls: int = 0
    activation_calls: int = 0
    disable_calls: int = 0

    def assert_gate_closed(self, **_kwargs):
        self.events.append("gate_closed")
        return _state(0, False)

    def ready_heartbeat_names(self, *, generation: int):
        self.ready_calls += 1
        self.events.append(f"ready:{generation}:{self.ready_calls}")
        if self.ready_calls < self.ready_after:
            return frozenset()
        return frozenset(REQUIRED_RUNTIME_HEARTBEATS)

    def activate_generation(self, **kwargs):
        self.activation_calls += 1
        self.events.append(f"cas:{kwargs['expected_generation']}:{kwargs['target_generation']}")
        return GenerationActivation(
            before=_state(int(kwargs["expected_generation"]), False),
            after=_state(int(kwargs["target_generation"]), True),
            activated_lanes=tuple(kwargs["lanes"]),
        )

    def disable_claims(self, **kwargs):
        self.disable_calls += 1
        self.events.append(f"disable:{kwargs['expected_generation']}")
        return _state(int(kwargs["expected_generation"]), False)


class _FakeLifecycle:
    def __init__(
        self,
        events: list[str],
        *,
        fail_drain: bool = False,
        fail_verify: bool = False,
        fail_replacement: bool = False,
    ) -> None:
        self.events = events
        self.fail_drain = fail_drain
        self.fail_verify = fail_verify
        self.fail_replacement = fail_replacement

    def stage_target_generation(self, generation: int) -> None:
        self.events.append(f"stage:{generation}")

    def start_target_service(self, service: str) -> None:
        self.events.append(f"start:{service}")

    def stop_legacy_triggers(self, units) -> None:
        self.events.append(f"stop_triggers:{','.join(units)}")

    def stop_legacy_services(self, units) -> None:
        self.events.append(f"stop_services:{','.join(units)}")

    def wait_legacy_services_drained(self, units, timeout_seconds: int) -> None:
        self.events.append(f"drain:{','.join(units)}:{timeout_seconds}")
        if self.fail_drain:
            raise RuntimeError("old owner still active")

    def retire_legacy_units(self, units) -> None:
        self.events.append(f"retire:{','.join(units)}")

    def verify_single_owner(
        self,
        *,
        legacy_triggers,
        legacy_services,
        legacy_persistent_services,
        replacement_active=False,
    ) -> None:
        self.events.append(
            "verify_single_owner:"
            + ",".join((*legacy_triggers, *legacy_services, *legacy_persistent_services))
        )
        if self.fail_verify:
            raise RuntimeError("old owner still enabled")

    def activate_post_cutover_replacements(self, generation: int) -> None:
        self.events.append(f"activate_replacements:{generation}")
        if self.fail_replacement:
            raise RuntimeError("replacement timer failed")

    def deactivate_post_cutover_replacements(self, generation: int) -> None:
        self.events.append(f"deactivate_replacements:{generation}")


def _state(generation: int, claim_enabled: bool) -> GenerationState:
    return GenerationState(
        active_generation=generation,
        claim_enabled=claim_enabled,
        rollout_mode="canary" if claim_enabled else "standby",
        policy_version="queue-v1",
        updated_by="pytest",
        updated_reason="test",
        updated_at=None,
    )


def _request() -> QueueRuntimeCutoverRequest:
    return QueueRuntimeCutoverRequest(
        expected_generation=0,
        target_generation=17,
        expected_policy_version="queue-v1",
        lanes=("internal_general", "webhook_inbox"),
        actor="pytest",
        reason="cutover ordering test",
        legacy_triggers=("legacy-internal.timer",),
        legacy_services=("legacy-internal.service",),
        legacy_persistent_services=("legacy-inbox.service",),
        readiness_timeout_seconds=5,
        drain_timeout_seconds=20,
    )


def test_cutover_starts_canonical_targets_then_drains_old_owner_before_cas() -> None:
    events: list[str] = []
    repository = _FakeRepository(events, ready_after=2)
    clock = [0.0]

    def sleep(seconds: float) -> None:
        clock[0] += seconds

    result = QueueRuntimeCutoverCoordinator(
        repository=repository,
        lifecycle=_FakeLifecycle(events),
        monotonic=lambda: clock[0],
        sleep=sleep,
    ).activate(_request())

    assert result.after.active_generation == 17
    assert result.after.claim_enabled is True
    assert events[:2] == ["gate_closed", "stage:17"]
    start_events = [f"start:{service}" for service in CANONICAL_RUNTIME_SERVICES]
    assert events[2:5] == start_events
    assert events.index("stop_triggers:legacy-internal.timer") > events.index("ready:17:2")
    assert events.index("stop_services:legacy-inbox.service") > events.index("stop_triggers:legacy-internal.timer")
    assert events.index("drain:legacy-internal.service,legacy-inbox.service:20") < events.index(
        "retire:legacy-internal.timer,legacy-internal.service,legacy-inbox.service"
    )
    assert events.index("ready:17:3") > events.index("drain:legacy-internal.service,legacy-inbox.service:20")
    assert events.index(
        "retire:legacy-internal.timer,legacy-internal.service,legacy-inbox.service"
    ) < events.index("verify_single_owner:legacy-internal.timer,legacy-internal.service,legacy-inbox.service")
    assert events.index(
        "verify_single_owner:legacy-internal.timer,legacy-internal.service,legacy-inbox.service"
    ) < events.index("cas:0:17")
    assert events.index("cas:0:17") < events.index("activate_replacements:17")
    assert events[-1] == "activate_replacements:17"


def test_cutover_drain_failure_keeps_database_claim_gate_closed() -> None:
    events: list[str] = []
    repository = _FakeRepository(events)

    with pytest.raises(RuntimeError, match="old owner still active"):
        QueueRuntimeCutoverCoordinator(
            repository=repository,
            lifecycle=_FakeLifecycle(events, fail_drain=True),
        ).activate(_request())

    assert repository.activation_calls == 0
    assert not any(event.startswith("cas:") for event in events)


def test_cutover_single_owner_verification_failure_keeps_database_claim_gate_closed() -> None:
    events: list[str] = []
    repository = _FakeRepository(events)

    with pytest.raises(RuntimeError, match="old owner still enabled"):
        QueueRuntimeCutoverCoordinator(
            repository=repository,
            lifecycle=_FakeLifecycle(events, fail_verify=True),
        ).activate(_request())

    assert repository.activation_calls == 0
    assert not any(event.startswith("cas:") for event in events)


def test_cutover_replacement_activation_failure_recloses_claim_gate() -> None:
    events: list[str] = []
    repository = _FakeRepository(events)

    with pytest.raises(RuntimeError, match="replacement timer failed"):
        QueueRuntimeCutoverCoordinator(
            repository=repository,
            lifecycle=_FakeLifecycle(events, fail_replacement=True),
        ).activate(_request())

    assert events.index("cas:0:17") < events.index("activate_replacements:17")
    assert events.index("activate_replacements:17") < events.index("disable:17")
    assert events.index("disable:17") < events.index("deactivate_replacements:17")
    assert repository.disable_calls == 1


def test_cutover_rejects_non_monotonic_generation_before_starting_services() -> None:
    events: list[str] = []
    request = _request()
    invalid = QueueRuntimeCutoverRequest(
        **{
            **request.__dict__,
            "expected_generation": 17,
            "target_generation": 17,
        }
    )

    with pytest.raises(ValueError, match="greater than"):
        QueueRuntimeCutoverCoordinator(
            repository=_FakeRepository(events),
            lifecycle=_FakeLifecycle(events),
        ).activate(invalid)

    assert events == []


def test_cutover_cli_is_plan_only_without_explicit_apply(capsys) -> None:
    exit_code = cutover_queue_runtime_generation.main(
        [
            "--expected-generation",
            "0",
            "--target-generation",
            "17",
            "--expected-policy-version",
            "queue-v1",
            "--lane",
            "internal_general",
            "--owner-inventory",
            "pr3",
            "--actor",
            "pytest",
            "--reason",
            "plan only",
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert '"applied": false' in output
    assert '"owner_inventory": "pr3"' in output
    for timer, service in PR3_LEGACY_TIMER_OWNERS:
        assert timer in output
        assert service in output
    for service in PR3_LEGACY_PERSISTENT_SERVICES:
        assert service in output


def test_cutover_cli_rejects_manual_legacy_owner_subset() -> None:
    with pytest.raises(SystemExit):
        cutover_queue_runtime_generation.main(
            [
                "--expected-generation",
                "0",
                "--target-generation",
                "17",
                "--expected-policy-version",
                "queue-v1",
                "--lane",
                "internal_general",
                "--legacy-timer",
                "legacy.timer:legacy.service",
                "--actor",
                "pytest",
                "--reason",
                "manual subset forbidden",
            ]
        )


def test_queue_cutover_ownership_checker_passes() -> None:
    assert collect_errors() == []


def test_ai_audience_legacy_owner_guard_allows_only_closed_generation_zero(monkeypatch) -> None:
    monkeypatch.setattr(
        check_ai_audience_refresh_owner,
        "_runtime_checks",
        lambda _url: {
            "active_generation": 0,
            "claim_enabled": False,
            "rollout_mode": "standby",
            "legacy_owner_allowed": True,
        },
    )

    state = check_ai_audience_refresh_owner.assert_legacy_owner_allowed(
        "postgresql://localhost/test"
    )

    assert state == {
        "active_generation": 0,
        "claim_enabled": False,
        "rollout_mode": "standby",
        "legacy_owner_allowed": True,
        "real_external_call_executed": False,
    }


def test_ai_audience_legacy_owner_guard_fails_after_generation_activation(monkeypatch) -> None:
    monkeypatch.setattr(
        check_ai_audience_refresh_owner,
        "_runtime_checks",
        lambda _url: {
            "active_generation": 17,
            "claim_enabled": True,
            "rollout_mode": "canary",
            "legacy_owner_allowed": False,
        },
    )

    with pytest.raises(RuntimeError, match="forbidden after queue generation activation"):
        check_ai_audience_refresh_owner.assert_legacy_owner_allowed(
            "postgresql://localhost/test"
        )
