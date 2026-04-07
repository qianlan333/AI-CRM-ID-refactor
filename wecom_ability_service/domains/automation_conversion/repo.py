from __future__ import annotations

import json
from typing import Any

from ...db import get_db, get_db_backend


def _db_bool(value: bool) -> bool | int:
    return value if get_db_backend() == "postgres" else (1 if value else 0)


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _json_dumps(value: Any) -> str:
    return json.dumps({} if value is None else value, ensure_ascii=False)


def _json_loads(value: Any, *, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    text = _normalized_text(value)
    if not text:
        return default
    try:
        return json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _fetchone_dict(sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    row = get_db().execute(sql, params).fetchone()
    return dict(row) if row else None


def _fetchall_dicts(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    rows = get_db().execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def lookup_person_id_by_external_contact_id(external_contact_id: str) -> int | None:
    row = _fetchone_dict(
        """
        SELECT person_id
        FROM external_contact_bindings
        WHERE external_userid = ?
        LIMIT 1
        """,
        (_normalized_text(external_contact_id),),
    )
    person_id = row.get("person_id") if row else None
    return int(person_id) if person_id not in (None, "") else None


def lookup_person_id_by_phone(phone: str) -> int | None:
    row = _fetchone_dict(
        """
        SELECT id
        FROM people
        WHERE mobile = ?
        LIMIT 1
        """,
        (_normalized_text(phone),),
    )
    person_id = row.get("id") if row else None
    return int(person_id) if person_id not in (None, "") else None


def list_external_contact_ids_by_person_id(person_id: int | None) -> list[str]:
    if person_id in (None, ""):
        return []
    rows = _fetchall_dicts(
        """
        SELECT external_userid
        FROM external_contact_bindings
        WHERE person_id = ?
        ORDER BY updated_at DESC, external_userid ASC
        """,
        (int(person_id),),
    )
    return [_normalized_text(row.get("external_userid")) for row in rows if _normalized_text(row.get("external_userid"))]


def find_latest_external_contact_id_by_phone(phone: str) -> str:
    normalized_phone = _normalized_text(phone)
    if not normalized_phone:
        return ""
    if get_db_backend() == "postgres":
        sql = """
        SELECT external_userid
        FROM (
            SELECT b.external_userid, COALESCE(b.updated_at::text, b.created_at::text, '') AS ordering_value
            FROM external_contact_bindings b
            INNER JOIN people p ON p.id = b.person_id
            WHERE p.mobile = ?

            UNION ALL

            SELECT external_userid, COALESCE(updated_at::text, created_at::text, '') AS ordering_value
            FROM class_user_status_current
            WHERE mobile_snapshot = ?

            UNION ALL

            SELECT external_userid, COALESCE(submitted_at::text, '') AS ordering_value
            FROM questionnaire_submissions
            WHERE mobile_snapshot = ? AND external_userid IS NOT NULL AND external_userid <> ''
        ) candidates
        WHERE external_userid IS NOT NULL AND external_userid <> ''
        ORDER BY ordering_value DESC, external_userid ASC
        LIMIT 1
        """
    else:
        sql = """
        SELECT external_userid
        FROM (
            SELECT b.external_userid, COALESCE(b.updated_at, b.created_at, '') AS ordering_value
            FROM external_contact_bindings b
            INNER JOIN people p ON p.id = b.person_id
            WHERE p.mobile = ?

            UNION ALL

            SELECT external_userid, COALESCE(updated_at, created_at, '') AS ordering_value
            FROM class_user_status_current
            WHERE mobile_snapshot = ?

            UNION ALL

            SELECT external_userid, COALESCE(submitted_at, '') AS ordering_value
            FROM questionnaire_submissions
            WHERE mobile_snapshot = ? AND external_userid IS NOT NULL AND external_userid <> ''
        ) candidates
        WHERE external_userid IS NOT NULL AND external_userid <> ''
        ORDER BY ordering_value DESC, external_userid ASC
        LIMIT 1
        """
    row = _fetchone_dict(sql, (normalized_phone, normalized_phone, normalized_phone))
    return _normalized_text((row or {}).get("external_userid"))


def get_member_by_id(member_id: int) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_member
        WHERE id = ?
        LIMIT 1
        """,
        (int(member_id),),
    )


def get_member_by_external_contact_id(external_contact_id: str) -> dict[str, Any] | None:
    normalized = _normalized_text(external_contact_id)
    if not normalized:
        return None
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_member
        WHERE external_contact_id = ?
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (normalized,),
    )


def get_member_by_phone(phone: str) -> dict[str, Any] | None:
    normalized = _normalized_text(phone)
    if not normalized:
        return None
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_member
        WHERE phone = ?
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (normalized,),
    )


def list_members_by_ids(member_ids: list[int]) -> list[dict[str, Any]]:
    normalized_ids = [int(item) for item in member_ids if str(item).strip()]
    if not normalized_ids:
        return []
    placeholders = ",".join("?" for _ in normalized_ids)
    return _fetchall_dicts(
        f"""
        SELECT *
        FROM automation_member
        WHERE id IN ({placeholders})
        ORDER BY id ASC
        """,
        tuple(normalized_ids),
    )


def insert_member(payload: dict[str, Any]) -> dict[str, Any]:
    db = get_db()
    params = (
        _normalized_text(payload.get("external_contact_id")),
        _normalized_text(payload.get("phone")),
        payload.get("master_customer_id"),
        _normalized_text(payload.get("owner_staff_id")),
        _db_bool(bool(payload.get("in_pool"))),
        _normalized_text(payload.get("current_pool")),
        _normalized_text(payload.get("follow_type")),
        _normalized_text(payload.get("activation_status")),
        _normalized_text(payload.get("questionnaire_status")),
        _normalized_text(payload.get("questionnaire_result")),
        _normalized_text(payload.get("decision_source")),
        _normalized_text(payload.get("source_type")),
        payload.get("source_channel_id"),
        _normalized_text(payload.get("last_active_pool")),
        _normalized_text(payload.get("joined_at")),
        _normalized_text(payload.get("last_ai_push_at")),
        _normalized_text(payload.get("ai_cooldown_until")),
    )
    row = db.execute(
        """
        INSERT INTO automation_member (
            external_contact_id,
            phone,
            master_customer_id,
            owner_staff_id,
            in_pool,
            current_pool,
            follow_type,
            activation_status,
            questionnaire_status,
            questionnaire_result,
            decision_source,
            source_type,
            source_channel_id,
            last_active_pool,
            joined_at,
            last_ai_push_at,
            ai_cooldown_until,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        params,
    ).fetchone()
    return dict(row) if row else {}


def update_member(member_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    db = get_db()
    params = (
        _normalized_text(payload.get("external_contact_id")),
        _normalized_text(payload.get("phone")),
        payload.get("master_customer_id"),
        _normalized_text(payload.get("owner_staff_id")),
        _db_bool(bool(payload.get("in_pool"))),
        _normalized_text(payload.get("current_pool")),
        _normalized_text(payload.get("follow_type")),
        _normalized_text(payload.get("activation_status")),
        _normalized_text(payload.get("questionnaire_status")),
        _normalized_text(payload.get("questionnaire_result")),
        _normalized_text(payload.get("decision_source")),
        _normalized_text(payload.get("source_type")),
        payload.get("source_channel_id"),
        _normalized_text(payload.get("last_active_pool")),
        _normalized_text(payload.get("joined_at")),
        _normalized_text(payload.get("last_ai_push_at")),
        _normalized_text(payload.get("ai_cooldown_until")),
        int(member_id),
    )
    row = db.execute(
        """
        UPDATE automation_member
        SET external_contact_id = ?,
            phone = ?,
            master_customer_id = ?,
            owner_staff_id = ?,
            in_pool = ?,
            current_pool = ?,
            follow_type = ?,
            activation_status = ?,
            questionnaire_status = ?,
            questionnaire_result = ?,
            decision_source = ?,
            source_type = ?,
            source_channel_id = ?,
            last_active_pool = ?,
            joined_at = ?,
            last_ai_push_at = ?,
            ai_cooldown_until = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        RETURNING *
        """,
        params,
    ).fetchone()
    return dict(row) if row else {}


def insert_event(
    *,
    member_id: int,
    action: str,
    operator_type: str,
    operator_id: str,
    before_snapshot: dict[str, Any] | None,
    after_snapshot: dict[str, Any] | None,
    remark: str = "",
) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_event (
            member_id,
            action,
            operator_type,
            operator_id,
            before_snapshot,
            after_snapshot,
            remark,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            int(member_id),
            _normalized_text(action),
            _normalized_text(operator_type),
            _normalized_text(operator_id),
            _json_dumps(before_snapshot or {}),
            _json_dumps(after_snapshot or {}),
            _normalized_text(remark),
        ),
    ).fetchone()
    return dict(row) if row else {}


def list_recent_events(member_id: int, *, limit: int = 10) -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT *
        FROM automation_event
        WHERE member_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (int(member_id), int(limit)),
    )


def get_latest_manual_event(member_id: int) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_event
        WHERE member_id = ?
          AND operator_type = 'user'
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (int(member_id),),
    )


def insert_ai_push_log(
    *,
    member_id: int,
    scene: str,
    request_payload: dict[str, Any],
    status: str,
    request_id: str = "",
    error_message: str = "",
    pushed_at: str = "",
    cooldown_until: str = "",
) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_ai_push_log (
            member_id,
            scene,
            request_payload,
            status,
            request_id,
            error_message,
            pushed_at,
            cooldown_until
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING *
        """,
        (
            int(member_id),
            _normalized_text(scene),
            _json_dumps(request_payload),
            _normalized_text(status),
            _normalized_text(request_id),
            _normalized_text(error_message),
            _normalized_text(pushed_at),
            _normalized_text(cooldown_until),
        ),
    ).fetchone()
    return dict(row) if row else {}


def insert_message_activity_sync_run(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_message_activity_sync_run (
            trigger_source,
            operator_type,
            operator_id,
            status,
            candidate_count,
            matched_count,
            updated_count,
            skipped_ambiguous_count,
            skipped_unmatched_count,
            skipped_missing_phone_count,
            focus_count,
            normal_count,
            error_message,
            summary_json,
            started_at,
            finished_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING *
        """,
        (
            _normalized_text(payload.get("trigger_source")),
            _normalized_text(payload.get("operator_type")),
            _normalized_text(payload.get("operator_id")),
            _normalized_text(payload.get("status")),
            int(payload.get("candidate_count") or 0),
            int(payload.get("matched_count") or 0),
            int(payload.get("updated_count") or 0),
            int(payload.get("skipped_ambiguous_count") or 0),
            int(payload.get("skipped_unmatched_count") or 0),
            int(payload.get("skipped_missing_phone_count") or 0),
            int(payload.get("focus_count") or 0),
            int(payload.get("normal_count") or 0),
            _normalized_text(payload.get("error_message")),
            _json_dumps(payload.get("summary_json") or {}),
            _normalized_text(payload.get("started_at")),
            _normalized_text(payload.get("finished_at")),
        ),
    ).fetchone()
    return dict(row) if row else {}


def update_message_activity_sync_run(run_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE automation_message_activity_sync_run
        SET trigger_source = ?,
            operator_type = ?,
            operator_id = ?,
            status = ?,
            candidate_count = ?,
            matched_count = ?,
            updated_count = ?,
            skipped_ambiguous_count = ?,
            skipped_unmatched_count = ?,
            skipped_missing_phone_count = ?,
            focus_count = ?,
            normal_count = ?,
            error_message = ?,
            summary_json = ?,
            started_at = ?,
            finished_at = ?
        WHERE id = ?
        RETURNING *
        """,
        (
            _normalized_text(payload.get("trigger_source")),
            _normalized_text(payload.get("operator_type")),
            _normalized_text(payload.get("operator_id")),
            _normalized_text(payload.get("status")),
            int(payload.get("candidate_count") or 0),
            int(payload.get("matched_count") or 0),
            int(payload.get("updated_count") or 0),
            int(payload.get("skipped_ambiguous_count") or 0),
            int(payload.get("skipped_unmatched_count") or 0),
            int(payload.get("skipped_missing_phone_count") or 0),
            int(payload.get("focus_count") or 0),
            int(payload.get("normal_count") or 0),
            _normalized_text(payload.get("error_message")),
            _json_dumps(payload.get("summary_json") or {}),
            _normalized_text(payload.get("started_at")),
            _normalized_text(payload.get("finished_at")),
            int(run_id),
        ),
    ).fetchone()
    return dict(row) if row else {}


def get_latest_message_activity_sync_run() -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_message_activity_sync_run
        ORDER BY finished_at DESC, id DESC
        LIMIT 1
        """
    )


def list_message_activity_sync_items(*, run_id: int, limit: int = 100) -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT *
        FROM automation_message_activity_sync_item
        WHERE run_id = ?
        ORDER BY id ASC
        LIMIT ?
        """,
        (int(run_id), int(limit)),
    )


def insert_message_activity_sync_item(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_message_activity_sync_item (
            run_id,
            member_id,
            external_contact_id,
            phone,
            phone_last4,
            message_count,
            status,
            detail,
            before_snapshot,
            after_snapshot,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING *
        """,
        (
            int(payload.get("run_id") or 0),
            payload.get("member_id"),
            _normalized_text(payload.get("external_contact_id")),
            _normalized_text(payload.get("phone")),
            _normalized_text(payload.get("phone_last4")),
            int(payload.get("message_count") or 0),
            _normalized_text(payload.get("status")),
            _normalized_text(payload.get("detail")),
            _json_dumps(payload.get("before_snapshot") or {}),
            _json_dumps(payload.get("after_snapshot") or {}),
            _normalized_text(payload.get("created_at")),
        ),
    ).fetchone()
    return dict(row) if row else {}


