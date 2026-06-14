from __future__ import annotations

import os
from typing import Any

from aicrm_next.shared.runtime import fixture_mode


DEFAULT_WORKER_BATCH_SIZE = 50
DEFAULT_AUTO_EXECUTE_MAX_BATCH_SIZE = 1


def _text(value: Any) -> str:
    return str(value or "").strip()


def env_bool(name: str, *, default: bool = False) -> bool:
    value = _text(os.getenv(name)).lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


def internal_events_enabled() -> bool:
    return env_bool("AICRM_INTERNAL_EVENTS_ENABLED", default=fixture_mode())


def payment_internal_events_enabled() -> bool:
    return internal_events_enabled() and env_bool("AICRM_INTERNAL_EVENTS_PAYMENT_ENABLED", default=False)


def questionnaire_internal_events_enabled() -> bool:
    return internal_events_enabled() and env_bool("AICRM_INTERNAL_EVENTS_QUESTIONNAIRE_ENABLED", default=False)


def internal_events_shadow_only() -> bool:
    return env_bool("AICRM_INTERNAL_EVENTS_SHADOW_ONLY", default=not fixture_mode())


def auto_execute_enabled() -> bool:
    return env_bool("AICRM_INTERNAL_EVENTS_AUTO_EXECUTE", default=fixture_mode())


def allowed_event_types() -> list[str]:
    raw = _text(os.getenv("AICRM_INTERNAL_EVENTS_ALLOWED_EVENT_TYPES"))
    return [item.strip() for item in raw.split(",") if item.strip()]


def allowed_consumers() -> list[str]:
    raw = _text(os.getenv("AICRM_INTERNAL_EVENTS_ALLOWED_CONSUMERS"))
    return [item.strip() for item in raw.split(",") if item.strip()]


def event_type_allowed(event_type: str, *, configured: list[str] | None = None) -> bool:
    allowed = configured if configured is not None else allowed_event_types()
    return not allowed or _text(event_type) in set(allowed)


def worker_batch_size() -> int:
    raw = _text(os.getenv("AICRM_INTERNAL_EVENTS_WORKER_BATCH_SIZE")) or _text(os.getenv("AICRM_INTERNAL_EVENT_WORKER_BATCH_SIZE"))
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        parsed = DEFAULT_WORKER_BATCH_SIZE
    return max(1, min(parsed, 500))


def auto_execute_max_batch_size() -> int:
    raw = _text(os.getenv("AICRM_INTERNAL_EVENTS_AUTO_EXECUTE_MAX_BATCH_SIZE"))
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        parsed = DEFAULT_AUTO_EXECUTE_MAX_BATCH_SIZE
    return max(1, min(parsed, 500))


def diagnostics_payload() -> dict[str, Any]:
    return {
        "internal_events_enabled": internal_events_enabled(),
        "payment_internal_events_enabled": payment_internal_events_enabled(),
        "questionnaire_internal_events_enabled": questionnaire_internal_events_enabled(),
        "shadow_only": internal_events_shadow_only(),
        "auto_execute_enabled": auto_execute_enabled(),
        "allowed_event_types": allowed_event_types(),
        "allowed_consumers": allowed_consumers(),
        "worker_batch_size": worker_batch_size(),
        "auto_execute_max_batch_size": auto_execute_max_batch_size(),
        "config_source": "env",
    }
