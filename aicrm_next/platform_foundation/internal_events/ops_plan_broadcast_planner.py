from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aicrm_next.background_jobs.db import connect, has_database_url
from aicrm_next.cloud_orchestrator.time_helpers import DEFAULT_TIMEZONE, campaign_step_due_iso

from .models import InternalEvent, InternalEventConsumerRun

_PRIVATE_CHANNEL = "wecom_private"
_TARGET_KIND = "external_userid"
_PRIVATE_CONTENT_TYPE = "private_message"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return default


def _json_load(value: Any, *, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        decoded = json.loads(str(value))
    except (TypeError, ValueError):
        return default
    return decoded if isinstance(decoded, type(default)) else default


def _json_dump(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True, default=str)


def _hash16(*parts: Any) -> str:
    return hashlib.sha256(_json_dump(parts).encode("utf-8")).hexdigest()[:16]


def _plan_date_from_id(plan_id: str) -> str:
    match = re.search(r"(?<!\d)(20\d{6})(?!\d)", _text(plan_id))
    if not match:
        return ""
    raw = match.group(1)
    return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"


def _plan_time_from_id(plan_id: str) -> str:
    match = re.search(r"20\d{6}[_-]([01]\d|2[0-3])([0-5]\d)(?!\d)", _text(plan_id))
    if not match:
        match = re.search(r"(?:^|[_-])([01]\d|2[0-3])([0-5]\d)(?:$|[_-])", _text(plan_id))
    if not match:
        return ""
    return f"{match.group(1)}:{match.group(2)}"


def _parse_datetime(value: Any, *, timezone_name: str = DEFAULT_TIMEZONE) -> datetime | None:
    raw = _text(value)
    if not raw:
        return None
    normalized = raw.replace(" ", "T", 1)
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    try:
        tzinfo = ZoneInfo(timezone_name or DEFAULT_TIMEZONE)
    except (ZoneInfoNotFoundError, ValueError):
        tzinfo = ZoneInfo(DEFAULT_TIMEZONE)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tzinfo)
    return parsed


def _find_datetime_hint(payload: Any) -> str:
    if isinstance(payload, dict):
        for key in ("scheduled_for", "scheduled_at", "send_at", "first_scheduled_for"):
            value = _text(payload.get(key))
            if value:
                return value
        for value in payload.values():
            found = _find_datetime_hint(value)
            if found:
                return found
    if isinstance(payload, list):
        for item in payload:
            found = _find_datetime_hint(item)
            if found:
                return found
    return ""


def _scheduled_from_plan(*, plan_id: str, day_offset: int, send_time: str, timezone_name: str, hints: list[Any]) -> str:
    for hint in hints:
        parsed = _parse_datetime(_find_datetime_hint(hint), timezone_name=timezone_name)
        if parsed:
            base = parsed + timedelta(days=int(day_offset or 0))
            if send_time:
                hour, minute = [int(part) for part in send_time.split(":", 1)]
                base = base.replace(hour=hour, minute=minute)
            return base.isoformat()
    plan_date = _plan_date_from_id(plan_id)
    plan_time = _text(send_time) or _plan_time_from_id(plan_id)
    if not plan_date or not plan_time:
        return ""
    return campaign_step_due_iso(
        anchor_date=plan_date,
        day_offset=int(day_offset or 0),
        send_time=plan_time,
        step_timezone=timezone_name or DEFAULT_TIMEZONE,
    )


def _has_content(payload: dict[str, Any], attachments: list[Any], content_text: str) -> bool:
    if _text(content_text):
        return True
    if attachments:
        return True
    for key in ("image_library_ids", "miniprogram_library_ids", "attachment_library_ids", "attachments"):
        value = payload.get(key)
        if isinstance(value, list) and value:
            return True
    nested = payload.get("content_package") if isinstance(payload.get("content_package"), dict) else {}
    if nested:
        return _has_content(nested, [], _text(nested.get("content_text")))
    return False


@dataclass(frozen=True)
class BroadcastJobPlan:
    source_type: str
    source_table: str
    source_id: str
    scheduled_for: str
    batch_key: str
    idempotency_key: str
    business_domain: str
    channel: str
    target_kind: str
    target_external_userids: list[str]
    target_count: int
    content_type: str
    content_payload: dict[str, Any]
    content_summary: str
    trace_id: str
    created_by: str


