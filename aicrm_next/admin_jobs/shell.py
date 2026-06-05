from __future__ import annotations

from urllib.parse import quote, urlencode

from fastapi import Request


def legacy_url_for(name: str, **path_params: object) -> str:
    if name == "static":
        return "/static/" + str(path_params.get("filename", "")).lstrip("/")
    if name == "api.admin_console_customer_detail":
        external_userid = str(path_params.get("external_userid", ""))
        return f"/admin/customers/{quote(external_userid, safe='')}"
    program_id = str(path_params.get("program_id") or "").strip()
    program_route_map = {
        "api.admin_automation_program_setup": "setup",
        "api.admin_automation_program_overview": "overview",
        "api.admin_automation_program_update": "update",
        "api.admin_automation_program_copy_form": "copy",
        "api.admin_automation_program_copy": "copy",
        "api.admin_automation_program_pause": "pause",
        "api.admin_automation_program_activate": "activate",
        "api.admin_automation_program_archive": "archive",
        "api.admin_automation_program_entry_channels": "entry-channels",
    }
    if name in program_route_map and program_id:
        base = f"/admin/automation-conversion/programs/{program_id}/{program_route_map[name]}"
        query = {
            key: value
            for key, value in path_params.items()
            if key != "program_id" and value not in (None, "")
        }
        return base + (f"?{urlencode(query)}" if query else "")
    path_map = {
        "api.admin_console_dashboard": "/admin",
        "api.admin_console_customers": "/admin/customers",
        "api.admin_owner_migration_page": "/admin/owner-migration",
        "api.admin_owner_migration_action": "/admin/owner-migration",
        "api.admin_user_ops_ui": "/admin/user-ops/ui",
        "api.admin_hxc_dashboard_workspace": "/admin/hxc-dashboard",
        "api.admin_hxc_send_config_page": "/admin/hxc-send-config",
        "api.admin_cloud_orchestrator_workspace": "/admin/cloud-orchestrator/plans",
        "api.admin_cloud_orchestrator_plans_workspace": "/admin/cloud-orchestrator/plans",
        "api.admin_cloud_orchestrator_plan_detail": "/admin/cloud-orchestrator/plans/"
        + quote(str(path_params.get("plan_id", "")).strip(), safe=""),
        "api.admin_cloud_orchestrator_campaigns_workspace": "/admin/cloud-orchestrator/campaigns",
        "api.admin_cloud_orchestrator_observability": "/admin/cloud-orchestrator/observability",
        "api.admin_wecom_tags_page": "/admin/wecom-tags",
        "api.admin_channels_page": "/admin/channels",
        "api.admin_channel_new_page": "/admin/channels/new",
        "api.admin_channel_edit_page": "/admin/channels/" + str(path_params.get("channel_id", "")).strip() + "/edit",
        "api.admin_automation_program_entry_channels": "/admin/automation-conversion/programs/"
        + str(path_params.get("program_id", "")).strip()
        + "/entry-channels",
        "api.admin_questionnaires": "/admin/questionnaires",
        "api.admin_console_questionnaires": "/admin/questionnaires",
        "api.admin_console_questionnaire_new": "/admin/questionnaires/new",
        "api.admin_radar_links": "/admin/radar-links",
        "api.admin_radar_link_new": "/admin/radar-links/new",
        "api.admin_radar_link_edit": "/admin/radar-links/" + str(path_params.get("link_id", "")).strip() + "/edit",
        "api.admin_radar_link_detail": "/admin/radar-links/" + str(path_params.get("link_id", "")).strip() + "/detail",
        "api.admin_automation_conversion": "/admin/automation-conversion",
        "api.admin_group_ops_ui": "/admin/automation-conversion/group-ops/ui",
        "api.admin_group_ops_plan_detail": "/admin/automation-conversion/group-ops/plans/"
        + str(path_params.get("plan_id", "")).strip(),
        "api.admin_group_ops_groups_ui": "/admin/automation-conversion/group-ops/groups/ui",
        "api.admin_jobs": "/admin/jobs",
        "api.admin_broadcast_jobs": "/admin/broadcast-jobs",
        "api.admin_console_jobs_action": "/admin/jobs/actions",
        "api.admin_wechat_pay_transactions_page": "/admin/wechat-pay/transactions",
        "api.admin_wechat_pay_transaction_detail_page": "/admin/wechat-pay/transactions/"
        + str(path_params.get("order_id", "")).strip(),
        "api.admin_wechat_pay_products_page": "/admin/wechat-pay/products",
        "api.admin_alipay_transactions_page": "/admin/alipay/transactions",
        "api.admin_image_library_workspace": "/admin/image-library",
        "api.admin_miniprogram_library_workspace": "/admin/miniprogram-library",
        "api.admin_attachment_library_workspace": "/admin/attachment-library",
        "api.admin_config": "/admin/config",
        "api.admin_config_home": "/admin/config",
        "api.admin_api_docs": "/admin/api-docs",
        "api.admin_console_api_docs": "/admin/api-docs",
        "api.admin_console_jobs": "/admin/jobs",
        "api.admin_dashboard_shell_context": "/api/admin/dashboard/shell-context",
        "api.admin_logout": "/logout",
    }
    base = path_map.get(name, "#")
    query = {key: value for key, value in path_params.items() if value not in (None, "")}
    return base + (f"?{urlencode(query)}" if query else "")


