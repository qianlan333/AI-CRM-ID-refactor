from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from aicrm_next.platform_foundation.external_calls import scrub_summary
from aicrm_next.shared.db_session import get_session_factory
from aicrm_next.shared.runtime import fixture_mode

from .models import (
    DEFAULT_TENANT_ID,
    ExternalEffectAttempt,
    ExternalEffectCreateRequest,
    ExternalEffectJob,
    public_datetime,
    utcnow,
)

_SENSITIVE_PAYLOAD_KEYS = {"token", "secret", "password", "authorization", "access_token", "refresh_token"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, default=str, separators=(",", ":"))


def _json_obj(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value:
        try:
            data = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(data) if isinstance(data, dict) else {}
    return {}


def _public_job(row: dict[str, Any] | None) -> ExternalEffectJob | None:
    if not row:
        return None
    payload = dict(row)
    for key in ("payload_json", "payload_summary_json"):
        payload[key] = _json_obj(payload.get(key))
    for key in (
        "scheduled_at",
        "next_retry_at",
        "locked_at",
        "created_at",
        "updated_at",
        "approved_at",
        "executed_at",
        "cancelled_at",
    ):
        payload[key] = public_datetime(payload.get(key))
    payload["id"] = int(payload.get("id") or 0)
    payload["priority"] = int(payload.get("priority") or 0)
    payload["attempt_count"] = int(payload.get("attempt_count") or 0)
    payload["max_attempts"] = int(payload.get("max_attempts") or 0)
    payload["requires_approval"] = bool(payload.get("requires_approval"))
    return ExternalEffectJob(**payload)


def _public_attempt(row: dict[str, Any] | None) -> ExternalEffectAttempt | None:
    if not row:
        return None
    payload = dict(row)
    for key in ("request_summary_json", "response_summary_json"):
        payload[key] = _json_obj(payload.get(key))
    for key in ("started_at", "completed_at"):
        payload[key] = public_datetime(payload.get(key))
    payload["id"] = int(payload.get("id") or 0)
    payload["job_id"] = int(payload.get("job_id") or 0)
    return ExternalEffectAttempt(**payload)


def _payload_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key, value in dict(payload or {}).items():
        if key.lower() in _SENSITIVE_PAYLOAD_KEYS:
            summary[key] = "[redacted]"
        elif isinstance(value, (str, int, float, bool)) or value is None:
            summary[key] = value
        else:
            summary[key] = type(value).__name__
    return summary


def _idempotency_key(request: ExternalEffectCreateRequest) -> str:
    explicit = _text(request.idempotency_key)
    if explicit:
        return explicit
    context_key = ":".join(
        item
        for item in (
            request.effect_type,
            request.target_type,
            request.target_id,
            request.business_type,
            request.business_id,
            request.source_command_id or request.context.request_id or request.context.trace_id,
        )
        if _text(item)
    )
    return context_key or f"{request.effect_type}:{request.target_type}:{request.target_id}"


class ExternalEffectRepository:
    def create_job(self, request: ExternalEffectCreateRequest) -> ExternalEffectJob:
        raise NotImplementedError

    def get_job(self, job_id: int) -> ExternalEffectJob | None:
        raise NotImplementedError

    def list_jobs(self, filters: dict[str, Any] | None = None, *, limit: int = 50, offset: int = 0) -> tuple[list[ExternalEffectJob], int]:
        raise NotImplementedError

    def list_attempts(self, job_id: int) -> list[ExternalEffectAttempt]:
        raise NotImplementedError

    def count_jobs(self, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        raise NotImplementedError

    def queue_metrics(self, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        raise NotImplementedError

    def list_due_jobs(self, *, limit: int = 50, effect_types: list[str] | None = None) -> list[ExternalEffectJob]:
        raise NotImplementedError

    def acquire_due_jobs(self, *, limit: int = 50, locked_by: str, effect_types: list[str] | None = None) -> list[ExternalEffectJob]:
        raise NotImplementedError

    def mark_dispatching(self, job_id: int, *, locked_by: str) -> ExternalEffectJob | None:
        raise NotImplementedError

    def mark_succeeded(self, job_id: int, *, attempt_id: str) -> ExternalEffectJob | None:
        raise NotImplementedError

    def mark_failed_retryable(self, job_id: int, *, attempt_id: str, error_code: str, error_message: str, next_retry_at: datetime) -> ExternalEffectJob | None:
        raise NotImplementedError

    def mark_failed_terminal(self, job_id: int, *, attempt_id: str, error_code: str, error_message: str) -> ExternalEffectJob | None:
        raise NotImplementedError

    def mark_blocked(self, job_id: int, *, attempt_id: str, error_code: str, error_message: str) -> ExternalEffectJob | None:
        raise NotImplementedError

    def cancel_job(self, job_id: int) -> ExternalEffectJob | None:
        raise NotImplementedError

    def enqueue_job(self, job_id: int) -> ExternalEffectJob | None:
        raise NotImplementedError

    def approve_job(self, job_id: int) -> ExternalEffectJob | None:
        raise NotImplementedError

    def record_attempt(self, *, job: ExternalEffectJob, status: str, adapter_mode: str, request_summary: dict[str, Any], response_summary: dict[str, Any], error_code: str = "", error_message: str = "") -> ExternalEffectAttempt:
        raise NotImplementedError


class SQLAlchemyExternalEffectRepository(ExternalEffectRepository):
    def __init__(self, session_factory: Callable[[], Session] | None = None):
        self._session_factory = session_factory or get_session_factory()

    def _one(self, statement: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        with self._session_factory() as session:
            row = session.execute(text(statement), params or {}).mappings().fetchone()
            return dict(row) if row else None

    def _all(self, statement: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            rows = session.execute(text(statement), params or {}).mappings().fetchall()
            return [dict(row) for row in rows]

    def _write_one(self, statement: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        with self._session_factory() as session:
            row = session.execute(text(statement), params or {}).mappings().fetchone()
            session.commit()
            return dict(row) if row else None

    def _write_all(self, statement: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            rows = session.execute(text(statement), params or {}).mappings().fetchall()
            session.commit()
            return [dict(row) for row in rows]

    def create_job(self, request: ExternalEffectCreateRequest) -> ExternalEffectJob:
        key = _idempotency_key(request)
        scheduled_at = request.scheduled_at or utcnow()
        payload_summary = dict(request.payload_summary or {}) or _payload_summary(request.payload)
        row = self._write_one(
            """
            INSERT INTO external_effect_job (
                tenant_id, effect_type, adapter_name, operation, target_type, target_id,
                business_type, business_id, source_module, source_route, source_event_id,
                source_command_id, trace_id, request_id, correlation_id, idempotency_key,
                actor_id, actor_type, risk_level, requires_approval, execution_mode,
                payload_json, payload_summary_json, status, priority, scheduled_at,
                attempt_count, max_attempts, created_at, updated_at
            )
            VALUES (
                :tenant_id, :effect_type, :adapter_name, :operation, :target_type, :target_id,
                :business_type, :business_id, :source_module, :source_route, :source_event_id,
                :source_command_id, :trace_id, :request_id, :correlation_id, :idempotency_key,
                :actor_id, :actor_type, :risk_level, :requires_approval, :execution_mode,
                CAST(:payload_json AS jsonb), CAST(:payload_summary_json AS jsonb), :status,
                :priority, CAST(:scheduled_at AS timestamptz), 0, :max_attempts,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
            RETURNING *
            """,
            {
                "tenant_id": _text(request.tenant_id) or DEFAULT_TENANT_ID,
                "effect_type": _text(request.effect_type),
                "adapter_name": _text(request.adapter_name),
                "operation": _text(request.operation),
                "target_type": _text(request.target_type),
                "target_id": _text(request.target_id),
                "business_type": _text(request.business_type),
                "business_id": _text(request.business_id),
                "source_module": _text(request.source_module),
                "source_route": _text(request.context.source_route),
                "source_event_id": _text(request.source_event_id),
                "source_command_id": _text(request.source_command_id),
                "trace_id": _text(request.context.trace_id),
                "request_id": _text(request.context.request_id),
                "correlation_id": _text(request.correlation_id),
                "idempotency_key": key,
                "actor_id": _text(request.context.actor_id),
                "actor_type": _text(request.context.actor_type) or "system",
                "risk_level": _text(request.risk_level) or "medium",
                "requires_approval": bool(request.requires_approval),
                "execution_mode": _text(request.execution_mode) or "shadow",
                "payload_json": _json_dumps(request.payload),
                "payload_summary_json": _json_dumps(payload_summary),
                "status": _text(request.status) or "planned",
                "priority": int(request.priority or 100),
                "scheduled_at": public_datetime(scheduled_at),
                "max_attempts": int(request.max_attempts or 5),
            },
        )
        if row:
            job = _public_job(row)
            assert job is not None
            return job
        existing = self._one(
            "SELECT * FROM external_effect_job WHERE tenant_id = :tenant_id AND idempotency_key = :idempotency_key LIMIT 1",
            {"tenant_id": _text(request.tenant_id) or DEFAULT_TENANT_ID, "idempotency_key": key},
        )
        job = _public_job(existing)
        if job is None:
            raise RuntimeError("external effect idempotent create failed")
        return job

    def get_job(self, job_id: int) -> ExternalEffectJob | None:
        return _public_job(self._one("SELECT * FROM external_effect_job WHERE id = :job_id LIMIT 1", {"job_id": int(job_id)}))

    def list_jobs(self, filters: dict[str, Any] | None = None, *, limit: int = 50, offset: int = 0) -> tuple[list[ExternalEffectJob], int]:
        filters = dict(filters or {})
        clauses: list[str] = []
        params: dict[str, Any] = {}
        for key in ("effect_type", "status", "target_type", "target_id", "business_type", "business_id", "trace_id"):
            value = _text(filters.get(key))
            if value:
                clauses.append(f"{key} = :{key}")
                params[key] = value
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        count_row = self._one(f"SELECT COUNT(*) AS total FROM external_effect_job {where}", params)
        rows = self._all(
            f"""
            SELECT *
            FROM external_effect_job
            {where}
            ORDER BY created_at DESC, id DESC
            LIMIT :limit OFFSET :offset
            """,
            {**params, "limit": max(1, min(int(limit or 50), 200)), "offset": max(0, int(offset or 0))},
        )
        return [job for row in rows if (job := _public_job(row)) is not None], int((count_row or {}).get("total") or 0)

    def list_attempts(self, job_id: int) -> list[ExternalEffectAttempt]:
        rows = self._all(
            "SELECT * FROM external_effect_attempt WHERE job_id = :job_id ORDER BY id ASC",
            {"job_id": int(job_id)},
        )
        return [attempt for row in rows if (attempt := _public_attempt(row)) is not None]

    def count_jobs(self, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        filters = dict(filters or {})
        clauses: list[str] = []
        params: dict[str, Any] = {}
        for key in ("effect_type", "status", "target_type", "target_id", "business_type", "business_id", "trace_id"):
            value = _text(filters.get(key))
            if value:
                clauses.append(f"{key} = :{key}")
                params[key] = value
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        rows = self._all(
            f"""
            SELECT status, COUNT(*) AS count
            FROM external_effect_job
            {where}
            GROUP BY status
            """,
            params,
        )
        by_status = {_text(row.get("status")): int(row.get("count") or 0) for row in rows}
        total = sum(by_status.values())
        return {
            "total": total,
            "by_status": by_status,
            "planned": by_status.get("planned", 0),
            "queued": by_status.get("queued", 0),
            "blocked": by_status.get("blocked", 0),
            "failed": by_status.get("failed_retryable", 0) + by_status.get("failed_terminal", 0),
            "succeeded": by_status.get("succeeded", 0),
            "cancelled": by_status.get("cancelled", 0),
        }

    def queue_metrics(self, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        filters = dict(filters or {})
        clauses: list[str] = []
        params: dict[str, Any] = {}
        for key in ("effect_type", "status", "target_type", "target_id", "business_type", "business_id", "trace_id"):
            value = _text(filters.get(key))
            if value:
                clauses.append(f"{key} = :{key}")
                params[key] = value
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        row = self._one(
            f"""
            SELECT
                COUNT(*) FILTER (
                    WHERE status IN ('queued', 'failed_retryable')
                      AND scheduled_at <= CURRENT_TIMESTAMP
                      AND (next_retry_at IS NULL OR next_retry_at <= CURRENT_TIMESTAMP)
                      AND (locked_at IS NULL OR locked_at <= CURRENT_TIMESTAMP - INTERVAL '5 minutes')
                ) AS eligible_due_count,
                COUNT(*) FILTER (WHERE status = 'dispatching') AS dispatching_count,
                COUNT(*) FILTER (WHERE status = 'failed_retryable') AS failed_retryable_count,
                COUNT(*) FILTER (WHERE status = 'failed_terminal') AS failed_terminal_count,
                COALESCE(
                    EXTRACT(EPOCH FROM CURRENT_TIMESTAMP - MIN(scheduled_at) FILTER (
                        WHERE status = 'queued' AND scheduled_at <= CURRENT_TIMESTAMP
                    )),
                    0
                ) AS oldest_queued_age_seconds,
                COALESCE(
                    EXTRACT(EPOCH FROM CURRENT_TIMESTAMP - MIN(COALESCE(next_retry_at, scheduled_at)) FILTER (
                        WHERE status = 'failed_retryable'
                          AND scheduled_at <= CURRENT_TIMESTAMP
                          AND (next_retry_at IS NULL OR next_retry_at <= CURRENT_TIMESTAMP)
                    )),
                    0
                ) AS oldest_failed_retryable_age_seconds
            FROM external_effect_job
            {where}
            """,
            params,
        ) or {}
        return {
            "eligible_due_count": int(row.get("eligible_due_count") or 0),
            "dispatching_count": int(row.get("dispatching_count") or 0),
            "failed_retryable_count": int(row.get("failed_retryable_count") or 0),
            "failed_terminal_count": int(row.get("failed_terminal_count") or 0),
            "oldest_queued_age_seconds": int(float(row.get("oldest_queued_age_seconds") or 0)),
            "oldest_failed_retryable_age_seconds": int(float(row.get("oldest_failed_retryable_age_seconds") or 0)),
        }

    def list_due_jobs(self, *, limit: int = 50, effect_types: list[str] | None = None) -> list[ExternalEffectJob]:
        type_filter = "AND effect_type = ANY(:effect_types)" if effect_types else ""
        params: dict[str, Any] = {"limit": max(1, min(int(limit or 50), 200))}
        if effect_types:
            params["effect_types"] = [_text(item) for item in effect_types if _text(item)]
        rows = self._all(
            f"""
            SELECT *
            FROM external_effect_job
            WHERE status IN ('queued', 'failed_retryable')
              AND scheduled_at <= CURRENT_TIMESTAMP
              AND (next_retry_at IS NULL OR next_retry_at <= CURRENT_TIMESTAMP)
              AND (locked_at IS NULL OR locked_at <= CURRENT_TIMESTAMP - INTERVAL '5 minutes')
              {type_filter}
            ORDER BY priority ASC, scheduled_at ASC, id ASC
            LIMIT :limit
            """,
            params,
        )
        return [job for row in rows if (job := _public_job(row)) is not None]

    def acquire_due_jobs(self, *, limit: int = 50, locked_by: str, effect_types: list[str] | None = None) -> list[ExternalEffectJob]:
        type_filter = "AND effect_type = ANY(:effect_types)" if effect_types else ""
        params: dict[str, Any] = {"limit": max(1, min(int(limit or 50), 200)), "locked_by": _text(locked_by)}
        if effect_types:
            params["effect_types"] = [_text(item) for item in effect_types if _text(item)]
        rows = self._write_all(
            f"""
            WITH due AS (
                SELECT id
                FROM external_effect_job
                WHERE status IN ('queued', 'failed_retryable')
                  AND scheduled_at <= CURRENT_TIMESTAMP
                  AND (next_retry_at IS NULL OR next_retry_at <= CURRENT_TIMESTAMP)
                  AND (locked_at IS NULL OR locked_at <= CURRENT_TIMESTAMP - INTERVAL '5 minutes')
                  {type_filter}
                ORDER BY priority ASC, scheduled_at ASC, id ASC
                LIMIT :limit
                FOR UPDATE SKIP LOCKED
            )
            UPDATE external_effect_job j
            SET locked_at = CURRENT_TIMESTAMP,
                locked_by = :locked_by,
                updated_at = CURRENT_TIMESTAMP
            FROM due
            WHERE j.id = due.id
            RETURNING j.*
            """,
            params,
        )
        return [job for row in rows if (job := _public_job(row)) is not None]

    def mark_dispatching(self, job_id: int, *, locked_by: str) -> ExternalEffectJob | None:
        return self._update(job_id, "status = 'dispatching', locked_by = :locked_by, locked_at = CURRENT_TIMESTAMP", {"locked_by": _text(locked_by)})

    def mark_succeeded(self, job_id: int, *, attempt_id: str) -> ExternalEffectJob | None:
        return self._update(
            job_id,
            "status = 'succeeded', last_attempt_id = :attempt_id, locked_by = '', locked_at = NULL, executed_at = CURRENT_TIMESTAMP",
            {"attempt_id": _text(attempt_id)},
        )

    def mark_failed_retryable(self, job_id: int, *, attempt_id: str, error_code: str, error_message: str, next_retry_at: datetime) -> ExternalEffectJob | None:
        return self._update(
            job_id,
            "status = 'failed_retryable', attempt_count = attempt_count + 1, next_retry_at = CAST(:next_retry_at AS timestamptz), last_attempt_id = :attempt_id, last_error_code = :error_code, last_error_message = :error_message, locked_by = '', locked_at = NULL",
            {
                "attempt_id": _text(attempt_id),
                "error_code": _text(error_code),
                "error_message": _text(error_message),
                "next_retry_at": public_datetime(next_retry_at),
            },
        )

    def mark_failed_terminal(self, job_id: int, *, attempt_id: str, error_code: str, error_message: str) -> ExternalEffectJob | None:
        return self._update(
            job_id,
            "status = 'failed_terminal', attempt_count = attempt_count + 1, last_attempt_id = :attempt_id, last_error_code = :error_code, last_error_message = :error_message, locked_by = '', locked_at = NULL",
            {"attempt_id": _text(attempt_id), "error_code": _text(error_code), "error_message": _text(error_message)},
        )

    def mark_blocked(self, job_id: int, *, attempt_id: str, error_code: str, error_message: str) -> ExternalEffectJob | None:
        return self._update(
            job_id,
            "status = 'blocked', attempt_count = attempt_count + 1, last_attempt_id = :attempt_id, last_error_code = :error_code, last_error_message = :error_message, locked_by = '', locked_at = NULL",
            {"attempt_id": _text(attempt_id), "error_code": _text(error_code), "error_message": _text(error_message)},
        )

    def cancel_job(self, job_id: int) -> ExternalEffectJob | None:
        return self._update(job_id, "status = 'cancelled', locked_by = '', locked_at = NULL, cancelled_at = CURRENT_TIMESTAMP", {})

    def enqueue_job(self, job_id: int) -> ExternalEffectJob | None:
        return self._update(job_id, "status = 'queued', locked_by = '', locked_at = NULL, next_retry_at = CURRENT_TIMESTAMP", {})

    def approve_job(self, job_id: int) -> ExternalEffectJob | None:
        return self._update(job_id, "status = 'approved', approved_at = CURRENT_TIMESTAMP", {})

    def record_attempt(self, *, job: ExternalEffectJob, status: str, adapter_mode: str, request_summary: dict[str, Any], response_summary: dict[str, Any], error_code: str = "", error_message: str = "") -> ExternalEffectAttempt:
        attempt_id = "eea_" + __import__("uuid").uuid4().hex
        row = self._write_one(
            """
            INSERT INTO external_effect_attempt (
                attempt_id, job_id, adapter_name, adapter_mode, operation, trace_id,
                request_id, status, request_summary_json, response_summary_json,
                error_code, error_message, started_at, completed_at
            )
            VALUES (
                :attempt_id, :job_id, :adapter_name, :adapter_mode, :operation, :trace_id,
                :request_id, :status, CAST(:request_summary AS jsonb), CAST(:response_summary AS jsonb),
                :error_code, :error_message, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            RETURNING *
            """,
            {
                "attempt_id": attempt_id,
                "job_id": int(job.id),
                "adapter_name": job.adapter_name,
                "adapter_mode": _text(adapter_mode) or "none",
                "operation": job.operation,
                "trace_id": job.trace_id,
                "request_id": job.request_id,
                "status": _text(status) or "skipped",
                "request_summary": _json_dumps(scrub_summary(request_summary or {})),
                "response_summary": _json_dumps(scrub_summary(response_summary or {})),
                "error_code": _text(error_code),
                "error_message": _text(error_message),
            },
        )
        attempt = _public_attempt(row)
        if attempt is None:
            raise RuntimeError("external effect attempt insert failed")
        return attempt

    def _update(self, job_id: int, set_sql: str, params: dict[str, Any]) -> ExternalEffectJob | None:
        row = self._write_one(
            f"""
            UPDATE external_effect_job
            SET {set_sql},
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :job_id
            RETURNING *
            """,
            {**params, "job_id": int(job_id)},
        )
        return _public_job(row)


class InMemoryExternalEffectRepository(ExternalEffectRepository):
    def __init__(self) -> None:
        self._jobs: list[dict[str, Any]] = []
        self._attempts: list[dict[str, Any]] = []
        self._next_id = 1
        self._next_attempt_id = 1

    def create_job(self, request: ExternalEffectCreateRequest) -> ExternalEffectJob:
        key = _idempotency_key(request)
        tenant_id = _text(request.tenant_id) or DEFAULT_TENANT_ID
        for row in self._jobs:
            if row["tenant_id"] == tenant_id and row["idempotency_key"] == key:
                job = _public_job(row)
                assert job is not None
                return job
        now = utcnow()
        payload_summary = dict(request.payload_summary or {}) or _payload_summary(request.payload)
        row = {
            "id": self._next_id,
            "tenant_id": tenant_id,
            "effect_type": _text(request.effect_type),
            "adapter_name": _text(request.adapter_name),
            "operation": _text(request.operation),
            "target_type": _text(request.target_type),
            "target_id": _text(request.target_id),
            "business_type": _text(request.business_type),
            "business_id": _text(request.business_id),
            "source_module": _text(request.source_module),
            "source_route": _text(request.context.source_route),
            "source_event_id": _text(request.source_event_id),
            "source_command_id": _text(request.source_command_id),
            "trace_id": _text(request.context.trace_id),
            "request_id": _text(request.context.request_id),
            "correlation_id": _text(request.correlation_id),
            "idempotency_key": key,
            "actor_id": _text(request.context.actor_id),
            "actor_type": _text(request.context.actor_type) or "system",
            "risk_level": _text(request.risk_level) or "medium",
            "requires_approval": bool(request.requires_approval),
            "execution_mode": _text(request.execution_mode) or "shadow",
            "payload_json": dict(request.payload or {}),
            "payload_summary_json": payload_summary,
            "status": _text(request.status) or "planned",
            "priority": int(request.priority or 100),
            "scheduled_at": public_datetime(request.scheduled_at or now),
            "attempt_count": 0,
            "max_attempts": int(request.max_attempts or 5),
            "next_retry_at": "",
            "locked_at": "",
            "locked_by": "",
            "last_attempt_id": "",
            "last_error_code": "",
            "last_error_message": "",
            "created_at": public_datetime(now),
            "updated_at": public_datetime(now),
            "approved_at": "",
            "executed_at": "",
            "cancelled_at": "",
        }
        self._next_id += 1
        self._jobs.append(row)
        job = _public_job(row)
        assert job is not None
        return job

    def get_job(self, job_id: int) -> ExternalEffectJob | None:
        return _public_job(self._find(job_id))

    def list_jobs(self, filters: dict[str, Any] | None = None, *, limit: int = 50, offset: int = 0) -> tuple[list[ExternalEffectJob], int]:
        filters = dict(filters or {})
        rows = list(self._jobs)
        for key in ("effect_type", "status", "target_type", "target_id", "business_type", "business_id", "trace_id"):
            value = _text(filters.get(key))
            if value:
                rows = [row for row in rows if _text(row.get(key)) == value]
        rows.sort(key=lambda row: (row.get("created_at") or "", int(row.get("id") or 0)), reverse=True)
        total = len(rows)
        window = rows[max(0, int(offset or 0)) : max(0, int(offset or 0)) + max(1, min(int(limit or 50), 200))]
        return [job for row in window if (job := _public_job(row)) is not None], total

    def list_attempts(self, job_id: int) -> list[ExternalEffectAttempt]:
        return [
            attempt
            for row in self._attempts
            if int(row.get("job_id") or 0) == int(job_id)
            if (attempt := _public_attempt(row)) is not None
        ]

    def count_jobs(self, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        items = [job for row in self._filtered_rows(filters or {}) if (job := _public_job(row)) is not None]
        by_status: dict[str, int] = {}
        for item in items:
            by_status[item.status] = by_status.get(item.status, 0) + 1
        total = sum(by_status.values())
        return {
            "total": total,
            "by_status": by_status,
            "planned": by_status.get("planned", 0),
            "queued": by_status.get("queued", 0),
            "blocked": by_status.get("blocked", 0),
            "failed": by_status.get("failed_retryable", 0) + by_status.get("failed_terminal", 0),
            "succeeded": by_status.get("succeeded", 0),
            "cancelled": by_status.get("cancelled", 0),
        }

    def queue_metrics(self, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        now = utcnow()
        rows = self._filtered_rows(filters or {})
        due_rows = [
            row
            for row in rows
            if row.get("status") in {"queued", "failed_retryable"}
            and self._dt(row.get("scheduled_at")) <= now
            and (not row.get("next_retry_at") or self._dt(row.get("next_retry_at")) <= now)
            and (not row.get("locked_at") or self._dt(row.get("locked_at")) <= now - timedelta(minutes=5))
        ]
        queued_due = [row for row in due_rows if row.get("status") == "queued"]
        retry_due = [row for row in due_rows if row.get("status") == "failed_retryable"]
        return {
            "eligible_due_count": len(due_rows),
            "dispatching_count": len([row for row in rows if row.get("status") == "dispatching"]),
            "failed_retryable_count": len([row for row in rows if row.get("status") == "failed_retryable"]),
            "failed_terminal_count": len([row for row in rows if row.get("status") == "failed_terminal"]),
            "oldest_queued_age_seconds": self._oldest_age_seconds(queued_due, now, "scheduled_at"),
            "oldest_failed_retryable_age_seconds": self._oldest_age_seconds(retry_due, now, "next_retry_at", fallback_key="scheduled_at"),
        }

    def list_due_jobs(self, *, limit: int = 50, effect_types: list[str] | None = None) -> list[ExternalEffectJob]:
        now = utcnow()
        type_set = {_text(item) for item in effect_types or [] if _text(item)}
        rows = [
            row
            for row in self._jobs
            if row.get("status") in {"queued", "failed_retryable"}
            and (not type_set or row.get("effect_type") in type_set)
            and self._dt(row.get("scheduled_at")) <= now
            and (not row.get("next_retry_at") or self._dt(row.get("next_retry_at")) <= now)
            and (not row.get("locked_at") or self._dt(row.get("locked_at")) <= now - timedelta(minutes=5))
        ]
        rows.sort(key=lambda row: (int(row.get("priority") or 100), row.get("scheduled_at") or "", int(row.get("id") or 0)))
        return [job for row in rows[: max(1, min(int(limit or 50), 200))] if (job := _public_job(row)) is not None]

    def acquire_due_jobs(self, *, limit: int = 50, locked_by: str, effect_types: list[str] | None = None) -> list[ExternalEffectJob]:
        jobs = self.list_due_jobs(limit=limit, effect_types=effect_types)
        now = public_datetime(utcnow())
        for job in jobs:
            row = self._find(job.id)
            if row:
                row["locked_at"] = now
                row["locked_by"] = _text(locked_by)
                row["updated_at"] = now
        return [job for job_id in [job.id for job in jobs] if (job := self.get_job(job_id)) is not None]

    def mark_dispatching(self, job_id: int, *, locked_by: str) -> ExternalEffectJob | None:
        return self._mutate(job_id, status="dispatching", locked_by=_text(locked_by), locked_at=public_datetime(utcnow()))

    def mark_succeeded(self, job_id: int, *, attempt_id: str) -> ExternalEffectJob | None:
        return self._mutate(job_id, status="succeeded", last_attempt_id=_text(attempt_id), locked_by="", locked_at="", executed_at=public_datetime(utcnow()))

    def mark_failed_retryable(self, job_id: int, *, attempt_id: str, error_code: str, error_message: str, next_retry_at: datetime) -> ExternalEffectJob | None:
        row = self._find(job_id)
        if row:
            row["attempt_count"] = int(row.get("attempt_count") or 0) + 1
        return self._mutate(job_id, status="failed_retryable", next_retry_at=public_datetime(next_retry_at), last_attempt_id=_text(attempt_id), last_error_code=_text(error_code), last_error_message=_text(error_message), locked_by="", locked_at="")

    def mark_failed_terminal(self, job_id: int, *, attempt_id: str, error_code: str, error_message: str) -> ExternalEffectJob | None:
        row = self._find(job_id)
        if row:
            row["attempt_count"] = int(row.get("attempt_count") or 0) + 1
        return self._mutate(job_id, status="failed_terminal", last_attempt_id=_text(attempt_id), last_error_code=_text(error_code), last_error_message=_text(error_message), locked_by="", locked_at="")

    def mark_blocked(self, job_id: int, *, attempt_id: str, error_code: str, error_message: str) -> ExternalEffectJob | None:
        row = self._find(job_id)
        if row:
            row["attempt_count"] = int(row.get("attempt_count") or 0) + 1
        return self._mutate(job_id, status="blocked", last_attempt_id=_text(attempt_id), last_error_code=_text(error_code), last_error_message=_text(error_message), locked_by="", locked_at="")

    def cancel_job(self, job_id: int) -> ExternalEffectJob | None:
        return self._mutate(job_id, status="cancelled", locked_by="", locked_at="", cancelled_at=public_datetime(utcnow()))

    def enqueue_job(self, job_id: int) -> ExternalEffectJob | None:
        return self._mutate(job_id, status="queued", locked_by="", locked_at="", next_retry_at=public_datetime(utcnow()))

    def approve_job(self, job_id: int) -> ExternalEffectJob | None:
        return self._mutate(job_id, status="approved", approved_at=public_datetime(utcnow()))

    def record_attempt(self, *, job: ExternalEffectJob, status: str, adapter_mode: str, request_summary: dict[str, Any], response_summary: dict[str, Any], error_code: str = "", error_message: str = "") -> ExternalEffectAttempt:
        now = public_datetime(utcnow())
        row = {
            "id": self._next_attempt_id,
            "attempt_id": "eea_" + __import__("uuid").uuid4().hex,
            "job_id": int(job.id),
            "adapter_name": job.adapter_name,
            "adapter_mode": _text(adapter_mode) or "none",
            "operation": job.operation,
            "trace_id": job.trace_id,
            "request_id": job.request_id,
            "status": _text(status) or "skipped",
            "request_summary_json": scrub_summary(request_summary or {}),
            "response_summary_json": scrub_summary(response_summary or {}),
            "error_code": _text(error_code),
            "error_message": _text(error_message),
            "started_at": now,
            "completed_at": now,
        }
        self._next_attempt_id += 1
        self._attempts.append(row)
        attempt = _public_attempt(row)
        assert attempt is not None
        return attempt

    def _find(self, job_id: int) -> dict[str, Any] | None:
        for row in self._jobs:
            if int(row.get("id") or 0) == int(job_id):
                return row
        return None

    def _filtered_rows(self, filters: dict[str, Any]) -> list[dict[str, Any]]:
        rows = list(self._jobs)
        for key in ("effect_type", "status", "target_type", "target_id", "business_type", "business_id", "trace_id"):
            value = _text(filters.get(key))
            if value:
                rows = [row for row in rows if _text(row.get(key)) == value]
        return rows

    def _mutate(self, job_id: int, **changes: Any) -> ExternalEffectJob | None:
        row = self._find(job_id)
        if not row:
            return None
        row.update(changes)
        row["updated_at"] = public_datetime(utcnow())
        return _public_job(row)

    def _dt(self, value: Any) -> datetime:
        text_value = _text(value)
        if not text_value:
            return datetime.min.replace(tzinfo=timezone.utc)
        dt = datetime.fromisoformat(text_value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    def _oldest_age_seconds(self, rows: list[dict[str, Any]], now: datetime, key: str, *, fallback_key: str = "") -> int:
        if not rows:
            return 0
        oldest = min(self._dt(row.get(key) or row.get(fallback_key)) for row in rows)
        return max(0, int((now - oldest).total_seconds()))


_fixture_repo = InMemoryExternalEffectRepository()


def reset_external_effect_fixture_state() -> None:
    global _fixture_repo
    _fixture_repo = InMemoryExternalEffectRepository()


def build_external_effect_repository() -> ExternalEffectRepository:
    if fixture_mode():
        return _fixture_repo
    return SQLAlchemyExternalEffectRepository()
