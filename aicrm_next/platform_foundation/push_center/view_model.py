from __future__ import annotations

from typing import Any

from . import ROUTE_OWNER
from .projection import EFFECTIVE_STATUS_LABELS
from .repository import PushCenterRepository
from .status_mapper import status_definitions_payload

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


def job_list_item(job: dict[str, Any]) -> dict[str, Any]:
    payload = dict(job)
    payload.setdefault("effective_status", payload.get("status"))
    payload.setdefault("effective_status_label", EFFECTIVE_STATUS_LABELS.get(_text(payload.get("effective_status")), _text(payload.get("status_label"))))
    payload.setdefault("status_label", payload.get("effective_status_label"))
    return payload


def build_sections_payload(params: dict[str, Any] | None = None, *, repository: PushCenterRepository | None = None) -> dict[str, Any]:
    repository = repository or PushCenterRepository()
    filters = push_center_filters(params)
    return {
        "ok": True,
        "sections": repository.sections(filters),
        "status_definitions": status_definitions_payload(),
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
        "status_definitions": status_definitions_payload(),
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
        "status_definitions": status_definitions_payload(),
        "filters": public_filters(filters),
        "route_owner": ROUTE_OWNER,
        "real_external_call_executed": False,
    }


def build_job_detail_payload(job_id: int | str, *, repository: PushCenterRepository | None = None) -> dict[str, Any] | None:
    repository = repository or PushCenterRepository()
    job = repository.get_job(job_id)
    if not job:
        return None
    job_payload = job_list_item(job)
    linked_records = job_payload.get("linked_records") if isinstance(job_payload.get("linked_records"), dict) else {}
    return {
        "ok": True,
        "job": job_payload,
        "attempts": list(linked_records.get("external_effect_attempts") or repository.list_attempts(job_id)),
        "linked_records": linked_records,
        "source": {
            "source_type": "push_center_projection",
            "external_effect_job_missing": False,
            "legacy_readonly": False,
        },
        "route_owner": ROUTE_OWNER,
        "real_external_call_executed": False,
    }
