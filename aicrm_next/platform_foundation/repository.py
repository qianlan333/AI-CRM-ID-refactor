from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Any, Callable

from aicrm_next.shared.runtime import raw_database_url


def _psycopg_url(url: str) -> str:
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url[len("postgresql+psycopg://") :]
    return url


def connect_operation_members_db() -> Any | None:
    database_url = _psycopg_url(raw_database_url())
    if not database_url.startswith(("postgresql://", "postgres://")):
        return None
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(database_url, row_factory=dict_row)


ConnectionFactory = Callable[[str], AbstractContextManager[Any]]


def _connect_readiness_db(database_url: str) -> AbstractContextManager[Any]:
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(
        _psycopg_url(database_url),
        autocommit=True,
        connect_timeout=3,
        row_factory=dict_row,
    )


class RuntimeReadinessRepository:
    def __init__(self, database_url: str, *, connection_factory: ConnectionFactory | None = None) -> None:
        self._database_url = database_url
        self._connection_factory = connection_factory or _connect_readiness_db
        self._connection_context: AbstractContextManager[Any] | None = None
        self._connection: Any | None = None

    def __enter__(self) -> "RuntimeReadinessRepository":
        self._connection_context = self._connection_factory(self._database_url)
        self._connection = self._connection_context.__enter__()
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        if self._connection_context is None:
            return False
        return bool(self._connection_context.__exit__(exc_type, exc, traceback))

    def ping(self) -> bool:
        row = self._execute("SELECT 1 AS ok").fetchone()
        return bool(row and int(row.get("ok") or 0) == 1)

    def migration_revisions(self) -> tuple[str, ...]:
        rows = self._execute("SELECT version_num FROM alembic_version ORDER BY version_num").fetchall()
        return tuple(sorted(str(row.get("version_num") or "").strip() for row in rows if row.get("version_num")))

    def queue_metrics(
        self,
        *,
        allowed_pairs: tuple[tuple[str, str], ...] = (),
        allowed_event_types: tuple[str, ...] = (),
        allowed_consumers: tuple[str, ...] = (),
    ) -> dict[str, int]:
        params: dict[str, Any] = {}
        if allowed_pairs:
            predicates = ["(e.event_type || ':' || r.consumer_name) = ANY(%(allowed_pairs)s)"]
            params["allowed_pairs"] = [f"{event_type}:{consumer_name}" for event_type, consumer_name in allowed_pairs]
            if allowed_event_types:
                predicates.append("e.event_type = ANY(%(allowed_event_types)s)")
                params["allowed_event_types"] = list(allowed_event_types)
            actionable_predicate = " AND ".join(predicates)
        else:
            predicates: list[str] = []
            if allowed_event_types:
                predicates.append("e.event_type = ANY(%(allowed_event_types)s)")
                params["allowed_event_types"] = list(allowed_event_types)
            if allowed_consumers:
                predicates.append("r.consumer_name = ANY(%(allowed_consumers)s)")
                params["allowed_consumers"] = list(allowed_consumers)
            actionable_predicate = " AND ".join(predicates) if predicates else "TRUE"
        row = self._execute(
            f"""
            WITH internal_rows AS (
              SELECT
                r.*,
                ({actionable_predicate}) AS policy_allowed,
                r.status IN ('pending', 'running', 'failed_retryable') AS raw_open,
                (
                  r.hold_reason = ''
                  AND ({actionable_predicate})
                  AND r.attempt_count < r.max_attempts
                  AND (
                    (r.status = 'pending' AND (r.locked_at IS NULL OR r.locked_at <= CURRENT_TIMESTAMP - INTERVAL '5 minutes'))
                    OR (r.status = 'failed_retryable'
                        AND (r.next_retry_at IS NULL OR r.next_retry_at <= CURRENT_TIMESTAMP)
                        AND (r.locked_at IS NULL OR r.locked_at <= CURRENT_TIMESTAMP - INTERVAL '5 minutes'))
                    OR (r.status = 'running' AND r.locked_at <= CURRENT_TIMESTAMP - INTERVAL '5 minutes')
                  )
                ) AS eligible
              FROM internal_event_consumer_run r
              JOIN internal_event e ON e.event_id = r.event_id
            ), internal_terminal AS (
              SELECT ({actionable_predicate}) AS policy_allowed
              FROM internal_event_consumer_run r
              JOIN internal_event e ON e.event_id = r.event_id
              WHERE r.status IN ('failed_terminal', 'blocked')
            ), queue_policy_rows AS (
              SELECT
                'webhook_inbox'::text AS queue_kind,
                i.received_at AS enqueued_at,
                i.status IN ('received', 'processing', 'failed_retryable') AS raw_open,
                i.hold_reason <> '' AND i.status IN ('received', 'processing', 'failed_retryable') AS held,
                (
                  i.hold_reason = '' AND i.attempt_count < i.max_attempts AND (
                    (i.status IN ('received', 'failed_retryable')
                     AND (i.next_retry_at IS NULL OR i.next_retry_at <= CURRENT_TIMESTAMP)
                     AND (i.locked_at IS NULL OR i.locked_at <= CURRENT_TIMESTAMP - INTERVAL '5 minutes'))
                    OR (i.status = 'processing' AND i.locked_at <= CURRENT_TIMESTAMP - INTERVAL '5 minutes')
                  )
                ) AS eligible,
                FALSE AS scheduled,
                (i.hold_reason = '' AND i.status = 'failed_retryable' AND i.next_retry_at > CURRENT_TIMESTAMP) AS retry_wait,
                (i.hold_reason = '' AND i.status = 'processing'
                 AND i.locked_at > CURRENT_TIMESTAMP - INTERVAL '5 minutes') AS in_flight,
                FALSE AS unknown,
                i.status IN ('dead_letter', 'failed_terminal') AS dlq
              FROM webhook_inbox i

              UNION ALL

              SELECT
                'internal_event', r.created_at, r.raw_open,
                r.hold_reason <> '' AND r.raw_open,
                r.eligible,
                FALSE,
                (r.hold_reason = '' AND r.status = 'failed_retryable' AND r.next_retry_at > CURRENT_TIMESTAMP),
                (r.hold_reason = '' AND r.status = 'running'
                 AND r.locked_at > CURRENT_TIMESTAMP - INTERVAL '5 minutes'),
                FALSE,
                r.status IN ('failed_terminal', 'blocked')
              FROM internal_rows r

              UNION ALL

              SELECT
                'internal_event_outbox', o.created_at,
                o.status IN ('pending', 'running', 'failed_retryable'),
                o.hold_reason <> '' AND o.status IN ('pending', 'running', 'failed_retryable'),
                (
                  o.hold_reason = '' AND o.attempt_count < o.max_attempts AND (
                    (o.status = 'pending' AND (o.locked_at IS NULL OR o.locked_at <= CURRENT_TIMESTAMP - INTERVAL '5 minutes'))
                    OR (o.status = 'failed_retryable'
                        AND (o.next_retry_at IS NULL OR o.next_retry_at <= CURRENT_TIMESTAMP)
                        AND (o.locked_at IS NULL OR o.locked_at <= CURRENT_TIMESTAMP - INTERVAL '5 minutes'))
                    OR (o.status = 'running' AND o.locked_at <= CURRENT_TIMESTAMP - INTERVAL '5 minutes')
                  )
                ),
                FALSE,
                (o.hold_reason = '' AND o.status = 'failed_retryable' AND o.next_retry_at > CURRENT_TIMESTAMP),
                (o.hold_reason = '' AND o.status = 'running'
                 AND o.locked_at > CURRENT_TIMESTAMP - INTERVAL '5 minutes'),
                FALSE,
                o.status = 'failed_terminal'
              FROM internal_event_outbox o

              UNION ALL

              SELECT
                'external_effect', j.created_at,
                j.status IN ('planned', 'approved', 'queued', 'dispatching', 'failed_retryable'),
                j.hold_reason <> '' AND j.status IN ('planned', 'approved', 'queued', 'dispatching', 'failed_retryable'),
                (
                  j.hold_reason = ''
                  AND j.status IN ('queued', 'failed_retryable')
                  AND j.attempt_count < j.max_attempts
                  AND j.scheduled_at <= CURRENT_TIMESTAMP
                  AND (j.next_retry_at IS NULL OR j.next_retry_at <= CURRENT_TIMESTAMP)
                  AND (j.lease_expires_at IS NULL OR j.lease_expires_at <= CURRENT_TIMESTAMP)
                ),
                (j.hold_reason = '' AND j.status = 'queued' AND j.scheduled_at > CURRENT_TIMESTAMP),
                (j.hold_reason = '' AND j.status = 'failed_retryable' AND j.next_retry_at > CURRENT_TIMESTAMP),
                (j.hold_reason = '' AND j.status = 'dispatching' AND j.lease_expires_at > CURRENT_TIMESTAMP),
                (j.status = 'unknown_after_dispatch' OR j.reconciliation_required = TRUE),
                j.status IN ('failed_terminal', 'blocked')
              FROM external_effect_job j

              UNION ALL

              SELECT
                'broadcast', b.created_at,
                b.status IN ('waiting_approval', 'queued', 'claimed', 'dispatching', 'failed_retryable'),
                b.hold_reason <> '' AND b.status IN ('waiting_approval', 'queued', 'claimed', 'dispatching', 'failed_retryable'),
                (
                  b.hold_reason = '' AND b.attempt_count < b.max_attempts AND b.scheduled_for <= CURRENT_TIMESTAMP AND (
                    b.status = 'queued'
                    OR (b.status = 'failed_retryable' AND (b.next_retry_at IS NULL OR b.next_retry_at <= CURRENT_TIMESTAMP))
                    OR (b.status = 'claimed' AND b.lease_expires_at <= CURRENT_TIMESTAMP)
                  )
                ),
                (b.hold_reason = '' AND b.status = 'queued' AND b.scheduled_for > CURRENT_TIMESTAMP),
                (b.hold_reason = '' AND b.status = 'failed_retryable' AND b.next_retry_at > CURRENT_TIMESTAMP),
                (b.hold_reason = '' AND b.status IN ('claimed', 'dispatching')
                 AND b.lease_expires_at > CURRENT_TIMESTAMP),
                (b.status = 'unknown_after_dispatch' OR b.reconciliation_required = TRUE),
                b.status IN ('failed', 'failed_terminal', 'blocked')
              FROM broadcast_jobs b
            )
            SELECT
              1::BIGINT AS queue_policy_version,
              COUNT(*) FILTER (WHERE raw_open)::BIGINT AS queue_raw_open_count,
              COUNT(*) FILTER (WHERE held)::BIGINT AS queue_held_count,
              COUNT(*) FILTER (WHERE eligible)::BIGINT AS queue_eligible_count,
              COUNT(*) FILTER (WHERE scheduled)::BIGINT AS queue_scheduled_count,
              COUNT(*) FILTER (WHERE retry_wait)::BIGINT AS queue_retry_wait_count,
              0::BIGINT AS queue_rate_limited_count,
              COUNT(*) FILTER (WHERE in_flight)::BIGINT AS queue_in_flight_count,
              COUNT(*) FILTER (WHERE unknown)::BIGINT AS queue_unknown_count,
              COUNT(*) FILTER (WHERE dlq)::BIGINT AS queue_dlq_count,

              COUNT(*) FILTER (WHERE queue_kind = 'webhook_inbox' AND raw_open)::BIGINT AS webhook_pending_count,
              COUNT(*) FILTER (WHERE queue_kind = 'webhook_inbox' AND raw_open)::BIGINT AS webhook_raw_open_count,
              COUNT(*) FILTER (WHERE queue_kind = 'webhook_inbox' AND held)::BIGINT AS webhook_held_count,
              COUNT(*) FILTER (WHERE queue_kind = 'webhook_inbox' AND eligible)::BIGINT AS webhook_eligible_count,
              COUNT(*) FILTER (WHERE queue_kind = 'webhook_inbox' AND scheduled)::BIGINT AS webhook_scheduled_count,
              COUNT(*) FILTER (WHERE queue_kind = 'webhook_inbox' AND retry_wait)::BIGINT AS webhook_retry_wait_count,
              0::BIGINT AS webhook_rate_limited_count,
              COUNT(*) FILTER (WHERE queue_kind = 'webhook_inbox' AND in_flight)::BIGINT AS webhook_in_flight_count,
              COUNT(*) FILTER (WHERE queue_kind = 'webhook_inbox' AND unknown)::BIGINT AS webhook_unknown_count,
              COALESCE(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - MIN(enqueued_at) FILTER (
                WHERE queue_kind = 'webhook_inbox' AND raw_open
              ))), 0)::BIGINT AS webhook_oldest_pending_age_seconds,
              COALESCE(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - MIN(enqueued_at) FILTER (
                WHERE queue_kind = 'webhook_inbox' AND eligible
              ))), 0)::BIGINT AS webhook_eligible_oldest_pending_age_seconds,
              (SELECT COUNT(*) FROM webhook_inbox WHERE status = 'dead_letter')::BIGINT AS webhook_dead_letter_count,
              COUNT(*) FILTER (WHERE queue_kind = 'webhook_inbox' AND dlq)::BIGINT AS webhook_dlq_count,

              (SELECT COUNT(*) FROM internal_rows WHERE raw_open)::BIGINT AS internal_event_pending_count,
              (SELECT COUNT(*) FROM internal_rows WHERE raw_open)::BIGINT AS internal_event_raw_open_count,
              (SELECT COUNT(*) FROM internal_rows WHERE raw_open AND hold_reason <> '')::BIGINT AS internal_event_held_count,
              (SELECT COUNT(*) FROM internal_rows WHERE eligible)::BIGINT AS internal_event_actionable_pending_count,
              (SELECT COUNT(*) FROM internal_rows WHERE eligible)::BIGINT AS internal_event_eligible_count,
              COUNT(*) FILTER (WHERE queue_kind = 'internal_event' AND scheduled)::BIGINT AS internal_event_scheduled_count,
              COUNT(*) FILTER (WHERE queue_kind = 'internal_event' AND retry_wait)::BIGINT AS internal_event_retry_wait_count,
              0::BIGINT AS internal_event_rate_limited_count,
              COUNT(*) FILTER (WHERE queue_kind = 'internal_event' AND in_flight)::BIGINT AS internal_event_in_flight_count,
              COUNT(*) FILTER (WHERE queue_kind = 'internal_event' AND unknown)::BIGINT AS internal_event_unknown_count,
              COUNT(*) FILTER (WHERE queue_kind = 'internal_event' AND dlq)::BIGINT AS internal_event_dlq_count,
              (SELECT COALESCE(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - MIN(created_at))), 0)
                 FROM internal_rows WHERE raw_open)::BIGINT AS internal_event_oldest_pending_age_seconds,
              (SELECT COALESCE(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - MIN(created_at))), 0)
                 FROM internal_rows WHERE eligible)::BIGINT AS internal_event_actionable_oldest_pending_age_seconds,
              (SELECT COUNT(*) FROM internal_rows WHERE raw_open AND NOT policy_allowed)::BIGINT AS internal_event_rollout_gated_pending_count,
              (SELECT COALESCE(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - MIN(created_at))), 0)
                 FROM internal_rows WHERE raw_open AND NOT policy_allowed)::BIGINT AS internal_event_rollout_gated_oldest_pending_age_seconds,
              (SELECT COUNT(*) FROM internal_terminal)::BIGINT AS internal_event_terminal_count,
              (SELECT COUNT(*) FROM internal_terminal WHERE policy_allowed)::BIGINT AS internal_event_actionable_terminal_count,
              (SELECT COUNT(*) FROM internal_terminal WHERE NOT policy_allowed)::BIGINT AS internal_event_rollout_gated_terminal_count,

              COUNT(*) FILTER (WHERE queue_kind = 'internal_event_outbox' AND raw_open)::BIGINT AS internal_event_outbox_raw_open_count,
              COUNT(*) FILTER (WHERE queue_kind = 'internal_event_outbox' AND held)::BIGINT AS internal_event_outbox_held_count,
              COUNT(*) FILTER (WHERE queue_kind = 'internal_event_outbox' AND eligible)::BIGINT AS internal_event_outbox_eligible_count,
              COUNT(*) FILTER (WHERE queue_kind = 'internal_event_outbox' AND scheduled)::BIGINT AS internal_event_outbox_scheduled_count,
              COUNT(*) FILTER (WHERE queue_kind = 'internal_event_outbox' AND retry_wait)::BIGINT AS internal_event_outbox_retry_wait_count,
              0::BIGINT AS internal_event_outbox_rate_limited_count,
              COUNT(*) FILTER (WHERE queue_kind = 'internal_event_outbox' AND in_flight)::BIGINT AS internal_event_outbox_in_flight_count,
              COUNT(*) FILTER (WHERE queue_kind = 'internal_event_outbox' AND unknown)::BIGINT AS internal_event_outbox_unknown_count,
              COUNT(*) FILTER (WHERE queue_kind = 'internal_event_outbox' AND dlq)::BIGINT AS internal_event_outbox_dlq_count,

              COUNT(*) FILTER (WHERE queue_kind = 'external_effect' AND raw_open)::BIGINT AS external_effect_pending_count,
              COUNT(*) FILTER (WHERE queue_kind = 'external_effect' AND raw_open)::BIGINT AS external_effect_raw_open_count,
              COUNT(*) FILTER (WHERE queue_kind = 'external_effect' AND held)::BIGINT AS external_effect_held_count,
              COUNT(*) FILTER (WHERE queue_kind = 'external_effect' AND eligible)::BIGINT AS external_effect_eligible_count,
              COUNT(*) FILTER (WHERE queue_kind = 'external_effect' AND scheduled)::BIGINT AS external_effect_scheduled_count,
              COUNT(*) FILTER (WHERE queue_kind = 'external_effect' AND retry_wait)::BIGINT AS external_effect_retry_wait_count,
              0::BIGINT AS external_effect_rate_limited_count,
              COUNT(*) FILTER (WHERE queue_kind = 'external_effect' AND in_flight)::BIGINT AS external_effect_in_flight_count,
              COUNT(*) FILTER (WHERE queue_kind = 'external_effect' AND unknown)::BIGINT AS external_effect_unknown_count,
              COALESCE(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - MIN(enqueued_at) FILTER (
                WHERE queue_kind = 'external_effect' AND raw_open
              ))), 0)::BIGINT AS external_effect_oldest_pending_age_seconds,
              COALESCE(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - MIN(enqueued_at) FILTER (
                WHERE queue_kind = 'external_effect' AND eligible
              ))), 0)::BIGINT AS external_effect_eligible_oldest_pending_age_seconds,
              COUNT(*) FILTER (WHERE queue_kind = 'external_effect' AND dlq)::BIGINT AS external_effect_terminal_count,
              COUNT(*) FILTER (WHERE queue_kind = 'external_effect' AND dlq)::BIGINT AS external_effect_dlq_count,

              COUNT(*) FILTER (WHERE queue_kind = 'broadcast' AND raw_open)::BIGINT AS broadcast_raw_open_count,
              COUNT(*) FILTER (WHERE queue_kind = 'broadcast' AND held)::BIGINT AS broadcast_held_count,
              COUNT(*) FILTER (WHERE queue_kind = 'broadcast' AND eligible)::BIGINT AS broadcast_eligible_count,
              COUNT(*) FILTER (WHERE queue_kind = 'broadcast' AND scheduled)::BIGINT AS broadcast_scheduled_count,
              COUNT(*) FILTER (WHERE queue_kind = 'broadcast' AND retry_wait)::BIGINT AS broadcast_retry_wait_count,
              0::BIGINT AS broadcast_rate_limited_count,
              COUNT(*) FILTER (WHERE queue_kind = 'broadcast' AND in_flight)::BIGINT AS broadcast_in_flight_count,
              COUNT(*) FILTER (WHERE queue_kind = 'broadcast' AND unknown)::BIGINT AS broadcast_unknown_count,
              COUNT(*) FILTER (WHERE queue_kind = 'broadcast' AND dlq)::BIGINT AS broadcast_dlq_count
            FROM queue_policy_rows
            """,
            params,
        ).fetchone()
        return {str(key): int(value or 0) for key, value in dict(row or {}).items()}

    def _execute(self, sql: str, params: dict[str, Any] | None = None):
        if self._connection is None:
            raise RuntimeError("readiness repository is not open")
        return self._connection.execute(sql, params) if params else self._connection.execute(sql)
