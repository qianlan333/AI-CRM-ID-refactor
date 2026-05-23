from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from aicrm_next.shared.runtime import production_data_ready
from aicrm_next.integration_gateway.legacy_flask_facade import forward_to_legacy_flask
from aicrm_next.admin_read_model.application import (
    GetAdminApiDocsPageQuery,
    GetAdminConfigPageQuery,
    GetAdminFunnelPageQuery,
    GetAdminJobsPageQuery,
    GetAdminMediaPageQuery,
    GetAdminProductsPageQuery,
    GetAdminTransactionsPageQuery,
    GetAdminWeComTagsPageQuery,
    page_row_count,
)
from aicrm_next.automation_engine.application import ListAutomationExecutionRecordsQuery, ListAutomationPoolsQuery
from aicrm_next.customer_read_model.dto import ListCustomersRequest
from aicrm_next.questionnaire.application import GetQuestionnaireDetailQuery, GetQuestionnairePreflightQuery
from aicrm_next.integration_gateway.legacy_customer_read_facade import list_customers_via_legacy
from aicrm_next.integration_gateway.legacy_automation_facade import LegacyAutomationDataUnavailable, list_automation_programs_from_legacy
from aicrm_next.integration_gateway.legacy_questionnaire_facade import (
    LegacyQuestionnaireDataUnavailable,
    get_questionnaire_detail_from_legacy,
    list_questionnaires_from_legacy,
)

router = APIRouter()
_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=_TEMPLATES_DIR)

LEGACY_FRONTEND_ROUTES = [
    "/admin",
    "/admin/customers",
    "/admin/questionnaires",
    "/admin/questionnaires/new",
    "/admin/questionnaires/{questionnaire_id}",
    "/admin/questionnaires/external-push-logs",
    "/admin/questionnaires/external-push-logs/retry-batch",
    "/admin/questionnaires/external-push-logs/{push_log_id}/retry",
    "/admin/questionnaires/{questionnaire_id}/external-push-logs",
    "/admin/questionnaires/{questionnaire_id}/external-push-logs/retry-batch",
    "/admin/questionnaires/{questionnaire_id}/external-push-logs/{push_log_id}/retry",
    "/admin/user-ops/ui",
    "/admin/user-ops",
    "/admin/hxc-dashboard",
    "/admin/hxc-send-config",
    "/admin/cloud-orchestrator",
    "/admin/cloud-orchestrator/campaigns",
    "/admin/cloud-orchestrator/observability",
    "/admin/wecom-tags",
    "/admin/channels",
    "/admin/channels/new",
    "/admin/channels/{channel_id}/edit",
    "/admin/automation-conversion",
    "/admin/automation-conversion/programs/{program_id}/entry-channels",
    "/admin/jobs",
    "/admin/wechat-pay/transactions",
    "/admin/wechat-pay/transactions/{order_id}",
    "/admin/wechat-pay/products",
    "/admin/alipay/transactions",
    "/admin/image-library",
    "/admin/miniprogram-library",
    "/admin/attachment-library",
    "/admin/config",
    "/admin/api-docs",
]


@router.get("/sidebar/bind-mobile", name="api.sidebar_bind_mobile_page")
async def sidebar_bind_mobile_page(request: Request):
    enabled = str(os.getenv("SIDEBAR_WORKBENCH_V2_ENABLED", "true")).strip().lower()
    if enabled in {"0", "false", "no", "off"} or str(request.query_params.get("v") or "").strip().lower() == "legacy":
        return await forward_to_legacy_flask(request)
    return templates.TemplateResponse(
        request,
        "sidebar_customer_workbench.html",
        {"request": request, "debug_enabled": False},
    )


def _legacy_url_for(name: str, **path_params: object) -> str:
    if name == "static":
        return "/static/" + str(path_params.get("filename", "")).lstrip("/")
    if name == "api.admin_console_customer_detail":
        external_userid = str(path_params.get("external_userid", ""))
        return f"/admin/customers/{external_userid}"
    program_id = str(path_params.get("program_id") or "").strip()
    program_route_map = {
        "api.admin_automation_program_setup": "setup",
        "api.admin_automation_program_overview": "overview",
        "api.admin_automation_program_copy": "copy",
        "api.admin_automation_program_pause": "pause",
        "api.admin_automation_program_activate": "activate",
        "api.admin_automation_program_archive": "archive",
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
        "api.admin_user_ops_ui": "/admin/user-ops/ui",
        "api.admin_hxc_dashboard_workspace": "/admin/hxc-dashboard",
        "api.admin_hxc_send_config_page": "/admin/hxc-send-config",
        "api.admin_cloud_orchestrator_workspace": "/admin/cloud-orchestrator/campaigns",
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
        "api.admin_console_global_questionnaire_external_push_logs": "/admin/questionnaires/external-push-logs",
        "api.admin_console_global_questionnaire_external_push_logs_retry_batch": "/admin/questionnaires/external-push-logs/retry-batch",
        "api.admin_console_global_questionnaire_external_push_logs_retry": "/admin/questionnaires/external-push-logs/"
        + str(path_params.get("push_log_id", "")).strip()
        + "/retry",
        "api.admin_console_questionnaire_external_push_logs": "/admin/questionnaires/"
        + str(path_params.get("questionnaire_id", "")).strip()
        + "/external-push-logs",
        "api.admin_console_questionnaire_external_push_logs_retry_batch": "/admin/questionnaires/"
        + str(path_params.get("questionnaire_id", "")).strip()
        + "/external-push-logs/retry-batch",
        "api.admin_console_questionnaire_external_push_logs_retry": "/admin/questionnaires/"
        + str(path_params.get("questionnaire_id", "")).strip()
        + "/external-push-logs/"
        + str(path_params.get("push_log_id", "")).strip()
        + "/retry",
        "api.admin_automation_conversion": "/admin/automation-conversion",
        "api.admin_jobs": "/admin/jobs",
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
        "api.admin_logout": "/admin/logout",
    }
    base = path_map.get(name, "#")
    query = {key: value for key, value in path_params.items() if value not in (None, "")}
    return base + (f"?{urlencode(query)}" if query else "")


