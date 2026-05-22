from __future__ import annotations

from aicrm_next.shared.errors import NotFoundError
from aicrm_next.shared.typing import JsonDict
from aicrm_next.integration_gateway.customer_sync_adapters import (
    build_archive_sync_adapter,
    build_contacts_sync_adapter,
    build_customer_projection_sync_gateway,
    customer_sync_side_effect_safety,
)

from .dto import CustomerContextRequest, CustomerDetailRequest, CustomerTimelineRequest, ListCustomersRequest, RecentMessagesRequest
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
    def __init__(self, repo: CustomerReadRepository | None = None, contacts_adapter=None, projection_gateway=None) -> None:
        self._repo = repo or build_customer_read_model_repository()
        self._contacts_adapter = contacts_adapter or build_contacts_sync_adapter()
        self._projection_gateway = projection_gateway or build_customer_projection_sync_gateway()

    def execute(self, query: ListCustomersRequest) -> JsonDict:
        contacts_contract = self._contacts_adapter.fetch_external_contacts(
            follow_user_userid=query.owner_userid or "",
            limit=query.limit,
            sync_cursor=f"offset:{query.offset}",
        )
        projection_contract = self._projection_gateway.update_customer_list_projection(
            projection_name="customer_list",
            sync_cursor=f"offset:{query.offset}:limit:{query.limit}",
        )
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
            "adapter_contract": {
                "contacts_sync": contacts_contract,
                "customer_projection": projection_contract,
            },
            "side_effect_safety": customer_sync_side_effect_safety(),
        }

    __call__ = execute


class GetCustomerDetailQuery:
    def __init__(self, repo: CustomerReadRepository | None = None, contacts_adapter=None, projection_gateway=None) -> None:
        self._repo = repo or build_customer_read_model_repository()
        self._contacts_adapter = contacts_adapter or build_contacts_sync_adapter()
        self._projection_gateway = projection_gateway or build_customer_projection_sync_gateway()

    def execute(self, query: CustomerDetailRequest) -> JsonDict:
        contacts_contract = self._contacts_adapter.fetch_contact_detail(external_userid=query.external_userid)
        projection_contract = self._projection_gateway.update_customer_detail_projection(external_userid=query.external_userid)
        customer = self._repo.get_customer(query.external_userid)
        if not customer:
            raise NotFoundError("customer not found")
        return {
            "ok": True,
            "customer": detail_projection(customer),
            "adapter_contract": {
                "contacts_sync": contacts_contract,
                "customer_projection": projection_contract,
            },
            "side_effect_safety": customer_sync_side_effect_safety(),
        }

    __call__ = execute


class GetCustomerTimelineQuery:
    def __init__(self, repo: CustomerReadRepository | None = None, projection_gateway=None) -> None:
        self._repo = repo or build_customer_read_model_repository()
        self._projection_gateway = projection_gateway or build_customer_projection_sync_gateway()

    def execute(self, query: CustomerTimelineRequest) -> JsonDict:
        projection_contract = self._projection_gateway.update_customer_timeline_projection(
            external_userid=query.external_userid,
            sync_cursor=f"offset:{query.offset}:limit:{query.limit}",
        )
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
            "adapter_contract": {"customer_projection": projection_contract},
            "side_effect_safety": customer_sync_side_effect_safety(),
        }

    __call__ = execute


class ListRecentMessagesQuery:
    def __init__(self, repo: CustomerReadRepository | None = None, archive_adapter=None, projection_gateway=None) -> None:
        self._repo = repo or build_customer_read_model_repository()
        self._archive_adapter = archive_adapter or build_archive_sync_adapter()
        self._projection_gateway = projection_gateway or build_customer_projection_sync_gateway()

    def execute(self, query: RecentMessagesRequest) -> JsonDict:
        archive_contract = self._archive_adapter.fetch_recent_messages(
            external_userid=query.external_userid,
            limit=query.limit,
        )
        projection_contract = self._projection_gateway.update_recent_messages_projection(
            external_userid=query.external_userid,
            sync_cursor=f"limit:{query.limit}",
        )
        customer = self._repo.get_customer(query.external_userid)
        if not customer:
            raise NotFoundError("customer not found")
        return {
            "ok": True,
            "messages": self._repo.list_recent_messages(query.external_userid)[: query.limit],
            "adapter_contract": {
                "archive_sync": archive_contract,
                "customer_projection": projection_contract,
            },
            "side_effect_safety": customer_sync_side_effect_safety(),
        }

    __call__ = execute


