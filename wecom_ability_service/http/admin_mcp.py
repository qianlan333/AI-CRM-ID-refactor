from __future__ import annotations

import json

from flask import request, url_for

from ..domains.admin_console import build_mcp_console_payload, run_mcp_preflight, run_mcp_sample_call
from .admin_console import _breadcrumb_items, _render_admin_template


def _operator_from_request() -> str:
    json_payload = request.get_json(silent=True) or {}
    return (
        str(request.headers.get("X-Admin-Operator") or "").strip()
        or str(request.values.get("operator") or "").strip()
        or str(json_payload.get("operator") or "").strip()
        or "crm_console"
    )


def _query_text(name: str) -> str:
    return str(request.args.get(name) or "").strip()


def _query_bool(name: str) -> bool:
    return str(request.args.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _default_arguments_json(row: dict[str, object]) -> str:
    sample_args = row.get("sample_args") if isinstance(row, dict) else {}
    return json.dumps(sample_args or {}, ensure_ascii=False, indent=2, sort_keys=True)


def _mcp_page(
    *,
    page_notice: str = "",
    page_error: str = "",
    sample_result: dict | None = None,
    preflight_result: dict | None = None,
    form_state: dict | None = None,
):
    payload = build_mcp_console_payload(request.args)
    selected_tool = (
        str((form_state or {}).get("tool_name") or "").strip()
        or _query_text("tool")
        or str((payload["registry_rows"][0]["tool_name"] if payload["registry_rows"] else "")).strip()
    )
    selected_row = next((item for item in payload["registry_rows"] if item["tool_name"] == selected_tool), payload["registry_rows"][0] if payload["registry_rows"] else {})
    sample_form = {
        "tool_name": str((form_state or {}).get("tool_name") or selected_tool).strip(),
        "arguments_json": str((form_state or {}).get("arguments_json") or "").strip() or _default_arguments_json(selected_row),
        "live_run": bool((form_state or {}).get("live_run")),
        "confirm_high_risk": bool((form_state or {}).get("confirm_high_risk")),
        "operator": str((form_state or {}).get("operator") or "").strip(),
    }
    return _render_admin_template(
        "mcp.html",
        active_nav="mcp",
        page_title="AI 工具控制台",
        page_summary="在这里查看 AI 工具是否可用，并做安全试运行。",
        breadcrumbs=_breadcrumb_items(("客户管理后台", url_for("api.admin_console_home")), ("AI 工具", None)),
        page_notice=page_notice,
        page_error=page_error,
        filters=payload["filters"],
        summary_cards=payload["summary_cards"],
        runtime=payload["runtime"],
        dependency_checks=payload["dependency_checks"],
        registry_rows=payload["registry_rows"],
        latest_preflight_log=payload["latest_preflight_log"],
        recent_preflight_logs=payload["recent_preflight_logs"],
        recent_sample_logs=payload["recent_sample_logs"],
        selected_tool=selected_row,
        sample_form=sample_form,
        sample_result=sample_result,
        preflight_result=preflight_result,
    )


def admin_console_mcp():
    return _mcp_page()


def admin_console_mcp_preflight():
    try:
        result = run_mcp_preflight(operator=_operator_from_request())
    except Exception as exc:
        return _mcp_page(page_error=str(exc))
    return _mcp_page(page_notice="环境检查已执行。", preflight_result=result)


def admin_console_mcp_sample_call():
    form_state = {
        "tool_name": str(request.form.get("tool_name") or "").strip(),
        "arguments_json": str(request.form.get("arguments_json") or "").strip(),
        "live_run": str(request.form.get("live_run") or "").strip().lower() in {"1", "true", "yes", "on"},
        "confirm_high_risk": str(request.form.get("confirm_high_risk") or "").strip().lower() in {"1", "true", "yes", "on"},
        "operator": str(request.form.get("operator") or "").strip(),
    }
    try:
        result = run_mcp_sample_call(
            tool_name=form_state["tool_name"],
            arguments_json=form_state["arguments_json"],
            live_run=form_state["live_run"],
            confirm_high_risk=form_state["confirm_high_risk"],
            operator=_operator_from_request(),
        )
    except ValueError as exc:
        return _mcp_page(page_error=str(exc), form_state=form_state)
    return _mcp_page(
        page_notice="试运行已执行。" if form_state["live_run"] else "试运行预览已生成。",
        sample_result=result,
        form_state=form_state,
    )


def register_routes(bp):
    bp.route("/admin/mcp", methods=["GET"])(admin_console_mcp)
    bp.route("/admin/mcp/preflight", methods=["POST"])(admin_console_mcp_preflight)
    bp.route("/admin/mcp/sample-call", methods=["POST"])(admin_console_mcp_sample_call)
