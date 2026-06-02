from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from aicrm_next.integration_gateway.legacy_automation_facade import get_automation_member_detail_from_legacy
from aicrm_next.integration_gateway.legacy_flask_facade import forward_to_legacy_flask

router = APIRouter()
wildcard_router = APIRouter()

_ALL_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]


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


@router.api_route("/api/admin/cloud-orchestrator/campaigns", methods=_ALL_METHODS)
@router.api_route("/api/admin/cloud-orchestrator/campaigns/{path:path}", methods=_ALL_METHODS)
async def legacy_cloud_orchestrator_campaign_routes(request: Request) -> Response:
    return await forward_to_legacy_flask(request)


@router.api_route("/api/admin/cloud-orchestrator/media/upload", methods=["POST", "OPTIONS"])
async def legacy_cloud_orchestrator_media_upload_route(request: Request) -> Response:
    return await forward_to_legacy_flask(request)


@router.api_route("/admin/hxc-dashboard", methods=_ALL_METHODS)
@router.api_route("/admin/hxc-send-config", methods=_ALL_METHODS)
@router.api_route("/api/admin/hxc-dashboard", methods=_ALL_METHODS)
@router.api_route("/api/admin/hxc-dashboard/{path:path}", methods=_ALL_METHODS)
async def legacy_hxc_dashboard_routes(request: Request) -> Response:
    return await forward_to_legacy_flask(request)


@router.api_route("/api/h5/wechat/oauth/start", methods=["GET", "OPTIONS", "HEAD"])
@router.api_route("/api/h5/wechat/oauth/callback", methods=["GET", "OPTIONS", "HEAD"])
async def legacy_questionnaire_oauth_routes(request: Request) -> Response:
    return await forward_to_legacy_flask(request)


@router.api_route("/api/h5/questionnaires/{slug}/submit", methods=["POST", "OPTIONS"])
@router.api_route("/api/h5/questionnaires/{slug}/client-diagnostics", methods=["POST", "OPTIONS"])
async def legacy_questionnaire_public_write_routes(request: Request) -> Response:
    return await forward_to_legacy_flask(request)


@router.api_route("/api/admin/wecom/tags", methods=_ALL_METHODS)
@router.api_route("/api/admin/wecom/tags/{path:path}", methods=_ALL_METHODS)
@router.api_route("/api/admin/wecom/tag-groups", methods=_ALL_METHODS)
@router.api_route("/api/admin/wecom/tag-groups/{path:path}", methods=_ALL_METHODS)
async def legacy_admin_wecom_tag_routes(request: Request) -> Response:
    return await forward_to_legacy_flask(request)


@router.api_route("/api/admin/automation-conversion/tasks/run-due", methods=["POST", "OPTIONS"])
@router.api_route("/api/admin/automation-conversion/execution-items/{execution_item_id:int}/send-via-bazhuayu", methods=["POST", "OPTIONS"])
async def legacy_automation_workspace_routes(request: Request) -> Response:
    return await forward_to_legacy_flask(request)


@router.api_route("/login", methods=_ALL_METHODS)
@router.api_route("/logout", methods=_ALL_METHODS)
async def legacy_admin_auth_routes(request: Request) -> Response:
    return await forward_to_legacy_flask(request)


@router.api_route("/admin/wechat-pay/products", methods=_ALL_METHODS)
@router.api_route("/admin/wechat-pay/products/{path:path}", methods=_ALL_METHODS)
@router.api_route("/api/admin/wechat-pay/products", methods=_ALL_METHODS)
@router.api_route("/api/admin/wechat-pay/products/{path:path}", methods=_ALL_METHODS)
async def legacy_wechat_pay_product_admin_routes(request: Request) -> Response:
    return await forward_to_legacy_flask(request)


@router.api_route("/p/{path:path}", methods=_ALL_METHODS)
@router.api_route("/pay/{path:path}", methods=_ALL_METHODS)
@router.api_route("/api/products/{path:path}", methods=_ALL_METHODS)
async def legacy_public_product_routes(request: Request) -> Response:
    return await forward_to_legacy_flask(request)


@router.api_route("/api/sidebar/bind-mobile", methods=["POST", "OPTIONS"])
@router.api_route("/api/sidebar/jssdk-config", methods=["GET", "HEAD", "OPTIONS"])
@router.api_route("/api/sidebar/lead-pool/upsert-class-term", methods=["POST", "OPTIONS"])
@router.api_route("/api/sidebar/signup-tags/mark", methods=["POST", "OPTIONS"])
@router.api_route("/api/sidebar/marketing-status/set-followup-segment", methods=["POST", "OPTIONS"])
@router.api_route("/api/sidebar/marketing-status/mark-enrolled", methods=["POST", "OPTIONS"])
@router.api_route("/api/sidebar/marketing-status/unmark-enrolled", methods=["POST", "OPTIONS"])
async def legacy_sidebar_compat_routes(request: Request) -> Response:
    return await forward_to_legacy_flask(request)


@router.api_route("/api/sidebar/v2/profile", methods=["PUT", "OPTIONS"])
@router.api_route("/api/sidebar/v2/materials/send", methods=["POST", "OPTIONS"])
async def legacy_sidebar_v2_compat_routes(request: Request) -> Response:
    return await forward_to_legacy_flask(request)


@router.api_route("/api/customers/automation/activation-webhook", methods=["POST", "OPTIONS"])
@router.api_route("/api/customers/automation/webhook-deliveries/{delivery_id:int}/retry", methods=["POST", "OPTIONS"])
@router.api_route("/api/customers/automation/webhook-deliveries/retry-due", methods=["POST", "OPTIONS"])
async def legacy_customer_automation_compat_routes(request: Request) -> Response:
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
@wildcard_router.api_route("/pay/{path:path}", methods=_ALL_METHODS)
@wildcard_router.api_route("/api/orders/{path:path}", methods=_ALL_METHODS)
@wildcard_router.api_route("/api/checkout/{path:path}", methods=_ALL_METHODS)
@wildcard_router.api_route("/api/wechat-pay/{path:path}", methods=_ALL_METHODS)
@wildcard_router.api_route("/api/alipay/{path:path}", methods=_ALL_METHODS)
@wildcard_router.api_route("/api/admin/hxc-dashboard", methods=_ALL_METHODS)
@wildcard_router.api_route("/api/admin/hxc-dashboard/{path:path}", methods=_ALL_METHODS)
@wildcard_router.api_route("/api/admin/automation-conversion/member/{path:path}", methods=_ALL_METHODS)
async def legacy_production_compat_routes(request: Request) -> Response:
    return await forward_to_legacy_flask(request)