ADMIN_NAV_GROUPS = [
    {
        "title": "运营",
        "items": [
            {"key": "automation_conversion", "label": "自动化运营", "endpoint": "api.admin_automation_conversion"},
            {"key": "channels", "label": "渠道码中心", "endpoint": "api.admin_channels_page"},
            {"key": "cloud_orchestrator", "label": "AI 助手", "endpoint": "api.admin_cloud_orchestrator_workspace"},
            {"key": "customers", "label": "客户激活 / 客户列表", "endpoint": "api.admin_console_customers"},
            {"key": "user_ops_funnel", "label": "漏斗 / 数据看板", "endpoint": "api.admin_hxc_dashboard_workspace"},
            {"key": "questionnaires", "label": "问卷", "endpoint": "api.admin_questionnaires"},
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
            {"key": "config", "label": "配置", "endpoint": "api.admin_config"},
            {"key": "api_docs", "label": "API 文档", "endpoint": "api.admin_api_docs"},
        ],
    },
]


def _nav_items(active_endpoint: str) -> list[dict]:
    groups: list[dict] = []
    for group in ADMIN_NAV_GROUPS:
        items = [{**item, "active": item["endpoint"] == active_endpoint} for item in group["items"]]
        groups.append({**group, "items": items, "active": any(item["active"] for item in items)})
    return groups


def _shell_context(
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
        "nav_items": _nav_items(active_endpoint),
        "current_admin_user": None,
        "show_shell_meta": False,
        "shell_status": {"environment": {"tone": "prod", "label": "AI-CRM Next"}, "health": {"state": "ok", "label": "OK", "detail": "postgres"}},
        "page_notice": "",
        "page_error": "",
        "url_for": _legacy_url_for,
    }


def _real_data_context(context: dict, *, payload: dict, title: str, summary: str) -> dict:
    context.update(
        {
            "real_data_payload": payload,
            "data_title": title,
            "data_summary": summary,
            "real_data_row_count": page_row_count(payload),
        }
    )
    if payload.get("page_error"):
        context["page_error"] = payload["page_error"]
    return context


def _is_assessment_template_asset(questionnaire: dict | None) -> bool:
    if not questionnaire or not questionnaire.get("assessment_enabled"):
        return False
    config = questionnaire.get("assessment_config") if isinstance(questionnaire.get("assessment_config"), dict) else {}
    asset_kind = str(config.get("asset_kind") or "").strip()
    if asset_kind:
        return asset_kind == "assessment_template"
    return str(config.get("template_id") or "").strip() == "siyuan_ip_business"


