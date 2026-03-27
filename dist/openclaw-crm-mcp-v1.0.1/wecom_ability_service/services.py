from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

import requests
from flask import current_app, has_request_context, session

from .db import get_db, get_db_backend


SENSITIVE_KEYS = {
    "WECOM_CONTACT_SECRET",
    "WECOM_SECRET",
    "WECOM_ARCHIVE_SECRET",
    "WECOM_CALLBACK_TOKEN",
    "WECOM_CALLBACK_AES_KEY",
    "WECHAT_MP_APP_SECRET",
}

LEGACY_DESCRIPTION_PREFIX = "external_userid:"
QUESTIONNAIRE_TYPES = {"single_choice", "multi_choice", "textarea"}
questionnaire_logger = logging.getLogger("questionnaire")

SIGNUP_TAG_GROUP_NAME = "AI 产品报名情况"
SIGNUP_TAG_STATUS_DEFINITIONS = [
    {
        "signup_status": "lead",
        "tag_name": "报名引流品",
        "label": "报名引流品",
        "routing_alias": "pre_signup",
    },
    {
        "signup_status": "signed_999",
        "tag_name": "已报名999",
        "label": "已报名999",
        "routing_alias": "signed_999",
    },
    {
        "signup_status": "signed_3999",
        "tag_name": "已报名3999",
        "label": "已报名3999",
        "routing_alias": "signed_3999",
    },
]

CLASS_USER_ALLOWED_STATUSES = {
    item["signup_status"]: {
        "signup_status": item["signup_status"],
        "label": item["label"],
        "tag_name": item["tag_name"],
    }
    for item in SIGNUP_TAG_STATUS_DEFINITIONS
}


class QuestionnaireAlreadySubmittedError(ValueError):
    pass


class ContactBindingConflictError(ValueError):
    pass


class ThirdPartyUserSyncError(RuntimeError):
    pass


def mask_value(key: str, value: str) -> str:
    if key not in SENSITIVE_KEYS:
        return value
    if not value:
        return ""
    if len(value) <= 6:
        return "*" * len(value)
    return f"{value[:3]}***{value[-2:]}"


def _normalize_optional_timestamp(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, str) and "-" in value and ":" in value:
        return value
    ts = int(value)
    if ts > 10_000_000_000:
        ts = ts // 1000
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def get_setting(key: str) -> str | None:
    row = get_db().execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_settings(settings: dict[str, Any]) -> None:
    db = get_db()
    for key, value in settings.items():
        db.execute(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
            """,
            (key, str(value)),
        )
    db.commit()


def list_settings_snapshot(config: dict[str, Any]) -> dict[str, str]:
    keys = [
        "WECOM_CORP_ID",
        "WECOM_SECRET",
        "WECOM_CONTACT_SECRET",
        "WECOM_AGENT_ID",
        "WECOM_API_BASE",
        "WECOM_ARCHIVE_SECRET",
        "WECOM_PRIVATE_KEY_PATH",
        "WECOM_SDK_LIB_PATH",
        "WECOM_DEFAULT_OWNER_USERID",
        "WECOM_CALLBACK_TOKEN",
        "WECOM_CALLBACK_AES_KEY",
        "WECOM_ARCHIVE_TIMEOUT",
        "WECHAT_MP_APP_ID",
        "WECHAT_MP_APP_SECRET",
        "WECHAT_MP_OAUTH_SCOPE",
    ]
    snapshot = {}
    for key in keys:
        value = get_setting(key)
        if value is None:
            value = str(config.get(key, ""))
        snapshot[key] = mask_value(key, value)
    return snapshot


def _select_follow_user(payload: dict[str, Any], owner_userid: str | None = None) -> dict[str, Any]:
    follow_users = payload.get("follow_user") or []
    if owner_userid:
        matched = next((item for item in follow_users if item.get("userid") == owner_userid), None)
        if matched:
            return matched
    return follow_users[0] if follow_users else {}


def normalize_contact_record(payload: dict[str, Any], owner_userid: str | None = None) -> dict[str, Any]:
    external_contact = payload.get("external_contact") or payload
    primary_follow_user = _select_follow_user(payload, owner_userid=owner_userid)
    normalized_owner = owner_userid or primary_follow_user.get("userid") or payload.get("owner_userid") or ""
    return {
        "external_userid": external_contact.get("external_userid", ""),
        "customer_name": external_contact.get("name", ""),
        "owner_userid": normalized_owner,
        "remark": primary_follow_user.get("remark", ""),
        "description": primary_follow_user.get("description", ""),
    }


def target_contact_description(external_userid: str) -> str:
    return external_userid.strip()


def contact_description_state(description: str | None, external_userid: str) -> str:
    normalized = (description or "").strip()
    target = target_contact_description(external_userid)
    if not normalized:
        return "empty"
    if normalized == target:
        return "target"
    if normalized == f"{LEGACY_DESCRIPTION_PREFIX} {target}" or normalized == f"{LEGACY_DESCRIPTION_PREFIX}{target}":
        return "legacy"
    return "custom"


def needs_contact_description_update(description: str | None, external_userid: str) -> bool:
    return contact_description_state(description, external_userid) in {"empty", "legacy"}


def plan_contact_description_fix(
    payload: dict[str, Any],
    *,
    owner_userid: str | None = None,
    existing_contact: dict[str, Any] | None = None,
    default_owner_userid: str = "",
) -> dict[str, Any]:
    normalized_original = normalize_contact_record(payload, owner_userid=owner_userid)
    external_userid = str(normalized_original.get("external_userid") or "").strip()
    result = {
        "external_userid": external_userid,
        "normalized_original": dict(normalized_original),
        "normalized": dict(normalized_original),
        "should_update": False,
        "target_description": target_contact_description(external_userid) if external_userid else "",
        "description_state": contact_description_state(normalized_original.get("description"), external_userid)
        if external_userid
        else "",
        "resolved_owner_userid": (
            str(normalized_original.get("owner_userid") or "").strip()
            or str(owner_userid or "").strip()
            or str(default_owner_userid or "").strip()
        ),
        "update_payload": None,
    }
    if not external_userid:
        return result

    if existing_contact and contact_description_state(existing_contact.get("description"), external_userid) == "custom":
        normalized = dict(normalized_original)
        normalized["description"] = str(existing_contact.get("description") or "").strip()
        result["normalized"] = normalized
        return result

    if not result["resolved_owner_userid"]:
        return result

    if needs_contact_description_update(normalized_original.get("description"), external_userid):
        normalized = dict(normalized_original)
        normalized["description"] = result["target_description"]
        result["normalized"] = normalized
        result["should_update"] = True
        result["update_payload"] = {
            "userid": result["resolved_owner_userid"],
            "external_userid": external_userid,
            "description": result["target_description"],
        }
    return result


def upsert_contacts(contacts: list[dict[str, Any]]) -> tuple[int, int]:
    db = get_db()
    inserted = 0
    updated = 0
    for item in contacts:
        if not item.get("external_userid"):
            continue
        existing = db.execute(
            """
            SELECT customer_name, owner_userid, remark, description
            FROM contacts
            WHERE external_userid = ?
            """,
            (item["external_userid"],),
        ).fetchone()
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(external_userid) DO UPDATE SET
                customer_name = excluded.customer_name,
                owner_userid = excluded.owner_userid,
                remark = excluded.remark,
                description = excluded.description,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                item["external_userid"],
                item.get("customer_name", ""),
                item.get("owner_userid", ""),
                item.get("remark", ""),
                item.get("description", ""),
            ),
        )
        if existing is None:
            inserted += 1
        elif (
            existing.get("customer_name") != item.get("customer_name", "")
            or existing.get("owner_userid") != item.get("owner_userid", "")
            or existing.get("remark") != item.get("remark", "")
            or existing.get("description") != item.get("description", "")
        ):
            updated += 1
    db.commit()
    return inserted, updated


def list_contacts(owner_userid: str | None = None) -> list[dict[str, Any]]:
    sql = """
        SELECT external_userid, customer_name, owner_userid, remark, description, updated_at
        FROM contacts
    """
    params: list[Any] = []
    if owner_userid:
        sql += " WHERE owner_userid = ?"
        params.append(owner_userid)
    sql += " ORDER BY updated_at DESC, id DESC"
    rows = get_db().execute(sql, tuple(params)).fetchall()
    return list(rows)


def get_contact_by_external_userid(external_userid: str) -> dict[str, Any] | None:
    row = get_db().execute(
        """
        SELECT external_userid, customer_name, owner_userid, remark, description, updated_at
        FROM contacts
        WHERE external_userid = ?
        """,
        (external_userid,),
    ).fetchone()
    if not row:
        return None
    return enrich_contact_context(dict(row))


def get_contact_tag_snapshots(external_userid: str) -> list[dict[str, Any]]:
    rows = get_db().execute(
        """
        SELECT external_userid, userid, tag_id, COALESCE(tag_name, '') AS tag_name, created_at
        FROM contact_tags
        WHERE external_userid = ?
        ORDER BY userid ASC, tag_name ASC, tag_id ASC
        """,
        (external_userid,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_owner_role(userid: str) -> dict[str, Any] | None:
    if not userid:
        return None
    row = get_db().execute(
        """
        SELECT userid, display_name, role, active, updated_at
        FROM owner_role_map
        WHERE userid = ?
        """,
        (userid,),
    ).fetchone()
    return dict(row) if row else None


def list_owner_role_map(active_only: bool = False) -> list[dict[str, Any]]:
    sql = """
        SELECT userid, display_name, role, active, updated_at
        FROM owner_role_map
    """
    params: list[Any] = []
    if active_only:
        sql += " WHERE active = ?"
        params.append(True if get_db_backend() == "postgres" else 1)
    sql += " ORDER BY active DESC, display_name ASC, userid ASC"
    rows = get_db().execute(sql, tuple(params)).fetchall()
    return [dict(row) for row in rows]


def list_signup_tag_rules(active_only: bool = False) -> list[dict[str, Any]]:
    sql = """
        SELECT tag_id, tag_name, signup_status, active, updated_at
        FROM signup_tag_rules
    """
    params: list[Any] = []
    if active_only:
        sql += " WHERE active = ?"
        params.append(True if get_db_backend() == "postgres" else 1)
    sql += " ORDER BY active DESC, signup_status ASC, tag_name ASC, tag_id ASC"
    rows = get_db().execute(sql, tuple(params)).fetchall()
    return [dict(row) for row in rows]


def _signup_tag_group_name() -> str:
    return SIGNUP_TAG_GROUP_NAME


def get_signup_status_definitions() -> list[dict[str, Any]]:
    return [dict(item) for item in SIGNUP_TAG_STATUS_DEFINITIONS]


def get_signup_status_definition(signup_status: str) -> dict[str, Any] | None:
    normalized = str(signup_status or "").strip()
    return next((dict(item) for item in SIGNUP_TAG_STATUS_DEFINITIONS if item["signup_status"] == normalized), None)


def get_signup_status_definition_by_tag_name(tag_name: str) -> dict[str, Any] | None:
    normalized = str(tag_name or "").strip()
    return next((dict(item) for item in SIGNUP_TAG_STATUS_DEFINITIONS if item["tag_name"] == normalized), None)


def upsert_signup_tag_rule(tag_id: str, tag_name: str, signup_status: str, active: bool = True) -> None:
    normalized_tag_id = str(tag_id or "").strip()
    normalized_tag_name = str(tag_name or "").strip()
    normalized_status = str(signup_status or "").strip()
    if not normalized_tag_id or not normalized_tag_name or not normalized_status:
        return
    active_value = True if get_db_backend() == "postgres" else (1 if active else 0)
    get_db().execute(
        """
        INSERT INTO signup_tag_rules (tag_id, tag_name, signup_status, active, updated_at)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(tag_id) DO UPDATE SET
            tag_name = excluded.tag_name,
            signup_status = excluded.signup_status,
            active = excluded.active,
            updated_at = CURRENT_TIMESTAMP
        """,
        (normalized_tag_id, normalized_tag_name, normalized_status, active_value),
    )
    get_db().commit()


def get_signup_tag_rules_config() -> dict[str, Any]:
    items = list_signup_tag_rules(active_only=True)
    rules_by_status: dict[str, list[dict[str, Any]]] = {
        definition["signup_status"]: [] for definition in SIGNUP_TAG_STATUS_DEFINITIONS
    }
    for item in items:
        signup_status = str(item.get("signup_status") or "").strip()
        if signup_status in rules_by_status:
            rules_by_status[signup_status].append(item)
    derived_statuses = [
        {
            "signup_status": "pre_signup",
            "match_mode": "no_tag_match",
            "tag_ids": [],
            "tag_names": [],
        }
    ]
    for definition in SIGNUP_TAG_STATUS_DEFINITIONS:
        status = definition["signup_status"]
        derived_statuses.append(
            {
                "signup_status": status,
                "match_mode": "match_any",
                "tag_ids": [item.get("tag_id", "") for item in rules_by_status[status]],
                "tag_names": [item.get("tag_name", "") for item in rules_by_status[status]],
                "label": definition["label"],
            }
        )
    return {
        "tag_group_name": _signup_tag_group_name(),
        "status_definitions": get_signup_status_definitions(),
        "items": items,
        "derived_statuses": derived_statuses
        + [
            {
                "signup_status": "unknown",
                "match_mode": "conflict",
                "tag_ids": sorted(
                    {
                        item.get("tag_id", "")
                        for status_items in rules_by_status.values()
                        for item in status_items
                        if item.get("tag_id")
                    }
                ),
                "tag_names": sorted(
                    {
                        item.get("tag_name", "")
                        for status_items in rules_by_status.values()
                        for item in status_items
                        if item.get("tag_name")
                    }
                ),
                "conflict_when_statuses": [item["signup_status"] for item in SIGNUP_TAG_STATUS_DEFINITIONS],
            },
        ],
    }


def resolve_signup_status_from_tags(tags: list[dict[str, Any]]) -> dict[str, Any]:
    rules = list_signup_tag_rules(active_only=True)
    status_by_tag_id: dict[str, str] = {}
    tag_name_by_id: dict[str, str] = {}
    for rule in rules:
        tag_id = str(rule.get("tag_id") or "").strip()
        signup_status = str(rule.get("signup_status") or "").strip()
        if not tag_id or not signup_status:
            continue
        status_by_tag_id[tag_id] = signup_status
        tag_name_by_id[tag_id] = str(rule.get("tag_name") or "").strip()

    matched_statuses: set[str] = set()
    matched_rules: list[dict[str, Any]] = []
    for tag in tags:
        tag_id = str(tag.get("tag_id") or "").strip()
        if not tag_id or tag_id not in status_by_tag_id:
            continue
        signup_status = status_by_tag_id[tag_id]
        matched_statuses.add(signup_status)
        matched_rules.append(
            {
                "tag_id": tag_id,
                "tag_name": tag_name_by_id.get(tag_id, "") or str(tag.get("tag_name") or "").strip(),
                "signup_status": signup_status,
            }
        )

    if len(matched_statuses) > 1:
        signup_status = "unknown"
    elif matched_statuses:
        signup_status = next(iter(matched_statuses))
    else:
        signup_status = "pre_signup"

    return {
        "signup_status": signup_status,
        "matched_signup_rules": matched_rules,
        "matched_signup_rule_statuses": sorted(matched_statuses),
    }


def get_routing_config() -> dict[str, Any]:
    return {
        "owner_role_map": list_owner_role_map(active_only=True),
        "signup_tag_rules": get_signup_tag_rules_config(),
        "routing_rules": {
            "pre_signup": {
                "route_owner_userid": "ZhaoYanFang",
                "route_owner_role": "sales",
                "routing_target": "sales_handle",
            },
            "signed_999": {
                "route_owner_userid": "ZhaoYanFang",
                "route_owner_role": "sales",
                "routing_target": "sales_handle",
            },
            "signed_3999": {
                "route_owner_userid": "QianLan",
                "when_owner_role_sales": "delivery_redirect",
                "when_owner_role_delivery": "delivery_handle",
                "fallback": "manual_review",
            },
            "unknown": {
                "routing_target": "manual_review",
            },
            "owner_role_missing": {
                "routing_target": "manual_review",
            },
        },
    }


def resolve_contact_routing_context(owner_userid: str, owner_role: str, signup_status: str) -> dict[str, Any]:
    definition = get_signup_status_definition(signup_status)
    routing_status = definition.get("routing_alias", signup_status) if definition else signup_status
    if not owner_role:
        return {"routing_target": "manual_review", "route_owner_userid": "", "reason": "owner_role_missing"}
    if routing_status == "pre_signup":
        return {"routing_target": "sales_handle", "route_owner_userid": "ZhaoYanFang"}
    if routing_status == "signed_999":
        return {"routing_target": "sales_handle", "route_owner_userid": "ZhaoYanFang"}
    if routing_status == "signed_3999":
        if owner_role == "sales":
            return {"routing_target": "delivery_redirect", "route_owner_userid": "QianLan"}
        if owner_role == "delivery":
            return {"routing_target": "delivery_handle", "route_owner_userid": "QianLan"}
        return {"routing_target": "manual_review", "route_owner_userid": "", "reason": "owner_role_unknown"}
    return {"routing_target": "manual_review", "route_owner_userid": "", "reason": "signup_status_unknown"}


def enrich_contact_context(contact: dict[str, Any]) -> dict[str, Any]:
    owner_userid = str(contact.get("owner_userid") or "").strip()
    owner_role = get_owner_role(owner_userid) or {}
    enriched = dict(contact)
    tags = get_contact_tag_snapshots(str(contact.get("external_userid") or ""))
    if owner_userid:
        owner_scoped_tags = [item for item in tags if str(item.get("userid") or "").strip() == owner_userid]
        if owner_scoped_tags:
            tags = owner_scoped_tags
    signup_context = resolve_signup_status_from_tags(tags)
    enriched["tags"] = tags
    enriched["owner_role"] = owner_role.get("role", "") or ""
    enriched["owner_role_map"] = owner_role or {}
    enriched["signup_status"] = signup_context["signup_status"]
    enriched["matched_signup_rules"] = signup_context["matched_signup_rules"]
    enriched["routing_context"] = resolve_contact_routing_context(
        owner_userid=owner_userid,
        owner_role=enriched["owner_role"],
        signup_status=enriched["signup_status"],
    )
    return enriched


def get_primary_follow_user_userid(external_userid: str) -> str:
    normalized_external_userid = str(external_userid or "").strip()
    if not normalized_external_userid:
        return ""
    corp_id = str(current_app.config.get("WECOM_CORP_ID", "") or "").strip()
    row = get_db().execute(
        """
        SELECT user_id
        FROM wecom_external_contact_follow_users
        WHERE corp_id = ? AND external_userid = ? AND relation_status = 'active' AND is_primary = ?
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (corp_id, normalized_external_userid, True if get_db_backend() == "postgres" else 1),
    ).fetchone()
    if row and row.get("user_id"):
        return str(row["user_id"]).strip()
    contact = get_contact_by_external_userid(normalized_external_userid)
    if contact and contact.get("owner_userid"):
        return str(contact["owner_userid"]).strip()
    identity = resolve_external_contact_identity(corp_id, external_userid=normalized_external_userid)
    if identity and identity.get("follow_user_userid"):
        return str(identity["follow_user_userid"]).strip()
    return ""


