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


def _row_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return _normalized_text(value).lower() in {"1", "true", "yes", "y", "on"}


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
            phone_prefix3,
            phone_last4,
            phone_match_key,
            message_count,
            status,
            detail,
            before_snapshot,
            after_snapshot,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING *
        """,
        (
            int(payload.get("run_id") or 0),
            payload.get("member_id"),
            _normalized_text(payload.get("external_contact_id")),
            _normalized_text(payload.get("phone")),
            _normalized_text(payload.get("phone_prefix3")),
            _normalized_text(payload.get("phone_last4")),
            _normalized_text(payload.get("phone_match_key")),
            int(payload.get("message_count") or 0),
            _normalized_text(payload.get("status")),
            _normalized_text(payload.get("detail")),
            _json_dumps(payload.get("before_snapshot") or {}),
            _json_dumps(payload.get("after_snapshot") or {}),
            _normalized_text(payload.get("created_at")),
        ),
    ).fetchone()
    return dict(row) if row else {}


def get_latest_archived_message_storage_id() -> int:
    row = _fetchone_dict(
        """
        SELECT COALESCE(MAX(id), 0) AS latest_id
        FROM archived_messages
        """
    ) or {}
    return int(row.get("latest_id") or 0)


def list_archived_messages_after_storage_cursor(*, after_id: int, limit: int = 500) -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT id, msgid, chat_type, external_userid, owner_userid, sender, receiver, msgtype, content, send_time, raw_payload
        FROM archived_messages
        WHERE id > ?
        ORDER BY id ASC
        LIMIT ?
        """,
        (int(after_id), int(limit)),
    )


def list_archived_messages_by_ids(message_ids: list[int]) -> list[dict[str, Any]]:
    normalized_ids = [int(item) for item in message_ids if str(item).strip()]
    if not normalized_ids:
        return []
    placeholders = ",".join("?" for _ in normalized_ids)
    return _fetchall_dicts(
        f"""
        SELECT id, msgid, chat_type, external_userid, owner_userid, sender, receiver, msgtype, content, send_time, raw_payload
        FROM archived_messages
        WHERE id IN ({placeholders})
        ORDER BY id ASC
        """,
        tuple(normalized_ids),
    )


def list_active_automation_external_contact_ids(external_contact_ids: list[str]) -> list[str]:
    normalized_ids = [_normalized_text(item) for item in external_contact_ids if _normalized_text(item)]
    if not normalized_ids:
        return []
    placeholders = ",".join("?" for _ in normalized_ids)
    rows = _fetchall_dicts(
        f"""
        SELECT external_contact_id
        FROM automation_member
        WHERE in_pool = ?
          AND external_contact_id IN ({placeholders})
        ORDER BY external_contact_id ASC
        """,
        (_db_bool(True), *normalized_ids),
    )
    return [_normalized_text(row.get("external_contact_id")) for row in rows if _normalized_text(row.get("external_contact_id"))]


def list_active_automation_members_by_external_contact_ids(external_contact_ids: list[str]) -> list[dict[str, Any]]:
    normalized_ids = [_normalized_text(item) for item in external_contact_ids if _normalized_text(item)]
    if not normalized_ids:
        return []
    placeholders = ",".join("?" for _ in normalized_ids)
    return _fetchall_dicts(
        f"""
        SELECT *
        FROM automation_member
        WHERE in_pool = ?
          AND external_contact_id IN ({placeholders})
        ORDER BY updated_at DESC, id DESC
        """,
        (_db_bool(True), *normalized_ids),
    )


