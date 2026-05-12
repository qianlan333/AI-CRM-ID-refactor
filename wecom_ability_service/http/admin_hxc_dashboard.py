"""用户激活漏斗看板 — admin 后台路由

页面: ``/admin/hxc-dashboard``  (HTML, Jinja 模板嵌入 JSON + Tabulator)
即时刷新: ``POST /api/admin/hxc-dashboard/refresh``

数据从 ``user_ops_hxc_dashboard_snapshot`` 快照表读, 看板自带筛选/排序/CSV 导出.
"""
from __future__ import annotations

from flask import jsonify, request, url_for

from ..domains.user_ops.hxc_dashboard_snapshot_service import refresh_hxc_dashboard_snapshot
from ..domains.user_ops.hxc_dashboard_view_service import (
    get_dashboard_summary,
    list_hxc_dashboard_rows,
)
from .admin_console import _breadcrumb_items, _render_admin_template


def admin_hxc_dashboard_workspace():
    rows = list_hxc_dashboard_rows()
    summary = get_dashboard_summary()
    return _render_admin_template(
        "hxc_dashboard.html",
        active_nav="user_ops_funnel",
        page_title="用户激活漏斗看板",
        page_summary=(
            "CRM 三表 (lead_pool / people / 激活问卷) 手机号并集 × 黄小璨用户/会员/会话/消息 "
            "聚合, 每 30 分钟自动刷新. 列头可筛选, 表格右上角可导出 CSV / Excel."
        ),
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("用户激活漏斗看板", None),
        ),
        dashboard_rows=rows,
        dashboard_summary=summary,
    )


def admin_hxc_dashboard_refresh():
    trigger_source = (request.json or {}).get("trigger_source") or "admin"
    result = refresh_hxc_dashboard_snapshot(trigger_source=str(trigger_source))
    status_code = 200 if result.get("ok") else 500
    return jsonify(result), status_code


def register_routes(bp):
    bp.route("/admin/hxc-dashboard", methods=["GET"])(admin_hxc_dashboard_workspace)
    bp.route("/api/admin/hxc-dashboard/refresh", methods=["POST"])(admin_hxc_dashboard_refresh)
