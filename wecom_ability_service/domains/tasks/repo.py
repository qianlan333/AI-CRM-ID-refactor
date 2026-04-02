from __future__ import annotations

import json
from typing import Any

from ...db import get_db


def save_outbound_task(task_type: str, request_payload: dict[str, Any], response_payload: dict[str, Any]) -> int:
    task_id = (
        response_payload.get("msgid")
        or response_payload.get("jobid")
        or response_payload.get("task_id")
        or response_payload.get("moment_id")
    )
    db = get_db()
    row = db.execute(
        """
        INSERT INTO outbound_tasks (task_type, request_payload, response_payload, wecom_task_id, status)
        VALUES (?, ?, ?, ?, 'created')
        RETURNING id
        """,
        (
            task_type,
            json.dumps(request_payload, ensure_ascii=False),
            json.dumps(response_payload, ensure_ascii=False),
            task_id,
        ),
    )
    result = row.fetchone()
    db.commit()
    return int(result["id"])


def record_conversion_feedback(
    *,
    feedback_type: str,
    external_userid: str = "",
    chat_id: str = "",
    actor: str = "",
    feedback_payload: dict[str, Any] | None = None,
) -> int:
    db = get_db()
    row = db.execute(
        """
        INSERT INTO conversion_feedback (external_userid, chat_id, feedback_type, feedback_payload, actor)
        VALUES (?, ?, ?, ?, ?)
        RETURNING id
        """,
        (
            external_userid or "",
            chat_id or "",
            feedback_type,
            json.dumps(feedback_payload or {}, ensure_ascii=False),
            actor or "",
        ),
    ).fetchone()
    db.commit()
    return int(row["id"])
