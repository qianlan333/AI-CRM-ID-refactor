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


def customer_tags_internal_events_enabled() -> bool:
    return internal_events_enabled() and env_bool("AICRM_INTERNAL_EVENTS_CUSTOMER_TAGS_ENABLED", default=False)


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


def allowed_event_consumers() -> list[str]:
    raw = _text(os.getenv("AICRM_INTERNAL_EVENTS_ALLOWED_EVENT_CONSUMERS"))
    normalized = raw.replace("\n", ",")
    pairs: list[str] = []
    seen: set[str] = set()
    for item in normalized.split(","):
        text = _text(item)
        if not text or ":" not in text:
            continue
        event_type, consumer_name = (_text(part) for part in text.split(":", 1))
        if not event_type or not consumer_name:
            continue
        pair = f"{event_type}:{consumer_name}"
        if pair not in seen:
            pairs.append(pair)
            seen.add(pair)
    return pairs


def allowed_event_consumer_pairs() -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for item in allowed_event_consumers():
        event_type, consumer_name = item.split(":", 1)
        pairs.append((event_type, consumer_name))
    return pairs


def pair_allowlist_enabled() -> bool:
    return bool(allowed_event_consumers())


def config_warnings() -> list[str]:
    warnings: list[str] = []
    if auto_execute_enabled() and len(allowed_event_types()) > 1 and not pair_allowlist_enabled():
        warnings.append("auto_execute_multi_event_without_pair_allowlist")
    return warnings


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
        "customer_tags_internal_events_enabled": customer_tags_internal_events_enabled(),
        "shadow_only": internal_events_shadow_only(),
        "auto_execute_enabled": auto_execute_enabled(),
        "allowed_event_types": allowed_event_types(),
        "allowed_consumers": allowed_consumers(),
        "allowed_event_consumers": allowed_event_consumers(),
        "pair_allowlist_enabled": pair_allowlist_enabled(),
        "worker_batch_size": worker_batch_size(),
        "auto_execute_max_batch_size": auto_execute_max_batch_size(),
        "config_warnings": config_warnings(),
        "config_source": "env",
    }
