from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from aicrm_next.admin_jobs.routes import _action_token_error, _operator_from_request, _request_payload

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
)

router = APIRouter()


def _raise(exc: Exception) -> None:
    if isinstance(exc, CloudPlanNotFoundError) or isinstance(exc, LookupError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail=str(exc)) from exc


async def _write_context(request: Request) -> tuple[dict[str, Any], str | None]:
    payload = await _request_payload(request)
    token_error = await _action_token_error(request, payload)
    if token_error:
        return payload, token_error
    return payload, None


@router.get("/admin/cloud-orchestrator/plans", response_class=HTMLResponse)
def admin_cloud_plans() -> str:
    return "<!doctype html><html><head><title>AI 助手计划</title></head><body><main id=\"cloud-plans-root\" data-api=\"/api/admin/cloud-orchestrator/plans\"></main></body></html>"


@router.get("/admin/cloud-orchestrator/plans/{plan_id}", response_class=HTMLResponse)
def admin_cloud_plan_detail(plan_id: str) -> str:
    return f"<!doctype html><html><head><title>AI 助手计划</title></head><body><main id=\"cloud-plan-detail-root\" data-plan-id=\"{plan_id}\" data-api=\"/api/admin/cloud-orchestrator/plans/{plan_id}\"></main></body></html>"


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
        return RejectCloudPlanCommand()(plan_id, operator=_operator_from_request(request, payload), reason=str(payload.get("reason") or ""))
    except Exception as exc:
        _raise(exc)


@router.post("/api/admin/cloud-orchestrator/plans/{plan_id}/recipients/{recipient_id}/approve")
async def api_approve_cloud_plan_recipient(plan_id: str, recipient_id: int, request: Request):
    payload, token_error = await _write_context(request)
    if token_error:
        return JSONResponse({"ok": False, "error": token_error}, status_code=401)
    try:
        return ApproveCloudPlanRecipientCommand()(plan_id, recipient_id, operator=_operator_from_request(request, payload))
    except Exception as exc:
        _raise(exc)


@router.post("/api/admin/cloud-orchestrator/plans/{plan_id}/recipients/{recipient_id}/reject")
async def api_reject_cloud_plan_recipient(plan_id: str, recipient_id: int, request: Request):
    payload, token_error = await _write_context(request)
    if token_error:
        return JSONResponse({"ok": False, "error": token_error}, status_code=401)
    try:
        return RejectCloudPlanRecipientCommand()(plan_id, recipient_id, operator=_operator_from_request(request, payload), reason=str(payload.get("reason") or ""))
    except Exception as exc:
        _raise(exc)

