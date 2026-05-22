from __future__ import annotations

from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from aicrm_next.shared.runtime import production_data_ready
from aicrm_next.automation_engine.application import ListAutomationExecutionRecordsQuery, ListAutomationPoolsQuery
from aicrm_next.customer_read_model.application import ListCustomersQuery
from aicrm_next.customer_read_model.dto import ListCustomersRequest
from aicrm_next.questionnaire.application import GetQuestionnairePreflightQuery, ListQuestionnairesQuery
from aicrm_next.integration_gateway.legacy_automation_facade import LegacyAutomationDataUnavailable, list_automation_programs_from_legacy
from .admin_real_data import (
    ai_assistant_payload,
    api_docs_payload,
    config_payload,
    funnel_payload,
    jobs_payload,
    media_payload,
    page_row_count,
    products_payload,
    transactions_payload,
    wecom_tags_payload,
)

router = APIRouter()
_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=_TEMPLATES_DIR)

LEGACY_FRONTEND_ROUTES = [
    "/admin",
    "/admin/customers",
    "/admin/questionnaires",
    "/admin/user-ops/ui",
    "/admin/user-ops",
    "/admin/cloud-orchestrator",
    "/admin/wecom-tags",
    "/admin/automation-conversion",
    "/admin/jobs",
    "/admin/wechat-pay/transactions",
    "/admin/wechat-pay/products",
    "/admin/alipay/transactions",
    "/admin/image-library",
    "/admin/miniprogram-library",
    "/admin/attachment-library",
    "/admin/config",
    "/admin/api-docs",
]


def _legacy_url_for(name: str, **path_params: object) -> str:
    if name == "static":
        return "/static/" + str(path_params.get("filename", "")).lstrip("/")
    if name == "api.admin_console_customer_detail":
        external_userid = str(path_params.get("external_userid", ""))
        return f"/admin/customers/{external_userid}"
    path_map = {
        "api.admin_console_dashboard": "/admin",
        "api.admin_console_customers": "/admin/customers",
        "api.admin_user_ops_ui": "/admin/user-ops/ui",
        "api.admin_hxc_dashboard_workspace": "/admin/user-ops",
        "api.admin_cloud_orchestrator_workspace": "/admin/cloud-orchestrator",
        "api.admin_wecom_tags_page": "/admin/wecom-tags",
        "api.admin_questionnaires": "/admin/questionnaires",
        "api.admin_console_questionnaires": "/admin/questionnaires",
        "api.admin_console_questionnaire_new": "/admin/questionnaires/ui",
        "api.admin_automation_conversion": "/admin/automation-conversion",
        "api.admin_automation_program_setup": "/admin/automation-conversion",
        "api.admin_automation_program_overview": "/admin/automation-conversion",
        "api.admin_automation_program_copy": "/admin/automation-conversion",
        "api.admin_automation_program_pause": "/admin/automation-conversion",
        "api.admin_automation_program_activate": "/admin/automation-conversion",
        "api.admin_automation_program_archive": "/admin/automation-conversion",
        "api.admin_jobs": "/admin/jobs",
        "api.admin_wechat_pay_transactions_page": "/admin/wechat-pay/transactions",
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
    return context


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
    payload = ListCustomersQuery()(
        ListCustomersRequest(
            owner_userid=owner or None,
            tag=tag or None,
            mobile=mobile or None,
            keyword=keyword or None,
            limit=limit,
            offset=offset,
        )
    )
    if not production_data_ready():
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
    payload = funnel_payload()
    _real_data_context(
        context,
        payload=payload,
        title="客户激活 / 客户列表",
        summary="生产客户、问卷、订单和自动化成员统计。",
    )
    return templates.TemplateResponse(request, "admin_console/real_data_page.html", context)


@router.get("/admin/user-ops", name="api.admin_hxc_dashboard_workspace")
def admin_user_ops_funnel(request: Request):
    context = _shell_context(
        request=request,
        page_title="漏斗 / 数据看板",
        page_summary="查看客户激活、会员状态和运营漏斗数据。",
        active_endpoint="api.admin_hxc_dashboard_workspace",
    )
    _real_data_context(
        context,
        payload=funnel_payload(),
        title="漏斗 / 数据看板",
        summary="生产客户、问卷提交、订单、自动化成员、运营任务和工作流执行统计。",
    )
    return templates.TemplateResponse(request, "admin_console/real_data_page.html", context)


@router.get("/admin/cloud-orchestrator", name="api.admin_cloud_orchestrator_workspace")
def admin_cloud_orchestrator(request: Request):
    context = _shell_context(
        request=request,
        page_title="AI 助手",
        page_summary="查看 AI 助手、云编排和自动化辅助能力入口。",
        active_endpoint="api.admin_cloud_orchestrator_workspace",
    )
    _real_data_context(
        context,
        payload=ai_assistant_payload(),
        title="AI 助手",
        summary="只读展示 automation_agent_config、run、output 与 LLM 调用日志；不触发外部调用。",
    )
    return templates.TemplateResponse(request, "admin_console/real_data_page.html", context)


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
        payload=wecom_tags_payload(),
        title="企微标签管理",
        summary="展示本地已同步标签缓存、使用人数和同步前置状态；不调用远程企微接口。",
    )
    return templates.TemplateResponse(request, "admin_console/real_data_page.html", context)