def get_reply_monitor_config() -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_reply_monitor_config
        WHERE config_key = 'default'
        LIMIT 1
        """
    )


def save_reply_monitor_config(payload: dict[str, Any]) -> dict[str, Any]:
    existing = get_reply_monitor_config()
    db = get_db()
    if existing:
        row = db.execute(
            """
            UPDATE automation_reply_monitor_config
            SET enabled = ?,
                last_capture_cursor = ?,
                last_capture_at = ?,
                last_capture_status = ?,
                last_capture_summary_json = ?,
                last_dispatch_at = ?,
                last_dispatch_status = ?,
                last_dispatch_summary_json = ?,
                last_error = ?,
                quiet_hours_start = ?,
                quiet_hours_end = ?,
                dispatch_interval_seconds = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            RETURNING *
            """,
            (
                _db_bool(bool(payload.get("enabled"))),
                int(payload.get("last_capture_cursor") or 0),
                _normalized_text(payload.get("last_capture_at")),
                _normalized_text(payload.get("last_capture_status")),
                _json_dumps(payload.get("last_capture_summary_json") or {}),
                _normalized_text(payload.get("last_dispatch_at")),
                _normalized_text(payload.get("last_dispatch_status")),
                _json_dumps(payload.get("last_dispatch_summary_json") or {}),
                _normalized_text(payload.get("last_error")),
                _normalized_text(payload.get("quiet_hours_start")),
                _normalized_text(payload.get("quiet_hours_end")),
                int(payload.get("dispatch_interval_seconds") or 0),
                int(existing["id"]),
            ),
        ).fetchone()
        return dict(row) if row else {}
    row = db.execute(
        """
        INSERT INTO automation_reply_monitor_config (
            config_key,
            enabled,
            last_capture_cursor,
            last_capture_at,
            last_capture_status,
            last_capture_summary_json,
            last_dispatch_at,
            last_dispatch_status,
            last_dispatch_summary_json,
            last_error,
            quiet_hours_start,
            quiet_hours_end,
            dispatch_interval_seconds,
            created_at,
            updated_at
        )
        VALUES ('default', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            _db_bool(bool(payload.get("enabled"))),
            int(payload.get("last_capture_cursor") or 0),
            _normalized_text(payload.get("last_capture_at")),
            _normalized_text(payload.get("last_capture_status")),
            _json_dumps(payload.get("last_capture_summary_json") or {}),
            _normalized_text(payload.get("last_dispatch_at")),
            _normalized_text(payload.get("last_dispatch_status")),
            _json_dumps(payload.get("last_dispatch_summary_json") or {}),
            _normalized_text(payload.get("last_error")),
            _normalized_text(payload.get("quiet_hours_start")),
            _normalized_text(payload.get("quiet_hours_end")),
            int(payload.get("dispatch_interval_seconds") or 0),
        ),
    ).fetchone()
    return dict(row) if row else {}


def get_reply_monitor_queue_item(queue_id: int) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_reply_monitor_queue
        WHERE id = ?
        LIMIT 1
        """,
        (int(queue_id),),
    )


def get_active_reply_monitor_queue_item(external_userid: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_reply_monitor_queue
        WHERE external_userid = ?
          AND status IN ('pending', 'deferred_quiet_hours', 'paused')
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (_normalized_text(external_userid),),
    )


def insert_reply_monitor_queue_item(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_reply_monitor_queue (
            member_id,
            external_userid,
            owner_userid,
            status,
            message_ids_json,
            message_count,
            first_inbound_at,
            last_inbound_at,
            not_before,
            last_dispatch_at,
            error_message,
            payload_snapshot_json,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            payload.get("member_id"),
            _normalized_text(payload.get("external_userid")),
            _normalized_text(payload.get("owner_userid")),
            _normalized_text(payload.get("status")),
            _json_dumps(payload.get("message_ids_json") or []),
            int(payload.get("message_count") or 0),
            _normalized_text(payload.get("first_inbound_at")),
            _normalized_text(payload.get("last_inbound_at")),
            _normalized_text(payload.get("not_before")),
            _normalized_text(payload.get("last_dispatch_at")),
            _normalized_text(payload.get("error_message")),
            _json_dumps(payload.get("payload_snapshot_json") or {}),
        ),
    ).fetchone()
    return dict(row) if row else {}


def update_reply_monitor_queue_item(queue_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE automation_reply_monitor_queue
        SET member_id = ?,
            external_userid = ?,
            owner_userid = ?,
            status = ?,
            message_ids_json = ?,
            message_count = ?,
            first_inbound_at = ?,
            last_inbound_at = ?,
            not_before = ?,
            last_dispatch_at = ?,
            error_message = ?,
            payload_snapshot_json = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        RETURNING *
        """,
        (
            payload.get("member_id"),
            _normalized_text(payload.get("external_userid")),
            _normalized_text(payload.get("owner_userid")),
            _normalized_text(payload.get("status")),
            _json_dumps(payload.get("message_ids_json") or []),
            int(payload.get("message_count") or 0),
            _normalized_text(payload.get("first_inbound_at")),
            _normalized_text(payload.get("last_inbound_at")),
            _normalized_text(payload.get("not_before")),
            _normalized_text(payload.get("last_dispatch_at")),
            _normalized_text(payload.get("error_message")),
            _json_dumps(payload.get("payload_snapshot_json") or {}),
            int(queue_id),
        ),
    ).fetchone()
    return dict(row) if row else {}


