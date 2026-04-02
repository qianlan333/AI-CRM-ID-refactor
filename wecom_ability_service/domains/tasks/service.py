from __future__ import annotations

from typing import Any

from ...wecom_client import WeComClient
from . import repo


def save_outbound_task(task_type: str, request_payload: dict[str, Any], response_payload: dict[str, Any]) -> int:
    return repo.save_outbound_task(task_type, request_payload, response_payload)


def dispatch_wecom_task(task_type: str, fn_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    client = WeComClient.from_app()
    result = getattr(client, fn_name)(payload)
    local_id = repo.save_outbound_task(task_type, payload, result)
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
) -> int:
    return repo.record_conversion_feedback(
        feedback_type=feedback_type,
        external_userid=external_userid,
        chat_id=chat_id,
        actor=actor,
        feedback_payload=feedback_payload,
    )
