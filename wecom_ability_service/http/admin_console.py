from __future__ import annotations

from flask import render_template, url_for

from ..domains.admin_audit import build_risk_control_rows, build_runbook_rows
from ..domains.admin_dashboard import (
    build_admin_shell_status,
    build_dashboard_summary,
    build_dashboard_todos,
    build_system_status_payload,
    list_admin_navigation,
)
from ..domains.followup_orchestrator import is_followup_orchestrator_enabled
from ..domains.customer_pulse import is_customer_pulse_inbox_enabled
from ..domains.customer_pulse.access import (
    CUSTOMER_PULSE_PERMISSION_PAGE_VISIBLE,
    current_customer_pulse_request_access_context,
    customer_pulse_has_permission,
)
from .common import _deprecated_admin_redirect


def _breadcrumb_items(*items: tuple[str, str | None]) -> list[dict[str, str]]:
    return [
        {"label": label, "href": href or ""}
        for label, href in items
    ]

def _render_admin_template(
    template_name: str,
    *,
    active_nav: str,
    page_title: str,
    page_summary: str,
    breadcrumbs: list[dict[str, str]],
    **extra,
):
    return render_template(
        f"admin_console/{template_name}",
        page_title=page_title,
        page_summary=page_summary,
        breadcrumbs=breadcrumbs,
        nav_items=list_admin_navigation(active_nav),
        shell_status=build_admin_shell_status(),
        show_shell_meta=extra.pop("show_shell_meta", True),
        **extra,
    )


def render_admin_user_ops_shell():
    return _render_admin_template(
        "user_ops.html",
        active_nav="operations",
        page_title="运营管理",
        page_summary="转化链路运营页。当前页只针对有班期标识的引流品用户做筛选、客户详情复用、批量群发、免打扰和发送记录。",
        breadcrumbs=_breadcrumb_items(("客户管理后台", url_for("api.admin_console_home")), ("运营", None)),
    )


def admin_console_home():
    access_context = current_customer_pulse_request_access_context()
    customer_pulse_page_visible = is_customer_pulse_inbox_enabled(access_context=access_context) and customer_pulse_has_permission(
        CUSTOMER_PULSE_PERMISSION_PAGE_VISIBLE,
        access_context=access_context,
    )
    followup_orchestrator_page_visible = is_followup_orchestrator_enabled(access_context=access_context) and customer_pulse_has_permission(
        CUSTOMER_PULSE_PERMISSION_PAGE_VISIBLE,
        access_context=access_context,
    )
    quick_links = [
        {
            "label": "进入客户中心",
            "description": "查看客户资料、沟通记录、标签和任务。",
            "href": url_for("api.admin_console_customers"),
        },
        {
            "label": "进入问卷中心",
            "description": "管理问卷、查看提交结果和发布状态。",
            "href": url_for("api.admin_console_questionnaires"),
        },
        {
            "label": "进入运营管理",
            "description": "查看运营名单、班期、导入记录和作业状态。",
            "href": url_for("api.admin_console_user_ops"),
        },
        *(
            [
                {
                    "label": "进入 AI推进",
                    "description": "按行动卡流查看今天该跟进谁、先做什么。",
                    "href": url_for("api.admin_customer_pulse_inbox"),
                }
            ]
            if customer_pulse_page_visible
            else []
        ),
        *(
            [
                {
                    "label": "进入团队编排",
                    "description": "按任务包、波次和团队负载查看今天谁接谁、哪些客户需要升级。",
                    "href": url_for("api.admin_followup_orchestrator"),
                }
            ]
            if followup_orchestrator_page_visible
            else []
        ),
        {
            "label": "进入同步任务",
            "description": "查看聊天同步、回调状态、消息批次和待处理作业。",
            "href": url_for("api.admin_console_jobs"),
        },
        {
            "label": "进入 AI 工具",
            "description": "查看 AI 工具状态，并做安全试运行。",
            "href": url_for("api.admin_console_mcp"),
        },
        {
            "label": "进入配置中心",
            "description": "维护负责人、分配规则、标签规则和系统设置。",
            "href": url_for("api.admin_config_home"),
        },
        {
            "label": "进入操作记录",
            "description": "查看后台关键操作和修改记录。",
            "href": url_for("api.admin_audit_logs"),
        },
    ]
    system_status = build_system_status_payload()
    dashboard_summary = build_dashboard_summary()
    dashboard_todos = build_dashboard_todos()
    return _render_admin_template(
        "dashboard.html",
        active_nav="workbench",
        page_title="工作台",
        page_summary="在这里可以快速查看系统是否正常、关键业务数据以及待处理事项。",
        breadcrumbs=_breadcrumb_items(("客户管理后台", url_for("api.admin_console_home")), ("工作台", None)),
        system_status=system_status,
        dashboard_summary=dashboard_summary,
        dashboard_cards=dashboard_summary["cards"],
        todo_groups=dashboard_todos["groups"],
        todo_total=dashboard_todos["total_pending"],
        quick_links=quick_links,
    )


def admin_console_system():
    return _render_admin_template(
        "system.html",
        active_nav="system",
        page_title="系统与帮助",
        page_summary="这里可以查看系统状态、常见入口和使用提醒。",
        breadcrumbs=_breadcrumb_items(("客户管理后台", url_for("api.admin_console_home")), ("系统", None)),
        system_status=build_system_status_payload(),
        runbook_rows=build_runbook_rows(),
        risk_rows=build_risk_control_rows(),
    )


def admin_console_legacy_user_ops():
    return render_admin_user_ops_shell()


def admin_console_legacy_questionnaires():
    return _deprecated_admin_redirect("api.admin_console_questionnaires")


def admin_console_legacy_class_user_management():
    return render_template("admin_class_user_management.html")


def admin_console_legacy_class_user_backoffice():
    return render_template("admin_class_user_backoffice.html")


def register_routes(bp):
    bp.route("/admin", methods=["GET"])(admin_console_home)
    bp.route("/admin/system", methods=["GET"])(admin_console_system)
    bp.route("/admin/_legacy/user-ops", methods=["GET"])(admin_console_legacy_user_ops)
    bp.route("/admin/_legacy/questionnaires", methods=["GET"])(admin_console_legacy_questionnaires)
    bp.route("/admin/_legacy/class-user-management", methods=["GET"])(admin_console_legacy_class_user_management)
    bp.route("/admin/_legacy/class-user-backoffice", methods=["GET"])(admin_console_legacy_class_user_backoffice)