def list_due_reply_monitor_queue_items(*, now_text: str, limit: int = 20) -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT *
        FROM automation_reply_monitor_queue
        WHERE status IN ('pending', 'deferred_quiet_hours')
          AND not_before <> ''
          AND not_before <= ?
        ORDER BY not_before ASC, id ASC
        LIMIT ?
        """,
        (_normalized_text(now_text), int(limit)),
    )


def list_recent_reply_monitor_queue_items(*, limit: int = 20) -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT *
        FROM automation_reply_monitor_queue
        ORDER BY updated_at DESC, id DESC
        LIMIT ?
        """,
        (int(limit),),
    )


def get_reply_monitor_queue_counts() -> dict[str, int]:
    rows = _fetchall_dicts(
        """
        SELECT status, COUNT(*) AS total
        FROM automation_reply_monitor_queue
        GROUP BY status
        """
    )
    counts = {
        "pending": 0,
        "deferred_quiet_hours": 0,
        "dispatched": 0,
        "failed": 0,
        "paused": 0,
    }
    for row in rows:
        status = _normalized_text(row.get("status"))
        if status in counts:
            counts[status] = int(row.get("total") or 0)
    counts["active_total"] = counts["pending"] + counts["deferred_quiet_hours"] + counts["paused"]
    return counts


def get_latest_reply_monitor_not_before() -> str:
    row = _fetchone_dict(
        """
        SELECT not_before
        FROM automation_reply_monitor_queue
        WHERE status IN ('pending', 'deferred_quiet_hours', 'paused')
        ORDER BY not_before DESC, id DESC
        LIMIT 1
        """
    ) or {}
    return _normalized_text(row.get("not_before"))


