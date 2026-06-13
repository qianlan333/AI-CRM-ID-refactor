from __future__ import annotations

from datetime import datetime
from typing import Any

from aicrm_next.platform_foundation.command_bus.models import CommandContext

from .models import ExternalEffectCreateRequest, ExternalEffectJob
from .repo import ExternalEffectRepository, build_external_effect_repository


class ExternalEffectService:
    def __init__(self, repository: ExternalEffectRepository | None = None):
        self._repo = repository or build_external_effect_repository()

    def plan_effect(
        self,
        *,
        effect_type: str,
        adapter_name: str,
        operation: str,
        target_type: str,
        target_id: str,
        payload: dict[str, Any] | None = None,
        payload_summary: dict[str, Any] | None = None,
        context: CommandContext | None = None,
        business_type: str = "",
        business_id: str = "",
        source_module: str = "",
        source_event_id: str = "",
        source_command_id: str = "",
        risk_level: str = "medium",
        requires_approval: bool = False,
        execution_mode: str = "shadow",
        scheduled_at: datetime | None = None,
        priority: int = 100,
        max_attempts: int = 5,
        idempotency_key: str = "",
        status: str = "planned",
    ) -> dict[str, Any]:
        request = ExternalEffectCreateRequest(
            effect_type=effect_type,
            adapter_name=adapter_name,
            operation=operation,
            target_type=target_type,
            target_id=target_id,
            payload=dict(payload or {}),
            payload_summary=dict(payload_summary or {}),
            context=context or CommandContext(),
            business_type=business_type,
            business_id=business_id,
            source_module=source_module,
            source_event_id=source_event_id,
            source_command_id=source_command_id,
            risk_level=risk_level,
            requires_approval=requires_approval,
            execution_mode=execution_mode,
            scheduled_at=scheduled_at,
            priority=priority,
            max_attempts=max_attempts,
            idempotency_key=idempotency_key,
            status=status,
        )
        return self._repo.create_job(request).to_dict()

    def get(self, job_id: int) -> ExternalEffectJob | None:
        return self._repo.get_job(job_id)

    def list_jobs(self, filters: dict[str, Any] | None = None, *, limit: int = 50, offset: int = 0) -> tuple[list[ExternalEffectJob], int]:
        return self._repo.list_jobs(filters or {}, limit=limit, offset=offset)

    def list_attempts(self, job_id: int):
        return self._repo.list_attempts(job_id)

    def count_jobs(self, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._repo.count_jobs(filters or {})

    def queue_metrics(self, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._repo.queue_metrics(filters or {})

    def list_test_receipts(self, filters: dict[str, Any] | None = None, *, limit: int = 50, offset: int = 0):
        return self._repo.list_test_receipts(filters or {}, limit=limit, offset=offset)

    def get_test_receipt(self, receipt_id: str):
        return self._repo.get_test_receipt(receipt_id)

    def test_receipt_metrics(self) -> dict[str, Any]:
        return self._repo.test_receipt_metrics()

    def enqueue(self, job_id: int) -> ExternalEffectJob | None:
        return self._repo.enqueue_job(job_id)

    def approve(self, job_id: int) -> ExternalEffectJob | None:
        return self._repo.approve_job(job_id)

    def retry(self, job_id: int) -> ExternalEffectJob | None:
        job = self._repo.get_job(job_id)
        if not job or job.status not in {"failed_retryable", "failed_terminal", "blocked"}:
            return None
        return self._repo.enqueue_job(job_id)

    def cancel(self, job_id: int) -> ExternalEffectJob | None:
        job = self._repo.get_job(job_id)
        if not job or job.status in {"succeeded", "cancelled"}:
            return None
        return self._repo.cancel_job(job_id)


def default_external_effect_service() -> ExternalEffectService:
    return ExternalEffectService()