def _questionnaire_editor_response(
    request: Request,
    *,
    questionnaire_id: int | None = None,
):
    payload: dict | None = None
    page_error = ""
    if questionnaire_id is not None:
        try:
            payload = (
                get_questionnaire_detail_from_legacy(questionnaire_id)
                if production_data_ready()
                else GetQuestionnaireDetailQuery()(questionnaire_id)
            )
        except Exception as exc:
            context = _shell_context(
                request=request,
                page_title="问卷不存在",
                page_summary="当前没有找到这个问卷。",
                active_endpoint="api.admin_questionnaires",
            )
            context.update(
                {
                    "state_title": "问卷不存在",
                    "state_body": "请确认问卷编号是否正确，或稍后重试。",
                    "state_items": ["问卷可能已被删除", "当前环境也可能还没有初始化相关数据"],
                    "actions": [{"label": "返回问卷管理", "href": "/admin/questionnaires", "variant": "secondary"}],
                    "page_error": f"未找到问卷：{exc}",
                }
            )
            return templates.TemplateResponse(request, "admin_console/placeholder.html", context, status_code=404)

    questionnaire = jsonable_encoder((payload or {}).get("questionnaire")) if payload else None
    if questionnaire is not None and isinstance(payload, dict):
        questionnaire["questions"] = jsonable_encoder(
            questionnaire.get("questions") or payload.get("questions") or []
        )
    default_assessment = (
        (questionnaire_id is None and str(request.query_params.get("mode") or "").strip() == "assessment")
        or _is_assessment_template_asset(questionnaire)
    )
    new_heading = "创建测评问卷模板" if default_assessment else "新建问卷"
    edit_heading = "编辑测评问卷模板" if default_assessment else "编辑问卷"
    new_subtitle = (
        "配置测评题目、维度分型和结果页规则，保存后可作为普通问卷的整组引用模板。"
        if default_assessment
        else "从空白模板开始搭建题目、标签和分数规则。"
    )
    edit_subtitle = (
        "维护这个测评模板的题目、维度分型和结果页规则。"
        if default_assessment
        else "维护当前问卷的题目、分数规则和发布设置。"
    )
    return templates.TemplateResponse(
        request,
        "admin_questionnaires.html",
        {
            "request": request,
            "editor_mode": "edit" if questionnaire_id is not None else "new",
            "editor_page_title": (questionnaire or {}).get("title")
            or (questionnaire or {}).get("name")
            or (edit_heading if questionnaire_id is not None else new_heading),
            "editor_heading": edit_heading if questionnaire_id is not None else new_heading,
            "editor_subtitle": edit_subtitle if questionnaire_id is not None else new_subtitle,
            "editor_back_href": "/admin/questionnaires",
            "editor_default_assessment": default_assessment,
            "initial_questionnaire": questionnaire,
            "initial_questionnaire_id": questionnaire_id,
            "page_error": page_error,
        },
    )


@router.get("/admin", name="api.admin_console_dashboard")
def admin_dashboard(request: Request):
    context = _shell_context(
        request=request,
        page_title="自动化运营",
        page_summary="AI-CRM Next 后台总览，生产数据通过 PostgreSQL 与兼容 facade 提供。",
        active_endpoint="api.admin_automation_conversion",
    )
    context.update(
        {
            "system_status": {
                "cards": [
                    {"label": "FastAPI", "value": "ok", "description": "Next 后端可响应后台 shell。", "tone": "ok"},
                    {"label": "Frontend parity", "value": "live", "description": "后台 shell 已切换为分组导航与生产数据入口。", "tone": "ok"},
                ]
            },
            "dashboard_cards": [
                {"label": "客户", "value": "postgres", "description": "客户列表走生产 PostgreSQL。", "href": request.url_for("api.admin_console_customers")},
                {"label": "自动化运营", "value": "postgres", "description": "自动化运营页优先使用生产数据。", "href": request.url_for("api.admin_automation_conversion")},
            ],
            "todo_total": 0,
            "todo_groups": [],
            "quick_links": [
                {"label": "客户激活 / 客户列表", "description": "查看客户列表和激活状态。", "href": request.url_for("api.admin_console_customers")},
                {"label": "AI 助手", "description": "进入 AI 助手兼容入口。", "href": request.url_for("api.admin_cloud_orchestrator_workspace")},
            ],
        }
    )
    return templates.TemplateResponse(request, "admin_console/dashboard.html", context)


@router.get("/admin/customers", name="api.admin_console_customers")
def admin_customers(request: Request, keyword: str = "", owner: str = "", mobile: str = "", tag: str = "", offset: int = 0):
    limit = 50
    customer_query = ListCustomersRequest(
        owner_userid=owner or None,
        tag=tag or None,
        mobile=mobile or None,
        keyword=keyword or None,
        limit=limit,
        offset=offset,
    )
    if production_data_ready():
        try:
            payload = list_customers_via_legacy(customer_query)
        except Exception as exc:
            payload = {"customers": [], "total": 0}
            page_error = f"生产客户数据读取失败：{exc}"
        else:
            page_error = ""
    else:
        payload = {
            "customers": [
                {
                    "external_userid": "local_contract_customer",
                    "customer_name": "本地结构校验客户",
                    "owner_display_name": "system",
                    "owner_userid": "system",
                    "mobile": "已脱敏",
                }
            ],
            "total": 1,
        }
        page_error = ""
    customer_payload = {
        "filters": {"keyword": keyword, "owner": owner, "mobile": mobile, "tag": tag},
        "customers": payload["customers"],
        "pagination": {
            "total": payload["total"],
            "has_prev": offset > 0,
            "has_next": offset + limit < payload["total"],
            "prev_offset": max(offset - limit, 0),
            "next_offset": offset + limit,
        },
    }
    context = _shell_context(
        request=request,
        page_title="客户激活 / 客户列表",
        page_summary="查看客户列表、筛选客户并打开客户档案。",
        active_endpoint="api.admin_console_customers",
    )
    context["page_error"] = page_error
    context["customer_payload"] = customer_payload
    return templates.TemplateResponse(request, "admin_console/customers.html", context)


