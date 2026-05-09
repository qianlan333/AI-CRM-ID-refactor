"""Cross-domain glue data-access for customer_pulse (阶段 5.1).

Extracted from repo.py. Reads referential data from peer domains
(reply_monitor / archived_messages / questionnaire / conversion_dispatch /
class_user / customer_marketing / external_contact) for customer_pulse
inbox/dashboard rendering.

External callers keep using ``customer_pulse.repo.X``.
"""

from __future__ import annotations

from typing import Any

from ._repo_helpers import (  # noqa: F401  shared helpers
    _fetchall_dict,
    _fetchone_dict,
    _normalized_text,
)


def get_latest_reply_monitor_row(external_userid: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_reply_monitor_queue
        WHERE external_userid = ?
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (_normalized_text(external_userid),),
    )


def get_latest_ai_output_row(external_userid: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM automation_agent_output
        WHERE external_contact_id = ?
          AND output_type IN ('next_action_suggestion', 'agent_reply_draft', 'agent_reply_final')
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (_normalized_text(external_userid),),
    )


def get_customer_marketing_state_current(external_userid: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM customer_marketing_state_current
        WHERE external_userid = ?
        LIMIT 1
        """,
        (_normalized_text(external_userid),),
    )


def get_class_user_status_current(external_userid: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM class_user_status_current
        WHERE external_userid = ?
        LIMIT 1
        """,
        (_normalized_text(external_userid),),
    )


