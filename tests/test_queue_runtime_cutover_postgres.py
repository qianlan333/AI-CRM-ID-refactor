from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import psycopg
import pytest
from psycopg.rows import dict_row

from aicrm_next.platform_foundation.execution_runtime.commands import (
    QUEUE_RUNTIME_COMMAND_APPLIED,
    QueueCommandConflict,
    QueueRuntimeCommandService,
)
from aicrm_next.platform_foundation.execution_runtime.cutover import (
    GenerationCASConflict,
    RuntimeGenerationRepository,
)
from aicrm_next.platform_foundation.execution_runtime.invariants import (
    QueueRuntimeInvariantChecker,
)
from aicrm_next.platform_foundation.execution_runtime.listener import (
    PostgresQueueWakeListener,
)
from aicrm_next.platform_foundation.external_effects.service import (
    ExternalEffectService,
)


pytestmark = pytest.mark.usefixtures("next_pg_schema")


def _database_url() -> str:
    return str(os.environ.get("DATABASE_URL") or os.environ.get("AICRM_TEST_DATABASE_URL") or "")


def _connect(*, autocommit: bool = True):
    return psycopg.connect(_database_url(), autocommit=autocommit, row_factory=dict_row)


@pytest.fixture(autouse=True)
def _reset_control_plane() -> None:
    with _connect() as connection:
        connection.execute("DELETE FROM queue_worker_heartbeat")
        connection.execute(
            """
            UPDATE queue_runtime_control
            SET active_generation = 0,
                claim_enabled = FALSE,
                rollout_mode = 'standby',
                policy_version = 'queue-v1',
                updated_by = 'pytest',
                updated_reason = 'cutover test reset'
            WHERE singleton = TRUE
            """
        )
        connection.execute(
            """
            UPDATE queue_lane_policy
            SET enabled = TRUE,
                rollout_mode = CASE
                    WHEN lane = 'outbound_webhook' THEN 'blocked'
                    ELSE 'standby'
                END,
                blocked_until = NULL,
                policy_version = 'queue-v1',
                updated_by = 'pytest',
                updated_reason = 'cutover test reset'
            """
        )


def test_numeric_generation_cas_allows_only_one_concurrent_winner() -> None:
    barrier = __import__("threading").Barrier(2)

    def activate(target: int) -> tuple[str, int]:
        repository = RuntimeGenerationRepository(_database_url())
        barrier.wait(timeout=5)
        try:
            result = repository.activate_generation(
                expected_generation=0,
                target_generation=target,
                expected_policy_version="queue-v1",
                lanes=("internal_general",),
                actor=f"pytest-{target}",
                reason="concurrent generation CAS",
            )
            return "won", result.after.active_generation
        except GenerationCASConflict:
            return "lost", target

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(activate, (31, 32)))

    assert [status for status, _target in results].count("won") == 1
    assert [status for status, _target in results].count("lost") == 1
    state = RuntimeGenerationRepository(_database_url()).read_state()
    assert state.claim_enabled is True
    assert state.active_generation in {31, 32}


def test_generation_cas_failure_does_not_change_lane_policy() -> None:
    repository = RuntimeGenerationRepository(_database_url())

    with pytest.raises(GenerationCASConflict):
        repository.activate_generation(
            expected_generation=99,
            target_generation=100,
            expected_policy_version="queue-v1",
            lanes=("internal_general",),
            actor="pytest",
            reason="wrong expected generation",
        )

    with _connect() as connection:
        lane = connection.execute(
            "SELECT rollout_mode, updated_reason FROM queue_lane_policy WHERE lane = 'internal_general'"
        ).fetchone()
    assert lane["rollout_mode"] == "standby"
    assert lane["updated_reason"] == "cutover test reset"


