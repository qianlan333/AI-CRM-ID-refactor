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
    GetAdminConfigPageQuery,
    GetAdminFunnelPageQuery,
    GetAdminProductsPageQuery,
    GetAdminTransactionsPageQuery,
    page_row_count,
)
from aicrm_next.frontend_compat.api_docs_view_model import build_api_docs_view_model
from aicrm_next.automation_engine.channels_api import (
    default_channel_form_payload,
    get_channel_resource,
    list_program_channel_bindings_resource,
    list_program_entry_candidate_channels,
)
from aicrm_next.automation_engine.programs import (
    AutomationProgramDataUnavailable,
    SETUP_STEPS,
    copy_automation_program,
    get_automation_program_setup_payload,
    get_automation_program_with_summary,
    list_automation_programs_payload,
    update_automation_program_basic_info,
    update_automation_program_status,
)
from aicrm_next.customer_read_model.application import GetAdminCustomerProfileQuery, ListCustomersQuery
from aicrm_next.customer_read_model.dto import ListCustomersRequest
from aicrm_next.questionnaire.application import GetQuestionnaireDetailQuery, GetQuestionnairePreflightQuery
from aicrm_next.integration_gateway.legacy_questionnaire_facade import (
    LegacyQuestionnaireDataUnavailable,
    get_questionnaire_detail_from_legacy,
    list_questionnaires_from_legacy,
)
from .admin_shell import (
    ADMIN_NAV_GROUPS,
    legacy_url_for as _legacy_url_for,
    nav_items as _nav_items,
    shell_context as _shell_context,
)

router = APIRouter()
_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=_TEMPLATES_DIR)
_ALL_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]

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
    "/admin/automation-conversion/programs/{program_id}/setup",
    "/admin/automation-conversion/programs/{program_id}/overview",
    "/admin/automation-conversion/programs/{program_id}/copy",
    "/admin/automation-conversion/group-ops/ui",
    "/admin/automation-conversion/group-ops/plans/{plan_id}",
    "/admin/automation-conversion/group-ops/groups/ui",
    "/admin/automation-conversion/programs/{program_id}/entry-channels",
    "/admin/wechat-pay/transactions",
    "/admin/wechat-pay/transactions/{order_id}",
    "/admin/wechat-pay/products",
    "/admin/alipay/transactions",
    "/admin/image-library",
    "/admin/miniprogram-library",
    "/admin/attachment-library",
    "/admin/config",
    "/admin/config/app-settings",
    "/admin/config/login-access",
    "/admin/config/checklist",
    "/setup/wizard",
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


def _admin_customer_payload_from_list_result(
    *,
    result: dict,
    keyword: str,
    owner: str,
    mobile: str,
    tag: str,
    limit: int,
    offset: int,
) -> tuple[dict, str]:
    degraded = bool(result.get("degraded")) or result.get("source_status") == "production_unavailable"
    page_error = str(result.get("page_error") or "") if degraded or not result.get("ok", True) else ""
    customers = [] if degraded else list(result.get("customers") or result.get("items") or [])
    total = 0 if degraded else int(result.get("total") or result.get("count") or len(customers))
    return (
        {
            "filters": {"keyword": keyword, "owner": owner, "mobile": mobile, "tag": tag},
            "customers": customers,
            "pagination": {
                "total": total,
                "has_prev": offset > 0,
                "has_next": offset + limit < total,
                "prev_offset": max(offset - limit, 0),
                "next_offset": offset + limit,
            },
        },
        page_error,
    )


def _customer_profile_initial_section(tab: str) -> str:
    tab_map = {
        "tags": "customer-live-tags",
        "questionnaire": "customer-questionnaire-answers",
        "questionnaires": "customer-questionnaire-answers",
        "messages": "customer-message-records",
        "automation": "customer-automation-sidebar",
    }
    return tab_map.get(str(tab or "").strip().lower(), "")


