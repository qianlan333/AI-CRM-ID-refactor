from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from aicrm_next.platform_foundation.push_center.capability_registry import capability_for_section
from aicrm_next.platform_foundation.push_center.section_mapper import section_for_job
from aicrm_next.shared.runtime_settings import runtime_bool, runtime_setting

from .adapters import DEFAULT_ADAPTER_REGISTRY, ExternalEffectAdapterRegistry
from .models import (
    WECOM_CONTACT_TAG_MARK,
    WECOM_CONTACT_TAG_UNMARK,
    WECOM_MESSAGE_GROUP_SEND,
    WECOM_MESSAGE_PRIVATE_SEND,
    WECOM_PROFILE_UPDATE,
    WECOM_WELCOME_MESSAGE_SEND,
    ExternalEffectJob,
)
from .repo import ExternalEffectRepository, build_external_effect_repository
from .retry_policy import next_retry_at, status_for_failure

LOGGER = logging.getLogger(__name__)
WECOM_EFFECT_TYPES = frozenset(
    {
        WECOM_CONTACT_TAG_MARK,
        WECOM_CONTACT_TAG_UNMARK,
        WECOM_MESSAGE_GROUP_SEND,
        WECOM_MESSAGE_PRIVATE_SEND,
        WECOM_PROFILE_UPDATE,
        WECOM_WELCOME_MESSAGE_SEND,
    }
)


def _enabled(name: str) -> bool:
    return runtime_bool(name)


def _is_test_job(job: ExternalEffectJob) -> bool:
    payload = dict(job.payload_json or {})
    return payload.get("execution_scope") == "test_loopback" or payload.get("is_test") is True


def _capability_gate_error(job: ExternalEffectJob) -> str:
    if job.effect_type in WECOM_EFFECT_TYPES:
        return ""
    capability = capability_for_section(section_for_job(job))
    if capability is None:
        return ""
    if not capability.supports_real_execution:
        return "push_capability_readonly"
    if not capability.toggleable:
        return ""
    value = runtime_setting(capability.setting_key, "__aicrm_missing__")
    if value == "__aicrm_missing__":
        return ""
    if str(value or "").strip().lower() not in {"1", "true", "yes", "y", "on"}:
        return "push_capability_disabled"
    return ""