def build_class_user_tag_view(tags: list[dict[str, Any]]) -> dict[str, Any]:
    signup_context = resolve_signup_status_from_tags(tags)
    status = signup_context["signup_status"]
    definition = get_signup_status_definition(status)
    matched_tags = [
        {
            "tag_id": str(item.get("tag_id") or "").strip(),
            "tag_name": str(item.get("tag_name") or "").strip(),
            "signup_status": str(item.get("signup_status") or "").strip(),
        }
        for item in signup_context.get("matched_signup_rules") or []
    ]
    current_tag_id = matched_tags[0]["tag_id"] if len(matched_tags) == 1 else ""
    current_tag_name = definition["label"] if definition else ("标签冲突" if status == "unknown" else "")
    return {
        "signup_status": status,
        "current_tag_id": current_tag_id,
        "current_tag_name": current_tag_name,
        "matched_tags": matched_tags,
    }


def get_class_user_status_definition(signup_status: str) -> dict[str, Any] | None:
    return CLASS_USER_ALLOWED_STATUSES.get(str(signup_status or "").strip())


def get_class_user_snapshot(external_userid: str, owner_userid: str = "") -> dict[str, str]:
    normalized_external_userid = str(external_userid or "").strip()
    normalized_owner_userid = str(owner_userid or "").strip()
    contact = get_contact_by_external_userid(normalized_external_userid) or {}
    person_identity = resolve_person_identity(external_userid=normalized_external_userid) if normalized_external_userid else {}
    mobile = str((person_identity or {}).get("mobile") or "").strip()
    customer_name = str(contact.get("customer_name") or "").strip() or str((person_identity or {}).get("customer_name") or "").strip()
    owner_snapshot = (
        normalized_owner_userid
        or str(contact.get("owner_userid") or "").strip()
        or str((person_identity or {}).get("owner_userid") or "").strip()
        or str((person_identity or {}).get("follow_user_userid") or "").strip()
    )
    return {
        "external_userid": normalized_external_userid,
        "customer_name_snapshot": customer_name,
        "owner_userid_snapshot": owner_snapshot,
        "mobile_snapshot": mobile,
    }


def get_class_user_status_current(external_userid: str) -> dict[str, Any] | None:
    row = get_db().execute(
        """
        SELECT
            external_userid,
            signup_status,
            signup_label_name,
            customer_name_snapshot,
            owner_userid_snapshot,
            mobile_snapshot,
            set_by_userid,
            set_at,
            wecom_tag_sync_status,
            wecom_tag_sync_error,
            status_flags_json,
            created_at,
            updated_at
        FROM class_user_status_current
        WHERE external_userid = ?
        """,
        (external_userid,),
    ).fetchone()
    return dict(row) if row else None


def upsert_class_user_status_current(
    *,
    external_userid: str,
    signup_status: str,
    signup_label_name: str,
    customer_name_snapshot: str,
    owner_userid_snapshot: str,
    mobile_snapshot: str,
    set_by_userid: str,
    set_at: str | None = None,
    wecom_tag_sync_status: str = "pending",
    wecom_tag_sync_error: str = "",
    status_flags_json: str = "{}",
) -> None:
    normalized_set_at = str(set_at or "").strip()
    db = get_db()
    if normalized_set_at:
        db.execute(
            """
            INSERT INTO class_user_status_current (
                external_userid,
                signup_status,
                signup_label_name,
                customer_name_snapshot,
                owner_userid_snapshot,
                mobile_snapshot,
                set_by_userid,
                set_at,
                wecom_tag_sync_status,
                wecom_tag_sync_error,
                status_flags_json,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(external_userid) DO UPDATE SET
                signup_status = excluded.signup_status,
                signup_label_name = excluded.signup_label_name,
                customer_name_snapshot = excluded.customer_name_snapshot,
                owner_userid_snapshot = excluded.owner_userid_snapshot,
                mobile_snapshot = excluded.mobile_snapshot,
                set_by_userid = excluded.set_by_userid,
                set_at = excluded.set_at,
                wecom_tag_sync_status = excluded.wecom_tag_sync_status,
                wecom_tag_sync_error = excluded.wecom_tag_sync_error,
                status_flags_json = excluded.status_flags_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                external_userid,
                signup_status,
                signup_label_name,
                customer_name_snapshot,
                owner_userid_snapshot,
                mobile_snapshot,
                set_by_userid,
                normalized_set_at,
                wecom_tag_sync_status,
                wecom_tag_sync_error,
                status_flags_json,
            ),
        )
    else:
        db.execute(
            """
            INSERT INTO class_user_status_current (
                external_userid,
                signup_status,
                signup_label_name,
                customer_name_snapshot,
                owner_userid_snapshot,
                mobile_snapshot,
                set_by_userid,
                set_at,
                wecom_tag_sync_status,
                wecom_tag_sync_error,
                status_flags_json,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(external_userid) DO UPDATE SET
                signup_status = excluded.signup_status,
                signup_label_name = excluded.signup_label_name,
                customer_name_snapshot = excluded.customer_name_snapshot,
                owner_userid_snapshot = excluded.owner_userid_snapshot,
                mobile_snapshot = excluded.mobile_snapshot,
                set_by_userid = excluded.set_by_userid,
                set_at = excluded.set_at,
                wecom_tag_sync_status = excluded.wecom_tag_sync_status,
                wecom_tag_sync_error = excluded.wecom_tag_sync_error,
                status_flags_json = excluded.status_flags_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                external_userid,
                signup_status,
                signup_label_name,
                customer_name_snapshot,
                owner_userid_snapshot,
                mobile_snapshot,
                set_by_userid,
                wecom_tag_sync_status,
                wecom_tag_sync_error,
                status_flags_json,
            ),
        )
    db.commit()


def append_class_user_status_history(
    *,
    external_userid: str,
    old_signup_status: str,
    new_signup_status: str,
    old_label_name: str,
    new_label_name: str,
    customer_name_snapshot: str,
    owner_userid_snapshot: str,
    mobile_snapshot: str,
    set_by_userid: str,
    set_at: str | None = None,
    wecom_tag_sync_status: str = "pending",
    wecom_tag_sync_error: str = "",
    status_flags_json: str = "{}",
) -> None:
    normalized_set_at = str(set_at or "").strip()
    db = get_db()
    if normalized_set_at:
        db.execute(
            """
            INSERT INTO class_user_status_history (
                external_userid,
                old_signup_status,
                new_signup_status,
                old_label_name,
                new_label_name,
                customer_name_snapshot,
                owner_userid_snapshot,
                mobile_snapshot,
                set_by_userid,
                set_at,
                wecom_tag_sync_status,
                wecom_tag_sync_error,
                status_flags_json,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                external_userid,
                old_signup_status,
                new_signup_status,
                old_label_name,
                new_label_name,
                customer_name_snapshot,
                owner_userid_snapshot,
                mobile_snapshot,
                set_by_userid,
                normalized_set_at,
                wecom_tag_sync_status,
                wecom_tag_sync_error,
                status_flags_json,
            ),
        )
    else:
        db.execute(
            """
            INSERT INTO class_user_status_history (
                external_userid,
                old_signup_status,
                new_signup_status,
                old_label_name,
                new_label_name,
                customer_name_snapshot,
                owner_userid_snapshot,
                mobile_snapshot,
                set_by_userid,
                set_at,
                wecom_tag_sync_status,
                wecom_tag_sync_error,
                status_flags_json,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                external_userid,
                old_signup_status,
                new_signup_status,
                old_label_name,
                new_label_name,
                customer_name_snapshot,
                owner_userid_snapshot,
                mobile_snapshot,
                set_by_userid,
                wecom_tag_sync_status,
                wecom_tag_sync_error,
                status_flags_json,
            ),
        )
    db.commit()


def update_class_user_status_sync_result(
    external_userid: str,
    *,
    wecom_tag_sync_status: str,
    wecom_tag_sync_error: str = "",
) -> None:
    get_db().execute(
        """
        UPDATE class_user_status_current
        SET wecom_tag_sync_status = ?,
            wecom_tag_sync_error = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE external_userid = ?
        """,
        (wecom_tag_sync_status, wecom_tag_sync_error, external_userid),
    )
    get_db().execute(
        """
        UPDATE class_user_status_history
        SET wecom_tag_sync_status = ?,
            wecom_tag_sync_error = ?
        WHERE id = (
            SELECT id
            FROM class_user_status_history
            WHERE external_userid = ?
            ORDER BY id DESC
            LIMIT 1
        )
        """,
        (wecom_tag_sync_status, wecom_tag_sync_error, external_userid),
    )
    get_db().commit()