def _customer_detail_payload_from_profile_result(result: dict, *, legacy_tab: str) -> dict | None:
    if not result.get("ok"):
        return None
    profile = dict(result.get("profile") or result.get("customer") or {})
    external_userid = str(profile.get("external_userid") or profile.get("user_id") or "").strip()
    if not external_userid:
        return None
    identity = dict(profile.get("identity") or {})
    profile["external_userid"] = external_userid
    profile["user_id"] = str(profile.get("user_id") or external_userid)
    profile["customer_name"] = str(profile.get("customer_name") or profile.get("remark") or external_userid)
    profile["mobile"] = str(profile.get("mobile") or identity.get("mobile") or "")
    profile["owner"] = str(profile.get("owner") or profile.get("owner_display_name") or profile.get("owner_userid") or "")
    profile["owner_userid"] = str(profile.get("owner_userid") or "")
    profile["unionid"] = str(profile.get("unionid") or identity.get("unionid") or "")
    return {
        "customer": profile,
        "lookup": dict(result.get("lookup") or {}),
        "initial_section": _customer_profile_initial_section(legacy_tab),
    }


def _customer_profile_urls(external_userid: str) -> dict[str, str]:
    query = urlencode({"external_userid": external_userid})
    return {
        "profile": f"/api/admin/customers/profile?{query}",
        "tags": f"/api/admin/customers/profile/tags?{query}",
        "questionnaire_answers": f"/api/admin/customers/profile/questionnaire-answers?{query}",
        "messages": f"/api/admin/customers/profile/messages?{query}",
        "automation_member": f"/api/admin/automation-conversion/member?{urlencode({'external_contact_id': external_userid})}",
        "automation_put_in_pool": "/api/admin/automation-conversion/member/put-in-pool",
        "automation_remove_from_pool": "/api/admin/automation-conversion/member/remove-from-pool",
        "automation_set_focus": "/api/admin/automation-conversion/member/set-focus",
        "automation_set_normal": "/api/admin/automation-conversion/member/set-normal",
        "automation_mark_won": "/api/admin/automation-conversion/member/mark-won",
        "automation_unmark_won": "/api/admin/automation-conversion/member/unmark-won",
        "automation_push_openclaw": "/api/admin/automation-conversion/member/push-openclaw",
    }


@router.get("/admin/customers", name="api.admin_console_customers")
def admin_customers(request: Request, keyword: str = "", owner: str = "", mobile: str = "", tag: str = "", offset: int = 0):
    limit = 50
    offset = max(int(offset or 0), 0)
    customer_query = ListCustomersRequest(
        owner_userid=owner or None,
        tag=tag or None,
        mobile=mobile or None,
        keyword=keyword or None,
        limit=limit,
        offset=offset,
    )
    result = ListCustomersQuery()(customer_query)
    customer_payload, page_error = _admin_customer_payload_from_list_result(
        result=result,
        keyword=keyword,
        owner=owner,
        mobile=mobile,
        tag=tag,
        limit=limit,
        offset=offset,
    )
    context = _shell_context(
        request=request,
        page_title="客户激活 / 客户列表",
        page_summary="查看客户列表、筛选客户并打开客户档案。",
        active_endpoint="api.admin_console_customers",
    )
    context["page_error"] = page_error
    context["customer_payload"] = customer_payload
    return templates.TemplateResponse(request, "admin_console/customers.html", context)