def test_command_cas_makes_target_due_writes_audit_intent_and_notifies_lane() -> None:
    scheduled_at = datetime.now(timezone.utc) + timedelta(hours=1)
    job = ExternalEffectService().plan_effect(
        effect_type="test.queue.command",
        adapter_name="test_provider",
        operation="send",
        target_type="test_target",
        target_id=f"target-{uuid4().hex}",
        payload={"execution_scope": "test_loopback"},
        idempotency_key=f"queue-command-{uuid4().hex}",
        scheduled_at=scheduled_at,
        lane="wecom_interactive",
        ordering_key=f"order-{uuid4().hex}",
        fairness_key="pytest",
        rate_scope_key=f"scope-{uuid4().hex}",
    )
    service = QueueRuntimeCommandService()
    before = service.read_target("external_effect", int(job["id"]))
    assert before is not None
    listener = PostgresQueueWakeListener(_database_url())
    listener.connect()
    try:
        result = service.request_immediate_execution(
            "external_effect",
            int(job["id"]),
            expected_status=before.status,
            expected_version=before.version_token,
            actor="pytest",
            reason="operator requested immediate execution",
            command_id=f"pytest-{uuid4().hex}",
        )
        hint = listener.wait(timeout_seconds=1.0)
    finally:
        listener.close()

    assert result.target.lane == "wecom_interactive"
    assert result.target.version_token != before.version_token
    assert result.notification_payload == {
        "queue_kind": "external_effect",
        "lane": "wecom_interactive",
    }
    assert result.intent_id.startswith("ieo_")
    assert hint is not None
    assert hint.queue_kind == "external_effect"
    assert hint.lane == "wecom_interactive"
    with _connect() as connection:
        persisted = connection.execute(
            "SELECT available_at, hold_reason FROM external_effect_job WHERE id = %s",
            (int(job["id"]),),
        ).fetchone()
        audit = connection.execute(
            "SELECT event_type, actor_id, payload_json FROM internal_event_outbox WHERE outbox_id = %s",
            (result.intent_id,),
        ).fetchone()
    assert persisted["available_at"] < scheduled_at
    assert persisted["hold_reason"] == ""
    assert audit["event_type"] == QUEUE_RUNTIME_COMMAND_APPLIED
    assert audit["actor_id"] == "pytest"
    assert audit["payload_json"]["reason"] == "operator requested immediate execution"


def test_command_rejects_stale_version_and_held_history_without_signal() -> None:
    job = ExternalEffectService().plan_effect(
        effect_type="test.queue.command.conflict",
        adapter_name="test_provider",
        operation="send",
        target_type="test_target",
        target_id=f"target-{uuid4().hex}",
        payload={"execution_scope": "test_loopback"},
        idempotency_key=f"queue-command-conflict-{uuid4().hex}",
        lane="wecom_interactive",
    )
    service = QueueRuntimeCommandService()
    target = service.read_target("external_effect", int(job["id"]))
    assert target is not None
    with _connect() as connection:
        connection.execute(
            "UPDATE external_effect_job SET hold_reason = 'history_frozen' WHERE id = %s",
            (int(job["id"]),),
        )

    with pytest.raises(QueueCommandConflict):
        service.request_immediate_execution(
            "external_effect",
            int(job["id"]),
            expected_status=target.status,
            expected_version=target.version_token,
            actor="pytest",
            reason="must remain held",
        )


