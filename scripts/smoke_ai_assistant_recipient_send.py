"""Real-send smoke for AI assistant per-recipient approval.

This script intentionally refuses to run unless all explicit real-send guard
environment variables are present. It creates exactly one plan, one recipient,
one message, approves only that recipient, then executes only the resulting
broadcast_job_id.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from script_runtime import ensure_repo_root_on_path, print_json

ensure_repo_root_on_path()


EXPECTED_EXTERNAL_USERID = "wmbNXyCwAAXhagLBNjtlFj2jbQevWinQ"
EXPECTED_OWNER_USERID = "HuangYouCan"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _require_exact_env(name: str, expected: str) -> None:
    actual = _text(os.getenv(name))
    if actual != expected:
        raise SystemExit(f"{name} must be exactly {expected!r}; got {actual!r}")


def _require_env(name: str) -> str:
    value = _text(os.getenv(name))
    if not value:
        raise SystemExit(f"{name} is required")
    return value


def _guard_real_send() -> None:
    _require_exact_env("RUN_REAL_WECOM_SEND", "1")
    _require_exact_env("CONFIRM_REAL_SEND_EXTERNAL_USERID", EXPECTED_EXTERNAL_USERID)
    _require_exact_env("CONFIRM_REAL_SEND_OWNER_USERID", EXPECTED_OWNER_USERID)
    _require_env("DATABASE_URL")
    for key in ("WECOM_CORP_ID", "WECOM_SECRET", "WECOM_AGENT_ID"):
        _require_env(key)


def _json_dump(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False)


def _now_label() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S")


def _insert_plan_recipient_message(*, plan_id: str, timestamp: str, content_text: str) -> int:
    from wecom_ability_service.db import get_db

    db = get_db()
    cur = db.cursor()
    cur.execute(
        """
        INSERT INTO cloud_broadcast_plans (
            plan_id, trace_id, session_id, operator, intent, display_name, owner_userid,
            selection_json, content_strategy, content_template, personalization_json,
            max_recipients, candidate_count, skipped_count, explanation_json,
            variants_json, copy_workorder_run_ids, requires_manual_copy,
            attachments_json, simulate_summary_json, status, review_status, run_status,
            expires_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'recipient_messages', ?, '[]', 1, 1, 0, '{}', '[]', '[]', FALSE, '[]', '{}', 'draft', 'pending_review', 'draft', ?)
        RETURNING id
        """,
        (
            plan_id,
            f"smoke-recipient-{uuid.uuid4().hex[:12]}",
            f"smoke-session-{uuid.uuid4().hex[:12]}",
            "smoke_ai_assistant_recipient_send",
            f"SMOKE 单人审批真实发送测试 {timestamp}",
            f"SMOKE 单人审批真实发送测试 {timestamp}",
            EXPECTED_OWNER_USERID,
            _json_dump({"owner_userid": EXPECTED_OWNER_USERID, "external_userids": [EXPECTED_EXTERNAL_USERID]}),
            content_text,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    cur.fetchone()
    row = cur.execute(
        """
        INSERT INTO cloud_broadcast_plan_recipients (
            plan_id, external_userid, owner_userid, display_name, planned_message_count,
            approval_status, send_status
        ) VALUES (?, ?, ?, ?, 1, 'pending', 'pending')
        RETURNING id
        """,
        (plan_id, EXPECTED_EXTERNAL_USERID, EXPECTED_OWNER_USERID, "AI-CRM smoke receiver"),
    ).fetchone()
    recipient_id = int(row["id"])
    cur.execute(
        """
        INSERT INTO cloud_broadcast_plan_recipient_messages (
            plan_id, recipient_id, external_userid, sequence_index, day_offset, send_time,
            content_text, content_payload_json, attachments_json, status
        ) VALUES (?, ?, ?, 1, 0, ?, ?, '{}', '[]', 'pending')
        """,
        (plan_id, recipient_id, EXPECTED_EXTERNAL_USERID, timestamp[-8:-3], content_text),
    )
    db.commit()
    return recipient_id


def _claim_only_job(job_id: int, *, expected_source_id: str) -> dict[str, Any]:
    from wecom_ability_service.db import get_db
    from wecom_ability_service.domains.broadcast_jobs import service as queue_service

    db = get_db()
    row = db.execute(
        """
        UPDATE broadcast_jobs
        SET status = 'claimed',
            claimed_at = CURRENT_TIMESTAMP,
            claim_token = ?,
            lease_expires_at = CURRENT_TIMESTAMP + INTERVAL '10 minutes',
            updated_at = CURRENT_TIMESTAMP,
            attempt_count = attempt_count + 1
        WHERE id = ?
          AND source_type = 'cloud_plan'
          AND source_table = 'cloud_broadcast_plan_recipients'
          AND source_id = ?
          AND status = 'queued'
        RETURNING id
        """,
        (f"smoke-{uuid.uuid4().hex}", int(job_id), expected_source_id),
    ).fetchone()
    db.commit()
    if not row:
        raise RuntimeError(f"failed to claim smoke broadcast_job_id={job_id}")
    job = queue_service.get_job(int(job_id))
    if not job:
        raise RuntimeError(f"claimed smoke job not found: {job_id}")
    return job


def _decode_json(value: Any, *, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError):
        return default


def run() -> dict[str, Any]:
    _guard_real_send()

    from aicrm_next.cloud_orchestrator.repository import PostgresCloudPlanRepository
    from aicrm_next.integration_gateway.legacy_flask_facade import _legacy_app
    from wecom_ability_service.db import get_db
    from wecom_ability_service.domains.broadcast_jobs import service as queue_service
    from wecom_ability_service.domains.broadcast_jobs.handlers import execute_job
    from wecom_ability_service.domains.tasks import service as outbound_task_service

    timestamp = _now_label()
    plan_id = f"smoke_recipient_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
    content_text = f"[AI-CRM真实发送测试] plan-recipient-approve smoke {timestamp}，请忽略。"
    repo = PostgresCloudPlanRepository()

    with _legacy_app().app_context():
        recipient_id = _insert_plan_recipient_message(plan_id=plan_id, timestamp=timestamp, content_text=content_text)
        repo.approve_plan(plan_id, operator="smoke_ai_assistant_recipient_send")
        first = repo.approve_recipient(plan_id, recipient_id, operator="smoke_ai_assistant_recipient_send")
        second = repo.approve_recipient(plan_id, recipient_id, operator="smoke_ai_assistant_recipient_send")
        if int(first.get("job_id") or 0) != int(second.get("job_id") or 0):
            raise RuntimeError(f"idempotency failed: first={first} second={second}")

        broadcast_job_id = int(first.get("job_id") or 0)
        if not broadcast_job_id:
            raise RuntimeError(f"recipient approve did not create broadcast job: {first}")
        source_id = f"{plan_id}:{recipient_id}"
        job = _claim_only_job(broadcast_job_id, expected_source_id=source_id)

        targets = list(job.get("target_external_userids") or [])
        if targets != [EXPECTED_EXTERNAL_USERID] or int(job.get("target_count") or 0) != 1:
            raise RuntimeError(f"unsafe target set for smoke job: {targets}")
        payload = dict(job.get("content_payload") or {})
        if payload.get("recipient_id") != recipient_id or payload.get("external_userid") != EXPECTED_EXTERNAL_USERID:
            raise RuntimeError(f"unsafe content_payload for smoke job: {payload}")

        result = execute_job(job)
        if result.get("ok"):
            queue_service.mark_sent(
                broadcast_job_id,
                outbound_task_id=result.get("outbound_task_id"),
                sent_count=int(result.get("sent_count") or 0),
                failed_count=int(result.get("failed_count") or 0),
            )
        else:
            queue_service.mark_failed(
                broadcast_job_id,
                error=str(result.get("error") or "unknown smoke send failure"),
                failure_type="handler_error",
            )
            raise RuntimeError(f"smoke send failed: {result}")

        final_job = queue_service.get_job(broadcast_job_id) or {}
        recipient = get_db().execute(
            "SELECT * FROM cloud_broadcast_plan_recipients WHERE id = ?",
            (recipient_id,),
        ).fetchone()
        message = get_db().execute(
            "SELECT * FROM cloud_broadcast_plan_recipient_messages WHERE recipient_id = ? ORDER BY id ASC LIMIT 1",
            (recipient_id,),
        ).fetchone()
        outbound_task = (
            outbound_task_service.get_outbound_task(int(final_job.get("outbound_task_id") or 0))
            if final_job.get("outbound_task_id")
            else None
        )
        request_payload = _decode_json((outbound_task or {}).get("request_payload"), default={})
        if request_payload.get("sender") != EXPECTED_OWNER_USERID:
            raise RuntimeError(f"unexpected sender in outbound task: {request_payload}")
        if request_payload.get("external_userid") != [EXPECTED_EXTERNAL_USERID]:
            raise RuntimeError(f"unexpected receiver in outbound task: {request_payload}")
        if final_job.get("status") != "sent" or int(final_job.get("sent_count") or 0) != 1 or int(final_job.get("failed_count") or 0) != 0:
            raise RuntimeError(f"broadcast job did not finish cleanly: {final_job}")
        if dict(recipient or {}).get("send_status") != "sent" or dict(recipient or {}).get("approval_status") != "approved":
            raise RuntimeError(f"recipient state invalid: {dict(recipient or {})}")
        if dict(message or {}).get("status") != "sent":
            raise RuntimeError(f"message state invalid: {dict(message or {})}")

    return {
        "ok": True,
        "plan_id": plan_id,
        "recipient_id": recipient_id,
        "broadcast_job_id": broadcast_job_id,
        "message_content": content_text,
        "sent_count": int(final_job.get("sent_count") or 0),
        "failed_count": int(final_job.get("failed_count") or 0),
        "receiver_external_userid": EXPECTED_EXTERNAL_USERID,
        "sender_owner_userid": EXPECTED_OWNER_USERID,
        "outbound_task_id": final_job.get("outbound_task_id"),
    }


if __name__ == "__main__":
    print_json(run(), indent=2)

