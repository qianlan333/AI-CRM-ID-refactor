"""Customer pulse card / evidence data-access (阶段 5.3).

Extracted from repo.py. Depends on _repo_jobs_queue (calls
get_customer_pulse_snapshot for snapshot resolution).
"""

from __future__ import annotations

from typing import Any

from ...db import get_db
from ._repo_helpers import (
    _fetchall_dict,
    _fetchone_dict,
    _json_storage,
    _normalized_text,
    _required_tenant_key,
)
from ._repo_jobs_queue import get_customer_pulse_snapshot


def get_customer_pulse_card(card_id: int, *, tenant_key: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT
            card.*
        FROM customer_pulse_cards card
        WHERE card.tenant_key = ?
          AND card.id = ?
        LIMIT 1
        """,
        (_required_tenant_key(tenant_key), int(card_id)),
    )


def get_customer_pulse_card_any_tenant(card_id: int) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT
            id,
            tenant_key,
            external_userid,
            owner_userid
        FROM customer_pulse_cards
        WHERE id = ?
        LIMIT 1
        """,
        (int(card_id),),
    )


def get_customer_pulse_card_by_key(card_key: str, *, tenant_key: str) -> dict[str, Any] | None:
    return _fetchone_dict(
        """
        SELECT *
        FROM customer_pulse_cards
        WHERE tenant_key = ?
          AND card_key = ?
        LIMIT 1
        """,
        (_required_tenant_key(tenant_key), _normalized_text(card_key)),
    )


