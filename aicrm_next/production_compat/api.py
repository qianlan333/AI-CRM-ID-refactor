from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from aicrm_next.integration_gateway.legacy_automation_facade import get_automation_member_detail_from_legacy
from aicrm_next.integration_gateway.legacy_flask_facade import forward_to_legacy_flask
from aicrm_next.integration_gateway.wecom_callback_facade import handle_wecom_callback_via_legacy

router = APIRouter()
wildcard_router = APIRouter()

_ALL_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]


@router.api_route("/wecom/external-contact/callback", methods=["GET", "POST", "OPTIONS", "HEAD"])
@router.api_route("/api/wecom/events", methods=["GET", "POST", "OPTIONS", "HEAD"])
async def wecom_callback_routes(request: Request) -> Response:
    return await handle_wecom_callback_via_legacy(request)


@router.api_route("/api/admin/automation-conversion/member", methods=["GET", "HEAD"])
async def automation_member_detail_route(request: Request) -> Response:
    external_contact_id = str(request.query_params.get("external_contact_id") or "").strip()
    phone = str(request.query_params.get("phone") or "").strip()
    payload = get_automation_member_detail_from_legacy(external_contact_id=external_contact_id, phone=phone)
    status_code = 200 if payload.get("ok") else 400
    return JSONResponse(
        payload,
        status_code=status_code,
        headers={
            "X-AICRM-Route-Owner": "ai_crm_next",
            "X-AICRM-Compatibility-Facade": "legacy_automation_facade",
        },
    )


@router.api_route("/api/admin/automation-conversion/reply-monitor/run-due", methods=["POST", "OPTIONS"])
@router.api_route("/api/admin/automation-conversion/reply-monitor/capture", methods=["POST", "OPTIONS"])
@router.api_route("/api/admin/automation-conversion/jobs/run-due", methods=["POST", "OPTIONS"])
@router.api_route("/api/admin/automation-conversion/jobs/run-due/preview", methods=["POST", "OPTIONS"])
@router.api_route("/api/admin/cloud-orchestrator/campaigns/run-due", methods=["POST", "OPTIONS"])
@router.api_route("/api/admin/cloud-orchestrator/campaigns/run-due/preview", methods=["POST", "OPTIONS"])
async def legacy_production_compat_timer_routes(request: Request) -> Response:
    return await forward_to_legacy_flask(request)


@router.api_route("/login", methods=_ALL_METHODS)
@router.api_route("/logout", methods=_ALL_METHODS)
async def legacy_admin_auth_routes(request: Request) -> Response:
    return await forward_to_legacy_flask(request)


@wildcard_router.api_route("/api/messages/{path:path}", methods=_ALL_METHODS)
@wildcard_router.api_route("/api/h5/wechat/oauth/{path:path}", methods=_ALL_METHODS)
@wildcard_router.api_route("/auth/wecom/{path:path}", methods=_ALL_METHODS)
@wildcard_router.api_route("/api/admin/wechat-pay/{path:path}", methods=_ALL_METHODS)
@wildcard_router.api_route("/api/admin/alipay/{path:path}", methods=_ALL_METHODS)
@wildcard_router.api_route("/api/h5/wechat-pay/{path:path}", methods=_ALL_METHODS)
@wildcard_router.api_route("/api/h5/alipay/{path:path}", methods=_ALL_METHODS)
@wildcard_router.api_route("/api/products/{path:path}", methods=_ALL_METHODS)
@wildcard_router.api_route("/p/{path:path}", methods=_ALL_METHODS)
@wildcard_router.api_route("/api/orders/{path:path}", methods=_ALL_METHODS)
@wildcard_router.api_route("/api/checkout/{path:path}", methods=_ALL_METHODS)
@wildcard_router.api_route("/api/wechat-pay/{path:path}", methods=_ALL_METHODS)
@wildcard_router.api_route("/api/alipay/{path:path}", methods=_ALL_METHODS)
@wildcard_router.api_route("/api/admin/image-library", methods=_ALL_METHODS)
@wildcard_router.api_route("/api/admin/image-library/{path:path}", methods=_ALL_METHODS)
@wildcard_router.api_route("/api/admin/attachment-library", methods=_ALL_METHODS)
@wildcard_router.api_route("/api/admin/attachment-library/{path:path}", methods=_ALL_METHODS)
@wildcard_router.api_route("/api/admin/miniprogram-library", methods=_ALL_METHODS)
@wildcard_router.api_route("/api/admin/miniprogram-library/{path:path}", methods=_ALL_METHODS)
@wildcard_router.api_route("/admin/automation-conversion/{path:path}", methods=_ALL_METHODS)
@wildcard_router.api_route("/sidebar/{path:path}", methods=_ALL_METHODS)
@wildcard_router.api_route("/api/sidebar/{path:path}", methods=_ALL_METHODS)
@wildcard_router.api_route("/api/admin/customers/profile", methods=_ALL_METHODS)
@wildcard_router.api_route("/api/admin/customers/profile/{path:path}", methods=_ALL_METHODS)
@wildcard_router.api_route("/api/admin/automation-conversion/member/{path:path}", methods=_ALL_METHODS)
@wildcard_router.api_route("/api/customers/automation/{path:path}", methods=_ALL_METHODS)
@wildcard_router.api_route("/api/customer-automation/{path:path}", methods=_ALL_METHODS)
async def legacy_production_compat_routes(request: Request) -> Response:
    return await forward_to_legacy_flask(request)
