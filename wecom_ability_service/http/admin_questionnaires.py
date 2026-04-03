from __future__ import annotations

from flask import Response, current_app, jsonify, request

from ..domains.questionnaire import build_questionnaire_preflight_payload
from ..services import (
    count_external_contact_identity_maps,
    create_questionnaire,
    delete_questionnaire,
    disable_questionnaire,
    export_questionnaire_submissions,
    get_latest_questionnaire_submit_debug,
    get_questionnaire_detail,
    list_questionnaires,
    update_questionnaire,
)
from ..wecom_client import WeComClientError
from .common import _build_excel_xml, _deprecated_admin_redirect, _wecom_error_response
from .questionnaire_support import _attach_questionnaire_links


def admin_list_questionnaires():
    return jsonify({"ok": True, "questionnaires": [_attach_questionnaire_links(item) for item in list_questionnaires()]})


def admin_list_wecom_tags():
    from .. import routes as routes_compat

    try:
        return jsonify({"items": routes_compat.list_available_wecom_tags()})
    except WeComClientError as exc:
        return _wecom_error_response(exc)



def admin_questionnaires_preflight():
    from .. import routes as routes_compat

    return jsonify(
        build_questionnaire_preflight_payload(
            config=current_app.config,
            list_available_wecom_tags_fn=routes_compat.list_available_wecom_tags,
            count_external_contact_identity_maps_fn=count_external_contact_identity_maps,
        )
    )



def admin_questionnaires_ui():
    return _deprecated_admin_redirect("api.admin_console_questionnaires")


def admin_create_questionnaire():
    payload = request.get_json(silent=True) or {}
    try:
        questionnaire = create_questionnaire(payload)
        return jsonify({"ok": True, "questionnaire": _attach_questionnaire_links(questionnaire)})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def admin_get_questionnaire(questionnaire_id: int):
    questionnaire = get_questionnaire_detail(questionnaire_id)
    if not questionnaire:
        return jsonify({"ok": False, "error": "questionnaire not found"}), 404
    return jsonify({"ok": True, "questionnaire": _attach_questionnaire_links(questionnaire)})


def admin_questionnaire_latest_submit_debug(questionnaire_id: int):
    result = get_latest_questionnaire_submit_debug(questionnaire_id)
    if not result:
        return jsonify({"ok": False, "error": "no_submission_found"})
    payload = {"ok": True}
    payload.update(result)
    return jsonify(payload)


def admin_update_questionnaire(questionnaire_id: int):
    payload = request.get_json(silent=True) or {}
    try:
        questionnaire = update_questionnaire(questionnaire_id, payload)
        if not questionnaire:
            return jsonify({"ok": False, "error": "questionnaire not found"}), 404
        return jsonify({"ok": True, "questionnaire": _attach_questionnaire_links(questionnaire)})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def admin_disable_questionnaire(questionnaire_id: int):
    payload = request.get_json(silent=True) or {}
    questionnaire = disable_questionnaire(questionnaire_id, payload.get("is_disabled", True))
    if not questionnaire:
        return jsonify({"ok": False, "error": "questionnaire not found"}), 404
    return jsonify({"ok": True, "questionnaire": _attach_questionnaire_links(questionnaire)})


def admin_delete_questionnaire(questionnaire_id: int):
    deleted = delete_questionnaire(questionnaire_id)
    if not deleted:
        return jsonify({"ok": False, "error": "questionnaire not found"}), 404
    return jsonify({"ok": True, "deleted": True})


def admin_export_questionnaire(questionnaire_id: int):
    try:
        export_payload = export_questionnaire_submissions(questionnaire_id)
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    content = _build_excel_xml(export_payload["headers"], export_payload["rows"])
    response = Response(content, mimetype="application/vnd.ms-excel")
    response.headers["Content-Disposition"] = f'attachment; filename="{export_payload["filename"]}"'
    return response



def register_routes(bp):
    bp.route('/api/admin/questionnaires', methods=['GET'])(admin_list_questionnaires)
    bp.route('/api/admin/wecom/tags', methods=['GET'])(admin_list_wecom_tags)
    bp.route('/api/admin/questionnaires/preflight', methods=['GET'])(admin_questionnaires_preflight)
    bp.route('/admin/questionnaires/ui', methods=['GET'])(admin_questionnaires_ui)
    bp.route('/api/admin/questionnaires', methods=['POST'])(admin_create_questionnaire)
    bp.route('/api/admin/questionnaires/<int:questionnaire_id>', methods=['GET'])(admin_get_questionnaire)
    bp.route('/api/admin/questionnaires/<int:questionnaire_id>/latest-submit-debug', methods=['GET'])(admin_questionnaire_latest_submit_debug)
    bp.route('/api/admin/questionnaires/<int:questionnaire_id>', methods=['PUT'])(admin_update_questionnaire)
    bp.route('/api/admin/questionnaires/<int:questionnaire_id>/disable', methods=['POST'])(admin_disable_questionnaire)
    bp.route('/api/admin/questionnaires/<int:questionnaire_id>', methods=['DELETE'])(admin_delete_questionnaire)
    bp.route('/api/admin/questionnaires/<int:questionnaire_id>/export', methods=['GET'])(admin_export_questionnaire)