def get_customer_owner_binding(external_userid: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT
            external_userid,
            COALESCE(first_owner_userid, '') AS first_owner_userid,
            COALESCE(last_owner_userid, '') AS last_owner_userid,
            COALESCE(updated_at::text, \'\') AS updated_at
        FROM external_contact_bindings
        WHERE external_userid = ?
        LIMIT 1
        """,
        (_normalized_text(external_userid),),
    )


def list_contact_tag_rows(external_userid: str, *, limit: int = 20) -> list[dict[str, Any]]:
    return _fetchall_dict(
        """
        SELECT external_userid, userid, tag_id, COALESCE(tag_name, '') AS tag_name, created_at
        FROM contact_tags
        WHERE external_userid = ?
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (_normalized_text(external_userid), max(1, min(int(limit), 100))),
    )


def list_recent_archived_message_rows(external_userid: str, *, limit: int = 20) -> list[dict[str, Any]]:
    return _fetchall_dict(
        """
        SELECT id, seq, msgid, chat_type, external_userid, owner_userid, sender, receiver,
               msgtype, content, send_time, raw_payload, created_at
        FROM archived_messages
        WHERE external_userid = ?
        ORDER BY send_time DESC, id DESC
        LIMIT ?
        """,
        (_normalized_text(external_userid), max(1, min(int(limit), 100))),
    )


def list_recent_questionnaire_rows(external_userid: str, *, limit: int = 5) -> list[dict[str, Any]]:
    return _fetchall_dict(
        """
        SELECT
            qs.id,
            qs.questionnaire_id,
            qs.external_userid,
            qs.follow_user_userid,
            qs.total_score,
            qs.final_tags,
            qs.submitted_at,
            COALESCE(q.name, '') AS questionnaire_name,
            COALESCE(q.title, '') AS questionnaire_title,
            COALESCE(apply_logs.status, '') AS scrm_apply_status,
            COALESCE(apply_logs.error_message, '') AS scrm_apply_error,
            COALESCE(apply_logs.created_at::text, \'\') AS scrm_apply_at
        FROM questionnaire_submissions qs
        LEFT JOIN questionnaires q ON q.id = qs.questionnaire_id
        LEFT JOIN questionnaire_scrm_apply_logs apply_logs
          ON apply_logs.id = (
                SELECT inner_logs.id
                FROM questionnaire_scrm_apply_logs inner_logs
                WHERE inner_logs.submission_id = qs.id
                ORDER BY inner_logs.id DESC
                LIMIT 1
             )
        WHERE qs.external_userid = ?
        ORDER BY qs.submitted_at DESC, qs.id DESC
        LIMIT ?
        """,
        (_normalized_text(external_userid), max(1, min(int(limit), 20))),
    )


def list_recent_conversion_dispatch_rows(external_userid: str, *, limit: int = 5) -> list[dict[str, Any]]:
    return _fetchall_dict(
        """
        SELECT
            id,
            automation_key,
            batch_id,
            external_userid,
            dispatch_status,
            dispatch_channel,
            dispatch_payload_json,
            dispatch_note,
            dispatched_at,
            acked_at,
            created_at,
            updated_at
        FROM conversion_dispatch_log
        WHERE external_userid = ?
        ORDER BY COALESCE(dispatched_at, acked_at, updated_at, created_at) DESC, id DESC
        LIMIT ?
        """,
        (_normalized_text(external_userid), max(1, min(int(limit), 20))),
    )


def get_reply_monitor_row_by_id(source_id: str, *, external_userid: str) -> dict[str, Any] | None:
    normalized_source_id = _normalized_text(source_id)
    normalized_external_userid = _normalized_text(external_userid)
    if not normalized_source_id or not normalized_external_userid:
        return None
    return _fetchone_dict(
        """
        SELECT id, external_userid, owner_userid, status, message_count, first_inbound_at, last_inbound_at, not_before, updated_at
        FROM automation_reply_monitor_queue
        WHERE external_userid = ?
          AND CAST(id AS TEXT) = ?
        LIMIT 1
        """,
        (normalized_external_userid, normalized_source_id),
    )


def get_questionnaire_submission_ref_row(source_id: str, *, external_userid: str) -> dict[str, Any] | None:
    normalized_source_id = _normalized_text(source_id)
    normalized_external_userid = _normalized_text(external_userid)
    if not normalized_source_id or not normalized_external_userid:
        return None
    return _fetchone_dict(
        """
        SELECT id, questionnaire_id, external_userid, follow_user_userid, total_score, submitted_at
        FROM questionnaire_submissions
        WHERE external_userid = ?
          AND CAST(id AS TEXT) = ?
        LIMIT 1
        """,
        (normalized_external_userid, normalized_source_id),
    )


def get_conversion_dispatch_ref_row(source_id: str, *, external_userid: str) -> dict[str, Any] | None:
    normalized_source_id = _normalized_text(source_id)
    normalized_external_userid = _normalized_text(external_userid)
    if not normalized_source_id or not normalized_external_userid:
        return None
    return _fetchone_dict(
        """
        SELECT id, external_userid, dispatch_status, dispatch_channel, dispatch_note, dispatched_at, updated_at
        FROM conversion_dispatch_log
        WHERE external_userid = ?
          AND CAST(id AS TEXT) = ?
        LIMIT 1
        """,
        (normalized_external_userid, normalized_source_id),
    )


def get_customer_marketing_state_ref_row(source_id: str, *, external_userid: str) -> dict[str, Any] | None:
    normalized_source_id = _normalized_text(source_id)
    normalized_external_userid = _normalized_text(external_userid)
    if not normalized_external_userid:
        return None
    if normalized_source_id:
        row = _fetchone_dict(
            """
            SELECT id, external_userid, main_stage, sub_stage, updated_at
            FROM customer_marketing_state_current
            WHERE external_userid = ?
              AND CAST(id AS TEXT) = ?
            LIMIT 1
            """,
            (normalized_external_userid, normalized_source_id),
        )
        if row:
            return row
        row = _fetchone_dict(
            """
            SELECT id, external_userid, segment, score, updated_at
            FROM customer_value_segment_current
            WHERE external_userid = ?
              AND CAST(id AS TEXT) = ?
            LIMIT 1
            """,
            (normalized_external_userid, normalized_source_id),
        )
        if row:
            return row
    return _fetchone_dict(
        """
        SELECT id, external_userid, main_stage, sub_stage, updated_at
        FROM customer_marketing_state_current
        WHERE external_userid = ?
        LIMIT 1
        """,
        (normalized_external_userid,),
    )


def get_external_contact_binding_ref_row(source_id: str, *, external_userid: str) -> dict[str, Any] | None:
    normalized_external_userid = _normalized_text(external_userid)
    normalized_source_id = _normalized_text(source_id)
    if not normalized_external_userid:
        return None
    if normalized_source_id and normalized_source_id != normalized_external_userid:
        return None
    return _fetchone_dict(
        """
        SELECT external_userid, person_id, first_owner_userid, last_owner_userid, updated_at
        FROM external_contact_bindings
        WHERE external_userid = ?
        LIMIT 1
        """,
        (normalized_external_userid,),
    )




__all__ = [
    "get_class_user_status_current",
    "get_conversion_dispatch_ref_row",
    "get_customer_marketing_state_current",
    "get_customer_marketing_state_ref_row",
    "get_customer_owner_binding",
    "get_external_contact_binding_ref_row",
    "get_latest_ai_output_row",
    "get_latest_reply_monitor_row",
    "get_questionnaire_submission_ref_row",
    "get_reply_monitor_row_by_id",
    "list_contact_tag_rows",
    "list_recent_archived_message_rows",
    "list_recent_conversion_dispatch_rows",
    "list_recent_questionnaire_rows",
]
