from __future__ import annotations

from typing import Any

from .definitions import (
    DEFAULT_DELIVERY_ROUTE_OWNER_USERID,
    DEFAULT_SALES_ROUTE_OWNER_USERID,
    OWNER_CLASS_TERM_BACKFILL_ENTRY_SOURCE_OVERRIDES,
    ROUTING_REASON_OWNER_ROLE_MISSING,
    ROUTING_REASON_OWNER_ROLE_UNKNOWN,
    ROUTING_REASON_SIGNUP_STATUS_UNKNOWN,
    ROUTING_RULES,
)
from . import repo


def get_owner_role(userid: str) -> dict[str, Any] | None:
    row = repo.get_owner_role(str(userid or "").strip())
    return dict(row) if row else None


def list_owner_role_map(active_only: bool = False) -> list[dict[str, Any]]:
    return [dict(row) for row in repo.list_owner_role_map(active_only=active_only)]


def build_routing_config(
    *,
    owner_role_map: list[dict[str, Any]] | None = None,
    signup_tag_rules: dict[str, Any],
) -> dict[str, Any]:
    owner_role_items = owner_role_map if owner_role_map is not None else list_owner_role_map()
    return {
        "owner_role_map": [dict(item) for item in owner_role_items],
        "signup_tag_rules": dict(signup_tag_rules),
        "routing_rules": {key: dict(value) for key, value in ROUTING_RULES.items()},
    }


def resolve_contact_routing_context(
    *,
    owner_userid: str,
    owner_role: str,
    signup_status: str,
    routing_alias: str = "",
) -> dict[str, Any]:
    del owner_userid

    normalized_owner_role = str(owner_role or "").strip()
    routing_status = str(routing_alias or signup_status or "").strip()

    if not normalized_owner_role:
        return {
            "routing_target": ROUTING_RULES["owner_role_missing"]["routing_target"],
            "route_owner_userid": "",
            "reason": ROUTING_REASON_OWNER_ROLE_MISSING,
        }
    if routing_status in {"pre_signup", "signed_999"}:
        return {
            "routing_target": ROUTING_RULES[routing_status]["routing_target"],
            "route_owner_userid": DEFAULT_SALES_ROUTE_OWNER_USERID,
        }
    if routing_status == "signed_3999":
        if normalized_owner_role == "sales":
            return {
                "routing_target": ROUTING_RULES["signed_3999"]["when_owner_role_sales"],
                "route_owner_userid": DEFAULT_DELIVERY_ROUTE_OWNER_USERID,
            }
        if normalized_owner_role == "delivery":
            return {
                "routing_target": ROUTING_RULES["signed_3999"]["when_owner_role_delivery"],
                "route_owner_userid": DEFAULT_DELIVERY_ROUTE_OWNER_USERID,
            }
        return {
            "routing_target": ROUTING_RULES["unknown"]["routing_target"],
            "route_owner_userid": "",
            "reason": ROUTING_REASON_OWNER_ROLE_UNKNOWN,
        }
    return {
        "routing_target": ROUTING_RULES["unknown"]["routing_target"],
        "route_owner_userid": "",
        "reason": ROUTING_REASON_SIGNUP_STATUS_UNKNOWN,
    }


def get_owner_class_term_backfill_entry_source_override(owner_userid: str) -> str:
    normalized_owner_userid = str(owner_userid or "").strip()
    return OWNER_CLASS_TERM_BACKFILL_ENTRY_SOURCE_OVERRIDES.get(normalized_owner_userid, "")