@router.get("/admin/customers/{external_userid}", name="api.admin_console_customer_detail")
def admin_customer_detail_page(request: Request, external_userid: str, tab: str = ""):
    result = GetAdminCustomerProfileQuery()(external_userid=external_userid)
    payload = _customer_detail_payload_from_profile_result(result, legacy_tab=tab)
    if not payload:
        status_code = int(result.get("status_code") or 404)
        page_error = str(result.get("page_error") or result.get("error") or "未找到客户")
        context = _shell_context(
            request=request,
            page_title="客户不存在",
            page_summary="当前客户编号没有查到对应客户。",
            active_endpoint="api.admin_console_customers",
        )
        context.update(
            {
                "breadcrumbs": [
                    {"label": "客户管理后台", "href": request.url_for("api.admin_console_dashboard")},
                    {"label": "客户", "href": "/admin/customers"},
                    {"label": external_userid, "href": ""},
                ],
                "actions": [{"label": "返回客户列表", "href": "/admin/customers", "variant": "secondary"}],
                "state_title": "客户不存在",
                "state_body": "请确认客户编号是否正确，或稍后重试。",
                "state_items": ["检查客户编号是否输入正确", "确认当前环境已经同步到该客户数据"],
                "table_rows": [],
                "page_error": page_error,
            }
        )
        return templates.TemplateResponse(request, "admin_console/placeholder.html", context, status_code=status_code)

    customer = payload["customer"]
    customer_name = str(customer.get("customer_name") or external_userid)
    context = _shell_context(
        request=request,
        page_title=customer_name,
        page_summary="查看客户基础资料、实时标签、问卷问答和聊天记录。",
        active_endpoint="api.admin_console_customers",
    )
    context.update(
        {
            "breadcrumbs": [
                {"label": "客户管理后台", "href": request.url_for("api.admin_console_dashboard")},
                {"label": "客户", "href": "/admin/customers"},
                {"label": customer_name, "href": ""},
            ],
            "customer_payload": payload,
            "page_error": str(result.get("page_error") or ""),
            "admin_action_token": "",
            "action_result": {},
            "customer_profile_urls": _customer_profile_urls(str(customer.get("external_userid") or external_userid)),
        }
    )
    return templates.TemplateResponse(request, "admin_console/customer_detail.html", context)


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
        page_summary="集中管理企业客户标签：同步、搜索、新增、编辑、删除和复制 tag_id。",
        active_endpoint="api.admin_wecom_tags_page",
    )
    context["breadcrumbs"] = [
        {"label": "客户管理后台", "href": request.url_for("api.admin_console_dashboard")},
        {"label": "企微标签管理"},
    ]
    return templates.TemplateResponse(request, "admin_console/config_wecom_tags.html", context)


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
    try:
        program_list_payload = list_automation_programs_payload()
    except AutomationProgramDataUnavailable:
        program_list_payload = {"items": [], "default_program": {}, "total": 0, "source_status": "next_postgres_unavailable"}
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


def _automation_program_workspace_tabs(request: Request, program_id: int, active_key: str) -> list[dict[str, object]]:
    tabs = (
        ("overview", "概览", "api.admin_automation_program_overview"),
        ("setup", "配置向导", "api.admin_automation_program_setup"),
        ("entry_channels", "入口渠道", "api.admin_automation_program_entry_channels"),
    )
    return [
        {
            "key": key,
            "label": label,
            "summary": "",
            "href": _legacy_url_for(endpoint, program_id=int(program_id)),
            "active": key == active_key,
        }
        for key, label, endpoint in tabs
    ]


def _automation_program_context(request: Request, program: dict[str, object], *, active_key: str) -> dict[str, object]:
    program_id = int(program.get("id") or 0)
    return {
        "id": program_id,
        "program_code": str(program.get("program_code") or ""),
        "program_name": str(program.get("program_name") or ""),
        "description": str(program.get("description") or ""),
        "status": str(program.get("status") or "draft"),
        "list_href": _legacy_url_for("api.admin_automation_conversion"),
        "overview_href": _legacy_url_for("api.admin_automation_program_overview", program_id=program_id),
        "update_href": _legacy_url_for("api.admin_automation_program_update", program_id=program_id),
        "copy_href": _legacy_url_for("api.admin_automation_program_copy", program_id=program_id),
        "activate_href": _legacy_url_for("api.admin_automation_program_activate", program_id=program_id),
        "pause_href": _legacy_url_for("api.admin_automation_program_pause", program_id=program_id),
        "archive_href": _legacy_url_for("api.admin_automation_program_archive", program_id=program_id),
        "active_key": active_key,
    }


