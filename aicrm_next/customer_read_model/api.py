from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from aicrm_next.integration_gateway.legacy_customer_read_facade import (
    recent_messages_via_legacy,
)
from aicrm_next.shared.errors import NotFoundError
from aicrm_next.shared.runtime import legacy_production_facade_enabled, production_data_ready

from .application import (
    GetAdminCustomerProfileQuery,
    GetAdminCustomerProfileTagsQuery,
    GetCustomerContextQuery,
    GetCustomerDetailQuery,
    GetCustomerTimelineQuery,
    ListCustomersQuery,
    ListRecentMessagesQuery,
)
from .dto import (
    CustomerContextRequest,
    CustomerDetailRequest,
    CustomerTimelineRequest,
    ListCustomersRequest,
    RecentMessagesRequest,
)

router = APIRouter()


def _use_production_customer_facade() -> bool:
    return production_data_ready() and legacy_production_facade_enabled()


def _service_unavailable(exc: Exception) -> None:
    raise HTTPException(
        status_code=503,
        detail={
            "error": "legacy_customer_read_facade_unavailable",
            "message": str(exc),
            "route_owner": "ai_crm_next",
        },
    ) from exc


def _input_error(message: str) -> JSONResponse:
    return JSONResponse(
        {"ok": False, "error": message, "source_status": "input_error", "route_owner": "ai_crm_next"},
        status_code=400,
    )


def _production_unavailable(exc: Exception) -> JSONResponse:
    return JSONResponse(
        {
            "ok": False,
            "degraded": True,
            "source_status": "production_unavailable",
            "error_code": "customer_profile_read_unavailable",
            "page_error": str(exc),
            "route_owner": "ai_crm_next",
        },
        status_code=503,
    )


def _resolve_external_userid(external_userid: str | None = None, user_id: str | None = None) -> str:
    return str(external_userid or user_id or "").strip()


def _context_for_external_userid(
    external_userid: str,
    *,
    recent_message_limit: int = 20,
    timeline_limit: int = 20,
) -> dict:
    return GetCustomerContextQuery()(
        CustomerContextRequest(
            external_userid=external_userid,
            recent_message_limit=recent_message_limit,
            timeline_limit=timeline_limit,
        )
    )


@router.get("/api/customers")
def list_customers(
    owner_userid: str | None = None,
    tag: str | None = None,
    status: str | None = None,
    is_bound: str | None = None,
    mobile: str | None = None,
    keyword: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    query = ListCustomersRequest(
        owner_userid=owner_userid,
        tag=tag,
        status=status,
        is_bound=is_bound,
        mobile=mobile,
        keyword=keyword,
        limit=limit,
        offset=offset,
    )
    result = ListCustomersQuery()(query)
    status_code = int(result.pop("status_code", 200) or 200)
    return JSONResponse(result, status_code=status_code)


@router.get("/api/customers/{external_userid}")
def get_customer(external_userid: str) -> dict:
    try:
        result = GetCustomerDetailQuery()(CustomerDetailRequest(external_userid=external_userid))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    status_code = int(result.pop("status_code", 200) or 200)
    return JSONResponse(result, status_code=status_code)


@router.get("/api/customers/{external_userid}/timeline")
def get_customer_timeline(
    external_userid: str,
    event_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    try:
        query = CustomerTimelineRequest(
            external_userid=external_userid,
            event_type=event_type,
            limit=limit,
            offset=offset,
        )
        result = GetCustomerTimelineQuery()(query)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    status_code = int(result.pop("status_code", 200) or 200)
    return JSONResponse(result, status_code=status_code)


@router.get("/api/messages/{external_userid}/recent")
def get_recent_messages(external_userid: str, limit: int = 20) -> dict:
    try:
        query = RecentMessagesRequest(external_userid=external_userid, limit=limit)
        if _use_production_customer_facade():
            return recent_messages_via_legacy(query)
        return ListRecentMessagesQuery()(query)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        _service_unavailable(exc)


@router.get("/api/sidebar/customer-context")
def get_sidebar_customer_context(external_userid: str | None = None, user_id: str | None = None):
    resolved_external_userid = _resolve_external_userid(external_userid, user_id)
    if not resolved_external_userid:
        return _input_error("external_userid is required")
    try:
        context = _context_for_external_userid(resolved_external_userid)
        if not context.get("ok"):
            return JSONResponse(context, status_code=503 if context.get("degraded") else 400)
        if not context.get("customer"):
            return _input_error("customer not found")
        return {
            "ok": True,
            "context": {
                "external_userid": context["external_userid"],
                "customer": context["customer"],
                "binding": context.get("binding") or {},
                "identity": context.get("identity") or {},
                "identity_binding_summary": context.get("identity_binding_summary") or {},
                "recent_messages": context.get("recent_messages") or [],
                "recent_timeline_events": context.get("recent_timeline_events") or [],
                "timeline": context.get("timeline") or {},
                "sidebar_context": context.get("customer", {}).get("sidebar_context") or {},
            },
            "source_status": context.get("source_status"),
            "degraded": bool(context.get("degraded")),
            "page_error": context.get("page_error") or "",
            "route_owner": "ai_crm_next",
        }
    except NotFoundError:
        return _input_error("customer not found")
    except Exception as exc:
        return _production_unavailable(exc)


@router.get("/api/admin/customers/profile")
def get_admin_customer_profile(
    external_userid: str | None = None,
    mobile: str | None = None,
    user_id: str | None = None,
):
    result = GetAdminCustomerProfileQuery()(
        external_userid=external_userid,
        mobile=mobile,
        user_id=user_id,
    )
    status_code = int(result.pop("status_code", 200) or 200)
    return JSONResponse(result, status_code=status_code)


@router.get("/api/admin/customers/profile/tags")
def get_admin_customer_profile_tags(external_userid: str | None = None, user_id: str | None = None):
    result = GetAdminCustomerProfileTagsQuery()(
        external_userid=external_userid,
        user_id=user_id,
    )
    status_code = int(result.pop("status_code", 200) or 200)
    return JSONResponse(result, status_code=status_code)
