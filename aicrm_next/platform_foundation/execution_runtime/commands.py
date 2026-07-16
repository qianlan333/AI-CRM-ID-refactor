from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from aicrm_next.platform_foundation.command_bus.models import CommandContext
from aicrm_next.platform_foundation.internal_events.models import (
    InternalEvent,
    InternalEventConsumerResult,
    InternalEventConsumerRun,
    InternalEventCreateRequest,
)
from aicrm_next.platform_foundation.internal_events.outbox import (
    enqueue_internal_event_outbox_in_session,
)
from aicrm_next.shared.db_session import get_session_factory


QUEUE_RUNTIME_COMMAND_APPLIED = "queue.runtime.command.applied"
QUEUE_RUNTIME_COMMAND_AUDIT_CONSUMER = "queue_runtime_command_audit_consumer"


@dataclass(frozen=True)
class QueueCommandTarget:
    queue_kind: str
    item_id: int
    execution_id: str
    lane: str
    status: str
    version_token: str
    hold_reason: str


@dataclass(frozen=True)
class QueueCommandResult:
    target: QueueCommandTarget
    intent_id: str
    command_id: str
    notification_payload: dict[str, str]


class QueueCommandConflict(RuntimeError):
    """The durable queue row no longer matches the operator's snapshot."""


@dataclass(frozen=True)
class _QueueFact:
    table: str
    eligible_statuses: frozenset[str]
    version_expression: str
    version_predicate: str
    version_assignment: str
    provider_boundary_predicate: str = ""


_QUEUE_FACTS = {
    "external_effect": _QueueFact(
        table="external_effect_job",
        eligible_statuses=frozenset({"queued", "failed_retryable"}),
        version_expression="row_version::text",
        version_predicate="row_version::text = :expected_version",
        version_assignment="row_version = row_version + 1,",
        provider_boundary_predicate="AND provider_call_started_at IS NULL",
    ),
    "internal_event": _QueueFact(
        table="internal_event_consumer_run",
        eligible_statuses=frozenset({"pending", "failed_retryable"}),
        version_expression="xmin::text",
        version_predicate="xmin::text = :expected_version",
        version_assignment="",
    ),
    "internal_outbox": _QueueFact(
        table="internal_event_outbox",
        eligible_statuses=frozenset({"pending", "failed_retryable"}),
        version_expression="xmin::text",
        version_predicate="xmin::text = :expected_version",
        version_assignment="",
    ),
    "webhook_inbox": _QueueFact(
        table="webhook_inbox",
        eligible_statuses=frozenset({"received", "failed_retryable"}),
        version_expression="xmin::text",
        version_predicate="xmin::text = :expected_version",
        version_assignment="",
    ),
}


