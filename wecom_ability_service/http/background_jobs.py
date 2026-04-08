from __future__ import annotations

import time
from datetime import datetime

from flask import current_app

from ..infra.wecom_runtime import get_app_runtime_client
from ..observability import (
    bind_background_context,
    generate_job_id,
    get_job_id,
    get_parent_request_id,
    get_request_id,
    get_task_name,
    unbind_background_context,
)
from ..services import (
    finish_external_contact_event_log,
    get_external_contact_event_log,
    get_group_chat_by_chat_id,
    mark_external_contact_event_processing,
    mark_external_contact_follow_user_status,
    mark_external_contact_identity_status,
    normalize_external_contact_identity,
    normalize_group_chat_record,
    refresh_external_contact_identity_owner,
    replace_external_contact_follow_users,
    run_due_user_ops_deferred_jobs,
    schedule_user_ops_auto_assign_class_term_job,
    upsert_contacts,
    upsert_external_contact_identity,
    upsert_group_chats,
)
from ..domains.automation_conversion.service import handle_qrcode_enter_from_callback
from .common import (
    _contact_sync_retry_limit,
    _default_owner_userid,
    background_executor,
    callback_logger,
)
from .sync_support import _sync_contact_detail_with_description_fix


def _run_app_task(
    app,
    task_name: str,
    task_fn,
    *args,
    job_id: str = "",
    parent_request_id: str = "",
    **kwargs,
) -> None:
    with app.app_context():
        context_tokens = bind_background_context(
            job_id=job_id,
            parent_request_id=parent_request_id,
            task_name=task_name,
        )
        try:
            callback_logger.info(
                "background task started job_id=%s task_name=%s parent_request_id=%s",
                job_id,
                task_name,
                parent_request_id,
            )
            task_fn(*args, **kwargs)
            callback_logger.info(
                "background task finished job_id=%s task_name=%s parent_request_id=%s",
                job_id,
                task_name,
                parent_request_id,
            )
        except Exception:
            callback_logger.exception(
                "background task failed job_id=%s task_name=%s parent_request_id=%s",
                job_id,
                task_name,
                parent_request_id,
            )
        finally:
            unbind_background_context(context_tokens)


def _dispatch_background_task(task_name: str, task_fn, *args, **kwargs) -> None:
    app = current_app._get_current_object()
    job_id = generate_job_id()
    parent_request_id = get_request_id()
    if current_app.config.get("CALLBACK_ASYNC_ENABLED", True):
        background_executor.submit(
            _run_app_task,
            app,
            task_name,
            task_fn,
            *args,
            job_id=job_id,
            parent_request_id=parent_request_id,
            **kwargs,
        )
    else:
        _run_app_task(
            app,
            task_name,
            task_fn,
            *args,
            job_id=job_id,
            parent_request_id=parent_request_id,
            **kwargs,
        )


def _run_user_ops_deferred_jobs_after_delay(wait_seconds: int = 10, limit: int = 20) -> None:
    delay = max(int(wait_seconds or 0), 0)
    if delay:
        time.sleep(delay)
    result = run_due_user_ops_deferred_jobs(limit=limit)
    callback_logger.info(
        "background task summary job_id=%s task_name=%s parent_request_id=%s "
        "stage=user_ops_auto_assign scanned=%s success=%s conflict=%s skipped=%s failed=%s",
        get_job_id(),
        get_task_name(),
        get_parent_request_id(),
        result.get("scanned_count", 0),
        result.get("success_count", 0),
        result.get("conflict_count", 0),
        result.get("skipped_count", 0),
        result.get("failed_count", 0),
    )


