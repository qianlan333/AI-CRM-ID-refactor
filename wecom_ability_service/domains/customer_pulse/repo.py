from __future__ import annotations

from typing import Any

from ...db import get_db
from ._repo_helpers import (  # noqa: F401  shared helpers — 阶段 5.1
    CUSTOMER_PULSE_DEFAULT_TENANT_KEY,
    _fetchall_dict,
    _fetchone_dict,
    _json_storage,
    _normalized_text,
    _required_tenant_key,
)
from ._repo_externals import (  # noqa: F401  cross-domain glue (re-exported) — 阶段 5.1
    get_class_user_status_current,
    get_conversion_dispatch_ref_row,
    get_customer_marketing_state_current,
    get_customer_marketing_state_ref_row,
    get_customer_owner_binding,
    get_external_contact_binding_ref_row,
    get_latest_ai_output_row,
    get_latest_reply_monitor_row,
    get_questionnaire_submission_ref_row,
    get_reply_monitor_row_by_id,
    list_contact_tag_rows,
    list_recent_archived_message_rows,
    list_recent_conversion_dispatch_rows,
    list_recent_questionnaire_rows,
)
from ._repo_segments import (  # noqa: F401  customer_value_segment (re-exported) — 阶段 5.1
    get_customer_value_segment_current,
)
from ._repo_jobs_queue import (  # noqa: F401  jobs/queue/snapshot — 阶段 5.3
    create_customer_pulse_snapshot,
    finish_customer_pulse_recompute_job,
    get_customer_pulse_recompute_job,
    get_customer_pulse_recompute_job_by_external_userid,
    get_customer_pulse_snapshot,
    get_latest_customer_pulse_snapshot_for_external_userid,
    list_customer_pulse_snapshots_by_ids,
    list_due_customer_pulse_recompute_jobs,
    mark_customer_pulse_recompute_job_running,
    upsert_customer_pulse_recompute_job,
)
from ._repo_cards import (  # noqa: F401  card/evidence — 阶段 5.3
    count_customer_pulse_cards_by_status,
    get_customer_pulse_card,
    get_customer_pulse_card_any_tenant,
    get_customer_pulse_card_by_key,
    get_latest_customer_pulse_card_for_external_userid,
    list_customer_pulse_cards,
    list_recent_customer_pulse_cards_for_dashboard,
    update_customer_pulse_card,
    upsert_customer_pulse_card,
)




def list_customer_pulse_candidate_external_userids(*, limit: int = 100) -> list[str]:
    rows = _fetchall_dict(
        """
        SELECT external_userid
        FROM (
            SELECT external_userid, MAX(last_seen_at) AS last_seen_at
            FROM (
                SELECT external_userid, COALESCE(send_time, created_at, '') AS last_seen_at
                FROM archived_messages
                WHERE external_userid <> ''
                UNION ALL
                SELECT external_userid, COALESCE(updated_at, created_at, '') AS last_seen_at
                FROM automation_reply_monitor_queue
                WHERE external_userid <> ''
                UNION ALL
                SELECT external_contact_id AS external_userid, COALESCE(created_at, '') AS last_seen_at
                FROM automation_agent_output
                WHERE external_contact_id <> ''
                  AND output_type IN ('next_action_suggestion', 'agent_reply_draft', 'agent_reply_final')
                UNION ALL
                SELECT external_userid, COALESCE(updated_at, entered_at, created_at, '') AS last_seen_at
                FROM customer_marketing_state_current
                WHERE external_userid <> ''
                UNION ALL
                SELECT external_userid, COALESCE(updated_at, computed_at, evaluated_at, created_at, '') AS last_seen_at
                FROM customer_value_segment_current
                WHERE external_userid <> ''
                UNION ALL
                SELECT external_userid, COALESCE(created_at, '') AS last_seen_at
                FROM contact_tags
                WHERE external_userid <> ''
                UNION ALL
                SELECT external_userid, COALESCE(submitted_at, '') AS last_seen_at
                FROM questionnaire_submissions
                WHERE external_userid <> ''
                UNION ALL
                SELECT external_userid, COALESCE(created_at, '') AS last_seen_at
                FROM questionnaire_scrm_apply_logs
                WHERE external_userid <> ''
                UNION ALL
                SELECT external_userid, COALESCE(dispatched_at, acked_at, updated_at, created_at, '') AS last_seen_at
                FROM conversion_dispatch_log
                WHERE external_userid <> ''
                UNION ALL
                SELECT external_userid, COALESCE(updated_at, created_at, '') AS last_seen_at
                FROM wecom_external_contact_follow_users
                WHERE external_userid <> ''
            ) candidates
            GROUP BY external_userid
        ) ranked
        WHERE external_userid <> ''
        ORDER BY last_seen_at DESC, external_userid ASC
        LIMIT ?
        """,
        (max(1, min(int(limit), 500)),),
    )
    return [_normalized_text(row.get("external_userid")) for row in rows if _normalized_text(row.get("external_userid"))]


