from __future__ import annotations

from fastapi import APIRouter, HTTPException

from aicrm_next.shared.errors import NotFoundError

from .application import GetCustomerDetailQuery, GetCustomerTimelineQuery, ListCustomersQuery, ListRecentMessagesQuery
from .dto import CustomerDetailRequest, CustomerTimelineRequest, ListCustomersRequest, RecentMessagesRequest

router = APIRouter()


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
    return ListCustomersQuery()(
        ListCustomersRequest(
            owner_userid=owner_userid,
            tag=tag,
            status=status,
            is_bound=is_bound,
            mobile=mobile,
            keyword=keyword,
            limit=limit,
            offset=offset,
        )
    )


@router.get("/api/customers/{external_userid}")
def get_customer(external_userid: str) -> dict:
    try:
        return GetCustomerDetailQuery()(CustomerDetailRequest(external_userid=external_userid))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/api/customers/{external_userid}/timeline")
def get_customer_timeline(
    external_userid: str,
    event_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    try:
        return GetCustomerTimelineQuery()(
            CustomerTimelineRequest(
                external_userid=external_userid,
                event_type=event_type,
                limit=limit,
                offset=offset,
            )
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/api/messages/{external_userid}/recent")
def get_recent_messages(external_userid: str, limit: int = 20) -> dict:
    try:
        return ListRecentMessagesQuery()(RecentMessagesRequest(external_userid=external_userid, limit=limit))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
