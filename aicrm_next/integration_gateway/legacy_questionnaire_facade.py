from __future__ import annotations

from typing import Any, Callable, TypeVar

from aicrm_next.questionnaire.domain import admin_detail_projection, summary_projection

from .legacy_flask_facade import _legacy_app, _legacy_import_module, legacy_questionnaire_service

LEGACY_COMPATIBILITY_BOUNDARY = "legacy_questionnaire_facade"

T = TypeVar("T")


class LegacyQuestionnaireDataUnavailable(RuntimeError):
    pass


def _with_legacy_app_context(callback: Callable[[], T]) -> T:
    try:
        app = _legacy_app()
        with app.app_context():
            return callback()
    except Exception as exc:  # pragma: no cover - exact DB/legacy failures vary by environment
        raise LegacyQuestionnaireDataUnavailable(str(exc)) from exc


def list_questionnaires_from_legacy(*, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    def _load() -> dict[str, Any]:
        legacy_service = legacy_questionnaire_service()
        rows = legacy_service.list_questionnaires()
        total = len(rows)
        page = rows[int(offset) : int(offset) + int(limit)]
        items = [summary_projection(item) for item in page]
        return {
            "ok": True,
            "items": items,
            "questionnaires": items,
            "total": total,
            "limit": int(limit),
            "offset": int(offset),
            "source_status": "production_postgres",
            "compatibility_facade": LEGACY_COMPATIBILITY_BOUNDARY,
        }

    return _with_legacy_app_context(_load)


def get_questionnaire_detail_from_legacy(questionnaire_id: int) -> dict[str, Any]:
    def _load() -> dict[str, Any]:
        legacy_service = legacy_questionnaire_service()
        item = legacy_service.get_questionnaire_detail(int(questionnaire_id))
        if not item:
            raise LookupError("questionnaire not found")
        return {
            "ok": True,
            **admin_detail_projection(item),
            "source_status": "production_postgres",
            "compatibility_facade": LEGACY_COMPATIBILITY_BOUNDARY,
        }

    return _with_legacy_app_context(_load)


def latest_submit_debug_from_legacy(questionnaire_id: int) -> dict[str, Any]:
    def _load() -> dict[str, Any]:
        legacy_service = legacy_questionnaire_service()
        item = legacy_service.get_latest_questionnaire_submit_debug(int(questionnaire_id))
        return {
            "ok": True,
            "submission": item,
            "source_status": "production_postgres",
            "safe_debug": True,
            "compatibility_facade": LEGACY_COMPATIBILITY_BOUNDARY,
        }

    return _with_legacy_app_context(_load)
