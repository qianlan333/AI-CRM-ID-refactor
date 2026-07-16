from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Protocol, Sequence

from aicrm_next.shared.runtime import raw_database_url

from .repository import normalize_runtime_database_url, open_runtime_connection


CANONICAL_RUNTIME_SERVICES = (
    "aicrm-internal-queue-runtime.service",
    "aicrm-inbox-queue-runtime.service",
    "aicrm-external-queue-runtime.service",
)
REQUIRED_RUNTIME_HEARTBEATS = (
    "aicrm-internal_event-runtime",
    "aicrm-internal_outbox-runtime",
    "aicrm-webhook_inbox-runtime",
    "aicrm-external_effect-runtime",
)
ACTIVATABLE_LANES = frozenset(
    {
        "internal_general",
        "internal_financial",
        "webhook_inbox",
        "wecom_interactive",
        "wecom_bulk",
        "wecom_media",
    }
)


@dataclass(frozen=True)
class GenerationState:
    active_generation: int
    claim_enabled: bool
    rollout_mode: str
    policy_version: str
    updated_by: str
    updated_reason: str
    updated_at: datetime | None


@dataclass(frozen=True)
class GenerationActivation:
    before: GenerationState
    after: GenerationState
    activated_lanes: tuple[str, ...]


class GenerationCASConflict(RuntimeError):
    """The runtime control row no longer matches the cutover precondition."""


