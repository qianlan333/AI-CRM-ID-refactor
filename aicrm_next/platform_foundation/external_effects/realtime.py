from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from aicrm_next.shared.runtime_settings import runtime_bool, runtime_csv, runtime_setting

from .adapters import ExternalEffectAdapterRegistry
from .repo import ExternalEffectRepository
from .worker import ExternalEffectWorker

LOGGER = logging.getLogger(__name__)
_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="external-effect-realtime")
_ACTIVE_LOCK = threading.Lock()
_ACTIVE_COUNT = 0


def _text(value: Any) -> str:
    return str(value or "").strip()


def _max_concurrency() -> int:
    try:
        value = int(runtime_setting("AICRM_EXTERNAL_EFFECT_REALTIME_MAX_CONCURRENCY", "2") or "2")
    except Exception:
        value = 2
    return max(1, min(value, 16))


def _execution_gate_enabled_for_type(effect_type: str) -> bool:
    allowed_types = runtime_csv("AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES")
    if effect_type not in allowed_types:
        return False
    if effect_type.startswith("wecom."):
        return runtime_bool("AICRM_EXTERNAL_EFFECT_WECOM_EXECUTE")
    if effect_type.startswith("webhook."):
        return runtime_bool("AICRM_EXTERNAL_EFFECT_WEBHOOK_EXECUTE")
    return True


def realtime_wakeup_allowed(effect_type: str) -> bool:
    normalized = _text(effect_type)
    if not normalized:
        return False
    if not runtime_bool("AICRM_EXTERNAL_EFFECT_REALTIME_ENABLED"):
        return False
    if normalized not in runtime_csv("AICRM_EXTERNAL_EFFECT_REALTIME_ALLOWED_TYPES"):
        return False
    return _execution_gate_enabled_for_type(normalized)


def _try_acquire_slot() -> bool:
    global _ACTIVE_COUNT
    with _ACTIVE_LOCK:
        if _ACTIVE_COUNT >= _max_concurrency():
            return False
        _ACTIVE_COUNT += 1
        return True


def _release_slot() -> None:
    global _ACTIVE_COUNT
    with _ACTIVE_LOCK:
        _ACTIVE_COUNT = max(0, _ACTIVE_COUNT - 1)


def dispatch_external_effect_job_realtime(
    job_id: int,
    *,
    reason: str,
    effect_type: str,
    repository: ExternalEffectRepository | None = None,
    adapter_registry: ExternalEffectAdapterRegistry | None = None,
) -> dict[str, Any]:
    try:
        return ExternalEffectWorker(
            repository,
            adapter_registry,
            locked_by=f"external-effect-realtime:{_text(reason) or 'unspecified'}",
        ).dispatch_one(int(job_id))
    except Exception as exc:
        LOGGER.exception(
            "external effect realtime dispatch failed",
            extra={"external_effect_job_id": int(job_id or 0), "effect_type": _text(effect_type), "reason": _text(reason)},
        )
        return {
            "ok": False,
            "error": "external_effect_realtime_dispatch_failed",
            "error_message": str(exc),
            "real_external_call_executed": False,
        }


def _dispatch_and_release(
    job_id: int,
    *,
    reason: str,
    effect_type: str,
    repository: ExternalEffectRepository | None,
    adapter_registry: ExternalEffectAdapterRegistry | None,
) -> None:
    try:
        dispatch_external_effect_job_realtime(
            job_id,
            reason=reason,
            effect_type=effect_type,
            repository=repository,
            adapter_registry=adapter_registry,
        )
    finally:
        _release_slot()


def wake_external_effect_job(
    job_id: Any,
    *,
    reason: str,
    effect_type: str,
    repository: ExternalEffectRepository | None = None,
    adapter_registry: ExternalEffectAdapterRegistry | None = None,
    run_inline: bool = False,
) -> bool:
    try:
        normalized_job_id = int(job_id or 0)
    except (TypeError, ValueError):
        normalized_job_id = 0
    normalized_effect_type = _text(effect_type)
    if normalized_job_id <= 0 or not realtime_wakeup_allowed(normalized_effect_type):
        return False
    if not _try_acquire_slot():
        LOGGER.warning(
            "external effect realtime wakeup skipped because concurrency limit is reached",
            extra={"external_effect_job_id": normalized_job_id, "effect_type": normalized_effect_type, "reason": _text(reason)},
        )
        return False
    if run_inline:
        _dispatch_and_release(
            normalized_job_id,
            reason=reason,
            effect_type=normalized_effect_type,
            repository=repository,
            adapter_registry=adapter_registry,
        )
        return True
    try:
        _EXECUTOR.submit(
            _dispatch_and_release,
            normalized_job_id,
            reason=reason,
            effect_type=normalized_effect_type,
            repository=repository,
            adapter_registry=adapter_registry,
        )
    except Exception:
        _release_slot()
        LOGGER.exception(
            "external effect realtime wakeup scheduling failed",
            extra={"external_effect_job_id": normalized_job_id, "effect_type": normalized_effect_type, "reason": _text(reason)},
        )
        return False
    return True
