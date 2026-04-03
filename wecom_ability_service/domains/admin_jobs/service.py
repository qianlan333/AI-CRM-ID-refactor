from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from flask import current_app

from ...http.sync_jobs import run_archive_health_check, run_manual_archive_sync
from ...infra.settings import get_setting
from ...services import get_message_batch
from ...wecom_callback import get_callback_config
from ..admin_config import repo as admin_config_repo
from ..archive.service import ack_message_batch, get_last_sync_run
from ..user_ops.service import get_user_ops_deferred_job_counts, run_due_user_ops_deferred_jobs
from . import repo

TARGET_JOBS_ACTION = "jobs_console_action"

JOB_TABS = (
    {"key": "overview", "label": "概览"},
    {"key": "archive", "label": "Archive Sync"},
    {"key": "callbacks", "label": "Callbacks"},
    {"key": "batches", "label": "Message Batches"},
    {"key": "deferred", "label": "Deferred Jobs"},
)


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _normalized_int(value: Any, *, default: int, minimum: int = 1, maximum: int = 200) -> int:
    try:
        parsed = int(value if value not in (None, "") else default)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _normalized_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _normalized_text(value).lower() in {"1", "true", "yes", "y", "on"}


def _operator(value: Any) -> str:
    return _normalized_text(value) or "crm_console"


def _status_tone(status: str) -> str:
    normalized_status = _normalized_text(status).lower()
    if normalized_status in {"success", "acked", "enabled", "healthy"}:
        return "ok"
    if normalized_status in {"failed", "disabled", "error"}:
        return "danger"
    if normalized_status in {"pending", "running", "processing", "conflict", "skipped"}:
        return "warn"
    return "neutral"


def _batch_status_options() -> list[str]:
    return ["", "pending", "acked"]


def _deferred_status_options() -> list[str]:
    return ["", "pending", "running", "success", "conflict", "skipped", "failed"]


def jobs_tabs(active_key: str) -> list[dict[str, Any]]:
    normalized_active_key = _normalized_text(active_key) or "overview"
    return [
        {
            **item,
            "active": item["key"] == normalized_active_key,
            "href": f"/admin/jobs?tab={item['key']}",
        }
        for item in JOB_TABS
    ]


def _archive_sync_form_defaults() -> dict[str, str]:
    end_time = datetime.now().replace(microsecond=0)
    start_time = end_time - timedelta(hours=1)
    return {
        "start_time": start_time.strftime("%Y-%m-%d %H:%M:%S"),
        "end_time": end_time.strftime("%Y-%m-%d %H:%M:%S"),
        "owner_userid": _normalized_text(current_app.config.get("WECOM_DEFAULT_OWNER_USERID")),
        "cursor": "",
        "operator": "",
    }


def _archive_sync_request_payload(source: Any) -> dict[str, str]:
    return {
        "start_time": _normalized_text(source.get("start_time")),
        "end_time": _normalized_text(source.get("end_time")),
        "owner_userid": _normalized_text(source.get("owner_userid")) or _normalized_text(current_app.config.get("WECOM_DEFAULT_OWNER_USERID")),
        "cursor": _normalized_text(source.get("cursor")),
    }


def _callback_enabled() -> bool:
    callback_config = get_callback_config()
    return bool(callback_config.get("token") and callback_config.get("aes_key") and callback_config.get("corp_id"))


def _mcp_auth_configured() -> bool:
    return bool(_normalized_text(get_setting("MCP_BEARER_TOKEN")) or _normalized_text(current_app.config.get("MCP_BEARER_TOKEN")))