def _identity_binding_summary(customer: JsonDict) -> JsonDict:
    binding = dict(customer.get("binding") or {})
    identity = dict(customer.get("identity") or {})
    mobile = binding.get("mobile") or identity.get("mobile") or customer.get("mobile")
    is_bound = bool(binding.get("is_bound") or mobile)
    return {
        "is_bound": is_bound,
        "binding_status": binding.get("binding_status") or ("bound" if is_bound else "unbound"),
        "person_id": identity.get("person_id") or binding.get("person_id") or customer.get("person_id"),
        "external_userid": customer.get("external_userid") or identity.get("external_userid"),
        "mobile": mobile,
        "third_party_user_id": binding.get("third_party_user_id") or identity.get("third_party_user_id"),
        "owner_userid": customer.get("owner_userid") or binding.get("owner_userid"),
    }


def _customer_context_payload(
    *,
    external_userid: str,
    customer: JsonDict,
    timeline: JsonDict,
    recent_messages: list[JsonDict],
    source_status: str,
    adapter_contract: JsonDict | None = None,
    warnings: list[str] | None = None,
) -> JsonDict:
    return {
        "ok": True,
        "external_userid": external_userid,
        "customer": customer,
        "profile": customer,
        "identity_binding_summary": _identity_binding_summary(customer),
        "binding": dict(customer.get("binding") or {}),
        "identity": dict(customer.get("identity") or {}),
        "recent_messages": recent_messages,
        "recent_timeline_events": list(timeline.get("items") or []),
        "timeline": timeline,
        "source_status": source_status,
        "degraded": False,
        "page_error": "",
        "warnings": warnings or [],
        "adapter_contract": adapter_contract or {},
        "side_effect_safety": customer_sync_side_effect_safety(),
    }


def _production_unavailable_payload(external_userid: str, exc: Exception) -> JsonDict:
    return {
        "ok": False,
        "external_userid": external_userid,
        "customer": {},
        "profile": {},
        "identity_binding_summary": {},
        "binding": {},
        "identity": {},
        "recent_messages": [],
        "recent_timeline_events": [],
        "timeline": {"external_userid": external_userid, "items": [], "count": 0, "total": 0},
        "source_status": "production_unavailable",
        "degraded": True,
        "page_error": str(exc),
        "error_code": "customer_context_read_unavailable",
        "warnings": ["customer_context_read_failed"],
        "adapter_contract": {},
        "side_effect_safety": customer_sync_side_effect_safety(),
    }