def insert_focus_send_batch(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_focus_send_batch (
            stage_key,
            pool_key,
            operator_type,
            operator_id,
            status,
            total_count,
            sent_count,
            failed_count,
            skipped_count,
            cancelled_count,
            next_run_at,
            last_run_at,
            created_at,
            updated_at,
            finished_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING *
        """,
        (
            _normalized_text(payload.get("stage_key")),
            _normalized_text(payload.get("pool_key")),
            _normalized_text(payload.get("operator_type")),
            _normalized_text(payload.get("operator_id")),
            _normalized_text(payload.get("status")),
            int(payload.get("total_count") or 0),
            int(payload.get("sent_count") or 0),
            int(payload.get("failed_count") or 0),
            int(payload.get("skipped_count") or 0),
            int(payload.get("cancelled_count") or 0),
            _normalized_text(payload.get("next_run_at")),
            _normalized_text(payload.get("last_run_at")),
            _normalized_text(payload.get("created_at")),
            _normalized_text(payload.get("updated_at")),
            _normalized_text(payload.get("finished_at")),
        ),
    ).fetchone()
    return dict(row) if row else {}


def update_focus_send_batch(batch_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE automation_focus_send_batch
        SET stage_key = ?,
            pool_key = ?,
            operator_type = ?,
            operator_id = ?,
            status = ?,
            total_count = ?,
            sent_count = ?,
            failed_count = ?,
            skipped_count = ?,
            cancelled_count = ?,
            next_run_at = ?,
            last_run_at = ?,
            updated_at = ?,
            finished_at = ?
        WHERE id = ?
        RETURNING *
        """,
        (
            _normalized_text(payload.get("stage_key")),
            _normalized_text(payload.get("pool_key")),
            _normalized_text(payload.get("operator_type")),
            _normalized_text(payload.get("operator_id")),
            _normalized_text(payload.get("status")),
            int(payload.get("total_count") or 0),
            int(payload.get("sent_count") or 0),
            int(payload.get("failed_count") or 0),
            int(payload.get("skipped_count") or 0),
            int(payload.get("cancelled_count") or 0),
            _normalized_text(payload.get("next_run_at")),
            _normalized_text(payload.get("last_run_at")),
            _normalized_text(payload.get("updated_at")),
            _normalized_text(payload.get("finished_at")),
            int(batch_id),
        ),
    ).fetchone()
    return dict(row) if row else {}


def get_focus_send_batch(batch_id: int) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_focus_send_batch
        WHERE id = ?
        LIMIT 1
        """,
        (int(batch_id),),
    )


def find_active_focus_send_batch_by_stage(stage_key: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_focus_send_batch
        WHERE stage_key = ?
          AND status IN ('pending', 'running')
        ORDER BY id DESC
        LIMIT 1
        """,
        (_normalized_text(stage_key),),
    )


def list_due_focus_send_batches(*, due_at: str, limit: int = 20) -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT *
        FROM automation_focus_send_batch
        WHERE status IN ('pending', 'running')
          AND (next_run_at = '' OR next_run_at <= ?)
        ORDER BY id ASC
        LIMIT ?
        """,
        (_normalized_text(due_at), int(limit)),
    )


def insert_focus_send_batch_item(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_focus_send_batch_item (
            batch_id,
            member_id,
            external_contact_id,
            phone,
            position_index,
            status,
            detail,
            result_payload,
            created_at,
            updated_at,
            started_at,
            finished_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING *
        """,
        (
            int(payload.get("batch_id") or 0),
            payload.get("member_id"),
            _normalized_text(payload.get("external_contact_id")),
            _normalized_text(payload.get("phone")),
            int(payload.get("position_index") or 0),
            _normalized_text(payload.get("status")),
            _normalized_text(payload.get("detail")),
            _json_dumps(payload.get("result_payload") or {}),
            _normalized_text(payload.get("created_at")),
            _normalized_text(payload.get("updated_at")),
            _normalized_text(payload.get("started_at")),
            _normalized_text(payload.get("finished_at")),
        ),
    ).fetchone()
    return dict(row) if row else {}


def update_focus_send_batch_item(item_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE automation_focus_send_batch_item
        SET member_id = ?,
            external_contact_id = ?,
            phone = ?,
            position_index = ?,
            status = ?,
            detail = ?,
            result_payload = ?,
            updated_at = ?,
            started_at = ?,
            finished_at = ?
        WHERE id = ?
        RETURNING *
        """,
        (
            payload.get("member_id"),
            _normalized_text(payload.get("external_contact_id")),
            _normalized_text(payload.get("phone")),
            int(payload.get("position_index") or 0),
            _normalized_text(payload.get("status")),
            _normalized_text(payload.get("detail")),
            _json_dumps(payload.get("result_payload") or {}),
            _normalized_text(payload.get("updated_at")),
            _normalized_text(payload.get("started_at")),
            _normalized_text(payload.get("finished_at")),
            int(item_id),
        ),
    ).fetchone()
    return dict(row) if row else {}


def list_focus_send_batch_items(*, batch_id: int, limit: int = 100, descending: bool = False) -> list[dict[str, Any]]:
    return _fetchall_dicts(
        f"""
        SELECT *
        FROM automation_focus_send_batch_item
        WHERE batch_id = ?
        ORDER BY position_index {'DESC' if descending else 'ASC'}, id {'DESC' if descending else 'ASC'}
        LIMIT ?
        """,
        (int(batch_id), int(limit)),
    )


def claim_next_focus_send_batch_item(*, batch_id: int, started_at: str) -> dict[str, Any] | None:
    candidate = _fetchone_dict(
        """
        SELECT *
        FROM automation_focus_send_batch_item
        WHERE batch_id = ?
          AND status = 'pending'
        ORDER BY position_index ASC, id ASC
        LIMIT 1
        """,
        (int(batch_id),),
    )
    if not candidate:
        return None
    row = get_db().execute(
        """
        UPDATE automation_focus_send_batch_item
        SET status = 'running',
            updated_at = ?,
            started_at = ?
        WHERE id = ?
          AND status = 'pending'
        RETURNING *
        """,
        (
            _normalized_text(started_at),
            _normalized_text(started_at),
            int(candidate["id"]),
        ),
    ).fetchone()
    return dict(row) if row else None


def list_sop_pool_configs() -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT *
        FROM automation_sop_pool_config
        ORDER BY pool_key ASC, id ASC
        """
    )


