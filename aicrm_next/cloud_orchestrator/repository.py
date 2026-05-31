from __future__ import annotations

import copy
import json
import os
from datetime import datetime, timezone
from typing import Any, Protocol

from aicrm_next.shared.repository_provider import RepositoryProviderError
from aicrm_next.shared.runtime import production_data_ready, raw_database_url


def _text(value: Any) -> str:
    return str(value or "").strip()


def _json(value: Any, *, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError):
        return default


def _json_dump(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False)


def _limit(value: int, *, default: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(1, min(parsed, maximum))


def _offset(value: int) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _psycopg_url(url: str) -> str:
    if url.startswith("postgresql+psycopg://"):
        return "postgresql://" + url[len("postgresql+psycopg://") :]
    return url


class CloudPlanRepository(Protocol):
    def list_plans(self, *, status: str = "", keyword: str = "", limit: int = 20, offset: int = 0) -> tuple[list[dict[str, Any]], int]: ...
    def get_plan(self, plan_id: str) -> dict[str, Any] | None: ...
    def plan_stats(self, plan_id: str) -> dict[str, int]: ...
    def list_recipients(self, plan_id: str, *, status: str = "", limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]: ...
    def get_recipient(self, plan_id: str, recipient_id: int) -> dict[str, Any] | None: ...
    def list_recipient_messages(self, recipient_id: int) -> list[dict[str, Any]]: ...
    def approve_plan(self, plan_id: str, *, operator: str) -> dict[str, Any] | None: ...
    def reject_plan(self, plan_id: str, *, operator: str, reason: str = "") -> dict[str, Any] | None: ...
    def approve_recipient(self, plan_id: str, recipient_id: int, *, operator: str) -> dict[str, Any]: ...
    def reject_recipient(self, plan_id: str, recipient_id: int, *, operator: str, reason: str = "") -> dict[str, Any]: ...


def _plan_view(row: dict[str, Any], stats: dict[str, int] | None = None) -> dict[str, Any]:
    selection = _json(row.get("selection_json"), default={})
    stats = stats or {}
    target_count = int(row.get("target_count") or row.get("candidate_count") or stats.get("target_count") or 0)
    return {
        "plan_id": _text(row.get("plan_id")),
        "display_name": _text(row.get("display_name")) or _text(row.get("intent")) or _text(row.get("plan_id")),
        "owner_userid": _text(row.get("owner_userid")) or _text(selection.get("owner_userid")),
        "target_count": target_count,
        "approved_count": int(stats.get("approved_count") or 0),
        "pending_count": int(stats.get("pending_count") or 0),
        "rejected_count": int(stats.get("rejected_count") or 0),
        "sent_count": int(stats.get("sent_count") or 0),
        "failed_count": int(stats.get("failed_count") or 0),
        "review_status": _text(row.get("review_status")) or ("rejected" if _text(row.get("status")) == "rejected" else "pending_review"),
        "run_status": _text(row.get("run_status")) or _text(row.get("status")) or "draft",
        "updated_at": row.get("updated_at") or "",
    }


def _recipient_view(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "recipient_id": int(row.get("id") or row.get("recipient_id") or 0),
        "external_userid": _text(row.get("external_userid")),
        "display_name": _text(row.get("display_name")) or _text(row.get("external_userid")),
        "owner_userid": _text(row.get("owner_userid")),
        "updated_at": row.get("updated_at") or "",
        "planned_message_count": int(row.get("planned_message_count") or 0),
        "approval_status": _text(row.get("approval_status")) or "pending",
        "send_status": _text(row.get("send_status")) or "pending",
        "approved_by": _text(row.get("approved_by")),
        "approved_at": row.get("approved_at"),
        "rejected_by": _text(row.get("rejected_by")),
        "rejected_at": row.get("rejected_at"),
        "reject_reason": _text(row.get("reject_reason")),
        "broadcast_job_id": row.get("broadcast_job_id"),
        "last_error": _text(row.get("last_error")),
    }


def _message_view(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "message_id": int(row.get("id") or row.get("message_id") or 0),
        "sequence_index": int(row.get("sequence_index") or 0),
        "day_offset": int(row.get("day_offset") or 0),
        "send_time": _text(row.get("send_time")),
        "content_text": _text(row.get("content_text")),
        "content_payload": _json(row.get("content_payload_json"), default={}),
        "attachments": _json(row.get("attachments_json"), default=[]),
        "status": _text(row.get("status")) or "pending",
        "sent_at": row.get("sent_at"),
        "last_error": _text(row.get("last_error")),
    }


class PostgresCloudPlanRepository:
    def __init__(self, database_url: str | None = None) -> None:
        self._database_url = _psycopg_url(_text(database_url or raw_database_url() or os.getenv("DATABASE_URL")))
        if not self._database_url:
            raise RepositoryProviderError("cloud_orchestrator production repository unavailable: DATABASE_URL is required")

    def _connect(self):
        try:
            import psycopg
            from psycopg.rows import dict_row

            return psycopg.connect(self._database_url, row_factory=dict_row)
        except Exception as exc:
            raise RepositoryProviderError(f"cloud_orchestrator production repository unavailable: {exc}") from exc

    def _audit(self, conn, *, operator: str, action_type: str, target_type: str, target_id: str, before: dict[str, Any], after: dict[str, Any]) -> None:
        conn.execute(
            """
            INSERT INTO admin_operation_logs (operator, action_type, target_type, target_id, before_json, after_json, created_at)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, CURRENT_TIMESTAMP)
            """,
            (_text(operator) or "crm_console", action_type, target_type, target_id, _json_dump(before), _json_dump(after)),
        )

    def _stats_for_plan_ids(self, conn, plan_ids: list[str]) -> dict[str, dict[str, int]]:
        if not plan_ids:
            return {}
        rows = conn.execute(
            """
            SELECT plan_id,
                   COUNT(*) AS target_count,
                   COALESCE(SUM(CASE WHEN approval_status = 'approved' THEN 1 ELSE 0 END), 0) AS approved_count,
                   COALESCE(SUM(CASE WHEN approval_status = 'pending' THEN 1 ELSE 0 END), 0) AS pending_count,
                   COALESCE(SUM(CASE WHEN approval_status = 'rejected' THEN 1 ELSE 0 END), 0) AS rejected_count,
                   COALESCE(SUM(CASE WHEN send_status = 'sent' THEN 1 ELSE 0 END), 0) AS sent_count,
                   COALESCE(SUM(CASE WHEN send_status = 'failed' THEN 1 ELSE 0 END), 0) AS failed_count
            FROM cloud_broadcast_plan_recipients
            WHERE plan_id = ANY(%s)
            GROUP BY plan_id
            """,
            (plan_ids,),
        ).fetchall()
        return {str(row["plan_id"]): {key: int(row.get(key) or 0) for key in row.keys() if key != "plan_id"} for row in rows}

    def list_plans(self, *, status: str = "", keyword: str = "", limit: int = 20, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("(COALESCE(review_status, '') = %s OR COALESCE(run_status, '') = %s OR status = %s)")
            params.extend([status, status, status])
        if keyword:
            like = f"%{keyword.lower()}%"
            clauses.append("(LOWER(plan_id) LIKE %s OR LOWER(COALESCE(display_name, intent, '')) LIKE %s OR LOWER(COALESCE(owner_userid, '')) LIKE %s)")
            params.extend([like, like, like])
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        limit = _limit(limit, default=20, maximum=100)
        offset = _offset(offset)
        with self._connect() as conn:
            total = int((conn.execute("SELECT COUNT(*) AS total FROM cloud_broadcast_plans" + where, tuple(params)).fetchone() or {}).get("total") or 0)
            rows = conn.execute(
                """
                SELECT id, plan_id, intent, display_name, owner_userid, candidate_count, selection_json,
                       review_status, run_status, status, updated_at
                FROM cloud_broadcast_plans
                """
                + where
                + " ORDER BY updated_at DESC, id DESC LIMIT %s OFFSET %s",
                tuple([*params, limit, offset]),
            ).fetchall()
            stats = self._stats_for_plan_ids(conn, [str(row["plan_id"]) for row in rows])
        return [_plan_view(dict(row), stats.get(str(row["plan_id"]), {})) for row in rows], total

    def get_plan(self, plan_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, plan_id, intent, display_name, owner_userid, candidate_count, selection_json,
                       review_status, run_status, status, updated_at
                FROM cloud_broadcast_plans
                WHERE plan_id = %s
                """,
                (_text(plan_id),),
            ).fetchone()
            if not row:
                return None
            stats = self._stats_for_plan_ids(conn, [_text(plan_id)]).get(_text(plan_id), {})
        return _plan_view(dict(row), stats)

    def plan_stats(self, plan_id: str) -> dict[str, int]:
        with self._connect() as conn:
            return self._stats_for_plan_ids(conn, [_text(plan_id)]).get(_text(plan_id), {})

    def list_recipients(self, plan_id: str, *, status: str = "", limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        clauses = ["plan_id = %s"]
        params: list[Any] = [_text(plan_id)]
        if status:
            clauses.append("(approval_status = %s OR send_status = %s)")
            params.extend([status, status])
        where = " WHERE " + " AND ".join(clauses)
        limit = _limit(limit, default=50, maximum=200)
        offset = _offset(offset)
        with self._connect() as conn:
            total = int((conn.execute("SELECT COUNT(*) AS total FROM cloud_broadcast_plan_recipients" + where, tuple(params)).fetchone() or {}).get("total") or 0)
            rows = conn.execute(
                """
                SELECT *
                FROM cloud_broadcast_plan_recipients
                """
                + where
                + " ORDER BY id ASC LIMIT %s OFFSET %s",
                tuple([*params, limit, offset]),
            ).fetchall()
        return [_recipient_view(dict(row)) for row in rows], total

    def get_recipient(self, plan_id: str, recipient_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM cloud_broadcast_plan_recipients
                WHERE plan_id = %s AND id = %s
                """,
                (_text(plan_id), int(recipient_id)),
            ).fetchone()
        return _recipient_view(dict(row)) if row else None

    def list_recipient_messages(self, recipient_id: int) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM cloud_broadcast_plan_recipient_messages
                WHERE recipient_id = %s
                ORDER BY sequence_index ASC, id ASC
                """,
                (int(recipient_id),),
            ).fetchall()
        return [_message_view(dict(row)) for row in rows]

    def approve_plan(self, plan_id: str, *, operator: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            before = conn.execute("SELECT * FROM cloud_broadcast_plans WHERE plan_id = %s FOR UPDATE", (_text(plan_id),)).fetchone()
            if not before:
                return None
            if _text(before.get("review_status") or before.get("status")) == "rejected":
                raise ValueError("plan is rejected")
            row = conn.execute(
                """
                UPDATE cloud_broadcast_plans
                SET review_status = 'approved', run_status = COALESCE(NULLIF(run_status, ''), status, 'draft'),
                    updated_at = CURRENT_TIMESTAMP
                WHERE plan_id = %s
                RETURNING *
                """,
                (_text(plan_id),),
            ).fetchone()
            self._audit(conn, operator=operator, action_type="cloud_plan_approve", target_type="cloud_broadcast_plan", target_id=_text(plan_id), before=dict(before), after=dict(row or {}))
            conn.commit()
        return self.get_plan(plan_id)

    def reject_plan(self, plan_id: str, *, operator: str, reason: str = "") -> dict[str, Any] | None:
        with self._connect() as conn:
            before = conn.execute("SELECT * FROM cloud_broadcast_plans WHERE plan_id = %s FOR UPDATE", (_text(plan_id),)).fetchone()
            if not before:
                return None
            row = conn.execute(
                """
                UPDATE cloud_broadcast_plans
                SET review_status = 'rejected', status = CASE WHEN status = 'committed' THEN status ELSE 'rejected' END,
                    error_message = %s, updated_at = CURRENT_TIMESTAMP
                WHERE plan_id = %s
                RETURNING *
                """,
                (_text(reason)[:200], _text(plan_id)),
            ).fetchone()
            self._audit(conn, operator=operator, action_type="cloud_plan_reject", target_type="cloud_broadcast_plan", target_id=_text(plan_id), before=dict(before), after=dict(row or {}))
            conn.commit()
        return self.get_plan(plan_id)

    def approve_recipient(self, plan_id: str, recipient_id: int, *, operator: str) -> dict[str, Any]:
        normalized_plan_id = _text(plan_id)
        with self._connect() as conn:
            plan = conn.execute("SELECT * FROM cloud_broadcast_plans WHERE plan_id = %s FOR UPDATE", (normalized_plan_id,)).fetchone()
            if not plan:
                raise LookupError("plan not found")
            if _text(plan.get("review_status") or plan.get("status")) == "rejected":
                raise ValueError("plan is rejected")
            if _text(plan.get("review_status")) not in {"approved", "reviewing"}:
                raise ValueError("plan is not approved for recipient review")
            recipient = conn.execute(
                "SELECT * FROM cloud_broadcast_plan_recipients WHERE plan_id = %s AND id = %s FOR UPDATE",
                (normalized_plan_id, int(recipient_id)),
            ).fetchone()
            if not recipient:
                raise LookupError("recipient not found")
            before = dict(recipient)
            if _text(recipient.get("approval_status")) == "rejected":
                raise ValueError("recipient is rejected")
            if _text(recipient.get("send_status")) == "sent":
                return {"status": "already_sent", "recipient": _recipient_view(dict(recipient)), "job_id": recipient.get("broadcast_job_id")}
            idempotency_key = f"cloud_plan_recipient:{normalized_plan_id}:{int(recipient_id)}"
            existing = conn.execute("SELECT id FROM broadcast_jobs WHERE idempotency_key = %s ORDER BY id DESC LIMIT 1", (idempotency_key,)).fetchone()
            job_id = int(existing["id"]) if existing else 0
            if not job_id:
                inserted = conn.execute(
                    """
                    INSERT INTO broadcast_jobs (
                        source_type, source_id, source_table, scheduled_for, priority, batch_key,
                        business_domain, idempotency_key, channel, target_kind, retry_policy_json, metadata_json,
                        status, requires_approval, target_external_userids, target_count, target_summary,
                        content_type, content_payload, content_summary, trace_id, created_by
                    ) VALUES (
                        'cloud_plan', %s, 'cloud_broadcast_plan_recipients', CURRENT_TIMESTAMP, 100, %s,
                        'ai_assistant', %s, 'wecom_private', 'external_userid', '{}'::jsonb, '{}'::jsonb,
                        'queued', FALSE, %s::jsonb, 1, %s,
                        'cloud_plan', %s::jsonb, %s, %s, %s
                    )
                    ON CONFLICT (idempotency_key) WHERE idempotency_key IS NOT NULL AND idempotency_key <> ''
                    DO NOTHING
                    RETURNING id
                    """,
                    (
                        f"{normalized_plan_id}:{int(recipient_id)}",
                        f"cloud_plan_recipient:{normalized_plan_id}",
                        idempotency_key,
                        _json_dump([_text(recipient.get("external_userid"))]),
                        _text(recipient.get("display_name")) or _text(recipient.get("external_userid")),
                        _json_dump(
                            {
                                "plan_id": normalized_plan_id,
                                "recipient_id": int(recipient_id),
                                "external_userid": _text(recipient.get("external_userid")),
                                "message_mode": "recipient_messages",
                            }
                        ),
                        f"{_text(plan.get('display_name')) or _text(plan.get('intent')) or normalized_plan_id} · {_text(recipient.get('display_name')) or _text(recipient.get('external_userid'))}",
                        _text(plan.get("trace_id")),
                        _text(operator) or "crm_console",
                    ),
                ).fetchone()
                if inserted:
                    job_id = int(inserted["id"])
                else:
                    existing = conn.execute("SELECT id FROM broadcast_jobs WHERE idempotency_key = %s ORDER BY id DESC LIMIT 1", (idempotency_key,)).fetchone()
                    job_id = int(existing["id"]) if existing else 0
            row = conn.execute(
                """
                UPDATE cloud_broadcast_plan_recipients
                SET approval_status = 'approved', send_status = CASE WHEN send_status = 'pending' THEN 'queued' ELSE send_status END,
                    approved_by = %s, approved_at = CURRENT_TIMESTAMP, broadcast_job_id = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING *
                """,
                (_text(operator) or "crm_console", job_id or None, int(recipient_id)),
            ).fetchone()
            conn.execute(
                """
                UPDATE cloud_broadcast_plan_recipient_messages
                SET status = CASE WHEN status = 'pending' THEN 'queued' ELSE status END, updated_at = CURRENT_TIMESTAMP
                WHERE recipient_id = %s
                """,
                (int(recipient_id),),
            )
            self._audit(conn, operator=operator, action_type="cloud_plan_recipient_approve", target_type="cloud_broadcast_plan_recipient", target_id=f"{normalized_plan_id}:{int(recipient_id)}", before=before, after=dict(row or {}))
            conn.commit()
        return {"status": "already_approved" if existing else "approved", "recipient": _recipient_view(dict(row or {})), "job_id": job_id}

    def reject_recipient(self, plan_id: str, recipient_id: int, *, operator: str, reason: str = "") -> dict[str, Any]:
        with self._connect() as conn:
            plan = conn.execute("SELECT * FROM cloud_broadcast_plans WHERE plan_id = %s", (_text(plan_id),)).fetchone()
            if not plan:
                raise LookupError("plan not found")
            if _text(plan.get("review_status") or plan.get("status")) == "rejected":
                raise ValueError("plan is rejected")
            recipient = conn.execute(
                "SELECT * FROM cloud_broadcast_plan_recipients WHERE plan_id = %s AND id = %s FOR UPDATE",
                (_text(plan_id), int(recipient_id)),
            ).fetchone()
            if not recipient:
                raise LookupError("recipient not found")
            before = dict(recipient)
            if _text(recipient.get("send_status")) == "sent":
                raise ValueError("sent recipient cannot be rejected")
            row = conn.execute(
                """
                UPDATE cloud_broadcast_plan_recipients
                SET approval_status = 'rejected', send_status = CASE WHEN send_status IN ('pending', 'queued') THEN 'cancelled' ELSE send_status END,
                    rejected_by = %s, rejected_at = CURRENT_TIMESTAMP, reject_reason = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING *
                """,
                (_text(operator) or "crm_console", _text(reason)[:500], int(recipient_id)),
            ).fetchone()
            self._audit(conn, operator=operator, action_type="cloud_plan_recipient_reject", target_type="cloud_broadcast_plan_recipient", target_id=f"{_text(plan_id)}:{int(recipient_id)}", before=before, after=dict(row or {}))
            conn.commit()
        return {"status": "rejected", "recipient": _recipient_view(dict(row or {}))}


class InMemoryCloudPlanRepository:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        now = _now()
        self.plans = [
            {
                "id": 1,
                "plan_id": "plan_probe",
                "display_name": "1.6.3 触达赵言方",
                "intent": "1.6.3 触达赵言方",
                "owner_userid": "HuangYouCan",
                "candidate_count": 2,
                "review_status": "pending_review",
                "run_status": "draft",
                "status": "draft",
                "selection_json": {"owner_userid": "HuangYouCan"},
                "updated_at": now,
            },
            {
                "id": 2,
                "plan_id": "plan_approved",
                "display_name": "1.6.3 黄永灿高意向转化",
                "intent": "1.6.3 黄永灿高意向转化",
                "owner_userid": "HuangYouCan",
                "candidate_count": 4,
                "review_status": "approved",
                "run_status": "active",
                "status": "draft",
                "selection_json": {"owner_userid": "HuangYouCan"},
                "updated_at": now,
            },
            {
                "id": 3,
                "plan_id": "plan_rejected",
                "display_name": "1.6.3 已拒绝计划",
                "intent": "1.6.3 已拒绝计划",
                "owner_userid": "OtherOwner",
                "candidate_count": 1,
                "review_status": "rejected",
                "run_status": "draft",
                "status": "rejected",
                "selection_json": {"owner_userid": "OtherOwner"},
                "updated_at": now,
            },
            {
                "id": 4,
                "plan_id": "plan_empty",
                "display_name": "空目标计划",
                "intent": "空目标计划",
                "owner_userid": "EmptyOwner",
                "candidate_count": 0,
                "review_status": "pending_review",
                "run_status": "draft",
                "status": "draft",
                "selection_json": {"owner_userid": "EmptyOwner"},
                "updated_at": now,
            },
        ]
        self.recipients = [
            {"id": 1, "plan_id": "plan_probe", "external_userid": "wm_a", "owner_userid": "HuangYouCan", "display_name": "赵言方", "planned_message_count": 1, "approval_status": "pending", "send_status": "pending", "updated_at": now},
            {"id": 2, "plan_id": "plan_probe", "external_userid": "wm_b", "owner_userid": "HuangYouCan", "display_name": "黄永灿", "planned_message_count": 1, "approval_status": "pending", "send_status": "pending", "updated_at": now},
            {"id": 3, "plan_id": "plan_approved", "external_userid": "wm_c", "owner_userid": "HuangYouCan", "display_name": "高意向A", "planned_message_count": 2, "approval_status": "approved", "send_status": "queued", "updated_at": now, "broadcast_job_id": 9001},
            {"id": 4, "plan_id": "plan_approved", "external_userid": "wm_d", "owner_userid": "HuangYouCan", "display_name": "已发送B", "planned_message_count": 1, "approval_status": "approved", "send_status": "sent", "updated_at": now, "broadcast_job_id": 9002},
            {"id": 5, "plan_id": "plan_approved", "external_userid": "wm_e", "owner_userid": "HuangYouCan", "display_name": "失败C", "planned_message_count": 1, "approval_status": "approved", "send_status": "failed", "updated_at": now, "broadcast_job_id": 9003},
            {"id": 6, "plan_id": "plan_approved", "external_userid": "wm_f", "owner_userid": "HuangYouCan", "display_name": "已拒绝D", "planned_message_count": 1, "approval_status": "rejected", "send_status": "cancelled", "updated_at": now},
        ]
        self.messages = [
            {"id": 1, "plan_id": "plan_probe", "recipient_id": 1, "external_userid": "wm_a", "sequence_index": 1, "day_offset": 0, "send_time": "10:00", "content_text": "你好", "content_payload_json": {}, "attachments_json": [], "status": "pending"},
            {"id": 2, "plan_id": "plan_probe", "recipient_id": 2, "external_userid": "wm_b", "sequence_index": 1, "day_offset": 0, "send_time": "10:00", "content_text": "你好", "content_payload_json": {}, "attachments_json": [], "status": "pending"},
            {"id": 3, "plan_id": "plan_approved", "recipient_id": 3, "external_userid": "wm_c", "sequence_index": 2, "day_offset": 1, "send_time": "11:00", "content_text": "第二条", "content_payload_json": {}, "attachments_json": [{"msgtype": "file"}], "status": "pending"},
            {"id": 4, "plan_id": "plan_approved", "recipient_id": 3, "external_userid": "wm_c", "sequence_index": 1, "day_offset": 0, "send_time": "10:00", "content_text": "第一条", "content_payload_json": {}, "attachments_json": [], "status": "pending"},
        ]
        self.broadcast_jobs: list[dict[str, Any]] = []
        self.audits: list[dict[str, Any]] = []

    def _stats(self, plan_id: str) -> dict[str, int]:
        rows = [item for item in self.recipients if item["plan_id"] == plan_id]
        return {
            "target_count": len(rows),
            "approved_count": sum(1 for item in rows if item.get("approval_status") == "approved"),
            "pending_count": sum(1 for item in rows if item.get("approval_status") == "pending"),
            "rejected_count": sum(1 for item in rows if item.get("approval_status") == "rejected"),
            "sent_count": sum(1 for item in rows if item.get("send_status") == "sent"),
            "failed_count": sum(1 for item in rows if item.get("send_status") == "failed"),
        }

    def list_plans(self, *, status: str = "", keyword: str = "", limit: int = 20, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        rows = [item for item in self.plans if (not status or item.get("review_status") == status or item.get("run_status") == status or item.get("status") == status)]
        if keyword:
            rows = [item for item in rows if keyword.lower() in (item.get("display_name", "") + item.get("plan_id", "") + item.get("owner_userid", "")).lower()]
        total = len(rows)
        rows = rows[_offset(offset) : _offset(offset) + _limit(limit, default=20, maximum=100)]
        return [_plan_view(copy.deepcopy(item), self._stats(item["plan_id"])) for item in rows], total

    def get_plan(self, plan_id: str) -> dict[str, Any] | None:
        for item in self.plans:
            if item["plan_id"] == plan_id:
                return _plan_view(copy.deepcopy(item), self._stats(plan_id))
        return None

    def plan_stats(self, plan_id: str) -> dict[str, int]:
        return self._stats(plan_id)

    def list_recipients(self, plan_id: str, *, status: str = "", limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        rows = [item for item in self.recipients if item["plan_id"] == plan_id and (not status or item.get("approval_status") == status or item.get("send_status") == status)]
        total = len(rows)
        rows = rows[_offset(offset) : _offset(offset) + _limit(limit, default=50, maximum=200)]
        return [_recipient_view(copy.deepcopy(item)) for item in rows], total

    def get_recipient(self, plan_id: str, recipient_id: int) -> dict[str, Any] | None:
        for item in self.recipients:
            if item["plan_id"] == plan_id and int(item["id"]) == int(recipient_id):
                return _recipient_view(copy.deepcopy(item))
        return None

    def list_recipient_messages(self, recipient_id: int) -> list[dict[str, Any]]:
        rows = [item for item in self.messages if int(item["recipient_id"]) == int(recipient_id)]
        rows = sorted(rows, key=lambda item: (int(item.get("sequence_index") or 0), int(item.get("id") or 0)))
        return [_message_view(copy.deepcopy(item)) for item in rows]

    def approve_plan(self, plan_id: str, *, operator: str) -> dict[str, Any] | None:
        for item in self.plans:
            if item["plan_id"] == plan_id:
                if item.get("review_status") == "rejected":
                    raise ValueError("plan is rejected")
                item["review_status"] = "approved"
                item["updated_at"] = _now()
                self.audits.append({"action_type": "cloud_plan_approve", "target_id": plan_id, "operator": operator})
                return self.get_plan(plan_id)
        return None

    def reject_plan(self, plan_id: str, *, operator: str, reason: str = "") -> dict[str, Any] | None:
        for item in self.plans:
            if item["plan_id"] == plan_id:
                item["review_status"] = "rejected"
                item["status"] = "rejected"
                item["updated_at"] = _now()
                self.audits.append({"action_type": "cloud_plan_reject", "target_id": plan_id, "operator": operator, "reason": reason})
                return self.get_plan(plan_id)
        return None

    def approve_recipient(self, plan_id: str, recipient_id: int, *, operator: str) -> dict[str, Any]:
        plan = self.get_plan(plan_id)
        if not plan:
            raise LookupError("plan not found")
        if plan["review_status"] == "rejected":
            raise ValueError("plan is rejected")
        if plan["review_status"] not in {"approved", "reviewing"}:
            raise ValueError("plan is not approved for recipient review")
        recipient = next((item for item in self.recipients if item["plan_id"] == plan_id and int(item["id"]) == int(recipient_id)), None)
        if not recipient:
            raise LookupError("recipient not found")
        if recipient.get("approval_status") == "rejected":
            raise ValueError("recipient is rejected")
        if recipient.get("send_status") == "sent":
            return {"status": "already_sent", "recipient": _recipient_view(copy.deepcopy(recipient)), "job_id": recipient.get("broadcast_job_id")}
        source_id = f"{plan_id}:{int(recipient_id)}"
        existing = next((item for item in self.broadcast_jobs if item["source_id"] == source_id), None)
        if existing:
            status = "already_approved"
            job_id = existing["id"]
        else:
            job_id = len(self.broadcast_jobs) + 1
            self.broadcast_jobs.append(
                {
                    "id": job_id,
                    "source_type": "cloud_plan",
                    "source_table": "cloud_broadcast_plan_recipients",
                    "source_id": source_id,
                    "target_external_userids": [recipient["external_userid"]],
                    "target_count": 1,
                    "content_payload": {"plan_id": plan_id, "recipient_id": int(recipient_id), "external_userid": recipient["external_userid"], "message_mode": "recipient_messages"},
                    "idempotency_key": f"cloud_plan_recipient:{plan_id}:{int(recipient_id)}",
                    "status": "queued",
                }
            )
            status = "approved"
        recipient.update({"approval_status": "approved", "send_status": "queued", "approved_by": operator, "approved_at": _now(), "broadcast_job_id": job_id, "updated_at": _now()})
        for message in self.messages:
            if int(message["recipient_id"]) == int(recipient_id) and message.get("status") == "pending":
                message["status"] = "queued"
        self.audits.append({"action_type": "cloud_plan_recipient_approve", "target_id": source_id, "operator": operator})
        return {"status": status, "recipient": _recipient_view(copy.deepcopy(recipient)), "job_id": job_id}

    def reject_recipient(self, plan_id: str, recipient_id: int, *, operator: str, reason: str = "") -> dict[str, Any]:
        plan = self.get_plan(plan_id)
        if not plan:
            raise LookupError("plan not found")
        if plan["review_status"] == "rejected":
            raise ValueError("plan is rejected")
        recipient = next((item for item in self.recipients if item["plan_id"] == plan_id and int(item["id"]) == int(recipient_id)), None)
        if not recipient:
            raise LookupError("recipient not found")
        if recipient.get("send_status") == "sent":
            raise ValueError("sent recipient cannot be rejected")
        recipient.update({"approval_status": "rejected", "send_status": "cancelled", "rejected_by": operator, "rejected_at": _now(), "reject_reason": reason, "updated_at": _now()})
        self.audits.append({"action_type": "cloud_plan_recipient_reject", "target_id": f"{plan_id}:{int(recipient_id)}", "operator": operator})
        return {"status": "rejected", "recipient": _recipient_view(copy.deepcopy(recipient))}


_FIXTURE_REPO = InMemoryCloudPlanRepository()


def reset_cloud_plan_fixture_state() -> None:
    _FIXTURE_REPO.reset()


def build_cloud_plan_repository() -> CloudPlanRepository:
    if production_data_ready():
        return PostgresCloudPlanRepository()
    return _FIXTURE_REPO
