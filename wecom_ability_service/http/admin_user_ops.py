from __future__ import annotations

from flask import Response, jsonify, render_template, request

from ..domains.routing_config import DEFAULT_SALES_ROUTE_OWNER_USERID
from ..services import (
    backfill_owner_class_terms_into_lead_pool,
    execute_user_ops_batch_send,
    export_user_ops_pool,
    get_user_ops_overview,
    import_activation_status_source,
    import_mobile_class_term_source,
    list_user_ops_history,
    list_user_ops_pool,
    list_user_ops_send_records,
    preview_user_ops_batch_send,
    run_due_user_ops_deferred_jobs,
    set_user_ops_do_not_disturb,
)
from ..wecom_client import WeComClientError
from .common import _build_excel_xml, _coerce_request_bool, _wecom_error_response


def _page_filters_from_request_args() -> dict[str, str]:
    return {
        "wecom_status": request.args.get("wecom_status", "").strip(),
        "mobile_binding_status": request.args.get("mobile_binding_status", "").strip(),
        "activation_bucket": request.args.get("activation_bucket", "").strip(),
        "class_term_no": request.args.get("class_term_no", "").strip(),
        "keyword": request.args.get("keyword", "").strip(),
        "mobile": request.args.get("mobile", "").strip(),
        "owner_userid": request.args.get("owner_userid", "").strip(),
        "is_wecom_added": request.args.get("is_wecom_added", "").strip(),
        "is_mobile_bound": request.args.get("is_mobile_bound", "").strip(),
        "huangxiaocan_activation_state": request.args.get("huangxiaocan_activation_state", "").strip(),
        "query": request.args.get("query", "").strip(),
    }


def admin_user_ops_overview():
    payload = get_user_ops_overview(**_page_filters_from_request_args())
    return jsonify({"ok": True, **payload})


def admin_user_ops_list():
    payload = list_user_ops_pool(**_page_filters_from_request_args())
    return jsonify({"ok": True, **payload})


def admin_user_ops_history():
    try:
        limit = int(request.args.get("limit", "100").strip() or "100")
    except ValueError:
        return jsonify({"ok": False, "error": "limit must be an integer"}), 400
    payload = list_user_ops_history(limit=limit)
    return jsonify({"ok": True, **payload})


def admin_user_ops_reload():
    return (
        jsonify(
            {
                "ok": False,
                "error": "deprecated_internal_only",
                "message": "legacy user-ops reload is no longer part of admin V2; use internal maintenance helpers only",
            }
        ),
        410,
    )


def admin_user_ops_import_experience_leads():
    return (
        jsonify(
            {
                "ok": False,
                "error": "deprecated_internal_only",
                "message": "legacy experience-leads import is no longer exposed by admin V2",
            }
        ),
        410,
    )


def admin_user_ops_import_mobile_class_terms():
    uploaded_file = request.files.get("file")
    pasted_text = ""
    if uploaded_file and uploaded_file.filename:
        try:
            payload = import_mobile_class_term_source(
                file_name=uploaded_file.filename,
                file_bytes=uploaded_file.read(),
            )
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify(payload)

    if request.is_json:
        pasted_text = str((request.get_json(silent=True) or {}).get("pasted_text") or "").strip()
    elif request.mimetype == "text/plain":
        pasted_text = request.get_data(as_text=True).strip()
    else:
        pasted_text = str(request.form.get("pasted_text") or "").strip()
    if not pasted_text:
        return jsonify({"ok": False, "error": "file or pasted_text is required"}), 400
    try:
        payload = import_mobile_class_term_source(pasted_text=pasted_text)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify(payload)


def admin_user_ops_import_activation_status():
    uploaded_file = request.files.get("file")
    pasted_text = ""
    if uploaded_file and uploaded_file.filename:
        try:
            payload = import_activation_status_source(
                file_name=uploaded_file.filename,
                file_bytes=uploaded_file.read(),
            )
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify(payload)

    if request.is_json:
        pasted_text = str((request.get_json(silent=True) or {}).get("pasted_text") or "").strip()
    elif request.mimetype == "text/plain":
        pasted_text = request.get_data(as_text=True).strip()
    else:
        pasted_text = str(request.form.get("pasted_text") or "").strip()
    if not pasted_text:
        return jsonify({"ok": False, "error": "file or pasted_text is required"}), 400
    try:
        payload = import_activation_status_source(pasted_text=pasted_text)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify(payload)


def admin_user_ops_backfill_class_term():
    return (
        jsonify(
            {
                "ok": False,
                "error": "deprecated_internal_only",
                "message": "legacy class-term backfill is no longer exposed by admin V2",
            }
        ),
        410,
    )


