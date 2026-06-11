from __future__ import annotations

import os
import uuid
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from .db import connect, has_database_url, int_value, json_list, utcnow


class BroadcastDispatcher(Protocol):
    def dispatch(self, job: dict[str, Any]) -> dict[str, Any]: ...


class BroadcastQueueRepository(Protocol):
    def claim_due_jobs(self, *, limit: int, now: datetime, claim_token: str, lease_seconds: int) -> list[dict[str, Any]]: ...
    def mark_sent(self, job_id: int, *, outbound_task_id: Any = None, sent_count: int = 0, failed_count: int = 0) -> None: ...
    def mark_failed(self, job_id: int, *, error: str, failure_type: str = "handler_error") -> None: ...


class SafeSkippedBroadcastDispatcher:
    def dispatch(self, job: dict[str, Any]) -> dict[str, Any]:
        payload = _json_dict(job.get("content_payload"))
        if _is_wecom_private_job(job, payload):
            return _dispatch_wecom_private(job, payload)
        if _is_wecom_customer_group_job(job, payload):
            return _dispatch_wecom_customer_group(job, payload)
        return {
            "ok": False,
            "status": "skipped",
            "reason": "next_native_dispatcher_missing",
            "source_type": str(job.get("source_type") or ""),
        }


class PostgresBroadcastQueueRepository:
    def claim_due_jobs(self, *, limit: int, now: datetime, claim_token: str, lease_seconds: int) -> list[dict[str, Any]]:
        with connect() as conn:
            rows = conn.execute(
                """
                WITH due AS (
                    SELECT id
                    FROM broadcast_jobs
                    WHERE status = 'queued'
                      AND scheduled_for <= %s
                    ORDER BY priority ASC, scheduled_for ASC, id ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT %s
                )
                UPDATE broadcast_jobs bj
                SET status = 'claimed',
                    claimed_at = %s,
                    claim_token = %s,
                    lease_expires_at = %s,
                    attempt_count = attempt_count + 1,
                    updated_at = CURRENT_TIMESTAMP
                FROM due
                WHERE bj.id = due.id
                RETURNING bj.*
                """,
                (now, int(limit), now, claim_token, now + timedelta(seconds=int(lease_seconds))),
            ).fetchall()
            return [dict(row) for row in rows]

    def mark_sent(self, job_id: int, *, outbound_task_id: Any = None, sent_count: int = 0, failed_count: int = 0) -> None:
        with connect() as conn:
            conn.execute(
                """
                UPDATE broadcast_jobs
                SET status = 'sent',
                    outbound_task_id = %s,
                    sent_count = %s,
                    failed_count = %s,
                    sent_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (outbound_task_id, int(sent_count), int(failed_count), int(job_id)),
            )

    def mark_failed(self, job_id: int, *, error: str, failure_type: str = "handler_error") -> None:
        with connect() as conn:
            conn.execute(
                """
                UPDATE broadcast_jobs
                SET status = 'failed',
                    failure_type = %s,
                    last_error = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (failure_type, str(error or "")[:1000], int(job_id)),
            )


def _summary(*, limit: int, dry_run: bool) -> dict[str, Any]:
    return {
        "ok": True,
        "job": "broadcast_queue_worker",
        "limit": int(limit),
        "dry_run": bool(dry_run),
        "scanned_at": utcnow().isoformat(),
        "claimed": 0,
        "sent_ok": 0,
        "sent_failed": 0,
        "skipped": 0,
        "results": [],
        "errors": [],
    }


def _count_targets(job: dict[str, Any]) -> int:
    return len(json_list(job.get("target_external_userids"))) or int_value(job.get("target_count"))


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            decoded = json.loads(value)
        except ValueError:
            return {}
        return decoded if isinstance(decoded, dict) else {}
    return {}


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        try:
            decoded = json.loads(value)
        except ValueError:
            return []
        return decoded if isinstance(decoded, list) else []
    return []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _is_wecom_customer_group_job(job: dict[str, Any], payload: dict[str, Any]) -> bool:
    return (
        str(payload.get("channel") or "").strip() == "wecom_customer_group"
        or str(job.get("content_type") or "").strip() == "wecom_customer_group"
        or str(job.get("channel") or "").strip() == "wecom_customer_group"
    )


def _is_wecom_private_job(job: dict[str, Any], payload: dict[str, Any]) -> bool:
    return (
        _text(payload.get("channel")) == "wecom_private"
        or _text(job.get("channel")) == "wecom_private"
        or (
            _text(job.get("source_type")) == "automation_runtime_v2"
            and _text(job.get("target_kind")) == "external_userid"
        )
    )