def get_default_channel() -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_channel
        WHERE channel_code = 'default_qrcode'
        LIMIT 1
        """
    )


def get_channel_by_id(channel_id: int) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_channel
        WHERE id = ?
        LIMIT 1
        """,
        (int(channel_id),),
    )


def find_channel_by_scene_value(scene_value: str) -> dict[str, Any] | None:
    normalized = _normalized_text(scene_value)
    if not normalized:
        return None
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_channel
        WHERE scene_value = ?
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (normalized,),
    )


def save_channel(payload: dict[str, Any]) -> dict[str, Any]:
    existing = get_default_channel() if _normalized_text(payload.get("channel_code")) == "default_qrcode" else None
    db = get_db()
    params = (
        _normalized_text(payload.get("channel_code")),
        _normalized_text(payload.get("channel_name")),
        _normalized_text(payload.get("qr_url")),
        _normalized_text(payload.get("qr_ticket")),
        _normalized_text(payload.get("scene_value")),
        _normalized_text(payload.get("owner_staff_id")),
        _normalized_text(payload.get("status")),
    )
    if existing:
        row = db.execute(
            """
            UPDATE automation_channel
            SET channel_name = ?,
                qr_url = ?,
                qr_ticket = ?,
                scene_value = ?,
                owner_staff_id = ?,
                status = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            RETURNING *
            """,
            (
                _normalized_text(payload.get("channel_name")),
                _normalized_text(payload.get("qr_url")),
                _normalized_text(payload.get("qr_ticket")),
                _normalized_text(payload.get("scene_value")),
                _normalized_text(payload.get("owner_staff_id")),
                _normalized_text(payload.get("status")),
                int(existing["id"]),
            ),
        ).fetchone()
        return dict(row) if row else {}
    row = db.execute(
        """
        INSERT INTO automation_channel (
            channel_code,
            channel_name,
            qr_url,
            qr_ticket,
            scene_value,
            owner_staff_id,
            status,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        params,
    ).fetchone()
    return dict(row) if row else {}


def get_stage_counts() -> dict[str, int]:
    rows = _fetchall_dicts(
        """
        SELECT current_pool, COUNT(*) AS total
        FROM automation_member
        GROUP BY current_pool
        """
    )
    return {_normalized_text(row.get("current_pool")): int(row.get("total") or 0) for row in rows}


def get_stage_metrics() -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT
            current_pool,
            COUNT(*) AS total_count,
            COALESCE(SUM(CASE WHEN follow_type = 'focus' THEN 1 ELSE 0 END), 0) AS focus_count,
            COALESCE(SUM(CASE WHEN follow_type = 'normal' THEN 1 ELSE 0 END), 0) AS normal_count,
            COALESCE(SUM(CASE WHEN joined_at IS NOT NULL AND joined_at <> '' AND DATE(joined_at) = DATE(CURRENT_TIMESTAMP) THEN 1 ELSE 0 END), 0) AS today_new_count
        FROM automation_member
        GROUP BY current_pool
        """
    )


