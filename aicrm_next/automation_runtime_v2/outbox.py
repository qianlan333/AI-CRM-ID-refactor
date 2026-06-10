from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from aicrm_next.shared.postgres_connection import get_db

from .domain import TRIGGER_ON_ENTER_STAGE, TRIGGER_SCHEDULED, TRIGGER_WEBHOOK_PUSH, as_int, text
from .membership_service import get_membership
from .task_planner import get_plan, update_plan_status


def _source_id(plan: dict[str, Any]) -> str:
    trigger = text(plan.get("trigger_type"))
    task_id = as_int(plan.get("task_id"))
    membership_id = as_int(plan.get("membership_id"))
    if trigger == TRIGGER_ON_ENTER_STAGE:
        return f"v2:stage:{as_int(plan.get('stage_entry_id'))}:task:{task_id}:member:{membership_id}"
    if trigger == TRIGGER_SCHEDULED:
        return f"v2:scheduled:{text(plan.get('schedule_key'))}:task:{task_id}:member:{membership_id}"
    if trigger == TRIGGER_WEBHOOK_PUSH:
        return f"v2:webhook:{as_int(plan.get('event_id'))}:task:{task_id}:member:{membership_id}"
    return f"v2:event:{as_int(plan.get('event_id'))}:task:{task_id}:member:{membership_id}"


def enqueue(task_plan_id: int, *, operator_id: str = "automation_runtime_v2") -> dict[str, Any]:
    plan = get_plan(int(task_plan_id))
    if not plan:
        raise LookupError("task_plan_not_found")
    if as_int(plan.get("broadcast_job_id")) > 0:
        return {"status": "duplicate", "broadcast_job_id": as_int(plan.get("broadcast_job_id"))}
    rendered = dict(plan.get("rendered_content_json") or {})
    if text(plan.get("status")) != "rendered" or not rendered:
        return {"status": "skipped", "reason": "plan_not_rendered"}
    membership = get_membership(as_int(plan.get("membership_id"))) or {}
    external = text(membership.get("external_userid"))
    if not external:
        updated = update_plan_status(int(task_plan_id), "failed", skip_reason="external_userid_missing")
        return {"status": "failed", "reason": "external_userid_missing", "plan": updated}
    source_id = _source_id(plan)
    payload = {
        "runtime_version": "v2",
        "task_plan_id": int(task_plan_id),
        "task_id": as_int(plan.get("task_id")),
        "membership_id": as_int(plan.get("membership_id")),
        "event_id": as_int(plan.get("event_id")) or None,
        "stage_entry_id": as_int(plan.get("stage_entry_id")) or None,
        "rendered_content": rendered,
        "operator_id": text(operator_id),
    }
    job_id = _insert_broadcast_job(
        source_id=source_id,
        target_external_userids=[external],
        content_type=text(rendered.get("type")) or "text",
        content_payload=payload,
        content_summary=text(rendered.get("content_text"))[:500],
        batch_key=f"automation_runtime_v2:{as_int(plan.get('program_id'))}",
        trace_id=source_id,
        created_by=text(operator_id) or "automation_runtime_v2",
    )
    updated = update_plan_status(int(task_plan_id), "enqueued", broadcast_job_id=job_id, diagnostics={"broadcast_job_id": job_id})
    return {"status": "enqueued" if job_id else "duplicate", "broadcast_job_id": job_id, "plan": updated}


def _insert_broadcast_job(
    *,
    source_id: str,
    target_external_userids: list[str],
    content_type: str,
    content_payload: dict[str, Any],
    content_summary: str,
    batch_key: str,
    trace_id: str,
    created_by: str,
) -> int:
    db = get_db()
    row = db.execute(
        """
        INSERT INTO broadcast_jobs (
            source_type, source_id, source_table, scheduled_for, priority, batch_key,
            business_domain, idempotency_key, channel, target_kind, retry_policy_json, metadata_json,
            status, requires_approval,
            target_external_userids, target_count, target_summary,
            content_type, content_payload, content_summary,
            trace_id, created_by
        )
        VALUES (
            'automation_runtime_v2', ?, 'automation_task_plan_v2', ?, 100, ?,
            'automation_ops', ?, 'wecom_private', 'external_userid', '{}'::jsonb, '{}'::jsonb,
            'queued', FALSE,
            CAST(? AS jsonb), ?, ?,
            ?, CAST(? AS jsonb), ?,
            ?, ?
        )
        ON CONFLICT (idempotency_key) WHERE idempotency_key IS NOT NULL AND idempotency_key <> '' DO NOTHING
        RETURNING id
        """,
        (
            source_id,
            datetime.now(timezone.utc),
            batch_key,
            source_id,
            json.dumps(list(target_external_userids or []), ensure_ascii=False),
            len(list(target_external_userids or [])),
            f"runtime_v2 member {', '.join(target_external_userids)}",
            content_type,
            json.dumps(content_payload or {}, ensure_ascii=False, default=str),
            content_summary,
            trace_id,
            created_by,
        ),
    ).fetchone()
    if row:
        return int(row["id"])
    existing = db.execute(
        "SELECT id FROM broadcast_jobs WHERE idempotency_key = ? ORDER BY id DESC LIMIT 1",
        (source_id,),
    ).fetchone()
    return int((existing or {}).get("id") or 0)
