from __future__ import annotations

from typing import Any

from ..db import get_db, get_db_backend


def _fetchall_dict(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in get_db().execute(sql, params).fetchall()]


def list_scope_external_userids() -> list[str]:
    rows = _fetchall_dict(
        """
        SELECT external_userid
        FROM (
            SELECT external_userid FROM contacts
            UNION
            SELECT external_userid FROM external_contact_bindings
            UNION
            SELECT external_userid FROM wecom_external_contact_identity_map
            UNION
            SELECT external_userid FROM wecom_external_contact_follow_users
            UNION
            SELECT external_userid FROM contact_tags
            UNION
            SELECT external_userid FROM class_user_status_current
            UNION
            SELECT external_userid FROM archived_messages
        ) scope
        WHERE external_userid IS NOT NULL AND external_userid <> ''
        ORDER BY external_userid ASC
        """
    )
    return [str(row.get("external_userid") or "").strip() for row in rows if str(row.get("external_userid") or "").strip()]


def fetch_contact_map(external_userids: list[str]) -> dict[str, dict[str, Any]]:
    if not external_userids:
        return {}
    placeholders = ",".join(["?"] * len(external_userids))
    rows = _fetchall_dict(
        f"""
        SELECT external_userid, customer_name, owner_userid, remark, description, updated_at
        FROM contacts
        WHERE external_userid IN ({placeholders})
        """,
        tuple(external_userids),
    )
    return {str(row.get("external_userid") or "").strip(): row for row in rows}


def fetch_binding_map(external_userids: list[str]) -> dict[str, dict[str, Any]]:
    if not external_userids:
        return {}
    placeholders = ",".join(["?"] * len(external_userids))
    rows = _fetchall_dict(
        f"""
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
        LEFT JOIN people p ON p.id = b.person_id
        WHERE b.external_userid IN ({placeholders})
        """,
        tuple(external_userids),
    )
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        external_userid = str(row.get("external_userid") or "").strip()
        if external_userid:
            payload = dict(row)
            payload["is_bound"] = True
            result[external_userid] = payload
    return result


def fetch_identity_map(external_userids: list[str]) -> dict[str, dict[str, Any]]:
    if not external_userids:
        return {}
    placeholders = ",".join(["?"] * len(external_userids))
    rows = _fetchall_dict(
        f"""
        SELECT
            external_userid,
            unionid,
            openid,
            follow_user_userid,
            name,
            status,
            created_at,
            updated_at
        FROM wecom_external_contact_identity_map
        WHERE external_userid IN ({placeholders})
        ORDER BY updated_at DESC, id DESC
        """,
        tuple(external_userids),
    )
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        external_userid = str(row.get("external_userid") or "").strip()
        if external_userid and external_userid not in result:
            result[external_userid] = row
    return result


def fetch_follow_users_map(external_userids: list[str]) -> dict[str, list[dict[str, Any]]]:
    if not external_userids:
        return {}
    placeholders = ",".join(["?"] * len(external_userids))
    rows = _fetchall_dict(
        f"""
        SELECT
            external_userid,
            user_id,
            relation_status,
            is_primary,
            remark,
            description,
            add_way,
            oper_userid,
            createtime,
            updated_at
        FROM wecom_external_contact_follow_users
        WHERE external_userid IN ({placeholders})
        ORDER BY external_userid ASC, is_primary DESC, updated_at DESC, id DESC
        """,
        tuple(external_userids),
    )
    result: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        external_userid = str(row.get("external_userid") or "").strip()
        if not external_userid:
            continue
        result.setdefault(external_userid, []).append(
            {
                "userid": str(row.get("user_id") or "").strip(),
                "relation_status": str(row.get("relation_status") or "").strip(),
                "is_primary": bool(row.get("is_primary")),
                "remark": str(row.get("remark") or "").strip(),
                "description": str(row.get("description") or "").strip(),
                "add_way": row.get("add_way"),
                "oper_userid": str(row.get("oper_userid") or "").strip(),
                "createtime": row.get("createtime"),
                "updated_at": str(row.get("updated_at") or "").strip(),
            }
        )
    return result


def fetch_tag_map(external_userids: list[str]) -> dict[str, list[dict[str, Any]]]:
    if not external_userids:
        return {}
    placeholders = ",".join(["?"] * len(external_userids))
    rows = _fetchall_dict(
        f"""
        SELECT external_userid, userid, tag_id, COALESCE(tag_name, '') AS tag_name, created_at
        FROM contact_tags
        WHERE external_userid IN ({placeholders})
        ORDER BY external_userid ASC, userid ASC, tag_name ASC, tag_id ASC
        """,
        tuple(external_userids),
    )
    result: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        external_userid = str(row.get("external_userid") or "").strip()
        if external_userid:
            result.setdefault(external_userid, []).append(row)
    return result


def fetch_class_status_map(external_userids: list[str]) -> dict[str, dict[str, Any]]:
    if not external_userids:
        return {}
    placeholders = ",".join(["?"] * len(external_userids))
    rows = _fetchall_dict(
        f"""
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
        WHERE external_userid IN ({placeholders})
        """,
        tuple(external_userids),
    )
    return {str(row.get("external_userid") or "").strip(): row for row in rows}


def fetch_last_message_map(external_userids: list[str]) -> dict[str, str]:
    if not external_userids:
        return {}
    placeholders = ",".join(["?"] * len(external_userids))
    rows = _fetchall_dict(
        f"""
        SELECT external_userid, MAX(send_time) AS last_message_at
        FROM archived_messages
        WHERE external_userid IN ({placeholders})
        GROUP BY external_userid
        """,
        tuple(external_userids),
    )
    return {
        str(row.get("external_userid") or "").strip(): str(row.get("last_message_at") or "").strip()
        for row in rows
        if str(row.get("external_userid") or "").strip()
    }


