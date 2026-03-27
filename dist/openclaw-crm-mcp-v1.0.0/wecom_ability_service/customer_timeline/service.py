from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from ..services import extract_roomid_from_raw_payload, format_message_row, get_group_chat_map
from .dto import TimelineDTO, TimelineItemDTO
from .repo import (
    fetch_archived_messages,
    fetch_questionnaire_submissions,
    fetch_status_changes,
    fetch_wecom_events,
    has_customer_timeline_scope,
)


def _stringify(value: Any) -> str:
    return str(value or "").strip()


def _json_loads(value: Any, *, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not value:
        return default
    try:
        decoded = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default
    return decoded


def _format_unix_timestamp(value: Any) -> str:
    try:
        if value in (None, ""):
            return ""
        return datetime.fromtimestamp(int(value)).strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError, OSError):
        return ""


def _message_items(external_userid: str) -> list[TimelineItemDTO]:
    rows = fetch_archived_messages(external_userid)
    group_map = get_group_chat_map([extract_roomid_from_raw_payload(row.get("raw_payload")) for row in rows])
    items: list[TimelineItemDTO] = []
    for row in rows:
        message = format_message_row(row, group_map=group_map)
        event_time = _stringify(row.get("send_time")) or _stringify(row.get("created_at"))
        items.append(
            TimelineItemDTO(
                event_id=f"message:{row['id']}",
                event_type="message",
                event_time=event_time,
                occurred_at=event_time,
                title=f"消息 · {_stringify(message.get('msgtype')) or 'unknown'}",
                summary=_stringify(message.get("content")),
                source_table="archived_messages",
                source_id=str(row["id"]),
                operator_userid=_stringify(message.get("from") or row.get("sender") or row.get("owner_userid")),
                external_userid=external_userid,
                metadata=message,
            )
        )
    return items


def _status_change_items(external_userid: str) -> list[TimelineItemDTO]:
    rows = fetch_status_changes(external_userid)
    items: list[TimelineItemDTO] = []
    for row in rows:
        event_time = _stringify(row.get("set_at")) or _stringify(row.get("created_at"))
        items.append(
            TimelineItemDTO(
                event_id=f"status_change:{row['id']}",
                event_type="status_change",
                event_time=event_time,
                occurred_at=event_time,
                title="状态变更",
                summary=f"{_stringify(row.get('old_signup_status')) or '-'} -> {_stringify(row.get('new_signup_status')) or '-'}",
                source_table="class_user_status_history",
                source_id=str(row["id"]),
                operator_userid=_stringify(row.get("set_by_userid") or row.get("owner_userid_snapshot")),
                external_userid=external_userid,
                metadata=dict(row),
            )
        )
    return items


def _questionnaire_items(external_userid: str) -> list[TimelineItemDTO]:
    rows = fetch_questionnaire_submissions(external_userid)
    items: list[TimelineItemDTO] = []
    for row in rows:
        title_suffix = _stringify(row.get("questionnaire_title")) or _stringify(row.get("questionnaire_name"))
        event_time = _stringify(row.get("submitted_at"))
        final_tags = _json_loads(row.get("final_tags"), default=[])
        metadata = dict(row)
        metadata["final_tags"] = final_tags if isinstance(final_tags, list) else []
        items.append(
            TimelineItemDTO(
                event_id=f"questionnaire_submit:{row['id']}",
                event_type="questionnaire_submit",
                event_time=event_time,
                occurred_at=event_time,
                title="问卷提交" + (f" · {title_suffix}" if title_suffix else ""),
                summary=f"score={row.get('total_score') or 0}",
                source_table="questionnaire_submissions",
                source_id=str(row["id"]),
                operator_userid=_stringify(row.get("follow_user_userid") or row.get("staff_id")),
                external_userid=external_userid,
                metadata=metadata,
            )
        )
    return items


def _wecom_event_items(external_userid: str) -> list[TimelineItemDTO]:
    rows = fetch_wecom_events(external_userid)
    items: list[TimelineItemDTO] = []
    for row in rows:
        event_time = _format_unix_timestamp(row.get("event_time")) or _stringify(row.get("created_at")) or _stringify(
            row.get("updated_at")
        )
        metadata = dict(row)
        metadata["payload_json"] = _json_loads(row.get("payload_json"), default={})
        items.append(
            TimelineItemDTO(
                event_id=f"wecom_event:{row['id']}",
                event_type="wecom_event",
                event_time=event_time,
                occurred_at=event_time,
                title="企微事件",
                summary=f"{_stringify(row.get('event_type'))} · {_stringify(row.get('change_type'))}",
                source_table="wecom_external_contact_event_logs",
                source_id=str(row["id"]),
                operator_userid=_stringify(row.get("user_id")),
                external_userid=external_userid,
                metadata=metadata,
            )
        )
    return items


def get_customer_timeline(external_userid: str, filters: dict[str, Any]) -> dict[str, Any] | None:
    normalized_external_userid = _stringify(external_userid)
    if not normalized_external_userid:
        return None
    if not has_customer_timeline_scope(normalized_external_userid):
        return None

    items = (
        _message_items(normalized_external_userid)
        + _status_change_items(normalized_external_userid)
        + _questionnaire_items(normalized_external_userid)
        + _wecom_event_items(normalized_external_userid)
    )

    event_type = _stringify(filters.get("event_type"))
    if event_type:
        items = [item for item in items if item.event_type == event_type]

    items.sort(key=lambda item: (item.event_time, item.source_table, item.source_id), reverse=True)

    limit = int(filters["normalized_limit"])
    offset = int(filters["normalized_offset"])
    page_items = items[offset : offset + limit]

    payload = TimelineDTO(
        external_userid=normalized_external_userid,
        items=page_items,
        count=len(page_items),
        limit=limit,
        offset=offset,
        filters={
            "event_type": _stringify(filters.get("event_type")),
            "limit": _stringify(filters.get("limit")),
            "offset": _stringify(filters.get("offset")),
        },
        total=len(items),
    )
    return payload.to_dict()