def get_latest_customer_pulse_card_for_external_userid(
    external_userid: str,
    *,
    tenant_key: str,
    statuses: tuple[str, ...] = ("open", "draft_ready", "snoozed", "completed", "dismissed"),
) -> dict[str, Any] | None:
    normalized_statuses = tuple(_normalized_text(item) for item in statuses if _normalized_text(item))
    if not normalized_statuses:
        return None
    placeholders = ",".join(["?"] * len(normalized_statuses))
    return _fetchone_dict(
        f"""
        SELECT *
        FROM customer_pulse_cards
        WHERE tenant_key = ?
          AND external_userid = ?
          AND card_status IN ({placeholders})
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (_required_tenant_key(tenant_key), _normalized_text(external_userid), *normalized_statuses),
    )


def upsert_customer_pulse_card(
    *,
    card_key: str,
    tenant_key: str,
    external_userid: str,
    owner_userid: str,
    customer_name: str,
    mobile: str,
    owner_display_name: str,
    marketing_main_stage: str,
    marketing_sub_stage: str,
    value_segment: str,
    snapshot_id: int | None,
    card_status: str,
    priority: str,
    priority_score: float,
    card_type: str,
    title: str,
    summary: str,
    suggested_action_type: str,
    suggested_action_payload: Any,
    evidence: Any,
    risk_flags: Any,
    opportunity_flags: Any,
    suggested_action_candidates: Any,
    score_breakdown: Any,
    draft_message: str,
    need_human_confirmation: bool,
    due_at: str,
    snooze_until: str,
    resolved_at: str,
    resolution_note: str,
    source_updated_at: str,
) -> dict[str, Any]:
    db = get_db()
    resolved_tenant_key = _required_tenant_key(tenant_key)
    existing = get_customer_pulse_card_by_key(card_key, tenant_key=resolved_tenant_key)
    if snapshot_id not in (None, "", 0):
        if not get_customer_pulse_snapshot(int(snapshot_id), tenant_key=resolved_tenant_key):
            raise ValueError("snapshot_id does not belong to tenant")
    params = (
        resolved_tenant_key,
        _normalized_text(external_userid),
        _normalized_text(owner_userid),
        _normalized_text(customer_name),
        _normalized_text(mobile),
        _normalized_text(owner_display_name),
        _normalized_text(marketing_main_stage),
        _normalized_text(marketing_sub_stage),
        _normalized_text(value_segment),
        snapshot_id,
        _normalized_text(card_status) or "open",
        _normalized_text(priority) or "normal",
        float(priority_score or 0),
        _normalized_text(card_type) or "followup",
        _normalized_text(title),
        _normalized_text(summary),
        _normalized_text(suggested_action_type),
        _json_storage(suggested_action_payload, default="{}"),
        _json_storage(evidence, default="[]"),
        _json_storage(risk_flags, default="[]"),
        _json_storage(opportunity_flags, default="[]"),
        _json_storage(suggested_action_candidates, default="[]"),
        _json_storage(score_breakdown, default="[]"),
        str(draft_message or ""),
        1 if need_human_confirmation else 0,
        _normalized_text(due_at),
        _normalized_text(snooze_until),
        _normalized_text(resolved_at),
        _normalized_text(resolution_note),
        _normalized_text(source_updated_at),
    )
    if existing:
        db.execute(
            """
            UPDATE customer_pulse_cards
            SET tenant_key = ?,
                external_userid = ?,
                owner_userid = ?,
                customer_name = ?,
                mobile = ?,
                owner_display_name = ?,
                marketing_main_stage = ?,
                marketing_sub_stage = ?,
                value_segment = ?,
                snapshot_id = ?,
                card_status = ?,
                priority = ?,
                priority_score = ?,
                card_type = ?,
                title = ?,
                summary = ?,
                suggested_action_type = ?,
                suggested_action_payload_json = ?,
                evidence_json = ?,
                risk_flags_json = ?,
                opportunity_flags_json = ?,
                suggested_action_candidates_json = ?,
                score_breakdown_json = ?,
                draft_message = ?,
                need_human_confirmation = ?,
                due_at = ?,
                snooze_until = ?,
                resolved_at = ?,
                resolution_note = ?,
                source_updated_at = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE card_key = ?
            """,
            (*params, _normalized_text(card_key)),
        )
    else:
        db.execute(
            """
            INSERT INTO customer_pulse_cards (
                card_key,
                tenant_key,
                external_userid,
                owner_userid,
                customer_name,
                mobile,
                owner_display_name,
                marketing_main_stage,
                marketing_sub_stage,
                value_segment,
                snapshot_id,
                card_status,
                priority,
                priority_score,
                card_type,
                title,
                summary,
                suggested_action_type,
                suggested_action_payload_json,
                evidence_json,
                risk_flags_json,
                opportunity_flags_json,
                suggested_action_candidates_json,
                score_breakdown_json,
                draft_message,
                need_human_confirmation,
                due_at,
                snooze_until,
                resolved_at,
                resolution_note,
                source_updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (_normalized_text(card_key), *params),
        )
    db.commit()
    existing = get_customer_pulse_card_by_key(card_key, tenant_key=resolved_tenant_key) or {}
    return get_customer_pulse_card(int(existing.get("id") or 0), tenant_key=resolved_tenant_key) or {}


def update_customer_pulse_card(card_id: int, *, tenant_key: str, **fields: Any) -> dict[str, Any]:
    allowed_fields = {
        "snapshot_id",
        "customer_name",
        "mobile",
        "owner_display_name",
        "marketing_main_stage",
        "marketing_sub_stage",
        "value_segment",
        "card_status",
        "priority",
        "priority_score",
        "card_type",
        "title",
        "summary",
        "suggested_action_type",
        "suggested_action_payload_json",
        "evidence_json",
        "risk_flags_json",
        "opportunity_flags_json",
        "suggested_action_candidates_json",
        "score_breakdown_json",
        "draft_message",
        "need_human_confirmation",
        "due_at",
        "snooze_until",
        "resolved_at",
        "resolution_note",
        "source_updated_at",
    }
    assignments: list[str] = []
    params: list[Any] = []
    for key, value in fields.items():
        if key not in allowed_fields:
            continue
        if key == "snapshot_id" and value not in (None, "", 0):
            if not get_customer_pulse_snapshot(int(value), tenant_key=_required_tenant_key(tenant_key)):
                raise ValueError("snapshot_id does not belong to tenant")
        if key in {
            "suggested_action_payload_json",
            "evidence_json",
            "risk_flags_json",
            "opportunity_flags_json",
            "suggested_action_candidates_json",
            "score_breakdown_json",
        }:
            default = "{}" if key == "suggested_action_payload_json" else "[]"
            value = _json_storage(value, default=default)
        if key == "need_human_confirmation":
            value = 1 if bool(value) else 0
        if key == "priority_score":
            value = float(value or 0)
        assignments.append(f"{key} = ?")
        params.append(value)
    resolved_tenant_key = _required_tenant_key(tenant_key)
    if not assignments:
        return get_customer_pulse_card(card_id, tenant_key=resolved_tenant_key) or {}
    assignments.append("updated_at = CURRENT_TIMESTAMP")
    where_clauses = ["id = ?"]
    where_params: list[Any] = []
    where_clauses.insert(0, "tenant_key = ?")
    where_params.append(resolved_tenant_key)
    where_params.append(int(card_id))
    get_db().execute(
        f"""
        UPDATE customer_pulse_cards
        SET {", ".join(assignments)}
        WHERE {" AND ".join(where_clauses)}
        """,
        tuple([*params, *where_params]),
    )
    get_db().commit()
    return get_customer_pulse_card(card_id, tenant_key=resolved_tenant_key) or {}


def list_customer_pulse_cards(
    *,
    statuses: tuple[str, ...] = ("open", "draft_ready", "snoozed"),
    tenant_key: str,
    owner_userid: str = "",
    external_userid: str = "",
    allowed_owner_userids: list[str] | tuple[str, ...] | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    normalized_statuses = tuple(_normalized_text(item) for item in statuses if _normalized_text(item))
    if not normalized_statuses:
        return []
    placeholders = ",".join(["?"] * len(normalized_statuses))
    clauses = ["card.tenant_key = ?", f"card.card_status IN ({placeholders})"]
    params: list[Any] = [_required_tenant_key(tenant_key), *normalized_statuses]
    if _normalized_text(owner_userid):
        clauses.append("card.owner_userid = ?")
        params.append(_normalized_text(owner_userid))
    if _normalized_text(external_userid):
        clauses.append("card.external_userid = ?")
        params.append(_normalized_text(external_userid))
    normalized_allowed_owner_userids = [
        _normalized_text(item) for item in (allowed_owner_userids or []) if _normalized_text(item)
    ]
    if normalized_allowed_owner_userids:
        owner_placeholders = ",".join(["?"] * len(normalized_allowed_owner_userids))
        clauses.append(f"card.owner_userid IN ({owner_placeholders})")
        params.extend(normalized_allowed_owner_userids)
    return _fetchall_dict(
        f"""
        SELECT
            card.*
        FROM customer_pulse_cards card
        WHERE {" AND ".join(clauses)}
        ORDER BY
            card.priority_score DESC,
            CASE card.priority
                WHEN 'high' THEN 0
                WHEN 'normal' THEN 1
                ELSE 2
            END ASC,
            CASE card.card_status
                WHEN 'draft_ready' THEN 0
                WHEN 'open' THEN 1
                WHEN 'snoozed' THEN 2
                ELSE 9
            END ASC,
            COALESCE(NULLIF(card.due_at, ''), NULLIF(card.source_updated_at, ''), card.updated_at) ASC,
            card.id DESC
        LIMIT ?
        """,
        (*params, max(1, min(int(limit), 200))),
    )


def count_customer_pulse_cards_by_status(*, tenant_key: str, allowed_owner_userids: list[str] | tuple[str, ...] | None = None) -> dict[str, int]:
    clauses = ["tenant_key = ?"]
    params: list[Any] = [_required_tenant_key(tenant_key)]
    normalized_allowed_owner_userids = [
        _normalized_text(item) for item in (allowed_owner_userids or []) if _normalized_text(item)
    ]
    if normalized_allowed_owner_userids:
        placeholders = ",".join(["?"] * len(normalized_allowed_owner_userids))
        clauses.append(f"owner_userid IN ({placeholders})")
        params.extend(normalized_allowed_owner_userids)
    rows = _fetchall_dict(
        f"""
        SELECT card_status, COUNT(*) AS total_count
        FROM customer_pulse_cards
        WHERE {" AND ".join(clauses)}
        GROUP BY card_status
        """,
        tuple(params),
    )
    return {_normalized_text(row.get("card_status")): int(row.get("total_count") or 0) for row in rows}


def list_recent_customer_pulse_cards_for_dashboard(*, limit: int = 5, tenant_key: str) -> list[dict[str, Any]]:
    return list_customer_pulse_cards(statuses=("open", "draft_ready"), limit=limit, tenant_key=tenant_key)




__all__ = [
    "count_customer_pulse_cards_by_status",
    "get_customer_pulse_card",
    "get_customer_pulse_card_any_tenant",
    "get_customer_pulse_card_by_key",
    "get_latest_customer_pulse_card_for_external_userid",
    "list_customer_pulse_cards",
    "list_recent_customer_pulse_cards_for_dashboard",
    "update_customer_pulse_card",
    "upsert_customer_pulse_card",
]
