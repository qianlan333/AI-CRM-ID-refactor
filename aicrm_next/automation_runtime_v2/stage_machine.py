from __future__ import annotations

from typing import Any

from aicrm_next.shared.postgres_connection import get_db

from .domain import (
    EVENT_CHANNEL_ENTERED,
    EVENT_PAYMENT_SUCCEEDED,
    EVENT_QUESTIONNAIRE_SUBMITTED,
    EVENT_WEBHOOK_RECEIVED,
    STAGE_CONVERTED,
    STAGE_OPERATING,
    STAGE_PENDING_QUESTIONNAIRE,
    STAGES,
    StageTransitionResult,
    as_int,
    text,
)


def _payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload_json")
    return payload if isinstance(payload, dict) else {}


def _program_requires_questionnaire(program_id: int) -> bool:
    row = get_db().execute(
        """
        SELECT payload_json
        FROM automation_program_config_block
        WHERE program_id = ? AND block_key IN ('audience_entry_rule', 'entry_questionnaire', 'questionnaire')
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (int(program_id),),
    ).fetchone()
    if not row:
        return False
    payload = row.get("payload_json")
    if isinstance(payload, dict):
        return bool(payload.get("requires_questionnaire") or payload.get("questionnaire_required") or payload.get("enabled"))
    return "questionnaire" in text(payload).lower()


def _has_questionnaire_submission(membership: dict[str, Any], event: dict[str, Any]) -> bool:
    if text(event.get("event_type")) == EVENT_QUESTIONNAIRE_SUBMITTED:
        return True
    external = text(membership.get("external_userid") or event.get("external_userid"))
    phone = text(membership.get("phone") or event.get("phone"))
    if not external and not phone:
        return False
    row = get_db().execute(
        """
        SELECT id
        FROM questionnaire_submissions
        WHERE NULLIF(COALESCE(userid_snapshot, external_userid, ''), '') = ?
           OR NULLIF(COALESCE(mobile_snapshot, phone, ''), '') = ?
        LIMIT 1
        """,
        (external, phone),
    ).fetchone()
    return bool(row)


def _has_successful_payment(membership: dict[str, Any], event: dict[str, Any]) -> bool:
    if text(event.get("event_type")) == EVENT_PAYMENT_SUCCEEDED:
        return True
    external = text(membership.get("external_userid") or event.get("external_userid"))
    phone = text(membership.get("phone") or event.get("phone"))
    if not external and not phone:
        return False
    row = get_db().execute(
        """
        SELECT id
        FROM wechat_pay_orders
        WHERE (NULLIF(COALESCE(external_userid, userid_snapshot, ''), '') = ?
            OR NULLIF(COALESCE(mobile_snapshot, respondent_key, ''), '') = ?)
          AND (status = 'paid' OR trade_state = 'SUCCESS')
        LIMIT 1
        """,
        (external, phone),
    ).fetchone()
    return bool(row)


def resolve_next_stage(event: dict[str, Any], membership: dict[str, Any], program_config: dict[str, Any] | None = None) -> StageTransitionResult:
    event_type = text(event.get("event_type"))
    payload = _payload(event)
    current_stage = text(membership.get("current_stage")) or STAGE_PENDING_QUESTIONNAIRE
    target_stage = current_stage
    reason = "stage_unchanged"
    if event_type == EVENT_CHANNEL_ENTERED:
        if _has_successful_payment(membership, event):
            target_stage = STAGE_CONVERTED
            reason = "payment_already_succeeded"
        elif _has_questionnaire_submission(membership, event):
            target_stage = STAGE_OPERATING
            reason = "questionnaire_already_submitted"
        elif bool((program_config or {}).get("requires_questionnaire")) or bool(payload.get("requires_questionnaire")) or _program_requires_questionnaire(as_int(membership.get("program_id"))):
            target_stage = STAGE_PENDING_QUESTIONNAIRE
            reason = "channel_entered_requires_questionnaire"
        else:
            target_stage = STAGE_OPERATING
            reason = "channel_entered"
    elif event_type == EVENT_QUESTIONNAIRE_SUBMITTED:
        target_stage = STAGE_OPERATING
        reason = "questionnaire_submitted"
    elif event_type == EVENT_PAYMENT_SUCCEEDED:
        target_stage = STAGE_CONVERTED
        reason = "payment_succeeded"
    elif event_type == EVENT_WEBHOOK_RECEIVED:
        requested = text(payload.get("stage_transition") or payload.get("target_stage"))
        if requested in STAGES:
            target_stage = requested
            reason = "webhook_stage_transition"
        else:
            target_stage = current_stage
            reason = "webhook_no_stage_transition"
    return StageTransitionResult(
        target_stage=target_stage,
        changed=target_stage != current_stage,
        entry_reason=reason,
        diagnostics={"event_type": event_type, "previous_stage": current_stage, "target_stage": target_stage},
    )