def get_overview_counts() -> dict[str, int]:
    row = _fetchone_dict(
        """
        SELECT
            COALESCE(SUM(CASE WHEN in_pool THEN 1 ELSE 0 END), 0) AS in_pool_total,
            COALESCE(SUM(CASE WHEN joined_at IS NOT NULL AND joined_at <> '' AND DATE(joined_at) = DATE(CURRENT_TIMESTAMP) THEN 1 ELSE 0 END), 0) AS today_joined,
            COALESCE(SUM(CASE WHEN questionnaire_status = 'pending' AND in_pool THEN 1 ELSE 0 END), 0) AS questionnaire_pending,
            COALESCE(SUM(CASE WHEN current_pool IN ('inactive_normal', 'active_normal') THEN 1 ELSE 0 END), 0) AS normal_followup,
            COALESCE(SUM(CASE WHEN current_pool IN ('inactive_focus', 'active_focus') THEN 1 ELSE 0 END), 0) AS focus_followup,
            COALESCE(SUM(CASE WHEN current_pool = 'silent' THEN 1 ELSE 0 END), 0) AS silent_total,
            COALESCE(SUM(CASE WHEN current_pool = 'won' THEN 1 ELSE 0 END), 0) AS won_total
        FROM automation_member
        """
    ) or {}
    return {key: int(row.get(key) or 0) for key in row}