@router.get("/admin/user-ops/ui", name="api.admin_user_ops_ui")
def admin_user_ops_ui(request: Request):
    context = _shell_context(
        request=request,
        page_title="客户激活 / 客户列表",
        page_summary="客户激活与运营入口读取生产客户、问卷、交易与自动化统计。",
        active_endpoint="api.admin_console_customers",
    )
    payload = GetAdminFunnelPageQuery()()
    _real_data_context(
        context,
        payload=payload,
        title="客户激活 / 客户列表",
        summary="生产客户、问卷、订单和自动化成员统计。",
    )
    return templates.TemplateResponse(request, "admin_console/real_data_page.html", context)


@router.get("/admin/user-ops", name="api.admin_user_ops_legacy_redirect")
def admin_user_ops_funnel(request: Request):
    return RedirectResponse(url=_legacy_url_for("api.admin_hxc_dashboard_workspace"), status_code=302)


def _empty_hxc_dashboard_summary() -> dict:
    return {
        "total": 0,
        "funnel": {
            "member_and_user": 0,
            "only_member": 0,
            "user_no_member": 0,
            "inactive": 0,
        },
        "latest_refresh": {"started_at": "", "finished_at": "", "status": "local_contract_probe"},
    }


@router.get("/admin/hxc-dashboard", name="api.admin_hxc_dashboard_workspace")
def admin_hxc_dashboard(request: Request):
    context = _shell_context(
        request=request,
        page_title="用户激活漏斗看板",
        page_summary=(
            "CRM 三表手机号并集 × 黄小璨用户/会员/订阅/测评/成长目标/路径/任务/复盘/V6 角色评分 "
            "聚合, 每 30 分钟自动刷新. 列头可筛选, 表格右上角可导出 CSV / Excel."
        ),
        active_endpoint="api.admin_hxc_dashboard_workspace",
    )
    context["breadcrumbs"] = [
        {"label": "客户管理后台", "href": request.url_for("api.admin_console_dashboard")},
        {"label": "用户激活漏斗看板"},
    ]
    context.update(
        {
            "dashboard_rows": [],
            "dashboard_summary": _empty_hxc_dashboard_summary(),
            "send_configs": [],
        }
    )
    return templates.TemplateResponse(request, "admin_console/hxc_dashboard.html", context)


@router.get("/admin/hxc-send-config", name="api.admin_hxc_send_config_page")
def admin_hxc_send_config(request: Request):
    context = _shell_context(
        request=request,
        page_title="群发发送人管理",
        page_summary="从企微通讯录选择群发发送人，设置优先级和启用状态。",
        active_endpoint="api.admin_hxc_dashboard_workspace",
    )
    context["breadcrumbs"] = [
        {"label": "客户管理后台", "href": request.url_for("api.admin_console_dashboard")},
        {"label": "激活漏斗看板", "href": request.url_for("api.admin_hxc_dashboard_workspace")},
        {"label": "群发发送人管理"},
    ]
    context.update(
        {
            "directory_count": 0,
            "sender_count": 0,
            "active_sender_count": 0,
            "last_synced_at": "暂无",
            "members": [],
            "send_configs": [],
        }
    )
    return templates.TemplateResponse(request, "admin_console/hxc_send_config.html", context)


@router.get("/admin/cloud-orchestrator", name="api.admin_cloud_orchestrator_workspace")
def admin_cloud_orchestrator(request: Request):
    return RedirectResponse(
        url=_legacy_url_for("api.admin_cloud_orchestrator_campaigns_workspace"),
        status_code=302,
    )


@router.get("/admin/cloud-orchestrator/campaigns", name="api.admin_cloud_orchestrator_campaigns_workspace")
def admin_cloud_orchestrator_campaigns(request: Request):
    context = _shell_context(
        request=request,
        page_title="AI 助手 · 运营计划审阅",
        page_summary="Agent 上架的多分层多步骤运营计划在这里审阅启动。",
        active_endpoint="api.admin_cloud_orchestrator_workspace",
    )
    context["breadcrumbs"] = [
        {"label": "客户管理后台", "href": request.url_for("api.admin_console_dashboard")},
        {"label": "AI 助手", "href": request.url_for("api.admin_cloud_orchestrator_workspace")},
        {"label": "运营计划审阅"},
    ]
    context["page_actions"] = [
        {
            "label": "可观察性",
            "href": "/admin/cloud-orchestrator/observability",
            "variant": "ghost",
        },
    ]
    return templates.TemplateResponse(request, "admin_console/cloud_campaigns_workspace.html", context)


