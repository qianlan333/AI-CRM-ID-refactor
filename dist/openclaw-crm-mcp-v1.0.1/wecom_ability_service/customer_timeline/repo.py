from __future__ import annotations

from typing import Any

from ..db import get_db


def _fetchall_dict(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in get_db().execute(sql, params).fetchall()]


def has_customer_timeline_scope(external_userid: str) -> bool:
    for table in [
        "contacts",
        "archived_messages",
        "class_user_status_history",
        "questionnaire_submissions",
        "wecom_external_contact_event_logs",
    ]:
        row = get_db().execute(
            f"SELECT 1 AS found FROM {table} WHERE external_userid = ? LIMIT 1",
            (external_userid,),
        ).fetchone()
        if row:
            return True
    return False


def fetch_archived_messages(external_userid: str) -> list[dict[str, Any]]:
    return _fetchall_dict(
        """
        SELECT id, seq, msgid, chat_type, external_userid, owner_userid, sender, receiver,
               msgtype, content, send_time, raw_payload, created_at
        FROM archived_messages
        WHERE external_userid = ?
        """,
        (external_userid,),
    )


def fetch_status_changes(external_userid: str) -> list[dict[str, Any]]:
    return _fetchall_dict(
        """
        SELECT id, external_userid, old_signup_status, new_signup_status, old_label_name, new_label_name,
               customer_name_snapshot, owner_userid_snapshot, mobile_snapshot, set_by_userid, set_at,
               wecom_tag_sync_status, wecom_tag_sync_error, status_flags_json, created_at
        FROM class_user_status_history
        WHERE external_userid = ?
        """,
        (external_userid,),
    )


def fetch_questionnaire_submissions(external_userid: str) -> list[dict[str, Any]]:
    return _fetchall_dict(
        """
        SELECT
            qs.id,
            qs.questionnaire_id,
            qs.respondent_key,
            qs.openid,
            qs.unionid,
            qs.external_userid,
            qs.follow_user_userid,
            qs.matched_by,
            qs.source_channel,
            qs.campaign_id,
            qs.staff_id,
            qs.total_score,
            qs.final_tags,
            qs.redirect_url_snapshot,
            qs.submitted_at,
            COALESCE(q.name, '') AS questionnaire_name,
            COALESCE(q.title, '') AS questionnaire_title
        FROM questionnaire_submissions qs
        LEFT JOIN questionnaires q ON q.id = qs.questionnaire_id
        WHERE qs.external_userid = ?
        """,
        (external_userid,),
    )


def fetch_wecom_events(external_userid: str) -> list[dict[str, Any]]:
    return _fetchall_dict(
        """
        SELECT id, corp_id, event_type, change_type, external_userid, user_id, event_time, event_key,
               payload_xml, payload_json, process_status, retry_count, error_message, created_at, updated_at
        FROM wecom_external_contact_event_logs
        WHERE external_userid = ?
        """,
        (external_userid,),
    )