class RuntimeGenerationRepository:
    """Fail-closed numeric generation control over PR-2's canonical tables."""

    def __init__(
        self,
        database_url: str | None = None,
        *,
        connect: Callable[[str], Any] = open_runtime_connection,
    ) -> None:
        self._database_url = normalize_runtime_database_url(database_url or raw_database_url())
        if not self._database_url.startswith("postgresql://"):
            raise RuntimeError("PostgreSQL DATABASE_URL is required for queue generation cutover")
        self._connect = connect

    def read_state(self) -> GenerationState:
        with self._connect(self._database_url) as connection:
            row = connection.execute(
                """
                SELECT active_generation, claim_enabled, rollout_mode,
                       policy_version, updated_by, updated_reason, updated_at
                FROM queue_runtime_control
                WHERE singleton = TRUE
                """
            ).fetchone()
        if not row:
            raise RuntimeError("queue runtime control row is missing")
        return self._state(row)

    def assert_gate_closed(
        self,
        *,
        expected_generation: int,
        expected_policy_version: str,
    ) -> GenerationState:
        expected = self._generation(expected_generation, allow_zero=True)
        policy_version = str(expected_policy_version or "").strip()
        if not policy_version:
            raise ValueError("expected_policy_version is required")
        state = self.read_state()
        if (
            state.active_generation != expected
            or state.claim_enabled
            or state.policy_version != policy_version
        ):
            raise GenerationCASConflict(
                "queue claim gate is not closed at the expected generation and policy version"
            )
        return state

    def activate_generation(
        self,
        *,
        expected_generation: int,
        target_generation: int,
        expected_policy_version: str,
        lanes: Sequence[str],
        actor: str,
        reason: str,
    ) -> GenerationActivation:
        expected = self._generation(expected_generation, allow_zero=True)
        target = self._generation(target_generation, allow_zero=False)
        if target <= expected:
            raise ValueError("target_generation must be greater than expected_generation")
        policy_version = str(expected_policy_version or "").strip()
        normalized_actor = str(actor or "").strip()
        normalized_reason = str(reason or "").strip()
        normalized_lanes = tuple(dict.fromkeys(str(lane or "").strip() for lane in lanes))
        if not policy_version:
            raise ValueError("expected_policy_version is required")
        if not normalized_actor:
            raise ValueError("actor is required")
        if not normalized_reason:
            raise ValueError("reason is required")
        if not normalized_lanes or any(lane not in ACTIVATABLE_LANES for lane in normalized_lanes):
            raise ValueError("lanes must be a non-empty subset of the approved non-outbound lanes")

        with self._connect(self._database_url) as connection:
            with connection.transaction():
                before_row = connection.execute(
                    """
                    SELECT active_generation, claim_enabled, rollout_mode,
                           policy_version, updated_by, updated_reason, updated_at
                    FROM queue_runtime_control
                    WHERE singleton = TRUE
                    FOR UPDATE
                    """
                ).fetchone()
                if not before_row:
                    raise RuntimeError("queue runtime control row is missing")
                before = self._state(before_row)
                if (
                    before.active_generation != expected
                    or before.claim_enabled
                    or before.policy_version != policy_version
                ):
                    raise GenerationCASConflict(
                        "generation activation precondition changed before the CAS"
                    )
                lane_rows = connection.execute(
                    """
                    SELECT lane, enabled, rollout_mode, blocked_until, policy_version
                    FROM queue_lane_policy
                    WHERE lane = ANY(%s)
                    FOR UPDATE
                    """,
                    (list(normalized_lanes),),
                ).fetchall()
                lane_by_name = {str(row.get("lane") or ""): row for row in lane_rows}
                if set(lane_by_name) != set(normalized_lanes):
                    raise GenerationCASConflict("one or more requested lane policy rows are missing")
                now = datetime.now().astimezone()
                for lane in normalized_lanes:
                    row = lane_by_name[lane]
                    blocked_until = row.get("blocked_until")
                    if (
                        not bool(row.get("enabled"))
                        or str(row.get("policy_version") or "") != policy_version
                        or (blocked_until is not None and blocked_until > now)
                    ):
                        raise GenerationCASConflict(
                            f"lane {lane} is disabled, rate-limited, or on another policy version"
                        )
                connection.execute(
                    """
                    UPDATE queue_lane_policy
                    SET rollout_mode = 'canary',
                        updated_by = %s,
                        updated_reason = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE lane = ANY(%s)
                      AND enabled = TRUE
                      AND policy_version = %s
                    """,
                    (
                        normalized_actor,
                        normalized_reason,
                        list(normalized_lanes),
                        policy_version,
                    ),
                )
                after_row = connection.execute(
                    """
                    UPDATE queue_runtime_control
                    SET active_generation = %s,
                        claim_enabled = TRUE,
                        rollout_mode = 'canary',
                        updated_by = %s,
                        updated_reason = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE singleton = TRUE
                      AND active_generation = %s
                      AND claim_enabled = FALSE
                      AND policy_version = %s
                    RETURNING active_generation, claim_enabled, rollout_mode,
                              policy_version, updated_by, updated_reason, updated_at
                    """,
                    (
                        target,
                        normalized_actor,
                        normalized_reason,
                        expected,
                        policy_version,
                    ),
                ).fetchone()
                if not after_row:
                    raise GenerationCASConflict("generation activation CAS lost")
        return GenerationActivation(
            before=before,
            after=self._state(after_row),
            activated_lanes=normalized_lanes,
        )

    def disable_claims(
        self,
        *,
        expected_generation: int,
        actor: str,
        reason: str,
    ) -> GenerationState:
        expected = self._generation(expected_generation, allow_zero=False)
        normalized_actor = str(actor or "").strip()
        normalized_reason = str(reason or "").strip()
        if not normalized_actor or not normalized_reason:
            raise ValueError("actor and reason are required")
        with self._connect(self._database_url) as connection:
            row = connection.execute(
                """
                UPDATE queue_runtime_control
                SET claim_enabled = FALSE,
                    rollout_mode = 'standby',
                    updated_by = %s,
                    updated_reason = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE singleton = TRUE
                  AND active_generation = %s
                  AND claim_enabled = TRUE
                RETURNING active_generation, claim_enabled, rollout_mode,
                          policy_version, updated_by, updated_reason, updated_at
                """,
                (normalized_actor, normalized_reason, expected),
            ).fetchone()
            connection.commit()
        if not row:
            raise GenerationCASConflict("disable-claims CAS lost")
        return self._state(row)

    def ready_heartbeat_names(
        self,
        *,
        generation: int,
        freshness_seconds: int = 30,
    ) -> frozenset[str]:
        target = self._generation(generation, allow_zero=False)
        freshness = max(10, min(int(freshness_seconds or 30), 300))
        with self._connect(self._database_url) as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT service_name
                FROM queue_worker_heartbeat
                WHERE generation = %s
                  AND listener_connected = TRUE
                  AND rollout_mode = 'canary'
                  AND heartbeat_at >= CURRENT_TIMESTAMP - (%s * INTERVAL '1 second')
                  AND service_name = ANY(%s)
                """,
                (target, freshness, list(REQUIRED_RUNTIME_HEARTBEATS)),
            ).fetchall()
        return frozenset(str(row.get("service_name") or "") for row in rows)

    @staticmethod
    def _generation(value: int, *, allow_zero: bool) -> int:
        generation = int(value)
        if generation < 0 or (generation == 0 and not allow_zero):
            comparator = ">= 0" if allow_zero else "> 0"
            raise ValueError(f"generation must be {comparator}")
        return generation

    @staticmethod
    def _state(row: Any) -> GenerationState:
        values = dict(row or {})
        return GenerationState(
            active_generation=int(values.get("active_generation") or 0),
            claim_enabled=bool(values.get("claim_enabled")),
            rollout_mode=str(values.get("rollout_mode") or "blocked"),
            policy_version=str(values.get("policy_version") or ""),
            updated_by=str(values.get("updated_by") or ""),
            updated_reason=str(values.get("updated_reason") or ""),
            updated_at=values.get("updated_at"),
        )


class QueueRuntimeLifecycle(Protocol):
    def stage_target_generation(self, generation: int) -> None: ...

    def start_target_service(self, service: str) -> None: ...

    def stop_legacy_triggers(self, units: Sequence[str]) -> None: ...

    def stop_legacy_services(self, units: Sequence[str]) -> None: ...

    def wait_legacy_services_drained(self, units: Sequence[str], timeout_seconds: int) -> None: ...

    def retire_legacy_units(self, units: Sequence[str]) -> None: ...


@dataclass(frozen=True)
class QueueRuntimeCutoverRequest:
    expected_generation: int
    target_generation: int
    expected_policy_version: str
    lanes: tuple[str, ...]
    actor: str
    reason: str
    legacy_triggers: tuple[str, ...] = ()
    legacy_services: tuple[str, ...] = ()
    legacy_persistent_services: tuple[str, ...] = ()
    readiness_timeout_seconds: int = 60
    drain_timeout_seconds: int = 600


class QueueRuntimeCutoverCoordinator:
    """Start replacements behind the closed gate, drain old owners, then CAS."""

    def __init__(
        self,
        *,
        repository: RuntimeGenerationRepository,
        lifecycle: QueueRuntimeLifecycle,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._repository = repository
        self._lifecycle = lifecycle
        self._monotonic = monotonic
        self._sleep = sleep

    def activate(self, request: QueueRuntimeCutoverRequest) -> GenerationActivation:
        self._validate_request(request)
        self._repository.assert_gate_closed(
            expected_generation=request.expected_generation,
            expected_policy_version=request.expected_policy_version,
        )
        self._lifecycle.stage_target_generation(int(request.target_generation))
        for service in CANONICAL_RUNTIME_SERVICES:
            self._lifecycle.start_target_service(service)
        self._wait_until_target_ready(
            generation=int(request.target_generation),
            timeout_seconds=int(request.readiness_timeout_seconds),
        )
        self._lifecycle.stop_legacy_triggers(request.legacy_triggers)
        self._lifecycle.stop_legacy_services(request.legacy_persistent_services)
        all_legacy_services = tuple(
            dict.fromkeys((*request.legacy_services, *request.legacy_persistent_services))
        )
        self._lifecycle.wait_legacy_services_drained(
            all_legacy_services,
            int(request.drain_timeout_seconds),
        )
        self._wait_until_target_ready(
            generation=int(request.target_generation),
            timeout_seconds=int(request.readiness_timeout_seconds),
        )
        self._lifecycle.retire_legacy_units(
            tuple(
                dict.fromkeys(
                    (
                        *request.legacy_triggers,
                        *request.legacy_services,
                        *request.legacy_persistent_services,
                    )
                )
            )
        )
        activation = self._repository.activate_generation(
            expected_generation=request.expected_generation,
            target_generation=request.target_generation,
            expected_policy_version=request.expected_policy_version,
            lanes=request.lanes,
            actor=request.actor,
            reason=request.reason,
        )
        return activation

    @staticmethod
    def _validate_request(request: QueueRuntimeCutoverRequest) -> None:
        if int(request.expected_generation) < 0:
            raise ValueError("expected_generation must be >= 0")
        if int(request.target_generation) <= 0:
            raise ValueError("target_generation must be > 0")
        if int(request.target_generation) <= int(request.expected_generation):
            raise ValueError("target_generation must be greater than expected_generation")
        if not str(request.expected_policy_version or "").strip():
            raise ValueError("expected_policy_version is required")
        if not str(request.actor or "").strip() or not str(request.reason or "").strip():
            raise ValueError("actor and reason are required")
        if not request.lanes or any(lane not in ACTIVATABLE_LANES for lane in request.lanes):
            raise ValueError("lanes must be a non-empty subset of the approved non-outbound lanes")
        if (
            len(request.legacy_triggers) != len(request.legacy_services)
            or any(not unit.endswith(".timer") for unit in request.legacy_triggers)
            or any(not unit.endswith(".service") for unit in request.legacy_services)
            or any(not unit.endswith(".service") for unit in request.legacy_persistent_services)
            or not (request.legacy_triggers or request.legacy_persistent_services)
        ):
            raise ValueError(
                "declare a service for each legacy timer or at least one persistent legacy service"
            )

    def _wait_until_target_ready(self, *, generation: int, timeout_seconds: int) -> None:
        timeout = max(1, min(int(timeout_seconds or 60), 600))
        deadline = self._monotonic() + timeout
        while True:
            ready = self._repository.ready_heartbeat_names(generation=generation)
            if set(REQUIRED_RUNTIME_HEARTBEATS) <= set(ready):
                return
            if self._monotonic() >= deadline:
                missing = sorted(set(REQUIRED_RUNTIME_HEARTBEATS) - set(ready))
                raise RuntimeError(f"target queue runtime heartbeat timeout: {missing}")
            self._sleep(min(1.0, max(0.0, deadline - self._monotonic())))


__all__ = [
    "ACTIVATABLE_LANES",
    "CANONICAL_RUNTIME_SERVICES",
    "REQUIRED_RUNTIME_HEARTBEATS",
    "GenerationActivation",
    "GenerationCASConflict",
    "GenerationState",
    "QueueRuntimeCutoverCoordinator",
    "QueueRuntimeCutoverRequest",
    "QueueRuntimeLifecycle",
    "RuntimeGenerationRepository",
]
