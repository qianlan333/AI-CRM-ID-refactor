from __future__ import annotations

import os

from aicrm_next.shared.errors import NotFoundError
from aicrm_next.shared.typing import JsonDict
from aicrm_next.integration_gateway.customer_sync_adapters import (
    build_archive_sync_adapter,
    build_contacts_sync_adapter,
    build_customer_projection_sync_gateway,
    customer_sync_side_effect_safety,
)

from .dto import (
    CustomerContextRequest,
    CustomerDetailRequest,
    CustomerTimelineRequest,
    ListCustomersRequest,
    RecentMessagesRequest,
)
from .projections import detail_projection, list_item_projection
from .repo import CustomerReadRepository, build_customer_read_model_repository


def _env_flag(name: str, *, default: bool = False) -> bool:
    value = str(os.getenv(name, "") or "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


def _customer_read_model_next_primary_enabled() -> bool:
    return _env_flag("CUSTOMER_READ_MODEL_NEXT_PRIMARY", default=True)


def _customer_read_model_legacy_rollback_enabled() -> bool:
    from aicrm_next.shared.runtime import legacy_production_facade_enabled, production_data_ready

    return (
        production_data_ready()
        and legacy_production_facade_enabled()
        and _env_flag("CUSTOMER_READ_MODEL_LEGACY_ROLLBACK_ENABLED", default=False)
    )


def _production_customer_data_required() -> bool:
    from aicrm_next.shared.runtime import production_data_ready

    return production_data_ready()


def _diagnostics(
    *,
    source_status: str,
    read_model_status: str,
    degraded: bool = False,
    fallback_used: bool = False,
    fallback_reason: str = "",
) -> JsonDict:
    payload: JsonDict = {
        "source_status": source_status,
        "read_model_status": read_model_status,
        "route_owner": "ai_crm_next",
        "degraded": degraded,
        "fallback_used": fallback_used,
    }
    if fallback_used or fallback_reason:
        payload["fallback_reason"] = fallback_reason
    return payload


def _list_customers_unavailable_payload(query: ListCustomersRequest, exc: Exception) -> JsonDict:
    return {
        "ok": False,
        "degraded": True,
        "customers": [],
        "items": [],
        "count": 0,
        "total": 0,
        "limit": query.limit,
        "offset": query.offset,
        "filters": {
            "owner_userid": query.owner_userid or "",
            "tag": query.tag or "",
            "status": query.status or "",
            "is_bound": query.is_bound or "",
            "mobile": query.mobile or "",
            "keyword": query.keyword or "",
            "limit": str(query.limit),
            "offset": str(query.offset),
        },
        "source_status": "production_unavailable",
        "read_model_status": "unavailable",
        "error_code": "customer_list_read_unavailable",
        "page_error": str(exc),
        "route_owner": "ai_crm_next",
        "fallback_used": False,
        "status_code": 503,
    }


def _customer_detail_unavailable_payload(external_userid: str, exc: Exception) -> JsonDict:
    return {
        "ok": False,
        "degraded": True,
        "customer": {},
        "source_status": "production_unavailable",
        "read_model_status": "unavailable",
        "error_code": "customer_detail_read_unavailable",
        "page_error": str(exc),
        "route_owner": "ai_crm_next",
        "fallback_used": False,
        "status_code": 503,
        "external_userid": external_userid,
    }


def _customer_timeline_unavailable_payload(query: CustomerTimelineRequest, exc: Exception) -> JsonDict:
    return {
        "ok": False,
        "degraded": True,
        "timeline": {
            "external_userid": query.external_userid,
            "items": [],
            "count": 0,
            "limit": query.limit,
            "offset": query.offset,
            "filters": {
                "event_type": query.event_type or "",
                "limit": str(query.limit),
                "offset": str(query.offset),
            },
            "total": 0,
        },
        "source_status": "production_unavailable",
        "read_model_status": "unavailable",
        "error_code": "customer_timeline_read_unavailable",
        "page_error": str(exc),
        "route_owner": "ai_crm_next",
        "fallback_used": False,
        "status_code": 503,
    }


def _recent_messages_unavailable_payload(query: RecentMessagesRequest, exc: Exception) -> JsonDict:
    return {
        "ok": False,
        "degraded": True,
        "messages": [],
        "items": [],
        "count": 0,
        "external_userid": query.external_userid,
        "limit": query.limit,
        "source_status": "production_unavailable",
        "read_model_status": "unavailable",
        "error_code": "recent_messages_read_unavailable",
        "page_error": str(exc),
        "route_owner": "ai_crm_next",
        "fallback_used": False,
        "status_code": 503,
    }


def _list_filters(query: ListCustomersRequest) -> JsonDict:
    return {
        "owner_userid": query.owner_userid or "",
        "tag": query.tag or "",
        "status": query.status or "",
        "is_bound": query.is_bound or "",
        "mobile": query.mobile or "",
        "keyword": query.keyword or "",
        "limit": str(query.limit),
        "offset": str(query.offset),
    }


def _legacy_list_customers(query: ListCustomersRequest, *, fallback_reason: str) -> JsonDict:
    from aicrm_next.integration_gateway.legacy_customer_read_facade import list_customers_via_legacy

    payload = dict(list_customers_via_legacy(query) or {})
    payload.setdefault("ok", True)
    payload.setdefault("status_code", 200)
    payload.update(
        _diagnostics(
            source_status="legacy_production_facade",
            read_model_status="fallback",
            fallback_used=True,
            fallback_reason=fallback_reason,
        )
    )
    return payload


def _legacy_customer_detail(query: CustomerDetailRequest, *, fallback_reason: str) -> JsonDict:
    from aicrm_next.integration_gateway.legacy_customer_read_facade import get_customer_via_legacy

    customer = get_customer_via_legacy(query)
    if not customer:
        raise NotFoundError("customer not found")
    return {
        "ok": True,
        "customer": customer,
        "status_code": 200,
        **_diagnostics(
            source_status="legacy_production_facade",
            read_model_status="fallback",
            fallback_used=True,
            fallback_reason=fallback_reason,
        ),
    }


def _legacy_customer_timeline(query: CustomerTimelineRequest, *, fallback_reason: str) -> JsonDict:
    from aicrm_next.integration_gateway.legacy_customer_read_facade import get_timeline_via_legacy

    timeline = get_timeline_via_legacy(query)
    if not timeline:
        raise NotFoundError("customer timeline not found")
    return {
        "ok": True,
        "timeline": timeline,
        "status_code": 200,
        **_diagnostics(
            source_status="legacy_production_facade",
            read_model_status="fallback",
            fallback_used=True,
            fallback_reason=fallback_reason,
        ),
    }


def _legacy_recent_messages(query: RecentMessagesRequest, *, fallback_reason: str) -> JsonDict:
    from aicrm_next.integration_gateway.legacy_customer_read_facade import recent_messages_via_legacy

    payload = dict(recent_messages_via_legacy(query) or {})
    payload.setdefault("ok", True)
    payload.setdefault("status_code", 200)
    payload.update(
        _diagnostics(
            source_status="legacy_production_facade",
            read_model_status="fallback",
            fallback_used=True,
            fallback_reason=fallback_reason,
        )
    )
    return payload


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
        self._repo = repo
        self._contacts_adapter = contacts_adapter
        self._projection_gateway = projection_gateway

    def execute(self, query: ListCustomersRequest) -> JsonDict:
        if _production_customer_data_required():
            try:
                if not _customer_read_model_next_primary_enabled():
                    raise RuntimeError("customer read model next primary disabled")
                repo = self._repo or build_customer_read_model_repository()
                filters = _list_filters(query)
                rows = [list_item_projection(item) for item in repo.list_customers(filters, limit=None, offset=0)]
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
                    "status_code": 200,
                    **_diagnostics(source_status="next_read_model", read_model_status="primary"),
                }
            except Exception as exc:
                if _customer_read_model_legacy_rollback_enabled():
                    try:
                        return _legacy_list_customers(query, fallback_reason=str(exc))
                    except Exception as fallback_exc:
                        return _list_customers_unavailable_payload(query, fallback_exc)
                return _list_customers_unavailable_payload(query, exc)

        repo = self._repo or build_customer_read_model_repository()
        contacts_adapter = self._contacts_adapter or build_contacts_sync_adapter()
        projection_gateway = self._projection_gateway or build_customer_projection_sync_gateway()
        contacts_contract = contacts_adapter.fetch_external_contacts(
            follow_user_userid=query.owner_userid or "",
            limit=query.limit,
            sync_cursor=f"offset:{query.offset}",
        )
        projection_contract = projection_gateway.update_customer_list_projection(
            projection_name="customer_list",
            sync_cursor=f"offset:{query.offset}:limit:{query.limit}",
        )
        filters = _list_filters(query)
        rows = [list_item_projection(item) for item in repo.list_customers()]
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
            **_diagnostics(source_status="local_contract_probe", read_model_status="fixture"),
        }

    __call__ = execute


