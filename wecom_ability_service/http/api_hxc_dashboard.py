"""用户激活漏斗看板 — 外部 HTTP API

需要 Bearer token 鉴权; token 配置在 ``HXC_DASHBOARD_API_TOKEN``
(优先) 或回退到 ``MCP_BEARER_TOKEN`` / ``AUTOMATION_INTERNAL_API_TOKEN``.

路由
----

``GET /api/v1/hxc-dashboard/list``
    返回快照表全量人级明细 + 顶部 summary; 支持简单过滤参数:

    - ``funnel_state`` ∈ ``member_and_user / only_member / user_no_member / inactive``
    - ``owner_userid``
    - ``class_term_label``
    - ``membership_type`` ∈ ``trial / member``
    - ``limit`` / ``offset`` (分页, 默认全量)

``GET /api/v1/hxc-dashboard/summary``
    只返回 summary (4 漏斗分布 + 命中率 + 最后刷新时间), 高频拉取场景用.
"""
from __future__ import annotations

from typing import Any

from flask import jsonify, request

from ..domains.user_ops.hxc_dashboard_view_service import (
    get_dashboard_summary,
    list_hxc_dashboard_rows,
)
from ..infra.internal_auth_runtime import require_internal_api_token_compat


_TOKEN_KEYS = (
    "HXC_DASHBOARD_API_TOKEN",
    "MCP_BEARER_TOKEN",
)


def _auth_or_response():
    return require_internal_api_token_compat(
        token_keys=_TOKEN_KEYS,
        require_configured=True,
    )


def _filter_rows(
    rows: list[dict[str, Any]],
    *,
    funnel_state: str,
    owner_userid: str,
    class_term_label: str,
    membership_type: str,
) -> list[dict[str, Any]]:
    if not (funnel_state or owner_userid or class_term_label or membership_type):
        return rows
    filtered = []
    for row in rows:
        if funnel_state and row.get("funnel_state") != funnel_state:
            continue
        if owner_userid and row.get("owner_userid") != owner_userid:
            continue
        if class_term_label and row.get("class_term_label") != class_term_label:
            continue
        if membership_type and row.get("membership_type") != membership_type:
            continue
        filtered.append(row)
    return filtered


def api_hxc_dashboard_list():
    failure = _auth_or_response()
    if failure is not None:
        return failure

    funnel_state = (request.args.get("funnel_state") or "").strip()
    owner_userid = (request.args.get("owner_userid") or "").strip()
    class_term_label = (request.args.get("class_term_label") or "").strip()
    membership_type = (request.args.get("membership_type") or "").strip()

    try:
        limit = int(request.args.get("limit") or 0)
    except (TypeError, ValueError):
        limit = 0
    try:
        offset = int(request.args.get("offset") or 0)
    except (TypeError, ValueError):
        offset = 0
    limit = max(0, min(limit, 10000))
    offset = max(0, offset)

    rows = list_hxc_dashboard_rows()
    filtered = _filter_rows(
        rows,
        funnel_state=funnel_state,
        owner_userid=owner_userid,
        class_term_label=class_term_label,
        membership_type=membership_type,
    )
    total = len(filtered)
    paginated = filtered[offset:offset + limit] if limit else filtered[offset:]

    summary = get_dashboard_summary()
    return jsonify({
        "ok": True,
        "total": total,
        "offset": offset,
        "limit": limit or total,
        "filters": {
            "funnel_state": funnel_state,
            "owner_userid": owner_userid,
            "class_term_label": class_term_label,
            "membership_type": membership_type,
        },
        "summary": summary,
        "items": paginated,
    })


def api_hxc_dashboard_summary():
    failure = _auth_or_response()
    if failure is not None:
        return failure
    return jsonify({"ok": True, "summary": get_dashboard_summary()})


def register_routes(bp):
    bp.route("/api/v1/hxc-dashboard/list", methods=["GET"])(api_hxc_dashboard_list)
    bp.route("/api/v1/hxc-dashboard/summary", methods=["GET"])(api_hxc_dashboard_summary)