def get_sop_pool_config(pool_key: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_sop_pool_config
        WHERE pool_key = ?
        LIMIT 1
        """,
        (_normalized_text(pool_key),),
    )


def save_sop_pool_config(payload: dict[str, Any]) -> dict[str, Any]:
    existing = get_sop_pool_config(_normalized_text(payload.get("pool_key")))
    db = get_db()
    if existing:
        row = db.execute(
            """
            UPDATE automation_sop_pool_config
            SET enabled = ?,
                max_day_count = ?,
                send_time = ?,
                timezone = ?,
                effective_start_at = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            RETURNING *
            """,
            (
                _db_bool(bool(payload.get("enabled"))),
                int(payload.get("max_day_count") or 0),
                _normalized_text(payload.get("send_time")),
                _normalized_text(payload.get("timezone")),
                _normalized_text(payload.get("effective_start_at")),
                int(existing["id"]),
            ),
        ).fetchone()
        return dict(row) if row else {}
    row = db.execute(
        """
        INSERT INTO automation_sop_pool_config (
            pool_key,
            enabled,
            max_day_count,
            send_time,
            timezone,
            effective_start_at,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            _normalized_text(payload.get("pool_key")),
            _db_bool(bool(payload.get("enabled"))),
            int(payload.get("max_day_count") or 0),
            _normalized_text(payload.get("send_time")),
            _normalized_text(payload.get("timezone")),
            _normalized_text(payload.get("effective_start_at")),
        ),
    ).fetchone()
    return dict(row) if row else {}


def list_sop_templates(*, pool_key: str = "") -> list[dict[str, Any]]:
    normalized_pool_key = _normalized_text(pool_key)
    if normalized_pool_key:
        return _fetchall_dicts(
            """
            SELECT *
            FROM automation_sop_template
            WHERE pool_key = ?
            ORDER BY day_index ASC, id ASC
            """,
            (normalized_pool_key,),
        )
    return _fetchall_dicts(
        """
        SELECT *
        FROM automation_sop_template
        ORDER BY pool_key ASC, day_index ASC, id ASC
        """
    )


def get_sop_template(*, pool_key: str, day_index: int) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_sop_template
        WHERE pool_key = ?
          AND day_index = ?
        LIMIT 1
        """,
        (_normalized_text(pool_key), int(day_index)),
    )


def save_sop_template(payload: dict[str, Any]) -> dict[str, Any]:
    existing = get_sop_template(
        pool_key=_normalized_text(payload.get("pool_key")),
        day_index=int(payload.get("day_index") or 0),
    )
    db = get_db()
    if existing:
        row = db.execute(
            """
            UPDATE automation_sop_template
            SET content = ?,
                images_json = ?,
                enabled = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            RETURNING *
            """,
            (
                _normalized_text(payload.get("content")),
                _json_dumps(payload.get("images_json") or []),
                _db_bool(bool(payload.get("enabled"))),
                int(existing["id"]),
            ),
        ).fetchone()
        return dict(row) if row else {}
    row = db.execute(
        """
        INSERT INTO automation_sop_template (
            pool_key,
            day_index,
            content,
            images_json,
            enabled,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            _normalized_text(payload.get("pool_key")),
            int(payload.get("day_index") or 0),
            _normalized_text(payload.get("content")),
            _json_dumps(payload.get("images_json") or []),
            _db_bool(bool(payload.get("enabled"))),
        ),
    ).fetchone()
    return dict(row) if row else {}