class GetCustomerDetailQuery:
    def __init__(self, repo: CustomerReadRepository | None = None, contacts_adapter=None, projection_gateway=None) -> None:
        self._repo = repo
        self._contacts_adapter = contacts_adapter
        self._projection_gateway = projection_gateway

    def execute(self, query: CustomerDetailRequest) -> JsonDict:
        if _production_customer_data_required():
            try:
                if not _customer_read_model_next_primary_enabled():
                    raise RuntimeError("customer read model next primary disabled")
                repo = self._repo or build_customer_read_model_repository()
                customer = repo.get_customer(query.external_userid)
                if not customer:
                    raise NotFoundError("customer not found")
            except NotFoundError:
                raise
            except Exception as exc:
                if _customer_read_model_legacy_rollback_enabled():
                    try:
                        return _legacy_customer_detail(query, fallback_reason=str(exc))
                    except NotFoundError:
                        raise
                    except Exception as fallback_exc:
                        return _customer_detail_unavailable_payload(query.external_userid, fallback_exc)
                return _customer_detail_unavailable_payload(query.external_userid, exc)
            return {
                "ok": True,
                "customer": detail_projection(customer),
                "status_code": 200,
                **_diagnostics(source_status="next_read_model", read_model_status="primary"),
            }

        repo = self._repo or build_customer_read_model_repository()
        contacts_adapter = self._contacts_adapter or build_contacts_sync_adapter()
        projection_gateway = self._projection_gateway or build_customer_projection_sync_gateway()
        contacts_contract = contacts_adapter.fetch_contact_detail(external_userid=query.external_userid)
        projection_contract = projection_gateway.update_customer_detail_projection(external_userid=query.external_userid)
        customer = repo.get_customer(query.external_userid)
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
            **_diagnostics(source_status="local_contract_probe", read_model_status="fixture"),
        }

    __call__ = execute


