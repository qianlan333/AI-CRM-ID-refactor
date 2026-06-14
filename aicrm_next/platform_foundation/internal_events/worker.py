from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import uuid4

from .config import allowed_event_types, diagnostics_payload, internal_events_enabled, internal_events_shadow_only
from .consumer_registry import DEFAULT_INTERNAL_EVENT_CONSUMER_REGISTRY, InternalEventConsumerRegistry
from .models import InternalEventConsumerResult, InternalEventConsumerRun, utcnow
from .repository import InternalEventRepository, build_internal_event_repository


def _next_retry_at(attempt_count: int, retry_after_seconds: int | None = None):
    if retry_after_seconds is not None and retry_after_seconds > 0:
        return utcnow() + timedelta(seconds=min(int(retry_after_seconds), 24 * 60 * 60))
    delays = [60, 300, 900, 3600, 6 * 3600]
    return utcnow() + timedelta(seconds=delays[min(max(int(attempt_count or 0), 0), len(delays) - 1)])


class InternalEventWorker:
    """Dispatch internal event consumer handlers.

    The worker is intentionally not an external adapter runner. Handlers that need
    external work must create external_effect_job records and return.
    """

    def __init__(
        self,
        repository: InternalEventRepository | None = None,
        consumer_registry: InternalEventConsumerRegistry | None = None,
        *,
        locked_by: str = "",
    ):
        self._repo = repository or build_internal_event_repository()
        self._registry = consumer_registry or DEFAULT_INTERNAL_EVENT_CONSUMER_REGISTRY
        self._locked_by = locked_by or f"internal-event-worker-{uuid4().hex[:8]}"

    def _effective_event_types(self, event_types: list[str] | None = None) -> list[str] | None:
        configured = allowed_event_types()
        requested = [str(item or "").strip() for item in (event_types or []) if str(item or "").strip()]
        if requested and configured:
            configured_set = set(configured)
            return [item for item in requested if item in configured_set]
        return requested or configured or None

    def preview_due(self, *, batch_size: int = 10, event_types: list[str] | None = None, consumer_names: list[str] | None = None) -> dict[str, Any]:
        effective_event_types = self._effective_event_types(event_types)
        runs = self._repo.list_due_runs(limit=batch_size, event_types=effective_event_types, consumer_names=consumer_names)
        return {
            "ok": True,
            "items": [run.to_dict() for run in runs],
            "counts": {
                "candidate_count": len(runs),
                "processed_count": 0,
                "succeeded_count": 0,
                "failed_retryable_count": 0,
                "failed_terminal_count": 0,
                "blocked_count": 0,
                "skipped_count": 0,
            },
            "dry_run": True,
            "event_types": effective_event_types or [],
            "config": diagnostics_payload(),
            "real_external_call_executed": False,
        }

    def run_due(
        self,
        *,
        batch_size: int = 10,
        dry_run: bool = True,
        event_types: list[str] | None = None,
        consumer_names: list[str] | None = None,
    ) -> dict[str, Any]:
        if dry_run:
            payload = self.preview_due(batch_size=batch_size, event_types=event_types, consumer_names=consumer_names)
            payload["dry_run"] = True
            return payload
        if not internal_events_enabled():
            return {
                "ok": False,
                "error": "internal_events_disabled",
                "items": [],
                "counts": {
                    "candidate_count": 0,
                    "processed_count": 0,
                    "succeeded_count": 0,
                    "failed_retryable_count": 0,
                    "failed_terminal_count": 0,
                    "blocked_count": 0,
                    "skipped_count": 0,
                },
                "dry_run": False,
                "config": diagnostics_payload(),
                "real_external_call_executed": False,
            }
        if internal_events_shadow_only():
            return {
                "ok": False,
                "error": "internal_events_shadow_only",
                "message": "Set AICRM_INTERNAL_EVENTS_SHADOW_ONLY=0 before executing consumers.",
                "items": [],
                "counts": {
                    "candidate_count": 0,
                    "processed_count": 0,
                    "succeeded_count": 0,
                    "failed_retryable_count": 0,
                    "failed_terminal_count": 0,
                    "blocked_count": 0,
                    "skipped_count": 0,
                },
                "dry_run": False,
                "config": diagnostics_payload(),
                "real_external_call_executed": False,
            }
        effective_event_types = self._effective_event_types(event_types)
        runs = self._repo.acquire_due_runs(
            limit=batch_size,
            locked_by=self._locked_by,
            event_types=effective_event_types,
            consumer_names=consumer_names,
        )
        items: list[dict[str, Any]] = []
        counts = {
            "candidate_count": len(runs),
            "processed_count": 0,
            "succeeded_count": 0,
            "failed_retryable_count": 0,
            "failed_terminal_count": 0,
            "blocked_count": 0,
            "skipped_count": 0,
        }
        for run in runs:
            result = self.dispatch_one(run)
            items.append(result)
            counts["processed_count"] += 1
            status = str(result.get("consumer_run", {}).get("status") or "")
            if status in {"succeeded", "failed_retryable", "failed_terminal", "blocked", "skipped"}:
                counts[f"{status}_count"] += 1
        return {
            "ok": True,
            "items": items,
            "counts": counts,
            "dry_run": False,
            "event_types": effective_event_types or [],
            "config": diagnostics_payload(),
            "real_external_call_executed": False,
        }

    def dispatch_one(self, run_or_id: int | InternalEventConsumerRun) -> dict[str, Any]:
        run = run_or_id if isinstance(run_or_id, InternalEventConsumerRun) else self._repo.get_consumer_run_by_id(int(run_or_id))
        if run is None:
            return {"ok": False, "error": "consumer_run_not_found", "real_external_call_executed": False}
        running = self._repo.mark_running(run.id, locked_by=self._locked_by) or run
        event = self._repo.get_event(running.event_id)
        if event is None:
            return self._blocked_result(running, "internal_event_not_found", f"event {running.event_id} was not found")

        handler = self._registry.get_handler(event.event_type, running.consumer_name)
        if handler is None:
            return self._blocked_result(
                running,
                "consumer_handler_not_registered",
                f"consumer handler is not registered: {event.event_type}/{running.consumer_name}",
            )

        try:
            handler_result = handler(event, running)
        except Exception as exc:
            handler_result = InternalEventConsumerResult(
                status="failed_retryable",
                request_summary={"event_id": event.event_id, "consumer_name": running.consumer_name},
                response_summary={"handler_exception": exc.__class__.__name__},
                error_code="handler_exception",
                error_message=str(exc),
            )

        status = handler_result.status
        if status == "failed_retryable" and int(running.attempt_count or 0) + 1 >= int(running.max_attempts or 5):
            status = "failed_terminal"
        attempt = self._repo.record_attempt(
            run=running,
            status=status,
            request_summary=handler_result.request_summary,
            response_summary={
                **handler_result.response_summary,
                "real_external_call_executed": False,
                "external_effect_boundary": "handler_must_enqueue_external_effect_job_for_external_calls",
            },
            error_code=handler_result.error_code,
            error_message=handler_result.error_message,
        )
        updated = self._repo.mark_result(
            running.id,
            status=status,
            attempt_id=attempt.attempt_id,
            result_summary=handler_result.result_summary or handler_result.response_summary,
            error_code=handler_result.error_code,
            error_message=handler_result.error_message,
            next_retry_at=_next_retry_at(running.attempt_count, handler_result.retry_after_seconds) if status == "failed_retryable" else None,
        )
        return {
            "ok": status == "succeeded",
            "event": event.to_dict(),
            "consumer_run": updated.to_dict() if updated else running.to_dict(),
            "attempt": attempt.to_dict(),
            "real_external_call_executed": False,
        }

    def _blocked_result(self, run: InternalEventConsumerRun, error_code: str, error_message: str) -> dict[str, Any]:
        attempt = self._repo.record_attempt(
            run=run,
            status="blocked",
            request_summary={"event_id": run.event_id, "consumer_name": run.consumer_name},
            response_summary={"blocked": True, "real_external_call_executed": False},
            error_code=error_code,
            error_message=error_message,
        )
        updated = self._repo.mark_result(
            run.id,
            status="blocked",
            attempt_id=attempt.attempt_id,
            result_summary={"blocked": True},
            error_code=error_code,
            error_message=error_message,
        )
        return {
            "ok": False,
            "consumer_run": updated.to_dict() if updated else run.to_dict(),
            "attempt": attempt.to_dict(),
            "real_external_call_executed": False,
        }
