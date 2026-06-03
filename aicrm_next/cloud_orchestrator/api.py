from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from aicrm_next.admin_jobs.routes import (
    _action_token_error,
    _operator_from_request,
    _request_payload,
    ensure_admin_action_token,
)
from aicrm_next.frontend_compat.admin_shell import shell_context

from .application import (
    ApproveCloudPlanCommand,
    ApproveCloudPlanRecipientCommand,
    CloudPlanNotFoundError,
    GetCloudPlanQuery,
    GetCloudPlanRecipientQuery,
    ListCloudPlanRecipientsQuery,
    ListCloudPlansQuery,
    RejectCloudPlanCommand,
    RejectCloudPlanRecipientCommand,
    UpdateCloudPlanRecipientMessageCommand,
)
from .campaigns_read import (
    GetCloudCampaignQuery,
    ListCloudCampaignMembersQuery,
    ListCloudCampaignStepsQuery,
    ListCloudCampaignsQuery,
    ROUTE_OWNER as CAMPAIGN_READ_ROUTE_OWNER,
    SOURCE_STATUS as CAMPAIGN_READ_SOURCE_STATUS,
)
from .media_upload import build_upload_command, diagnostics_payload

router = APIRouter()
_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "frontend_compat" / "templates"
templates = Jinja2Templates(directory=_TEMPLATES_DIR)

_MEDIA_UPLOAD_HEADERS = {
    "X-AICRM-Route-Owner": "ai_crm_next",
    "X-AICRM-Fallback-Used": "false",
    "X-AICRM-Real-External-Call-Executed": "false",
    "X-AICRM-WeCom-Media-Upload-Executed": "false",
}
_CAMPAIGN_READ_HEADERS = {
    "X-AICRM-Route-Owner": "ai_crm_next",
    "X-AICRM-Fallback-Used": "false",
    "X-AICRM-Real-External-Call-Executed": "false",
}


def _raise(exc: Exception) -> None:
    if isinstance(exc, CloudPlanNotFoundError) or isinstance(exc, LookupError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail=str(exc)) from exc


def _media_error(error: str, *, status_code: int = 400) -> JSONResponse:
    payload = diagnostics_payload()
    payload.update({"ok": False, "error": error})
    return JSONResponse(payload, status_code=status_code, headers=_MEDIA_UPLOAD_HEADERS)


def _campaign_read_error(error: str, *, status_code: int = 404) -> JSONResponse:
    return JSONResponse(
        {
            "ok": False,
            "error": error,
            "source_status": CAMPAIGN_READ_SOURCE_STATUS,
            "route_owner": CAMPAIGN_READ_ROUTE_OWNER,
            "fallback_used": False,
            "real_external_call_executed": False,
        },
        status_code=status_code,
        headers=_CAMPAIGN_READ_HEADERS,
    )


async def _write_context(request: Request) -> tuple[dict[str, Any], str | None]:
    payload = await _request_payload(request)
    token_error = await _action_token_error(request, payload)
    if token_error:
        return payload, token_error
    return payload, None


@router.get(
    "/admin/cloud-orchestrator/plans",
    response_class=HTMLResponse,
    name="api.admin_cloud_orchestrator_plans_workspace",
)
def admin_cloud_plans(request: Request):
    context = shell_context(
        request=request,
        page_title="AI 助手 · 运营计划审阅",
        page_summary="计划列表、目标人员明细与逐人审批。",
        active_endpoint="api.admin_cloud_orchestrator_workspace",
    )
    context.update(
        {
            "breadcrumbs": [
                {"label": "客户管理后台", "href": request.url_for("api.admin_console_dashboard")},
                {"label": "AI 助手", "href": request.url_for("api.admin_cloud_orchestrator_workspace")},
                {"label": "运营计划审阅"},
            ],
            "page_mode": "list",
            "plan_id": "",
            "admin_action_token": ensure_admin_action_token(),
        }
    )
    return templates.TemplateResponse(request, "admin_console/cloud_plan_review.html", context)


@router.get(
    "/admin/cloud-orchestrator/campaigns",
    response_class=HTMLResponse,
    name="api.admin_cloud_orchestrator_campaigns_workspace",
)
def admin_cloud_campaigns(request: Request):
    context = shell_context(
        request=request,
        page_title="AI 助手 · 运营计划审阅",
        page_summary="Agent 上架的多分层多步骤运营计划在这里审阅启动。",
        active_endpoint="api.admin_cloud_orchestrator_workspace",
    )
    context.update(
        {
            "breadcrumbs": [
                {"label": "客户管理后台", "href": request.url_for("api.admin_console_dashboard")},
                {"label": "AI 助手", "href": request.url_for("api.admin_cloud_orchestrator_workspace")},
                {"label": "运营计划审阅"},
            ],
            "page_actions": [
                {
                    "label": "可观察性",
                    "href": "/admin/cloud-orchestrator/observability",
                    "variant": "ghost",
                },
            ],
        }
    )
    return templates.TemplateResponse(request, "admin_console/cloud_campaigns_workspace.html", context)


