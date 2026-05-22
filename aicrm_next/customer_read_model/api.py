from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from aicrm_next.integration_gateway.legacy_customer_read_facade import (
    get_customer_via_legacy,
    get_timeline_via_legacy,
    list_customers_via_legacy,
    recent_messages_via_legacy,
)
from aicrm_next.shared.errors import NotFoundError
from aicrm_next.shared.runtime import legacy_production_facade_enabled, production_data_ready

from .application import (
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


def _profile_payload(customer: dict, *, source_status: str, resolved_by: str = "external_userid") -> dict:
    external_userid = str(customer.get("external_userid") or customer.get("user_id") or "")
    profile = {
        **customer,
        "external_userid": external_userid,
        "user_id": customer.get("user_id") or external_userid,
        "tags": list(customer.get("tags") or []),
        "binding": dict(customer.get("binding") or {}),
        "identity": dict(customer.get("identity") or {}),
        "marketing_profile": dict(customer.get("marketing_profile") or {}),
        "sidebar_context": dict(customer.get("sidebar_context") or {}),
    }
    return {
        "ok": True,
        "profile": profile,
        "customer": profile,
        "lookup": {"resolved_by": resolved_by, "external_userid": external_userid},
        "source_status": source_status,
        "route_owner": "ai_crm_next",
    }


def _profile_tags_payload(customer: dict, *, source_status: str) -> dict:
    tags = list(customer.get("tags") or [])
    return {
        "ok": True,
        "tags": tags,
        "count": len(tags),
        "external_userid": str(customer.get("external_userid") or ""),
        "source_status": source_status,
        "route_owner": "ai_crm_next",
    }


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


def _context_for_lookup(
    *,
    external_userid: str | None = None,
    mobile: str | None = None,
    user_id: str | None = None,
    recent_message_limit: int = 20,
    timeline_limit: int = 20,
) -> dict:
    return GetCustomerContextQuery()(
        CustomerContextRequest(
            external_userid=external_userid or None,
            mobile=mobile or None,
            user_id=user_id or None,
            recent_message_limit=recent_message_limit,
            timeline_limit=timeline_limit,
        )
    )


def _profile_payload_from_context(context: dict, *, resolved_by: str = "external_userid") -> dict:
    profile = dict(context.get("customer") or context.get("profile") or {})
    payload = _profile_payload(profile, source_status=str(context.get("source_status") or ""), resolved_by=resolved_by)
    payload["context"] = context
    payload["identity_binding_summary"] = dict(context.get("identity_binding_summary") or {})
    payload["degraded"] = bool(context.get("degraded"))
    payload["page_error"] = context.get("page_error") or ""
    return payload


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
    if _use_production_customer_facade():
        try:
            return list_customers_via_legacy(query)
        except Exception as exc:
            _service_unavailable(exc)
    return ListCustomersQuery()(query)


@router.get("/api/customers/{external_userid}")
def get_customer(external_userid: str) -> dict:
    try:
        if _use_production_customer_facade():
            customer = get_customer_via_legacy(CustomerDetailRequest(external_userid=external_userid))
            if not customer:
                raise NotFoundError("customer not found")
            return {"ok": True, "customer": customer, "source_status": "legacy_production_facade"}
        return GetCustomerDetailQuery()(CustomerDetailRequest(external_userid=external_userid))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        _service_unavailable(exc)


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
        if _use_production_customer_facade():
            timeline = get_timeline_via_legacy(query)
            if not timeline:
                raise NotFoundError("customer timeline not found")
            return {"ok": True, "timeline": timeline, "source_status": "legacy_production_facade"}
        return GetCustomerTimelineQuery()(
            query
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        _service_unavailable(exc)


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
    resolved_external_userid = _resolve_external_userid(external_userid, user_id)
    if not resolved_external_userid and not mobile:
        return _input_error("external_userid is required")
    try:
        if resolved_external_userid:
            context = _context_for_lookup(external_userid=resolved_external_userid)
        else:
            context = _context_for_lookup(mobile=str(mobile or ""))
        if not context.get("ok"):
            return JSONResponse(context, status_code=503 if context.get("degraded") else 400)
        customer = dict(context.get("customer") or {})
        if not customer:
            return _input_error("customer not found")
        if mobile and not resolved_external_userid:
            resolved_by = "mobile"
        else:
            resolved_by = "user_id_fallback_external_userid" if user_id and not external_userid else "external_userid"
        return _profile_payload_from_context(context, resolved_by=resolved_by)
    except NotFoundError:
        return _input_error("customer not found")
    except Exception as exc:
        return _production_unavailable(exc)


@router.get("/api/admin/customers/profile/tags")
def get_admin_customer_profile_tags(external_userid: str | None = None, user_id: str | None = None):
    resolved_external_userid = _resolve_external_userid(external_userid, user_id)
    if not resolved_external_userid:
        return _input_error("external_userid is required")
    try:
        context = _context_for_external_userid(resolved_external_userid)
        if not context.get("ok"):
            return JSONResponse(context, status_code=503 if context.get("degraded") else 400)
        customer = dict(context.get("customer") or {})
        if not customer:
            return _input_error("customer not found")
        return _profile_tags_payload(customer, source_status=str(context.get("source_status") or ""))
    except NotFoundError:
        return _input_error("customer not found")
    except Exception as exc:
        return _production_unavailable(exc)
