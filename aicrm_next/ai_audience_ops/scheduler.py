from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from aicrm_next.platform_foundation.internal_events import PAYMENT_SUCCEEDED_EVENT_TYPES, QUESTIONNAIRE_SUBMITTED_EVENT_TYPE
from aicrm_next.platform_foundation.internal_events.worker import InternalEventWorker

from .event_types import (
    DAILY_REFRESH_CONSUMER,
    DAILY_TICK_EVENT,
    INCREMENTAL_REFRESH_CONSUMER,
    INCREMENTAL_TICK_EVENT,
    MEMBER_EVENT_PREFIX,
    OUTBOUND_EFFECT_CONSUMER,
    SOURCE_CHANGED_EVENT,
    SOURCE_POKE_CONSUMER,
)
from .service import AudiencePackageService


DEFAULT_DAILY_REFRESH_TIME = "02:00"
DEFAULT_DAILY_TICK_WINDOW_MINUTES = 60


def emit_due_ticks(
    *,
    include_daily: bool = True,
    include_incremental: bool = True,
    now: datetime | None = None,
    daily_refresh_time: str = DEFAULT_DAILY_REFRESH_TIME,
    daily_window_minutes: int = DEFAULT_DAILY_TICK_WINDOW_MINUTES,
) -> dict[str, Any]:
    service = AudiencePackageService()
    items: list[dict[str, Any]] = []
    if include_incremental:
        items.append({"tick_type": "incremental", "result": service.emit_tick("incremental")})
    daily_due = _daily_tick_window_open(
        now=now,
        daily_refresh_time=daily_refresh_time,
        daily_window_minutes=daily_window_minutes,
    )
    if include_daily and daily_due:
        items.append({"tick_type": "daily", "result": service.emit_tick("daily")})
    return {
        "ok": True,
        "items": items,
        "daily_tick_due": daily_due,
        "daily_refresh_time": daily_refresh_time,
        "daily_window_minutes": max(1, int(daily_window_minutes or DEFAULT_DAILY_TICK_WINDOW_MINUTES)),
        "real_external_call_executed": False,
    }


def run_due_refresh_consumers(*, dry_run: bool = True, batch_size: int = 20) -> dict[str, Any]:
    return InternalEventWorker().run_due(
        batch_size=batch_size,
        dry_run=dry_run,
        event_types=[INCREMENTAL_TICK_EVENT, DAILY_TICK_EVENT],
        consumer_names=[INCREMENTAL_REFRESH_CONSUMER, DAILY_REFRESH_CONSUMER],
    )


def run_due_source_poke_consumers(*, dry_run: bool = True, batch_size: int = 20) -> dict[str, Any]:
    return InternalEventWorker().run_due(
        batch_size=batch_size,
        dry_run=dry_run,
        event_types=_source_poke_event_types(),
        consumer_names=[SOURCE_POKE_CONSUMER],
    )


def run_due_outbound_consumers(*, dry_run: bool = True, batch_size: int = 20) -> dict[str, Any]:
    return InternalEventWorker().run_due(
        batch_size=batch_size,
        dry_run=dry_run,
        event_types=[f"{MEMBER_EVENT_PREFIX}{event_type}" for event_type in ("entered", "updated", "exited")],
        consumer_names=[OUTBOUND_EFFECT_CONSUMER],
    )


def run_due_ai_audience_consumers(*, dry_run: bool = True, batch_size: int = 20) -> dict[str, Any]:
    source_poke = run_due_source_poke_consumers(dry_run=dry_run, batch_size=batch_size)
    refresh = run_due_refresh_consumers(dry_run=dry_run, batch_size=batch_size)
    outbound = run_due_outbound_consumers(dry_run=dry_run, batch_size=batch_size)
    return {
        "ok": bool(source_poke.get("ok")) and bool(refresh.get("ok")) and bool(outbound.get("ok")),
        "source_poke": source_poke,
        "refresh": refresh,
        "outbound": outbound,
        "real_external_call_executed": False,
    }


def ai_audience_event_consumer_pairs(*, include_source_poke: bool = True, include_refresh: bool = True, include_outbound: bool = True) -> list[str]:
    pairs: list[str] = []
    if include_source_poke:
        pairs.extend(f"{event_type}:{SOURCE_POKE_CONSUMER}" for event_type in _source_poke_event_types())
    if include_refresh:
        pairs.extend(
            [
                f"{INCREMENTAL_TICK_EVENT}:{INCREMENTAL_REFRESH_CONSUMER}",
                f"{DAILY_TICK_EVENT}:{DAILY_REFRESH_CONSUMER}",
            ]
        )
    if include_outbound:
        pairs.extend(f"{MEMBER_EVENT_PREFIX}{event_type}:{OUTBOUND_EFFECT_CONSUMER}" for event_type in ("entered", "updated", "exited"))
    return pairs


def _source_poke_event_types() -> list[str]:
    return [
        SOURCE_CHANGED_EVENT,
        "channel_entry.entered",
        QUESTIONNAIRE_SUBMITTED_EVENT_TYPE,
        "external_form.submitted",
        *PAYMENT_SUCCEEDED_EVENT_TYPES,
    ]


def _daily_tick_window_open(
    *,
    now: datetime | None = None,
    daily_refresh_time: str = DEFAULT_DAILY_REFRESH_TIME,
    daily_window_minutes: int = DEFAULT_DAILY_TICK_WINDOW_MINUTES,
    timezone_name: str = "Asia/Shanghai",
) -> bool:
    local_now = (now or datetime.now(ZoneInfo(timezone_name))).astimezone(ZoneInfo(timezone_name))
    hour, minute = _parse_hhmm(daily_refresh_time)
    start = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    minutes_since_start = (local_now - start).total_seconds() / 60
    return 0 <= minutes_since_start < max(1, int(daily_window_minutes or DEFAULT_DAILY_TICK_WINDOW_MINUTES))


def _parse_hhmm(value: str) -> tuple[int, int]:
    raw = str(value or "").strip() or DEFAULT_DAILY_REFRESH_TIME
    try:
        hour_text, minute_text = raw.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
    except (TypeError, ValueError):
        return 2, 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return 2, 0
    return hour, minute