@router.get("/admin/cloud-orchestrator/observability", name="api.admin_cloud_orchestrator_observability")
def admin_cloud_orchestrator_observability(request: Request):
    context = _shell_context(
        request=request,
        page_title="Cloud Orchestrator · 可观察性",
        page_summary="工单、审计、漏斗与 Tool 调用统计按 trace_id 串联排查。",
        active_endpoint="api.admin_cloud_orchestrator_workspace",
    )
    context["breadcrumbs"] = [
        {"label": "客户管理后台", "href": request.url_for("api.admin_console_dashboard")},
        {"label": "AI 助手", "href": request.url_for("api.admin_cloud_orchestrator_workspace")},
        {"label": "可观察性"},
    ]
    context["page_actions"] = [
        {
            "label": "返回助手",
            "href": request.url_for("api.admin_cloud_orchestrator_campaigns_workspace"),
            "variant": "primary",
        },
    ]
    return templates.TemplateResponse(request, "admin_console/cloud_observability.html", context)


@router.get("/admin/wecom-tags", name="api.admin_wecom_tags_page")
def admin_wecom_tags(request: Request):
    context = _shell_context(
        request=request,
        page_title="企微标签管理",
        page_summary="管理企微标签分组和标签同步状态。",
        active_endpoint="api.admin_wecom_tags_page",
    )
    _real_data_context(
        context,
        payload=GetAdminWeComTagsPageQuery()(),
        title="企微标签管理",
        summary="展示本地已同步标签缓存、使用人数和同步前置状态；不调用远程企微接口。",
    )
    return templates.TemplateResponse(request, "admin_console/real_data_page.html", context)


@router.get("/admin/questionnaires", name="api.admin_questionnaires")
@router.get("/admin/questionnaires/ui", name="api.admin_console_questionnaires")
def admin_questionnaires(request: Request):
    if production_data_ready():
        try:
            list_payload = list_questionnaires_from_legacy(limit=100, offset=0)
        except LegacyQuestionnaireDataUnavailable as exc:
            list_payload = {"questionnaires": [], "items": [], "total": 0}
            preflight_error = f"生产问卷数据读取失败：{exc}"
        else:
            preflight_error = ""
    else:
        list_payload = {
            "questionnaires": [
                {
                    "id": "local_contract_questionnaire",
                    "slug": "local-contract-questionnaire",
                    "title": "本地结构校验问卷",
                    "name": "本地结构校验问卷",
                    "enabled": True,
                    "is_disabled": False,
                    "created_at": "2026-05-20T00:00:00Z",
                    "updated_at": "2026-05-20T00:00:00Z",
                    "submission_count": 0,
                    "assessment_enabled": False,
                    "public_path": "/s/local-contract-questionnaire",
                }
            ],
            "total": 1,
            "source_status": "local_contract_probe",
        }
        preflight_error = ""
    preflight_payload = GetQuestionnairePreflightQuery()()
    context = _shell_context(
        request=request,
        page_title="问卷管理",
        page_summary="读取生产问卷列表，保留新建、编辑、停用、删除和导出入口。",
        active_endpoint="api.admin_questionnaires",
    )
    questionnaires = jsonable_encoder(list_payload.get("questionnaires") or list_payload.get("items") or [])
    context["questionnaire_payload"] = {
        "questionnaires": questionnaires,
        "preflight": preflight_payload["checks"],
        "preflight_error": preflight_error,
        "total": list_payload.get("total", len(questionnaires)),
        "source_status": list_payload.get("source_status", "local_contract_probe"),
    }
    return templates.TemplateResponse(request, "admin_console/questionnaires.html", context)


@router.get("/admin/questionnaires/new", name="api.admin_console_questionnaire_new")
def admin_questionnaire_new(request: Request):
    return _questionnaire_editor_response(request)


@router.get("/admin/questionnaires/{questionnaire_id:int}", name="api.admin_console_questionnaire_detail")
def admin_questionnaire_detail(request: Request, questionnaire_id: int):
    return _questionnaire_editor_response(request, questionnaire_id=questionnaire_id)


@router.api_route(
    "/admin/questionnaires/external-push-logs",
    methods=["GET"],
    name="api.admin_console_global_questionnaire_external_push_logs",
)
@router.api_route(
    "/admin/questionnaires/external-push-logs/retry-batch",
    methods=["POST"],
    name="api.admin_console_global_questionnaire_external_push_logs_retry_batch",
)
@router.api_route(
    "/admin/questionnaires/external-push-logs/{push_log_id:int}/retry",
    methods=["POST"],
    name="api.admin_console_global_questionnaire_external_push_logs_retry",
)
@router.api_route(
    "/admin/questionnaires/{questionnaire_id:int}/external-push-logs",
    methods=["GET"],
    name="api.admin_console_questionnaire_external_push_logs",
)
@router.api_route(
    "/admin/questionnaires/{questionnaire_id:int}/external-push-logs/retry-batch",
    methods=["POST"],
    name="api.admin_console_questionnaire_external_push_logs_retry_batch",
)
@router.api_route(
    "/admin/questionnaires/{questionnaire_id:int}/external-push-logs/{push_log_id:int}/retry",
    methods=["POST"],
    name="api.admin_console_questionnaire_external_push_logs_retry",
)
async def admin_questionnaire_external_push_logs(request: Request) -> Response:
    return await forward_to_legacy_flask(request)


