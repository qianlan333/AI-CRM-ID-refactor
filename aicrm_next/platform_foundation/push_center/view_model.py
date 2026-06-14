from __future__ import annotations

from typing import Any

from aicrm_next.platform_foundation.external_calls import scrub_summary
from aicrm_next.platform_foundation.external_effects.models import ExternalEffectAttempt, ExternalEffectJob

from . import ROUTE_OWNER
from .repository import PushCenterRepository, external_userid_for_job, owner_userid_for_job
from .section_mapper import label_for_section, section_for_job

FILTER_KEYS = (
    "section",
    "effect_type",
    "status",
    "business_type",
    "business_id",
    "target_type",
    "target_id",
    "external_userid",
    "owner_userid",
    "trace_id",
    "idempotency_key",
    "source_module",
    "source_route",
    "created_from",
    "created_to",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any, *, default: int, minimum: int = 0, maximum: int = 200) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(minimum, min(parsed, maximum))


def push_center_filters(params: dict[str, Any] | None = None) -> dict[str, str]:
    raw = dict(params or {})
    return {key: _text(raw.get(key)) for key in FILTER_KEYS}


def public_filters(filters: dict[str, Any]) -> dict[str, str]:
    return {key: _text(value) for key, value in filters.items() if _text(value)}


def _job_base(job: ExternalEffectJob) -> dict[str, Any]:
    section = section_for_job(job)
    return {
        "id": job.id,
        "source_type": "external_effect_job",
        "external_effect_job_missing": False,
        "section": section,
        "section_label": label_for_section(section),
        "effect_type": job.effect_type,
        "adapter_name": job.adapter_name,
        "operation": job.operation,
        "status": job.status,
        "execution_mode": job.execution_mode,
        "business_type": job.business_type,
        "business_id": job.business_id,
        "target_type": job.target_type,
        "target_id": job.target_id,
        "external_userid": external_userid_for_job(job),
        "owner_userid": owner_userid_for_job(job),
        "source_module": job.source_module,
        "source_route": job.source_route,
        "source_event_id": job.source_event_id,
        "source_command_id": job.source_command_id,
        "trace_id": job.trace_id,
        "request_id": job.request_id,
        "idempotency_key": job.idempotency_key,
        "actor_id": job.actor_id,
        "actor_type": job.actor_type,
        "risk_level": job.risk_level,
        "requires_approval": job.requires_approval,
        "attempt_count": job.attempt_count,
        "max_attempts": job.max_attempts,
        "last_attempt_id": job.last_attempt_id,
        "last_error_code": job.last_error_code,
        "last_error_message": job.last_error_message,
        "scheduled_at": job.scheduled_at,
        "next_retry_at": job.next_retry_at,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "executed_at": job.executed_at,
        "cancelled_at": job.cancelled_at,
        "payload_summary": scrub_summary(dict(job.payload_summary_json or {})),
        "payload_summary_json": scrub_summary(dict(job.payload_summary_json or {})),
    }


def job_list_item(job: ExternalEffectJob) -> dict[str, Any]:
    return _job_base(job)


def attempt_item(attempt: ExternalEffectAttempt) -> dict[str, Any]:
    return {
        "id": attempt.id,
        "attempt_id": attempt.attempt_id,
        "job_id": attempt.job_id,
        "adapter_name": attempt.adapter_name,
        "adapter_mode": attempt.adapter_mode,
        "operation": attempt.operation,
        "trace_id": attempt.trace_id,
        "request_id": attempt.request_id,
        "status": attempt.status,
        "request_summary": scrub_summary(dict(attempt.request_summary_json or {})),
        "request_summary_json": scrub_summary(dict(attempt.request_summary_json or {})),
        "response_summary": scrub_summary(dict(attempt.response_summary_json or {})),
        "response_summary_json": scrub_summary(dict(attempt.response_summary_json or {})),
        "error_code": attempt.error_code,
        "error_message": attempt.error_message,
        "started_at": attempt.started_at,
        "completed_at": attempt.completed_at,
    }


def build_sections_payload(params: dict[str, Any] | None = None, *, repository: PushCenterRepository | None = None) -> dict[str, Any]:
    repository = repository or PushCenterRepository()
    filters = push_center_filters(params)
    return {
        "ok": True,
        "sections": repository.sections(filters),
        "filters": public_filters(filters),
        "route_owner": ROUTE_OWNER,
    }


def build_jobs_payload(params: dict[str, Any] | None = None, *, repository: PushCenterRepository | None = None) -> dict[str, Any]:
    repository = repository or PushCenterRepository()
    filters = push_center_filters(params)
    limit = _int((params or {}).get("limit"), default=50, minimum=1, maximum=200)
    offset = _int((params or {}).get("offset"), default=0, minimum=0, maximum=100000)
    jobs, total = repository.list_jobs(filters, limit=limit, offset=offset)
    return {
        "ok": True,
        "items": [job_list_item(job) for job in jobs],
        "total": total,
        "counts": repository.counts(filters),
        "sections": repository.sections(filters),
        "filters": public_filters(filters),
        "limit": limit,
        "offset": offset,
        "route_owner": ROUTE_OWNER,
        "real_external_call_executed": False,
    }


def build_stats_payload(params: dict[str, Any] | None = None, *, repository: PushCenterRepository | None = None) -> dict[str, Any]:
    repository = repository or PushCenterRepository()
    filters = push_center_filters(params)
    return {
        "ok": True,
        "counts": repository.counts(filters),
        "sections": repository.sections(filters),
        "filters": public_filters(filters),
        "route_owner": ROUTE_OWNER,
        "real_external_call_executed": False,
    }


def build_job_detail_payload(job_id: int, *, repository: PushCenterRepository | None = None) -> dict[str, Any] | None:
    repository = repository or PushCenterRepository()
    job = repository.get_job(job_id)
    if not job:
        return None
    return {
        "ok": True,
        "job": _job_base(job),
        "attempts": [attempt_item(attempt) for attempt in repository.list_attempts(job_id)],
        "source": {
            "source_type": "external_effect_job",
            "external_effect_job_missing": False,
            "legacy_readonly": False,
        },
        "route_owner": ROUTE_OWNER,
        "real_external_call_executed": False,
    }