def _automation_program_not_found(request: Request, program_id: int) -> Response:
    context = _shell_context(
        request=request,
        page_title="自动化运营方案不存在",
        page_summary="没有找到对应的自动化运营方案。",
        active_endpoint="api.admin_automation_conversion",
    )
    context.update(
        {
            "breadcrumbs": [
                {"label": "客户管理后台", "href": request.url_for("api.admin_console_dashboard")},
                {"label": "自动化运营", "href": request.url_for("api.admin_automation_conversion")},
                {"label": f"方案 {program_id}"},
            ],
            "state_title": "方案不存在",
            "state_body": f"没有找到 ID 为 {program_id} 的自动化运营方案。",
            "state_items": ["请从自动化运营方案列表重新进入", "生产环境直接读取 Next PostgreSQL 方案表"],
            "actions": [{"label": "返回方案列表", "href": request.url_for("api.admin_automation_conversion"), "variant": "primary"}],
        }
    )
    return templates.TemplateResponse(request, "admin_console/placeholder.html", context, status_code=404)


def _setup_workspace(request: Request, program: dict[str, object], summary: dict[str, object], *, step: str) -> dict[str, object]:
    program_id = int(program.get("id") or 0)
    normalized_step = step if step in {item["key"] for item in SETUP_STEPS} else "basic"
    try:
        workspace = get_automation_program_setup_payload(program_id, step=normalized_step)
    except AutomationProgramDataUnavailable:
        workspace = {
            "program": program,
            "summary": summary,
            "step": normalized_step,
            "steps": list(SETUP_STEPS),
            "is_default_program": str(program.get("program_code") or "") == "signup_conversion_v1",
            "basic": dict(program.get("config_json") or {}),
            "entry_channel": {},
            "entry": {"channels": [], "qrcode_channel": {}, "customer_acquisition_links": []},
            "segmentation": {},
            "audience_entry_rule": {},
            "operations": {"tasks": [], "active_count": 0},
            "publish_check": {},
        }
    workspace["program"] = workspace.get("program") or program
    workspace["summary"] = workspace.get("summary") or summary
    workspace["urls"] = {
        "base": _legacy_url_for("api.admin_automation_program_setup", program_id=program_id),
        "overview": _legacy_url_for("api.admin_automation_program_overview", program_id=program_id),
        "entry_channels": _legacy_url_for("api.admin_automation_program_entry_channels", program_id=program_id),
        "update": _legacy_url_for("api.admin_automation_program_update", program_id=program_id),
        "copy": _legacy_url_for("api.admin_automation_program_copy", program_id=program_id),
        "basic": _legacy_url_for("api.admin_automation_program_update", program_id=program_id),
    }
    workspace["operations_workspace"] = {
        "program_id": program_id,
        "api_urls": {
            "groups": f"/api/admin/automation-conversion/task-groups?program_id={program_id}&limit=300",
            "tasks": f"/api/admin/automation-conversion/tasks?program_id={program_id}&limit=300",
            "task_base": "/api/admin/automation-conversion/tasks/0",
            "profile_segment_templates_options": f"/api/admin/automation-conversion/profile-segment-templates/options?program_id={program_id}",
            "profile_segment_template_detail_base": "/api/admin/automation-conversion/profile-segment-templates/0",
        },
    }
    return workspace


def _overview_workspace(request: Request, program: dict[str, object], summary: dict[str, object]) -> dict[str, object]:
    program_id = int(program.get("id") or 0)
    return {
        "program": program,
        "summary": summary,
        "api_urls": {
            "dashboard": f"/api/admin/automation-conversion/overview?program_id={program_id}",
        },
    }