@router.get("/admin/automation-conversion", name="api.admin_automation_conversion")
def admin_automation_conversion(request: Request):
    if production_data_ready():
        try:
            program_list_payload = list_automation_programs_from_legacy()
        except LegacyAutomationDataUnavailable:
            program_list_payload = {"items": [], "default_program": {}, "total": 0, "source_status": "production_unavailable"}
    else:
        pools = ListAutomationPoolsQuery()()["pools"]
        records = ListAutomationExecutionRecordsQuery()(limit=5, offset=0)["items"]
        program_list_payload = {
            "items": [
                {
                    "program": {
                        "id": 1,
                        "program_name": "自动化运营方案",
                        "program_code": "next_local_preview",
                        "status": "active",
                        "updated_at": "2026-05-20T12:00:00Z",
                        "description": "本地结构校验方案；生产环境读取 PostgreSQL。",
                    },
                    "summary": {
                        "channel_count": len(pools),
                        "workflow_count": sum(pool.get("active_action_count", 0) for pool in pools),
                        "latest_execution_at": records[0]["created_at"] if records else "",
                    },
                }
            ],
            "default_program": {"id": 1, "program_name": "自动化运营方案"},
            "total": 1,
            "source_status": "local_contract_probe",
        }
    context = _shell_context(
        request=request,
        page_title="自动化运营",
        page_summary="查看自动化运营方案、渠道、工作流与执行记录；生产环境读取 PostgreSQL。",
        active_endpoint="api.admin_automation_conversion",
    )
    context.update(
        {
            "program_list_payload": program_list_payload,
            "show_create_form": False,
            "admin_action_token": "",
            "action_urls": {"create": "/admin/automation-conversion"},
        }
    )
    return templates.TemplateResponse(request, "admin_console/automation_program_list.html", context)


@router.get("/admin/channels", name="api.admin_channels_page")
async def admin_channels_page(request: Request) -> Response:
    if production_data_ready():
        return await forward_to_legacy_flask(request)
    context = _shell_context(
        request=request,
        page_title="渠道码中心",
        page_summary="独立管理普通二维码和企微获客助手链接；绑定自动化运营请进入对应方案的入口渠道页。",
        active_endpoint="api.admin_channels_page",
    )
    context.update(
        {
            "breadcrumbs": [
                {"label": "客户管理后台", "href": request.url_for("api.admin_console_dashboard")},
                {"label": "渠道码中心"},
            ],
            "state_title": "渠道码中心",
            "state_body": "渠道码中心是一级后台能力，用于查看、新建和维护独立获客渠道。",
            "state_items": [
                "普通二维码支持下载二维码",
                "企微获客助手链接支持复制链接和分享链接",
                "绑定自动化运营只在方案入口渠道页完成",
            ],
            "actions": [
                {"label": "新建渠道", "href": request.url_for("api.admin_channel_new_page"), "variant": "primary"},
                {"label": "自动化运营", "href": request.url_for("api.admin_automation_conversion"), "variant": "secondary"},
            ],
        }
    )
    return templates.TemplateResponse(request, "admin_console/placeholder.html", context)


@router.get("/admin/channels/new", name="api.admin_channel_new_page")
async def admin_channel_new_page(request: Request) -> Response:
    if production_data_ready():
        return await forward_to_legacy_flask(request)
    context = _shell_context(
        request=request,
        page_title="新建渠道",
        page_summary="创建普通二维码或企微获客助手链接渠道；渠道绑定在自动化运营入口渠道页完成。",
        active_endpoint="api.admin_channels_page",
    )
    context.update(
        {
            "breadcrumbs": [
                {"label": "客户管理后台", "href": request.url_for("api.admin_console_dashboard")},
                {"label": "渠道码中心", "href": request.url_for("api.admin_channels_page")},
                {"label": "新建渠道"},
            ],
            "state_title": "新建渠道",
            "state_body": "生产环境会打开完整的新建渠道表单；本地兼容层保留入口和导航契约。",
            "state_items": [
                "支持普通二维码",
                "支持企微获客助手链接",
                "支持欢迎语、小程序、图片和 PDF 素材选择",
            ],
            "actions": [{"label": "返回渠道码中心", "href": request.url_for("api.admin_channels_page"), "variant": "secondary"}],
        }
    )
    return templates.TemplateResponse(request, "admin_console/placeholder.html", context)