class ExternalEffectWorker:
    def __init__(
        self,
        repository: ExternalEffectRepository | None = None,
        adapter_registry: ExternalEffectAdapterRegistry | None = None,
        *,
        locked_by: str = "",
    ):
        self._repo = repository or build_external_effect_repository()
        self._adapters = adapter_registry or DEFAULT_ADAPTER_REGISTRY
        self._locked_by = locked_by or f"external-effect-worker-{uuid4().hex[:8]}"

    def preview_due(self, *, batch_size: int = 10, effect_types: list[str] | None = None, test_only: bool = False) -> dict[str, Any]:
        jobs = self._repo.list_due_jobs(limit=batch_size, effect_types=effect_types, test_only=test_only)
        return {
            "ok": True,
            "items": [job.to_dict() for job in jobs],
            "counts": {
                "candidate_count": len(jobs),
                "processed_count": 0,
                "succeeded_count": 0,
                "failed_count": 0,
                "blocked_count": 0,
            },
            "dry_run": True,
            "test_only": bool(test_only),
            "real_external_call_executed": False,
        }

    def run_due(self, *, batch_size: int = 10, dry_run: bool = True, effect_types: list[str] | None = None, test_only: bool = False) -> dict[str, Any]:
        if dry_run:
            payload = self.preview_due(batch_size=batch_size, effect_types=effect_types, test_only=test_only)
            payload["dry_run"] = True
            return payload
        if WECOM_MESSAGE_GROUP_SEND in set(effect_types or []) and int(batch_size or 0) != 1:
            return {
                "ok": False,
                "error": "batch_size_one_required",
                "items": [],
                "counts": {"candidate_count": 0, "processed_count": 0, "succeeded_count": 0, "failed_count": 0, "blocked_count": 0},
                "dry_run": False,
                "test_only": bool(test_only),
                "real_external_call_executed": False,
            }
        if _enabled("AICRM_EXTERNAL_EFFECT_TEST_EXECUTION_ONLY") and not test_only:
            return {
                "ok": False,
                "error": "test_only_required",
                "items": [],
                "counts": {"candidate_count": 0, "processed_count": 0, "succeeded_count": 0, "failed_count": 0, "blocked_count": 0},
                "dry_run": False,
                "test_only": False,
                "real_external_call_executed": False,
            }

        jobs = self._repo.acquire_due_jobs(limit=batch_size, locked_by=self._locked_by, effect_types=effect_types, test_only=test_only)
        items: list[dict[str, Any]] = []
        counts = {"candidate_count": len(jobs), "processed_count": 0, "succeeded_count": 0, "failed_count": 0, "blocked_count": 0}
        real_external_call_executed = False
        for job in jobs:
            result = self.dispatch_one(job)
            items.append(result)
            counts["processed_count"] += 1
            status = str(result.get("job", {}).get("status") or "")
            if status == "succeeded":
                counts["succeeded_count"] += 1
            elif status == "blocked":
                counts["blocked_count"] += 1
            elif status.startswith("failed"):
                counts["failed_count"] += 1
            real_external_call_executed = real_external_call_executed or bool(result.get("real_external_call_executed"))
        return {
            "ok": True,
            "items": items,
            "counts": counts,
            "dry_run": False,
            "test_only": bool(test_only),
            "real_external_call_executed": real_external_call_executed,
        }

    def dispatch_one(self, job_or_id: int | ExternalEffectJob) -> dict[str, Any]:
        job = job_or_id if isinstance(job_or_id, ExternalEffectJob) else self._repo.get_job(int(job_or_id))
        if job is None:
            return {"ok": False, "error": "job_not_found", "real_external_call_executed": False}
        self._repo.mark_dispatching(job.id, locked_by=self._locked_by)
        if _enabled("AICRM_EXTERNAL_EFFECT_TEST_EXECUTION_ONLY") and not _is_test_job(job):
            attempt = self._repo.record_attempt(
                job=job,
                status="failed_terminal",
                adapter_mode=job.execution_mode or "execute",
                request_summary={"effect_type": job.effect_type, "test_execution_only": True},
                response_summary={"blocked": True, "real_external_call_executed": False},
                error_code="test_execution_only_required",
                error_message="AICRM_EXTERNAL_EFFECT_TEST_EXECUTION_ONLY=1 blocks non-test jobs.",
            )
            updated = self._repo.mark_failed_terminal(
                job.id,
                attempt_id=attempt.attempt_id,
                error_code="test_execution_only_required",
                error_message="AICRM_EXTERNAL_EFFECT_TEST_EXECUTION_ONLY=1 blocks non-test jobs.",
            )
            return {
                "ok": False,
                "job": updated.to_dict() if updated else job.to_dict(),
                "attempt": attempt.to_dict(),
                "real_external_call_executed": False,
            }
        capability_error = _capability_gate_error(job)
        if capability_error:
            message = (
                "Push capability is disabled by admin config."
                if capability_error == "push_capability_disabled"
                else "Push capability does not support real execution."
            )
            attempt = self._repo.record_attempt(
                job=job,
                status="failed_terminal",
                adapter_mode=job.execution_mode or "execute",
                request_summary={
                    "effect_type": job.effect_type,
                    "business_type": job.business_type,
                    "section": section_for_job(job),
                    "capability_gate": capability_error,
                },
                response_summary={"blocked": True, "real_external_call_executed": False},
                error_code=capability_error,
                error_message=message,
            )
            updated = self._repo.mark_failed_terminal(
                job.id,
                attempt_id=attempt.attempt_id,
                error_code=capability_error,
                error_message=message,
            )
            return {
                "ok": False,
                "job": updated.to_dict() if updated else job.to_dict(),
                "attempt": attempt.to_dict(),
                "real_external_call_executed": False,
            }
        try:
            dispatch_result = self._adapters.get(job.adapter_name).dispatch(job)
        except Exception as exc:
            LOGGER.exception(
                "external effect adapter dispatch raised",
                extra={
                    "external_effect_job_id": int(job.id or 0),
                    "effect_type": job.effect_type,
                    "adapter_name": job.adapter_name,
                },
            )
            error_code = "adapter_exception"
            error_message = str(exc)[:500]
            attempt = self._repo.record_attempt(
                job=job,
                status="failed_retryable",
                adapter_mode=job.execution_mode or "execute",
                request_summary={
                    "effect_type": job.effect_type,
                    "adapter_name": job.adapter_name,
                    "operation": job.operation,
                    "adapter_exception": True,
                },
                response_summary={
                    "adapter_exception": True,
                    "real_external_call_executed": False,
                },
                error_code=error_code,
                error_message=error_message,
            )
            if status_for_failure(
                error_code=error_code,
                attempt_count=int(job.attempt_count or 0) + 1,
                max_attempts=int(job.max_attempts or 5),
            ) == "failed_retryable":
                updated = self._repo.mark_failed_retryable(
                    job.id,
                    attempt_id=attempt.attempt_id,
                    error_code=error_code,
                    error_message=error_message,
                    next_retry_at=next_retry_at(job.attempt_count),
                )
            else:
                updated = self._repo.mark_failed_terminal(
                    job.id,
                    attempt_id=attempt.attempt_id,
                    error_code=error_code,
                    error_message=error_message,
                )
            return {
                "ok": False,
                "job": updated.to_dict() if updated else job.to_dict(),
                "attempt": attempt.to_dict(),
                "real_external_call_executed": False,
            }
        attempt = self._repo.record_attempt(
            job=job,
            status=dispatch_result.status,
            adapter_mode=dispatch_result.adapter_mode,
            request_summary=dispatch_result.request_summary,
            response_summary=dispatch_result.response_summary,
            error_code=dispatch_result.error_code,
            error_message=dispatch_result.error_message,
        )
        if dispatch_result.status == "succeeded":
            updated = self._repo.mark_succeeded(job.id, attempt_id=attempt.attempt_id)
        elif dispatch_result.status == "failed_retryable" and status_for_failure(
            error_code=dispatch_result.error_code,
            attempt_count=int(job.attempt_count or 0) + 1,
            max_attempts=int(job.max_attempts or 5),
        ) == "failed_retryable":
            updated = self._repo.mark_failed_retryable(
                job.id,
                attempt_id=attempt.attempt_id,
                error_code=dispatch_result.error_code,
                error_message=dispatch_result.error_message,
                next_retry_at=next_retry_at(job.attempt_count),
            )
        elif dispatch_result.status in {"failed_retryable", "failed_terminal"}:
            updated = self._repo.mark_failed_terminal(
                job.id,
                attempt_id=attempt.attempt_id,
                error_code=dispatch_result.error_code,
                error_message=dispatch_result.error_message,
            )
        else:
            updated = self._repo.mark_failed_terminal(
                job.id,
                attempt_id=attempt.attempt_id,
                error_code=dispatch_result.error_code or "adapter_blocked",
                error_message=dispatch_result.error_message,
            )
        return {
            "ok": dispatch_result.ok,
            "job": updated.to_dict() if updated else job.to_dict(),
            "attempt": attempt.to_dict(),
            "real_external_call_executed": dispatch_result.real_external_call_executed,
        }
