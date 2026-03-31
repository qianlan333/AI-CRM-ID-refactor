from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from .db import get_db, get_db_backend
from .services import _normalize_optional_timestamp


def normalize_group_chat_record(payload: dict[str, Any], owner_userid: str | None = None, status: str = "active") -> dict[str, Any]:
    group_chat = payload.get("group_chat") or payload
    member_list = group_chat.get("member_list") or []
    manager_list = group_chat.get("admin_list") or []
    derived_owner = owner_userid or group_chat.get("owner") or (manager_list[0] if manager_list else "")
    return {
        "chat_id": group_chat.get("chat_id", ""),
        "group_name": group_chat.get("name", ""),
        "owner_userid": derived_owner or "",
        "notice": group_chat.get("notice", "") or "",
        "member_count": len(member_list),
        "status": status,
        "create_time": _normalize_optional_timestamp(group_chat.get("create_time")) if group_chat.get("create_time") else "",
        "dismissed_at": _normalize_optional_timestamp(group_chat.get("dismiss_time")) if group_chat.get("dismiss_time") else "",
        "raw_payload": json.dumps(payload, ensure_ascii=False),
    }


def upsert_group_chats(group_chats: list[dict[str, Any]]) -> tuple[int, int]:
    db = get_db()
    inserted = 0
    updated = 0
    for item in group_chats:
        chat_id = item.get("chat_id", "")
        if not chat_id:
            continue
        existing = db.execute(
            """
            SELECT group_name, owner_userid, notice, member_count, status, create_time, dismissed_at, raw_payload
            FROM group_chats
            WHERE chat_id = ?
            """,
            (chat_id,),
        ).fetchone()
        db.execute(
            """
            INSERT INTO group_chats (
                chat_id, group_name, owner_userid, notice, member_count, status,
                create_time, dismissed_at, raw_payload, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(chat_id) DO UPDATE SET
                group_name = excluded.group_name,
                owner_userid = excluded.owner_userid,
                notice = excluded.notice,
                member_count = excluded.member_count,
                status = excluded.status,
                create_time = excluded.create_time,
                dismissed_at = excluded.dismissed_at,
                raw_payload = excluded.raw_payload,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                chat_id,
                item.get("group_name", ""),
                item.get("owner_userid", ""),
                item.get("notice", ""),
                int(item.get("member_count", 0)),
                item.get("status", "active"),
                item.get("create_time", ""),
                item.get("dismissed_at", ""),
                item.get("raw_payload", "{}"),
            ),
        )
        if existing is None:
            inserted += 1
        elif any(
            [
                existing.get("group_name") != item.get("group_name", ""),
                existing.get("owner_userid") != item.get("owner_userid", ""),
                existing.get("notice") != item.get("notice", ""),
                int(existing.get("member_count") or 0) != int(item.get("member_count", 0)),
                existing.get("status") != item.get("status", "active"),
                existing.get("create_time") != item.get("create_time", ""),
                existing.get("dismissed_at") != item.get("dismissed_at", ""),
                existing.get("raw_payload") != item.get("raw_payload", "{}"),
            ]
        ):
            updated += 1
    db.commit()
    return inserted, updated


def get_group_chat_by_chat_id(chat_id: str) -> dict[str, Any] | None:
    return get_db().execute(
        """
        SELECT chat_id, group_name, owner_userid, notice, member_count, status, create_time, dismissed_at, raw_payload, updated_at
        FROM group_chats
        WHERE chat_id = ?
        """,
        (chat_id,),
    ).fetchone()


def get_group_chat_map(chat_ids: list[str]) -> dict[str, dict[str, Any]]:
    unique_ids = [chat_id for chat_id in dict.fromkeys(chat_ids) if chat_id]
    if not unique_ids:
        return {}
    placeholders = ",".join("?" for _ in unique_ids)
    rows = get_db().execute(
        f"""
        SELECT chat_id, group_name, owner_userid, notice, member_count, status, create_time, dismissed_at, raw_payload, updated_at
        FROM group_chats
        WHERE chat_id IN ({placeholders})
        """,
        tuple(unique_ids),
    ).fetchall()
    return {row["chat_id"]: row for row in rows}


def list_group_chats(status: str | None = None) -> list[dict[str, Any]]:
    sql = """
        SELECT chat_id, group_name, owner_userid, notice, member_count, status, create_time, dismissed_at, raw_payload, updated_at
        FROM group_chats
    """
    params: list[Any] = []
    if status:
        sql += " WHERE status = ?"
        params.append(status)
    sql += " ORDER BY updated_at DESC, id DESC"
    return get_db().execute(sql, tuple(params)).fetchall()


def count_group_chats() -> int:
    row = get_db().execute("SELECT COUNT(*) AS total FROM group_chats").fetchone()
    return int(row["total"]) if row else 0


def count_archived_messages() -> int:
    row = get_db().execute("SELECT COUNT(*) AS total FROM archived_messages").fetchone()
    return int(row["total"]) if row else 0


def normalize_archived_message(item: dict[str, Any]) -> dict[str, Any]:
    if "raw_payload" in item and "sender" in item and "receiver" in item and "external_userid" in item:
        return {
            "seq": item.get("seq"),
            "msgid": item["msgid"],
            "chat_type": item.get("chat_type", "private"),
            "external_userid": item["external_userid"],
            "owner_userid": item["owner_userid"],
            "sender": item["sender"],
            "receiver": item["receiver"],
            "msgtype": item["msgtype"],
            "content": item["content"],
            "send_time": item["send_time"],
            "raw_payload": item["raw_payload"],
        }

    msgtype = item.get("msgtype", "text")
    content = (item.get("text") or {}).get("content") or item.get("content") or ""
    from_type = item.get("from_type", "")
    from_userid = item.get("from_userid", "")
    external_userid = item.get("external_userid") or (from_userid if from_type == "external" else "")
    owner_userid = item.get("owner_userid", "")
    sender = from_userid or owner_userid
    receiver = owner_userid if from_type == "external" else external_userid

    return {
        "seq": item.get("seq"),
        "msgid": item["msgid"],
        "chat_type": item.get("chat_type", "private"),
        "external_userid": external_userid,
        "owner_userid": owner_userid,
        "sender": sender,
        "receiver": receiver,
        "msgtype": msgtype,
        "content": content,
        "send_time": item["send_time"],
        "raw_payload": json.dumps(item, ensure_ascii=False),
    }


def format_message_row(row: dict[str, Any], group_map: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    raw_payload = row.get("raw_payload")
    decrypted_message = {}
    if raw_payload:
        try:
            payload = json.loads(raw_payload)
            decrypted_message = payload.get("decrypted_message") or {}
        except (TypeError, json.JSONDecodeError):
            decrypted_message = {}

    tolist = decrypted_message.get("tolist") or []
    if isinstance(tolist, str):
        tolist = [tolist]
    chat_id = decrypted_message.get("roomid", "") or ""
    group_info = (group_map or {}).get(chat_id) or {}

    return {
        "seq": row["seq"],
        "msgid": row["msgid"],
        "chat_type": row.get("chat_type") or ("group" if decrypted_message.get("roomid") else ("private" if len(tolist) == 1 else "group")),
        "external_userid": row["external_userid"],
        "owner_userid": row["owner_userid"],
        "sender": row["sender"],
        "from": decrypted_message.get("from") or row["sender"],
        "tolist": tolist,
        "roomid": chat_id,
        "chat_id": chat_id,
        "group_name": group_info.get("group_name", ""),
        "msgtype": row["msgtype"],
        "content": row["content"],
        "send_time": row["send_time"],
    }


def extract_roomid_from_raw_payload(raw_payload: str | None) -> str:
    if not raw_payload:
        return ""
    try:
        payload = json.loads(raw_payload)
    except (TypeError, json.JSONDecodeError):
        return ""
    return ((payload.get("decrypted_message") or {}).get("roomid")) or ""


def insert_archived_messages(messages: list[dict[str, Any]]) -> int:
    db = get_db()
    backend = get_db_backend()
    inserted = 0
    for item in messages:
        normalized = normalize_archived_message(item)
        sql = """
            INSERT INTO archived_messages (
                seq, msgid, chat_type, external_userid, owner_userid, sender, receiver,
                msgtype, content, send_time, raw_payload
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        if backend == "postgres":
            sql += " ON CONFLICT (msgid) DO NOTHING"
        else:
            sql = sql.replace("INSERT INTO", "INSERT OR IGNORE INTO", 1)
        cursor = db.execute(
            sql,
            (
                normalized["seq"],
                normalized["msgid"],
                normalized["chat_type"],
                normalized["external_userid"],
                normalized["owner_userid"],
                normalized["sender"],
                normalized["receiver"],
                normalized["msgtype"],
                normalized["content"],
                normalized["send_time"],
                normalized["raw_payload"],
            ),
        )
        inserted += cursor.rowcount
    db.commit()
    return inserted


def create_sync_run(start_time: str, end_time: str, owner_userid: str, cursor: str) -> int:
    db = get_db()
    cursor_row = db.execute(
        """
        INSERT INTO sync_runs (status, start_time, end_time, owner_userid, cursor)
        VALUES ('running', ?, ?, ?, ?)
        RETURNING id
        """,
        (start_time, end_time, owner_userid, cursor),
    )
    row = cursor_row.fetchone()
    db.commit()
    return int(row["id"])


def finish_sync_run(
    run_id: int,
    status: str,
    fetched_count: int,
    inserted_count: int,
    raw_response: dict[str, Any] | None = None,
    error_message: str | None = None,
) -> None:
    db = get_db()
    db.execute(
        """
        UPDATE sync_runs
        SET status = ?, fetched_count = ?, inserted_count = ?, raw_response = ?,
            error_message = ?, finished_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            status,
            fetched_count,
            inserted_count,
            json.dumps(raw_response, ensure_ascii=False) if raw_response is not None else None,
            error_message,
            run_id,
        ),
    )
    db.commit()


def _normalize_chat_type_filter(chat_type: str | None) -> str | None:
    if not chat_type:
        return None
    value = chat_type.strip().lower()
    if value not in {"private", "group"}:
        raise ValueError("chat_type must be private or group")
    return value


def get_messages_by_user(external_userid: str, chat_type: str | None = None) -> list[dict[str, Any]]:
    normalized_chat_type = _normalize_chat_type_filter(chat_type)
    sql = """
        SELECT seq, msgid, chat_type, external_userid, owner_userid, sender, receiver, msgtype, content, send_time, raw_payload
        FROM archived_messages
        WHERE external_userid = ?
    """
    params: list[Any] = [external_userid]
    if normalized_chat_type:
        sql += " AND chat_type = ?"
        params.append(normalized_chat_type)
    sql += " ORDER BY send_time ASC, id ASC"
    rows = get_db().execute(sql, tuple(params)).fetchall()
    group_map = get_group_chat_map([extract_roomid_from_raw_payload(row.get("raw_payload")) for row in rows])
    return [format_message_row(row, group_map=group_map) for row in rows]


def get_recent_messages_by_user(external_userid: str, limit: int = 20, chat_type: str | None = None) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 200))
    normalized_chat_type = _normalize_chat_type_filter(chat_type)
    sql = """
        SELECT seq, msgid, chat_type, external_userid, owner_userid, sender, receiver, msgtype, content, send_time, raw_payload
        FROM archived_messages
        WHERE external_userid = ?
    """
    params: list[Any] = [external_userid]
    if normalized_chat_type:
        sql += " AND chat_type = ?"
        params.append(normalized_chat_type)
    sql += " ORDER BY send_time DESC, id DESC LIMIT ?"
    params.append(safe_limit)
    rows = get_db().execute(sql, tuple(params)).fetchall()
    group_map = get_group_chat_map([extract_roomid_from_raw_payload(row.get("raw_payload")) for row in rows])
    return [format_message_row(row, group_map=group_map) for row in rows]


def search_messages(external_userid: str, keyword: str) -> list[dict[str, Any]]:
    rows = get_db().execute(
        """
        SELECT seq, msgid, chat_type, external_userid, owner_userid, sender, receiver, msgtype, content, send_time, raw_payload
        FROM archived_messages
        WHERE external_userid = ? AND content LIKE ?
        ORDER BY send_time ASC, id ASC
        """,
        (external_userid, f"%{keyword}%"),
    ).fetchall()
    group_map = get_group_chat_map([extract_roomid_from_raw_payload(row.get("raw_payload")) for row in rows])
    return [format_message_row(row, group_map=group_map) for row in rows]


def list_archived_messages_by_window(
    start_time: str,
    end_time: str,
    owner_userid: str,
    cursor: str = "",
    limit: int = 100,
) -> dict[str, Any]:
    db = get_db()
    offset = int(cursor or "0")
    rows = db.execute(
        """
        SELECT seq, msgid, external_userid, owner_userid, sender, receiver, msgtype, content, send_time, raw_payload
        FROM archived_messages
        WHERE send_time >= ? AND send_time <= ? AND owner_userid = ?
        ORDER BY send_time ASC, id ASC
        LIMIT ? OFFSET ?
        """,
        (start_time, end_time, owner_userid, limit + 1, offset),
    ).fetchall()

    has_more = len(rows) > limit
    page_rows = rows[:limit]
    next_cursor = str(offset + limit) if has_more else ""
    messages = [json.loads(row["raw_payload"]) for row in page_rows]
    return {"messages": messages, "has_more": has_more, "next_cursor": next_cursor}


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


def save_tag_snapshot(userid: str, external_userid: str, add_tag_ids: list[str], tag_name_map: dict[str, str] | None = None) -> None:
    db = get_db()
    for tag_id in add_tag_ids:
        sql = """
            INSERT INTO contact_tags (external_userid, userid, tag_id, tag_name)
            VALUES (?, ?, ?, ?)
        """
        sql += """
            ON CONFLICT (external_userid, userid, tag_id) DO UPDATE SET
                tag_name = excluded.tag_name
        """
        db.execute(
            sql,
            (external_userid, userid, tag_id, (tag_name_map or {}).get(tag_id)),
        )
    db.commit()


def remove_tag_snapshot(userid: str, external_userid: str, remove_tag_ids: list[str]) -> None:
    db = get_db()
    for tag_id in remove_tag_ids:
        db.execute(
            "DELETE FROM contact_tags WHERE external_userid = ? AND userid = ? AND tag_id = ?",
            (external_userid, userid, tag_id),
        )
    db.commit()


def remove_tag_snapshots_for_other_users(external_userid: str, keep_userids: list[str], scoped_tag_ids: list[str]) -> None:
    normalized_external_userid = str(external_userid or "").strip()
    normalized_keep_userids = [str(item or "").strip() for item in keep_userids if str(item or "").strip()]
    normalized_tag_ids = [str(item or "").strip() for item in scoped_tag_ids if str(item or "").strip()]
    if not normalized_external_userid or not normalized_tag_ids:
        return
    params: list[Any] = [normalized_external_userid, *normalized_tag_ids]
    sql = (
        "DELETE FROM contact_tags WHERE external_userid = ? AND tag_id IN ("
        + ",".join(["?"] * len(normalized_tag_ids))
        + ")"
    )
    if normalized_keep_userids:
        sql += " AND userid NOT IN (" + ",".join(["?"] * len(normalized_keep_userids)) + ")"
        params.extend(normalized_keep_userids)
    db = get_db()
    db.execute(sql, tuple(params))
    db.commit()


def _list_contact_tag_ids_for_user(external_userid: str, userid: str) -> list[str]:
    rows = get_db().execute(
        """
        SELECT tag_id
        FROM contact_tags
        WHERE external_userid = ? AND userid = ?
        ORDER BY tag_id ASC
        """,
        (str(external_userid or "").strip(), str(userid or "").strip()),
    ).fetchall()
    return [str(row.get("tag_id") or "").strip() for row in rows if str(row.get("tag_id") or "").strip()]


def remove_all_tag_snapshots_for_other_users(external_userid: str, keep_userids: list[str]) -> None:
    normalized_external_userid = str(external_userid or "").strip()
    normalized_keep_userids = [str(item or "").strip() for item in keep_userids if str(item or "").strip()]
    if not normalized_external_userid:
        return
    params: list[Any] = [normalized_external_userid]
    sql = "DELETE FROM contact_tags WHERE external_userid = ?"
    if normalized_keep_userids:
        sql += " AND userid NOT IN (" + ",".join(["?"] * len(normalized_keep_userids)) + ")"
        params.extend(normalized_keep_userids)
    db = get_db()
    db.execute(sql, tuple(params))
    db.commit()


def get_archive_last_seq() -> int:
    row = get_db().execute(
        "SELECT last_seq FROM archive_sync_state WHERE state_key = 'global'"
    ).fetchone()
    return int(row["last_seq"]) if row else 0


def set_archive_last_seq(last_seq: int) -> None:
    db = get_db()
    db.execute(
        """
        INSERT INTO archive_sync_state (state_key, last_seq, updated_at)
        VALUES ('global', ?, CURRENT_TIMESTAMP)
        ON CONFLICT(state_key) DO UPDATE SET
            last_seq = excluded.last_seq,
            updated_at = CURRENT_TIMESTAMP
        """,
        (int(last_seq),),
    )
    db.commit()


def get_last_sync_run() -> dict[str, Any] | None:
    return get_db().execute(
        """
        SELECT id, status, owner_userid, fetched_count, inserted_count, error_message, created_at, finished_at
        FROM sync_runs
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()


def _parse_send_time(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


def _batch_window_for_send_time(send_time: str, window_minutes: int = 3) -> tuple[str, str, str]:
    dt = _parse_send_time(send_time)
    floored_minute = (dt.minute // window_minutes) * window_minutes
    window_start_dt = dt.replace(minute=floored_minute, second=0, microsecond=0)
    window_end_dt = window_start_dt + timedelta(minutes=window_minutes) - timedelta(seconds=1)
    window_start = window_start_dt.strftime("%Y-%m-%d %H:%M:%S")
    window_end = window_end_dt.strftime("%Y-%m-%d %H:%M:%S")
    batch_key = f"{window_start}->{window_end}"
    return window_start, window_end, batch_key


def materialize_message_batches(window_minutes: int = 3) -> dict[str, int]:
    db = get_db()
    rows = db.execute(
        """
        SELECT am.id, am.msgid, am.chat_type, am.external_userid, am.owner_userid, am.send_time, am.raw_payload
        FROM archived_messages am
        LEFT JOIN message_batch_items mbi ON mbi.message_id = am.id
        WHERE mbi.message_id IS NULL
        ORDER BY am.send_time ASC, am.id ASC
        """
    ).fetchall()
    if not rows:
        return {"created_batches": 0, "added_items": 0}

    created_batches = 0
    added_items = 0
    batch_cache: dict[str, int] = {}

    for row in rows:
        window_start, window_end, batch_key = _batch_window_for_send_time(row["send_time"], window_minutes=window_minutes)
        batch_id = batch_cache.get(batch_key)
        if batch_id is None:
            existing = db.execute(
                """
                SELECT id FROM message_batches WHERE batch_key = ?
                """,
                (batch_key,),
            ).fetchone()
            if existing:
                batch_id = int(existing["id"])
            else:
                inserted = db.execute(
                    """
                    INSERT INTO message_batches (batch_key, window_start, window_end, status, message_count)
                    VALUES (?, ?, ?, 'pending', 0)
                    RETURNING id
                    """,
                    (batch_key, window_start, window_end),
                ).fetchone()
                batch_id = int(inserted["id"])
                created_batches += 1
            batch_cache[batch_key] = batch_id

        payload = {}
        if row.get("raw_payload"):
            try:
                payload = json.loads(row["raw_payload"])
            except (TypeError, json.JSONDecodeError):
                payload = {}
        chat_id = ((payload.get("decrypted_message") or {}).get("roomid")) or ""
        cursor = db.execute(
            """
            INSERT INTO message_batch_items (
                batch_id, message_id, msgid, chat_type, chat_id, external_userid, owner_userid, send_time
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (message_id) DO NOTHING
            """,
            (
                batch_id,
                row["id"],
                row["msgid"],
                row.get("chat_type", "private"),
                chat_id,
                row.get("external_userid", ""),
                row.get("owner_userid", ""),
                row["send_time"],
            ),
        )
        if cursor.rowcount:
            added_items += 1
            db.execute(
                """
                UPDATE message_batches
                SET message_count = message_count + 1
                WHERE id = ?
                """,
                (batch_id,),
            )

    db.commit()
    return {"created_batches": created_batches, "added_items": added_items}


def list_message_batches(status: str = "pending", limit: int = 20, cursor: str = "") -> dict[str, Any]:
    safe_limit = max(1, min(int(limit), 200))
    cursor_id = int(cursor or 0)
    rows = get_db().execute(
        """
        SELECT id, batch_key, window_start, window_end, status, message_count, created_at, acked_at, ack_note, acked_by
        FROM message_batches
        WHERE status = ? AND id > ?
        ORDER BY id ASC
        LIMIT ?
        """,
        (status, cursor_id, safe_limit + 1),
    ).fetchall()
    items = list(rows[:safe_limit])
    next_cursor = str(items[-1]["id"]) if len(rows) > safe_limit and items else ""
    return {"items": items, "next_cursor": next_cursor}


def get_message_batch(batch_id: int, *, limit: int = 200, cursor: str = "") -> dict[str, Any] | None:
    db = get_db()
    batch = db.execute(
        """
        SELECT id, batch_key, window_start, window_end, status, message_count, created_at, acked_at, ack_note, acked_by
        FROM message_batches
        WHERE id = ?
        """,
        (int(batch_id),),
    ).fetchone()
    if not batch:
        return None
    safe_limit = max(1, min(int(limit), 500))
    cursor_id = int(cursor or 0)
    rows = db.execute(
        """
        SELECT am.seq, am.msgid, am.chat_type, am.external_userid, am.owner_userid, am.sender, am.receiver,
               am.msgtype, am.content, am.send_time, am.raw_payload, mbi.id AS batch_item_id
        FROM message_batch_items mbi
        JOIN archived_messages am ON am.id = mbi.message_id
        WHERE mbi.batch_id = ? AND mbi.id > ?
        ORDER BY mbi.id ASC
        LIMIT ?
        """,
        (int(batch_id), cursor_id, safe_limit + 1),
    ).fetchall()
    page_rows = list(rows[:safe_limit])
    next_cursor = str(page_rows[-1]["batch_item_id"]) if len(rows) > safe_limit and page_rows else ""
    group_map = get_group_chat_map([extract_roomid_from_raw_payload(row.get("raw_payload")) for row in page_rows])
    return {
        "batch": batch,
        "messages": [format_message_row(row, group_map=group_map) for row in page_rows],
        "paging": {
            "limit": safe_limit,
            "cursor": str(cursor or ""),
            "next_cursor": next_cursor,
        },
    }


def ack_message_batch(batch_id: int, ack_note: str = "", acked_by: str = "") -> dict[str, Any] | None:
    db = get_db()
    existing = db.execute(
        """
        SELECT id, batch_key, window_start, window_end, status, message_count, created_at, acked_at, ack_note, acked_by
        FROM message_batches
        WHERE id = ?
        """,
        (int(batch_id),),
    ).fetchone()
    if not existing:
        return None
    db.execute(
        """
        UPDATE message_batches
        SET status = 'acked',
            acked_at = COALESCE(acked_at, CURRENT_TIMESTAMP),
            ack_note = CASE WHEN ? <> '' THEN ? ELSE COALESCE(ack_note, '') END,
            acked_by = CASE WHEN ? <> '' THEN ? ELSE COALESCE(acked_by, '') END
        WHERE id = ?
        """,
        (ack_note, ack_note, acked_by, acked_by, int(batch_id)),
    )
    db.commit()
    return db.execute(
        """
        SELECT id, batch_key, window_start, window_end, status, message_count, created_at, acked_at, ack_note, acked_by
        FROM message_batches
        WHERE id = ?
        """,
        (int(batch_id),),
    ).fetchone()


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