@router.get("/admin/channels/{channel_id:int}/edit", name="api.admin_channel_edit_page")
async def admin_channel_edit_page(request: Request, channel_id: int) -> Response:
    if production_data_ready():
        return await forward_to_legacy_flask(request)
    context = _shell_context(
        request=request,
        page_title="编辑渠道",
        page_summary="维护渠道本体、欢迎语和素材配置；不会在这里绑定自动化运营。",
        active_endpoint="api.admin_channels_page",
    )
    context.update(
        {
            "breadcrumbs": [
                {"label": "客户管理后台", "href": request.url_for("api.admin_console_dashboard")},
                {"label": "渠道码中心", "href": request.url_for("api.admin_channels_page")},
                {"label": f"编辑渠道 {channel_id}"},
            ],
            "state_title": "编辑渠道",
            "state_body": "生产环境会打开完整的渠道编辑表单；本地兼容层保留入口和导航契约。",
            "state_items": [
                "普通二维码不会被重新生成",
                "企微获客助手链接不会被重新生成",
                "绑定状态只在入口渠道页变更",
            ],
            "actions": [{"label": "返回渠道码中心", "href": request.url_for("api.admin_channels_page"), "variant": "secondary"}],
        }
    )
    return templates.TemplateResponse(request, "admin_console/placeholder.html", context)


@router.get(
    "/admin/automation-conversion/programs/{program_id:int}/entry-channels",
    name="api.admin_automation_program_entry_channels",
)
async def admin_automation_program_entry_channels(request: Request, program_id: int) -> Response:
    if production_data_ready():
        return await forward_to_legacy_flask(request)
    context = _shell_context(
        request=request,
        page_title="入口渠道",
        page_summary="在自动化运营方案内绑定已有渠道码，渠道码中心不提供绑定入口。",
        active_endpoint="api.admin_automation_conversion",
    )
    context.update(
        {
            "breadcrumbs": [
                {"label": "客户管理后台", "href": request.url_for("api.admin_console_dashboard")},
                {"label": "自动化运营", "href": request.url_for("api.admin_automation_conversion")},
                {"label": f"方案 {program_id} 入口渠道"},
            ],
            "state_title": "入口渠道",
            "state_body": "生产环境会打开当前方案的入口渠道页，用于绑定已有普通二维码或企微获客助手链接。",
            "state_items": [
                "一个渠道同一时间只能 active 绑定一个方案",
                "绑定不会自动导入历史用户",
                "扫码或人工导入后才产生入池清洗",
            ],
            "actions": [{"label": "渠道码中心", "href": request.url_for("api.admin_channels_page"), "variant": "secondary"}],
        }
    )
    return templates.TemplateResponse(request, "admin_console/placeholder.html", context)


@router.get("/admin/wechat-pay/transactions", name="api.admin_wechat_pay_transactions_page")
async def admin_wechat_pay_transactions(request: Request) -> Response:
    if production_data_ready():
        return await forward_to_legacy_flask(request)
    context = _shell_context(
        request=request,
        page_title="微信支付交易管理",
        page_summary="按订单创建时间展示生产微信支付订单；不触发支付外呼。",
        active_endpoint="api.admin_wechat_pay_transactions_page",
    )
    _real_data_context(
        context,
        payload=GetAdminTransactionsPageQuery()(),
        title="交易管理",
        summary="生产 wechat_pay_orders 只读列表，包含商户单号、微信单号、客户、商品、金额和状态。",
    )
    return templates.TemplateResponse(request, "admin_console/real_data_page.html", context)


@router.get("/admin/wechat-pay/transactions/{order_id}", name="api.admin_wechat_pay_transaction_detail_page")
async def admin_wechat_pay_transaction_detail(request: Request, order_id: int) -> Response:
    if production_data_ready():
        return await forward_to_legacy_flask(request)
    return RedirectResponse(_legacy_url_for("api.admin_wechat_pay_transactions_page"), status_code=302)


@router.get("/admin/wechat-pay/products", name="api.admin_wechat_pay_products_page")
def admin_wechat_pay_products(request: Request):
    context = _shell_context(
        request=request,
        page_title="商品管理",
        page_summary="查看和维护生产商品配置；支付外部动作仍受安全边界保护。",
        active_endpoint="api.admin_wechat_pay_products_page",
    )
    _real_data_context(
        context,
        payload=GetAdminProductsPageQuery()(),
        title="商品管理",
        summary="生产 wechat_pay_products 与 page slices 只读列表。",
    )
    return templates.TemplateResponse(request, "admin_console/real_data_page.html", context)


@router.get("/admin/alipay/transactions", name="api.admin_alipay_transactions_page")
def admin_alipay_transactions(request: Request):
    context = _shell_context(
        request=request,
        page_title="支付宝交易管理",
        page_summary="查看支付宝交易兼容入口；外部支付动作仍受 adapter guard 保护。",
        active_endpoint="api.admin_alipay_transactions_page",
    )
    _real_data_context(
        context,
        payload=GetAdminTransactionsPageQuery()(),
        title="支付宝交易兼容入口",
        summary="当前交易页展示统一生产订单只读视图；不触发支付外呼。",
    )
    return templates.TemplateResponse(request, "admin_console/real_data_page.html", context)


