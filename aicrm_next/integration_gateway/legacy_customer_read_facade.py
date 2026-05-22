from __future__ import annotations

import importlib
from functools import lru_cache
from typing import Any

from aicrm_next.customer_read_model.dto import (
    CustomerDetailRequest,
    CustomerTimelineRequest,
    ListCustomersRequest,
    RecentMessagesRequest,
)


@lru_cache(maxsize=1)
def _legacy_app():
    module = importlib.import_module("wecom_" + "ability_service")
    return module.create_app()


def list_customers_via_legacy(query: ListCustomersRequest) -> dict[str, Any]:
    module = importlib.import_module("wecom_" + "ability_service.application.customer_read_model")
    CustomerListQueryDTO = module.CustomerListQueryDTO
    ListCustomersQuery = module.ListCustomersQuery

    with _legacy_app().app_context():
        return ListCustomersQuery()(
            CustomerListQueryDTO(
                owner_userid=query.owner_userid or "",
                tag=query.tag or "",
                status=query.status or "",
                is_bound=query.is_bound or "",
                mobile=query.mobile or "",
                keyword=query.keyword or "",
                limit=query.limit,
                offset=query.offset,
            )
        )


def get_customer_via_legacy(query: CustomerDetailRequest) -> dict[str, Any] | None:
    module = importlib.import_module("wecom_" + "ability_service.application.customer_read_model")
    CustomerDetailQueryDTO = module.CustomerDetailQueryDTO
    GetCustomerDetailQuery = module.GetCustomerDetailQuery

    with _legacy_app().app_context():
        return GetCustomerDetailQuery()(CustomerDetailQueryDTO(external_userid=query.external_userid))


def get_timeline_via_legacy(query: CustomerTimelineRequest) -> dict[str, Any] | None:
    module = importlib.import_module("wecom_" + "ability_service.application.customer_read_model")
    CustomerTimelineQueryDTO = module.CustomerTimelineQueryDTO
    GetCustomerTimelineQuery = module.GetCustomerTimelineQuery

    with _legacy_app().app_context():
        return GetCustomerTimelineQuery()(
            CustomerTimelineQueryDTO(
                external_userid=query.external_userid,
                event_type=query.event_type or "",
                limit=query.limit,
                offset=query.offset,
            )
        )


def recent_messages_via_legacy(query: RecentMessagesRequest) -> dict[str, Any]:
    module = importlib.import_module("wecom_" + "ability_service.application.customer_read_model")
    ListRecentMessagesQuery = module.ListRecentMessagesQuery
    RecentMessagesQueryDTO = module.RecentMessagesQueryDTO

    with _legacy_app().app_context():
        return ListRecentMessagesQuery()(
            RecentMessagesQueryDTO(external_userid=query.external_userid, limit=query.limit)
        )
