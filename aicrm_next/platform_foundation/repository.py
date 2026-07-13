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

    def queue_metrics(self) -> dict[str, int]:
        row = self._execute(
            """
            SELECT
              (SELECT COUNT(*) FROM webhook_inbox
                 WHERE status IN ('received', 'processing', 'failed_retryable'))::BIGINT AS webhook_pending_count,
              (SELECT COALESCE(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - MIN(created_at))), 0)
                 FROM webhook_inbox
                 WHERE status IN ('received', 'processing', 'failed_retryable'))::BIGINT AS webhook_oldest_pending_age_seconds,
              (SELECT COUNT(*) FROM webhook_inbox WHERE status = 'dead_letter')::BIGINT AS webhook_dead_letter_count,
              (SELECT COUNT(*) FROM internal_event_consumer_run
                 WHERE status IN ('pending', 'running', 'failed_retryable'))::BIGINT AS internal_event_pending_count,
              (SELECT COALESCE(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - MIN(created_at))), 0)
                 FROM internal_event_consumer_run
                 WHERE status IN ('pending', 'running', 'failed_retryable'))::BIGINT AS internal_event_oldest_pending_age_seconds,
              (SELECT COUNT(*) FROM internal_event_consumer_run
                 WHERE status IN ('failed_terminal', 'blocked'))::BIGINT AS internal_event_terminal_count,
              (SELECT COUNT(*) FROM external_effect_job
                 WHERE status IN ('planned', 'approved', 'queued', 'dispatching', 'failed_retryable'))::BIGINT AS external_effect_pending_count,
              (SELECT COALESCE(EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - MIN(created_at))), 0)
                 FROM external_effect_job
                 WHERE status IN ('planned', 'approved', 'queued', 'dispatching', 'failed_retryable'))::BIGINT AS external_effect_oldest_pending_age_seconds,
              (SELECT COUNT(*) FROM external_effect_job
                 WHERE status IN ('failed_terminal', 'blocked'))::BIGINT AS external_effect_terminal_count
            """
        ).fetchone()
        return {str(key): int(value or 0) for key, value in dict(row or {}).items()}

    def _execute(self, sql: str):
        if self._connection is None:
            raise RuntimeError("readiness repository is not open")
        return self._connection.execute(sql)