def _required_text(value: Any, label: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{label} is required")
    return normalized


def _fact(queue_kind: str) -> tuple[str, _QueueFact]:
    normalized = _required_text(queue_kind, "queue_kind").lower()
    fact = _QUEUE_FACTS.get(normalized)
    if fact is None:
        raise ValueError(f"unsupported queue_kind: {normalized}")
    return normalized, fact


class QueueRuntimeCommandService:
    """CAS a concrete queue fact and emit a durable, auditable wake intent.

    The command never executes a handler or provider.  It only makes one
    already-unheld row eligible, appends an Internal Event Outbox audit record,
    and sends a non-sensitive PostgreSQL dirty hint in the same transaction.
    """

    def __init__(
        self,
        *,
        session_factory: Callable[[], Session] | None = None,
    ) -> None:
        self._session_factory = session_factory or get_session_factory()

    def read_target(self, queue_kind: str, item_id: int) -> QueueCommandTarget | None:
        normalized_kind, fact = _fact(queue_kind)
        with self._session_factory() as session:
            row = (
                session.execute(
                    text(
                        f"""
                        SELECT id, execution_id, lane, status, hold_reason,
                               {fact.version_expression} AS version_token
                        FROM {fact.table}
                        WHERE id = :item_id
                        """
                    ),
                    {"item_id": int(item_id)},
                )
                .mappings()
                .fetchone()
            )
            session.rollback()
        return self._target(normalized_kind, row) if row else None

    def request_immediate_execution(
        self,
        queue_kind: str,
        item_id: int,
        *,
        expected_status: str,
        expected_version: str,
        actor: str,
        reason: str,
        command_id: str = "",
        source_route: str = "",
    ) -> QueueCommandResult:
        normalized_kind, fact = _fact(queue_kind)
        normalized_status = _required_text(expected_status, "expected_status")
        normalized_version = _required_text(expected_version, "expected_version")
        normalized_actor = _required_text(actor, "actor")
        normalized_reason = _required_text(reason, "reason")
        normalized_command_id = str(command_id or "").strip() or "qcmd_" + uuid4().hex
        if normalized_status not in fact.eligible_statuses:
            raise ValueError(
                f"status {normalized_status!r} is not eligible for {normalized_kind} immediate execution"
            )

        with self._session_factory() as session:
            with session.begin():
                row = (
                    session.execute(
                        text(
                            f"""
                            UPDATE {fact.table}
                            SET available_at = CURRENT_TIMESTAMP,
                                next_retry_at = CURRENT_TIMESTAMP,
                                worker_generation = 0,
                                {fact.version_assignment}
                                updated_at = CURRENT_TIMESTAMP
                            WHERE id = :item_id
                              AND status = :expected_status
                              AND {fact.version_predicate}
                              AND hold_reason = ''
                              AND (lease_expires_at IS NULL OR lease_expires_at <= CURRENT_TIMESTAMP)
                              {fact.provider_boundary_predicate}
                            RETURNING id, execution_id, lane, status, hold_reason,
                                      {fact.version_expression} AS version_token
                            """
                        ),
                        {
                            "item_id": int(item_id),
                            "expected_status": normalized_status,
                            "expected_version": normalized_version,
                        },
                    )
                    .mappings()
                    .fetchone()
                )
                if not row:
                    raise QueueCommandConflict(
                        "queue command CAS failed; target changed, is held, leased, or crossed the provider boundary"
                    )
                target = self._target(normalized_kind, row)
                notification = {"queue_kind": normalized_kind, "lane": target.lane}
                session.execute(
                    text(
                        """
                        SELECT pg_notify(
                            'aicrm_queue_wakeup',
                            json_build_object(
                                'queue_kind', CAST(:queue_kind AS TEXT),
                                'lane', CAST(:lane AS TEXT)
                            )::text
                        )
                        """
                    ),
                    notification,
                )
                audit = enqueue_internal_event_outbox_in_session(
                    session,
                    InternalEventCreateRequest(
                        event_type=QUEUE_RUNTIME_COMMAND_APPLIED,
                        aggregate_type="queue_runtime_item",
                        aggregate_id=f"{normalized_kind}:{int(item_id)}",
                        subject_type="execution",
                        subject_id=target.execution_id,
                        idempotency_key=f"queue-runtime-command:{normalized_command_id}",
                        source_module="platform_foundation.execution_runtime.commands",
                        source_command_id=normalized_command_id,
                        parent_execution_id=target.execution_id,
                        payload={
                            "queue_kind": normalized_kind,
                            "item_id": int(item_id),
                            "lane": target.lane,
                            "action": "make_eligible_now",
                            "reason": normalized_reason,
                        },
                        payload_summary={
                            "queue_kind": normalized_kind,
                            "lane": target.lane,
                            "action": "make_eligible_now",
                            "expected_status": normalized_status,
                            "provider_call_requested": False,
                        },
                        context=CommandContext(
                            actor_id=normalized_actor,
                            actor_type="operator",
                            request_id=normalized_command_id,
                            trace_id=normalized_command_id,
                            source_route=str(source_route or "").strip(),
                        ),
                    ),
                )
        return QueueCommandResult(
            target=target,
            intent_id=str(audit.get("outbox_id") or ""),
            command_id=normalized_command_id,
            notification_payload=notification,
        )

    @staticmethod
    def _target(queue_kind: str, row: Any) -> QueueCommandTarget:
        values = dict(row or {})
        return QueueCommandTarget(
            queue_kind=queue_kind,
            item_id=int(values.get("id") or 0),
            execution_id=str(values.get("execution_id") or ""),
            lane=str(values.get("lane") or ""),
            status=str(values.get("status") or ""),
            version_token=str(values.get("version_token") or ""),
            hold_reason=str(values.get("hold_reason") or ""),
        )


def consume_queue_runtime_command_audit(
    event: InternalEvent,
    run: InternalEventConsumerRun,
) -> InternalEventConsumerResult:
    payload = dict(event.payload_json or {})
    queue_kind = str(payload.get("queue_kind") or "").strip()
    if queue_kind not in _QUEUE_FACTS:
        return InternalEventConsumerResult(
            status="failed_terminal",
            error_code="invalid_queue_kind",
            error_message="queue runtime command audit has an invalid queue kind",
        )
    return InternalEventConsumerResult(
        status="succeeded",
        request_summary={
            "queue_kind": queue_kind,
            "lane": str(payload.get("lane") or ""),
            "consumer_run_id": int(run.id),
        },
        response_summary={
            "audit_acknowledged": True,
            "inline_execution": False,
            "provider_call_started": False,
        },
        result_summary={"queue_kind": queue_kind, "audit_acknowledged": True},
    )


def register_queue_runtime_command_consumer(registry: Any) -> None:
    registry.register(
        QUEUE_RUNTIME_COMMAND_APPLIED,
        QUEUE_RUNTIME_COMMAND_AUDIT_CONSUMER,
        consume_queue_runtime_command_audit,
        consumer_type="diagnostic",
        max_attempts=3,
    )


__all__ = [
    "QUEUE_RUNTIME_COMMAND_APPLIED",
    "QUEUE_RUNTIME_COMMAND_AUDIT_CONSUMER",
    "QueueCommandConflict",
    "QueueCommandResult",
    "QueueCommandTarget",
    "QueueRuntimeCommandService",
    "consume_queue_runtime_command_audit",
    "register_queue_runtime_command_consumer",
]
