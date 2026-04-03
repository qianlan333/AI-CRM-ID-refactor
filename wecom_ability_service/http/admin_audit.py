from __future__ import annotations

from flask import jsonify, request, url_for

from ..domains.admin_audit import build_admin_audit_payload
from .admin_console import _breadcrumb_items, _render_admin_template


def admin_audit_logs():
    payload = build_admin_audit_payload(request.args)
    return _render_admin_template(
        "audit.html",
        active_nav="audit",
        page_title="操作审计",
        page_summary="所有后台写操作、确认执行、MCP sample call 和配置变更统一落在 admin_operation_logs。当前页提供标准化筛选、分页、排序和可分享 query params。",
        breadcrumbs=_breadcrumb_items(("CRM Console", url_for("api.admin_console_home")), ("操作审计", None)),
        audit_payload=payload,
    )


def api_admin_audit_logs():
    return jsonify({"ok": True, "audit": build_admin_audit_payload(request.args)})


def register_routes(bp):
    bp.route("/admin/audit", methods=["GET"])(admin_audit_logs)
    bp.route("/api/admin/audit/logs", methods=["GET"])(api_admin_audit_logs)