@pytest.mark.parametrize(
    ("queue_kind", "status", "expected_lane"),
    (
        ("internal_event", "pending", "internal_general"),
        ("internal_outbox", "pending", "internal_financial"),
        ("webhook_inbox", "received", "webhook_inbox"),
    ),
)
def test_command_cas_supports_each_non_external_durable_queue_fact(
    queue_kind: str,
    status: str,
    expected_lane: str,
) -> None:
    key = uuid4().hex
    with _connect() as connection:
        if queue_kind == "internal_event":
            event_id = f"iev_{key}"
            connection.execute(
                """
                INSERT INTO internal_event (
                    event_id, event_type, aggregate_type, aggregate_id,
                    idempotency_key, execution_id
                ) VALUES (%s, 'test.queue.command', 'test', %s, %s, %s)
                """,
                (event_id, key, f"event-{key}", f"exe-event-{key}"),
            )
            row = connection.execute(
                """
                INSERT INTO internal_event_consumer_run (
                    event_id, consumer_name, status, execution_id,
                    parent_execution_id, lane, available_at,
                    ordering_key, fairness_key, policy_version
                ) VALUES (
                    %s, 'pytest_consumer', 'pending', %s, %s,
                    'internal_general', CURRENT_TIMESTAMP + INTERVAL '1 hour',
                    %s, 'pytest', 'queue-v1'
                ) RETURNING id
                """,
                (event_id, f"exe-run-{key}", f"exe-event-{key}", f"order-{key}"),
            ).fetchone()
        elif queue_kind == "internal_outbox":
            row = connection.execute(
                """
                INSERT INTO internal_event_outbox (
                    outbox_id, event_type, aggregate_type, aggregate_id,
                    idempotency_key, execution_id, lane, available_at,
                    ordering_key, fairness_key, policy_version
                ) VALUES (
                    %s, 'test.queue.command', 'test', %s, %s, %s,
                    'internal_financial', CURRENT_TIMESTAMP + INTERVAL '1 hour',
                    %s, 'pytest', 'queue-v1'
                ) RETURNING id
                """,
                (f"ieo_{key}", key, f"outbox-{key}", f"exe-outbox-{key}", f"order-{key}"),
            ).fetchone()
        else:
            row = connection.execute(
                """
                INSERT INTO webhook_inbox (
                    provider, event_family, route, idempotency_key,
                    execution_id, lane, available_at, ordering_key,
                    fairness_key, policy_version
                ) VALUES (
                    'pytest', 'test', '/tests/queue-command', %s, %s,
                    'webhook_inbox', CURRENT_TIMESTAMP + INTERVAL '1 hour',
                    %s, 'pytest', 'queue-v1'
                ) RETURNING id
                """,
                (f"webhook-{key}", f"exe-webhook-{key}", f"order-{key}"),
            ).fetchone()
    item_id = int(row["id"])
    service = QueueRuntimeCommandService()
    target = service.read_target(queue_kind, item_id)
    assert target is not None and target.status == status
    listener = PostgresQueueWakeListener(_database_url())
    listener.connect()
    try:
        result = service.request_immediate_execution(
            queue_kind,
            item_id,
            expected_status=status,
            expected_version=target.version_token,
            actor="pytest",
            reason=f"make {queue_kind} immediately eligible",
        )
        hint = listener.wait(timeout_seconds=1.0)
    finally:
        listener.close()

    assert result.target.lane == expected_lane
    assert result.target.version_token != target.version_token
    assert hint is not None
    assert hint.queue_kind == queue_kind
    assert hint.lane == expected_lane


def test_invariant_checker_reports_without_changing_queue_rows() -> None:
    job = ExternalEffectService().plan_effect(
        effect_type="test.queue.invariant",
        adapter_name="test_provider",
        operation="send",
        target_type="test_target",
        target_id=f"target-{uuid4().hex}",
        payload={"execution_scope": "test_loopback"},
        idempotency_key=f"queue-invariant-{uuid4().hex}",
        lane="wecom_interactive",
    )
    with _connect() as connection:
        connection.execute(
            """
            UPDATE external_effect_job
            SET status = 'dispatching', lease_token = '', lease_expires_at = NULL,
                worker_generation = 0
            WHERE id = %s
            """,
            (int(job["id"]),),
        )
        before = connection.execute(
            "SELECT status, lease_token, lease_expires_at, worker_generation, updated_at FROM external_effect_job WHERE id = %s",
            (int(job["id"]),),
        ).fetchone()

    report = QueueRuntimeInvariantChecker(_database_url()).check()

    with _connect() as connection:
        after = connection.execute(
            "SELECT status, lease_token, lease_expires_at, worker_generation, updated_at FROM external_effect_job WHERE id = %s",
            (int(job["id"]),),
        ).fetchone()
    assert report.read_only is True
    assert any(item.code == "active_lease_incomplete" for item in report.violations)
    assert dict(after) == dict(before)


def test_invariant_checker_reports_missing_active_generation_heartbeats() -> None:
    RuntimeGenerationRepository(_database_url()).activate_generation(
        expected_generation=0,
        target_generation=77,
        expected_policy_version="queue-v1",
        lanes=("internal_general",),
        actor="pytest",
        reason="heartbeat invariant test",
    )

    report = QueueRuntimeInvariantChecker(_database_url()).check()

    missing = {
        item.dimensions.get("queue_kind")
        for item in report.violations
        if item.code == "missing_active_worker_heartbeat"
    }
    assert missing == {
        "aicrm-internal_event-runtime",
        "aicrm-internal_outbox-runtime",
        "aicrm-webhook_inbox-runtime",
        "aicrm-external_effect-runtime",
    }
