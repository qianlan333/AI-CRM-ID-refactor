from __future__ import annotations

from datetime import datetime
from typing import Any

from .db import get_db
from .services import (
    CLASS_USER_ALLOWED_STATUSES,
    get_contact_by_external_userid,
    get_signup_status_definition,
    get_signup_status_definitions,
    resolve_signup_status_from_tags,
)


def resolve_person_identity(*, external_userid: str = "", mobile: str = "") -> dict[str, Any]:
    from .identity_binding_service import resolve_person_identity as _resolve_person_identity

    return _resolve_person_identity(external_userid=external_userid, mobile=mobile)


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