@router.get("/admin/automation-conversion/programs/{program_id:int}/setup", name="api.admin_automation_program_setup")
def admin_automation_program_setup(request: Request, program_id: int) -> Response:
    data = get_automation_program_with_summary(int(program_id))
    if not data:
        return _automation_program_not_found(request, program_id)
    program = dict(data.get("program") or {})
    summary = dict(data.get("summary") or {})
    context = _shell_context(
        request=request,
        page_title="自动化运营方案",
        page_summary="按方案配置基础信息、入口渠道、分层规则、入池规则、运营编排和发布检查。",
        active_endpoint="api.admin_automation_conversion",
    )
    context.update(
        {
            "breadcrumbs": [
                {"label": "客户管理后台", "href": request.url_for("api.admin_console_dashboard")},
                {"label": "自动化运营方案", "href": request.url_for("api.admin_automation_conversion")},
                {
                    "label": str(program.get("program_name") or f"方案 {program_id}"),
                    "href": request.url_for("api.admin_automation_program_overview", program_id=program_id),
                },
            ],
            "setup_workspace": _setup_workspace(request, program, summary, step=str(request.query_params.get("step") or "basic")),
            "workspace_tabs": _automation_program_workspace_tabs(request, program_id, "setup"),
            "program_context": _automation_program_context(request, program, active_key="setup"),
            "admin_action_token": "",
        }
    )
    return templates.TemplateResponse(request, "admin_console/automation_program_setup_next.html", context)


@router.get("/admin/automation-conversion/programs/{program_id:int}/overview", name="api.admin_automation_program_overview")
def admin_automation_program_overview(request: Request, program_id: int) -> Response:
    data = get_automation_program_with_summary(int(program_id))
    if not data:
        return _automation_program_not_found(request, program_id)
    program = dict(data.get("program") or {})
    summary = dict(data.get("summary") or {})
    context = _shell_context(
        request=request,
        page_title="自动化运营方案概览",
        page_summary="查看当前方案的发布状态、入口、运营编排和最近执行情况。",
        active_endpoint="api.admin_automation_conversion",
    )
    context.update(
        {
            "breadcrumbs": [
                {"label": "客户管理后台", "href": request.url_for("api.admin_console_dashboard")},
                {"label": "自动化运营方案", "href": request.url_for("api.admin_automation_conversion")},
                {"label": str(program.get("program_name") or f"方案 {program_id}")},
            ],
            "overview_workspace": _overview_workspace(request, program, summary),
            "workspace_tabs": _automation_program_workspace_tabs(request, program_id, "overview"),
            "program_context": _automation_program_context(request, program, active_key="overview"),
            "admin_action_token": "",
        }
    )
    return templates.TemplateResponse(request, "admin_console/automation_program_overview_next.html", context)


@router.get("/admin/automation-conversion/programs/{program_id:int}/copy", name="api.admin_automation_program_copy_form")
def admin_automation_program_copy_form(request: Request, program_id: int) -> Response:
    data = get_automation_program_with_summary(int(program_id))
    if not data:
        return _automation_program_not_found(request, program_id)
    program = dict(data.get("program") or {})
    context = _shell_context(
        request=request,
        page_title="复制自动化运营方案",
        page_summary="复制当前方案配置，不复制成员、执行记录和运行日志。",
        active_endpoint="api.admin_automation_conversion",
    )
    context.update(
        {
            "breadcrumbs": [
                {"label": "客户管理后台", "href": request.url_for("api.admin_console_dashboard")},
                {"label": "自动化运营方案", "href": request.url_for("api.admin_automation_conversion")},
                {"label": "复制方案"},
            ],
            "copy_source_program": program,
            "copy_action": _legacy_url_for("api.admin_automation_program_copy", program_id=program_id),
            "cancel_href": _legacy_url_for("api.admin_automation_program_overview", program_id=program_id),
            "admin_action_token": "",
        }
    )
    return templates.TemplateResponse(request, "admin_console/automation_program_copy_next.html", context)


@router.post("/admin/automation-conversion/programs/{program_id:int}/copy", name="api.admin_automation_program_copy")
async def admin_automation_program_copy(request: Request, program_id: int) -> Response:
    form = await request.form()
    copied = copy_automation_program(
        int(program_id),
        operator_id="admin",
        payload={
            "program_name": form.get("program_name"),
            "program_code": form.get("program_code"),
        },
    )
    copied_program = dict(copied.get("program") or {})
    copied_id = int(copied_program.get("id") or 0)
    return RedirectResponse(
        _legacy_url_for("api.admin_automation_program_setup", program_id=copied_id, step="basic"),
        status_code=303,
    )