class GetCustomerContextQuery:
    def __init__(self, repo: CustomerReadRepository | None = None) -> None:
        self._repo = repo

    def _resolve_fixture_external_userid(self, query: CustomerContextRequest) -> str:
        external_userid = str(query.external_userid or query.user_id or "").strip()
        if external_userid:
            return external_userid
        mobile = str(query.mobile or "").strip()
        if not mobile:
            raise NotFoundError("external_userid is required")
        repo = self._repo or build_customer_read_model_repository()
        matches = repo.list_customers({"mobile": mobile}, limit=1, offset=0)
        if not matches or not str(matches[0].get("external_userid") or "").strip():
            raise NotFoundError("customer not found")
        return str(matches[0]["external_userid"])

    def _resolve_production_external_userid(self, query: CustomerContextRequest) -> str:
        external_userid = str(query.external_userid or query.user_id or "").strip()
        if external_userid:
            return external_userid
        mobile = str(query.mobile or "").strip()
        if not mobile:
            raise NotFoundError("external_userid is required")
        from aicrm_next.integration_gateway.legacy_customer_read_facade import list_customers_via_legacy

        payload = list_customers_via_legacy(ListCustomersRequest(mobile=mobile, limit=1, offset=0))
        rows = list(payload.get("customers") or payload.get("items") or [])
        if not rows or not str(rows[0].get("external_userid") or "").strip():
            raise NotFoundError("customer not found")
        return str(rows[0]["external_userid"])

    def execute(self, query: CustomerContextRequest) -> JsonDict:
        from aicrm_next.shared.runtime import legacy_production_facade_enabled, production_data_ready

        if production_data_ready():
            if not legacy_production_facade_enabled():
                fallback_external_userid = str(query.external_userid or query.user_id or "")
                return _production_unavailable_payload(fallback_external_userid, RuntimeError("production customer facade disabled"))
            try:
                from aicrm_next.integration_gateway.legacy_customer_read_facade import (
                    get_customer_via_legacy,
                    get_timeline_via_legacy,
                    recent_messages_via_legacy,
                )

                external_userid = self._resolve_production_external_userid(query)
                customer = get_customer_via_legacy(CustomerDetailRequest(external_userid=external_userid))
                if not customer:
                    raise NotFoundError("customer not found")
                timeline_payload = get_timeline_via_legacy(
                    CustomerTimelineRequest(external_userid=external_userid, limit=query.timeline_limit)
                )
                timeline = dict(timeline_payload or {})
                if "items" not in timeline:
                    timeline = {
                        "external_userid": external_userid,
                        "items": list(timeline_payload.get("items") or []) if isinstance(timeline_payload, dict) else [],
                        "count": int(timeline_payload.get("count") or 0) if isinstance(timeline_payload, dict) else 0,
                        "limit": query.timeline_limit,
                        "offset": 0,
                        "total": int(timeline_payload.get("total") or 0) if isinstance(timeline_payload, dict) else 0,
                    }
                messages_payload = recent_messages_via_legacy(
                    RecentMessagesRequest(external_userid=external_userid, limit=query.recent_message_limit)
                )
                recent_messages = list(messages_payload.get("messages") or messages_payload.get("items") or [])
                return _customer_context_payload(
                    external_userid=external_userid,
                    customer=detail_projection(customer),
                    timeline=timeline,
                    recent_messages=recent_messages,
                    source_status="legacy_production_facade",
                    adapter_contract={
                        "detail": {"source_status": "legacy_production_facade"},
                        "timeline": {"source_status": "legacy_production_facade"},
                        "recent_messages": {"source_status": "legacy_production_facade"},
                    },
                )
            except NotFoundError:
                raise
            except Exception as exc:
                fallback_external_userid = str(query.external_userid or query.user_id or "")
                return _production_unavailable_payload(fallback_external_userid, exc)

        external_userid = self._resolve_fixture_external_userid(query)
        repo = self._repo or build_customer_read_model_repository()
        detail = GetCustomerDetailQuery(repo)(CustomerDetailRequest(external_userid=external_userid))
        timeline = GetCustomerTimelineQuery(repo)(
            CustomerTimelineRequest(external_userid=external_userid, limit=query.timeline_limit)
        )
        messages = ListRecentMessagesQuery(repo)(
            RecentMessagesRequest(external_userid=external_userid, limit=query.recent_message_limit)
        )
        return _customer_context_payload(
            external_userid=external_userid,
            customer=detail["customer"],
            timeline=timeline["timeline"],
            recent_messages=messages["messages"],
            source_status="local_contract_probe",
            adapter_contract={
                "detail": detail.get("adapter_contract", {}),
                "timeline": timeline.get("adapter_contract", {}),
                "recent_messages": messages.get("adapter_contract", {}),
            },
        )

    __call__ = execute


GetCustomerChatContextQuery = GetCustomerContextQuery