@router.get("/admin/questionnaires", name="api.admin_questionnaires")
@router.get("/admin/questionnaires/ui", name="api.admin_console_questionnaires")
def admin_questionnaires(request: Request):
    list_payload = ListQuestionnairesQuery()(limit=100, offset=0)
    preflight_payload = GetQuestionnairePreflightQuery()()
    context = _shell_context(
        request=request,
        page_title="问卷管理",
        page_summary="读取生产问卷列表，保留新建、编辑、停用、删除和导出入口。",
        active_endpoint="api.admin_questionnaires",
    )
    context["questionnaire_payload"] = {
        "questionnaires": list_payload["questionnaires"],
        "preflight": preflight_payload["checks"],
        "preflight_error": "",
    }
    return templates.TemplateResponse(request, "admin_console/questionnaires.html", context)


@router.get("/admin/automation-conversion", name="api.admin_automation_conversion")
def admin_automation_conversion(request: Request):
    pools = ListAutomationPoolsQuery()()["pools"]
    records = ListAutomationExecutionRecordsQuery()(limit=5, offset=0)["items"]
    if production_data_ready():
        try:
            program_list_payload = list_automation_programs_from_legacy()
        except LegacyAutomationDataUnavailable:
            program_list_payload = {"items": [], "default_program": {}, "total": 0, "source_status": "production_unavailable"}
    else:
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


@router.get("/admin/wechat-pay/transactions", name="api.admin_wechat_pay_transactions_page")
def admin_wechat_pay_transactions(request: Request):
    context = _shell_context(
        request=request,
        page_title="微信支付交易管理",
        page_summary="按订单创建时间展示生产微信支付订单；不触发支付外呼。",
        active_endpoint="api.admin_wechat_pay_transactions_page",
    )
    _real_data_context(
        context,
        payload=transactions_payload(),
        title="交易管理",
        summary="生产 wechat_pay_orders 只读列表，包含商户单号、微信单号、客户、商品、金额和状态。",
    )
    return templates.TemplateResponse(request, "admin_console/real_data_page.html", context)


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
        payload=products_payload(),
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
        payload=transactions_payload(),
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
        payload=media_payload("image"),
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
        payload=media_payload("miniprogram"),
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
        payload=media_payload("attachment"),
        title="附件素材库",
        summary="生产 attachment_library 首屏只读列表，生产表为空时展示明确空状态。",
    )
    return templates.TemplateResponse(request, "admin_console/real_data_page.html", context)


@router.get("/admin/customers/{external_userid}", name="api.admin_console_customer_detail")
def admin_customer_detail_redirect(external_userid: str):
    return RedirectResponse(url=f"/api/customers/{external_userid}", status_code=307)


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
        payload=jobs_payload(),
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
        payload=config_payload(),
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
        payload=api_docs_payload(),
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