def delete_sop_template_day(*, pool_key: str, day_index: int) -> None:
    normalized_pool_key = _normalized_text(pool_key)
    normalized_day_index = int(day_index)
    db = get_db()
    db.execute(
        """
        DELETE FROM automation_sop_template
        WHERE pool_key = ?
          AND day_index = ?
        """,
        (normalized_pool_key, normalized_day_index),
    )
    db.execute(
        """
        UPDATE automation_sop_template
        SET day_index = day_index + 1000,
            updated_at = CURRENT_TIMESTAMP
        WHERE pool_key = ?
          AND day_index > ?
        """,
        (normalized_pool_key, normalized_day_index),
    )
    db.execute(
        """
        UPDATE automation_sop_template
        SET day_index = day_index - 1001,
            updated_at = CURRENT_TIMESTAMP
        WHERE pool_key = ?
          AND day_index > ?
        """,
        (normalized_pool_key, normalized_day_index + 1000),
    )


def get_sop_progress(*, member_id: int, pool_key: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_sop_progress
        WHERE member_id = ?
          AND pool_key = ?
        LIMIT 1
        """,
        (int(member_id), _normalized_text(pool_key)),
    )


def list_sop_progress_for_members(*, member_ids: list[int] | None = None, pool_key: str = "") -> list[dict[str, Any]]:
    normalized_member_ids = [int(item) for item in (member_ids or []) if str(item).strip()]
    normalized_pool_key = _normalized_text(pool_key)
    params: list[Any] = []
    sql = """
    SELECT *
    FROM automation_sop_progress
    WHERE 1 = 1
    """
    if normalized_member_ids:
        placeholders = ",".join("?" for _ in normalized_member_ids)
        sql += f" AND member_id IN ({placeholders})"
        params.extend(normalized_member_ids)
    if normalized_pool_key:
        sql += " AND pool_key = ?"
        params.append(normalized_pool_key)
    sql += " ORDER BY pool_key ASC, member_id ASC, id ASC"
    return _fetchall_dicts(sql, tuple(params))


def save_sop_progress(payload: dict[str, Any]) -> dict[str, Any]:
    existing = get_sop_progress(
        member_id=int(payload.get("member_id") or 0),
        pool_key=_normalized_text(payload.get("pool_key")),
    )
    db = get_db()
    if existing:
        row = db.execute(
            """
            UPDATE automation_sop_progress
            SET first_entered_at = ?,
                last_entered_at = ?,
                sop_anchor_date = ?,
                first_effective_in_pool_at = ?,
                last_in_pool_at = ?,
                last_sent_day = ?,
                last_sent_at = ?,
                completed_at = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            RETURNING *
            """,
            (
                _normalized_text(payload.get("first_entered_at")),
                _normalized_text(payload.get("last_entered_at")),
                _normalized_text(payload.get("sop_anchor_date")),
                _normalized_text(payload.get("first_effective_in_pool_at")),
                _normalized_text(payload.get("last_in_pool_at")),
                int(payload.get("last_sent_day") or 0),
                _normalized_text(payload.get("last_sent_at")),
                _normalized_text(payload.get("completed_at")),
                int(existing["id"]),
            ),
        ).fetchone()
        return dict(row) if row else {}
    row = db.execute(
        """
        INSERT INTO automation_sop_progress (
            member_id,
            pool_key,
            first_entered_at,
            last_entered_at,
            sop_anchor_date,
            first_effective_in_pool_at,
            last_in_pool_at,
            last_sent_day,
            last_sent_at,
            completed_at,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            int(payload.get("member_id") or 0),
            _normalized_text(payload.get("pool_key")),
            _normalized_text(payload.get("first_entered_at")),
            _normalized_text(payload.get("last_entered_at")),
            _normalized_text(payload.get("sop_anchor_date")),
            _normalized_text(payload.get("first_effective_in_pool_at")),
            _normalized_text(payload.get("last_in_pool_at")),
            int(payload.get("last_sent_day") or 0),
            _normalized_text(payload.get("last_sent_at")),
            _normalized_text(payload.get("completed_at")),
        ),
    ).fetchone()
    return dict(row) if row else {}