def list_class_user_management_records(signup_status: str = "") -> dict[str, Any]:
    normalized_filter = str(signup_status or "").strip()
    status_definitions = get_signup_status_definitions()
    allowed_statuses = {item["signup_status"] for item in status_definitions}
    rows = get_db().execute(
        """
        SELECT
            current_status.external_userid,
            current_status.signup_status,
            current_status.signup_label_name,
            current_status.customer_name_snapshot,
            current_status.owner_userid_snapshot,
            current_status.mobile_snapshot,
            current_status.set_by_userid,
            current_status.set_at,
            current_status.wecom_tag_sync_status,
            current_status.wecom_tag_sync_error,
            current_status.updated_at AS current_updated_at,
            COALESCE(c.customer_name, '') AS contact_customer_name,
            COALESCE(c.owner_userid, '') AS contact_owner_userid,
            COALESCE(p.mobile, '') AS bound_mobile,
            COALESCE(owner_map.display_name, '') AS follow_user_display_name
        FROM class_user_status_current current_status
        LEFT JOIN contacts c
          ON c.external_userid = current_status.external_userid
        LEFT JOIN external_contact_bindings bindings
          ON bindings.external_userid = current_status.external_userid
        LEFT JOIN people p
          ON p.id = bindings.person_id
        LEFT JOIN owner_role_map owner_map
          ON owner_map.userid = COALESCE(current_status.owner_userid_snapshot, c.owner_userid, '')
        ORDER BY current_status.updated_at DESC, current_status.external_userid DESC
        """,
    ).fetchall()
    counts = {item["signup_status"]: 0 for item in status_definitions}
    items: list[dict[str, Any]] = []
    for row in rows:
        status = str(row.get("signup_status") or "").strip()
        if status in counts:
            counts[status] += 1
        if status not in allowed_statuses:
            continue
        if normalized_filter and status != normalized_filter:
            continue
        owner_userid = str(row.get("owner_userid_snapshot") or "").strip() or str(row.get("contact_owner_userid") or "").strip()
        customer_name = str(row.get("customer_name_snapshot") or "").strip() or str(row.get("contact_customer_name") or "").strip()
        mobile = str(row.get("bound_mobile") or "").strip() or str(row.get("mobile_snapshot") or "").strip()
        label_name = str(row.get("signup_label_name") or "").strip()
        items.append(
            {
                "external_userid": str(row.get("external_userid") or "").strip(),
                "customer_name": customer_name,
                "mobile": mobile,
                "follow_user_userid": owner_userid,
                "follow_user_display_name": str(row.get("follow_user_display_name") or "").strip() or owner_userid,
                "updated_at": str(row.get("current_updated_at") or row.get("set_at") or "").strip(),
                "status_fields": {
                    "signup_status": status,
                    "current_tag_id": "",
                    "current_tag_name": label_name,
                    "matched_tags": [
                        {
                            "tag_id": "",
                            "tag_name": label_name,
                            "signup_status": status,
                        }
                    ],
                    "operation_flags": {
                        "action_executed": None,
                        "added_wecom": None,
                        "mobile_bound": bool(mobile),
                    },
                    "wecom_tag_sync_status": str(row.get("wecom_tag_sync_status") or "").strip(),
                    "wecom_tag_sync_error": str(row.get("wecom_tag_sync_error") or "").strip(),
                },
            }
        )

    status_stats = [
        {
            "signup_status": item["signup_status"],
            "label": item["label"],
            "count": counts[item["signup_status"]],
        }
        for item in status_definitions
    ]
    items.sort(key=lambda item: (item.get("updated_at", ""), item.get("external_userid", "")), reverse=True)
    return {
        "filter": normalized_filter,
        "status_definitions": status_definitions,
        "stats": status_stats,
        "items": items,
        "total": len(items),
        "meta": {
            "module": "class_user_management",
            "reserved_filters": ["action_executed", "added_wecom", "mobile_bound", "phone_compare_status"],
            "reserved_fields": ["operation_flags", "binding_flags", "compare_flags"],
            "data_generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
    }


def export_class_user_management_records(signup_status: str = "") -> dict[str, Any]:
    result = list_class_user_management_records(signup_status=signup_status)
    headers = ["客户昵称", "手机号", "跟进人", "当前状态标签", "external_userid", "更新时间"]
    rows = [
        [
            item.get("customer_name", ""),
            item.get("mobile", ""),
            item.get("follow_user_display_name", ""),
            item.get("status_fields", {}).get("current_tag_name", ""),
            item.get("external_userid", ""),
            item.get("updated_at", ""),
        ]
        for item in result["items"]
    ]
    return {
        "headers": headers,
        "rows": rows,
        "filename": f"class-user-management-{result['filter'] or 'all'}-{datetime.now().strftime('%Y%m%d%H%M%S')}.xls",
    }


def list_class_user_status_history(limit: int = 100) -> dict[str, Any]:
    normalized_limit = max(1, min(int(limit or 100), 500))
    rows = get_db().execute(
        """
        SELECT
            id,
            external_userid,
            old_signup_status,
            new_signup_status,
            old_label_name,
            new_label_name,
            customer_name_snapshot,
            owner_userid_snapshot,
            mobile_snapshot,
            set_by_userid,
            set_at,
            wecom_tag_sync_status,
            wecom_tag_sync_error,
            created_at
        FROM class_user_status_history
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (normalized_limit,),
    ).fetchall()
    items = [dict(row) for row in rows]
    total_row = get_db().execute("SELECT COUNT(*) AS total FROM class_user_status_history").fetchone()
    return {
        "items": items,
        "total": int((total_row or {}).get("total") or 0),
        "limit": normalized_limit,
    }


def migrate_class_user_status_from_contact_tags() -> dict[str, Any]:
    rows = get_db().execute(
        """
        SELECT
            ct.external_userid,
            COALESCE(ct.userid, '') AS tag_userid,
            COALESCE(ct.tag_id, '') AS tag_id,
            COALESCE(ct.tag_name, '') AS tag_name,
            ct.created_at AS tag_created_at,
            COALESCE(c.customer_name, '') AS customer_name,
            COALESCE(c.owner_userid, '') AS owner_userid,
            COALESCE(p.mobile, '') AS mobile
        FROM contact_tags ct
        INNER JOIN signup_tag_rules signup_rules
          ON signup_rules.tag_id = ct.tag_id
         AND signup_rules.active = ?
        LEFT JOIN contacts c
          ON c.external_userid = ct.external_userid
        LEFT JOIN external_contact_bindings bindings
          ON bindings.external_userid = ct.external_userid
        LEFT JOIN people p
          ON p.id = bindings.person_id
        ORDER BY ct.created_at DESC, ct.id DESC
        """,
        (True if get_db_backend() == "postgres" else 1,),
    ).fetchall()
    by_external: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        external_userid = str(row.get("external_userid") or "").strip()
        if not external_userid:
            continue
        by_external.setdefault(external_userid, []).append(dict(row))

    migrated = 0
    for external_userid, candidates in by_external.items():
        candidates.sort(
            key=lambda item: (
                str(item.get("tag_created_at") or ""),
                str(item.get("tag_id") or ""),
            ),
            reverse=True,
        )
        chosen = candidates[0]
        signup_status = str(get_signup_status_definition_by_tag_name(str(chosen.get("tag_name") or "").strip()).get("signup_status") if get_signup_status_definition_by_tag_name(str(chosen.get("tag_name") or "").strip()) else "").strip()
        definition = get_class_user_status_definition(signup_status)
        if not definition:
            continue
        existing = get_class_user_status_current(external_userid) or {}
        customer_name = str(chosen.get("customer_name") or "").strip()
        owner_userid = str(chosen.get("tag_userid") or "").strip() or str(chosen.get("owner_userid") or "").strip()
        mobile = str(chosen.get("mobile") or "").strip()
        upsert_class_user_status_current(
            external_userid=external_userid,
            signup_status=signup_status,
            signup_label_name=definition["label"],
            customer_name_snapshot=customer_name,
            owner_userid_snapshot=owner_userid,
            mobile_snapshot=mobile,
            set_by_userid=owner_userid,
            set_at=str(chosen.get("tag_created_at") or "").strip(),
            wecom_tag_sync_status="migrated",
            wecom_tag_sync_error="",
        )
        append_class_user_status_history(
            external_userid=external_userid,
            old_signup_status=str(existing.get("signup_status") or "").strip(),
            new_signup_status=signup_status,
            old_label_name=str(existing.get("signup_label_name") or "").strip(),
            new_label_name=definition["label"],
            customer_name_snapshot=customer_name,
            owner_userid_snapshot=owner_userid,
            mobile_snapshot=mobile,
            set_by_userid=owner_userid,
            set_at=str(chosen.get("tag_created_at") or "").strip(),
            wecom_tag_sync_status="migrated",
            wecom_tag_sync_error="",
        )
        migrated += 1
    return {"migrated_count": migrated}


def apply_class_user_status_change(
    *,
    external_userid: str,
    signup_status: str,
    set_by_userid: str,
    customer_name_snapshot: str,
    owner_userid_snapshot: str,
    mobile_snapshot: str,
) -> dict[str, Any]:
    definition = get_class_user_status_definition(signup_status)
    if not definition:
        raise ValueError("signup_status is invalid")
    existing = get_class_user_status_current(external_userid) or {}
    upsert_class_user_status_current(
        external_userid=external_userid,
        signup_status=signup_status,
        signup_label_name=definition["label"],
        customer_name_snapshot=customer_name_snapshot,
        owner_userid_snapshot=owner_userid_snapshot,
        mobile_snapshot=mobile_snapshot,
        set_by_userid=set_by_userid,
        wecom_tag_sync_status="pending",
        wecom_tag_sync_error="",
    )
    append_class_user_status_history(
        external_userid=external_userid,
        old_signup_status=str(existing.get("signup_status") or "").strip(),
        new_signup_status=signup_status,
        old_label_name=str(existing.get("signup_label_name") or "").strip(),
        new_label_name=definition["label"],
        customer_name_snapshot=customer_name_snapshot,
        owner_userid_snapshot=owner_userid_snapshot,
        mobile_snapshot=mobile_snapshot,
        set_by_userid=set_by_userid,
        wecom_tag_sync_status="pending",
        wecom_tag_sync_error="",
    )
    return get_class_user_status_current(external_userid) or {}


def update_contact_description_snapshot(external_userid: str, description: str) -> None:
    get_db().execute(
        """
        UPDATE contacts
        SET description = ?, updated_at = CURRENT_TIMESTAMP
        WHERE external_userid = ?
        """,
        (description, external_userid),
    )
    get_db().commit()


def count_contacts() -> int:
    row = get_db().execute("SELECT COUNT(*) AS total FROM contacts").fetchone()
    return int(row["total"]) if row else 0


def get_last_contacts_sync_time() -> str:
    row = get_db().execute("SELECT MAX(updated_at) AS updated_at FROM contacts").fetchone()
    return row["updated_at"] if row and row["updated_at"] else ""


def normalize_external_contact_identity(
    corp_id: str,
    payload: dict[str, Any],
    *,
    follow_user_userid: str = "",
    status: str = "active",
) -> dict[str, Any]:
    external_contact = payload.get("external_contact") or payload
    follow_users = payload.get("follow_user") or []
    matched_follow_user = {}
    if follow_user_userid:
        matched_follow_user = next((item for item in follow_users if item.get("userid") == follow_user_userid), {}) or {}
    if not matched_follow_user and follow_users:
        matched_follow_user = follow_users[0]
    external_userid = external_contact.get("external_userid", "")
    return {
        "corp_id": corp_id,
        "external_userid": external_userid,
        "unionid": external_contact.get("unionid", "") or "",
        "openid": external_contact.get("openid", "") or "",
        "follow_user_userid": matched_follow_user.get("userid", "") or follow_user_userid or "",
        "name": external_contact.get("name", "") or "",
        "type": external_contact.get("type"),
        "avatar": external_contact.get("avatar", "") or "",
        "gender": external_contact.get("gender"),
        "status": status,
        "raw_profile": json.dumps(payload, ensure_ascii=False),
    }


def replace_external_contact_follow_users(
    corp_id: str,
    external_userid: str,
    follow_users: list[dict[str, Any]],
    *,
    preferred_userid: str = "",
) -> None:
    if not corp_id or not external_userid:
        return
    db = get_db()
    normalized_follow_users = [item for item in (follow_users or []) if item.get("userid")]
    preferred_found = any(item.get("userid") == preferred_userid for item in normalized_follow_users)
    existing_primary = db.execute(
        """
        SELECT user_id
        FROM wecom_external_contact_follow_users
        WHERE corp_id = ? AND external_userid = ? AND is_primary = TRUE
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (corp_id, external_userid),
    ).fetchone()
    existing_primary_userid = existing_primary["user_id"] if existing_primary else ""
    existing_primary_found = any(item.get("userid") == existing_primary_userid for item in normalized_follow_users)
    if preferred_found:
        primary_userid = preferred_userid
    elif existing_primary_found:
        primary_userid = existing_primary_userid
    else:
        primary_userid = normalized_follow_users[0].get("userid", "") if normalized_follow_users else ""

    db.execute(
        """
        UPDATE wecom_external_contact_follow_users
        SET relation_status = 'inactive',
            is_primary = FALSE,
            updated_at = CURRENT_TIMESTAMP
        WHERE corp_id = ? AND external_userid = ?
        """,
        (corp_id, external_userid),
    )

    for item in normalized_follow_users:
        user_id = item.get("userid", "")
        db.execute(
            """
            INSERT INTO wecom_external_contact_follow_users (
                corp_id, external_userid, user_id, relation_status, is_primary, remark, description,
                add_way, state, oper_userid, createtime, raw_follow_user, first_seen_at, last_seen_at, created_at, updated_at
            )
            VALUES (?, ?, ?, 'active', ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(corp_id, external_userid, user_id) DO UPDATE SET
                relation_status = 'active',
                is_primary = excluded.is_primary,
                remark = excluded.remark,
                description = excluded.description,
                add_way = excluded.add_way,
                state = excluded.state,
                oper_userid = excluded.oper_userid,
                createtime = excluded.createtime,
                raw_follow_user = excluded.raw_follow_user,
                last_seen_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                corp_id,
                external_userid,
                user_id,
                user_id == primary_userid,
                item.get("remark", "") or "",
                item.get("description", "") or "",
                item.get("add_way"),
                item.get("state", "") or "",
                item.get("oper_userid", "") or "",
                item.get("createtime"),
                json.dumps(item, ensure_ascii=False),
            ),
        )
    db.commit()


def mark_external_contact_follow_user_status(
    corp_id: str,
    external_userid: str,
    *,
    user_id: str = "",
    status: str,
) -> None:
    db = get_db()
    if user_id:
        db.execute(
            """
            UPDATE wecom_external_contact_follow_users
            SET relation_status = ?,
                is_primary = FALSE,
                last_seen_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE corp_id = ? AND external_userid = ? AND user_id = ?
            """,
            (status, corp_id, external_userid, user_id),
        )
    else:
        db.execute(
            """
            UPDATE wecom_external_contact_follow_users
            SET relation_status = ?,
                is_primary = FALSE,
                last_seen_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE corp_id = ? AND external_userid = ?
            """,
            (status, corp_id, external_userid),
        )
    db.commit()


def refresh_external_contact_identity_owner(corp_id: str, external_userid: str) -> None:
    db = get_db()
    active_primary = db.execute(
        """
        SELECT user_id
        FROM wecom_external_contact_follow_users
        WHERE corp_id = ? AND external_userid = ? AND relation_status = 'active'
        ORDER BY is_primary DESC, updated_at DESC, id DESC
        LIMIT 1
        """,
        (corp_id, external_userid),
    ).fetchone()
    next_owner = active_primary["user_id"] if active_primary else ""
    next_status = "active" if next_owner else "inactive"
    db.execute(
        """
        UPDATE wecom_external_contact_identity_map
        SET follow_user_userid = ?,
            status = ?,
            last_seen_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE corp_id = ? AND external_userid = ?
        """,
        (next_owner, next_status, corp_id, external_userid),
    )
    db.commit()


def upsert_external_contact_identity(record: dict[str, Any]) -> int:
    db = get_db()
    row = db.execute(
        """
        INSERT INTO wecom_external_contact_identity_map (
            corp_id, external_userid, unionid, openid, follow_user_userid, name, type, avatar, gender,
            status, raw_profile, first_seen_at, last_seen_at, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT(corp_id, external_userid) DO UPDATE SET
            unionid = CASE WHEN excluded.unionid <> '' THEN excluded.unionid ELSE wecom_external_contact_identity_map.unionid END,
            openid = CASE WHEN excluded.openid <> '' THEN excluded.openid ELSE wecom_external_contact_identity_map.openid END,
            follow_user_userid = CASE WHEN excluded.follow_user_userid <> '' THEN excluded.follow_user_userid ELSE wecom_external_contact_identity_map.follow_user_userid END,
            name = excluded.name,
            type = excluded.type,
            avatar = excluded.avatar,
            gender = excluded.gender,
            status = excluded.status,
            raw_profile = excluded.raw_profile,
            last_seen_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        RETURNING id
        """,
        (
            record.get("corp_id", ""),
            record.get("external_userid", ""),
            record.get("unionid", ""),
            record.get("openid", ""),
            record.get("follow_user_userid", ""),
            record.get("name", ""),
            record.get("type"),
            record.get("avatar", ""),
            record.get("gender"),
            record.get("status", "active"),
            record.get("raw_profile", "{}"),
        ),
    ).fetchone()
    db.commit()
    return int(row["id"])


def mark_external_contact_identity_status(
    corp_id: str,
    external_userid: str,
    *,
    status: str,
    follow_user_userid: str = "",
) -> None:
    db = get_db()
    db.execute(
        """
        UPDATE wecom_external_contact_identity_map
        SET status = ?,
            follow_user_userid = CASE WHEN ? <> '' THEN ? ELSE follow_user_userid END,
            last_seen_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE corp_id = ? AND external_userid = ?
        """,
        (status, follow_user_userid, follow_user_userid, corp_id, external_userid),
    )
    db.commit()


def count_external_contact_identity_maps() -> int:
    row = get_db().execute("SELECT COUNT(*) AS total FROM wecom_external_contact_identity_map").fetchone()
    return int(row["total"]) if row else 0


def resolve_external_contact_identity(
    corp_id: str,
    *,
    unionid: str = "",
    openid: str = "",
    external_userid: str = "",
) -> dict[str, Any] | None:
    db = get_db()
    if unionid:
        row = db.execute(
            """
            SELECT id AS identity_map_id, external_userid, unionid, openid, follow_user_userid, status
            FROM wecom_external_contact_identity_map
            WHERE corp_id = ? AND unionid = ?
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (corp_id, unionid),
        ).fetchone()
        if row:
            return row
    if openid:
        row = db.execute(
            """
            SELECT id AS identity_map_id, external_userid, unionid, openid, follow_user_userid, status
            FROM wecom_external_contact_identity_map
            WHERE corp_id = ? AND openid = ?
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (corp_id, openid),
        ).fetchone()
        if row:
            return row
    if external_userid:
        return db.execute(
            """
            SELECT id AS identity_map_id, external_userid, unionid, openid, follow_user_userid, status
            FROM wecom_external_contact_identity_map
            WHERE corp_id = ? AND external_userid = ?
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (corp_id, external_userid),
        ).fetchone()
    return None


def bind_openid_to_external_contact(
    corp_id: str,
    external_userid: str,
    openid: str,
    unionid: str = "",
) -> dict[str, Any] | None:
    target = resolve_external_contact_identity(corp_id, external_userid=external_userid)
    if not target:
        return None
    resolved_by_union = resolve_external_contact_identity(corp_id, unionid=unionid) if unionid else None
    if resolved_by_union and resolved_by_union.get("external_userid") != external_userid:
        return target

    db = get_db()
    current_openid = target.get("openid", "") or ""
    current_unionid = target.get("unionid", "") or ""
    next_openid = current_openid or (openid or "")
    next_unionid = current_unionid or (unionid or "")
    if next_openid == current_openid and next_unionid == current_unionid:
        return resolve_external_contact_identity(corp_id, external_userid=external_userid)

    db.execute(
        """
        UPDATE wecom_external_contact_identity_map
        SET openid = ?,
            unionid = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE corp_id = ? AND external_userid = ?
        """,
        (next_openid, next_unionid, corp_id, external_userid),
    )
    db.commit()
    return resolve_external_contact_identity(corp_id, external_userid=external_userid)


def _normalize_mobile(value: str) -> str:
    digits = re.sub(r"\D+", "", str(value or "").strip())
    if digits.startswith("86") and len(digits) == 13:
        digits = digits[2:]
    if not re.fullmatch(r"1\d{10}", digits):
        raise ValueError("mobile must be a valid mainland China mobile number")
    return digits


def _extract_third_party_user_id(payload: Any) -> str:
    if isinstance(payload, dict):
        for key in ("third_party_user_id", "user_id", "id"):
            value = str(payload.get(key) or "").strip()
            if value:
                return value
        for key in ("data", "result", "user", "person"):
            value = _extract_third_party_user_id(payload.get(key))
            if value:
                return value
    elif isinstance(payload, list):
        for item in payload:
            value = _extract_third_party_user_id(item)
            if value:
                return value
    return ""


def _resolve_third_party_user_id_by_mobile(mobile: str) -> str:
    existing = current_app.config.get("SIDEBAR_THIRD_PARTY_RESOLVER")
    if callable(existing):
        resolved = str(existing(mobile) or "").strip()
        if resolved:
            return resolved

    api_url = str(current_app.config.get("SIDEBAR_THIRD_PARTY_API_URL", "") or "").strip()
    api_token = str(current_app.config.get("SIDEBAR_THIRD_PARTY_API_TOKEN", "") or "").strip()
    timeout = int(current_app.config.get("SIDEBAR_THIRD_PARTY_TIMEOUT_SECONDS", 10))
    if api_url:
        headers = {"Content-Type": "application/json"}
        if api_token:
            headers["Authorization"] = f"Bearer {api_token}"
        try:
            response = requests.post(
                api_url,
                json={"mobile": mobile},
                headers=headers,
                timeout=timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise ThirdPartyUserSyncError(f"third-party sync request failed: {exc}") from exc
        except ValueError as exc:
            raise ThirdPartyUserSyncError("third-party sync returned invalid JSON") from exc

        third_party_user_id = _extract_third_party_user_id(payload)
        if third_party_user_id:
            return third_party_user_id
        raise ThirdPartyUserSyncError("third-party sync response missing third_party_user_id")

    if current_app.testing or current_app.config.get("DEBUG"):
        return f"mocktp_{mobile}"

    raise ThirdPartyUserSyncError("third-party resolver is not configured")


def _sidebar_contact_profile(external_userid: str, owner_userid: str = "") -> dict[str, str]:
    normalized_external_userid = str(external_userid or "").strip()
    normalized_owner_userid = str(owner_userid or "").strip()
    if not normalized_external_userid:
        return {
            "customer_name": "",
            "remark": "",
            "display_name": "",
            "owner_userid": normalized_owner_userid,
        }

    db = get_db()
    contact = db.execute(
        """
        SELECT external_userid, COALESCE(customer_name, '') AS customer_name, COALESCE(owner_userid, '') AS owner_userid,
               COALESCE(remark, '') AS remark
        FROM contacts
        WHERE external_userid = ?
        LIMIT 1
        """,
        (normalized_external_userid,),
    ).fetchone()
    if contact:
        fallback_owner_userid = str(contact.get("owner_userid") or "").strip()
        customer_name = str(contact.get("customer_name") or "").strip()
        remark = str(contact.get("remark") or "").strip()
    else:
        fallback_owner_userid = ""
        customer_name = ""
        remark = ""

    if not remark:
        follow_user = None
        if normalized_owner_userid:
            follow_user = db.execute(
                """
                SELECT COALESCE(remark, '') AS remark
                FROM wecom_external_contact_follow_users
                WHERE corp_id = ? AND external_userid = ? AND user_id = ?
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                (current_app.config.get("WECOM_CORP_ID", ""), normalized_external_userid, normalized_owner_userid),
            ).fetchone()
        if not follow_user:
            follow_user = db.execute(
                """
                SELECT COALESCE(remark, '') AS remark
                FROM wecom_external_contact_follow_users
                WHERE corp_id = ? AND external_userid = ?
                ORDER BY is_primary DESC, updated_at DESC, id DESC
                LIMIT 1
                """,
                (current_app.config.get("WECOM_CORP_ID", ""), normalized_external_userid),
            ).fetchone()
        remark = str((follow_user or {}).get("remark") or "").strip()

    display_name = customer_name or remark
    if not display_name:
        suffix = normalized_external_userid[-6:] if len(normalized_external_userid) > 6 else normalized_external_userid
        display_name = f"客户 {suffix}" if suffix else "当前客户"

    return {
        "customer_name": customer_name,
        "remark": remark,
        "display_name": display_name,
        "owner_userid": normalized_owner_userid or fallback_owner_userid,
    }


def _resolve_binding_owner_userid(external_userid: str, owner_userid: str = "") -> str:
    profile = _sidebar_contact_profile(external_userid, owner_userid)
    resolved_owner_userid = str(profile.get("owner_userid") or "").strip()
    if resolved_owner_userid:
        return resolved_owner_userid
    row = get_db().execute(
        """
        SELECT COALESCE(follow_user_userid, '') AS follow_user_userid
        FROM wecom_external_contact_identity_map
        WHERE corp_id = ? AND external_userid = ?
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (current_app.config.get("WECOM_CORP_ID", ""), str(external_userid or "").strip()),
    ).fetchone()
    return str((row or {}).get("follow_user_userid") or "").strip()


def resolve_person_identity(*, external_userid: str = "", mobile: str = "") -> dict[str, Any]:
    """
    people is the system's canonical person table:
    - people.id is the internal person_id
    - people.mobile is the canonical primary mobile

    Other tables only provide bindings, WeCom identity details, or CRM snapshots.
    This resolver unifies those sources so callers can resolve one person by either
    external_userid or mobile without redefining the underlying schema.
    """
    normalized_external_userid = str(external_userid or "").strip()
    normalized_mobile = str(mobile or "").strip()
    if not normalized_external_userid and not normalized_mobile:
        raise ValueError("external_userid or mobile is required")

    db = get_db()
    row = None
    if normalized_external_userid:
        row = db.execute(
            """
            SELECT
                p.id AS person_id,
                p.mobile,
                b.external_userid,
                b.first_bound_by_userid,
                b.first_owner_userid,
                b.last_owner_userid,
                c.customer_name,
                c.owner_userid,
                c.remark,
                m.unionid,
                m.openid,
                m.follow_user_userid
            FROM external_contact_bindings b
            LEFT JOIN people p ON p.id = b.person_id
            LEFT JOIN contacts c ON c.external_userid = b.external_userid
            LEFT JOIN wecom_external_contact_identity_map m
              ON m.corp_id = ? AND m.external_userid = b.external_userid
            WHERE b.external_userid = ?
            ORDER BY m.updated_at DESC NULLS LAST, m.id DESC NULLS LAST
            LIMIT 1
            """,
            (current_app.config.get("WECOM_CORP_ID", ""), normalized_external_userid),
        ).fetchone()
        if not row:
            row = db.execute(
                """
                SELECT
                    NULL AS person_id,
                    '' AS mobile,
                    c.external_userid,
                    '' AS first_bound_by_userid,
                    '' AS first_owner_userid,
                    '' AS last_owner_userid,
                    c.customer_name,
                    c.owner_userid,
                    c.remark,
                    COALESCE(m.unionid, '') AS unionid,
                    COALESCE(m.openid, '') AS openid,
                    COALESCE(m.follow_user_userid, '') AS follow_user_userid
                FROM contacts c
                LEFT JOIN wecom_external_contact_identity_map m
                  ON m.corp_id = ? AND m.external_userid = c.external_userid
                WHERE c.external_userid = ?
                ORDER BY m.updated_at DESC NULLS LAST, m.id DESC NULLS LAST
                LIMIT 1
                """,
                (current_app.config.get("WECOM_CORP_ID", ""), normalized_external_userid),
            ).fetchone()
        if not row:
            row = db.execute(
                """
                SELECT
                    NULL AS person_id,
                    '' AS mobile,
                    external_userid,
                    '' AS first_bound_by_userid,
                    '' AS first_owner_userid,
                    '' AS last_owner_userid,
                    name AS customer_name,
                    '' AS owner_userid,
                    '' AS remark,
                    COALESCE(unionid, '') AS unionid,
                    COALESCE(openid, '') AS openid,
                    COALESCE(follow_user_userid, '') AS follow_user_userid
                FROM wecom_external_contact_identity_map
                WHERE corp_id = ? AND external_userid = ?
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                (current_app.config.get("WECOM_CORP_ID", ""), normalized_external_userid),
            ).fetchone()
    else:
        row = db.execute(
            """
            SELECT
                p.id AS person_id,
                p.mobile,
                COALESCE(b.external_userid, '') AS external_userid,
                COALESCE(b.first_bound_by_userid, '') AS first_bound_by_userid,
                COALESCE(b.first_owner_userid, '') AS first_owner_userid,
                COALESCE(b.last_owner_userid, '') AS last_owner_userid,
                COALESCE(c.customer_name, '') AS customer_name,
                COALESCE(c.owner_userid, '') AS owner_userid,
                COALESCE(c.remark, '') AS remark,
                COALESCE(m.unionid, '') AS unionid,
                COALESCE(m.openid, '') AS openid,
                COALESCE(m.follow_user_userid, '') AS follow_user_userid
            FROM people p
            LEFT JOIN external_contact_bindings b ON b.person_id = p.id
            LEFT JOIN contacts c ON c.external_userid = b.external_userid
            LEFT JOIN wecom_external_contact_identity_map m
              ON m.corp_id = ? AND m.external_userid = b.external_userid
            WHERE p.mobile = ?
            ORDER BY b.updated_at DESC NULLS LAST, m.updated_at DESC NULLS LAST, b.external_userid ASC
            LIMIT 1
            """,
            (current_app.config.get("WECOM_CORP_ID", ""), normalized_mobile),
        ).fetchone()

    if not row:
        return {
            "person_id": None,
            "mobile": normalized_mobile,
            "external_userid": normalized_external_userid,
            "customer_name": "",
            "owner_userid": "",
            "remark": "",
            "unionid": "",
            "openid": "",
            "follow_user_userid": "",
            "signup_status": "",
            "is_bound": False,
        }

    resolved_external_userid = str(row.get("external_userid") or "").strip()
    resolved_owner_userid = (
        str(row.get("owner_userid") or "").strip()
        or str(row.get("last_owner_userid") or "").strip()
        or str(row.get("first_owner_userid") or "").strip()
        or str(row.get("follow_user_userid") or "").strip()
    )
    signup_status = ""
    if resolved_external_userid:
        signup_status = enrich_contact_context(
            {
                "external_userid": resolved_external_userid,
                "owner_userid": resolved_owner_userid,
            }
        ).get("signup_status", "")

    return {
        "person_id": int(row["person_id"]) if row.get("person_id") is not None else None,
        "mobile": str(row.get("mobile") or "").strip(),
        "external_userid": resolved_external_userid,
        "customer_name": str(row.get("customer_name") or "").strip(),
        "owner_userid": resolved_owner_userid,
        "remark": str(row.get("remark") or "").strip(),
        "unionid": str(row.get("unionid") or "").strip(),
        "openid": str(row.get("openid") or "").strip(),
        "follow_user_userid": str(row.get("follow_user_userid") or "").strip(),
        "signup_status": signup_status,
        "is_bound": bool(row.get("person_id") is not None and resolved_external_userid),
    }


def get_contact_binding_status(external_userid: str, owner_userid: str = "") -> dict[str, Any]:
    normalized_external_userid = str(external_userid or "").strip()
    normalized_owner_userid = str(owner_userid or "").strip()
    profile = _sidebar_contact_profile(normalized_external_userid, normalized_owner_userid)
    row = get_db().execute(
        """
        SELECT
            b.external_userid,
            b.person_id,
            b.first_bound_by_userid,
            b.first_owner_userid,
            b.last_owner_userid,
            b.created_at,
            b.updated_at,
            p.mobile,
            p.third_party_user_id
        FROM external_contact_bindings b
        JOIN people p ON p.id = b.person_id
        WHERE b.external_userid = ?
        """,
        (normalized_external_userid,),
    ).fetchone()
    if not row:
        return {
            "is_bound": False,
            "external_userid": normalized_external_userid,
            "owner_userid": profile.get("owner_userid", ""),
            "customer_name": profile.get("customer_name", ""),
            "remark": profile.get("remark", ""),
            "display_name": profile.get("display_name", ""),
        }
    return {
        "is_bound": True,
        "person_id": int(row["person_id"]),
        "external_userid": row["external_userid"],
        "owner_userid": profile.get("owner_userid", "") or row.get("last_owner_userid") or row.get("first_owner_userid") or "",
        "customer_name": profile.get("customer_name", ""),
        "remark": profile.get("remark", ""),
        "display_name": profile.get("display_name", ""),
        "mobile": row["mobile"],
        "third_party_user_id": row.get("third_party_user_id") or "",
        "first_bound_by_userid": row.get("first_bound_by_userid") or "",
        "first_owner_userid": row.get("first_owner_userid") or "",
        "last_owner_userid": row.get("last_owner_userid") or "",
        "created_at": row.get("created_at") or "",
        "updated_at": row.get("updated_at") or "",
    }


def bind_mobile_to_external_contact(
    *,
    external_userid: str,
    owner_userid: str,
    bind_by_userid: str,
    mobile: str,
    force_rebind: bool = False,
) -> dict[str, Any]:
    normalized_external_userid = str(external_userid or "").strip()
    normalized_owner_userid = _resolve_binding_owner_userid(normalized_external_userid, owner_userid)
    normalized_bind_by_userid = str(bind_by_userid or "").strip() or normalized_owner_userid
    if not normalized_external_userid:
        raise ValueError("external_userid is required")
    if not normalized_bind_by_userid:
        normalized_bind_by_userid = "sidebar_bind"
    normalized_mobile = _normalize_mobile(mobile)

    db = get_db()
    existing = get_contact_binding_status(normalized_external_userid, normalized_owner_userid)
    if existing.get("is_bound"):
        if existing.get("mobile") != normalized_mobile and not force_rebind:
            raise ContactBindingConflictError("external_userid already bound to another mobile")
        if existing.get("mobile") == normalized_mobile:
            return existing

    try:
        person = db.execute(
            """
            SELECT id, mobile, third_party_user_id
            FROM people
            WHERE mobile = ?
            ORDER BY id ASC
            LIMIT 1
            """,
            (normalized_mobile,),
        ).fetchone()
        if person:
            person_id = int(person["id"])
            existing_third_party_user_id = str(person.get("third_party_user_id") or "").strip()
        else:
            created = db.execute(
                """
                INSERT INTO people (mobile, third_party_user_id, created_at, updated_at)
                VALUES (?, '', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                RETURNING id
                """,
                (normalized_mobile,),
            ).fetchone()
            person_id = int(created["id"])
            existing_third_party_user_id = ""

        if existing.get("is_bound") and force_rebind:
            db.execute(
                """
                UPDATE external_contact_bindings
                SET person_id = ?,
                    last_owner_userid = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE external_userid = ?
                """,
                (
                    person_id,
                    normalized_owner_userid,
                    normalized_external_userid,
                ),
            )
        else:
            db.execute(
                """
                INSERT INTO external_contact_bindings (
                    external_userid,
                    person_id,
                    first_bound_by_userid,
                    first_owner_userid,
                    last_owner_userid,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (
                    normalized_external_userid,
                    person_id,
                    normalized_bind_by_userid,
                    normalized_owner_userid,
                    normalized_owner_userid,
                ),
            )
        db.commit()
    except Exception:
        db.rollback()
        raise

    third_party_sync_error = ""
    if not existing_third_party_user_id:
        try:
            third_party_user_id = _resolve_third_party_user_id_by_mobile(normalized_mobile)
            db.execute(
                """
                UPDATE people
                SET third_party_user_id = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (third_party_user_id, person_id),
            )
            db.commit()
        except ThirdPartyUserSyncError as exc:
            db.rollback()
            third_party_sync_error = str(exc)

    result = get_contact_binding_status(normalized_external_userid, normalized_owner_userid)
    if third_party_sync_error:
        result["third_party_sync_status"] = "pending"
        result["third_party_sync_error"] = third_party_sync_error
    else:
        result["third_party_sync_status"] = "success" if result.get("third_party_user_id") else "empty"
    return result


def log_external_contact_event(
    *,
    corp_id: str,
    event_type: str,
    change_type: str,
    external_userid: str,
    user_id: str,
    event_time: int,
    event_key: str,
    payload_xml: str,
    payload_json: dict[str, Any],
) -> dict[str, Any]:
    db = get_db()
    existing = db.execute(
        """
        SELECT id, process_status, retry_count
        FROM wecom_external_contact_event_logs
        WHERE event_key = ?
        """,
        (event_key,),
    ).fetchone()
    if existing:
        db.execute(
            """
            UPDATE wecom_external_contact_event_logs
            SET updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (existing["id"],),
        )
        db.commit()
        return {
            "id": int(existing["id"]),
            "process_status": existing.get("process_status", ""),
            "retry_count": int(existing.get("retry_count") or 0),
            "is_duplicate": True,
        }

    row = db.execute(
        """
        INSERT INTO wecom_external_contact_event_logs (
            corp_id, event_type, change_type, external_userid, user_id, event_time,
            event_key, payload_xml, payload_json, process_status, retry_count, error_message
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', 0, '')
        RETURNING id, process_status, retry_count
        """,
        (
            corp_id,
            event_type,
            change_type,
            external_userid,
            user_id,
            event_time,
            event_key,
            payload_xml,
            json.dumps(payload_json, ensure_ascii=False),
        ),
    ).fetchone()
    db.commit()
    return {
        "id": int(row["id"]),
        "process_status": row.get("process_status", "pending"),
        "retry_count": int(row.get("retry_count") or 0),
        "is_duplicate": False,
    }


def mark_external_contact_event_processing(event_log_id: int) -> dict[str, Any] | None:
    db = get_db()
    db.execute(
        """
        UPDATE wecom_external_contact_event_logs
        SET process_status = 'processing',
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (event_log_id,),
    )
    db.commit()
    return db.execute(
        """
        SELECT *
        FROM wecom_external_contact_event_logs
        WHERE id = ?
        """,
        (event_log_id,),
    ).fetchone()


def get_external_contact_event_log(event_log_id: int) -> dict[str, Any] | None:
    return get_db().execute(
        """
        SELECT *
        FROM wecom_external_contact_event_logs
        WHERE id = ?
        """,
        (event_log_id,),
    ).fetchone()


def finish_external_contact_event_log(
    event_log_id: int,
    *,
    status: str,
    error_message: str = "",
    increment_retry: bool = False,
) -> None:
    db = get_db()
    retry_expr = "retry_count + 1" if increment_retry else "retry_count"
    db.execute(
        f"""
        UPDATE wecom_external_contact_event_logs
        SET process_status = ?,
            error_message = ?,
            retry_count = {retry_expr},
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (status, error_message, event_log_id),
    )
    db.commit()


def get_recent_external_contact_event_logs(limit: int = 20) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 200))
    rows = get_db().execute(
        """
        SELECT id, corp_id, event_type, change_type, external_userid, user_id, event_time,
               event_key, process_status, retry_count, error_message, created_at, updated_at
        FROM wecom_external_contact_event_logs
        ORDER BY id DESC
        LIMIT ?
        """,
        (safe_limit,),
    ).fetchall()
    return list(rows)


def normalize_group_chat_record(payload: dict[str, Any], owner_userid: str | None = None, status: str = "active") -> dict[str, Any]:
    group_chat = payload.get("group_chat") or payload
    member_list = group_chat.get("member_list") or []
    manager_list = group_chat.get("admin_list") or []
    derived_owner = owner_userid or group_chat.get("owner") or (manager_list[0] if manager_list else "")
    return {
        "chat_id": group_chat.get("chat_id", ""),
        "group_name": group_chat.get("name", ""),
        "owner_userid": derived_owner or "",
        "notice": group_chat.get("notice", "") or "",
        "member_count": len(member_list),
        "status": status,
        "create_time": _normalize_optional_timestamp(group_chat.get("create_time")) if group_chat.get("create_time") else "",
        "dismissed_at": _normalize_optional_timestamp(group_chat.get("dismiss_time")) if group_chat.get("dismiss_time") else "",
        "raw_payload": json.dumps(payload, ensure_ascii=False),
    }


def upsert_group_chats(group_chats: list[dict[str, Any]]) -> tuple[int, int]:
    db = get_db()
    inserted = 0
    updated = 0
    for item in group_chats:
        chat_id = item.get("chat_id", "")
        if not chat_id:
            continue
        existing = db.execute(
            """
            SELECT group_name, owner_userid, notice, member_count, status, create_time, dismissed_at, raw_payload
            FROM group_chats
            WHERE chat_id = ?
            """,
            (chat_id,),
        ).fetchone()
        db.execute(
            """
            INSERT INTO group_chats (
                chat_id, group_name, owner_userid, notice, member_count, status,
                create_time, dismissed_at, raw_payload, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(chat_id) DO UPDATE SET
                group_name = excluded.group_name,
                owner_userid = excluded.owner_userid,
                notice = excluded.notice,
                member_count = excluded.member_count,
                status = excluded.status,
                create_time = excluded.create_time,
                dismissed_at = excluded.dismissed_at,
                raw_payload = excluded.raw_payload,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                chat_id,
                item.get("group_name", ""),
                item.get("owner_userid", ""),
                item.get("notice", ""),
                int(item.get("member_count", 0)),
                item.get("status", "active"),
                item.get("create_time", ""),
                item.get("dismissed_at", ""),
                item.get("raw_payload", "{}"),
            ),
        )
        if existing is None:
            inserted += 1
        elif any(
            [
                existing.get("group_name") != item.get("group_name", ""),
                existing.get("owner_userid") != item.get("owner_userid", ""),
                existing.get("notice") != item.get("notice", ""),
                int(existing.get("member_count") or 0) != int(item.get("member_count", 0)),
                existing.get("status") != item.get("status", "active"),
                existing.get("create_time") != item.get("create_time", ""),
                existing.get("dismissed_at") != item.get("dismissed_at", ""),
                existing.get("raw_payload") != item.get("raw_payload", "{}"),
            ]
        ):
            updated += 1
    db.commit()
    return inserted, updated


def get_group_chat_by_chat_id(chat_id: str) -> dict[str, Any] | None:
    return get_db().execute(
        """
        SELECT chat_id, group_name, owner_userid, notice, member_count, status, create_time, dismissed_at, raw_payload, updated_at
        FROM group_chats
        WHERE chat_id = ?
        """,
        (chat_id,),
    ).fetchone()


def get_group_chat_map(chat_ids: list[str]) -> dict[str, dict[str, Any]]:
    unique_ids = [chat_id for chat_id in dict.fromkeys(chat_ids) if chat_id]
    if not unique_ids:
        return {}
    placeholders = ",".join("?" for _ in unique_ids)
    rows = get_db().execute(
        f"""
        SELECT chat_id, group_name, owner_userid, notice, member_count, status, create_time, dismissed_at, raw_payload, updated_at
        FROM group_chats
        WHERE chat_id IN ({placeholders})
        """,
        tuple(unique_ids),
    ).fetchall()
    return {row["chat_id"]: row for row in rows}


def list_group_chats(status: str | None = None) -> list[dict[str, Any]]:
    sql = """
        SELECT chat_id, group_name, owner_userid, notice, member_count, status, create_time, dismissed_at, raw_payload, updated_at
        FROM group_chats
    """
    params: list[Any] = []
    if status:
        sql += " WHERE status = ?"
        params.append(status)
    sql += " ORDER BY updated_at DESC, id DESC"
    return get_db().execute(sql, tuple(params)).fetchall()


def count_group_chats() -> int:
    row = get_db().execute("SELECT COUNT(*) AS total FROM group_chats").fetchone()
    return int(row["total"]) if row else 0


def count_archived_messages() -> int:
    row = get_db().execute("SELECT COUNT(*) AS total FROM archived_messages").fetchone()
    return int(row["total"]) if row else 0


def normalize_archived_message(item: dict[str, Any]) -> dict[str, Any]:
    if "raw_payload" in item and "sender" in item and "receiver" in item and "external_userid" in item:
        return {
            "seq": item.get("seq"),
            "msgid": item["msgid"],
            "chat_type": item.get("chat_type", "private"),
            "external_userid": item["external_userid"],
            "owner_userid": item["owner_userid"],
            "sender": item["sender"],
            "receiver": item["receiver"],
            "msgtype": item["msgtype"],
            "content": item["content"],
            "send_time": item["send_time"],
            "raw_payload": item["raw_payload"],
        }

    msgtype = item.get("msgtype", "text")
    content = (item.get("text") or {}).get("content") or item.get("content") or ""
    from_type = item.get("from_type", "")
    from_userid = item.get("from_userid", "")
    external_userid = item.get("external_userid") or (from_userid if from_type == "external" else "")
    owner_userid = item.get("owner_userid", "")
    sender = from_userid or owner_userid
    receiver = owner_userid if from_type == "external" else external_userid

    return {
        "seq": item.get("seq"),
        "msgid": item["msgid"],
        "chat_type": item.get("chat_type", "private"),
        "external_userid": external_userid,
        "owner_userid": owner_userid,
        "sender": sender,
        "receiver": receiver,
        "msgtype": msgtype,
        "content": content,
        "send_time": item["send_time"],
        "raw_payload": json.dumps(item, ensure_ascii=False),
    }


def format_message_row(row: dict[str, Any], group_map: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    raw_payload = row.get("raw_payload")
    decrypted_message = {}
    if raw_payload:
        try:
            payload = json.loads(raw_payload)
            decrypted_message = payload.get("decrypted_message") or {}
        except (TypeError, json.JSONDecodeError):
            decrypted_message = {}

    tolist = decrypted_message.get("tolist") or []
    if isinstance(tolist, str):
        tolist = [tolist]
    chat_id = decrypted_message.get("roomid", "") or ""
    group_info = (group_map or {}).get(chat_id) or {}

    return {
        "seq": row["seq"],
        "msgid": row["msgid"],
        "chat_type": row.get("chat_type") or ("group" if decrypted_message.get("roomid") else ("private" if len(tolist) == 1 else "group")),
        "external_userid": row["external_userid"],
        "owner_userid": row["owner_userid"],
        "sender": row["sender"],
        "from": decrypted_message.get("from") or row["sender"],
        "tolist": tolist,
        "roomid": chat_id,
        "chat_id": chat_id,
        "group_name": group_info.get("group_name", ""),
        "msgtype": row["msgtype"],
        "content": row["content"],
        "send_time": row["send_time"],
    }


def extract_roomid_from_raw_payload(raw_payload: str | None) -> str:
    if not raw_payload:
        return ""
    try:
        payload = json.loads(raw_payload)
    except (TypeError, json.JSONDecodeError):
        return ""
    return ((payload.get("decrypted_message") or {}).get("roomid")) or ""


def insert_archived_messages(messages: list[dict[str, Any]]) -> int:
    db = get_db()
    backend = get_db_backend()
    inserted = 0
    for item in messages:
        normalized = normalize_archived_message(item)
        sql = """
            INSERT INTO archived_messages (
                seq, msgid, chat_type, external_userid, owner_userid, sender, receiver,
                msgtype, content, send_time, raw_payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        if backend == "postgres":
            sql += " ON CONFLICT (msgid) DO NOTHING"
        else:
            sql = sql.replace("INSERT INTO", "INSERT OR IGNORE INTO", 1)
        cursor = db.execute(
            sql,
            (
                normalized["seq"],
                normalized["msgid"],
                normalized["chat_type"],
                normalized["external_userid"],
                normalized["owner_userid"],
                normalized["sender"],
                normalized["receiver"],
                normalized["msgtype"],
                normalized["content"],
                normalized["send_time"],
                normalized["raw_payload"],
            ),
        )
        inserted += cursor.rowcount
    db.commit()
    return inserted


def create_sync_run(start_time: str, end_time: str, owner_userid: str, cursor: str) -> int:
    db = get_db()
    cursor_row = db.execute(
        """
        INSERT INTO sync_runs (status, start_time, end_time, owner_userid, cursor)
        VALUES ('running', ?, ?, ?, ?)
        RETURNING id
        """,
        (start_time, end_time, owner_userid, cursor),
    )
    row = cursor_row.fetchone()
    db.commit()
    return int(row["id"])


def finish_sync_run(
    run_id: int,
    status: str,
    fetched_count: int,
    inserted_count: int,
    raw_response: dict[str, Any] | None = None,
    error_message: str | None = None,
) -> None:
    db = get_db()
    db.execute(
        """
        UPDATE sync_runs
        SET status = ?, fetched_count = ?, inserted_count = ?, raw_response = ?,
            error_message = ?, finished_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            status,
            fetched_count,
            inserted_count,
            json.dumps(raw_response, ensure_ascii=False) if raw_response is not None else None,
            error_message,
            run_id,
        ),
    )
    db.commit()


def _normalize_chat_type_filter(chat_type: str | None) -> str | None:
    if not chat_type:
        return None
    value = chat_type.strip().lower()
    if value not in {"private", "group"}:
        raise ValueError("chat_type must be private or group")
    return value


def get_messages_by_user(external_userid: str, chat_type: str | None = None) -> list[dict[str, Any]]:
    normalized_chat_type = _normalize_chat_type_filter(chat_type)
    sql = """
        SELECT seq, msgid, chat_type, external_userid, owner_userid, sender, receiver, msgtype, content, send_time, raw_payload
        FROM archived_messages
        WHERE external_userid = ?
    """
    params: list[Any] = [external_userid]
    if normalized_chat_type:
        sql += " AND chat_type = ?"
        params.append(normalized_chat_type)
    sql += " ORDER BY send_time ASC, id ASC"
    rows = get_db().execute(sql, tuple(params)).fetchall()
    group_map = get_group_chat_map([extract_roomid_from_raw_payload(row.get("raw_payload")) for row in rows])
    return [format_message_row(row, group_map=group_map) for row in rows]


def get_recent_messages_by_user(external_userid: str, limit: int = 20, chat_type: str | None = None) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 200))
    normalized_chat_type = _normalize_chat_type_filter(chat_type)
    sql = """
        SELECT seq, msgid, chat_type, external_userid, owner_userid, sender, receiver, msgtype, content, send_time, raw_payload
        FROM archived_messages
        WHERE external_userid = ?
    """
    params: list[Any] = [external_userid]
    if normalized_chat_type:
        sql += " AND chat_type = ?"
        params.append(normalized_chat_type)
    sql += " ORDER BY send_time DESC, id DESC LIMIT ?"
    params.append(safe_limit)
    rows = get_db().execute(sql, tuple(params)).fetchall()
    group_map = get_group_chat_map([extract_roomid_from_raw_payload(row.get("raw_payload")) for row in rows])
    return [format_message_row(row, group_map=group_map) for row in rows]


def search_messages(external_userid: str, keyword: str) -> list[dict[str, Any]]:
    rows = get_db().execute(
        """
        SELECT seq, msgid, chat_type, external_userid, owner_userid, sender, receiver, msgtype, content, send_time, raw_payload
        FROM archived_messages
        WHERE external_userid = ? AND content LIKE ?
        ORDER BY send_time ASC, id ASC
        """,
        (external_userid, f"%{keyword}%"),
    ).fetchall()
    group_map = get_group_chat_map([extract_roomid_from_raw_payload(row.get("raw_payload")) for row in rows])
    return [format_message_row(row, group_map=group_map) for row in rows]


def list_archived_messages_by_window(
    start_time: str,
    end_time: str,
    owner_userid: str,
    cursor: str = "",
    limit: int = 100,
) -> dict[str, Any]:
    db = get_db()
    offset = int(cursor or "0")
    rows = db.execute(
        """
        SELECT seq, msgid, external_userid, owner_userid, sender, receiver, msgtype, content, send_time, raw_payload
        FROM archived_messages
        WHERE send_time >= ? AND send_time <= ? AND owner_userid = ?
        ORDER BY send_time ASC, id ASC
        LIMIT ? OFFSET ?
        """,
        (start_time, end_time, owner_userid, limit + 1, offset),
    ).fetchall()

    has_more = len(rows) > limit
    page_rows = rows[:limit]
    next_cursor = str(offset + limit) if has_more else ""
    messages = [json.loads(row["raw_payload"]) for row in page_rows]
    return {"messages": messages, "has_more": has_more, "next_cursor": next_cursor}


def save_outbound_task(task_type: str, request_payload: dict[str, Any], response_payload: dict[str, Any]) -> int:
    task_id = (
        response_payload.get("msgid")
        or response_payload.get("jobid")
        or response_payload.get("task_id")
        or response_payload.get("moment_id")
    )
    db = get_db()
    row = db.execute(
        """
        INSERT INTO outbound_tasks (task_type, request_payload, response_payload, wecom_task_id, status)
        VALUES (?, ?, ?, ?, 'created')
        RETURNING id
        """,
        (
            task_type,
            json.dumps(request_payload, ensure_ascii=False),
            json.dumps(response_payload, ensure_ascii=False),
            task_id,
        ),
    )
    result = row.fetchone()
    db.commit()
    return int(result["id"])


def save_tag_snapshot(userid: str, external_userid: str, add_tag_ids: list[str], tag_name_map: dict[str, str] | None = None) -> None:
    db = get_db()
    backend = get_db_backend()
    for tag_id in add_tag_ids:
        sql = """
            INSERT INTO contact_tags (external_userid, userid, tag_id, tag_name)
            VALUES (?, ?, ?, ?)
        """
        if backend == "postgres":
            sql += " ON CONFLICT (external_userid, userid, tag_id) DO NOTHING"
        else:
            sql = sql.replace("INSERT INTO", "INSERT OR IGNORE INTO", 1)
        db.execute(
            sql,
            (external_userid, userid, tag_id, (tag_name_map or {}).get(tag_id)),
        )
    db.commit()


def remove_tag_snapshot(userid: str, external_userid: str, remove_tag_ids: list[str]) -> None:
    db = get_db()
    for tag_id in remove_tag_ids:
        db.execute(
            "DELETE FROM contact_tags WHERE external_userid = ? AND userid = ? AND tag_id = ?",
            (external_userid, userid, tag_id),
        )
    db.commit()


def remove_tag_snapshots_for_other_users(external_userid: str, keep_userids: list[str], scoped_tag_ids: list[str]) -> None:
    normalized_external_userid = str(external_userid or "").strip()
    normalized_keep_userids = [str(item or "").strip() for item in keep_userids if str(item or "").strip()]
    normalized_tag_ids = [str(item or "").strip() for item in scoped_tag_ids if str(item or "").strip()]
    if not normalized_external_userid or not normalized_tag_ids:
        return
    params: list[Any] = [normalized_external_userid, *normalized_tag_ids]
    sql = (
        "DELETE FROM contact_tags WHERE external_userid = ? AND tag_id IN ("
        + ",".join(["?"] * len(normalized_tag_ids))
        + ")"
    )
    if normalized_keep_userids:
        sql += " AND userid NOT IN (" + ",".join(["?"] * len(normalized_keep_userids)) + ")"
        params.extend(normalized_keep_userids)
    db = get_db()
    db.execute(sql, tuple(params))
    db.commit()


def get_archive_last_seq() -> int:
    row = get_db().execute(
        "SELECT last_seq FROM archive_sync_state WHERE state_key = 'global'"
    ).fetchone()
    return int(row["last_seq"]) if row else 0


def set_archive_last_seq(last_seq: int) -> None:
    db = get_db()
    db.execute(
        """
        INSERT INTO archive_sync_state (state_key, last_seq, updated_at)
        VALUES ('global', ?, CURRENT_TIMESTAMP)
        ON CONFLICT(state_key) DO UPDATE SET
            last_seq = excluded.last_seq,
            updated_at = CURRENT_TIMESTAMP
        """,
        (int(last_seq),),
    )
    db.commit()


def get_last_sync_run() -> dict[str, Any] | None:
    return get_db().execute(
        """
        SELECT id, status, owner_userid, fetched_count, inserted_count, error_message, created_at, finished_at
        FROM sync_runs
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()


def _parse_send_time(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


def _batch_window_for_send_time(send_time: str, window_minutes: int = 3) -> tuple[str, str, str]:
    dt = _parse_send_time(send_time)
    floored_minute = (dt.minute // window_minutes) * window_minutes
    window_start_dt = dt.replace(minute=floored_minute, second=0, microsecond=0)
    window_end_dt = window_start_dt + timedelta(minutes=window_minutes) - timedelta(seconds=1)
    window_start = window_start_dt.strftime("%Y-%m-%d %H:%M:%S")
    window_end = window_end_dt.strftime("%Y-%m-%d %H:%M:%S")
    batch_key = f"{window_start}->{window_end}"
    return window_start, window_end, batch_key


def materialize_message_batches(window_minutes: int = 3) -> dict[str, int]:
    db = get_db()
    rows = db.execute(
        """
        SELECT am.id, am.msgid, am.chat_type, am.external_userid, am.owner_userid, am.send_time, am.raw_payload
        FROM archived_messages am
        LEFT JOIN message_batch_items mbi ON mbi.message_id = am.id
        WHERE mbi.message_id IS NULL
        ORDER BY am.send_time ASC, am.id ASC
        """
    ).fetchall()
    if not rows:
        return {"created_batches": 0, "added_items": 0}

    created_batches = 0
    added_items = 0
    batch_cache: dict[str, int] = {}

    for row in rows:
        window_start, window_end, batch_key = _batch_window_for_send_time(row["send_time"], window_minutes=window_minutes)
        batch_id = batch_cache.get(batch_key)
        if batch_id is None:
            existing = db.execute(
                """
                SELECT id FROM message_batches WHERE batch_key = ?
                """,
                (batch_key,),
            ).fetchone()
            if existing:
                batch_id = int(existing["id"])
            else:
                inserted = db.execute(
                    """
                    INSERT INTO message_batches (batch_key, window_start, window_end, status, message_count)
                    VALUES (?, ?, ?, 'pending', 0)
                    RETURNING id
                    """,
                    (batch_key, window_start, window_end),
                ).fetchone()
                batch_id = int(inserted["id"])
                created_batches += 1
            batch_cache[batch_key] = batch_id

        payload = {}
        if row.get("raw_payload"):
            try:
                payload = json.loads(row["raw_payload"])
            except (TypeError, json.JSONDecodeError):
                payload = {}
        chat_id = ((payload.get("decrypted_message") or {}).get("roomid")) or ""
        cursor = db.execute(
            """
            INSERT INTO message_batch_items (
                batch_id, message_id, msgid, chat_type, chat_id, external_userid, owner_userid, send_time
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (message_id) DO NOTHING
            """,
            (
                batch_id,
                row["id"],
                row["msgid"],
                row.get("chat_type", "private"),
                chat_id,
                row.get("external_userid", ""),
                row.get("owner_userid", ""),
                row["send_time"],
            ),
        )
        if cursor.rowcount:
            added_items += 1
            db.execute(
                """
                UPDATE message_batches
                SET message_count = message_count + 1
                WHERE id = ?
                """,
                (batch_id,),
            )

    db.commit()
    return {"created_batches": created_batches, "added_items": added_items}


def list_message_batches(status: str = "pending", limit: int = 20, cursor: str = "") -> dict[str, Any]:
    safe_limit = max(1, min(int(limit), 200))
    cursor_id = int(cursor or 0)
    rows = get_db().execute(
        """
        SELECT id, batch_key, window_start, window_end, status, message_count, created_at, acked_at, ack_note, acked_by
        FROM message_batches
        WHERE status = ? AND id > ?
        ORDER BY id ASC
        LIMIT ?
        """,
        (status, cursor_id, safe_limit + 1),
    ).fetchall()
    items = list(rows[:safe_limit])
    next_cursor = str(items[-1]["id"]) if len(rows) > safe_limit and items else ""
    return {"items": items, "next_cursor": next_cursor}


def get_message_batch(batch_id: int, *, limit: int = 200, cursor: str = "") -> dict[str, Any] | None:
    db = get_db()
    batch = db.execute(
        """
        SELECT id, batch_key, window_start, window_end, status, message_count, created_at, acked_at, ack_note, acked_by
        FROM message_batches
        WHERE id = ?
        """,
        (int(batch_id),),
    ).fetchone()
    if not batch:
        return None
    safe_limit = max(1, min(int(limit), 500))
    cursor_id = int(cursor or 0)
    rows = db.execute(
        """
        SELECT am.seq, am.msgid, am.chat_type, am.external_userid, am.owner_userid, am.sender, am.receiver,
               am.msgtype, am.content, am.send_time, am.raw_payload, mbi.id AS batch_item_id
        FROM message_batch_items mbi
        JOIN archived_messages am ON am.id = mbi.message_id
        WHERE mbi.batch_id = ? AND mbi.id > ?
        ORDER BY mbi.id ASC
        LIMIT ?
        """,
        (int(batch_id), cursor_id, safe_limit + 1),
    ).fetchall()
    page_rows = list(rows[:safe_limit])
    next_cursor = str(page_rows[-1]["batch_item_id"]) if len(rows) > safe_limit and page_rows else ""
    group_map = get_group_chat_map([extract_roomid_from_raw_payload(row.get("raw_payload")) for row in page_rows])
    return {
        "batch": batch,
        "messages": [format_message_row(row, group_map=group_map) for row in page_rows],
        "paging": {
            "limit": safe_limit,
            "cursor": str(cursor or ""),
            "next_cursor": next_cursor,
        },
    }


def ack_message_batch(batch_id: int, ack_note: str = "", acked_by: str = "") -> dict[str, Any] | None:
    db = get_db()
    existing = db.execute(
        """
        SELECT id, batch_key, window_start, window_end, status, message_count, created_at, acked_at, ack_note, acked_by
        FROM message_batches
        WHERE id = ?
        """,
        (int(batch_id),),
    ).fetchone()
    if not existing:
        return None
    db.execute(
        """
        UPDATE message_batches
        SET status = 'acked',
            acked_at = COALESCE(acked_at, CURRENT_TIMESTAMP),
            ack_note = CASE WHEN ? <> '' THEN ? ELSE COALESCE(ack_note, '') END,
            acked_by = CASE WHEN ? <> '' THEN ? ELSE COALESCE(acked_by, '') END
        WHERE id = ?
        """,
        (ack_note, ack_note, acked_by, acked_by, int(batch_id)),
    )
    db.commit()
    return db.execute(
        """
        SELECT id, batch_key, window_start, window_end, status, message_count, created_at, acked_at, ack_note, acked_by
        FROM message_batches
        WHERE id = ?
        """,
        (int(batch_id),),
    ).fetchone()


def record_conversion_feedback(
    *,
    feedback_type: str,
    external_userid: str = "",
    chat_id: str = "",
    actor: str = "",
    feedback_payload: dict[str, Any] | None = None,
) -> int:
    db = get_db()
    row = db.execute(
        """
        INSERT INTO conversion_feedback (external_userid, chat_id, feedback_type, feedback_payload, actor)
        VALUES (?, ?, ?, ?, ?)
        RETURNING id
        """,
        (
            external_userid or "",
            chat_id or "",
            feedback_type,
            json.dumps(feedback_payload or {}, ensure_ascii=False),
            actor or "",
        ),
    ).fetchone()
    db.commit()
    return int(row["id"])


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _json_array(value: Any) -> list[Any]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _dedupe_strings(values: list[Any]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        deduped.append(text)
    return deduped


def _normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _normalize_float(value: Any, field_name: str, *, allow_none: bool = False) -> float | None:
    if value in (None, ""):
        if allow_none:
            return None
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a number") from exc


def _normalize_int(value: Any, default: int) -> int:
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("sort_order must be an integer") from exc


def _normalize_required_integer(value: Any, field_name: str, *, allow_none: bool = False) -> int | None:
    if value in (None, ""):
        if allow_none:
            return None
        return 0
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer") from exc


def _validate_tag_codes_payload(value: Any, field_name: str) -> list[str]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be an array")
    return _dedupe_strings(value)


def _slugify_questionnaire(value: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not base:
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        suffix = uuid4().hex[:6]
        base = f"q-{timestamp}-{suffix}"
    return base[:120]


def _questionnaire_exists_by_slug(slug: str, *, exclude_id: int | None = None) -> bool:
    sql = "SELECT id FROM questionnaires WHERE slug = ?"
    params: list[Any] = [slug]
    if exclude_id is not None:
        sql += " AND id <> ?"
        params.append(int(exclude_id))
    row = get_db().execute(sql, tuple(params)).fetchone()
    return row is not None


def _normalize_tag_codes(value: Any) -> list[str]:
    # The questionnaire schema keeps the historical field name `tag_codes`,
    # but values are treated end-to-end as the exact WeCom tag identifiers
    # accepted by externalcontact/mark_tag.
    if isinstance(value, str):
        candidate = value.strip()
        if candidate.startswith("[") and candidate.endswith("]"):
            return _dedupe_strings(_json_array(candidate))
        if "/" in candidate:
            return _dedupe_strings(candidate.split("/"))
        if "," in candidate:
            return _dedupe_strings(candidate.split(","))
        return _dedupe_strings([candidate])
    if isinstance(value, (list, tuple)):
        return _dedupe_strings(list(value))
    return []


def _normalize_questionnaire_payload(
    payload: dict[str, Any],
    *,
    questionnaire_id: int | None = None,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    name = str(payload.get("name") or "").strip()
    title = str(payload.get("title") or "").strip()
    description = str(payload.get("description") or "").strip()
    redirect_url = str(payload.get("redirect_url") or "").strip()
    slug_source = str(payload.get("slug") or (existing or {}).get("slug") or name or title).strip()
    slug = _slugify_questionnaire(slug_source)

    if not name:
        raise ValueError("name is required")
    if not title:
        raise ValueError("title is required")
    if _questionnaire_exists_by_slug(slug, exclude_id=questionnaire_id):
        raise ValueError("slug already exists")

    raw_questions = payload.get("questions", [])
    if raw_questions is None:
        raw_questions = []
    if not isinstance(raw_questions, list):
        raise ValueError("questions must be an array")

    normalized_questions: list[dict[str, Any]] = []
    for index, item in enumerate(raw_questions, start=1):
        if not isinstance(item, dict):
            raise ValueError("question must be an object")
        question_type = str(item.get("type") or "").strip()
        if question_type not in QUESTIONNAIRE_TYPES:
            raise ValueError("question type must be single_choice, multi_choice or textarea")
        question_title = str(item.get("title") or "").strip()
        if not question_title:
            raise ValueError("question title is required")
        question_payload = {
            "id": int(item["id"]) if item.get("id") not in (None, "") else None,
            "type": question_type,
            "title": question_title,
            "required": _normalize_bool(item.get("required")),
            "sort_order": _normalize_int(item.get("sort_order"), index),
            "options": [],
        }
        raw_options = item.get("options") or []
        if question_type in {"single_choice", "multi_choice"}:
            if not isinstance(raw_options, list) or not raw_options:
                raise ValueError(f"question '{question_title}' must have options")
            normalized_options: list[dict[str, Any]] = []
            for option_index, option in enumerate(raw_options, start=1):
                if not isinstance(option, dict):
                    raise ValueError("option must be an object")
                option_text = str(option.get("option_text") or "").strip()
                if not option_text:
                    raise ValueError(f"question '{question_title}' has an empty option_text")
                normalized_options.append(
                    {
                        "id": int(option["id"]) if option.get("id") not in (None, "") else None,
                        "option_text": option_text,
                        "score": _normalize_required_integer(option.get("score"), "score"),
                        "tag_codes": _validate_tag_codes_payload(option.get("tag_codes"), "tag_codes"),
                        "sort_order": _normalize_int(option.get("sort_order"), option_index),
                    }
                )
            question_payload["options"] = normalized_options
        normalized_questions.append(question_payload)

    raw_score_rules = payload.get("score_rules") or []
    if not isinstance(raw_score_rules, list):
        raise ValueError("score_rules must be an array")
    normalized_score_rules: list[dict[str, Any]] = []
    for index, item in enumerate(raw_score_rules, start=1):
        if not isinstance(item, dict):
            raise ValueError("score rule must be an object")
        min_score = _normalize_required_integer(item.get("min_score"), "min_score", allow_none=True)
        max_score = _normalize_required_integer(item.get("max_score"), "max_score", allow_none=True)
        if min_score is None and max_score is None:
            raise ValueError("score rule must have min_score or max_score")
        if min_score is not None and max_score is not None and min_score > max_score:
            raise ValueError("score rule min_score cannot be greater than max_score")
        tag_codes = _validate_tag_codes_payload(item.get("tag_codes"), "tag_codes")
        if not tag_codes:
            raise ValueError("score rule tag_codes cannot be empty")
        normalized_score_rules.append(
            {
                "id": int(item["id"]) if item.get("id") not in (None, "") else None,
                "min_score": min_score,
                "max_score": max_score,
                "tag_codes": tag_codes,
                "sort_order": _normalize_int(item.get("sort_order"), index),
            }
        )

    return {
        "slug": slug,
        "name": name,
        "title": title,
        "description": description,
        "is_disabled": _normalize_bool(payload.get("is_disabled", (existing or {}).get("is_disabled"))),
        "redirect_url": redirect_url,
        "questions": normalized_questions,
        "score_rules": normalized_score_rules,
    }


def _get_questionnaire_row(questionnaire_id: int) -> dict[str, Any] | None:
    return get_db().execute(
        """
        SELECT id, slug, name, title, description, is_disabled, redirect_url, created_at, updated_at
        FROM questionnaires
        WHERE id = ?
        """,
        (int(questionnaire_id),),
    ).fetchone()


def _serialize_questionnaire_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "slug": row.get("slug", ""),
        "name": row.get("name", ""),
        "title": row.get("title", ""),
        "description": row.get("description", "") or "",
        "is_disabled": _normalize_bool(row.get("is_disabled")),
        "redirect_url": row.get("redirect_url", "") or "",
        "created_at": row.get("created_at", ""),
        "updated_at": row.get("updated_at", ""),
    }


def _load_questionnaire_questions(questionnaire_id: int) -> list[dict[str, Any]]:
    question_rows = get_db().execute(
        """
        SELECT id, questionnaire_id, type, title, required, sort_order, created_at, updated_at
        FROM questionnaire_questions
        WHERE questionnaire_id = ?
        ORDER BY sort_order ASC, id ASC
        """,
        (int(questionnaire_id),),
    ).fetchall()
    if not question_rows:
        return []
    question_ids = [int(row["id"]) for row in question_rows]
    placeholders = ",".join("?" for _ in question_ids)
    option_rows = get_db().execute(
        f"""
        SELECT id, question_id, option_text, score, tag_codes, sort_order, created_at, updated_at
        FROM questionnaire_options
        WHERE question_id IN ({placeholders})
        ORDER BY sort_order ASC, id ASC
        """,
        tuple(question_ids),
    ).fetchall()
    options_by_question: dict[int, list[dict[str, Any]]] = {}
    for row in option_rows:
        options_by_question.setdefault(int(row["question_id"]), []).append(
            {
                "id": int(row["id"]),
                "question_id": int(row["question_id"]),
                "option_text": row.get("option_text", ""),
                "score": float(row.get("score") or 0),
                "tag_codes": _normalize_tag_codes(row.get("tag_codes")),
                "sort_order": int(row.get("sort_order") or 0),
                "created_at": row.get("created_at", ""),
                "updated_at": row.get("updated_at", ""),
            }
        )
    return [
        {
            "id": int(row["id"]),
            "questionnaire_id": int(row["questionnaire_id"]),
            "type": row.get("type", ""),
            "title": row.get("title", ""),
            "required": _normalize_bool(row.get("required")),
            "sort_order": int(row.get("sort_order") or 0),
            "created_at": row.get("created_at", ""),
            "updated_at": row.get("updated_at", ""),
            "options": options_by_question.get(int(row["id"]), []),
        }
        for row in question_rows
    ]


def _load_questionnaire_score_rules(questionnaire_id: int) -> list[dict[str, Any]]:
    rows = get_db().execute(
        """
        SELECT id, questionnaire_id, min_score, max_score, tag_codes, sort_order, created_at, updated_at
        FROM questionnaire_score_rules
        WHERE questionnaire_id = ?
        ORDER BY sort_order ASC, id ASC
        """,
        (int(questionnaire_id),),
    ).fetchall()
    return [
        {
            "id": int(row["id"]),
            "questionnaire_id": int(row["questionnaire_id"]),
            "min_score": float(row["min_score"]) if row.get("min_score") is not None else None,
            "max_score": float(row["max_score"]) if row.get("max_score") is not None else None,
            "tag_codes": _normalize_tag_codes(row.get("tag_codes")),
            "sort_order": int(row.get("sort_order") or 0),
            "created_at": row.get("created_at", ""),
            "updated_at": row.get("updated_at", ""),
        }
        for row in rows
    ]


def _questionnaire_submission_stats(questionnaire_id: int) -> dict[str, Any]:
    row = get_db().execute(
        """
        SELECT COUNT(*) AS submission_count, MAX(submitted_at) AS last_submitted_at
        FROM questionnaire_submissions
        WHERE questionnaire_id = ?
        """,
        (int(questionnaire_id),),
    ).fetchone()
    return {
        "submission_count": int(row["submission_count"] or 0) if row else 0,
        "last_submitted_at": row.get("last_submitted_at", "") if row else "",
    }


def _build_questionnaire_detail(row: dict[str, Any]) -> dict[str, Any]:
    detail = _serialize_questionnaire_row(row)
    detail["questions"] = _load_questionnaire_questions(int(row["id"]))
    detail["score_rules"] = _load_questionnaire_score_rules(int(row["id"]))
    detail.update(_questionnaire_submission_stats(int(row["id"])))
    return detail


def _insert_questionnaire_options(question_id: int, options: list[dict[str, Any]]) -> None:
    db = get_db()
    for item in options:
        db.execute(
            """
            INSERT INTO questionnaire_options (
                question_id, option_text, score, tag_codes, sort_order, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                int(question_id),
                item["option_text"],
                item["score"],
                _json_dumps(item["tag_codes"]),
                item["sort_order"],
            ),
        )


def _sync_questionnaire_questions(questionnaire_id: int, questions: list[dict[str, Any]]) -> None:
    db = get_db()
    db.execute("DELETE FROM questionnaire_questions WHERE questionnaire_id = ?", (int(questionnaire_id),))

    for item in questions:
        row = db.execute(
            """
            INSERT INTO questionnaire_questions (
                questionnaire_id, type, title, required, sort_order, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            RETURNING id
            """,
            (
                int(questionnaire_id),
                item["type"],
                item["title"],
                item["required"],
                item["sort_order"],
            ),
        ).fetchone()
        current_question_id = int(row["id"])
        if item["type"] != "textarea":
            _insert_questionnaire_options(current_question_id, item.get("options") or [])


def _sync_questionnaire_score_rules(questionnaire_id: int, score_rules: list[dict[str, Any]]) -> None:
    db = get_db()
    db.execute("DELETE FROM questionnaire_score_rules WHERE questionnaire_id = ?", (int(questionnaire_id),))

    for item in score_rules:
        db.execute(
            """
            INSERT INTO questionnaire_score_rules (
                questionnaire_id, min_score, max_score, tag_codes, sort_order, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                int(questionnaire_id),
                item["min_score"],
                item["max_score"],
                _json_dumps(item["tag_codes"]),
                item["sort_order"],
            ),
        )


def list_questionnaires() -> list[dict[str, Any]]:
    rows = get_db().execute(
        """
        SELECT q.id, q.slug, q.name, q.title, q.description, q.is_disabled, q.redirect_url, q.created_at, q.updated_at,
               COUNT(s.id) AS submission_count, MAX(s.submitted_at) AS last_submitted_at
        FROM questionnaires q
        LEFT JOIN questionnaire_submissions s ON s.questionnaire_id = q.id
        GROUP BY q.id, q.slug, q.name, q.title, q.description, q.is_disabled, q.redirect_url, q.created_at, q.updated_at
        ORDER BY q.updated_at DESC, q.id DESC
        """
    ).fetchall()
    results: list[dict[str, Any]] = []
    for row in rows:
        item = _serialize_questionnaire_row(row)
        item["submission_count"] = int(row["submission_count"] or 0)
        item["last_submitted_at"] = row.get("last_submitted_at", "") or ""
        results.append(item)
    return results


def list_available_wecom_tags() -> list[dict[str, Any]]:
    from .wecom_client import WeComClient

    client = WeComClient.from_app()
    payload = client.list_external_contact_tags()
    items: list[dict[str, Any]] = []
    for group in payload.get("tag_group") or []:
        group_name = str(group.get("group_name") or "").strip()
        group_id = str(group.get("group_id") or "").strip()
        for tag in group.get("tag") or []:
            tag_id = str(tag.get("id") or "").strip()
            tag_name = str(tag.get("name") or "").strip()
            if not tag_id or not tag_name:
                continue
            items.append(
                {
                    "tag_id": tag_id,
                    "tag_name": tag_name,
                    "group_name": group_name,
                    "group_id": group_id,
                }
            )
    return sorted(items, key=lambda item: ((item.get("group_name") or ""), (item.get("tag_name") or ""), item["tag_id"]))


def get_latest_questionnaire_submit_debug(questionnaire_id: int) -> dict[str, Any] | None:
    submission = get_db().execute(
        """
        SELECT id, questionnaire_id, submitted_at, matched_by, identity_map_id, openid, unionid,
               external_userid, follow_user_userid, total_score, final_tags, redirect_url_snapshot
        FROM questionnaire_submissions
        WHERE questionnaire_id = ?
        ORDER BY submitted_at DESC, id DESC
        LIMIT 1
        """,
        (int(questionnaire_id),),
    ).fetchone()
    if not submission:
        return None

    scrm_apply = get_db().execute(
        """
        SELECT status, error_message
        FROM questionnaire_scrm_apply_logs
        WHERE submission_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (int(submission["id"]),),
    ).fetchone()
    return {
        "questionnaire_id": int(submission["questionnaire_id"]),
        "submission_id": int(submission["id"]),
        "submitted_at": submission.get("submitted_at", "") or "",
        "matched_by": submission.get("matched_by", "") or "",
        "identity_map_id": int(submission["identity_map_id"]) if submission.get("identity_map_id") is not None else None,
        "openid": submission.get("openid", "") or "",
        "unionid": submission.get("unionid", "") or "",
        "external_userid": submission.get("external_userid", "") or "",
        "follow_user_userid": submission.get("follow_user_userid", "") or "",
        "total_score": float(submission.get("total_score") or 0),
        "final_tags": _dedupe_strings(_json_array(submission.get("final_tags"))),
        "redirect_url_snapshot": submission.get("redirect_url_snapshot", "") or "",
        "scrm_apply_status": (scrm_apply or {}).get("status", "") or "",
        "scrm_apply_error": (scrm_apply or {}).get("error_message", "") or "",
    }


def create_questionnaire(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_questionnaire_payload(payload)
    db = get_db()
    try:
        row = db.execute(
            """
            INSERT INTO questionnaires (
                slug, name, title, description, is_disabled, redirect_url, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            RETURNING id
            """,
            (
                normalized["slug"],
                normalized["name"],
                normalized["title"],
                normalized["description"],
                normalized["is_disabled"],
                normalized["redirect_url"],
            ),
        ).fetchone()
        questionnaire_id = int(row["id"])
        _sync_questionnaire_questions(questionnaire_id, normalized["questions"])
        _sync_questionnaire_score_rules(questionnaire_id, normalized["score_rules"])
        db.commit()
        created = get_questionnaire_detail(questionnaire_id)
        if created is None:
            raise RuntimeError("questionnaire creation failed")
        return created
    except Exception:
        db.rollback()
        raise


def get_questionnaire_detail(questionnaire_id: int) -> dict[str, Any] | None:
    row = _get_questionnaire_row(int(questionnaire_id))
    if not row:
        return None
    return _build_questionnaire_detail(row)


def update_questionnaire(questionnaire_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
    existing = _get_questionnaire_row(int(questionnaire_id))
    if not existing:
        return None
    normalized = _normalize_questionnaire_payload(payload, questionnaire_id=int(questionnaire_id), existing=existing)
    db = get_db()
    try:
        db.execute(
            """
            UPDATE questionnaires
            SET slug = ?, name = ?, title = ?, description = ?, is_disabled = ?, redirect_url = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                normalized["slug"],
                normalized["name"],
                normalized["title"],
                normalized["description"],
                normalized["is_disabled"],
                normalized["redirect_url"],
                int(questionnaire_id),
            ),
        )
        _sync_questionnaire_questions(int(questionnaire_id), normalized["questions"])
        _sync_questionnaire_score_rules(int(questionnaire_id), normalized["score_rules"])
        db.commit()
        return get_questionnaire_detail(int(questionnaire_id))
    except Exception:
        db.rollback()
        raise


def disable_questionnaire(questionnaire_id: int, is_disabled: bool = True) -> dict[str, Any] | None:
    db = get_db()
    db.execute(
        """
        UPDATE questionnaires
        SET is_disabled = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (_normalize_bool(is_disabled), int(questionnaire_id)),
    )
    db.commit()
    return get_questionnaire_detail(int(questionnaire_id))


def delete_questionnaire(questionnaire_id: int) -> bool:
    db = get_db()
    cursor = db.execute("DELETE FROM questionnaires WHERE id = ?", (int(questionnaire_id),))
    db.commit()
    return cursor.rowcount > 0


def export_questionnaire_submissions(questionnaire_id: int) -> dict[str, Any]:
    questionnaire = get_questionnaire_detail(int(questionnaire_id))
    if not questionnaire:
        raise LookupError("questionnaire not found")

    db = get_db()
    submission_rows = db.execute(
        """
        SELECT id, submitted_at, respondent_key, openid, unionid, external_userid, follow_user_userid,
               matched_by, source_channel, campaign_id, staff_id, total_score, final_tags
        FROM questionnaire_submissions
        WHERE questionnaire_id = ?
        ORDER BY submitted_at DESC, id DESC
        """,
        (int(questionnaire_id),),
    ).fetchall()
    answer_rows = db.execute(
        """
        SELECT submission_id, question_id, question_type, question_title_snapshot,
               selected_option_texts_snapshot, text_value
        FROM questionnaire_submission_answers
        WHERE submission_id IN (
            SELECT id FROM questionnaire_submissions WHERE questionnaire_id = ?
        )
        ORDER BY submission_id ASC, id ASC
        """,
        (int(questionnaire_id),),
    ).fetchall()

    current_sort_order = {int(question["id"]): int(question.get("sort_order") or 0) for question in questionnaire["questions"]}
    question_columns: list[dict[str, Any]] = []
    seen_question_ids: set[int] = set()
    if answer_rows:
        for row in answer_rows:
            question_id = int(row["question_id"])
            if question_id in seen_question_ids:
                continue
            seen_question_ids.add(question_id)
            question_columns.append(
                {
                    "question_id": question_id,
                    "title": row.get("question_title_snapshot", "") or f"Question {question_id}",
                    "sort_order": current_sort_order.get(question_id, 10_000 + len(question_columns)),
                }
            )
        question_columns.sort(key=lambda item: (item["sort_order"], item["question_id"]))
    else:
        question_columns = [
            {"question_id": int(question["id"]), "title": question["title"], "sort_order": int(question.get("sort_order") or 0)}
            for question in questionnaire["questions"]
        ]

    question_headers = [column["title"] for column in question_columns]
    question_order = [column["question_id"] for column in question_columns]
    answer_values_by_submission: dict[int, dict[int, str]] = {}
    for row in answer_rows:
        submission_id = int(row["submission_id"])
        question_id = int(row["question_id"])
        question_type = row.get("question_type", "")
        if question_type == "textarea":
            cell_value = row.get("text_value", "") or ""
        else:
            cell_value = "/".join(_dedupe_strings(_json_array(row.get("selected_option_texts_snapshot"))))
        answer_values_by_submission.setdefault(submission_id, {})[question_id] = cell_value

    headers = [
        "提交时间",
        "问卷名称",
        "respondent_key",
        "openid",
        "unionid",
        "external_userid",
        "follow_user_userid",
        "matched_by",
        "source_channel",
        "campaign_id",
        "staff_id",
        "总分",
        "最终标签",
        *question_headers,
    ]
    rows: list[list[str]] = []
    for submission in submission_rows:
        submission_id = int(submission["id"])
        answer_map = answer_values_by_submission.get(submission_id, {})
        rows.append(
            [
                submission.get("submitted_at", "") or "",
                questionnaire["name"],
                submission.get("respondent_key", "") or "",
                submission.get("openid", "") or "",
                submission.get("unionid", "") or "",
                submission.get("external_userid", "") or "",
                submission.get("follow_user_userid", "") or "",
                submission.get("matched_by", "") or "",
                submission.get("source_channel", "") or "",
                submission.get("campaign_id", "") or "",
                submission.get("staff_id", "") or "",
                str(submission.get("total_score", "") or 0),
                "/".join(_dedupe_strings(_json_array(submission.get("final_tags")))),
                *[answer_map.get(question_id, "") for question_id in question_order],
            ]
        )

    return {
        "questionnaire": questionnaire,
        "headers": headers,
        "rows": rows,
        "filename": f"questionnaire-{questionnaire['slug']}-submissions.xls",
    }


def get_public_questionnaire_by_slug(slug: str) -> dict[str, Any] | None:
    row = get_db().execute(
        """
        SELECT id, slug, name, title, description, is_disabled, redirect_url, created_at, updated_at
        FROM questionnaires
        WHERE slug = ? AND is_disabled = ?
        LIMIT 1
        """,
        (slug.strip(), False),
    ).fetchone()
    if not row:
        return None
    detail = _build_questionnaire_detail(row)
    detail["questions"] = [
        {
            "id": question["id"],
            "type": question["type"],
            "title": question["title"],
            "required": question["required"],
            "sort_order": question["sort_order"],
            "options": [
                {
                    "id": option["id"],
                    "option_text": option["option_text"],
                    "sort_order": option["sort_order"],
                }
                for option in question["options"]
            ],
        }
        for question in detail["questions"]
    ]
    detail.pop("score_rules", None)
    detail.pop("submission_count", None)
    detail.pop("last_submitted_at", None)
    return detail


def _normalize_answer_payload(answers: Any) -> dict[str, Any]:
    if isinstance(answers, dict):
        return {str(key): value for key, value in answers.items()}
    if isinstance(answers, list):
        normalized: dict[str, Any] = {}
        for item in answers:
            if not isinstance(item, dict):
                continue
            question_id = item.get("question_id") or item.get("id")
            if question_id in (None, ""):
                continue
            value = item.get("value")
            if value is None and "selected_option_ids" in item:
                value = item.get("selected_option_ids")
            if value is None and "text_value" in item:
                value = item.get("text_value")
            normalized[str(question_id)] = value
        return normalized
    raise ValueError("answers must be an object or array")


def validate_questionnaire_answers(questionnaire: dict[str, Any], answers: Any) -> list[dict[str, Any]]:
    normalized_answers = _normalize_answer_payload(answers)
    known_question_ids = {str(int(question["id"])) for question in questionnaire.get("questions") or []}
    unknown_question_ids = sorted(set(normalized_answers.keys()) - known_question_ids)
    if unknown_question_ids:
        raise ValueError(f"unknown question_id: {','.join(unknown_question_ids)}")
    validated: list[dict[str, Any]] = []

    for question in questionnaire.get("questions") or []:
        question_id = int(question["id"])
        question_key = str(question_id)
        question_type = question["type"]
        raw_value = normalized_answers.get(question_key)
        option_map = {int(option["id"]): option for option in question.get("options") or []}

        if question_type == "textarea":
            text_value = str(raw_value or "").strip()
            if question["required"] and not text_value:
                raise ValueError(f"question '{question['title']}' is required")
            validated.append(
                {
                    "question": question,
                    "question_id": question_id,
                    "question_type": question_type,
                    "selected_options": [],
                    "text_value": text_value,
                }
            )
            continue

        selected_ids_raw: list[Any]
        if raw_value in (None, ""):
            selected_ids_raw = []
        elif isinstance(raw_value, list):
            selected_ids_raw = raw_value
        else:
            selected_ids_raw = [raw_value]

        normalized_ids: list[int] = []
        seen_ids: set[int] = set()
        for raw_id in selected_ids_raw:
            try:
                option_id = int(raw_id)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"question '{question['title']}' has an invalid option") from exc
            if option_id in seen_ids:
                continue
            if option_id not in option_map:
                raise ValueError(f"question '{question['title']}' has an invalid option")
            seen_ids.add(option_id)
            normalized_ids.append(option_id)

        if question_type == "single_choice" and len(normalized_ids) > 1:
            raise ValueError(f"question '{question['title']}' only allows one option")
        if question["required"] and not normalized_ids:
            raise ValueError(f"question '{question['title']}' is required")

        validated.append(
            {
                "question": question,
                "question_id": question_id,
                "question_type": question_type,
                "selected_options": [option_map[option_id] for option_id in normalized_ids],
                "text_value": "",
            }
        )

    return validated


def compute_questionnaire_result(questionnaire: dict[str, Any], answers: Any) -> dict[str, Any]:
    validated_answers = answers if isinstance(answers, list) and answers and "question" in answers[0] else validate_questionnaire_answers(questionnaire, answers)
    total_score = 0.0
    option_tags: list[str] = []
    answer_snapshots: list[dict[str, Any]] = []

    for item in validated_answers:
        question = item["question"]
        selected_options = item.get("selected_options") or []
        selected_option_ids = [int(option["id"]) for option in selected_options]
        selected_option_texts = [option["option_text"] for option in selected_options]
        selected_option_scores = [float(option.get("score") or 0) for option in selected_options]
        selected_option_tags = _dedupe_strings(
            [tag for option in selected_options for tag in _normalize_tag_codes(option.get("tag_codes"))]
        )
        score_contribution = sum(selected_option_scores)
        if question["type"] in {"single_choice", "multi_choice"}:
            total_score += score_contribution
            option_tags.extend(selected_option_tags)

        answer_snapshots.append(
            {
                "question_id": int(question["id"]),
                "question_type": question["type"],
                "question_title_snapshot": question["title"],
                "selected_option_ids": selected_option_ids,
                "selected_option_texts_snapshot": selected_option_texts,
                "selected_option_scores_snapshot": selected_option_scores,
                "selected_option_tags_snapshot": selected_option_tags,
                "text_value": item.get("text_value", ""),
                "score_contribution": score_contribution if question["type"] != "textarea" else 0.0,
            }
        )

    matched_rule_tags: list[str] = []
    for rule in questionnaire.get("score_rules") or []:
        min_score = rule.get("min_score")
        max_score = rule.get("max_score")
        if min_score is not None and total_score < float(min_score):
            continue
        if max_score is not None and total_score > float(max_score):
            continue
        matched_rule_tags.extend(_normalize_tag_codes(rule.get("tag_codes")))

    final_tags = _dedupe_strings(option_tags + matched_rule_tags)
    return {
        "validated_answers": validated_answers,
        "answer_snapshots": answer_snapshots,
        "total_score": total_score,
        "final_tags": final_tags,
        "redirect_url": questionnaire.get("redirect_url", "") or "",
    }


def resolve_questionnaire_submit_identity(
    openid: str = "",
    unionid: str = "",
    external_userid: str = "",
) -> dict[str, Any] | None:
    corp_id = str(current_app.config.get("WECOM_CORP_ID", "") or "").strip()
    if not corp_id:
        return None
    lookup_order = [
        ("unionid", str(unionid or "").strip()),
        ("openid", str(openid or "").strip()),
        ("external_userid", str(external_userid or "").strip()),
    ]
    for matched_by, value in lookup_order:
        if not value:
            continue
        resolved = resolve_external_contact_identity(corp_id, **{matched_by: value})
        if resolved:
            identity = dict(resolved)
            identity["matched_by"] = matched_by
            return identity
    return None


def _get_questionnaire_session_identity() -> dict[str, str]:
    if not has_request_context():
        return {}
    identity = session.get("questionnaire_h5_identity") or {}
    if not isinstance(identity, dict):
        return {}
    return {
        "openid": str(identity.get("openid") or "").strip(),
        "unionid": str(identity.get("unionid") or "").strip(),
        "respondent_key": str(identity.get("respondent_key") or "").strip(),
    }


def _build_respondent_key(identity: dict[str, Any] | None, request_meta: dict[str, Any] | None) -> str:
    meta = request_meta or {}
    explicit = str(meta.get("respondent_key") or "").strip()
    if explicit:
        return explicit
    if identity:
        for field in ["unionid", "openid", "external_userid"]:
            value = str(identity.get(field) or "").strip()
            if value:
                return value
    for field in ["unionid", "openid", "external_userid"]:
        value = str(meta.get(field) or "").strip()
        if value:
            return value
    ip = str(meta.get("ip") or "").strip()
    if ip:
        return f"ip:{ip}"
    return f"anon:{uuid4().hex}"


def has_questionnaire_submission(questionnaire_id: int, identity: dict[str, Any] | None) -> bool:
    normalized = identity or {}
    lookup_order = [
        ("external_userid", str(normalized.get("external_userid") or "").strip()),
        ("unionid", str(normalized.get("unionid") or "").strip()),
        ("openid", str(normalized.get("openid") or "").strip()),
        ("respondent_key", str(normalized.get("respondent_key") or "").strip()),
    ]
    db = get_db()
    for field, value in lookup_order:
        if not value:
            continue
        row = db.execute(
            f"""
            SELECT id
            FROM questionnaire_submissions
            WHERE questionnaire_id = ? AND {field} = ?
            LIMIT 1
            """,
            (int(questionnaire_id), value),
        ).fetchone()
        if row:
            return True
    return False


def save_questionnaire_submission(
    questionnaire: dict[str, Any],
    identity: dict[str, Any] | None,
    computed_result: dict[str, Any],
    answers: Any,
    request_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del answers
    meta = request_meta or {}
    identity = identity or {}
    db = get_db()
    respondent_key = _build_respondent_key(identity, meta)
    openid = str(identity.get("openid") or meta.get("openid") or "").strip()
    unionid = str(identity.get("unionid") or meta.get("unionid") or "").strip()
    external_userid = str(identity.get("external_userid") or meta.get("external_userid") or "").strip()
    follow_user_userid = str(identity.get("follow_user_userid") or "").strip()
    row = db.execute(
        """
        INSERT INTO questionnaire_submissions (
            questionnaire_id, identity_map_id, respondent_key, openid, unionid, external_userid,
            follow_user_userid, matched_by, source_channel, campaign_id, staff_id,
            total_score, final_tags, redirect_url_snapshot, submitted_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        RETURNING id, submitted_at
        """,
        (
            int(questionnaire["id"]),
            identity.get("identity_map_id"),
            respondent_key,
            openid,
            unionid,
            external_userid,
            follow_user_userid,
            str(identity.get("matched_by") or "").strip(),
            str(meta.get("source_channel") or "").strip(),
            str(meta.get("campaign_id") or "").strip(),
            str(meta.get("staff_id") or "").strip(),
            float(computed_result.get("total_score") or 0),
            _json_dumps(computed_result.get("final_tags") or []),
            str(computed_result.get("redirect_url") or questionnaire.get("redirect_url") or "").strip(),
        ),
    ).fetchone()
    submission_id = int(row["id"])

    for item in computed_result.get("answer_snapshots") or []:
        db.execute(
            """
            INSERT INTO questionnaire_submission_answers (
                submission_id, question_id, question_type, question_title_snapshot,
                selected_option_ids, selected_option_texts_snapshot, selected_option_scores_snapshot,
                selected_option_tags_snapshot, text_value, score_contribution, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                submission_id,
                int(item["question_id"]),
                item["question_type"],
                item["question_title_snapshot"],
                _json_dumps(item.get("selected_option_ids") or []),
                _json_dumps(item.get("selected_option_texts_snapshot") or []),
                _json_dumps(item.get("selected_option_scores_snapshot") or []),
                _json_dumps(item.get("selected_option_tags_snapshot") or []),
                item.get("text_value", "") or "",
                float(item.get("score_contribution") or 0),
            ),
        )
    db.commit()
    questionnaire_logger.info(
        "questionnaire submission saved submission_id=%s total_score=%s final_tags=%s",
        submission_id,
        float(computed_result.get("total_score") or 0),
        ",".join(computed_result.get("final_tags") or []),
    )
    return {
        "id": submission_id,
        "submitted_at": row.get("submitted_at", ""),
        "questionnaire_id": int(questionnaire["id"]),
        "respondent_key": respondent_key,
        "openid": openid,
        "unionid": unionid,
        "external_userid": external_userid,
        "follow_user_userid": follow_user_userid,
        "matched_by": str(identity.get("matched_by") or "").strip(),
        "total_score": float(computed_result.get("total_score") or 0),
        "final_tags": computed_result.get("final_tags") or [],
        "redirect_url_snapshot": str(computed_result.get("redirect_url") or questionnaire.get("redirect_url") or "").strip(),
    }


def _log_questionnaire_scrm_apply(
    submission_id: int,
    *,
    external_userid: str,
    follow_user_userid: str,
    final_tags: list[str],
    status: str,
    error_message: str = "",
) -> None:
    get_db().execute(
        """
        INSERT INTO questionnaire_scrm_apply_logs (
            submission_id, external_userid, follow_user_userid, final_tags, status, error_message, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (
            int(submission_id),
            external_userid,
            follow_user_userid,
            _json_dumps(final_tags),
            status,
            error_message,
        ),
    )
    get_db().commit()


def apply_questionnaire_result_to_scrm(submission_id: int) -> dict[str, Any]:
    submission = get_db().execute(
        """
        SELECT id, external_userid, follow_user_userid, final_tags
        FROM questionnaire_submissions
        WHERE id = ?
        """,
        (int(submission_id),),
    ).fetchone()
    if not submission:
        return {"applied": False, "reason": "submission_not_found"}

    external_userid = str(submission.get("external_userid") or "").strip()
    follow_user_userid = str(submission.get("follow_user_userid") or "").strip()
    final_tags = _dedupe_strings(_json_array(submission.get("final_tags")))
    if not external_userid:
        _log_questionnaire_scrm_apply(
            submission_id,
            external_userid=external_userid,
            follow_user_userid=follow_user_userid,
            final_tags=final_tags,
            status="skipped",
            error_message="no_external_userid",
        )
        questionnaire_logger.info("questionnaire scrm skip submission_id=%s reason=no_external_userid", submission_id)
        return {"applied": False, "reason": "no_external_userid"}

    if not follow_user_userid:
        _log_questionnaire_scrm_apply(
            submission_id,
            external_userid=external_userid,
            follow_user_userid=follow_user_userid,
            final_tags=final_tags,
            status="skipped",
            error_message="no_follow_user_userid",
        )
        questionnaire_logger.info("questionnaire scrm skip submission_id=%s reason=no_follow_user_userid", submission_id)
        return {"applied": False, "reason": "no_follow_user_userid"}

    if not final_tags:
        _log_questionnaire_scrm_apply(
            submission_id,
            external_userid=external_userid,
            follow_user_userid=follow_user_userid,
            final_tags=final_tags,
            status="skipped",
            error_message="no_final_tags",
        )
        questionnaire_logger.info("questionnaire scrm skip submission_id=%s reason=no_final_tags", submission_id)
        return {"applied": False, "reason": "no_final_tags"}

    try:
        from .wecom_client import WeComClient

        client = WeComClient.from_app()
        result = client.mark_external_contact_tags(
            external_userid=external_userid,
            follow_user_userid=follow_user_userid,
            add_tags=final_tags,
            remove_tags=None,
        )
        save_tag_snapshot(follow_user_userid, external_userid, final_tags)
        _log_questionnaire_scrm_apply(
            submission_id,
            external_userid=external_userid,
            follow_user_userid=follow_user_userid,
            final_tags=final_tags,
            status="success",
        )
        questionnaire_logger.info(
            "questionnaire scrm applied submission_id=%s external_userid=%s follow_user_userid=%s tags=%s",
            submission_id,
            external_userid,
            follow_user_userid,
            ",".join(final_tags),
        )
        return {"applied": True, "result": result}
    except Exception as exc:
        _log_questionnaire_scrm_apply(
            submission_id,
            external_userid=external_userid,
            follow_user_userid=follow_user_userid,
            final_tags=final_tags,
            status="failed",
            error_message=str(exc),
        )
        questionnaire_logger.exception(
            "questionnaire scrm apply failed submission_id=%s external_userid=%s follow_user_userid=%s",
            submission_id,
            external_userid,
            follow_user_userid,
        )
        return {"applied": False, "reason": "wecom_error", "error": str(exc)}


def submit_questionnaire(slug: str, payload: dict[str, Any], request_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    slug_value = str(slug or "").strip()
    row = get_db().execute(
        """
        SELECT id, slug, name, title, description, is_disabled, redirect_url, created_at, updated_at
        FROM questionnaires
        WHERE slug = ? AND is_disabled = ?
        LIMIT 1
        """,
        (slug_value, False),
    ).fetchone()
    if not row:
        raise LookupError("questionnaire not found")
    questionnaire = _build_questionnaire_detail(row)

    answers = payload.get("answers")
    if answers is None:
        raise ValueError("answers is required")

    submit_meta = dict(request_meta or {})
    session_identity = _get_questionnaire_session_identity()
    for field in ["source_channel", "campaign_id", "staff_id"]:
        if field in payload and payload.get(field) is not None:
            submit_meta[field] = payload.get(field)
    submit_meta["respondent_key"] = session_identity.get("respondent_key") or str(payload.get("respondent_key") or "").strip()
    submit_meta["openid"] = session_identity.get("openid") or str(payload.get("openid") or "").strip()
    submit_meta["unionid"] = session_identity.get("unionid") or str(payload.get("unionid") or "").strip()
    submit_meta["external_userid"] = str(payload.get("external_userid") or "").strip()

    resolved_unionid = submit_meta["unionid"]
    resolved_openid = submit_meta["openid"]
    payload_external_userid = submit_meta["external_userid"]

    identity = resolve_questionnaire_submit_identity(
        openid=resolved_openid,
        unionid=resolved_unionid,
        external_userid=payload_external_userid,
    )
    if identity and identity.get("matched_by") == "unionid" and resolved_openid and not str(identity.get("openid") or "").strip():
        corp_id = str(current_app.config.get("WECOM_CORP_ID", "") or "").strip()
        rebound = bind_openid_to_external_contact(
            corp_id,
            str(identity.get("external_userid") or "").strip(),
            resolved_openid,
            unionid=resolved_unionid,
        )
        if rebound:
            identity = dict(rebound)
            identity["matched_by"] = "unionid"
    if identity:
        identity["openid"] = str(identity.get("openid") or resolved_openid or "").strip()
        identity["unionid"] = str(identity.get("unionid") or resolved_unionid or "").strip()

    questionnaire_logger.info(
        "questionnaire identity resolved slug=%s questionnaire_id=%s matched_by=%s identity_map_id=%s external_userid=%s follow_user_userid=%s",
        slug_value,
        int(questionnaire["id"]),
        str((identity or {}).get("matched_by") or ""),
        str((identity or {}).get("identity_map_id") or ""),
        str((identity or {}).get("external_userid") or ""),
        str((identity or {}).get("follow_user_userid") or ""),
    )

    duplicate_identity = {
        "external_userid": str((identity or {}).get("external_userid") or payload_external_userid or "").strip(),
        "unionid": str((identity or {}).get("unionid") or resolved_unionid or "").strip(),
        "openid": str((identity or {}).get("openid") or resolved_openid or "").strip(),
        "respondent_key": _build_respondent_key(identity, submit_meta),
    }
    if has_questionnaire_submission(int(questionnaire["id"]), duplicate_identity):
        raise QuestionnaireAlreadySubmittedError("已经提交")

    validated_answers = validate_questionnaire_answers(questionnaire, answers)
    computed_result = compute_questionnaire_result(questionnaire, validated_answers)
    submission = save_questionnaire_submission(
        questionnaire,
        identity,
        computed_result,
        answers,
        request_meta=submit_meta,
    )
    apply_questionnaire_result_to_scrm(submission["id"])
    return {
        "success": True,
        "redirect_url": computed_result.get("redirect_url", "") or "",
        "message": "已收到提交",
    }
