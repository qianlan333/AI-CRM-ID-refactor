from __future__ import annotations

from typing import Any, Callable, TypeVar

from aicrm_next.questionnaire.domain import admin_detail_projection, public_projection, summary_projection

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


def _text(value: Any) -> str:
    return str(value or "").strip()


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


def create_questionnaire_in_legacy(payload: dict[str, Any]) -> dict[str, Any]:
    def _save() -> dict[str, Any]:
        legacy_service = legacy_questionnaire_service()
        item = legacy_service.create_questionnaire(dict(payload or {}))
        return {
            "ok": True,
            **admin_detail_projection(item),
            "source_status": "production_postgres",
            "compatibility_facade": LEGACY_COMPATIBILITY_BOUNDARY,
        }

    return _with_legacy_app_context(_save)


def update_questionnaire_in_legacy(questionnaire_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    def _save() -> dict[str, Any]:
        legacy_service = legacy_questionnaire_service()
        item = legacy_service.update_questionnaire(int(questionnaire_id), dict(payload or {}))
        if not item:
            raise LookupError("questionnaire not found")
        return {
            "ok": True,
            **admin_detail_projection(item),
            "source_status": "production_postgres",
            "compatibility_facade": LEGACY_COMPATIBILITY_BOUNDARY,
        }

    return _with_legacy_app_context(_save)


def set_questionnaire_enabled_in_legacy(questionnaire_id: int, *, enabled: bool) -> dict[str, Any]:
    def _save() -> dict[str, Any]:
        legacy_service = legacy_questionnaire_service()
        item = legacy_service.disable_questionnaire(int(questionnaire_id), is_disabled=not bool(enabled))
        if not item:
            raise LookupError("questionnaire not found")
        return {
            "ok": True,
            "questionnaire": summary_projection(item),
            "source_status": "production_postgres",
            "compatibility_facade": LEGACY_COMPATIBILITY_BOUNDARY,
        }

    return _with_legacy_app_context(_save)


def delete_questionnaire_in_legacy(questionnaire_id: int) -> dict[str, Any]:
    def _delete() -> dict[str, Any]:
        legacy_service = legacy_questionnaire_service()
        return {
            "ok": True,
            "deleted": legacy_service.delete_questionnaire(int(questionnaire_id)),
            "delete_mode": "legacy_postgres",
            "source_status": "production_postgres",
            "compatibility_facade": LEGACY_COMPATIBILITY_BOUNDARY,
        }

    return _with_legacy_app_context(_delete)


def get_public_questionnaire_from_legacy(slug: str) -> dict[str, Any]:
    def _load() -> dict[str, Any]:
        legacy_service = legacy_questionnaire_service()
        item = legacy_service.get_public_questionnaire_by_slug(slug)
        if not item:
            raise LookupError("questionnaire not found")
        return {
            "ok": True,
            **public_projection(item),
            "source_status": "production_postgres",
            "compatibility_facade": LEGACY_COMPATIBILITY_BOUNDARY,
        }

    return _with_legacy_app_context(_load)


def get_public_questionnaire_submission_status_from_legacy(
    slug: str,
    *,
    session_identity: dict[str, Any] | None = None,
    request_identity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    def _load() -> dict[str, Any]:
        legacy_service = legacy_questionnaire_service()
        questionnaire = legacy_service.get_public_questionnaire_by_slug(slug)
        if not questionnaire:
            raise LookupError("questionnaire not found")

        dto = _legacy_import_module(".application.questionnaire.dto")
        queries = _legacy_import_module(".application.questionnaire.queries")
        identity = queries.ResolveQuestionnaireRespondentIdentityQuery()(
            session_identity=dict(session_identity or {}) if session_identity else None,
            request_identity=dict(request_identity or {}) if request_identity else None,
        )
        submitted = bool(
            queries.HasQuestionnaireSubmissionQuery()(
                dto.HasQuestionnaireSubmissionQueryDTO(
                    questionnaire_id=int(questionnaire["id"]),
                    identity=dict(identity or {}) if identity else None,
                )
            )
        )
        normalized_slug = _text(questionnaire.get("slug")) or _text(slug)
        redirect_url = _text(questionnaire.get("redirect_url"))
        return {
            "ok": True,
            "submitted": submitted,
            "questionnaire_id": int(questionnaire["id"]),
            "slug": normalized_slug,
            "identity": identity,
            "redirect_url": redirect_url,
            "submitted_url": f"/s/{normalized_slug}/submitted",
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


def export_questionnaire_from_legacy(questionnaire_id: int) -> dict[str, Any]:
    def _load() -> dict[str, Any]:
        legacy_service = legacy_questionnaire_service()
        return {
            "ok": True,
            "export": legacy_service.export_questionnaire_submissions(int(questionnaire_id)),
            "source_status": "production_postgres",
            "compatibility_facade": LEGACY_COMPATIBILITY_BOUNDARY,
        }

    return _with_legacy_app_context(_load)