def insert_sop_batch(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_sop_batch (
            pool_key,
            day_index,
            template_id,
            scheduled_for,
            status,
            total_count,
            success_count,
            skipped_count,
            failed_count,
            summary_json,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            _normalized_text(payload.get("pool_key")),
            int(payload.get("day_index") or 0),
            payload.get("template_id"),
            _normalized_text(payload.get("scheduled_for")),
            _normalized_text(payload.get("status")),
            int(payload.get("total_count") or 0),
            int(payload.get("success_count") or 0),
            int(payload.get("skipped_count") or 0),
            int(payload.get("failed_count") or 0),
            _json_dumps(payload.get("summary_json") or {}),
        ),
    ).fetchone()
    return dict(row) if row else {}


def update_sop_batch(batch_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE automation_sop_batch
        SET pool_key = ?,
            day_index = ?,
            template_id = ?,
            scheduled_for = ?,
            status = ?,
            total_count = ?,
            success_count = ?,
            skipped_count = ?,
            failed_count = ?,
            summary_json = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        RETURNING *
        """,
        (
            _normalized_text(payload.get("pool_key")),
            int(payload.get("day_index") or 0),
            payload.get("template_id"),
            _normalized_text(payload.get("scheduled_for")),
            _normalized_text(payload.get("status")),
            int(payload.get("total_count") or 0),
            int(payload.get("success_count") or 0),
            int(payload.get("skipped_count") or 0),
            int(payload.get("failed_count") or 0),
            _json_dumps(payload.get("summary_json") or {}),
            int(batch_id),
        ),
    ).fetchone()
    return dict(row) if row else {}


def get_sop_batch(batch_id: int) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_sop_batch
        WHERE id = ?
        LIMIT 1
        """,
        (int(batch_id),),
    )


def list_sop_batches(*, pool_key: str = "", limit: int = 50) -> list[dict[str, Any]]:
    normalized_pool_key = _normalized_text(pool_key)
    params: list[Any] = []
    sql = """
    SELECT *
    FROM automation_sop_batch
    WHERE 1 = 1
    """
    if normalized_pool_key:
        sql += " AND pool_key = ?"
        params.append(normalized_pool_key)
    sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
    params.append(max(1, int(limit)))
    return _fetchall_dicts(sql, tuple(params))