class GetCustomerTimelineQuery:
    def __init__(self, repo: CustomerReadRepository | None = None, projection_gateway=None) -> None:
        self._repo = repo
        self._projection_gateway = projection_gateway

    def execute(self, query: CustomerTimelineRequest) -> JsonDict:
        if _production_customer_data_required():
            try:
                if not _customer_read_model_next_primary_enabled():
                    raise RuntimeError("customer read model next primary disabled")
                repo = self._repo or build_customer_read_model_repository()
                if not repo.customer_exists(query.external_userid):
                    raise NotFoundError("customer not found")
                items = repo.list_timeline(query.external_userid, {"event_type": query.event_type or ""}, limit=None, offset=0)
                total = len(items)
                page = items[query.offset : query.offset + query.limit]
            except NotFoundError:
                raise
            except Exception as exc:
                if _customer_read_model_legacy_rollback_enabled():
                    try:
                        return _legacy_customer_timeline(query, fallback_reason=str(exc))
                    except NotFoundError:
                        raise
                    except Exception as fallback_exc:
                        return _customer_timeline_unavailable_payload(query, fallback_exc)
                return _customer_timeline_unavailable_payload(query, exc)
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
                "status_code": 200,
                **_diagnostics(source_status="next_read_model", read_model_status="primary"),
            }

        repo = self._repo or build_customer_read_model_repository()
        projection_gateway = self._projection_gateway or build_customer_projection_sync_gateway()
        projection_contract = projection_gateway.update_customer_timeline_projection(
            external_userid=query.external_userid,
            sync_cursor=f"offset:{query.offset}:limit:{query.limit}",
        )
        customer = repo.get_customer(query.external_userid)
        if not customer:
            raise NotFoundError("customer not found")
        items = repo.list_timeline(query.external_userid)
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
            **_diagnostics(source_status="local_contract_probe", read_model_status="fixture"),
        }

    __call__ = execute


