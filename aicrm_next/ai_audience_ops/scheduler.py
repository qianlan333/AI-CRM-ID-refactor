from __future__ import annotations

from typing import Any

from aicrm_next.platform_foundation.internal_events.worker import InternalEventWorker

from .event_types import (
    DAILY_REFRESH_CONSUMER,
    DAILY_TICK_EVENT,
    INCREMENTAL_REFRESH_CONSUMER,
    INCREMENTAL_TICK_EVENT,
)
from .service import AudiencePackageService


def emit_due_ticks(*, include_daily: bool = True, include_incremental: bool = True) -> dict[str, Any]:
    service = AudiencePackageService()
    items: list[dict[str, Any]] = []
    if include_incremental:
        items.append({"tick_type": "incremental", "result": service.emit_tick("incremental")})
    if include_daily:
        items.append({"tick_type": "daily", "result": service.emit_tick("daily")})
    return {"ok": True, "items": items, "real_external_call_executed": False}


def run_due_refresh_consumers(*, dry_run: bool = True, batch_size: int = 20) -> dict[str, Any]:
    return InternalEventWorker().run_due(
        batch_size=batch_size,
        dry_run=dry_run,
        event_types=[INCREMENTAL_TICK_EVENT, DAILY_TICK_EVENT],
        consumer_names=[INCREMENTAL_REFRESH_CONSUMER, DAILY_REFRESH_CONSUMER],
    )
