from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Callable, TypeVar

from .legacy_flask_facade import _legacy_app

LEGACY_COMPATIBILITY_BOUNDARY = "legacy_automation_facade"

T = TypeVar("T")


class LegacyAutomationDataUnavailable(RuntimeError):
    pass


def _with_legacy_app_context(callback: Callable[[], T]) -> T:
    try:
        app = _legacy_app()
        with app.app_context():
            return callback()
    except Exception as exc:  # pragma: no cover - exact DB/legacy failures vary by environment
        raise LegacyAutomationDataUnavailable(str(exc)) from exc


def get_automation_overview_from_legacy() -> dict[str, Any]:
    def _load() -> dict[str, Any]:
        from wecom_ability_service.domains.automation_conversion import service as legacy_service

        payload = legacy_service.get_overview_payload()
        cards = list(payload.get("cards") or [])
        counts = payload.get("counts") if isinstance(payload.get("counts"), dict) else {}
        total = int(counts.get("in_pool_total") or sum(int(card.get("value") or 0) for card in cards[:1]))
        return {
            "ok": True,
            "cards": cards,
            "total": total,
            "filters": {},
            "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "status": "live",
            "source_status": "production_postgres",
            "compatibility_facade": LEGACY_COMPATIBILITY_BOUNDARY,
            **payload,
        }

    return _with_legacy_app_context(_load)


def list_automation_pools_from_legacy() -> dict[str, Any]:
    def _load() -> dict[str, Any]:
        from wecom_ability_service.domains.automation_conversion import service as legacy_service

        payload = legacy_service.get_overview_payload()
        stage_columns = list(payload.get("stage_columns") or [])
        pools = [
            {
                "pool_key": item.get("pool") or item.get("route_key") or "",
                "label": item.get("label") or "",
                "description": item.get("description") or "",
                "count": int(item.get("total_count") or 0),
                "focus_count": int(item.get("focus_count") or 0),
                "normal_count": int(item.get("normal_count") or 0),
                "today_new_count": int(item.get("today_new_count") or 0),
            }
            for item in stage_columns
        ]
        return {
            "ok": True,
            "pools": pools,
            "total": len(pools),
            "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "source_status": "production_postgres",
            "compatibility_facade": LEGACY_COMPATIBILITY_BOUNDARY,
        }

    return _with_legacy_app_context(_load)


def list_automation_programs_from_legacy() -> dict[str, Any]:
    def _load() -> dict[str, Any]:
        from wecom_ability_service.domains.automation_conversion import list_automation_programs

        payload = list_automation_programs(include_archived=False)
        return {
            **payload,
            "ok": True,
            "source_status": "production_postgres",
            "compatibility_facade": LEGACY_COMPATIBILITY_BOUNDARY,
        }

    return _with_legacy_app_context(_load)
