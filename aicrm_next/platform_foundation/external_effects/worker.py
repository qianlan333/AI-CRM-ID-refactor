from __future__ import annotations

from typing import Any
from uuid import uuid4

from aicrm_next.shared.runtime_settings import runtime_bool

from .adapters import DEFAULT_ADAPTER_REGISTRY, ExternalEffectAdapterRegistry
from .models import WECOM_MESSAGE_GROUP_SEND, ExternalEffectJob
from .repo import ExternalEffectRepository, build_external_effect_repository
from .retry_policy import next_retry_at, status_for_failure


def _enabled(name: str) -> bool:
    return runtime_bool(name)


def _is_test_job(job: ExternalEffectJob) -> bool:
    payload = dict(job.payload_json or {})
    return payload.get("execution_scope") == "test_loopback" or payload.get("is_test") is True


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
                status="blocked",
                adapter_mode=job.execution_mode or "execute",
                request_summary={"effect_type": job.effect_type, "test_execution_only": True},
                response_summary={"blocked": True, "real_external_call_executed": False},
                error_code="test_execution_only_required",
                error_message="AICRM_EXTERNAL_EFFECT_TEST_EXECUTION_ONLY=1 blocks non-test jobs.",
            )
            updated = self._repo.mark_blocked(
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
        dispatch_result = self._adapters.get(job.adapter_name).dispatch(job)
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
            updated = self._repo.mark_blocked(
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
