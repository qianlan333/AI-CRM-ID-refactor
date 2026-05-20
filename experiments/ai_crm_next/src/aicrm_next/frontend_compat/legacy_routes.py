from __future__ import annotations

from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from aicrm_next.automation_engine.application import ListAutomationExecutionRecordsQuery, ListAutomationPoolsQuery
from aicrm_next.commerce.application import ListProductsQuery, ListTransactionsQuery
from aicrm_next.customer_read_model.application import ListCustomersQuery
from aicrm_next.customer_read_model.dto import ListCustomersRequest
from aicrm_next.media_library.application import ListMediaItemsQuery
from aicrm_next.questionnaire.application import GetQuestionnairePreflightQuery, ListQuestionnairesQuery

router = APIRouter()
_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=_TEMPLATES_DIR)

LEGACY_FRONTEND_ROUTES = [
    "/admin",
    "/admin/customers",
    "/admin/questionnaires",
    "/admin/user-ops/ui",
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
        "api.admin_api_docs": "/admin/api-docs",
        "api.admin_dashboard_shell_context": "/api/admin/dashboard/shell-context",
        "api.admin_logout": "/admin/logout",
    }
    base = path_map.get(name, "#")
    query = {key: value for key, value in path_params.items() if value not in (None, "")}
    return base + (f"?{urlencode(query)}" if query else "")


def _nav_items(active_endpoint: str) -> list[dict]:
    items = [
        ("首页", "api.admin_console_dashboard"),
        ("客户中心", "api.admin_console_customers"),
        ("User Ops", "api.admin_user_ops_ui"),
        ("问卷", "api.admin_questionnaires"),
        ("自动化转化", "api.admin_automation_conversion"),
        ("交易", "api.admin_wechat_pay_transactions_page"),
        ("素材", "api.admin_image_library_workspace"),
        ("任务", "api.admin_jobs"),
        ("配置", "api.admin_config"),
        ("API 文档", "api.admin_api_docs"),
    ]
    return [{"label": label, "endpoint": endpoint, "active": endpoint == active_endpoint} for label, endpoint in items]


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
        "shell_status": {"environment": {"tone": "dev", "label": "实验"}, "health": {"state": "ok", "label": "OK", "detail": "fixture"}},
        "page_notice": "",
        "page_error": "",
        "url_for": _legacy_url_for,
    }


def _placeholder_state(title: str, body: str, items: list[str] | None = None) -> dict:
    return {
        "state_title": title,
        "state_body": body,
        "state_items": items or [],
        "actions": [],
        "table_headers": ["入口", "状态", "说明"],
        "table_rows": [],
    }