class ListRecentMessagesQuery:
    def __init__(self, repo: CustomerReadRepository | None = None, archive_adapter=None, projection_gateway=None) -> None:
        self._repo = repo
        self._archive_adapter = archive_adapter
        self._projection_gateway = projection_gateway

    def execute(self, query: RecentMessagesRequest) -> JsonDict:
        if _production_customer_data_required():
            try:
                if not _customer_read_model_next_primary_enabled():
                    raise RuntimeError("customer read model next primary disabled")
                repo = self._repo or build_customer_read_model_repository()
                if not repo.customer_exists(query.external_userid):
                    raise NotFoundError("customer not found")
                messages = repo.list_recent_messages(query.external_userid, limit=query.limit)
            except NotFoundError:
                raise
            except Exception as exc:
                if _customer_read_model_legacy_rollback_enabled():
                    try:
                        return _legacy_recent_messages(query, fallback_reason=str(exc))
                    except NotFoundError:
                        raise
                    except Exception as fallback_exc:
                        return _recent_messages_unavailable_payload(query, fallback_exc)
                return _recent_messages_unavailable_payload(query, exc)
            return {
                "ok": True,
                "messages": messages,
                "items": messages,
                "count": len(messages),
                "external_userid": query.external_userid,
                "limit": query.limit,
                "status_code": 200,
                **_diagnostics(source_status="next_read_model", read_model_status="primary"),
            }

        repo = self._repo or build_customer_read_model_repository()
        archive_adapter = self._archive_adapter or build_archive_sync_adapter()
        projection_gateway = self._projection_gateway or build_customer_projection_sync_gateway()
        archive_contract = archive_adapter.fetch_recent_messages(
            external_userid=query.external_userid,
            limit=query.limit,
        )
        projection_contract = projection_gateway.update_recent_messages_projection(
            external_userid=query.external_userid,
            sync_cursor=f"limit:{query.limit}",
        )
        customer = repo.get_customer(query.external_userid)
        if not customer:
            raise NotFoundError("customer not found")
        messages = repo.list_recent_messages(query.external_userid)[: query.limit]
        return {
            "ok": True,
            "messages": messages,
            "items": messages,
            "count": len(messages),
            "external_userid": query.external_userid,
            "limit": query.limit,
            "adapter_contract": {
                "archive_sync": archive_contract,
                "customer_projection": projection_contract,
            },
            "side_effect_safety": customer_sync_side_effect_safety(),
            **_diagnostics(source_status="local_contract_probe", read_model_status="fixture"),
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
    read_model_status: str = "",
    adapter_contract: JsonDict | None = None,
    warnings: list[str] | None = None,
    fallback_used: bool = False,
    fallback_reason: str = "",
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
        **_diagnostics(
            source_status=source_status,
            read_model_status=read_model_status or source_status,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
        ),
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
        "read_model_status": "unavailable",
        "degraded": True,
        "fallback_used": False,
        "page_error": str(exc),
        "error_code": "customer_context_read_unavailable",
        "warnings": ["customer_context_read_failed"],
        "adapter_contract": {},
        "side_effect_safety": customer_sync_side_effect_safety(),
    }