@router.options("/api/admin/cloud-orchestrator/media/upload")
def api_cloud_orchestrator_media_upload_options() -> JSONResponse:
    payload = diagnostics_payload()
    payload.update({"allowed_methods": ["POST", "OPTIONS"]})
    return JSONResponse(payload, headers=_MEDIA_UPLOAD_HEADERS)


@router.post("/api/admin/cloud-orchestrator/media/upload")
async def api_cloud_orchestrator_media_upload(
    request: Request,
    image: UploadFile | None = File(default=None),
    idempotency_key: str = Header(default="", alias="Idempotency-Key"),
) -> JSONResponse:
    if image is None or not image.filename:
        return _media_error("missing_image")
    content_type = str(image.content_type or "").strip().lower()
    if not content_type.startswith("image/"):
        return _media_error("invalid_content_type")
    file_bytes = await image.read()
    operator = str(request.headers.get("X-AICRM-Actor") or "admin_ui").strip()
    trace_id = str(request.headers.get("X-AICRM-Trace-Id") or "").strip()
    command = build_upload_command(
        idempotency_key=idempotency_key,
        actor_id=operator,
        actor_type="admin",
        trace_id=trace_id,
    )
    try:
        payload = command(file_name=image.filename, file_bytes=file_bytes, content_type=content_type)
    except ValueError as exc:
        return _media_error(str(exc))
    return JSONResponse(payload, headers=_MEDIA_UPLOAD_HEADERS)


@router.get("/api/admin/cloud-orchestrator/campaigns")
def api_list_cloud_campaigns(
    review_status: str = "",
    run_status: str = "",
    group_code: str = "",
    limit: int = 5000,
    offset: int = 0,
) -> JSONResponse:
    payload = ListCloudCampaignsQuery()(
        review_status=review_status,
        run_status=run_status,
        group_code=group_code,
        limit=limit,
        offset=offset,
    )
    return JSONResponse(payload, headers=_CAMPAIGN_READ_HEADERS)


@router.get("/api/admin/cloud-orchestrator/campaigns/{campaign_code}")
def api_get_cloud_campaign(campaign_code: str) -> JSONResponse:
    try:
        payload = GetCloudCampaignQuery()(campaign_code)
    except LookupError as exc:
        return _campaign_read_error(str(exc) or "campaign_not_found")
    except Exception as exc:
        return _campaign_read_error(str(exc) or "campaign_read_unavailable", status_code=503)
    return JSONResponse(payload, headers=_CAMPAIGN_READ_HEADERS)


@router.get("/api/admin/cloud-orchestrator/campaigns/{campaign_code}/members")
def api_list_cloud_campaign_members(campaign_code: str, status: str = "", limit: int = 200, offset: int = 0) -> JSONResponse:
    try:
        payload = ListCloudCampaignMembersQuery()(campaign_code, status=status, limit=limit, offset=offset)
    except LookupError as exc:
        return _campaign_read_error(str(exc) or "campaign_not_found")
    except Exception as exc:
        return _campaign_read_error(str(exc) or "campaign_members_unavailable", status_code=503)
    return JSONResponse(payload, headers=_CAMPAIGN_READ_HEADERS)


@router.get("/api/admin/cloud-orchestrator/campaigns/{campaign_code}/steps")
def api_list_cloud_campaign_steps(campaign_code: str) -> JSONResponse:
    try:
        payload = ListCloudCampaignStepsQuery()(campaign_code)
    except LookupError as exc:
        return _campaign_read_error(str(exc) or "campaign_not_found")
    except Exception as exc:
        return _campaign_read_error(str(exc) or "campaign_steps_unavailable", status_code=503)
    return JSONResponse(payload, headers=_CAMPAIGN_READ_HEADERS)


@router.get(
    "/admin/cloud-orchestrator/plans/{plan_id}",
    response_class=HTMLResponse,
    name="api.admin_cloud_orchestrator_plan_detail",
)
def admin_cloud_plan_detail(request: Request, plan_id: str):
    context = shell_context(
        request=request,
        page_title="AI 助手 · 计划二级明细",
        page_summary="目标人员列表与单人话术任务审批。",
        active_endpoint="api.admin_cloud_orchestrator_workspace",
    )
    context.update(
        {
            "breadcrumbs": [
                {"label": "客户管理后台", "href": request.url_for("api.admin_console_dashboard")},
                {"label": "AI 助手", "href": request.url_for("api.admin_cloud_orchestrator_workspace")},
                {"label": "运营计划审阅", "href": "/admin/cloud-orchestrator/plans"},
                {"label": "计划二级明细"},
            ],
            "page_mode": "detail",
            "plan_id": plan_id,
            "admin_action_token": ensure_admin_action_token(),
        }
    )
    return templates.TemplateResponse(request, "admin_console/cloud_plan_review.html", context)