def get_latest_questionnaire_submission(
    *,
    questionnaire_id: int,
    external_contact_ids: list[str] | None = None,
    phone: str = "",
) -> dict[str, Any] | None:
    normalized_external_contact_ids = [
        _normalized_text(item) for item in (external_contact_ids or []) if _normalized_text(item)
    ]
    normalized_phone = _normalized_text(phone)
    filters: list[str] = []
    params: list[Any] = [int(questionnaire_id)]
    if normalized_external_contact_ids:
        placeholders = ",".join("?" for _ in normalized_external_contact_ids)
        filters.append(f"external_userid IN ({placeholders})")
        params.extend(normalized_external_contact_ids)
    if normalized_phone:
        filters.append("mobile_snapshot = ?")
        params.append(normalized_phone)
    if not filters:
        return None
    sql = """
    SELECT *
    FROM questionnaire_submissions
    WHERE questionnaire_id = ?
      AND (
    """
    sql += " OR ".join(filters)
    sql += """
      )
    ORDER BY submitted_at DESC, id DESC
    LIMIT 1
    """
    return _fetchone_dict(sql, tuple(params))


def list_questionnaire_submission_answers(submission_id: int) -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT *
        FROM questionnaire_submission_answers
        WHERE submission_id = ?
        ORDER BY id ASC
        """,
        (int(submission_id),),
    )


def list_stage_members(*, current_pool: str, keyword: str = "", limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    normalized_keyword = _normalized_text(keyword)
    params: list[Any] = [_normalized_text(current_pool)]
    sql = """
    SELECT *
    FROM automation_member
    WHERE current_pool = ?
    """
    if normalized_keyword:
        sql += """
          AND (
            external_contact_id LIKE ?
            OR phone LIKE ?
          )
        """
        like_value = f"%{normalized_keyword}%"
        params.extend([like_value, like_value])
    sql += """
    ORDER BY updated_at DESC, id DESC
    LIMIT ?
    OFFSET ?
    """
    params.extend([int(limit), int(offset)])
    return _fetchall_dicts(sql, tuple(params))


def count_stage_members(*, current_pool: str, keyword: str = "") -> int:
    normalized_keyword = _normalized_text(keyword)
    params: list[Any] = [_normalized_text(current_pool)]
    sql = """
    SELECT COUNT(*) AS total
    FROM automation_member
    WHERE current_pool = ?
    """
    if normalized_keyword:
        like_value = f"%{normalized_keyword}%"
        sql += """
          AND (
            external_contact_id LIKE ?
            OR phone LIKE ?
          )
        """
        params.extend([like_value, like_value])
    row = _fetchone_dict(sql, tuple(params)) or {}
    return int(row.get("total") or 0)


def list_members_for_silent_refresh() -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT *
        FROM automation_member
        WHERE in_pool = ?
          AND current_pool IN ('new_user', 'inactive_normal', 'inactive_focus', 'active_normal', 'active_focus')
        ORDER BY updated_at ASC, id ASC
        """,
        (_db_bool(True),),
    )