@router.get("/admin/image-library", name="api.admin_image_library_workspace")
def admin_image_library(request: Request):
    context = _shell_context(
        request=request,
        page_title="图片素材库",
        page_summary="集中维护可被群发 / 卡片 / 自动化欢迎语等场景引用的图片，支持上传和外链。",
        active_endpoint="api.admin_image_library_workspace",
    )
    _real_data_context(
        context,
        payload=GetAdminMediaPageQuery()("image"),
        title="图片素材库",
        summary="生产 image_library 首屏只读列表；上传入口保留但不在本页触发外部动作。",
    )
    return templates.TemplateResponse(request, "admin_console/real_data_page.html", context)


@router.get("/admin/miniprogram-library", name="api.admin_miniprogram_library_workspace")
def admin_miniprogram_library(request: Request):
    context = _shell_context(
        request=request,
        page_title="小程序素材库",
        page_summary="维护群发和自动化可复用的小程序卡片。",
        active_endpoint="api.admin_miniprogram_library_workspace",
    )
    _real_data_context(
        context,
        payload=GetAdminMediaPageQuery()("miniprogram"),
        title="小程序素材库",
        summary="生产 miniprogram_library 首屏只读列表。",
    )
    return templates.TemplateResponse(request, "admin_console/real_data_page.html", context)


@router.get("/admin/attachment-library", name="api.admin_attachment_library_workspace")
def admin_attachment_library(request: Request):
    context = _shell_context(
        request=request,
        page_title="附件素材库",
        page_summary="维护 PDF、附件和课程资料等可复用素材。",
        active_endpoint="api.admin_attachment_library_workspace",
    )
    _real_data_context(
        context,
        payload=GetAdminMediaPageQuery()("attachment"),
        title="附件素材库",
        summary="生产 attachment_library 首屏只读列表，生产表为空时展示明确空状态。",
    )
    return templates.TemplateResponse(request, "admin_console/real_data_page.html", context)


@router.get("/admin/customers/{external_userid}", name="api.admin_console_customer_detail")
def admin_customer_detail_redirect(external_userid: str):
    return RedirectResponse(url=f"/api/admin/customers/profile?external_userid={external_userid}", status_code=307)


@router.get("/api/admin/dashboard/shell-context", name="api.admin_dashboard_shell_context")
def admin_dashboard_shell_context() -> dict:
    return {
        "ok": True,
        "environment": {"tone": "dev", "label": "AI-CRM Next"},
        "health": {"state": "ok", "label": "OK", "detail": "frontend compat shell"},
        "navigation": _nav_items(""),
        "nav_groups": _nav_items(""),
    }


@router.get("/admin/logout", name="api.admin_logout")
def admin_logout_stub() -> dict:
    return {"ok": True, "status": "stubbed"}


@router.get("/admin/jobs", name="api.admin_jobs")
def admin_jobs(request: Request):
    context = _shell_context(
        request=request,
        page_title="同步任务配置 / 同步任务",
        page_summary="查看同步任务、消息批次、回调和 timer safe mode 状态。",
        active_endpoint="api.admin_jobs",
    )
    _real_data_context(
        context,
        payload=GetAdminJobsPageQuery()(),
        title="同步任务配置 / 同步任务",
        summary="展示同步记录、回调事件、消息批次、出站任务和四个 timer 的 safe mode 状态。",
    )
    return templates.TemplateResponse(request, "admin_console/real_data_page.html", context)


@router.get("/admin/config", name="api.admin_config")
def admin_config(request: Request):
    context = _shell_context(
        request=request,
        page_title="配置",
        page_summary="集中管理后台配置、登录访问和 MCP 工具配置。",
        active_endpoint="api.admin_config",
    )
    _real_data_context(
        context,
        payload=GetAdminConfigPageQuery()(),
        title="运行配置",
        summary="展示数据库模式、release、callback fallback、OAuth、企微和支付配置预检状态；不展示 secrets。",
    )
    return templates.TemplateResponse(request, "admin_console/real_data_page.html", context)


@router.get("/admin/api-docs", name="api.admin_api_docs")
def admin_api_docs(request: Request):
    context = _shell_context(
        request=request,
        page_title="API 文档",
        page_summary="查看 AI-CRM 后台和外部集成 API 文档。",
        active_endpoint="api.admin_api_docs",
    )
    _real_data_context(
        context,
        payload=GetAdminApiDocsPageQuery()(),
        title="API 文档",
        summary="按后台 API、企微回调、支付回调、自动化任务、素材 API 和商品/订单 API 分组展示。",
    )
    return templates.TemplateResponse(request, "admin_console/real_data_page.html", context)


@router.get("/api/frontend-compat/legacy-routes")
def legacy_routes_manifest() -> dict:
    return {
        "ok": True,
        "frontend_parity_policy": "1:1 replicate existing AI-CRM admin frontend; do not redesign",
        "routes": LEGACY_FRONTEND_ROUTES,
    }