class OpsPlanBroadcastPlannerRepository(Protocol):
    def plan_approved_plan(
        self,
        *,
        plan_id: str,
        event_id: str,
        trace_id: str,
        operator: str,
        plan_type: str,
        expected_target_count: int,
    ) -> dict[str, Any]: ...

    def diagnose_plan(self, plan_id: str) -> dict[str, Any]: ...


class PostgresOpsPlanBroadcastPlannerRepository:
    source_status = "production_postgres"

    def plan_approved_plan(
        self,
        *,
        plan_id: str,
        event_id: str,
        trace_id: str,
        operator: str,
        plan_type: str,
        expected_target_count: int,
    ) -> dict[str, Any]:
        if not has_database_url():
            return self._blocked("database_url_missing", plan_id=plan_id)
        with connect() as conn:
            jobs = self._collect_job_plans(conn, plan_id=plan_id, plan_type=plan_type, trace_id=trace_id, operator=operator)
            if not jobs:
                return self._blocked("no_eligible_broadcast_targets", plan_id=plan_id)
            actual_targets = sorted({target for job in jobs for target in job.target_external_userids if _text(target)})
            if expected_target_count and len(actual_targets) != int(expected_target_count):
                return self._blocked(
                    "target_count_mismatch",
                    plan_id=plan_id,
                    expected_target_count=expected_target_count,
                    actual_target_count=len(actual_targets),
                )
            created_ids: list[int] = []
            reused_ids: list[int] = []
            for job in jobs:
                row = self._insert_job(conn, job)
                if row.get("created"):
                    created_ids.append(int(row["id"]))
                elif row.get("id"):
                    reused_ids.append(int(row["id"]))
            all_ids = sorted({*created_ids, *reused_ids})
            return {
                "ok": True,
                "planner_status": "planned",
                "broadcast_job_ids": all_ids,
                "created_broadcast_job_ids": created_ids,
                "reused_broadcast_job_ids": reused_ids,
                "scheduled_for": sorted({job.scheduled_for for job in jobs}),
                "planned_count": len(actual_targets),
                "queued_count": len(all_ids),
                "blocked_reason": "",
                "skipped_reason": "",
                "source_status": self.source_status,
                "real_external_call_executed": False,
                "event_id": event_id,
            }

    def diagnose_plan(self, plan_id: str) -> dict[str, Any]:
        if not has_database_url():
            return {"ok": False, "error": "database_url_missing", "plan_id": _text(plan_id), "real_external_call_executed": False}
        with connect() as conn:
            cloud = self._cloud_status(conn, plan_id)
            legacy = self._legacy_status(conn, plan_id)
            members = self._campaign_member_status(conn, plan_id)
            jobs = self._broadcast_job_status(conn, plan_id)
            events = self._internal_event_status(conn, plan_id)
        queued_1230 = [
            job
            for job in jobs.get("items", [])
            if _text(job.get("status")) in {"queued", "claimed", "sent"}
            and ("12:30" in _text(job.get("scheduled_for_label")) or "12:30" in _text(job.get("scheduled_for")))
        ]
        blocked_reason = ""
        if not jobs.get("total_count"):
            blocked_reason = "no_broadcast_jobs"
        elif not queued_1230:
            blocked_reason = "no_1230_queued_job"
        return {
            "ok": True,
            "plan_id": _text(plan_id),
            "cloud_broadcast_plans": cloud,
            "legacy_campaigns": legacy,
            "campaign_members": members,
            "broadcast_jobs": jobs,
            "internal_event": events,
            "will_execute_at_1230": bool(queued_1230),
            "blocked_reason": blocked_reason,
            "real_external_call_executed": False,
        }

    def _blocked(self, reason: str, **extra: Any) -> dict[str, Any]:
        return {
            "ok": False,
            "planner_status": "blocked",
            "broadcast_job_ids": [],
            "scheduled_for": [],
            "planned_count": 0,
            "queued_count": 0,
            "blocked_reason": reason,
            "skipped_reason": reason,
            "source_status": self.source_status,
            "real_external_call_executed": False,
            **extra,
        }

    def _collect_job_plans(self, conn: Any, *, plan_id: str, plan_type: str, trace_id: str, operator: str) -> list[BroadcastJobPlan]:
        if _text(plan_type) == "legacy_campaign":
            jobs = self._collect_legacy_job_plans(conn, plan_id=plan_id, trace_id=trace_id, operator=operator)
            return jobs or self._collect_cloud_job_plans(conn, plan_id=plan_id, trace_id=trace_id, operator=operator)
        jobs = self._collect_cloud_job_plans(conn, plan_id=plan_id, trace_id=trace_id, operator=operator)
        return jobs or self._collect_legacy_job_plans(conn, plan_id=plan_id, trace_id=trace_id, operator=operator)

    def _collect_cloud_job_plans(self, conn: Any, *, plan_id: str, trace_id: str, operator: str) -> list[BroadcastJobPlan]:
        rows = conn.execute(
            """
            SELECT p.plan_id, p.display_name, p.intent, p.owner_userid AS plan_owner_userid,
                   p.trace_id AS plan_trace_id, p.selection_json, p.explanation_json,
                   p.simulate_summary_json, p.created_at,
                   r.id AS recipient_id, r.external_userid, r.owner_userid AS recipient_owner_userid,
                   r.display_name AS recipient_display_name,
                   m.id AS message_id, m.sequence_index, m.day_offset, m.send_time,
                   m.content_text, m.content_payload_json, m.attachments_json
            FROM cloud_broadcast_plans p
            JOIN cloud_broadcast_plan_recipients r ON r.plan_id = p.plan_id
            JOIN cloud_broadcast_plan_recipient_messages m ON m.recipient_id = r.id
            WHERE p.plan_id = %s
              AND COALESCE(r.external_userid, '') <> ''
              AND COALESCE(r.send_status, 'pending') IN ('pending', 'queued')
              AND COALESCE(m.status, 'pending') IN ('pending', 'queued')
            ORDER BY m.sequence_index ASC, m.id ASC, r.id ASC
            """,
            (_text(plan_id),),
        ).fetchall()
        groups: dict[str, dict[str, Any]] = {}
        for row in rows:
            item = dict(row)
            payload = _json_load(item.get("content_payload_json"), default={})
            attachments = _json_load(item.get("attachments_json"), default=[])
            content_text = _text(item.get("content_text") or payload.get("content_text"))
            sender = _text(item.get("recipient_owner_userid") or item.get("plan_owner_userid"))
            send_time = _text(item.get("send_time")) or _plan_time_from_id(plan_id)
            scheduled_for = _scheduled_from_plan(
                plan_id=plan_id,
                day_offset=_int(item.get("day_offset")),
                send_time=send_time,
                timezone_name=_text(payload.get("timezone")) or DEFAULT_TIMEZONE,
                hints=[payload, item.get("selection_json"), item.get("explanation_json"), item.get("simulate_summary_json")],
            )
            content_hash = _hash16(content_text, payload, attachments, sender, scheduled_for)
            key = f"{_int(item.get('sequence_index'))}:{scheduled_for}:{sender}:{content_hash}"
            bucket = groups.setdefault(
                key,
                {
                    "row": item,
                    "payload": payload,
                    "attachments": attachments,
                    "content_text": content_text,
                    "sender": sender,
                    "scheduled_for": scheduled_for,
                    "targets": [],
                    "members": [],
                },
            )
            bucket["targets"].append(_text(item.get("external_userid")))
            bucket["members"].append({"recipient_id": _int(item.get("recipient_id")), "message_id": _int(item.get("message_id"))})
        jobs: list[BroadcastJobPlan] = []
        for bucket in groups.values():
            if not bucket["scheduled_for"] or not bucket["sender"] or not _has_content(bucket["payload"], bucket["attachments"], bucket["content_text"]):
                continue
            row = bucket["row"]
            source_id = f"{_text(plan_id)}:{_int(row.get('sequence_index'))}:{_hash16(bucket['scheduled_for'], bucket['content_text'], bucket['payload'], bucket['attachments'], bucket['sender'])}"
            payload = {
                "channel": _PRIVATE_CHANNEL,
                "target_kind": _TARGET_KIND,
                "sender_userid": bucket["sender"],
                "target_external_userids": bucket["targets"],
                "content_text": bucket["content_text"],
                "content_package": bucket["payload"],
                "attachments": bucket["attachments"],
                "plan_id": _text(plan_id),
                "plan_type": "cloud_plan",
                "message_mode": "plan_approval_batch",
                "members": bucket["members"],
                "real_external_call_executed": False,
            }
            jobs.append(
                BroadcastJobPlan(
                    source_type="cloud_plan",
                    source_table="cloud_broadcast_plan_recipient_messages",
                    source_id=source_id,
                    scheduled_for=bucket["scheduled_for"],
                    batch_key=f"ops_plan:{_text(plan_id)}",
                    idempotency_key=f"ops_plan.approved:broadcast_task_planner:{source_id}",
                    business_domain="ai_assistant",
                    channel=_PRIVATE_CHANNEL,
                    target_kind=_TARGET_KIND,
                    target_external_userids=list(bucket["targets"]),
                    target_count=len(bucket["targets"]),
                    content_type=_PRIVATE_CONTENT_TYPE,
                    content_payload=payload,
                    content_summary=bucket["content_text"][:200],
                    trace_id=_text(trace_id or row.get("plan_trace_id") or plan_id),
                    created_by=_text(operator) or "internal_event",
                )
            )
        return jobs

    def _collect_legacy_job_plans(self, conn: Any, *, plan_id: str, trace_id: str, operator: str) -> list[BroadcastJobPlan]:
        rows = conn.execute(
            """
            SELECT cm.id AS cm_id, cm.member_id, cm.external_contact_id, cm.campaign_id,
                   cm.campaign_segment_id, cm.anchor_date, cm.next_due_at, cm.trace_id AS member_trace_id,
                   c.campaign_code, c.owner_userid, c.trace_id AS campaign_trace_id,
                   c.anchor_date AS campaign_anchor_date, c.metadata_json,
                   cs.id AS step_id, cs.step_index, cs.day_offset, cs.send_time,
                   cs.timezone, cs.content_text, cs.content_payload_json,
                   cs.stop_on_reply, cs.skip_if_recently_touched_days
            FROM campaign_members cm
            JOIN campaigns c ON c.id = cm.campaign_id
            JOIN LATERAL (
                SELECT *
                FROM campaign_steps cs
                WHERE cs.campaign_segment_id = cm.campaign_segment_id
                ORDER BY cs.step_index ASC, cs.id ASC
                LIMIT 1
            ) cs ON TRUE
            WHERE COALESCE(NULLIF(c.metadata_json->>'group_code', ''), c.campaign_code) = %s
              AND COALESCE(cm.external_contact_id, '') <> ''
              AND cm.status IN ('pending', 'queued', 'running')
            ORDER BY cm.id ASC
            """,
            (_text(plan_id),),
        ).fetchall()
        groups: dict[str, dict[str, Any]] = {}
        for row in rows:
            item = dict(row)
            payload = _json_load(item.get("content_payload_json"), default={})
            content_text = _text(item.get("content_text") or payload.get("content_text"))
            sender = _text(item.get("owner_userid"))
            scheduled_for = _text(item.get("next_due_at"))
            if not scheduled_for:
                anchor_date = _text(item.get("anchor_date") or item.get("campaign_anchor_date") or _plan_date_from_id(plan_id))
                scheduled_for = campaign_step_due_iso(
                    anchor_date=anchor_date,
                    day_offset=_int(item.get("day_offset")),
                    send_time=_text(item.get("send_time")) or _plan_time_from_id(plan_id) or "09:00",
                    step_timezone=_text(item.get("timezone")) or DEFAULT_TIMEZONE,
                )
            source_id = f"{_int(item['campaign_id'])}:{_int(item['campaign_segment_id'])}:{_int(item.get('step_index'))}"
            bucket = groups.setdefault(
                source_id,
                {
                    "row": item,
                    "payload": payload,
                    "content_text": content_text,
                    "sender": sender,
                    "scheduled_for": scheduled_for,
                    "targets": [],
                    "members": [],
                },
            )
            bucket["targets"].append(_text(item.get("external_contact_id")))
            bucket["members"].append(
                {
                    "cm_id": _int(item.get("cm_id")),
                    "member_id": _int(item.get("member_id")),
                    "campaign_segment_id": _int(item.get("campaign_segment_id")),
                    "trace_id": _text(item.get("member_trace_id")),
                }
            )
        jobs: list[BroadcastJobPlan] = []
        for source_id, bucket in groups.items():
            if not bucket["scheduled_for"] or not bucket["sender"] or not _has_content(bucket["payload"], [], bucket["content_text"]):
                continue
            row = bucket["row"]
            conn.execute(
                """
                UPDATE campaign_members
                SET next_due_at = %s::timestamptz,
                    current_step_index = CASE WHEN COALESCE(current_step_index, -1) < 0 THEN -1 ELSE current_step_index END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ANY(%s)
                """,
                (bucket["scheduled_for"], [member["cm_id"] for member in bucket["members"]]),
            )
            payload = {
                "channel": _PRIVATE_CHANNEL,
                "target_kind": _TARGET_KIND,
                "sender_userid": bucket["sender"],
                "target_external_userids": bucket["targets"],
                "content_text": bucket["content_text"],
                "campaign": {
                    "id": _int(row.get("campaign_id")),
                    "campaign_code": _text(row.get("campaign_code")),
                    "owner_userid": bucket["sender"],
                    "trace_id": _text(row.get("campaign_trace_id") or row.get("member_trace_id")),
                },
                "step": {
                    "id": _int(row.get("step_id")),
                    "step_index": _int(row.get("step_index")),
                    "day_offset": _int(row.get("day_offset")),
                    "send_time": _text(row.get("send_time")),
                    "timezone": _text(row.get("timezone")),
                    "content_text": bucket["content_text"],
                    "content_payload_json": bucket["payload"],
                    "stop_on_reply": bool(row.get("stop_on_reply")),
                    "skip_if_recently_touched_days": _int(row.get("skip_if_recently_touched_days")),
                },
                "members": bucket["members"],
                "plan_id": _text(plan_id),
                "plan_type": "legacy_campaign",
                "real_external_call_executed": False,
            }
            jobs.append(
                BroadcastJobPlan(
                    source_type="campaign",
                    source_table="campaign_members",
                    source_id=source_id,
                    scheduled_for=bucket["scheduled_for"],
                    batch_key=_text(plan_id),
                    idempotency_key=f"campaign_member_step:{source_id}",
                    business_domain="ai_assistant",
                    channel=_PRIVATE_CHANNEL,
                    target_kind=_TARGET_KIND,
                    target_external_userids=list(bucket["targets"]),
                    target_count=len(bucket["targets"]),
                    content_type=_PRIVATE_CONTENT_TYPE,
                    content_payload=payload,
                    content_summary=bucket["content_text"][:200],
                    trace_id=_text(trace_id or row.get("campaign_trace_id") or row.get("member_trace_id") or plan_id),
                    created_by=_text(operator) or "internal_event",
                )
            )
        return jobs

    def _insert_job(self, conn: Any, job: BroadcastJobPlan) -> dict[str, Any]:
        row = conn.execute(
            """
            INSERT INTO broadcast_jobs (
                source_type, source_id, source_table, scheduled_for, priority, batch_key,
                business_domain, idempotency_key, channel, target_kind, retry_policy_json, metadata_json,
                status, requires_approval, target_external_userids, target_count, target_summary,
                content_type, content_payload, content_summary, trace_id, created_by,
                created_at, updated_at
            )
            VALUES (
                %s, %s, %s, %s::timestamptz, 100, %s,
                %s, %s, %s, %s, '{}'::jsonb, %s::jsonb,
                'queued', FALSE, %s::jsonb, %s, %s,
                %s, %s::jsonb, %s, %s, %s,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            ON CONFLICT (idempotency_key) WHERE idempotency_key IS NOT NULL AND idempotency_key <> ''
            DO NOTHING
            RETURNING id
            """,
            (
                job.source_type,
                job.source_id,
                job.source_table,
                job.scheduled_for,
                job.batch_key,
                job.business_domain,
                job.idempotency_key,
                job.channel,
                job.target_kind,
                _json_dump({"planner": "ops_plan.approved", "real_external_call_executed": False}),
                _json_dump(job.target_external_userids),
                int(job.target_count),
                f"{int(job.target_count)} 个客户",
                job.content_type,
                _json_dump(job.content_payload),
                job.content_summary,
                job.trace_id,
                job.created_by,
            ),
        ).fetchone()
        if row:
            return {"id": int(row["id"]), "created": True}
        existing = conn.execute(
            "SELECT id FROM broadcast_jobs WHERE idempotency_key = %s ORDER BY id DESC LIMIT 1",
            (job.idempotency_key,),
        ).fetchone()
        return {"id": int((existing or {}).get("id") or 0), "created": False}

    def _cloud_status(self, conn: Any, plan_id: str) -> dict[str, Any]:
        row = conn.execute(
            """
            SELECT plan_id, review_status, run_status, status, candidate_count, updated_at
            FROM cloud_broadcast_plans
            WHERE plan_id = %s
            """,
            (_text(plan_id),),
        ).fetchone()
        return dict(row or {})

    def _legacy_status(self, conn: Any, plan_id: str) -> dict[str, Any]:
        rows = conn.execute(
            """
            SELECT c.review_status, c.run_status, COUNT(*) AS count
            FROM campaigns c
            WHERE COALESCE(NULLIF(c.metadata_json->>'group_code', ''), c.campaign_code) = %s
            GROUP BY c.review_status, c.run_status
            ORDER BY c.review_status, c.run_status
            """,
            (_text(plan_id),),
        ).fetchall()
        return {"total_count": sum(_int(row.get("count")) for row in rows), "status_counts": [dict(row) for row in rows]}

    def _campaign_member_status(self, conn: Any, plan_id: str) -> dict[str, Any]:
        rows = conn.execute(
            """
            SELECT cm.status, COUNT(*) AS count, MIN(cm.next_due_at) AS min_next_due_at, MAX(cm.next_due_at) AS max_next_due_at
            FROM campaign_members cm
            JOIN campaigns c ON c.id = cm.campaign_id
            WHERE COALESCE(NULLIF(c.metadata_json->>'group_code', ''), c.campaign_code) = %s
            GROUP BY cm.status
            ORDER BY cm.status
            """,
            (_text(plan_id),),
        ).fetchall()
        return {"total_count": sum(_int(row.get("count")) for row in rows), "status_counts": [dict(row) for row in rows]}

    def _broadcast_job_status(self, conn: Any, plan_id: str) -> dict[str, Any]:
        like = f"{_text(plan_id)}:%"
        rows = conn.execute(
            """
            SELECT id, source_type, source_table, source_id, status, scheduled_for,
                   TO_CHAR(scheduled_for AT TIME ZONE 'Asia/Shanghai', 'YYYY-MM-DD HH24:MI:SS') AS scheduled_for_label,
                   target_count, last_error
            FROM broadcast_jobs
            WHERE batch_key = %s
               OR source_id = %s
               OR source_id LIKE %s
               OR content_payload->>'plan_id' = %s
            ORDER BY scheduled_for ASC, id ASC
            LIMIT 200
            """,
            (_text(plan_id), _text(plan_id), like, _text(plan_id)),
        ).fetchall()
        counts: dict[str, int] = {}
        items: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            status = _text(item.get("status")) or "unknown"
            counts[status] = counts.get(status, 0) + 1
            items.append(item)
        return {"total_count": len(items), "status_counts": counts, "items": items}

    def _internal_event_status(self, conn: Any, plan_id: str) -> dict[str, Any]:
        rows = conn.execute(
            """
            SELECT e.event_id, e.event_type, e.created_at, r.consumer_name, r.status, r.last_error_code, r.last_error_message
            FROM internal_event e
            LEFT JOIN internal_event_consumer_run r ON r.event_id = e.event_id
            WHERE e.aggregate_id = %s OR e.trace_id = %s
            ORDER BY e.created_at DESC, r.consumer_name ASC
            LIMIT 200
            """,
            (_text(plan_id), _text(plan_id)),
        ).fetchall()
        return {"total_rows": len(rows), "items": [dict(row) for row in rows]}