def _record_outbound_task(
    *,
    job: dict[str, Any],
    request_payload: dict[str, Any],
    response_payload: dict[str, Any],
    status: str,
    task_type: str = "broadcast_job/group_ops",
) -> int | None:
    task_id = str(
        response_payload.get("wecom_msgid")
        or response_payload.get("msgid")
        or _json_dict(response_payload.get("result")).get("msgid")
        or _json_dict(response_payload.get("result")).get("task_id")
        or ""
    )
    with connect() as conn:
        row = conn.execute(
            """
            INSERT INTO outbound_tasks (task_type, request_payload, response_payload, wecom_task_id, status, trace_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                task_type,
                _json_dumps(request_payload),
                _json_dumps(response_payload),
                task_id,
                status,
                str(job.get("trace_id") or ""),
            ),
        ).fetchone()
    return int((row or {}).get("id") or 0) or None


def _extract_private_targets(job: dict[str, Any], payload: dict[str, Any]) -> list[str]:
    values = _json_list(job.get("target_external_userids")) or _json_list(payload.get("target_external_userids"))
    return [_text(item) for item in values if _text(item)]


def _extract_private_text(payload: dict[str, Any]) -> str:
    rendered = payload.get("rendered_content") if isinstance(payload.get("rendered_content"), dict) else {}
    return _text(rendered.get("content_text") or rendered.get("text") or payload.get("content_text") or payload.get("text"))


def _realtest_guard(*, sender_userid: str, targets: list[str], content_text: str) -> tuple[bool, str]:
    if "【RuntimeV2真实链路测试】" not in content_text and "runtime_v2_realtest_" not in content_text:
        return True, ""
    allowed_target = "wmbNXyCwAAXhagLBNjtlFj2jbQevWinQ"
    if sender_userid not in {"HuangYouCan", "QianLan"}:
        return False, "realtest_sender_not_allowed"
    if targets != [allowed_target]:
        return False, "realtest_target_not_allowed"
    return True, ""


def _dispatch_wecom_private(job: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    from aicrm_next.integration_gateway.wecom_private_adapter import build_wecom_private_message_adapter

    targets = _extract_private_targets(job, payload)
    target_count = int_value(job.get("target_count"))
    sender_userid = _text(payload.get("sender_userid") or payload.get("owner_userid"))
    content_text = _extract_private_text(payload)
    if not targets:
        return {"ok": False, "error": "target_external_userids_missing", "failure_type": "validation_failed"}
    if target_count != len(targets):
        return {"ok": False, "error": "target_count_mismatch", "failure_type": "validation_failed"}
    if not sender_userid:
        return {"ok": False, "error": "sender_userid_missing", "failure_type": "validation_failed"}
    if not content_text:
        return {"ok": False, "error": "content_text_missing", "failure_type": "validation_failed"}
    ok, reason = _realtest_guard(sender_userid=sender_userid, targets=targets, content_text=content_text)
    if not ok:
        return {"ok": False, "error": reason, "failure_type": "validation_failed"}
    request_payload = {
        "job_id": int_value(job.get("id")),
        "source_type": _text(job.get("source_type")),
        "source_id": _text(job.get("source_id")),
        "sender_userid": sender_userid,
        "external_userids": targets,
        "text": {"content": content_text},
        "content_hash": _json_dict(payload.get("rendered_content")).get("content_hash") or "",
        "content_preview": content_text[:120],
    }
    result = build_wecom_private_message_adapter().create_private_message_task(
        {"sender": sender_userid, "external_userids": targets, "text": {"content": content_text}},
        idempotency_key=_text(job.get("idempotency_key") or job.get("trace_id") or job.get("id")),
    )
    failure_type = _text(result.get("error_code")) or "handler_error"
    outbound_task_id = _record_outbound_task(
        job=job,
        request_payload=request_payload,
        response_payload=result,
        status="created" if result.get("ok") else "failed",
        task_type="broadcast_job/wecom_private",
    )
    if not result.get("ok"):
        return {
            "ok": False,
            "error": _text(result.get("error_message") or result.get("error_code") or "wecom private message dispatch failed"),
            "failure_type": failure_type,
            "outbound_task_id": outbound_task_id,
        }
    if not outbound_task_id:
        return {"ok": False, "error": "outbound_task_record_missing", "failure_type": "handler_error"}
    return {
        "ok": True,
        "sent_count": len(targets),
        "failed_count": 0,
        "outbound_task_id": outbound_task_id,
        "wecom_msgid": _text(result.get("wecom_msgid") or _json_dict(result.get("result")).get("msgid")),
    }


def _dispatch_wecom_customer_group(job: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    from aicrm_next.integration_gateway.wecom_group_adapter import build_wecom_group_message_adapter

    existing_outbound_task_id = int_value(job.get("outbound_task_id"))
    if existing_outbound_task_id:
        return {
            "ok": True,
            "sent_count": len(list(payload.get("chat_ids") or [])),
            "failed_count": 0,
            "outbound_task_id": existing_outbound_task_id,
        }
    result = build_wecom_group_message_adapter().create_group_message_task(
        payload,
        idempotency_key=str(job.get("idempotency_key") or job.get("trace_id") or job.get("id") or ""),
    )
    if result.get("ok") and result.get("exact_target_verified") is not True:
        chats = ",".join([str(item) for item in list(result.get("requested_chat_ids") or payload.get("chat_ids") or [])])
        return {"ok": False, "error": f"exact target not verified for requested chat ids: {chats}"}
    outbound_task_id = _record_outbound_task(
        job=job,
        request_payload=payload,
        response_payload=result,
        status="created" if result.get("ok") else "failed",
    )
    if not result.get("ok"):
        error = str(result.get("error_message") or result.get("error_code") or "wecom group message dispatch failed")
        return {"ok": False, "error": error, "outbound_task_id": outbound_task_id}
    return {
        "ok": True,
        "sent_count": len(list(payload.get("chat_ids") or [])),
        "failed_count": 0,
        "outbound_task_id": outbound_task_id,
    }


def run_broadcast_queue_worker(
    *,
    limit: int = 50,
    dry_run: bool = False,
    repo: BroadcastQueueRepository | None = None,
    dispatcher: BroadcastDispatcher | None = None,
    now: datetime | None = None,
    lease_seconds: int | None = None,
) -> dict[str, Any]:
    summary = _summary(limit=limit, dry_run=dry_run)
    if int(limit) <= 0:
        return {**summary, "ok": False, "errors": [{"code": "invalid_limit", "message": "limit must be >= 1"}]}
    if dry_run and repo is None:
        return {**summary, "status": "skipped", "skipped": 1, "skipped_components": [{"component": "postgres_repository", "status": "skipped", "reason": "dry_run"}]}
    if repo is None and not has_database_url():
        return {**summary, "ok": False, "errors": [{"code": "database_url_missing", "message": "DATABASE_URL is required"}]}

    repo = repo or PostgresBroadcastQueueRepository()
    dispatcher = dispatcher or SafeSkippedBroadcastDispatcher()
    current_time = now or utcnow()
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    lease = int(lease_seconds or int(os.getenv("BROADCAST_QUEUE_LEASE_SECONDS", "900")))
    try:
        jobs = repo.claim_due_jobs(limit=int(limit), now=current_time, claim_token=f"{os.getpid()}:{uuid.uuid4().hex}", lease_seconds=lease)
        summary["claimed"] = len(jobs)
        for job in jobs:
            job_id = int(job.get("id") or 0)
            outcome = dispatcher.dispatch(job)
            if outcome.get("ok"):
                sent_count = int_value(outcome.get("sent_count")) or _count_targets(job)
                repo.mark_sent(
                    job_id,
                    outbound_task_id=outcome.get("outbound_task_id") or outcome.get("task_id"),
                    sent_count=sent_count,
                    failed_count=int_value(outcome.get("failed_count")),
                )
                summary["sent_ok"] += 1
                summary["results"].append({"id": job_id, "status": "sent", "sent_count": sent_count})
                continue
            reason = str(outcome.get("reason") or outcome.get("error") or "next_native_dispatch_failed")
            repo.mark_failed(
                job_id,
                error=reason,
                failure_type=str(outcome.get("failure_type") or ("next_native_dispatch_skipped" if outcome.get("status") == "skipped" else "handler_error")),
            )
            summary["sent_failed"] += 1
            if outcome.get("status") == "skipped":
                summary["skipped"] += 1
            summary["results"].append({"id": job_id, "status": outcome.get("status") or "failed", "reason": reason, "failure_type": outcome.get("failure_type") or ""})
        return summary
    except Exception as exc:
        return {**summary, "ok": False, "errors": [{"code": "broadcast_queue_worker_failed", "message": str(exc)}]}