@router.get("/api/admin/cloud-orchestrator/plans")
def api_list_cloud_plans(status: str = "", keyword: str = "", limit: int = 20, offset: int = 0) -> dict[str, Any]:
    try:
        return ListCloudPlansQuery()(status=status, keyword=keyword, limit=limit, offset=offset)
    except Exception as exc:
        _raise(exc)


@router.get("/api/admin/cloud-orchestrator/plans/{plan_id}")
def api_get_cloud_plan(plan_id: str) -> dict[str, Any]:
    try:
        return GetCloudPlanQuery()(plan_id)
    except Exception as exc:
        _raise(exc)


@router.get("/api/admin/cloud-orchestrator/plans/{plan_id}/recipients")
def api_list_cloud_plan_recipients(plan_id: str, status: str = "", limit: int = 50, offset: int = 0) -> dict[str, Any]:
    try:
        return ListCloudPlanRecipientsQuery()(plan_id, status=status, limit=limit, offset=offset)
    except Exception as exc:
        _raise(exc)


@router.get("/api/admin/cloud-orchestrator/plans/{plan_id}/recipients/{recipient_id}")
def api_get_cloud_plan_recipient(plan_id: str, recipient_id: int) -> dict[str, Any]:
    try:
        return GetCloudPlanRecipientQuery()(plan_id, recipient_id)
    except Exception as exc:
        _raise(exc)


@router.post("/api/admin/cloud-orchestrator/plans/{plan_id}/approve")
async def api_approve_cloud_plan(plan_id: str, request: Request):
    payload, token_error = await _write_context(request)
    if token_error:
        return JSONResponse({"ok": False, "error": token_error}, status_code=401)
    try:
        return ApproveCloudPlanCommand()(plan_id, operator=_operator_from_request(request, payload))
    except Exception as exc:
        _raise(exc)


@router.post("/api/admin/cloud-orchestrator/plans/{plan_id}/reject")
async def api_reject_cloud_plan(plan_id: str, request: Request):
    payload, token_error = await _write_context(request)
    if token_error:
        return JSONResponse({"ok": False, "error": token_error}, status_code=401)
    try:
        return RejectCloudPlanCommand()(
            plan_id,
            operator=_operator_from_request(request, payload),
            reason=str(payload.get("reason") or ""),
        )
    except Exception as exc:
        _raise(exc)


@router.post("/api/admin/cloud-orchestrator/plans/{plan_id}/recipients/{recipient_id}/approve")
async def api_approve_cloud_plan_recipient(plan_id: str, recipient_id: int, request: Request):
    payload, token_error = await _write_context(request)
    if token_error:
        return JSONResponse({"ok": False, "error": token_error}, status_code=401)
    try:
        return ApproveCloudPlanRecipientCommand()(
            plan_id,
            recipient_id,
            operator=_operator_from_request(request, payload),
        )
    except Exception as exc:
        _raise(exc)


@router.post("/api/admin/cloud-orchestrator/plans/{plan_id}/recipients/{recipient_id}/reject")
async def api_reject_cloud_plan_recipient(plan_id: str, recipient_id: int, request: Request):
    payload, token_error = await _write_context(request)
    if token_error:
        return JSONResponse({"ok": False, "error": token_error}, status_code=401)
    try:
        return RejectCloudPlanRecipientCommand()(
            plan_id,
            recipient_id,
            operator=_operator_from_request(request, payload),
            reason=str(payload.get("reason") or ""),
        )
    except Exception as exc:
        _raise(exc)


@router.patch("/api/admin/cloud-orchestrator/plans/{plan_id}/recipients/{recipient_id}/messages/{message_id}")
async def api_update_cloud_plan_recipient_message(plan_id: str, recipient_id: int, message_id: int, request: Request):
    payload, token_error = await _write_context(request)
    if token_error:
        return JSONResponse({"ok": False, "error": token_error}, status_code=401)
    try:
        return UpdateCloudPlanRecipientMessageCommand()(
            plan_id,
            recipient_id,
            message_id,
            payload=payload,
            operator=_operator_from_request(request, payload),
        )
    except Exception as exc:
        _raise(exc)