class InternalEventOpsPlanBroadcastPlannerService:
    def __init__(self, repository: OpsPlanBroadcastPlannerRepository | None = None) -> None:
        self._repo = repository or PostgresOpsPlanBroadcastPlannerRepository()

    def plan_event(self, event: InternalEvent, run: InternalEventConsumerRun) -> dict[str, Any]:
        payload_summary = event.payload_summary_json if isinstance(event.payload_summary_json, dict) else {}
        payload = event.payload_json if isinstance(event.payload_json, dict) else {}
        plan_id = _text(payload_summary.get("plan_id") or payload.get("plan_id") or event.aggregate_id or event.subject_id)
        plan_type = _text(payload_summary.get("plan_type") or payload.get("plan_type") or payload_summary.get("source"))
        operator = _text(payload_summary.get("operator") or payload.get("operator") or run.locked_by)
        expected_target_count = _int(payload_summary.get("target_count") or payload.get("target_count"))
        if not plan_id:
            return {
                "ok": False,
                "planner_status": "blocked",
                "blocked_reason": "plan_id_missing",
                "skipped_reason": "plan_id_missing",
                "broadcast_job_ids": [],
                "scheduled_for": [],
                "planned_count": 0,
                "queued_count": 0,
                "real_external_call_executed": False,
            }
        return self._repo.plan_approved_plan(
            plan_id=plan_id,
            event_id=event.event_id,
            trace_id=event.trace_id or plan_id,
            operator=operator,
            plan_type=plan_type,
            expected_target_count=expected_target_count,
        )

    def diagnose_plan(self, plan_id: str) -> dict[str, Any]:
        return self._repo.diagnose_plan(plan_id)


def build_ops_plan_broadcast_planner_service() -> InternalEventOpsPlanBroadcastPlannerService:
    return InternalEventOpsPlanBroadcastPlannerService()
