from __future__ import annotations

from typing import Any, Callable, TypeVar

from .legacy_flask_facade import (
    _legacy_app,
    legacy_automation_conversion_module,
    legacy_automation_conversion_service,
)

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


def list_automation_programs_from_legacy() -> dict[str, Any]:
    def _load() -> dict[str, Any]:
        legacy_automation_conversion = legacy_automation_conversion_module()
        payload = legacy_automation_conversion.list_automation_programs(include_archived=False)
        return {
            **payload,
            "ok": True,
            "source_status": "production_postgres",
            "compatibility_facade": LEGACY_COMPATIBILITY_BOUNDARY,
        }

    return _with_legacy_app_context(_load)


def get_automation_member_detail_from_legacy(*, external_contact_id: str = "", phone: str = "") -> dict[str, Any]:
    external_contact_id = str(external_contact_id or "").strip()
    phone = str(phone or "").strip()
    if not external_contact_id and not phone:
        return {"ok": False, "error": "external_contact_id or phone is required"}

    def _load() -> dict[str, Any]:
        legacy_service = legacy_automation_conversion_service()
        return {
            "ok": True,
            "detail": legacy_service.get_member_detail(external_contact_id=external_contact_id, phone=phone),
            "source_status": "production_postgres",
            "compatibility_facade": LEGACY_COMPATIBILITY_BOUNDARY,
        }

    return _with_legacy_app_context(_load)