ADMIN_NAV_GROUPS = [
    {
        "title": "运营",
        "items": [
            {"key": "automation_conversion", "label": "自动化运营", "endpoint": "api.admin_automation_conversion"},
            {"key": "group_ops", "label": "群运营计划", "endpoint": "api.admin_group_ops_ui"},
            {"key": "channels", "label": "渠道码中心", "endpoint": "api.admin_channels_page"},
            {"key": "cloud_orchestrator", "label": "AI 助手", "endpoint": "api.admin_cloud_orchestrator_workspace"},
            {"key": "customers", "label": "客户激活 / 客户列表", "endpoint": "api.admin_console_customers"},
            {"key": "user_ops_funnel", "label": "漏斗 / 数据看板", "endpoint": "api.admin_hxc_dashboard_workspace"},
            {"key": "questionnaires", "label": "问卷", "endpoint": "api.admin_questionnaires"},
            {"key": "radar_links", "label": "内容雷达", "endpoint": "api.admin_radar_links"},
            {"key": "wecom_tags", "label": "企微标签管理", "endpoint": "api.admin_wecom_tags_page"},
        ],
    },
    {
        "title": "交易",
        "items": [
            {"key": "wechat_pay_transactions", "label": "交易管理", "endpoint": "api.admin_wechat_pay_transactions_page"},
            {"key": "wechat_pay_products", "label": "商品管理", "endpoint": "api.admin_wechat_pay_products_page"},
        ],
    },
    {
        "title": "素材",
        "items": [
            {"key": "image_library", "label": "图片素材库", "endpoint": "api.admin_image_library_workspace"},
            {"key": "miniprogram_library", "label": "小程序素材库", "endpoint": "api.admin_miniprogram_library_workspace"},
            {"key": "attachment_library", "label": "附件素材库", "endpoint": "api.admin_attachment_library_workspace"},
        ],
    },
    {
        "title": "配置及后台",
        "items": [
            {"key": "jobs", "label": "同步任务配置 / 同步任务", "endpoint": "api.admin_jobs"},
            {"key": "owner_migration", "label": "负责人迁移", "endpoint": "api.admin_owner_migration_page"},
            {"key": "config", "label": "配置", "endpoint": "api.admin_config"},
            {"key": "api_docs", "label": "API 文档", "endpoint": "api.admin_api_docs"},
        ],
    },
]


def nav_items(active_endpoint: str) -> list[dict]:
    groups: list[dict] = []
    for group in ADMIN_NAV_GROUPS:
        items = [{**item, "active": item["endpoint"] == active_endpoint} for item in group["items"]]
        groups.append({**group, "items": items, "active": any(item["active"] for item in items)})
    return groups


def shell_context(
    *,
    request: Request,
    page_title: str,
    page_summary: str,
    active_endpoint: str,
) -> dict:
    return {
        "request": request,
        "page_title": page_title,
        "page_summary": page_summary,
        "breadcrumbs": [{"label": "客户管理后台", "href": request.url_for("api.admin_console_dashboard")}],
        "nav_items": nav_items(active_endpoint),
        "current_admin_user": None,
        "show_shell_meta": False,
        "shell_status": {"environment": {"tone": "prod", "label": "AI-CRM Next"}, "health": {"state": "ok", "label": "OK", "detail": "postgres"}},
        "page_notice": "",
        "page_error": "",
        "url_for": legacy_url_for,
    }
