"""用户激活漏斗看板 — admin 后台路由

页面: ``/admin/hxc-dashboard``  (HTML, Jinja 模板嵌入 JSON + Tabulator)
即时刷新: ``POST /api/admin/hxc-dashboard/refresh``
发送人白名单 CRUD: ``/api/admin/hxc-dashboard/send-config``
一键群发: ``POST /api/admin/hxc-dashboard/broadcast``
"""
from __future__ import annotations

from flask import jsonify, request, url_for

from ..domains.user_ops.hxc_dashboard_snapshot_service import refresh_hxc_dashboard_snapshot
from ..domains.user_ops.hxc_dashboard_view_service import (
    get_dashboard_summary,
    list_hxc_dashboard_rows,
)
from ..domains.user_ops.hxc_send_config_service import (
    broadcast_to_filtered_users,
    delete_send_config,
    list_send_configs,
    upsert_send_config,
)
from .admin_console import _breadcrumb_items, _render_admin_template


def admin_hxc_dashboard_workspace():
    rows = list_hxc_dashboard_rows()
    summary = get_dashboard_summary()
    send_configs = list_send_configs()
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
        send_configs=send_configs,
    )


def admin_hxc_dashboard_refresh():
    trigger_source = (request.json or {}).get("trigger_source") or "admin"
    result = refresh_hxc_dashboard_snapshot(trigger_source=str(trigger_source))
    status_code = 200 if result.get("ok") else 500
    return jsonify(result), status_code


# ── 发送人白名单 CRUD ──

def admin_hxc_send_config_list():
    return jsonify(list_send_configs())


def admin_hxc_send_config_upsert():
    body = request.json or {}
    sender_userid = (body.get("sender_userid") or "").strip()
    if not sender_userid:
        return jsonify({"ok": False, "error": "sender_userid required"}), 400
    result = upsert_send_config(
        sender_userid=sender_userid,
        display_name=(body.get("display_name") or "").strip(),
        priority=int(body.get("priority", 100)),
        is_active=bool(body.get("is_active", True)),
    )
    return jsonify(result)


def admin_hxc_send_config_delete(sender_userid):
    result = delete_send_config(sender_userid)
    return jsonify(result)


# ── 一键群发 ──

def admin_hxc_dashboard_broadcast():
    body = request.json or {}
    external_userids = body.get("external_userids") or []
    content = (body.get("content") or "").strip()
    if not external_userids:
        return jsonify({"ok": False, "error": "no targets"}), 400
    if not content:
        return jsonify({"ok": False, "error": "empty content"}), 400
    result = broadcast_to_filtered_users(
        external_userids=external_userids,
        content=content,
        operator_id="admin",
    )
    status_code = 200 if result.get("ok") else 400
    return jsonify(result), status_code


def register_routes(bp):
    bp.route("/admin/hxc-dashboard", methods=["GET"])(admin_hxc_dashboard_workspace)
    bp.route("/api/admin/hxc-dashboard/refresh", methods=["POST"])(admin_hxc_dashboard_refresh)
    bp.route("/api/admin/hxc-dashboard/send-config", methods=["GET"])(admin_hxc_send_config_list)
    bp.route("/api/admin/hxc-dashboard/send-config", methods=["POST"])(admin_hxc_send_config_upsert)
    bp.route("/api/admin/hxc-dashboard/send-config/<sender_userid>", methods=["DELETE"])(admin_hxc_send_config_delete)
    bp.route("/api/admin/hxc-dashboard/broadcast", methods=["POST"])(admin_hxc_dashboard_broadcast)