def get_customer_pulse_customer_summary(external_userid: str) -> dict[str, Any]:
    normalized_external_userid = _normalized_text(external_userid)
    if not normalized_external_userid:
        return {}
    row = _fetchone_dict(
        """
        SELECT
            ? AS external_userid,
            COALESCE(NULLIF(contacts.customer_name, ''), NULLIF(identity_map.name, ''), ?) AS customer_name,
            COALESCE(NULLIF(contacts.owner_userid, ''), NULLIF(follow_user.user_id, ''), NULLIF(identity_map.follow_user_userid, ''), '') AS owner_userid,
            COALESCE(NULLIF(owner_role.display_name, ''), COALESCE(NULLIF(contacts.owner_userid, ''), NULLIF(follow_user.user_id, ''), NULLIF(identity_map.follow_user_userid, ''), '')) AS owner_display_name,
            COALESCE(people.mobile, '') AS mobile,
            COALESCE(contacts.updated_at, '') AS contact_updated_at,
            COALESCE(bindings.first_owner_userid, '') AS first_owner_userid,
            COALESCE(bindings.last_owner_userid, '') AS last_owner_userid,
            COALESCE(bindings.updated_at, '') AS binding_updated_at
        FROM (SELECT 1 AS anchor) seed
        LEFT JOIN contacts ON contacts.external_userid = ?
        LEFT JOIN external_contact_bindings bindings ON bindings.external_userid = ?
        LEFT JOIN people ON people.id = bindings.person_id
        LEFT JOIN (
            SELECT external_userid, name, follow_user_userid
            FROM wecom_external_contact_identity_map
            WHERE external_userid = ?
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
        ) identity_map ON identity_map.external_userid = ?
        LEFT JOIN (
            SELECT external_userid, user_id
            FROM wecom_external_contact_follow_users
            WHERE external_userid = ?
            ORDER BY is_primary DESC, updated_at DESC, id DESC
            LIMIT 1
        ) follow_user ON follow_user.external_userid = ?
        LEFT JOIN owner_role_map owner_role
          ON owner_role.userid = COALESCE(NULLIF(contacts.owner_userid, ''), NULLIF(follow_user.user_id, ''), NULLIF(identity_map.follow_user_userid, ''), '')
        """,
        (
            normalized_external_userid,
            normalized_external_userid,
            normalized_external_userid,
            normalized_external_userid,
            normalized_external_userid,
            normalized_external_userid,
            normalized_external_userid,
            normalized_external_userid,
        ),
    )
    return row or {
        "external_userid": normalized_external_userid,
        "customer_name": normalized_external_userid,
        "owner_userid": "",
        "owner_display_name": "",
        "mobile": "",
        "contact_updated_at": "",
        "first_owner_userid": "",
        "last_owner_userid": "",
        "binding_updated_at": "",
    }


def get_archived_message_ref_row(source_id: str, *, external_userid: str) -> dict[str, Any] | None:
    normalized_source_id = _normalized_text(source_id)
    normalized_external_userid = _normalized_text(external_userid)
    if not normalized_source_id or not normalized_external_userid:
        return None
    return _fetchone_dict(
        """
        SELECT id, msgid, external_userid, owner_userid, sender, receiver, content, send_time
        FROM archived_messages
        WHERE external_userid = ?
          AND (CAST(id AS TEXT) = ? OR msgid = ?)
        ORDER BY send_time DESC, id DESC
        LIMIT 1
        """,
        (normalized_external_userid, normalized_source_id, normalized_source_id),
    )


