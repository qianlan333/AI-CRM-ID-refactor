from __future__ import annotations

import json
import re
import sys
from typing import Any

import requests
from flask import current_app

from .db import get_db
from .services import ContactBindingConflictError, ThirdPartyUserSyncError, enrich_contact_context


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
    services_module = sys.modules.get("wecom_ability_service.services")
    if services_module is not None:
        patched = getattr(services_module, "_resolve_third_party_user_id_by_mobile", None)
        if callable(patched) and patched is not _resolve_third_party_user_id_by_mobile:
            return str(patched(mobile) or "").strip()

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