def _admin_profile_input_error(message: str) -> JsonDict:
    return {
        "ok": False,
        "error": message,
        "source_status": "input_error",
        "route_owner": "ai_crm_next",
        "status_code": 400,
    }


def _admin_profile_payload(
    context: JsonDict,
    *,
    resolved_by: str = "external_userid",
) -> JsonDict:
    profile = dict(context.get("customer") or context.get("profile") or {})
    external_userid = str(profile.get("external_userid") or profile.get("user_id") or "")
    normalized_profile = {
        **profile,
        "external_userid": external_userid,
        "user_id": profile.get("user_id") or external_userid,
        "tags": list(profile.get("tags") or []),
        "binding": dict(profile.get("binding") or {}),
        "identity": dict(profile.get("identity") or {}),
        "marketing_profile": dict(profile.get("marketing_profile") or {}),
        "sidebar_context": dict(profile.get("sidebar_context") or {}),
    }
    return {
        "ok": True,
        "profile": normalized_profile,
        "customer": normalized_profile,
        "lookup": {"resolved_by": resolved_by, "external_userid": external_userid},
        "source_status": context.get("source_status"),
        "read_model_status": context.get("read_model_status"),
        "route_owner": "ai_crm_next",
        "context": context,
        "identity_binding_summary": dict(context.get("identity_binding_summary") or {}),
        "degraded": bool(context.get("degraded")),
        "fallback_used": bool(context.get("fallback_used")),
        "fallback_reason": context.get("fallback_reason") or "",
        "page_error": context.get("page_error") or "",
        "status_code": 200,
    }