def _handle_group_chat_change(event_data: dict[str, str]) -> dict:
    chat_id = event_data.get("ChatId") or event_data.get("chat_id") or event_data.get("ChatID") or ""
    change_type = (event_data.get("ChangeType") or event_data.get("change_type") or "").lower()
    if not chat_id:
        return {"handled": False, "reason": "missing chat_id"}
    if "dismiss" in change_type:
        existing = get_group_chat_by_chat_id(chat_id) or {"chat_id": chat_id}
        upsert_group_chats(
            [
                {
                    "chat_id": chat_id,
                    "group_name": existing.get("group_name", ""),
                    "owner_userid": existing.get("owner_userid", ""),
                    "notice": existing.get("notice", ""),
                    "member_count": existing.get("member_count", 0),
                    "status": "dismissed",
                    "create_time": existing.get("create_time", ""),
                    "dismissed_at": existing.get("dismissed_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "raw_payload": existing.get("raw_payload", "{}"),
                }
            ]
        )
        return {"handled": True, "chat_id": chat_id, "change_type": change_type}

    wecom_client = get_app_runtime_client()
    detail = wecom_client.get_group_chat(chat_id)
    upsert_group_chats([normalize_group_chat_record(detail)])
    return {"handled": True, "chat_id": chat_id, "change_type": change_type}


def _process_external_contact_event(event_log_id: int) -> dict:
    event_log = get_external_contact_event_log(event_log_id)
    if not event_log:
        return {"ok": False, "error": "event_log_not_found"}
    if event_log.get("process_status") == "success":
        return {"ok": True, "status": "success", "event_log_id": event_log_id, "duplicate": True}

    mark_external_contact_event_processing(event_log_id)
    event_log = get_external_contact_event_log(event_log_id) or event_log
    retry_limit = _contact_sync_retry_limit()
    corp_id = event_log.get("corp_id", "")
    external_userid = event_log.get("external_userid", "")
    user_id = event_log.get("user_id", "")
    change_type = (event_log.get("change_type") or "").lower()
    from .. import routes as routes_compat

    client = routes_compat._contact_client()
    scheduled_auto_assign_job: dict[str, object] | None = None

    try:
        if change_type in {"add_external_contact", "add_half_external_contact", "edit_external_contact"}:
            detail = client.get_contact(external_userid)
            normalized_contact, _ = _sync_contact_detail_with_description_fix(
                client,
                detail,
                owner_userid=user_id,
                default_owner_userid=_default_owner_userid(),
                tolerate_update_error=True,
                log_stage="external_contact.callback",
            )
            upsert_contacts([normalized_contact])
            identity = normalize_external_contact_identity(
                corp_id,
                detail,
                follow_user_userid=user_id,
                status="active",
            )
            upsert_external_contact_identity(identity)
            replace_external_contact_follow_users(
                corp_id,
                external_userid,
                detail.get("follow_user") or [],
                preferred_userid=user_id,
            )
            refresh_external_contact_identity_owner(corp_id, external_userid)
            try:
                handle_qrcode_enter_from_callback(
                    external_contact_id=external_userid,
                    phone=str(normalized_contact.get("mobile") or "").strip(),
                    payload_json=event_log.get("payload_json") or {},
                    operator_id=user_id or "wecom_callback",
                    send_welcome_message=change_type in {"add_external_contact", "add_half_external_contact"},
                )
            except Exception:
                callback_logger.exception(
                    "automation conversion qrcode enter handling failed external_userid=%s",
                    external_userid,
                )
            if change_type in {"add_external_contact", "add_half_external_contact"}:
                scheduled_auto_assign_job = schedule_user_ops_auto_assign_class_term_job(
                    external_userid=external_userid,
                    owner_userid=str(normalized_contact.get("owner_userid") or user_id or "").strip(),
                    delay_seconds=10,
                    operator="system_auto_assign",
                )
        elif change_type in {"del_external_contact", "del_follow_user"}:
            mark_external_contact_identity_status(
                corp_id,
                external_userid,
                status="inactive",
                follow_user_userid=user_id,
            )
            mark_external_contact_follow_user_status(
                corp_id,
                external_userid,
                user_id=user_id if change_type == "del_follow_user" else "",
                status="inactive",
            )
            refresh_external_contact_identity_owner(corp_id, external_userid)
        else:
            finish_external_contact_event_log(event_log_id, status="ignored")
            callback_logger.info(
                "stage=external_contact_callback errcode=0 errmsg=ignored_change_type change_type=%s owner_userid=%s external_userid=%s chat_id=",
                change_type,
                user_id,
                external_userid,
            )
            return {"ok": True, "status": "ignored", "event_log_id": event_log_id}

        finish_external_contact_event_log(event_log_id, status="success")
        if scheduled_auto_assign_job and scheduled_auto_assign_job.get("scheduled"):
            routes_compat._dispatch_background_task(
                "user_ops_auto_assign_class_term",
                _run_user_ops_deferred_jobs_after_delay,
                11,
                20,
            )
        callback_logger.info(
            "stage=external_contact_callback errcode=0 errmsg=success owner_userid=%s external_userid=%s chat_id=",
            user_id,
            external_userid,
        )
        return {"ok": True, "status": "success", "event_log_id": event_log_id}
    except Exception as exc:
        latest = get_external_contact_event_log(event_log_id) or event_log
        next_retry = int(latest.get("retry_count") or 0) + 1
        final_status = "failed" if next_retry >= retry_limit else "pending"
        finish_external_contact_event_log(
            event_log_id,
            status=final_status,
            error_message=str(exc),
            increment_retry=True,
        )
        callback_logger.error(
            "stage=external_contact_callback errcode=1 errmsg=%s owner_userid=%s external_userid=%s chat_id=",
            str(exc),
            user_id,
            external_userid,
        )
        if final_status == "pending":
            return _process_external_contact_event(event_log_id)
        return {"ok": False, "status": final_status, "event_log_id": event_log_id, "error": str(exc)}