@router.get("/admin", name="api.admin_console_dashboard")
def admin_dashboard(request: Request):
    context = _shell_context(
        request=request,
        page_title="系统概况",
        page_summary="旧 AI-CRM 后台 shell 复刻基线，后端由 AI-CRM Next adapter 支撑。",
        active_endpoint="api.admin_console_dashboard",
    )
    context.update(
        {
            "system_status": {
                "cards": [
                    {"label": "FastAPI", "value": "ok", "description": "实验后端可响应 legacy shell。", "tone": "ok"},
                    {"label": "Frontend parity", "value": "partial", "description": "首轮已复制旧后台模板与静态资源。", "tone": "warn"},
                ]
            },
            "dashboard_cards": [
                {"label": "客户", "value": "adapter", "description": "客户中心读模型已接入兼容 API。", "href": request.url_for("api.admin_console_customers")},
                {"label": "User Ops", "value": "copied", "description": "旧运营页模板已挂载。", "href": request.url_for("api.admin_user_ops_ui")},
            ],
            "todo_total": 0,
            "todo_groups": [],
            "quick_links": [
                {"label": "客户中心", "description": "查看复制后的客户中心 shell。", "href": request.url_for("api.admin_console_customers")},
                {"label": "User Ops", "description": "进入旧 User Ops 页面。", "href": request.url_for("api.admin_user_ops_ui")},
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
        page_title="客户中心",
        page_summary="查看客户列表、筛选客户并打开客户档案。",
        active_endpoint="api.admin_console_customers",
    )
    context["customer_payload"] = customer_payload
    return templates.TemplateResponse(request, "admin_console/customers.html", context)


@router.get("/admin/user-ops/ui", name="api.admin_user_ops_ui")
def admin_user_ops_ui(request: Request):
    return templates.TemplateResponse(request, "admin_user_ops.html", {"request": request})


@router.get("/admin/questionnaires", name="api.admin_questionnaires")
@router.get("/admin/questionnaires/ui", name="api.admin_console_questionnaires")
def admin_questionnaires(request: Request):
    list_payload = ListQuestionnairesQuery()(limit=100, offset=0)
    preflight_payload = GetQuestionnairePreflightQuery()()
    context = _shell_context(
        request=request,
        page_title="问卷管理",
        page_summary="复刻旧问卷后台列表页，后端由 AI-CRM Next fixture adapter 支撑。",
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
    context = _shell_context(
        request=request,
        page_title="自动化转化",
        page_summary="复刻旧自动化转化方案列表入口，后端由 AI-CRM Next fixture adapter 支撑。",
        active_endpoint="api.admin_automation_conversion",
    )
    context.update(
        {
            "program_list_payload": {
                "items": [
                    {
                        "program": {
                            "id": 1,
                            "program_name": "默认转化方案",
                            "program_code": "default_conversion_v1",
                            "status": "active",
                            "updated_at": "2026-05-20T12:00:00Z",
                            "description": "AI-CRM Next 自动化转化 fixture 方案。",
                        },
                        "summary": {
                            "channel_count": len(pools),
                            "workflow_count": sum(pool.get("active_action_count", 0) for pool in pools),
                            "latest_execution_at": records[0]["created_at"] if records else "",
                        },
                    }
                ],
                "default_program": {"id": 1, "program_name": "默认转化方案"},
                "total": 1,
            },
            "show_create_form": False,
            "admin_action_token": "fixture-token",
            "action_urls": {"create": "/admin/automation-conversion"},
        }
    )
    return templates.TemplateResponse(request, "admin_console/automation_program_list.html", context)


@router.get("/admin/wechat-pay/transactions", name="api.admin_wechat_pay_transactions_page")
def admin_wechat_pay_transactions(request: Request):
    transactions = ListTransactionsQuery("wechat")({}, limit=20, offset=0)
    context = _shell_context(
        request=request,
        page_title="微信支付交易管理",
        page_summary="按订单创建时间检索微信支付订单、导出筛选结果，并进入独立详情页查看订单状态。",
        active_endpoint="api.admin_wechat_pay_transactions_page",
    )
    context.update(
        {
            "page_mode": "list",
            "product_options": ListProductsQuery()(limit=100, offset=0)["items"],
            "default_filters": {"status": "", "product_code": "", "created_from": "", "created_to": ""},
            "initial_transactions": transactions["items"],
        }
    )
    return templates.TemplateResponse(request, "admin_console/wechat_pay_transactions.html", context)


@router.get("/admin/wechat-pay/products", name="api.admin_wechat_pay_products_page")
def admin_wechat_pay_products(request: Request):
    products = ListProductsQuery()(limit=100, offset=0)
    context = _shell_context(
        request=request,
        page_title="商品管理",
        page_summary="复刻旧后台商品配置入口，第一阶段由 fake payment contract 支撑。",
        active_endpoint="api.admin_wechat_pay_products_page",
    )
    context.update({"placeholder_items": products["items"], "planned_surface": "wechat-pay-products"})
    context.update(
        _placeholder_state(
            "商品管理 legacy adapter",
            "商品管理 API contract 已接入 fake payment 后端；完整旧模板仍标记 partial adapter。",
            ["商品列表", "价格 cents 校验", "enable / disable", "soft delete"],
        )
    )
    return templates.TemplateResponse(request, "admin_console/placeholder.html", context)


@router.get("/admin/alipay/transactions", name="api.admin_alipay_transactions_page")
def admin_alipay_transactions(request: Request):
    transactions = ListTransactionsQuery("alipay")({}, limit=20, offset=0)
    context = _shell_context(
        request=request,
        page_title="支付宝交易管理",
        page_summary="复刻旧后台支付宝交易入口，第一阶段由 fake Alipay contract 支撑。",
        active_endpoint="api.admin_alipay_transactions_page",
    )
    context.update({"placeholder_items": transactions["items"], "planned_surface": "alipay-transactions"})
    context.update(
        _placeholder_state(
            "支付宝交易 legacy adapter",
            "支付宝交易 API contract 已接入 fake notify/return；旧后台交易体验保持 partial adapter。",
            ["交易列表", "状态筛选", "fake return", "不接真实支付宝"],
        )
    )
    return templates.TemplateResponse(request, "admin_console/placeholder.html", context)


@router.get("/admin/image-library", name="api.admin_image_library_workspace")
def admin_image_library(request: Request):
    context = _shell_context(
        request=request,
        page_title="图片素材库",
        page_summary="集中维护可被群发 / 卡片 / 自动化欢迎语等场景引用的图片，支持上传和外链。",
        active_endpoint="api.admin_image_library_workspace",
    )
    context.update({"show_page_header": True})
    return templates.TemplateResponse(request, "admin_console/image_library.html", context)


@router.get("/admin/miniprogram-library", name="api.admin_miniprogram_library_workspace")
def admin_miniprogram_library(request: Request):
    context = _shell_context(
        request=request,
        page_title="小程序素材库",
        page_summary="维护群发和自动化可复用的小程序卡片。",
        active_endpoint="api.admin_miniprogram_library_workspace",
    )
    context.update({"show_page_header": True})
    return templates.TemplateResponse(request, "admin_console/miniprogram_library.html", context)


@router.get("/admin/attachment-library", name="api.admin_attachment_library_workspace")
def admin_attachment_library(request: Request):
    attachments = ListMediaItemsQuery("attachment")(limit=100, offset=0)
    context = _shell_context(
        request=request,
        page_title="附件素材库",
        page_summary="复刻旧后台附件素材入口，第一阶段使用 fixture/data_base64 contract。",
        active_endpoint="api.admin_attachment_library_workspace",
    )
    context.update({"placeholder_items": attachments["items"], "planned_surface": "attachment-library"})
    context.update(
        _placeholder_state(
            "附件素材库 legacy adapter",
            "附件素材库 API contract 已接入 fixture data_base64；旧模板缺口保持 partial adapter。",
            ["附件列表", "创建", "更新", "soft delete"],
        )
    )
    return templates.TemplateResponse(request, "admin_console/placeholder.html", context)


@router.get("/admin/customers/{external_userid}", name="api.admin_console_customer_detail")
def admin_customer_detail_redirect(external_userid: str):
    return RedirectResponse(url=f"/api/customers/{external_userid}", status_code=307)


@router.get("/api/admin/dashboard/shell-context", name="api.admin_dashboard_shell_context")
def admin_dashboard_shell_context() -> dict:
    return {
        "ok": True,
        "environment": {"tone": "dev", "label": "AI-CRM Next"},
        "health": {"state": "ok", "label": "OK", "detail": "frontend compat shell"},
    }


@router.get("/admin/logout", name="api.admin_logout")
def admin_logout_stub() -> dict:
    return {"ok": True, "status": "stubbed"}


@router.get("/admin/jobs", name="api.admin_jobs")
@router.get("/admin/config", name="api.admin_config")
@router.get("/admin/api-docs", name="api.admin_api_docs")
def planned_admin_page(request: Request):
    context = _shell_context(
        request=request,
        page_title="待复刻页面",
        page_summary="该 legacy 页面模板已复制，路由承载仍处于 planned/partial。",
        active_endpoint="",
    )
    return templates.TemplateResponse(request, "admin_console/placeholder.html", context)


@router.get("/api/frontend-compat/legacy-routes")
def legacy_routes_manifest() -> dict:
    return {
        "ok": True,
        "frontend_parity_policy": "1:1 replicate existing AI-CRM admin frontend; do not redesign",
        "routes": LEGACY_FRONTEND_ROUTES,
    }