def _admin_profile_tags_payload(customer: JsonDict, *, source_status: str) -> JsonDict:
    tags = list(customer.get("tags") or [])
    return {
        "ok": True,
        "tags": tags,
        "count": len(tags),
        "external_userid": str(customer.get("external_userid") or ""),
        "source_status": source_status,
        "route_owner": "ai_crm_next",
        "status_code": 200,
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
        payload = ListCustomersQuery(self._repo)(ListCustomersRequest(mobile=mobile, limit=1, offset=0))
        if not payload.get("ok"):
            raise RuntimeError(str(payload.get("page_error") or payload.get("error_code") or "customer read model unavailable"))
        rows = list(payload.get("customers") or payload.get("items") or [])
        if not rows or not str(rows[0].get("external_userid") or "").strip():
            raise NotFoundError("customer not found")
        return str(rows[0]["external_userid"])

    def execute(self, query: CustomerContextRequest) -> JsonDict:
        from aicrm_next.shared.runtime import production_data_ready

        if production_data_ready():
            try:
                external_userid = self._resolve_production_external_userid(query)
                detail = GetCustomerDetailQuery(self._repo)(CustomerDetailRequest(external_userid=external_userid))
                if not detail.get("ok"):
                    raise RuntimeError(str(detail.get("page_error") or detail.get("error_code") or "customer detail unavailable"))
                timeline_payload = GetCustomerTimelineQuery(self._repo)(
                    CustomerTimelineRequest(external_userid=external_userid, limit=query.timeline_limit)
                )
                if not timeline_payload.get("ok"):
                    raise RuntimeError(str(timeline_payload.get("page_error") or timeline_payload.get("error_code") or "customer timeline unavailable"))
                messages_payload = ListRecentMessagesQuery(self._repo)(
                    RecentMessagesRequest(external_userid=external_userid, limit=query.recent_message_limit)
                )
                if not messages_payload.get("ok"):
                    raise RuntimeError(str(messages_payload.get("page_error") or messages_payload.get("error_code") or "recent messages unavailable"))
                timeline = dict(timeline_payload.get("timeline") or {})
                recent_messages = list(messages_payload.get("messages") or messages_payload.get("items") or [])
                return _customer_context_payload(
                    external_userid=external_userid,
                    customer=detail["customer"],
                    timeline=timeline,
                    recent_messages=recent_messages,
                    source_status=str(detail.get("source_status") or "next_read_model"),
                    read_model_status=str(detail.get("read_model_status") or "primary"),
                    adapter_contract={
                        "detail": {"source_status": detail.get("source_status"), "fallback_used": detail.get("fallback_used")},
                        "timeline": {"source_status": timeline_payload.get("source_status"), "fallback_used": timeline_payload.get("fallback_used")},
                        "recent_messages": {"source_status": messages_payload.get("source_status"), "fallback_used": messages_payload.get("fallback_used")},
                    },
                    fallback_used=bool(detail.get("fallback_used") or timeline_payload.get("fallback_used") or messages_payload.get("fallback_used")),
                    fallback_reason=str(detail.get("fallback_reason") or timeline_payload.get("fallback_reason") or messages_payload.get("fallback_reason") or ""),
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
            read_model_status="fixture",
            adapter_contract={
                "detail": detail.get("adapter_contract", {}),
                "timeline": timeline.get("adapter_contract", {}),
                "recent_messages": messages.get("adapter_contract", {}),
            },
        )

    __call__ = execute


class GetAdminCustomerProfileQuery:
    def __init__(self, context_query: GetCustomerContextQuery | None = None) -> None:
        self._context_query = context_query or GetCustomerContextQuery()

    def execute(
        self,
        *,
        external_userid: str | None = None,
        mobile: str | None = None,
        user_id: str | None = None,
    ) -> JsonDict:
        resolved_external_userid = str(external_userid or user_id or "").strip()
        resolved_mobile = str(mobile or "").strip()
        if not resolved_external_userid and not resolved_mobile:
            return _admin_profile_input_error("external_userid is required")

        request = CustomerContextRequest(
            external_userid=resolved_external_userid or None,
            mobile=resolved_mobile or None,
            user_id=str(user_id or "").strip() or None,
        )
        try:
            context = self._context_query(request)
        except NotFoundError:
            return _admin_profile_input_error("customer not found")
        except Exception as exc:
            fallback_external_userid = resolved_external_userid
            context = _production_unavailable_payload(fallback_external_userid, exc)

        if not context.get("ok"):
            payload = dict(context)
            payload.setdefault("route_owner", "ai_crm_next")
            payload["status_code"] = 503 if payload.get("degraded") else 400
            return payload

        customer = dict(context.get("customer") or {})
        if not customer:
            return _admin_profile_input_error("customer not found")

        if resolved_mobile and not resolved_external_userid:
            resolved_by = "mobile"
        else:
            resolved_by = (
                "user_id_fallback_external_userid"
                if user_id and not external_userid
                else "external_userid"
            )
        return _admin_profile_payload(context, resolved_by=resolved_by)

    __call__ = execute


class GetAdminCustomerProfileTagsQuery:
    def __init__(self, context_query: GetCustomerContextQuery | None = None) -> None:
        self._context_query = context_query or GetCustomerContextQuery()

    def execute(
        self,
        *,
        external_userid: str | None = None,
        user_id: str | None = None,
    ) -> JsonDict:
        resolved_external_userid = str(external_userid or user_id or "").strip()
        if not resolved_external_userid:
            return _admin_profile_input_error("external_userid is required")

        try:
            context = self._context_query(
                CustomerContextRequest(
                    external_userid=resolved_external_userid,
                    user_id=str(user_id or "").strip() or None,
                )
            )
        except NotFoundError:
            return _admin_profile_input_error("customer not found")
        except Exception as exc:
            context = _production_unavailable_payload(resolved_external_userid, exc)

        if not context.get("ok"):
            payload = dict(context)
            payload.setdefault("route_owner", "ai_crm_next")
            payload["status_code"] = 503 if payload.get("degraded") else 400
            return payload

        customer = dict(context.get("customer") or {})
        if not customer:
            return _admin_profile_input_error("customer not found")
        return _admin_profile_tags_payload(
            customer,
            source_status=str(context.get("source_status") or ""),
        )

    __call__ = execute


GetCustomerChatContextQuery = GetCustomerContextQuery
