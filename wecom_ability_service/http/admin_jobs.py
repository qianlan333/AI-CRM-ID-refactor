from __future__ import annotations

from flask import jsonify, request, url_for

from ..domains.admin_jobs import (
    build_jobs_archive_sync_payload,
    build_jobs_callbacks_payload,
    build_jobs_deferred_jobs_payload,
    build_jobs_message_batch_detail_payload,
    build_jobs_message_batches_payload,
    build_jobs_payload,
    build_jobs_summary_payload,
    execute_jobs_action,
)
from .admin_console import _breadcrumb_items, _render_admin_template


def _operator_from_request() -> str:
    json_payload = request.get_json(silent=True) or {}
    return (
        str(request.headers.get("X-Admin-Operator") or "").strip()
        or str(request.values.get("operator") or "").strip()
        or str(json_payload.get("operator") or "").strip()
    )


def _request_confirmed() -> bool:
    json_payload = request.get_json(silent=True) or {}
    return (
        str(request.values.get("confirm") or "").strip().lower() in {"1", "true", "yes", "on"}
        or str(json_payload.get("confirm") or "").strip().lower() in {"1", "true", "yes", "on"}
    )


def _request_payload() -> dict:
    return request.get_json(silent=True) or {}


def _api_args() -> dict[str, str]:
    return request.args.to_dict(flat=True)


def _jobs_page(
    *,
    tab: str = "",
    page_notice: str = "",
    page_error: str = "",
    action_result: dict | None = None,
    query_overrides: dict[str, str] | None = None,
):
    args = request.args.to_dict(flat=True)
    if tab:
        args["tab"] = tab
    for key, value in (query_overrides or {}).items():
        if value != "":
            args[key] = value
    payload = build_jobs_payload(args)
    return _render_admin_template(
        "jobs.html",
        active_nav="jobs",
        page_title="同步与任务",
        page_summary="同步与任务后台页统一展示 archive sync、callback runtime、message batches 和 deferred jobs。读路径只做聚合展示，写动作统一确认并写审计。",
        breadcrumbs=_breadcrumb_items(("CRM Console", url_for("api.admin_console_home")), ("同步与任务", None)),
        jobs_payload=payload,
        page_notice=page_notice,
        page_error=page_error,
        action_result=action_result or {},
    )


def admin_console_jobs():
    return _jobs_page()


def admin_console_jobs_action():
    active_tab = str(request.form.get("return_tab") or request.args.get("tab") or "").strip()
    query_overrides = {
        "batch_id": str(request.form.get("batch_id") or "").strip(),
        "batch_status": str(request.form.get("batch_status") or "").strip(),
        "batch_limit": str(request.form.get("batch_limit") or "").strip(),
    }
    try:
        payload = execute_jobs_action(
            action=str(request.form.get("action") or "").strip(),
            form=request.form,
            operator=_operator_from_request(),
        )
        if payload.get("ok") is False:
            return _jobs_page(
                tab=active_tab,
                page_error=str(payload.get("error") or "action failed"),
                action_result=payload,
                query_overrides=query_overrides,
            )
        if payload.get("preview_only"):
            return _jobs_page(
                tab=active_tab,
                page_notice="当前为 preview，勾选确认后才会真正执行 archive sync。",
                action_result=payload,
                query_overrides=query_overrides,
            )
        return _jobs_page(
            tab=active_tab,
            page_notice="操作已完成，结果与审计已刷新。",
            action_result=payload,
            query_overrides=query_overrides,
        )
    except Exception as exc:
        return _jobs_page(
            tab=active_tab,
            page_error=str(exc),
            query_overrides=query_overrides,
        )


def api_admin_jobs_summary():
    return jsonify({"ok": True, "summary": build_jobs_summary_payload(_api_args())})


def api_admin_jobs_archive_sync():
    return jsonify({"ok": True, "archive_sync": build_jobs_archive_sync_payload(_api_args())})


def api_admin_jobs_archive_sync_run():
    payload = _request_payload()
    params = {
        "start_time": str(payload.get("start_time") or request.values.get("start_time") or "").strip(),
        "end_time": str(payload.get("end_time") or request.values.get("end_time") or "").strip(),
        "owner_userid": str(payload.get("owner_userid") or request.values.get("owner_userid") or "").strip(),
        "cursor": str(payload.get("cursor") or request.values.get("cursor") or "").strip(),
        "confirm": _request_confirmed(),
    }
    try:
        result = execute_jobs_action(action="run-archive-sync", form=params, operator=_operator_from_request())
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    status_code = 200 if result.get("ok", False) else 502
    return jsonify(result), status_code


def api_admin_jobs_callbacks():
    return jsonify({"ok": True, "callbacks": build_jobs_callbacks_payload(_api_args())})


def api_admin_jobs_message_batches():
    return jsonify({"ok": True, "message_batches": build_jobs_message_batches_payload(_api_args())})


def api_admin_jobs_message_batch_detail(batch_id: int):
    payload = build_jobs_message_batch_detail_payload(batch_id, _api_args())
    if not payload.get("batch"):
        return jsonify({"ok": False, "error": "message batch not found"}), 404
    return jsonify({"ok": True, "message_batch": payload})


def api_admin_jobs_message_batch_ack(batch_id: int):
    payload = _request_payload()
    params = {
        "batch_id": batch_id,
        "ack_note": str(payload.get("ack_note") or request.values.get("ack_note") or "").strip(),
        "confirm": _request_confirmed(),
    }
    try:
        result = execute_jobs_action(action="ack-message-batch", form=params, operator=_operator_from_request())
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    if not result.get("batch"):
        return jsonify({"ok": False, "error": "message batch not found"}), 404
    return jsonify(result)


def api_admin_jobs_deferred_jobs():
    return jsonify({"ok": True, "deferred_jobs": build_jobs_deferred_jobs_payload(_api_args())})


def api_admin_jobs_deferred_jobs_run():
    payload = _request_payload()
    params = {
        "limit": payload.get("limit") if "limit" in payload else request.values.get("limit"),
        "confirm": _request_confirmed(),
    }
    try:
        result = execute_jobs_action(action="run-deferred-jobs", form=params, operator=_operator_from_request())
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    status_code = 200 if result.get("ok", False) else 502
    return jsonify(result), status_code


def register_routes(bp):
    bp.route("/admin/jobs", methods=["GET"])(admin_console_jobs)
    bp.route("/admin/jobs/actions", methods=["POST"])(admin_console_jobs_action)
    bp.route("/api/admin/jobs/summary", methods=["GET"])(api_admin_jobs_summary)
    bp.route("/api/admin/jobs/archive-sync", methods=["GET"])(api_admin_jobs_archive_sync)
    bp.route("/api/admin/jobs/archive-sync/run", methods=["POST"])(api_admin_jobs_archive_sync_run)
    bp.route("/api/admin/jobs/callbacks", methods=["GET"])(api_admin_jobs_callbacks)
    bp.route("/api/admin/jobs/message-batches", methods=["GET"])(api_admin_jobs_message_batches)
    bp.route("/api/admin/jobs/message-batches/<int:batch_id>", methods=["GET"])(api_admin_jobs_message_batch_detail)
    bp.route("/api/admin/jobs/message-batches/<int:batch_id>/ack", methods=["POST"])(api_admin_jobs_message_batch_ack)
    bp.route("/api/admin/jobs/deferred-jobs", methods=["GET"])(api_admin_jobs_deferred_jobs)
    bp.route("/api/admin/jobs/deferred-jobs/run", methods=["POST"])(api_admin_jobs_deferred_jobs_run)