def list_customer_agent_output_rows(external_userid: str, *, limit: int = 10) -> list[dict[str, Any]]:
    normalized_external_userid = str(external_userid or "").strip()
    if not normalized_external_userid:
        return []
    return _fetchall_dict(
        """
        SELECT
            output.id,
            output.output_id,
            output.run_id,
            output.request_id,
            output.userid,
            output.external_contact_id,
            output.agent_code,
            output.output_type,
            output.raw_output_text,
            output.normalized_output_json,
            output.rendered_output_text,
            output.target_agent_code,
            output.target_pool,
            output.confidence,
            output.reason,
            output.need_human_review,
            output.applied_status,
            output.error_code,
            output.error_message,
            output.created_at,
            COALESCE(run.input_snapshot_json, '{}') AS input_snapshot_json,
            COALESCE(run.variables_snapshot_json, '{}') AS variables_snapshot_json,
            COALESCE(run.status, '') AS run_status,
            COALESCE(run.created_at, '') AS run_created_at
        FROM automation_agent_output output
        LEFT JOIN automation_agent_run run ON run.run_id = output.run_id
        WHERE output.external_contact_id = ?
          AND output.output_type IN ('next_action_suggestion', 'agent_reply_draft', 'agent_reply_final')
          AND COALESCE(output.error_code, '') = ''
          AND COALESCE(output.error_message, '') = ''
        ORDER BY output.created_at DESC, output.id DESC
        LIMIT ?
        """,
        (normalized_external_userid, max(1, min(int(limit or 10), 50))),
    )


def fetch_owner_role_map(userids: list[str]) -> dict[str, dict[str, Any]]:
    normalized = [str(userid or "").strip() for userid in userids if str(userid or "").strip()]
    if not normalized:
        return {}
    placeholders = ",".join(["?"] * len(normalized))
    rows = _fetchall_dict(
        f"""
        SELECT userid, display_name, role, active, updated_at
        FROM owner_role_map
        WHERE userid IN ({placeholders})
        """,
        tuple(normalized),
    )
    return {str(row.get("userid") or "").strip(): row for row in rows}


def fetch_customer_marketing_state_current(external_userid: str) -> dict[str, Any] | None:
    normalized_external_userid = str(external_userid or "").strip()
    if not normalized_external_userid:
        return None
    row = get_db().execute(
        """
        SELECT
            external_userid,
            main_stage,
            sub_stage,
            eligible_for_conversion,
            last_activation_at,
            last_conversion_marked_at,
            state_payload_json,
            updated_at
        FROM customer_marketing_state_current
        WHERE external_userid = ?
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (normalized_external_userid,),
    ).fetchone()
    return dict(row) if row else None


def fetch_customer_marketing_state_current_map(external_userids: list[str]) -> dict[str, dict[str, Any]]:
    normalized = [str(item or "").strip() for item in external_userids if str(item or "").strip()]
    if not normalized:
        return {}
    placeholders = ",".join(["?"] * len(normalized))
    rows = _fetchall_dict(
        f"""
        SELECT
            external_userid,
            main_stage,
            sub_stage,
            eligible_for_conversion,
            last_activation_at,
            last_conversion_marked_at,
            state_payload_json,
            updated_at,
            id
        FROM customer_marketing_state_current
        WHERE external_userid IN ({placeholders})
        ORDER BY external_userid ASC, updated_at DESC, id DESC
        """,
        tuple(normalized),
    )
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        external_userid = str(row.get("external_userid") or "").strip()
        if external_userid and external_userid not in result:
            result[external_userid] = row
    return result


def fetch_customer_value_segment_current(external_userid: str) -> dict[str, Any] | None:
    normalized_external_userid = str(external_userid or "").strip()
    if not normalized_external_userid:
        return None
    row = get_db().execute(
        """
        SELECT
            external_userid,
            segment,
            score,
            updated_at
        FROM customer_value_segment_current
        WHERE external_userid = ?
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (normalized_external_userid,),
    ).fetchone()
    return dict(row) if row else None


def fetch_customer_value_segment_current_map(external_userids: list[str]) -> dict[str, dict[str, Any]]:
    normalized = [str(item or "").strip() for item in external_userids if str(item or "").strip()]
    if not normalized:
        return {}
    placeholders = ",".join(["?"] * len(normalized))
    rows = _fetchall_dict(
        f"""
        SELECT
            external_userid,
            segment,
            score,
            updated_at,
            id
        FROM customer_value_segment_current
        WHERE external_userid IN ({placeholders})
        ORDER BY external_userid ASC, updated_at DESC, id DESC
        """,
        tuple(normalized),
    )
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        external_userid = str(row.get("external_userid") or "").strip()
        if external_userid and external_userid not in result:
            result[external_userid] = row
    return result


def fetch_customer_last_dispatch_at(external_userid: str) -> str:
    normalized_external_userid = str(external_userid or "").strip()
    if not normalized_external_userid:
        return ""
    if get_db_backend() == "postgres":
        row = get_db().execute(
            """
            SELECT COALESCE(MAX(dispatched_at)::text, '') AS last_dispatch_at
            FROM conversion_dispatch_log
            WHERE external_userid = ?
              AND dispatched_at IS NOT NULL
            """,
            (normalized_external_userid,),
        ).fetchone()
    else:
        row = get_db().execute(
            """
            SELECT MAX(dispatched_at) AS last_dispatch_at
            FROM conversion_dispatch_log
            WHERE external_userid = ?
              AND dispatched_at IS NOT NULL
              AND dispatched_at <> ''
            """,
            (normalized_external_userid,),
        ).fetchone()
    return str((row or {}).get("last_dispatch_at") or "").strip()