@router.post("/admin/automation-conversion/programs/{program_id:int}/update", name="api.admin_automation_program_update")
async def admin_automation_program_update(request: Request, program_id: int) -> Response:
    form = await request.form()
    update_automation_program_basic_info(
        int(program_id),
        {
            "program_name": form.get("program_name"),
            "program_code": form.get("program_code"),
            "description": form.get("description"),
            "status": form.get("status"),
        },
        operator_id="admin",
    )
    next_url = str(form.get("next") or "").strip()
    if not next_url or not next_url.startswith("/"):
        next_url = _legacy_url_for("api.admin_automation_program_setup", program_id=program_id, step="basic")
    return RedirectResponse(next_url, status_code=303)


async def _automation_program_status_redirect(request: Request, program_id: int, status: str) -> Response:
    form = await request.form()
    update_automation_program_status(int(program_id), status=status, operator_id="admin")
    next_url = str(form.get("next") or "").strip()
    if not next_url or not next_url.startswith("/"):
        next_url = _legacy_url_for("api.admin_automation_conversion")
    return RedirectResponse(next_url, status_code=303)


@router.post("/admin/automation-conversion/programs/{program_id:int}/pause", name="api.admin_automation_program_pause")
async def admin_automation_program_pause(request: Request, program_id: int) -> Response:
    return await _automation_program_status_redirect(request, program_id, "paused")


@router.post("/admin/automation-conversion/programs/{program_id:int}/activate", name="api.admin_automation_program_activate")
async def admin_automation_program_activate(request: Request, program_id: int) -> Response:
    return await _automation_program_status_redirect(request, program_id, "active")


@router.post("/admin/automation-conversion/programs/{program_id:int}/archive", name="api.admin_automation_program_archive")
async def admin_automation_program_archive(request: Request, program_id: int) -> Response:
    return await _automation_program_status_redirect(request, program_id, "archived")


def _group_ops_page_context(
    request: Request,
    *,
    page_title: str,
    page_summary: str,
    page_mode: str,
    plan_id: int | None = None,
) -> dict:
    context = _shell_context(
        request=request,
        page_title=page_title,
        page_summary=page_summary,
        active_endpoint="api.admin_group_ops_ui",
    )
    context.update(
        {
            "breadcrumbs": [
                {"label": "客户管理后台", "href": request.url_for("api.admin_console_dashboard")},
                {"label": "群运营计划", "href": request.url_for("api.admin_group_ops_ui")},
            ],
            "group_ops_page_mode": page_mode,
            "group_ops_plan_id": int(plan_id or 0),
            "page_actions": [],
        }
    )
    if page_mode != "list":
        context["breadcrumbs"].append({"label": page_title})
    return context


def _channel_form_payload(request: Request, *, channel: dict | None) -> dict:
    del request
    is_edit = bool(channel)
    channel_id = int((channel or {}).get("id") or 0)
    return {
        "channel": channel or default_channel_form_payload(),
        "is_edit": is_edit,
        "api_urls": {
            "channels": "/api/admin/channels",
            "detail": f"/api/admin/channels/{channel_id}" if is_edit else "",
            "qrcode_download": f"/api/admin/channels/{channel_id}/qrcode/download" if is_edit else "",
            "share_link": f"/api/admin/channels/{channel_id}/share-link" if is_edit else "",
            "welcome_materials": "/api/admin/channel-welcome-materials",
            "wecom_tags": "/api/admin/wecom/tags",
        },
    }


@router.get("/admin/automation-conversion/group-ops/ui", name="api.admin_group_ops_ui")
def admin_group_ops_ui(request: Request):
    context = _group_ops_page_context(
        request,
        page_title="群运营计划",
        page_summary="按计划管理客户群运营内容。",
        page_mode="list",
    )
    return templates.TemplateResponse(request, "admin_console/group_ops.html", context)


@router.get("/admin/automation-conversion/group-ops/plans/{plan_id:int}", name="api.admin_group_ops_plan_detail")
def admin_group_ops_plan_detail(request: Request, plan_id: int):
    context = _group_ops_page_context(
        request,
        page_title="群运营计划",
        page_summary="配置运营成员、群包和计划内容。",
        page_mode="detail",
        plan_id=plan_id,
    )
    return templates.TemplateResponse(request, "admin_console/group_ops.html", context)