def upsert_customer_pulse_signal_event(
    *,
    signal_key: str,
    tenant_key: str,
    external_userid: str,
    owner_userid: str,
    signal_type: str,
    signal_source: str,
    signal_status: str,
    priority: str,
    evidence: Any,
    source_ref_type: str,
    source_ref_id: str,
    source_updated_at: str,
    score: float,
    summary: str,
    payload: Any,
) -> dict[str, Any]:
    db = get_db()
    resolved_tenant_key = _required_tenant_key(tenant_key)
    existing = _fetchone_dict(
        """
        SELECT id
        FROM customer_pulse_signal_events
        WHERE signal_key = ?
          AND tenant_key = ?
        """,
        (_normalized_text(signal_key), resolved_tenant_key),
    )
    params = (
        resolved_tenant_key,
        _normalized_text(external_userid),
        _normalized_text(owner_userid),
        _normalized_text(signal_type),
        _normalized_text(signal_source),
        _normalized_text(signal_status) or "open",
        _normalized_text(priority) or "normal",
        _json_storage(evidence, default="[]"),
        _normalized_text(source_ref_type),
        _normalized_text(source_ref_id),
        _normalized_text(source_updated_at),
        float(score or 0),
        _normalized_text(summary),
        _json_storage(payload, default="{}"),
    )
    if existing:
        db.execute(
            """
            UPDATE customer_pulse_signal_events
            SET tenant_key = ?,
                external_userid = ?,
                owner_userid = ?,
                signal_type = ?,
                signal_source = ?,
                signal_status = ?,
                priority = ?,
                evidence_json = ?,
                source_ref_type = ?,
                source_ref_id = ?,
                source_updated_at = ?,
                score = ?,
                summary = ?,
                payload_json = ?,
                last_seen_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE signal_key = ?
              AND tenant_key = ?
            """,
            (*params, _normalized_text(signal_key), resolved_tenant_key),
        )
    else:
        db.execute(
            """
            INSERT INTO customer_pulse_signal_events (
                signal_key,
                tenant_key,
                external_userid,
                owner_userid,
                signal_type,
                signal_source,
                signal_status,
                priority,
                evidence_json,
                source_ref_type,
                source_ref_id,
                source_updated_at,
                score,
                summary,
                payload_json,
                first_seen_at,
                last_seen_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (_normalized_text(signal_key), *params),
        )
    db.commit()
    return get_customer_pulse_signal_event(signal_key, tenant_key=resolved_tenant_key) or {}


def resolve_customer_pulse_stale_signals(external_userid: str, *, active_signal_keys: list[str]) -> None:
    resolve_customer_pulse_stale_signals_by_tenant(
        external_userid,
        active_signal_keys=active_signal_keys,
        tenant_key=CUSTOMER_PULSE_DEFAULT_TENANT_KEY,
    )


def resolve_customer_pulse_stale_signals_by_tenant(
    external_userid: str,
    *,
    active_signal_keys: list[str],
    tenant_key: str,
) -> None:
    normalized_external_userid = _normalized_text(external_userid)
    if not normalized_external_userid:
        return
    db = get_db()
    normalized_tenant_key = _required_tenant_key(tenant_key)
    if active_signal_keys:
        placeholders = ",".join(["?"] * len(active_signal_keys))
        db.execute(
            f"""
            UPDATE customer_pulse_signal_events
            SET signal_status = 'resolved',
                updated_at = CURRENT_TIMESTAMP
            WHERE tenant_key = ?
              AND external_userid = ?
              AND signal_key NOT IN ({placeholders})
              AND signal_status <> 'resolved'
            """,
            (normalized_tenant_key, normalized_external_userid, *[_normalized_text(item) for item in active_signal_keys]),
        )
    else:
        db.execute(
            """
            UPDATE customer_pulse_signal_events
            SET signal_status = 'resolved',
                updated_at = CURRENT_TIMESTAMP
            WHERE tenant_key = ?
              AND external_userid = ?
              AND signal_status <> 'resolved'
            """,
            (normalized_tenant_key, normalized_external_userid),
        )
    db.commit()


def get_customer_pulse_signal_event(signal_key: str, *, tenant_key: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM customer_pulse_signal_events
        WHERE signal_key = ?
          AND tenant_key = ?
        LIMIT 1
        """,
        (_normalized_text(signal_key), _required_tenant_key(tenant_key)),
    )


def list_customer_pulse_signal_events(
    external_userid: str,
    *,
    tenant_key: str,
    statuses: tuple[str, ...] = ("open",),
    limit: int = 20,
) -> list[dict[str, Any]]:
    normalized_statuses = tuple(_normalized_text(item) for item in statuses if _normalized_text(item))
    if not normalized_statuses:
        return []
    placeholders = ",".join(["?"] * len(normalized_statuses))
    return _fetchall_dict(
        f"""
        SELECT *
        FROM customer_pulse_signal_events
        WHERE tenant_key = ?
          AND external_userid = ?
          AND signal_status IN ({placeholders})
        ORDER BY score DESC, updated_at DESC, id DESC
        LIMIT ?
        """,
        (_required_tenant_key(tenant_key), _normalized_text(external_userid), *normalized_statuses, max(1, min(int(limit), 100))),
    )


