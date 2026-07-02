from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from aicrm_next.data_health.application import data_health_summary
from aicrm_next.delivery_lineage.application import (
    get_delivery_lineage,
    list_delivery_lineage,
    list_delivery_lineage_by_trace,
    list_delivery_lineage_by_unionid,
)

from .navigation import admin_path_for, shell_context
from .view_model import AdminShellApiClient

router = APIRouter()
_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=_TEMPLATES_DIR)


@router.get("/admin", name="api.admin_console_dashboard")
def admin_dashboard(request: Request):
    client = AdminShellApiClient(active_endpoint="api.admin_automation_conversion")
    context = shell_context(
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
            "dashboard_cards": client.dashboard_cards(),
            "todo_total": 0,
            "todo_groups": [],
            "quick_links": [
                {
                    "label": "客户激活 / 客户列表",
                    "description": "查看客户列表和激活状态。",
                    "href": admin_path_for("api.admin_console_customers"),
                },
                {
                    "label": "AI 助手",
                    "description": "进入 AI 助手兼容入口。",
                    "href": admin_path_for("api.admin_cloud_orchestrator_workspace"),
                },
            ],
            "loading_state": {"enabled": True, "label": "加载后台总览"},
            "empty_state": {"title": "暂无待处理事项", "body": "当前没有需要优先处理的问题。"},
            "error_state": {"title": "后台总览加载失败", "body": "请稍后刷新。"},
        }
    )
    return templates.TemplateResponse(request, "admin_shell/dashboard.html", context)


@router.get("/admin/p1/group-ops-workspace", name="api.admin_p1_group_ops_workspace")
def admin_p1_group_ops_workspace(request: Request):
    context = shell_context(
        request=request,
        page_title="P1 Native Group Ops Workspace",
        page_summary="TS-native draft-only / preview-only 群运营工作台壳；不发送、不审批、不写生产。",
        active_endpoint="api.admin_p1_group_ops_workspace",
    )
    context.update(
        {
            "breadcrumbs": [
                {"label": "客户管理后台", "href": admin_path_for("api.admin_console_dashboard")},
                {"label": "P1 Group Ops Workspace", "href": ""},
            ],
            "page_actions": [
                {
                    "label": "返回群运营计划",
                    "href": admin_path_for("api.admin_group_ops_ui"),
                    "variant": "secondary",
                },
            ],
        }
    )
    return templates.TemplateResponse(request, "admin_shell/p1_group_ops_workspace.html", context)


@router.get("/admin/data-health", name="api.admin_data_health_page")
def admin_data_health_page(request: Request):
    summary = data_health_summary()
    context = shell_context(
        request=request,
        page_title="数据健康",
        page_summary="查看 identity、schema drift、队列和事实归属检查的当前状态。",
        active_endpoint="api.admin_data_health_page",
    )
    context.update(
        {
            "breadcrumbs": [
                {"label": "客户管理后台", "href": admin_path_for("api.admin_console_dashboard")},
                {"label": "数据健康", "href": ""},
            ],
            "page_actions": [
                {
                    "label": "查看 API",
                    "href": "/api/admin/data-health/summary",
                    "variant": "secondary",
                },
            ],
            "health_summary": summary,
            "health_cards": _data_health_cards(summary),
        }
    )
    return templates.TemplateResponse(request, "admin_shell/data_health.html", context)


@router.get("/admin/delivery-lineage", name="api.admin_delivery_lineage_page")
def admin_delivery_lineage_page(request: Request):
    filters = _delivery_lineage_filters(request)
    payload = _delivery_lineage_payload(filters)
    context = shell_context(
        request=request,
        page_title="投递排障",
        page_summary="按 unionid、broadcast job、external effect 或 trace 查询统一投递链路。",
        active_endpoint="api.admin_delivery_lineage_page",
    )
    context.update(
        {
            "breadcrumbs": [
                {"label": "客户管理后台", "href": admin_path_for("api.admin_console_dashboard")},
                {"label": "投递排障", "href": ""},
            ],
            "page_actions": [
                {
                    "label": "查看 API",
                    "href": "/api/admin/delivery-lineage",
                    "variant": "secondary",
                },
            ],
            "filters": filters,
            "lineage_items": payload.get("items") or ([] if not payload.get("item") else [payload["item"]]),
            "lineage_error": payload.get("error_code", ""),
        }
    )
    return templates.TemplateResponse(request, "admin_shell/delivery_lineage.html", context)


@router.get("/api/admin/dashboard/shell-context", name="api.admin_dashboard_shell_context")
def admin_dashboard_shell_context() -> dict:
    return AdminShellApiClient().shell_context_payload()


@router.get("/admin/logout", name="api.admin_logout_compat")
def admin_logout_compat() -> RedirectResponse:
    return RedirectResponse(admin_path_for("api.admin_logout"), status_code=302)


def _data_health_cards(summary: dict) -> list[dict[str, str]]:
    counts = summary.get("counts") or {}
    fail_count = int(counts.get("fail") or 0)
    warn_count = int(counts.get("warn") or 0)
    ok_count = int(counts.get("ok") or 0)
    pending_count = int(counts.get("not_applicable") or 0)
    return [
        {
            "label": "红色",
            "value": str(fail_count),
            "description": "schema drift、runtime reference、orphan facts 等阻断项。",
            "tone": "danger" if fail_count else "ok",
        },
        {
            "label": "黄色",
            "value": str(warn_count),
            "description": "队列积压、投影延迟、缺 owner 等需关注项。",
            "tone": "warn" if warn_count else "ok",
        },
        {
            "label": "绿色",
            "value": str(ok_count),
            "description": "当前证据已经通过的治理检查。",
            "tone": "ok",
        },
        {
            "label": "待接入",
            "value": str(pending_count),
            "description": "未配置 DB 探针或仍待接生产安全读仓库的检查。",
            "tone": "neutral" if pending_count else "ok",
        },
    ]


def _delivery_lineage_filters(request: Request) -> dict[str, str]:
    params = request.query_params
    return {
        "unionid": str(params.get("unionid") or "").strip(),
        "broadcast_job_id": str(params.get("broadcast_job_id") or "").strip(),
        "external_effect_job_id": str(params.get("external_effect_job_id") or "").strip(),
        "trace_id": str(params.get("trace_id") or "").strip(),
    }


def _delivery_lineage_payload(filters: dict[str, str]) -> dict:
    if filters["broadcast_job_id"]:
        return get_delivery_lineage(f"broadcast:{filters['broadcast_job_id']}")
    if filters["external_effect_job_id"]:
        return get_delivery_lineage(f"external_effect:{filters['external_effect_job_id']}")
    if filters["unionid"]:
        return list_delivery_lineage_by_unionid(filters["unionid"])
    if filters["trace_id"]:
        return list_delivery_lineage_by_trace(filters["trace_id"])
    return list_delivery_lineage()
