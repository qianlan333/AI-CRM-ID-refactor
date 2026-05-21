from __future__ import annotations

from typing import Any

from ...wecom_client import WeComClient
from .private_message import build_private_message_request_payload
from . import repo

_MARK_ENROLLED_FEEDBACK_TYPES = {
    "mark_enrolled",
    "enrolled",
    "signup_success",
    "converted_enrolled",
}
_UNMARK_ENROLLED_FEEDBACK_TYPES = {
    "unmark_enrolled",
    "unenrolled",
    "undo_enrolled",
    "reopen_conversion",
}


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _conversion_feedback_action(feedback_type: str) -> str:
    normalized = _normalized_text(feedback_type).lower()
    if normalized in _MARK_ENROLLED_FEEDBACK_TYPES:
        return "mark_enrolled"
    if normalized in _UNMARK_ENROLLED_FEEDBACK_TYPES:
        return "unmark_enrolled"
    return ""


def _sync_conversion_truth_from_feedback(
    *,
    feedback_type: str,
    external_userid: str,
    actor: str,
    feedback_payload: dict[str, Any],
) -> dict[str, Any]:
    action = _conversion_feedback_action(feedback_type)
    if not action:
        return {}
    normalized_external_userid = _normalized_text(external_userid)
    if not normalized_external_userid:
        raise ValueError("external_userid is required for enrolled feedback")

    from ..marketing_automation.service import mark_enrolled, unmark_enrolled

    owner_userid = _normalized_text(feedback_payload.get("owner_userid")) or _normalized_text(feedback_payload.get("userid"))
    operator = _normalized_text(feedback_payload.get("operator")) or _normalized_text(actor) or "mcp_feedback"
    source = _normalized_text(feedback_payload.get("source")) or "mcp_feedback"
    if action == "mark_enrolled":
        return {
            "action": action,
            "result": mark_enrolled(
                external_userid=normalized_external_userid,
                owner_userid=owner_userid,
                operator=operator,
                source=source,
                signup_status=_normalized_text(feedback_payload.get("signup_status")),
            ),
        }
    return {
        "action": action,
        "result": unmark_enrolled(
            external_userid=normalized_external_userid,
            owner_userid=owner_userid,
            operator=operator,
            source=source,
            restore_signup_status=_normalized_text(feedback_payload.get("restore_signup_status")),
        ),
    }


def save_outbound_task(task_type: str, request_payload: dict[str, Any], response_payload: dict[str, Any]) -> int:
    return repo.save_outbound_task(task_type, request_payload, response_payload)


def save_local_private_message_draft(
    payload: dict[str, Any],
    *,
    source: str = "",
) -> dict[str, Any]:
    normalized_payload, image_count = build_private_message_request_payload(dict(payload or {}))
    response_payload = {
        "draft_only": True,
        "status": "draft",
        "image_count": image_count,
        "source": _normalized_text(source) or "manual",
    }
    task_id = repo.save_outbound_task_record(
        "private_message",
        normalized_payload,
        response_payload,
        status="draft",
    )
    return {
        "task_id": int(task_id),
        "request_payload": normalized_payload,
        "response_payload": response_payload,
        "image_count": image_count,
        "status": "draft",
    }


def update_outbound_task_status(
    task_id: int,
    *,
    status: str,
    response_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return repo.update_outbound_task_status(task_id, status=status, response_payload=response_payload)


def get_outbound_task(task_id: int) -> dict[str, Any] | None:
    return repo.get_outbound_task(task_id)


def dispatch_wecom_task(task_type: str, fn_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    client = WeComClient.from_app()
    result = getattr(client, fn_name)(payload)
    local_id = repo.save_outbound_task(task_type, payload, result)
    return {
        "task_id": local_id,
        "wecom_result": result,
    }


def dispatch_wecom_task_with_intent(
    task_type: str,
    fn_name: str,
    payload: dict[str, Any],
    *,
    broadcast_job_id: int | None = None,
    trace_id: str = "",
) -> dict[str, Any]:
    """Create a local outbound intent before calling WeCom.

    This gives the queue worker a durable recovery boundary. If the worker dies
    before the external call, the job can be safely requeued. If it dies after
    creating an intent but before recording a WeCom result, recovery fails the
    job for manual reconciliation instead of blindly duplicating the send.
    """
    local_id = repo.create_outbound_task_intent(
        task_type,
        payload,
        trace_id=trace_id,
    )
    if broadcast_job_id:
        from ..broadcast_jobs import service as queue_service

        queue_service.mark_dispatch_started(
            int(broadcast_job_id),
            outbound_task_id=int(local_id),
        )
    client = WeComClient.from_app()
    try:
        result = getattr(client, fn_name)(payload)
    except Exception as exc:
        repo.update_outbound_task_status(
            int(local_id),
            status="failed",
            response_payload={
                "error": str(exc),
                "error_type": type(exc).__name__,
            },
        )
        raise
    repo.update_outbound_task_status(int(local_id), status="created", response_payload=result)
    return {
        "task_id": local_id,
        "wecom_result": result,
    }


def record_conversion_feedback(
    *,
    feedback_type: str,
    external_userid: str = "",
    chat_id: str = "",
    actor: str = "",
    feedback_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(feedback_payload or {})
    conversion_sync = _sync_conversion_truth_from_feedback(
        feedback_type=feedback_type,
        external_userid=external_userid,
        actor=actor,
        feedback_payload=payload,
    )
    if conversion_sync:
        payload = {
            **payload,
            "conversion_action": conversion_sync["action"],
            "conversion_source": _normalized_text(((conversion_sync["result"] or {}).get("source"))),
            "conversion_stage_key": _normalized_text((((conversion_sync["result"] or {}).get("marketing_state") or {}).get("stage_key"))),
        }
    feedback_id = repo.record_conversion_feedback(
        feedback_type=feedback_type,
        external_userid=external_userid,
        chat_id=chat_id,
        actor=actor,
        feedback_payload=payload,
    )
    return {
        "ok": True,
        "feedback_id": int(feedback_id),
        "feedback_type": _normalized_text(feedback_type),
        "conversion_result": conversion_sync.get("result") or {},
    }
