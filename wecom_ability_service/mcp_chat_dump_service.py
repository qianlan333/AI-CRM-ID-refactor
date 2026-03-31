from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable


def _list_owner_archived_messages(
    owner_userid: str,
    *,
    window_start: str,
    window_end: str,
    include_private: bool,
    include_group: bool,
    get_db: Callable[[], Any],
) -> list[dict[str, Any]]:
    if not include_private and not include_group:
        return []

    sql = """
        SELECT id, seq, msgid, chat_type, external_userid, owner_userid, sender, receiver, msgtype, content, send_time, raw_payload
        FROM archived_messages
        WHERE owner_userid = ? AND send_time >= ? AND send_time <= ?
    """
    params: list[Any] = [owner_userid, window_start, window_end]
    if include_private and not include_group:
        sql += " AND chat_type = ?"
        params.append("private")
    elif include_group and not include_private:
        sql += " AND chat_type = ?"
        params.append("group")
    sql += " ORDER BY send_time ASC, id ASC"
    return get_db().execute(sql, tuple(params)).fetchall()


def _sender_role_for_message(message: dict[str, Any], *, owner_userid: str) -> str:
    sender = str(message.get("from") or message.get("sender") or "").strip()
    external_userid = str(message.get("external_userid") or "").strip()
    if sender and sender == owner_userid:
        return "staff"
    if sender and external_userid and sender == external_userid:
        return "customer"
    return "unknown"


def build_owner_recent_chat_dump_payload(
    arguments: dict[str, Any],
    *,
    require_text: Callable[[Any], str],
    normalize_lookback_minutes: Callable[[Any], int],
    normalize_boolean: Callable[[Any], bool],
    get_db: Callable[[], Any],
    get_group_chat_map: Callable[[list[str]], dict[str, Any]],
    extract_roomid_from_raw_payload: Callable[[Any], str],
    format_message_row: Callable[..., dict[str, Any]],
    get_contact_by_external_userid: Callable[[str], dict[str, Any] | None],
) -> dict[str, Any]:
    owner_userid = require_text(arguments.get("owner_userid"), field_name="owner_userid")
    lookback_minutes = normalize_lookback_minutes(arguments.get("lookback_minutes"))
    include_private = normalize_boolean(arguments.get("include_private"), field_name="include_private", default=True)
    include_group = normalize_boolean(arguments.get("include_group"), field_name="include_group", default=True)

    window_end_dt = datetime.now()
    window_start_dt = window_end_dt - timedelta(minutes=lookback_minutes)
    window_start = window_start_dt.strftime("%Y-%m-%d %H:%M:%S")
    window_end = window_end_dt.strftime("%Y-%m-%d %H:%M:%S")

    rows = _list_owner_archived_messages(
        owner_userid,
        window_start=window_start,
        window_end=window_end,
        include_private=include_private,
        include_group=include_group,
        get_db=get_db,
    )
    group_map = get_group_chat_map([extract_roomid_from_raw_payload(row.get("raw_payload")) for row in rows])
    formatted_messages = [format_message_row(row, group_map=group_map) for row in rows]

    private_conversations_by_userid: dict[str, dict[str, Any]] = {}
    group_conversations_by_chat_id: dict[str, dict[str, Any]] = {}
    contact_cache: dict[str, dict[str, Any]] = {}

    for message in formatted_messages:
        chat_type = str(message.get("chat_type") or "").strip().lower()
        if chat_type == "private":
            external_userid = str(message.get("external_userid") or "").strip()
            if not external_userid:
                continue
            contact = contact_cache.get(external_userid)
            if contact is None:
                contact = get_contact_by_external_userid(external_userid) or {}
                contact_cache[external_userid] = contact
            conversation = private_conversations_by_userid.setdefault(
                external_userid,
                {
                    "external_userid": external_userid,
                    "customer_name": str(contact.get("customer_name") or "").strip(),
                    "messages": [],
                },
            )
            conversation["messages"].append(
                {
                    "send_time": str(message.get("send_time") or "").strip(),
                    "sender_role": _sender_role_for_message(message, owner_userid=owner_userid),
                    "msgtype": str(message.get("msgtype") or "").strip(),
                    "content": str(message.get("content") or "").strip(),
                    "owner_userid": owner_userid,
                    "sender": str(message.get("sender") or "").strip(),
                    "from": str(message.get("from") or "").strip(),
                    "tolist": message.get("tolist") or [],
                }
            )
            continue

        if chat_type != "group":
            continue

        chat_id = str(message.get("roomid") or message.get("chat_id") or "").strip()
        conversation = group_conversations_by_chat_id.setdefault(
            chat_id,
            {
                "roomid": chat_id,
                "chat_id": chat_id,
                "group_name": str(message.get("group_name") or "").strip(),
                "messages": [],
            },
        )
        conversation["messages"].append(
            {
                "send_time": str(message.get("send_time") or "").strip(),
                "sender_role": _sender_role_for_message(message, owner_userid=owner_userid),
                "external_userid": str(message.get("external_userid") or "").strip(),
                "msgtype": str(message.get("msgtype") or "").strip(),
                "content": str(message.get("content") or "").strip(),
                "owner_userid": owner_userid,
                "sender": str(message.get("sender") or "").strip(),
                "from": str(message.get("from") or "").strip(),
                "tolist": message.get("tolist") or [],
            }
        )

    return {
        "ok": True,
        "owner_userid": owner_userid,
        "lookback_minutes": lookback_minutes,
        "window_start": window_start,
        "window_end": window_end,
        "include_private": include_private,
        "include_group": include_group,
        "private_conversations": list(private_conversations_by_userid.values()),
        "group_conversations": list(group_conversations_by_chat_id.values()),
    }