def internal_user_ops_backfill_owner_class_terms():
    payload_json = request.get_json(silent=True) or {}
    owner_userid = str(payload_json.get("owner_userid") or DEFAULT_SALES_ROUTE_OWNER_USERID).strip()
    class_term_min_value = payload_json.get("class_term_min", 1)
    class_term_max_value = payload_json.get("class_term_max", 5)
    dry_run = _coerce_request_bool(payload_json.get("dry_run", True), default=True)
    try:
        class_term_min = int(class_term_min_value)
        class_term_max = int(class_term_max_value)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "class_term_min and class_term_max must be integers"}), 400
    try:
        payload = backfill_owner_class_terms_into_lead_pool(
            owner_userid=owner_userid,
            class_term_min=class_term_min,
            class_term_max=class_term_max,
            dry_run=dry_run,
            operator=str(payload_json.get("operator") or "").strip(),
            entry_source=str(payload_json.get("entry_source") or "").strip(),
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except WeComClientError as exc:
        return _wecom_error_response(exc)
    return jsonify(payload)


def admin_user_ops_run_deferred_jobs():
    payload_json = request.get_json(silent=True) or {}
    limit_value = payload_json.get("limit", 20)
    try:
        limit = int(limit_value)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "limit must be an integer"}), 400
    payload = run_due_user_ops_deferred_jobs(limit=limit)
    return jsonify(payload)


def admin_user_ops_export():
    export_payload = export_user_ops_pool(**_page_filters_from_request_args())
    content = _build_excel_xml(export_payload["headers"], export_payload["rows"])
    return Response(
        content,
        mimetype="application/vnd.ms-excel",
        headers={"Content-Disposition": f"attachment; filename={export_payload['filename']}"},
    )


def admin_user_ops_do_not_disturb():
    payload_json = request.get_json(silent=True) or {}
    try:
        payload = set_user_ops_do_not_disturb(payload_json)
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **payload})


def admin_user_ops_batch_send_preview():
    payload_json = request.get_json(silent=True) or {}
    try:
        payload = preview_user_ops_batch_send(payload_json)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **payload})


def admin_user_ops_batch_send_execute():
    payload_json = request.get_json(silent=True) or {}
    try:
        payload = execute_user_ops_batch_send(payload_json)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except WeComClientError as exc:
        return _wecom_error_response(exc)
    return jsonify({"ok": True, **payload})


def admin_user_ops_send_records():
    try:
        limit = int(request.args.get("limit", "20").strip() or "20")
        offset = int(request.args.get("offset", "0").strip() or "0")
    except ValueError:
        return jsonify({"ok": False, "error": "limit and offset must be integers"}), 400
    payload = list_user_ops_send_records(limit=limit, offset=offset)
    return jsonify({"ok": True, **payload})


def admin_user_ops_ui():
    return render_template("admin_user_ops.html")



def register_routes(bp):
    bp.route('/api/admin/user-ops/overview', methods=['GET'])(admin_user_ops_overview)
    bp.route('/api/admin/user-ops/list', methods=['GET'])(admin_user_ops_list)
    bp.route('/api/admin/user-ops/history', methods=['GET'])(admin_user_ops_history)
    bp.route('/api/admin/user-ops/reload', methods=['POST'])(admin_user_ops_reload)
    bp.route('/api/admin/user-ops/import-experience-leads', methods=['POST'])(admin_user_ops_import_experience_leads)
    bp.route('/api/admin/user-ops/import-mobile-class-terms', methods=['POST'])(admin_user_ops_import_mobile_class_terms)
    bp.route('/api/admin/user-ops/import-activation-status', methods=['POST'])(admin_user_ops_import_activation_status)
    bp.route('/api/admin/user-ops/backfill-class-term', methods=['POST'])(admin_user_ops_backfill_class_term)
    bp.route('/api/internal/user-ops/lead-pool/backfill-owner-class-terms', methods=['POST'])(internal_user_ops_backfill_owner_class_terms)
    bp.route('/api/admin/user-ops/run-deferred-jobs', methods=['POST'])(admin_user_ops_run_deferred_jobs)
    bp.route('/api/admin/user-ops/export', methods=['GET'])(admin_user_ops_export)
    bp.route('/api/admin/user-ops/do-not-disturb', methods=['POST'])(admin_user_ops_do_not_disturb)
    bp.route('/api/admin/user-ops/batch-send/preview', methods=['POST'])(admin_user_ops_batch_send_preview)
    bp.route('/api/admin/user-ops/batch-send/execute', methods=['POST'])(admin_user_ops_batch_send_execute)
    bp.route('/api/admin/user-ops/send-records', methods=['GET'])(admin_user_ops_send_records)
    bp.route('/admin/user-ops/ui', methods=['GET'])(admin_user_ops_ui)
