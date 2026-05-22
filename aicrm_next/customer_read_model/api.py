from __future__ import annotations

from fastapi import APIRouter, HTTPException

from aicrm_next.integration_gateway.legacy_customer_read_facade import (
    get_customer_via_legacy,
    get_timeline_via_legacy,
    list_customers_via_legacy,
    recent_messages_via_legacy,
)
from aicrm_next.shared.errors import NotFoundError
from aicrm_next.shared.runtime import legacy_production_facade_enabled, production_data_ready

from .application import GetCustomerDetailQuery, GetCustomerTimelineQuery, ListCustomersQuery, ListRecentMessagesQuery
from .dto import CustomerDetailRequest, CustomerTimelineRequest, ListCustomersRequest, RecentMessagesRequest

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