@router.get("/admin/automation-conversion/group-ops/groups/ui", name="api.admin_group_ops_groups_ui")
def admin_group_ops_groups_ui(request: Request):
    context = _group_ops_page_context(
        request,
        page_title="查看所有群",
        page_summary="按群名、群主、所属计划和状态查看客户群。",
        page_mode="groups",
    )
    return templates.TemplateResponse(request, "admin_console/group_ops.html", context)


@router.get("/admin/channels", name="api.admin_channels_page")
async def admin_channels_page(request: Request) -> Response:
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
            "channel_center_payload": {
                "api_urls": {
                    "channels": "/api/admin/channels?limit=300",
                    "contacts_base": "/api/admin/channels/0/contacts",
                    "bindings_base": "/api/admin/channels/0/bindings",
                }
            },
        }
    )
    return templates.TemplateResponse(request, "admin_console/channel_code_center.html", context)


@router.get("/admin/channels/new", name="api.admin_channel_new_page")
async def admin_channel_new_page(request: Request) -> Response:
    context = _shell_context(
        request=request,
        page_title="新建渠道",
        page_summary="创建渠道资产本身，不在渠道中心绑定自动化运营。普通二维码和企微获客助手链接按载体类型显示不同操作。",
        active_endpoint="api.admin_channels_page",
    )
    context.update(
        {
            "breadcrumbs": [
                {"label": "客户管理后台", "href": request.url_for("api.admin_console_dashboard")},
                {"label": "渠道码中心", "href": request.url_for("api.admin_channels_page")},
                {"label": "新建渠道"},
            ],
            "channel_form_payload": _channel_form_payload(request, channel=None),
            "admin_action_token": "",
        }
    )
    return templates.TemplateResponse(request, "admin_console/channel_code_form.html", context)


@router.get("/admin/channels/{channel_id:int}/edit", name="api.admin_channel_edit_page")
async def admin_channel_edit_page(request: Request, channel_id: int) -> Response:
    channel = get_channel_resource(int(channel_id))
    if not channel:
        context = _shell_context(
            request=request,
            page_title="渠道不存在",
            page_summary="当前没有找到这个渠道。",
            active_endpoint="api.admin_channels_page",
        )
        context.update(
            {
                "breadcrumbs": [
                    {"label": "客户管理后台", "href": request.url_for("api.admin_console_dashboard")},
                    {"label": "渠道码中心", "href": request.url_for("api.admin_channels_page")},
                    {"label": f"编辑渠道 {channel_id}"},
                ],
                "state_title": "渠道不存在",
                "state_body": "请确认渠道编号是否正确，或回到渠道码中心重新选择。",
                "state_items": ["渠道可能已被删除", "当前环境也可能还没有初始化渠道数据"],
                "actions": [{"label": "返回渠道码中心", "href": request.url_for("api.admin_channels_page"), "variant": "secondary"}],
            }
        )
        return templates.TemplateResponse(request, "admin_console/placeholder.html", context, status_code=404)
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
            "channel_form_payload": _channel_form_payload(request, channel=channel),
            "admin_action_token": "",
        }
    )
    return templates.TemplateResponse(request, "admin_console/channel_code_form.html", context)