def get_successful_sop_batch_item(*, member_id: int, pool_key: str, day_index: int) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_sop_batch_item
        WHERE member_id = ?
          AND pool_key = ?
          AND day_index = ?
          AND status = 'success'
        ORDER BY id DESC
        LIMIT 1
        """,
        (int(member_id), _normalized_text(pool_key), int(day_index)),
    )


def get_sop_batch_item_for_member_day(*, member_id: int, pool_key: str, day_index_snapshot: int) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_sop_batch_item
        WHERE member_id = ?
          AND pool_key = ?
          AND day_index_snapshot = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (int(member_id), _normalized_text(pool_key), int(day_index_snapshot)),
    )


def insert_sop_batch_item(payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        INSERT INTO automation_sop_batch_item (
            batch_id,
            member_id,
            pool_key,
            day_index,
            day_index_snapshot,
            external_userid,
            status,
            error_message,
            content_snapshot,
            images_snapshot,
            sent_record_id,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        (
            int(payload.get("batch_id") or 0),
            payload.get("member_id"),
            _normalized_text(payload.get("pool_key")),
            int(payload.get("day_index") or 0),
            int(payload.get("day_index_snapshot") or payload.get("day_index") or 0),
            _normalized_text(payload.get("external_userid")),
            _normalized_text(payload.get("status")),
            _normalized_text(payload.get("error_message")),
            _normalized_text(payload.get("content_snapshot")),
            _json_dumps(payload.get("images_snapshot") or []),
            payload.get("sent_record_id"),
        ),
    ).fetchone()
    return dict(row) if row else {}


def update_sop_batch_item(item_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    row = get_db().execute(
        """
        UPDATE automation_sop_batch_item
        SET batch_id = ?,
            member_id = ?,
            pool_key = ?,
            day_index = ?,
            day_index_snapshot = ?,
            external_userid = ?,
            status = ?,
            error_message = ?,
            content_snapshot = ?,
            images_snapshot = ?,
            sent_record_id = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        RETURNING *
        """,
        (
            int(payload.get("batch_id") or 0),
            payload.get("member_id"),
            _normalized_text(payload.get("pool_key")),
            int(payload.get("day_index") or 0),
            int(payload.get("day_index_snapshot") or payload.get("day_index") or 0),
            _normalized_text(payload.get("external_userid")),
            _normalized_text(payload.get("status")),
            _normalized_text(payload.get("error_message")),
            _normalized_text(payload.get("content_snapshot")),
            _json_dumps(payload.get("images_snapshot") or []),
            payload.get("sent_record_id"),
            int(item_id),
        ),
    ).fetchone()
    return dict(row) if row else {}


def list_sop_batch_items(*, batch_id: int, limit: int = 200) -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT *
        FROM automation_sop_batch_item
        WHERE batch_id = ?
        ORDER BY id ASC
        LIMIT ?
        """,
        (int(batch_id), max(1, int(limit))),
    )


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
        _normalized_text(payload.get("welcome_message")),
        _db_bool(bool(payload.get("auto_accept_friend"))),
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
                welcome_message = ?,
                auto_accept_friend = ?,
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
                _normalized_text(payload.get("welcome_message")),
                _db_bool(bool(payload.get("auto_accept_friend"))),
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
            welcome_message,
            auto_accept_friend,
            owner_staff_id,
            status,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
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


def list_stage_members_for_manual_send(*, current_pool: str) -> list[dict[str, Any]]:
    return _fetchall_dicts(
        """
        SELECT *
        FROM automation_member
        WHERE current_pool = ?
        ORDER BY updated_at DESC, id DESC
        """,
        (_normalized_text(current_pool),),
    )


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


def deserialize_reply_monitor_config_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "enabled": _row_bool(row.get("enabled")),
        "last_capture_summary_json": _json_loads(row.get("last_capture_summary_json"), default={}),
        "last_dispatch_summary_json": _json_loads(row.get("last_dispatch_summary_json"), default={}),
    }


def deserialize_reply_monitor_queue_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "message_ids_json": _json_loads(row.get("message_ids_json"), default=[]),
        "payload_snapshot_json": _json_loads(row.get("payload_snapshot_json"), default={}),
    }


def deserialize_focus_send_batch_row(row: dict[str, Any]) -> dict[str, Any]:
    return dict(row or {})


def deserialize_focus_send_batch_item_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "result_payload": _json_loads(row.get("result_payload"), default={}),
    }


def deserialize_sop_template_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "images_json": _json_loads(row.get("images_json"), default=[]),
        "enabled": _row_bool(row.get("enabled")),
    }


def deserialize_sop_progress_row(row: dict[str, Any]) -> dict[str, Any]:
    return dict(row or {})


def deserialize_sop_batch_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "summary_json": _json_loads(row.get("summary_json"), default={}),
    }


def deserialize_sop_batch_item_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **dict(row or {}),
        "images_snapshot": _json_loads((row or {}).get("images_snapshot"), default=[]),
    }
