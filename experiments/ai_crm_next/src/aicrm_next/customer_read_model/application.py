from __future__ import annotations

from aicrm_next.shared.errors import NotFoundError
from aicrm_next.shared.typing import JsonDict

from .dto import (
    CustomerChatContextRequest,
    CustomerDetailRequest,
    CustomerTimelineRequest,
    ListCustomersRequest,
    RecentMessagesRequest,
)
from .projections import detail_projection, list_item_projection
from .repo import CustomerReadRepository, build_customer_read_model_repository


def _normalize_bool_filter(value: str | None) -> bool | None:
    normalized = str(value or "").strip().lower()
    if normalized in {"", "all"}:
        return None
    if normalized in {"1", "true", "yes", "y", "on", "bound"}:
        return True
    if normalized in {"0", "false", "no", "n", "off", "unbound"}:
        return False
    return None


class ListCustomersQuery:
    def __init__(self, repo: CustomerReadRepository | None = None) -> None:
        self._repo = repo or build_customer_read_model_repository()

    def execute(self, query: ListCustomersRequest) -> JsonDict:
        filters = {
            "owner_userid": query.owner_userid or "",
            "tag": query.tag or "",
            "status": query.status or "",
            "is_bound": query.is_bound or "",
            "mobile": query.mobile or "",
            "keyword": query.keyword or "",
            "limit": str(query.limit),
            "offset": str(query.offset),
        }
        rows = [list_item_projection(item) for item in self._repo.list_customers()]
        if query.owner_userid:
            rows = [item for item in rows if item.get("owner_userid") == query.owner_userid]
        if query.mobile:
            rows = [item for item in rows if query.mobile in str(item.get("mobile") or "")]
        if query.tag:
            rows = [item for item in rows if query.tag in item.get("tags", [])]
        if query.status:
            rows = [
                item
                for item in rows
                if query.status in {
                    str(item.get("class_user_status", {}).get("current_status") or ""),
                    str(item.get("class_user_status", {}).get("signup_status") or ""),
                    str(item.get("class_user_status", {}).get("activation_bucket") or ""),
                    str(item.get("binding_status") or ""),
                }
            ]
        is_bound = _normalize_bool_filter(query.is_bound)
        if is_bound is not None:
            rows = [item for item in rows if bool(item.get("is_bound")) is is_bound]
        if query.keyword:
            rows = [
                item
                for item in rows
                if query.keyword in str(item.get("customer_name") or "")
                or query.keyword in str(item.get("external_userid") or "")
                or query.keyword in str(item.get("mobile") or "")
                or query.keyword in str(item.get("owner_userid") or "")
                or query.keyword in str(item.get("owner_display_name") or "")
            ]
        total = len(rows)
        page = rows[query.offset : query.offset + query.limit]
        return {
            "ok": True,
            "customers": page,
            "items": page,
            "count": len(page),
            "total": total,
            "limit": query.limit,
            "offset": query.offset,
            "filters": filters,
        }

    __call__ = execute


class GetCustomerDetailQuery:
    def __init__(self, repo: CustomerReadRepository | None = None) -> None:
        self._repo = repo or build_customer_read_model_repository()

    def execute(self, query: CustomerDetailRequest) -> JsonDict:
        customer = self._repo.get_customer(query.external_userid)
        if not customer:
            raise NotFoundError("customer not found")
        return {"ok": True, "customer": detail_projection(customer)}

    __call__ = execute


class GetCustomerTimelineQuery:
    def __init__(self, repo: CustomerReadRepository | None = None) -> None:
        self._repo = repo or build_customer_read_model_repository()

    def execute(self, query: CustomerTimelineRequest) -> JsonDict:
        customer = self._repo.get_customer(query.external_userid)
        if not customer:
            raise NotFoundError("customer not found")
        items = self._repo.list_timeline(query.external_userid)
        if query.event_type:
            items = [item for item in items if item.get("event_type") == query.event_type]
        total = len(items)
        page = items[query.offset : query.offset + query.limit]
        return {
            "ok": True,
            "timeline": {
                "external_userid": query.external_userid,
                "items": page,
                "count": len(page),
                "limit": query.limit,
                "offset": query.offset,
                "filters": {"event_type": query.event_type or "", "limit": str(query.limit), "offset": str(query.offset)},
                "total": total,
            },
        }

    __call__ = execute


class ListRecentMessagesQuery:
    def __init__(self, repo: CustomerReadRepository | None = None) -> None:
        self._repo = repo or build_customer_read_model_repository()

    def execute(self, query: RecentMessagesRequest) -> JsonDict:
        customer = self._repo.get_customer(query.external_userid)
        if not customer:
            raise NotFoundError("customer not found")
        return {"ok": True, "messages": self._repo.list_recent_messages(query.external_userid)[: query.limit]}

    __call__ = execute


class GetCustomerChatContextQuery:
    def __init__(self, repo: CustomerReadRepository | None = None) -> None:
        self._repo = repo or build_customer_read_model_repository()

    def execute(self, query: CustomerChatContextRequest) -> JsonDict:
        detail = GetCustomerDetailQuery(self._repo)(CustomerDetailRequest(external_userid=query.external_userid))
        timeline = GetCustomerTimelineQuery(self._repo)(
            CustomerTimelineRequest(external_userid=query.external_userid, limit=query.timeline_limit)
        )
        messages = ListRecentMessagesQuery(self._repo)(
            RecentMessagesRequest(external_userid=query.external_userid, limit=query.recent_message_limit)
        )
        return {
            "external_userid": query.external_userid,
            "customer": detail["customer"],
            "recent_messages": messages["messages"],
            "recent_timeline_events": timeline["timeline"]["items"],
            "timeline": timeline["timeline"],
            "source_status": "fixture",
            "degraded": False,
            "warnings": [],
        }

    __call__ = execute
