from __future__ import annotations

from flask import request, url_for

from ..domains.admin_console import (
    build_customer_detail_payload,
    build_customer_list_payload,
    execute_customer_tag_action,
    execute_customer_task_action,
    preview_customer_tag_action,
    preview_customer_task_action,
)
from .admin_console import _breadcrumb_items, _render_admin_template


CUSTOMER_TABS = (
    ("basic", "基本信息"),
    ("timeline", "互动记录"),
    ("recent-messages", "最近聊天"),
    ("tags", "标签管理"),
    ("tasks", "触达任务"),
    ("questionnaires", "问卷记录"),
    ("routing", "分配信息"),
)


def _customer_tabs(external_userid: str, active_tab: str) -> list[dict[str, str | bool]]:
    normalized_active_tab = str(active_tab or "").strip() or "basic"
    return [
        {
            "key": key,
            "label": label,
            "active": key == normalized_active_tab,
            "href": url_for("api.admin_console_customer_detail", external_userid=external_userid, tab=key),
        }
        for key, label in CUSTOMER_TABS
    ]


def admin_console_customers():
    payload = build_customer_list_payload(request.args)
    return _render_admin_template(
        "customers.html",
        active_nav="customers",
        page_title="客户中心",
        page_summary="查看客户资料、标签、状态和最近互动记录。",
        breadcrumbs=_breadcrumb_items(("客户管理后台", url_for("api.admin_console_home")), ("客户", None)),
        customer_payload=payload,
    )


def _render_customer_detail_page(
    external_userid: str,
    *,
    active_tab: str = "basic",
    page_notice: str = "",
    page_error: str = "",
    action_result: dict | None = None,
    active_action: str = "",
):
    payload = build_customer_detail_payload(external_userid)
    if not payload:
        return _render_admin_template(
            "placeholder.html",
            active_nav="customers",
            page_title="客户不存在",
            page_summary="当前客户编号没有查到对应客户。",
            breadcrumbs=_breadcrumb_items(
                ("客户管理后台", url_for("api.admin_console_home")),
                ("客户", url_for("api.admin_console_customers")),
                (external_userid, None),
            ),
            actions=[{"label": "返回客户列表", "href": url_for("api.admin_console_customers"), "variant": "secondary"}],
            state_title="客户不存在",
            state_body="请确认客户编号是否正确，或稍后重试。",
            state_items=["检查客户编号是否输入正确", "确认当前环境已经同步到该客户数据"],
            page_error=page_error or "未找到客户",
        ), 404

    return _render_admin_template(
        "customer_detail.html",
        active_nav="customers",
        page_title=payload["customer"].get("customer_name") or external_userid,
        page_summary="查看客户资料、沟通记录、标签、任务和问卷记录。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("客户", url_for("api.admin_console_customers")),
            (payload["customer"].get("customer_name") or external_userid, None),
        ),
        customer_payload=payload,
        customer_tabs=_customer_tabs(external_userid, active_tab),
        active_tab=active_tab,
        page_notice=page_notice,
        page_error=page_error,
        action_result=action_result or {},
        active_action=active_action,
    )


def admin_console_customer_detail(external_userid: str):
    active_tab = str(request.args.get("tab") or "basic").strip() or "basic"
    return _render_customer_detail_page(external_userid, active_tab=active_tab)


def admin_console_customer_tag_action(external_userid: str):
    active_tab = str(request.form.get("return_tab") or "tags").strip() or "tags"
    operator = str(request.form.get("operator") or request.headers.get("X-Admin-Operator") or "").strip()
    try:
        if request.form.get("confirm"):
            action_result = execute_customer_tag_action(
                external_userid=external_userid,
                userid=str(request.form.get("userid") or "").strip(),
                action=str(request.form.get("tag_action") or "").strip(),
                tag_ids=str(request.form.get("tag_ids") or "").strip().split(","),
                operator=operator,
            )
            return _render_customer_detail_page(
                external_userid,
                active_tab=active_tab,
                page_notice="标签操作已执行，并已记录操作人和时间。",
                action_result=action_result,
                active_action="tags",
            )
        action_result = preview_customer_tag_action(
            external_userid=external_userid,
            userid=str(request.form.get("userid") or "").strip(),
            action=str(request.form.get("tag_action") or "").strip(),
            tag_ids=str(request.form.get("tag_ids") or "").strip().split(","),
        )
        return _render_customer_detail_page(
            external_userid,
            active_tab=active_tab,
            page_notice="这里会先展示操作预览，确认后才会真正执行。",
            action_result=action_result,
            active_action="tags",
        )
    except Exception as exc:
        return _render_customer_detail_page(
            external_userid,
            active_tab=active_tab,
            page_error=str(exc),
            active_action="tags",
        )


def admin_console_customer_task_action(external_userid: str):
    active_tab = str(request.form.get("return_tab") or "tasks").strip() or "tasks"
    operator = str(request.form.get("operator") or request.headers.get("X-Admin-Operator") or "").strip()
    try:
        if request.form.get("confirm"):
            action_result = execute_customer_task_action(
                external_userid=external_userid,
                task_type=str(request.form.get("task_type") or "").strip(),
                userid=str(request.form.get("userid") or "").strip(),
                content=str(request.form.get("content") or "").strip(),
                operator=operator,
            )
            return _render_customer_detail_page(
                external_userid,
                active_tab=active_tab,
                page_notice="触达任务已执行，并已记录操作人和时间。",
                action_result=action_result,
                active_action="tasks",
            )
        action_result = preview_customer_task_action(
            external_userid=external_userid,
            task_type=str(request.form.get("task_type") or "").strip(),
            userid=str(request.form.get("userid") or "").strip(),
            content=str(request.form.get("content") or "").strip(),
        )
        return _render_customer_detail_page(
            external_userid,
            active_tab=active_tab,
            page_notice="这里会先展示操作预览，确认后才会真正执行。",
            action_result=action_result,
            active_action="tasks",
        )
    except Exception as exc:
        return _render_customer_detail_page(
            external_userid,
            active_tab=active_tab,
            page_error=str(exc),
            active_action="tasks",
        )


def register_routes(bp):
    bp.route("/admin/customers", methods=["GET"])(admin_console_customers)
    bp.route("/admin/customers/<external_userid>", methods=["GET"])(admin_console_customer_detail)
    bp.route("/admin/customers/<external_userid>/tags", methods=["POST"])(admin_console_customer_tag_action)
    bp.route("/admin/customers/<external_userid>/tasks", methods=["POST"])(admin_console_customer_task_action)