def list_members_for_message_activity_sync(*, current_pools: list[str]) -> list[dict[str, Any]]:
    normalized_pools = [_normalized_text(item) for item in current_pools if _normalized_text(item)]
    if not normalized_pools:
        return []
    placeholders = ",".join("?" for _ in normalized_pools)
    return _fetchall_dicts(
        f"""
        SELECT *
        FROM automation_member
        WHERE in_pool = ?
          AND current_pool IN ({placeholders})
        ORDER BY current_pool ASC, updated_at DESC, id ASC
        """,
        (_db_bool(True), *normalized_pools),
    )


def list_recent_debug_events(*, external_contact_id: str = "", phone: str = "", limit: int = 10) -> list[dict[str, Any]]:
    member = get_member_by_external_contact_id(external_contact_id) or get_member_by_phone(phone)
    if not member:
        return []
    return list_recent_events(int(member["id"]), limit=int(limit))


def deserialize_event_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "before_snapshot": _json_loads(row.get("before_snapshot"), default={}),
        "after_snapshot": _json_loads(row.get("after_snapshot"), default={}),
    }


def deserialize_ai_push_log_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "request_payload": _json_loads(row.get("request_payload"), default={}),
    }


def deserialize_message_activity_sync_run_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "summary_json": _json_loads(row.get("summary_json"), default={}),
    }


def deserialize_message_activity_sync_item_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "before_snapshot": _json_loads(row.get("before_snapshot"), default={}),
        "after_snapshot": _json_loads(row.get("after_snapshot"), default={}),
    }
