from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from aicrm_next.platform_foundation.external_effects.models import ExternalEffectAttempt, ExternalEffectJob
from aicrm_next.platform_foundation.external_effects.service import ExternalEffectService

from .section_mapper import all_sections, effect_types_for_section, label_for_section, section_for_job


def _text(value: Any) -> str:
    return str(value or "").strip()


def _lower(value: Any) -> str:
    return _text(value).lower()


def _dt(value: Any) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _payload(job: ExternalEffectJob) -> dict[str, Any]:
    return dict(job.payload_json or {})


def _summary(job: ExternalEffectJob) -> dict[str, Any]:
    return dict(job.payload_summary_json or {})


def external_userid_for_job(job: ExternalEffectJob) -> str:
    if job.target_type in {"external_user", "external_userid", "wecom_external_user"}:
        return _text(job.target_id)
    summary = _summary(job)
    payload = _payload(job)
    for source in (summary, payload):
        value = _text(source.get("external_userid") or source.get("external_user_id"))
        if value:
            return value
        values = source.get("external_userids")
        if isinstance(values, list) and values:
            return _text(values[0])
    return ""


def owner_userid_for_job(job: ExternalEffectJob) -> str:
    summary = _summary(job)
    payload = _payload(job)
    for source in (summary, payload):
        value = _text(source.get("owner_userid") or source.get("sender") or source.get("operator_member_id"))
        if value:
            return value
    return _text(job.actor_id)


def _matches_text(value: Any, expected: Any) -> bool:
    expected_text = _text(expected)
    if not expected_text:
        return True
    return _text(value) == expected_text


def _contains_text(value: Any, expected: Any) -> bool:
    expected_text = _lower(expected)
    if not expected_text:
        return True
    if isinstance(value, list):
        return any(_lower(item) == expected_text for item in value)
    return expected_text in _lower(value)


def _matches_created(job: ExternalEffectJob, filters: dict[str, Any]) -> bool:
    created_at = _dt(job.created_at)
    if created_at is None:
        return True
    created_from = _dt(filters.get("created_from"))
    created_to = _dt(filters.get("created_to"))
    if created_from and created_at < created_from:
        return False
    if created_to and created_at > created_to:
        return False
    return True


def _matches_job(job: ExternalEffectJob, filters: dict[str, Any]) -> bool:
    if _text(filters.get("section")) and section_for_job(job) != _text(filters.get("section")):
        return False
    section_types = set(effect_types_for_section(_text(filters.get("section"))))
    if section_types and job.effect_type not in section_types:
        return False
    for key in (
        "effect_type",
        "status",
        "business_type",
        "business_id",
        "target_type",
        "target_id",
        "trace_id",
        "idempotency_key",
        "source_module",
        "source_route",
    ):
        if not _matches_text(getattr(job, key), filters.get(key)):
            return False
    if not _matches_text(external_userid_for_job(job), filters.get("external_userid")):
        return False
    if not _matches_text(owner_userid_for_job(job), filters.get("owner_userid")):
        return False
    if not _matches_created(job, filters):
        return False
    return True


class PushCenterRepository:
    def __init__(self, service: ExternalEffectService | None = None) -> None:
        self._service = service or ExternalEffectService()

    def list_jobs(self, filters: dict[str, Any] | None = None, *, limit: int = 50, offset: int = 0) -> tuple[list[ExternalEffectJob], int]:
        filters = dict(filters or {})
        # The push center is a read model over external_effect_job. Fetch a bounded
        # window from the queue repository, then apply cross-field section and
        # payload-summary filters without exposing payload_json to callers.
        base_filters = {
            key: filters.get(key)
            for key in ("effect_type", "status", "business_type", "business_id", "target_type", "target_id", "trace_id")
            if _text(filters.get(key))
        }
        candidates, _total = self._service.list_jobs(base_filters, limit=1000, offset=0)
        matched = [job for job in candidates if _matches_job(job, filters)]
        start = max(0, int(offset or 0))
        size = max(1, min(int(limit or 50), 200))
        return matched[start : start + size], len(matched)

    def get_job(self, job_id: int) -> ExternalEffectJob | None:
        return self._service.get(job_id)

    def list_attempts(self, job_id: int) -> list[ExternalEffectAttempt]:
        return list(self._service.list_attempts(job_id))

    def counts(self, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        jobs, total = self.list_jobs(filters or {}, limit=1000, offset=0)
        by_status: dict[str, int] = {}
        by_section: dict[str, int] = {}
        for job in jobs:
            by_status[job.status] = by_status.get(job.status, 0) + 1
            section = section_for_job(job)
            by_section[section] = by_section.get(section, 0) + 1
        return {
            "total": total,
            "by_status": by_status,
            "by_section": by_section,
            "queued": by_status.get("queued", 0),
            "planned": by_status.get("planned", 0),
            "succeeded": by_status.get("succeeded", 0),
            "blocked": by_status.get("blocked", 0),
            "failed": by_status.get("failed_retryable", 0) + by_status.get("failed_terminal", 0),
            "cancelled": by_status.get("cancelled", 0),
        }

    def sections(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        counts = self.counts(filters or {}).get("by_section", {})
        return [
            {
                **section,
                "count": int(counts.get(section["key"], 0)),
                "label": label_for_section(section["key"]),
            }
            for section in all_sections()
        ]
