from __future__ import annotations

from flask import render_template, url_for

from ..domains.admin_audit import build_legacy_admin_path_rows, build_risk_control_rows, build_runbook_rows
from ..domains.admin_dashboard import (
    build_admin_shell_status,
    build_dashboard_summary,
    build_dashboard_todos,
    build_system_status_payload,
    list_admin_navigation,
)


def _breadcrumb_items(*items: tuple[str, str | None]) -> list[dict[str, str]]:
    return [
        {"label": label, "href": href or ""}
        for label, href in items
    ]


def _shell_links() -> list[dict[str, str]]:
    return [
        {"label": "MCP Preflight", "href": "/admin/mcp"},
        {"label": "Questionnaire Preflight", "href": "/admin/questionnaires"},
        {"label": "审计", "href": "/admin/audit"},
        {"label": "Runbooks", "href": "/admin/system"},
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
        shell_links=_shell_links(),
        **extra,
    )


def admin_console_home():
    quick_links = [
        {
            "label": "去客户中心",
            "description": "进入统一客户入口，查看列表、详情、timeline、recent messages、tags、tasks 和 routing context。",
            "href": url_for("api.admin_console_customers"),
        },
        {
            "label": "去问卷中心",
            "description": "查看问卷定义、提交情况、preflight、SCRM apply 结果与公开路径。",
            "href": url_for("api.admin_console_questionnaires"),
        },
        {
            "label": "去运营看板",
            "description": "把 user_ops、class_user 和 imports 放进一个统一运营模块。",
            "href": url_for("api.admin_console_user_ops"),
        },
        {
            "label": "去同步与任务",
            "description": "查看 archive sync、callbacks、message batches 和 deferred jobs 的统一运行面板。",
            "href": url_for("api.admin_console_jobs"),
        },
        {
            "label": "去 MCP 控制台",
            "description": "查看 MCP registry、runtime 状态、preflight 和安全 sample call。",
            "href": url_for("api.admin_console_mcp"),
        },
        {
            "label": "去配置中心",
            "description": "进入统一配置入口，后续承接 routing / settings / tags。",
            "href": url_for("api.admin_config_home"),
        },
        {
            "label": "去审计中心",
            "description": "查询后台写操作、配置变更、preview / live run 和最近风险动作。",
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
        page_summary="CRM Console 首页现在直接展示系统状态、业务总览和待处理事项，所有指标都复用现有 domain 读模型，不在 controller 里拼装 SQL。",
        breadcrumbs=_breadcrumb_items(("CRM Console", url_for("api.admin_console_home")), ("工作台", None)),
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
        page_title="系统",
        page_summary="系统页统一展示环境、release、health、runbook、风险控制策略和 legacy admin path 兼容结论，避免后台长期漂成无人维护的并行集合。",
        breadcrumbs=_breadcrumb_items(("CRM Console", url_for("api.admin_console_home")), ("系统", None)),
        system_status=build_system_status_payload(),
        runbook_rows=build_runbook_rows(),
        risk_rows=build_risk_control_rows(),
        legacy_rows=build_legacy_admin_path_rows(),
    )


def admin_console_legacy_user_ops():
    return render_template("admin_user_ops.html")


def admin_console_legacy_questionnaires():
    return render_template("admin_questionnaires.html")


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