def _audit_log(
    *,
    operator: str,
    action_type: str,
    target_id: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> None:
    admin_config_repo.insert_admin_operation_log(
        operator=_operator(operator),
        action_type=_normalized_text(action_type),
        target_type=TARGET_JOBS_ACTION,
        target_id=_normalized_text(target_id),
        before_json=before or {},
        after_json=after or {},
    )


def _sync_row_view(row: dict[str, Any]) -> dict[str, Any]:
    status = _normalized_text(row.get("status")) or "unknown"
    return {
        **row,
        "status_label": status.upper(),
        "status_tone": _status_tone(status),
        "finished_or_created_at": _normalized_text(row.get("finished_at")) or _normalized_text(row.get("created_at")) or "-",
    }


def _callback_row_view(row: dict[str, Any]) -> dict[str, Any]:
    status = _normalized_text(row.get("process_status")) or "pending"
    return {
        **row,
        "status_tone": _status_tone(status),
        "event_label": _normalized_text(row.get("change_type")) or _normalized_text(row.get("event_type")) or "callback",
    }


def _batch_row_view(row: dict[str, Any]) -> dict[str, Any]:
    status = _normalized_text(row.get("status")) or "pending"
    return {
        **row,
        "status_tone": _status_tone(status),
        "window_label": f"{_normalized_text(row.get('window_start'))} ~ {_normalized_text(row.get('window_end'))}",
    }


def _deferred_row_view(row: dict[str, Any]) -> dict[str, Any]:
    status = _normalized_text(row.get("status")) or "pending"
    return {
        **row,
        "status_tone": _status_tone(status),
    }


def _build_pending_message_batches_group() -> dict[str, Any]:
    rows = [_batch_row_view(item) for item in repo.list_message_batches(status="pending", limit=5)]
    total_count = len(rows)
    return {
        "key": "pending_message_batches",
        "title": "Pending Message Batches",
        "count": total_count,
        "description": "待确认的 archive message batches。",
        "tone": "warn" if total_count else "ok",
        "items": [
            {
                "title": f"Batch #{item['id']}",
                "meta": item["window_label"],
                "detail": f"消息 {int(item.get('message_count') or 0)} 条 · 状态 {item.get('status', 'pending')}",
            }
            for item in rows
        ],
        "empty_title": "暂无待确认批次",
        "href": "/admin/jobs?tab=batches&batch_status=pending",
    }


def _build_deferred_jobs_group() -> dict[str, Any]:
    counts = get_user_ops_deferred_job_counts()
    total_pending = int(counts.get("pending_count") or 0)
    total_failed = int(counts.get("failed_count") or 0)
    items: list[dict[str, Any]] = []
    if total_pending:
        items.append(
            {
                "title": f"{total_pending} 个待执行任务",
                "meta": "status = pending",
                "detail": "来自 user_ops_deferred_jobs",
            }
        )
    if total_failed:
        items.append(
            {
                "title": f"{total_failed} 个失败任务",
                "meta": "status = failed",
                "detail": "需要人工复查或重试",
            }
        )
    return {
        "key": "deferred_jobs",
        "title": "Deferred Jobs",
        "count": total_pending + total_failed,
        "description": "user_ops 延迟任务待处理与失败项。",
        "tone": "danger" if total_failed else ("warn" if total_pending else "ok"),
        "items": items,
        "empty_title": "暂无 deferred jobs 异常",
        "href": "/admin/jobs?tab=deferred&job_status=pending",
    }


def _build_failed_sync_group() -> dict[str, Any]:
    rows = [_sync_row_view(item) for item in repo.list_sync_runs(status="failed", limit=5)]
    return {
        "key": "failed_sync_runs",
        "title": "Failed Sync Runs",
        "count": len(rows),
        "description": "最近失败的 archive sync 任务。",
        "tone": "danger" if rows else "ok",
        "items": [
            {
                "title": f"Sync #{row['id']}",
                "meta": row["finished_or_created_at"],
                "detail": _normalized_text(row.get("error_message")) or "archive sync failed",
            }
            for row in rows
        ],
        "empty_title": "最近没有 sync 失败",
        "href": "/admin/jobs?tab=archive&archive_status=failed",
    }


def _build_failed_callbacks_group() -> dict[str, Any]:
    rows = [_callback_row_view(item) for item in repo.list_callback_logs(process_status="failed", limit=5)]
    return {
        "key": "failed_callbacks",
        "title": "Failed Callbacks",
        "count": len(rows),
        "description": "最近失败的回调处理记录。",
        "tone": "danger" if rows else "ok",
        "items": [
            {
                "title": item["event_label"],
                "meta": _normalized_text(item.get("updated_at")) or _normalized_text(item.get("created_at")) or "Never",
                "detail": _normalized_text(item.get("error_message")) or _normalized_text(item.get("external_userid")) or "callback processing failed",
            }
            for item in rows
        ],
        "empty_title": "最近没有 callback 失败",
        "href": "/admin/jobs?tab=callbacks&callback_status=failed",
    }


def build_jobs_runtime_snapshot(*, include_archive_health: bool = False) -> dict[str, Any]:
    last_sync_run = dict(get_last_sync_run() or {})
    snapshot = {
        "last_sync_run": _sync_row_view(last_sync_run) if last_sync_run else {},
        "sync_counts": repo.get_sync_run_counts(),
        "callback_enabled": _callback_enabled(),
        "background_async_enabled": bool(current_app.config.get("CALLBACK_ASYNC_ENABLED", True)),
        "callback_counts": repo.get_callback_counts(),
        "batch_counts": repo.get_message_batch_counts(),
        "deferred_counts": get_user_ops_deferred_job_counts(),
    }
    if include_archive_health:
        try:
            snapshot["archive_health"] = run_archive_health_check()
            snapshot["archive_health_error"] = ""
        except Exception as exc:
            snapshot["archive_health"] = {}
            snapshot["archive_health_error"] = str(exc)
    else:
        snapshot["archive_health"] = {}
        snapshot["archive_health_error"] = ""
    return snapshot


def build_jobs_dashboard_groups() -> list[dict[str, Any]]:
    return [
        _build_pending_message_batches_group(),
        _build_deferred_jobs_group(),
        _build_failed_callbacks_group(),
        _build_failed_sync_group(),
    ]


def build_jobs_payload(args: Any) -> dict[str, Any]:
    active_tab = _normalized_text(args.get("tab")) or "overview"
    valid_tabs = {item["key"] for item in JOB_TABS}
    if active_tab not in valid_tabs:
        active_tab = "overview"

    archive_filters = {
        "status": _normalized_text(args.get("archive_status")),
        "limit": _normalized_int(args.get("archive_limit"), default=20),
    }
    callback_filters = {
        "process_status": _normalized_text(args.get("callback_status")),
        "query": _normalized_text(args.get("callback_query")),
        "limit": _normalized_int(args.get("callback_limit"), default=20),
    }
    batch_filters = {
        "status": _normalized_text(args.get("batch_status")),
        "limit": _normalized_int(args.get("batch_limit"), default=20),
        "selected_batch_id": _normalized_text(args.get("batch_id")),
    }
    deferred_filters = {
        "status": _normalized_text(args.get("job_status")),
        "owner_userid": _normalized_text(args.get("owner_userid")),
        "external_userid": _normalized_text(args.get("external_userid")),
        "limit": _normalized_int(args.get("job_limit"), default=20),
    }

    runtime_snapshot = build_jobs_runtime_snapshot(include_archive_health=active_tab in {"overview", "archive"})
    last_sync_run = dict(runtime_snapshot.get("last_sync_run") or {})
    sync_counts = runtime_snapshot["sync_counts"]
    callback_counts = runtime_snapshot["callback_counts"]
    batch_counts = runtime_snapshot["batch_counts"]
    deferred_counts = runtime_snapshot["deferred_counts"]

    sync_runs = [_sync_row_view(item) for item in repo.list_sync_runs(status=archive_filters["status"], limit=archive_filters["limit"])]
    callback_logs = [
        _callback_row_view(item)
        for item in repo.list_callback_logs(
            process_status=callback_filters["process_status"],
            query=callback_filters["query"],
            limit=callback_filters["limit"],
        )
    ]
    batch_rows = [_batch_row_view(item) for item in repo.list_message_batches(status=batch_filters["status"], limit=batch_filters["limit"])]
    deferred_jobs = [
        _deferred_row_view(item)
        for item in repo.list_deferred_jobs(
            status=deferred_filters["status"],
            owner_userid=deferred_filters["owner_userid"],
            external_userid=deferred_filters["external_userid"],
            limit=deferred_filters["limit"],
        )
    ]

    selected_batch = {}
    selected_batch_messages: list[dict[str, Any]] = []
    selected_batch_id = _normalized_text(batch_filters["selected_batch_id"])
    if selected_batch_id.isdigit():
        batch_detail = get_message_batch(int(selected_batch_id), limit=50) or {}
        selected_batch = dict(batch_detail.get("batch") or repo.get_selected_message_batch(int(selected_batch_id)) or {})
        selected_batch_messages = list(batch_detail.get("messages") or [])
        if selected_batch:
            selected_batch = {
                **_batch_row_view(selected_batch),
                "paging": batch_detail.get("paging") or {},
            }

    summary_cards = [
        {
            "label": "Archive Sync",
            "value": (_normalized_text(last_sync_run.get("status")) or "never").upper(),
            "description": (
                f"run #{last_sync_run.get('id') or '-'} · {_normalized_text(last_sync_run.get('finished_at')) or _normalized_text(last_sync_run.get('created_at')) or 'Never'}"
            ),
            "tone": _status_tone(_normalized_text(last_sync_run.get("status")) or "unknown"),
        },
        {
            "label": "Callbacks",
            "value": "Enabled" if _callback_enabled() else "Disabled",
            "description": f"failed {int(callback_counts.get('failed_count') or 0)} · async {'on' if bool(current_app.config.get('CALLBACK_ASYNC_ENABLED', True)) else 'off'}",
            "tone": "ok" if _callback_enabled() else "danger",
        },
        {
            "label": "Message Batches",
            "value": int(batch_counts.get("pending_count") or 0),
            "description": f"pending · acked {int(batch_counts.get('acked_count') or 0)}",
            "tone": "warn" if int(batch_counts.get("pending_count") or 0) else "ok",
        },
        {
            "label": "Deferred Jobs",
            "value": int(deferred_counts.get("pending_count") or 0),
            "description": f"pending · failed {int(deferred_counts.get('failed_count') or 0)}",
            "tone": "danger" if int(deferred_counts.get("failed_count") or 0) else ("warn" if int(deferred_counts.get("pending_count") or 0) else "ok"),
        },
    ]

    return {
        "active_tab": active_tab,
        "tabs": jobs_tabs(active_tab),
        "summary_cards": summary_cards,
        "archive_runtime": {
            "last_sync_run": _sync_row_view(last_sync_run) if last_sync_run else {},
            "sync_counts": sync_counts,
            "health": runtime_snapshot.get("archive_health") or {},
            "health_error": _normalized_text(runtime_snapshot.get("archive_health_error")),
            "sync_form": _archive_sync_form_defaults(),
        },
        "callback_runtime": {
            "enabled": runtime_snapshot["callback_enabled"],
            "async_enabled": runtime_snapshot["background_async_enabled"],
            "counts": callback_counts,
        },
        "batches_runtime": {
            "counts": batch_counts,
        },
        "deferred_runtime": {
            "counts": deferred_counts,
            "mcp_auth_configured": _mcp_auth_configured(),
        },
        "archive_filters": archive_filters,
        "callback_filters": callback_filters,
        "batch_filters": batch_filters,
        "deferred_filters": deferred_filters,
        "archive_status_options": ["", "success", "failed"],
        "callback_status_options": ["", "pending", "processing", "success", "failed"],
        "batch_status_options": _batch_status_options(),
        "deferred_status_options": _deferred_status_options(),
        "sync_runs": sync_runs,
        "callback_logs": callback_logs,
        "batch_rows": batch_rows,
        "selected_batch": selected_batch,
        "selected_batch_messages": selected_batch_messages,
        "deferred_jobs": deferred_jobs,
    }


def build_jobs_summary_payload(args: Any) -> dict[str, Any]:
    payload = build_jobs_payload(args)
    return {
        "summary_cards": payload["summary_cards"],
        "archive_runtime": payload["archive_runtime"],
        "callback_runtime": payload["callback_runtime"],
        "batches_runtime": payload["batches_runtime"],
        "deferred_runtime": payload["deferred_runtime"],
    }


def build_jobs_archive_sync_payload(args: Any) -> dict[str, Any]:
    raw_args = dict(args or {})
    raw_args["tab"] = "archive"
    payload = build_jobs_payload(raw_args)
    return {
        "runtime": payload["archive_runtime"],
        "filters": payload["archive_filters"],
        "items": payload["sync_runs"],
        "status_options": payload["archive_status_options"],
    }


def build_jobs_callbacks_payload(args: Any) -> dict[str, Any]:
    raw_args = dict(args or {})
    raw_args["tab"] = "callbacks"
    payload = build_jobs_payload(raw_args)
    return {
        "runtime": payload["callback_runtime"],
        "filters": payload["callback_filters"],
        "items": payload["callback_logs"],
        "status_options": payload["callback_status_options"],
    }


def build_jobs_message_batches_payload(args: Any) -> dict[str, Any]:
    raw_args = dict(args or {})
    raw_args["tab"] = "batches"
    payload = build_jobs_payload(raw_args)
    return {
        "runtime": payload["batches_runtime"],
        "filters": payload["batch_filters"],
        "items": payload["batch_rows"],
        "status_options": payload["batch_status_options"],
    }


def build_jobs_message_batch_detail_payload(batch_id: int, args: Any) -> dict[str, Any]:
    raw_args = dict(args or {})
    raw_args["tab"] = "batches"
    raw_args["batch_id"] = str(int(batch_id))
    payload = build_jobs_payload(raw_args)
    return {
        "runtime": payload["batches_runtime"],
        "filters": payload["batch_filters"],
        "batch": payload["selected_batch"],
        "messages": payload["selected_batch_messages"],
    }


def build_jobs_deferred_jobs_payload(args: Any) -> dict[str, Any]:
    raw_args = dict(args or {})
    raw_args["tab"] = "deferred"
    payload = build_jobs_payload(raw_args)
    return {
        "runtime": payload["deferred_runtime"],
        "filters": payload["deferred_filters"],
        "items": payload["deferred_jobs"],
        "status_options": payload["deferred_status_options"],
    }


def execute_jobs_action(*, action: str, form: Any, operator: str) -> dict[str, Any]:
    normalized_action = _normalized_text(action)
    operator_value = _operator(operator)

    if normalized_action == "run-archive-sync":
        request_payload = _archive_sync_request_payload(form)
        if not request_payload["start_time"] or not request_payload["end_time"] or not request_payload["owner_userid"]:
            raise ValueError("start_time, end_time and owner_userid are required")
        if not _normalized_bool(form.get("confirm")):
            preview = {
                "ok": True,
                "preview_only": True,
                "confirm_required": True,
                "request": request_payload,
            }
            _audit_log(
                operator=operator_value,
                action_type="preview_archive_sync",
                target_id="archive_sync",
                before=request_payload,
                after=preview,
            )
            return preview
        payload = run_manual_archive_sync(**request_payload)
        _audit_log(
            operator=operator_value,
            action_type="run_archive_sync",
            target_id=str((payload.get("sync_run") or {}).get("id") or "archive_sync"),
            before=request_payload,
            after=payload,
        )
        return payload

    if normalized_action == "ack-message-batch":
        if not _normalized_bool(form.get("confirm")):
            raise ValueError("confirm is required before acking message batch")
        batch_id = _normalized_int(form.get("batch_id"), default=0, minimum=1, maximum=10**9)
        ack_note = _normalized_text(form.get("ack_note"))
        payload = ack_message_batch(batch_id, ack_note=ack_note, acked_by=operator_value)
        if not payload:
            raise ValueError("message batch not found")
        result = dict(payload)
        _audit_log(
            operator=operator_value,
            action_type="ack_message_batch",
            target_id=str(batch_id),
            before={"batch_id": batch_id, "ack_note": ack_note},
            after=result,
        )
        return {"ok": True, "batch": result}

    if normalized_action == "run-deferred-jobs":
        if not _normalized_bool(form.get("confirm")):
            raise ValueError("confirm is required before running deferred jobs")
        limit = _normalized_int(form.get("limit"), default=20)
        payload = run_due_user_ops_deferred_jobs(limit=limit)
        _audit_log(
            operator=operator_value,
            action_type="run_deferred_jobs",
            target_id=f"limit:{limit}",
            before={"limit": limit},
            after=payload,
        )
        return payload

    raise ValueError("unsupported jobs action")