def insert_customer_pulse_feedback(
    *,
    card_id: int,
    tenant_key: str,
    external_userid: str,
    feedback_type: str,
    feedback_value: str,
    note: str,
    operator: str,
    payload: Any,
) -> dict[str, Any]:
    db = get_db()
    resolved_tenant_key = _required_tenant_key(tenant_key)
    if not get_customer_pulse_card(int(card_id), tenant_key=resolved_tenant_key):
        raise ValueError("card_id does not belong to tenant")
    row = db.execute(
        """
        INSERT INTO customer_pulse_feedback_logs (
            card_id,
            tenant_key,
            external_userid,
            feedback_type,
            feedback_value,
            note,
            operator,
            payload_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        (
            int(card_id),
            resolved_tenant_key,
            _normalized_text(external_userid),
            _normalized_text(feedback_type),
            _normalized_text(feedback_value),
            _normalized_text(note),
            _normalized_text(operator),
            _json_storage(payload, default="{}"),
        ),
    ).fetchone()
    feedback_id = int((row or {}).get("id") or 0)
    db.commit()
    return _fetchone_dict(
        """
        SELECT *
        FROM customer_pulse_feedback_logs
        WHERE tenant_key = ?
          AND id = ?
        LIMIT 1
        """,
        (resolved_tenant_key, feedback_id),
    ) or {}


def insert_customer_pulse_action_feedback(
    *,
    card_id: int,
    execution_log_id: int | None = None,
    external_userid: str,
    owner_userid: str,
    action_type: str,
    feedback_type: str,
    feedback_source: str,
    operator: str,
    note: str = "",
    tenant_key: str,
    payload: Any = None,
) -> dict[str, Any]:
    db = get_db()
    resolved_tenant_key = _required_tenant_key(tenant_key)
    if not get_customer_pulse_card(int(card_id), tenant_key=resolved_tenant_key):
        raise ValueError("card_id does not belong to tenant")
    if execution_log_id not in (None, "", 0) and not get_customer_pulse_execution_log(
        int(execution_log_id), tenant_key=resolved_tenant_key
    ):
        raise ValueError("execution_log_id does not belong to tenant")
    row = db.execute(
        """
        INSERT INTO customer_pulse_action_feedback (
            card_id,
            execution_log_id,
            external_userid,
            owner_userid,
            action_type,
            feedback_type,
            feedback_source,
            tenant_key,
            operator,
            note,
            payload_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        (
            int(card_id),
            int(execution_log_id) if execution_log_id not in (None, "", 0) else None,
            _normalized_text(external_userid),
            _normalized_text(owner_userid),
            _normalized_text(action_type),
            _normalized_text(feedback_type),
            _normalized_text(feedback_source),
            resolved_tenant_key,
            _normalized_text(operator),
            _normalized_text(note),
            _json_storage(payload, default="{}"),
        ),
    ).fetchone()
    feedback_id = int((row or {}).get("id") or 0)
    db.commit()
    return _fetchone_dict(
        """
        SELECT *
        FROM customer_pulse_action_feedback
        WHERE tenant_key = ?
          AND id = ?
        LIMIT 1
        """,
        (resolved_tenant_key, feedback_id),
    ) or {}


def list_customer_pulse_action_feedback(
    *,
    card_id: int = 0,
    external_userid: str = "",
    tenant_key: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    clauses = ["tenant_key = ?"]
    params: list[Any] = [_required_tenant_key(tenant_key)]
    if int(card_id or 0) > 0:
        clauses.append("card_id = ?")
        params.append(int(card_id))
    if _normalized_text(external_userid):
        clauses.append("external_userid = ?")
        params.append(_normalized_text(external_userid))
    params.append(max(1, min(int(limit), 200)))
    return _fetchall_dict(
        f"""
        SELECT *
        FROM customer_pulse_action_feedback
        WHERE {" AND ".join(clauses)}
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        tuple(params),
    )


def insert_customer_pulse_metric_event(
    *,
    event_type: str,
    event_source: str,
    card_id: int | None = None,
    execution_log_id: int | None = None,
    external_userid: str = "",
    owner_userid: str = "",
    action_type: str = "",
    operator: str = "",
    tenant_key: str,
    payload: Any = None,
) -> dict[str, Any]:
    db = get_db()
    resolved_tenant_key = _required_tenant_key(tenant_key)
    if card_id not in (None, "", 0) and not get_customer_pulse_card(int(card_id), tenant_key=resolved_tenant_key):
        raise ValueError("card_id does not belong to tenant")
    if execution_log_id not in (None, "", 0) and not get_customer_pulse_execution_log(
        int(execution_log_id), tenant_key=resolved_tenant_key
    ):
        raise ValueError("execution_log_id does not belong to tenant")
    row = db.execute(
        """
        INSERT INTO customer_pulse_metric_events (
            card_id,
            execution_log_id,
            external_userid,
            owner_userid,
            action_type,
            event_type,
            event_source,
            tenant_key,
            operator,
            payload_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        (
            int(card_id) if card_id not in (None, "", 0) else None,
            int(execution_log_id) if execution_log_id not in (None, "", 0) else None,
            _normalized_text(external_userid),
            _normalized_text(owner_userid),
            _normalized_text(action_type),
            _normalized_text(event_type),
            _normalized_text(event_source),
            resolved_tenant_key,
            _normalized_text(operator),
            _json_storage(payload, default="{}"),
        ),
    ).fetchone()
    event_id = int((row or {}).get("id") or 0)
    db.commit()
    return _fetchone_dict(
        """
        SELECT *
        FROM customer_pulse_metric_events
        WHERE tenant_key = ?
          AND id = ?
        LIMIT 1
        """,
        (resolved_tenant_key, event_id),
    ) or {}


def insert_customer_pulse_metric_events_batch(*, tenant_key: str, events: list[dict[str, Any]]) -> int:
    resolved_tenant_key = _required_tenant_key(tenant_key)
    normalized_events = [dict(item) for item in events if isinstance(item, dict) and _normalized_text(item.get("event_type"))]
    if not normalized_events:
        return 0

    card_ids = sorted({int(item.get("card_id") or 0) for item in normalized_events if int(item.get("card_id") or 0) > 0})
    if card_ids:
        placeholders = ",".join(["?"] * len(card_ids))
        rows = _fetchall_dict(
            f"""
            SELECT id
            FROM customer_pulse_cards
            WHERE tenant_key = ?
              AND id IN ({placeholders})
            """,
            (resolved_tenant_key, *card_ids),
        )
        existing_card_ids = {int(row.get("id") or 0) for row in rows}
        missing_card_ids = sorted(card_id for card_id in card_ids if card_id not in existing_card_ids)
        if missing_card_ids:
            raise ValueError(f"card_ids do not belong to tenant: {missing_card_ids}")

    execution_log_ids = sorted(
        {int(item.get("execution_log_id") or 0) for item in normalized_events if int(item.get("execution_log_id") or 0) > 0}
    )
    if execution_log_ids:
        placeholders = ",".join(["?"] * len(execution_log_ids))
        rows = _fetchall_dict(
            f"""
            SELECT id
            FROM customer_pulse_execution_logs
            WHERE tenant_key = ?
              AND id IN ({placeholders})
            """,
            (resolved_tenant_key, *execution_log_ids),
        )
        existing_execution_log_ids = {int(row.get("id") or 0) for row in rows}
        missing_execution_log_ids = sorted(
            execution_log_id for execution_log_id in execution_log_ids if execution_log_id not in existing_execution_log_ids
        )
        if missing_execution_log_ids:
            raise ValueError(f"execution_log_ids do not belong to tenant: {missing_execution_log_ids}")

    db = get_db()
    chunk_size = 80
    inserted_count = 0
    for index in range(0, len(normalized_events), chunk_size):
        chunk = normalized_events[index : index + chunk_size]
        placeholders = ",".join(["(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"] * len(chunk))
        params: list[Any] = []
        for item in chunk:
            params.extend(
                [
                    int(item.get("card_id") or 0) if int(item.get("card_id") or 0) > 0 else None,
                    int(item.get("execution_log_id") or 0) if int(item.get("execution_log_id") or 0) > 0 else None,
                    _normalized_text(item.get("external_userid")),
                    _normalized_text(item.get("owner_userid")),
                    _normalized_text(item.get("action_type")),
                    _normalized_text(item.get("event_type")),
                    _normalized_text(item.get("event_source")),
                    resolved_tenant_key,
                    _normalized_text(item.get("operator")),
                    _json_storage(item.get("payload"), default="{}"),
                ]
            )
        db.execute(
            f"""
            INSERT INTO customer_pulse_metric_events (
                card_id,
                execution_log_id,
                external_userid,
                owner_userid,
                action_type,
                event_type,
                event_source,
                tenant_key,
                operator,
                payload_json
            )
            VALUES {placeholders}
            """,
            tuple(params),
        )
        inserted_count += len(chunk)
    db.commit()
    return inserted_count


def count_customer_pulse_metric_events(
    *,
    event_types: tuple[str, ...] = (),
    tenant_key: str,
    owner_userids: list[str] | tuple[str, ...] | None = None,
    since: str = "",
) -> dict[str, int]:
    clauses = ["tenant_key = ?"]
    params: list[Any] = [_required_tenant_key(tenant_key)]
    normalized_event_types = tuple(_normalized_text(item) for item in event_types if _normalized_text(item))
    if normalized_event_types:
        placeholders = ",".join(["?"] * len(normalized_event_types))
        clauses.append(f"event_type IN ({placeholders})")
        params.extend(normalized_event_types)
    if _normalized_text(since):
        clauses.append("created_at >= ?")
        params.append(_normalized_text(since))
    normalized_owner_userids = [_normalized_text(item) for item in (owner_userids or []) if _normalized_text(item)]
    if normalized_owner_userids:
        placeholders = ",".join(["?"] * len(normalized_owner_userids))
        clauses.append(f"owner_userid IN ({placeholders})")
        params.extend(normalized_owner_userids)
    rows = _fetchall_dict(
        f"""
        SELECT event_type, COUNT(*) AS total_count
        FROM customer_pulse_metric_events
        WHERE {" AND ".join(clauses)}
        GROUP BY event_type
        """,
        tuple(params),
    )
    return {_normalized_text(row.get("event_type")): int(row.get("total_count") or 0) for row in rows}


def count_customer_pulse_metric_events_by_day(
    *,
    event_types: tuple[str, ...] = (),
    tenant_key: str,
    owner_userids: list[str] | tuple[str, ...] | None = None,
    since: str = "",
) -> list[dict[str, Any]]:
    clauses = ["tenant_key = ?"]
    params: list[Any] = [_required_tenant_key(tenant_key)]
    normalized_event_types = tuple(_normalized_text(item) for item in event_types if _normalized_text(item))
    if normalized_event_types:
        placeholders = ",".join(["?"] * len(normalized_event_types))
        clauses.append(f"event_type IN ({placeholders})")
        params.extend(normalized_event_types)
    if _normalized_text(since):
        clauses.append("created_at >= ?")
        params.append(_normalized_text(since))
    normalized_owner_userids = [_normalized_text(item) for item in (owner_userids or []) if _normalized_text(item)]
    if normalized_owner_userids:
        placeholders = ",".join(["?"] * len(normalized_owner_userids))
        clauses.append(f"owner_userid IN ({placeholders})")
        params.extend(normalized_owner_userids)
    return _fetchall_dict(
        f"""
        SELECT DATE(created_at) AS metric_date, event_type, COUNT(*) AS total_count
        FROM customer_pulse_metric_events
        WHERE {" AND ".join(clauses)}
        GROUP BY DATE(created_at), event_type
        ORDER BY DATE(created_at) ASC, event_type ASC
        """,
        tuple(params),
    )


def insert_customer_pulse_execution_log(
    *,
    card_id: int,
    external_userid: str,
    action_type: str,
    execution_status: str,
    channel_type: str,
    operator: str,
    actor_userid: str = "",
    actor_role: str = "",
    resource_type: str = "",
    resource_id: str = "",
    request_payload: Any,
    result_payload: Any,
    error_message: str,
    tenant_key: str,
    tenant_context: Any = None,
    audit_labels: Any = None,
    rollback_payload: Any = None,
    execution_key: str = "",
    idempotency_key: str = "",
    activity_log_id: int | None = None,
    outbound_task_id: int | None = None,
    undo_status: str = "",
    undo_until: str = "",
    undone_at: str = "",
) -> dict[str, Any]:
    db = get_db()
    resolved_tenant_key = _required_tenant_key(tenant_key)
    if not get_customer_pulse_card(int(card_id), tenant_key=resolved_tenant_key):
        raise ValueError("card_id does not belong to tenant")
    if activity_log_id not in (None, "", 0) and not get_customer_pulse_activity_log(
        int(activity_log_id), tenant_key=resolved_tenant_key
    ):
        raise ValueError("activity_log_id does not belong to tenant")
    row = db.execute(
        """
        INSERT INTO customer_pulse_execution_logs (
            card_id,
            external_userid,
            action_type,
            execution_status,
            channel_type,
            operator,
            actor_userid,
            actor_role,
            resource_type,
            resource_id,
            tenant_key,
            tenant_context_json,
            audit_labels_json,
            rollback_payload_json,
            execution_key,
            idempotency_key,
            activity_log_id,
            outbound_task_id,
            undo_status,
            undo_until,
            undone_at,
            request_payload_json,
            result_payload_json,
            error_message
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        (
            int(card_id),
            _normalized_text(external_userid),
            _normalized_text(action_type),
            _normalized_text(execution_status),
            _normalized_text(channel_type),
            _normalized_text(operator),
            _normalized_text(actor_userid),
            _normalized_text(actor_role),
            _normalized_text(resource_type),
            _normalized_text(resource_id),
            resolved_tenant_key,
            _json_storage(tenant_context, default="{}"),
            _json_storage(audit_labels, default="[]"),
            _json_storage(rollback_payload, default="{}"),
            _normalized_text(execution_key),
            _normalized_text(idempotency_key),
            int(activity_log_id) if activity_log_id not in (None, "", 0) else None,
            int(outbound_task_id) if outbound_task_id not in (None, "", 0) else None,
            _normalized_text(undo_status),
            _normalized_text(undo_until),
            _normalized_text(undone_at),
            _json_storage(request_payload, default="{}"),
            _json_storage(result_payload, default="{}"),
            _normalized_text(error_message),
        ),
    ).fetchone()
    execution_id = int((row or {}).get("id") or 0)
    db.commit()
    return _fetchone_dict(
        """
        SELECT *
        FROM customer_pulse_execution_logs
        WHERE tenant_key = ?
          AND id = ?
        LIMIT 1
        """,
        (resolved_tenant_key, execution_id),
    ) or {}


def get_customer_pulse_execution_log(execution_id: int, *, tenant_key: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM customer_pulse_execution_logs
        WHERE tenant_key = ?
          AND id = ?
        LIMIT 1
        """,
        (_required_tenant_key(tenant_key), int(execution_id)),
    )


def get_customer_pulse_execution_log_any_tenant(execution_id: int) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT
            id,
            tenant_key,
            card_id
        FROM customer_pulse_execution_logs
        WHERE id = ?
        LIMIT 1
        """,
        (int(execution_id),),
    )


def get_latest_customer_pulse_execution_log(card_id: int, *, tenant_key: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM customer_pulse_execution_logs
        WHERE tenant_key = ?
          AND card_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (_required_tenant_key(tenant_key), int(card_id)),
    )


def get_latest_customer_pulse_execution_log_by_idempotency(
    *,
    card_id: int,
    action_type: str,
    idempotency_key: str,
    tenant_key: str,
) -> dict[str, Any] | None:
    normalized_key = _normalized_text(idempotency_key)
    if not normalized_key:
        return None
    return _fetchone_dict(
        """
        SELECT *
        FROM customer_pulse_execution_logs
        WHERE tenant_key = ?
          AND card_id = ?
          AND action_type = ?
          AND idempotency_key = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (_required_tenant_key(tenant_key), int(card_id), _normalized_text(action_type), normalized_key),
    )


def update_customer_pulse_execution_log(execution_id: int, *, tenant_key: str, **fields: Any) -> dict[str, Any]:
    allowed_fields = {
        "execution_status",
        "channel_type",
        "operator",
        "actor_userid",
        "actor_role",
        "resource_type",
        "resource_id",
        "tenant_key",
        "tenant_context_json",
        "audit_labels_json",
        "rollback_payload_json",
        "execution_key",
        "idempotency_key",
        "activity_log_id",
        "outbound_task_id",
        "undo_status",
        "undo_until",
        "undone_at",
        "request_payload_json",
        "result_payload_json",
        "error_message",
    }
    assignments: list[str] = []
    params: list[Any] = []
    for key, value in fields.items():
        if key not in allowed_fields:
            continue
        if key == "activity_log_id" and value not in (None, "", 0):
            if not get_customer_pulse_activity_log(int(value), tenant_key=_required_tenant_key(tenant_key)):
                raise ValueError("activity_log_id does not belong to tenant")
        if key == "audit_labels_json":
            value = _json_storage(value, default="[]")
        elif key in {"request_payload_json", "result_payload_json", "tenant_context_json", "rollback_payload_json"}:
            value = _json_storage(value, default="{}")
        if key in {"activity_log_id", "outbound_task_id"}:
            value = int(value) if value not in (None, "", 0) else None
        assignments.append(f"{key} = ?")
        params.append(value)
    resolved_tenant_key = _required_tenant_key(tenant_key)
    if not assignments:
        return get_customer_pulse_execution_log(int(execution_id), tenant_key=resolved_tenant_key) or {}
    assignments.append("updated_at = CURRENT_TIMESTAMP")
    where_clauses = ["id = ?"]
    where_params: list[Any] = []
    where_clauses.insert(0, "tenant_key = ?")
    where_params.append(resolved_tenant_key)
    where_params.append(int(execution_id))
    get_db().execute(
        f"""
        UPDATE customer_pulse_execution_logs
        SET {", ".join(assignments)}
        WHERE {" AND ".join(where_clauses)}
        """,
        tuple([*params, *where_params]),
    )
    get_db().commit()
    return get_customer_pulse_execution_log(int(execution_id), tenant_key=resolved_tenant_key) or {}


def insert_customer_pulse_activity_log(
    *,
    card_id: int,
    external_userid: str,
    owner_userid: str,
    activity_type: str,
    activity_status: str,
    title: str,
    summary: str,
    operator: str,
    due_at: str = "",
    activity_source: str = "ai_customer_pulse",
    tenant_key: str,
    execution_key: str = "",
    idempotency_key: str = "",
    payload: Any = None,
    undone_at: str = "",
) -> dict[str, Any]:
    db = get_db()
    resolved_tenant_key = _required_tenant_key(tenant_key)
    if not get_customer_pulse_card(int(card_id), tenant_key=resolved_tenant_key):
        raise ValueError("card_id does not belong to tenant")
    row = db.execute(
        """
        INSERT INTO customer_pulse_activity_logs (
            card_id,
            external_userid,
            owner_userid,
            activity_type,
            activity_status,
            activity_source,
            tenant_key,
            execution_key,
            idempotency_key,
            title,
            summary,
            due_at,
            operator,
            payload_json,
            undone_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        (
            int(card_id),
            _normalized_text(external_userid),
            _normalized_text(owner_userid),
            _normalized_text(activity_type),
            _normalized_text(activity_status),
            _normalized_text(activity_source) or "ai_customer_pulse",
            resolved_tenant_key,
            _normalized_text(execution_key),
            _normalized_text(idempotency_key),
            _normalized_text(title),
            _normalized_text(summary),
            _normalized_text(due_at),
            _normalized_text(operator),
            _json_storage(payload, default="{}"),
            _normalized_text(undone_at),
        ),
    ).fetchone()
    activity_id = int((row or {}).get("id") or 0)
    db.commit()
    return get_customer_pulse_activity_log(activity_id, tenant_key=resolved_tenant_key) or {}


def get_customer_pulse_activity_log(activity_id: int, *, tenant_key: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM customer_pulse_activity_logs
        WHERE tenant_key = ?
          AND id = ?
        LIMIT 1
        """,
        (_required_tenant_key(tenant_key), int(activity_id)),
    )


def update_customer_pulse_activity_log(activity_id: int, *, tenant_key: str, **fields: Any) -> dict[str, Any]:
    allowed_fields = {
        "activity_status",
        "activity_source",
        "tenant_key",
        "execution_key",
        "idempotency_key",
        "title",
        "summary",
        "due_at",
        "operator",
        "payload_json",
        "undone_at",
    }
    assignments: list[str] = []
    params: list[Any] = []
    for key, value in fields.items():
        if key not in allowed_fields:
            continue
        if key == "payload_json":
            value = _json_storage(value, default="{}")
        assignments.append(f"{key} = ?")
        params.append(value)
    resolved_tenant_key = _required_tenant_key(tenant_key)
    if not assignments:
        return get_customer_pulse_activity_log(int(activity_id), tenant_key=resolved_tenant_key) or {}
    assignments.append("updated_at = CURRENT_TIMESTAMP")
    where_clauses = ["id = ?"]
    where_params: list[Any] = []
    where_clauses.insert(0, "tenant_key = ?")
    where_params.append(resolved_tenant_key)
    where_params.append(int(activity_id))
    get_db().execute(
        f"""
        UPDATE customer_pulse_activity_logs
        SET {", ".join(assignments)}
        WHERE {" AND ".join(where_clauses)}
        """,
        tuple([*params, *where_params]),
    )
    get_db().commit()
    return get_customer_pulse_activity_log(int(activity_id), tenant_key=resolved_tenant_key) or {}


def list_customer_pulse_activity_logs(external_userid: str, *, tenant_key: str, limit: int = 20) -> list[dict[str, Any]]:
    return _fetchall_dict(
        """
        SELECT *
        FROM customer_pulse_activity_logs
        WHERE tenant_key = ?
          AND external_userid = ?
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (_required_tenant_key(tenant_key), _normalized_text(external_userid), max(1, min(int(limit), 200))),
    )