@router.get(
    "/admin/automation-conversion/programs/{program_id:int}/entry-channels",
    name="api.admin_automation_program_entry_channels",
)
async def admin_automation_program_entry_channels(request: Request, program_id: int) -> Response:
    data = get_automation_program_with_summary(int(program_id))
    if not data:
        return _automation_program_not_found(request, program_id)
    program = dict(data.get("program") or {})
    bindings = list_program_channel_bindings_resource(int(program_id))
    candidate_channels = list_program_entry_candidate_channels(int(program_id))
    context = _shell_context(
        request=request,
        page_title="入口渠道",
        page_summary="在自动化运营方案内绑定已有渠道码；普通二维码和企微获客助手链接都可以作为入口。",
        active_endpoint="api.admin_automation_conversion",
    )
    context.update(
        {
            "breadcrumbs": [
                {"label": "客户管理后台", "href": request.url_for("api.admin_console_dashboard")},
                {"label": "自动化运营", "href": request.url_for("api.admin_automation_conversion")},
                {
                    "label": str(program.get("program_name") or f"方案 {program_id}"),
                    "href": request.url_for("api.admin_automation_program_overview", program_id=program_id),
                },
                {"label": "入口渠道"},
            ],
            "workspace_tabs": _automation_program_workspace_tabs(request, program_id, "entry_channels"),
            "program_context": _automation_program_context(request, program, active_key="entry_channels"),
            "entry_channels_payload": jsonable_encoder(
                {
                    "program": program,
                    "bindings": bindings,
                    "candidate_channels": candidate_channels,
                    "api_urls": {
                        "bindings": f"/api/admin/automation-conversion/programs/{program_id}/channel-bindings",
                        "binding_base": f"/api/admin/automation-conversion/programs/{program_id}/channel-bindings/0",
                    },
                }
            ),
            "admin_action_token": "",
        }
    )
    return templates.TemplateResponse(request, "admin_console/automation_conversion_entry_channels.html", context)


@router.get("/admin/wechat-pay/transactions", name="api.admin_wechat_pay_transactions_page")
async def admin_wechat_pay_transactions(request: Request) -> Response:
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
    return templates.TemplateResponse(request, "admin_console/image_library.html", context)


@router.get("/admin/miniprogram-library", name="api.admin_miniprogram_library_workspace")
def admin_miniprogram_library(request: Request):
    context = _shell_context(
        request=request,
        page_title="小程序素材库",
        page_summary="维护群发和自动化可复用的小程序卡片。",
        active_endpoint="api.admin_miniprogram_library_workspace",
    )
    return templates.TemplateResponse(request, "admin_console/miniprogram_library.html", context)


@router.get("/admin/attachment-library", name="api.admin_attachment_library_workspace")
def admin_attachment_library(request: Request):
    context = _shell_context(
        request=request,
        page_title="附件素材库",
        page_summary="维护 PDF、附件和课程资料等可复用素材。",
        active_endpoint="api.admin_attachment_library_workspace",
    )
    return templates.TemplateResponse(request, "admin_console/attachment_library.html", context)


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


@router.api_route("/admin/config", methods=_ALL_METHODS, name="api.admin_config")
@router.api_route("/admin/config/{path:path}", methods=_ALL_METHODS, name="api.admin_config_legacy_path")
@router.api_route("/api/admin/config/{path:path}", methods=_ALL_METHODS, name="api.admin_config_legacy_api_path")
@router.api_route("/setup/wizard", methods=_ALL_METHODS, name="api.setup_wizard")
@router.api_route("/setup/wizard/save", methods=_ALL_METHODS, name="api.setup_wizard_save")
async def admin_config_legacy_facade(request: Request) -> Response:
    return await forward_to_legacy_flask(request)


@router.get("/admin/runtime-config", name="api.admin_runtime_config")
def admin_runtime_config(request: Request):
    context = _shell_context(
        request=request,
        page_title="运行配置",
        page_summary="查看 Next 运行时、发布和外部回调预检状态。",
        active_endpoint="api.admin_runtime_config",
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
    context.update(
        {
            "breadcrumbs": [
                {"label": "客户管理后台", "href": request.url_for("api.admin_console_dashboard")},
                {"label": "API 文档"},
            ],
            **build_api_docs_view_model(frontend_router=router),
        }
    )
    return templates.TemplateResponse(request, "admin_console/api_docs.html", context)


@router.get("/api/frontend-compat/legacy-routes")
def legacy_routes_manifest() -> dict:
    return {
        "ok": True,
        "frontend_parity_policy": "1:1 replicate existing AI-CRM admin frontend; do not redesign",
        "routes": LEGACY_FRONTEND_ROUTES,
    }
