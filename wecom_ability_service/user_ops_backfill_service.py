
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from .archive_message_service import (
    _list_contact_tag_ids_for_user,
    remove_all_tag_snapshots_for_other_users,
    remove_tag_snapshot,
    save_tag_snapshot,
)
from .db import get_db
from .services import (
    USER_OPS_CLASS_TERM_TAG_GROUP_NAME,
    USER_OPS_CONFIRMED_CLASS_TERM_MAPPINGS,
    USER_OPS_DEFERRED_JOB_TYPE_AUTO_ASSIGN_CLASS_TERM,
    USER_OPS_TARGET_AUTO_ASSIGN_OWNER,
)
from .user_ops_pool_service import reload_user_ops_pool
from .user_ops_shared import (
    _current_user_ops_operator,
    _db_bool,
    _ensure_class_term_tag_mapping_seed,
    _normalize_user_ops_strategy_tag_groups,
    _stringify_db_timestamp,
    _user_ops_contact_client,
)

def sync_user_ops_class_term_tag_definitions() -> dict[str, Any]:
    _ensure_class_term_tag_mapping_seed()
    client = _user_ops_contact_client()
    payload = client.list_external_contact_tags()
    groups = _normalize_user_ops_strategy_tag_groups(payload)
    target_groups = [group for group in groups if group.get("group_name") == USER_OPS_CLASS_TERM_TAG_GROUP_NAME]
    rows = get_db().execute(
        """
        SELECT id, strategy_id, group_id, tag_id, tag_group_name, tag_name, class_term_no, class_term_label
        FROM class_term_tag_mapping
        WHERE tag_group_name = ?
        ORDER BY id ASC
        """,
        (USER_OPS_CLASS_TERM_TAG_GROUP_NAME,),
    ).fetchall()
    by_tag_id = {
        str(row.get("tag_id") or "").strip(): dict(row)
        for row in rows
        if str(row.get("tag_id") or "").strip()
    }
    by_tag_name = {
        str(row.get("tag_name") or "").strip(): dict(row)
        for row in rows
        if str(row.get("tag_name") or "").strip()
    }
    updated_count = 0
    skipped_count = 0
    synced_items: list[dict[str, Any]] = []
    db = get_db()
    for group in target_groups:
        group_id = str(group.get("group_id") or "").strip()
        strategy_id = str(group.get("strategy_id") or "").strip()
        for tag in group.get("tags") or []:
            tag_id = str(tag.get("tag_id") or "").strip()
            tag_name = str(tag.get("tag_name") or "").strip()
            existing = by_tag_id.get(tag_id) or by_tag_name.get(tag_name)
            if not existing:
                skipped_count += 1
                continue
            changed = any(
                [
                    str(existing.get("strategy_id") or "").strip() != strategy_id,
                    str(existing.get("group_id") or "").strip() != group_id,
                    str(existing.get("tag_id") or "").strip() != tag_id,
                    str(existing.get("tag_name") or "").strip() != tag_name,
                ]
            )
            db.execute(
                """
                UPDATE class_term_tag_mapping
                SET strategy_id = ?,
                    group_id = ?,
                    tag_id = ?,
                    tag_group_name = ?,
                    tag_name = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    strategy_id,
                    group_id,
                    tag_id,
                    USER_OPS_CLASS_TERM_TAG_GROUP_NAME,
                    tag_name,
                    int(existing["id"]),
                ),
            )
            if changed:
                updated_count += 1
            synced_items.append(
                {
                    "mapping_id": int(existing["id"]),
                    "strategy_id": strategy_id,
                    "group_id": group_id,
                    "tag_id": tag_id,
                    "tag_name": tag_name,
                    "class_term_no": int(existing["class_term_no"]),
                    "class_term_label": str(existing.get("class_term_label") or "").strip(),
                }
            )
    db.commit()
    return {
        "ok": True,
        "group_count": len(target_groups),
        "synced_count": len(synced_items),
        "updated_count": updated_count,
        "skipped_count": skipped_count,
        "items": synced_items,
    }

def _list_active_class_term_mappings() -> list[dict[str, Any]]:
    _ensure_class_term_tag_mapping_seed()
    rows = get_db().execute(
        """
        SELECT id, strategy_id, group_id, tag_id, tag_group_name, tag_name, class_term_no, class_term_label
        FROM class_term_tag_mapping
        WHERE is_active = ? AND tag_group_name = ?
        ORDER BY class_term_no ASC, id ASC
        """,
        (_db_bool(True), USER_OPS_CLASS_TERM_TAG_GROUP_NAME),
    ).fetchall()
    return [
        {
            "id": int(row["id"]),
            "strategy_id": str(row.get("strategy_id") or "").strip(),
            "group_id": str(row.get("group_id") or "").strip(),
            "tag_id": str(row.get("tag_id") or "").strip(),
            "tag_group_name": str(row.get("tag_group_name") or "").strip(),
            "tag_name": str(row.get("tag_name") or "").strip(),
            "class_term_no": int(row["class_term_no"]),
            "class_term_label": str(row.get("class_term_label") or "").strip(),
        }
        for row in rows
    ]

def _list_user_ops_pool_external_userids_for_owner(owner_userid: str) -> list[str]:
    rows = get_db().execute(
        """
        SELECT external_userid
        FROM user_ops_pool_current
        WHERE owner_userid = ?
          AND COALESCE(external_userid, '') <> ''
        ORDER BY external_userid ASC
        """,
        (str(owner_userid or "").strip(),),
    ).fetchall()
    return [str(row.get("external_userid") or "").strip() for row in rows if str(row.get("external_userid") or "").strip()]

def refresh_contact_tags_for_external_userid(
    *,
    external_userid: str,
    owner_userid: str = "",
    scoped_tag_ids: list[str] | None = None,
) -> dict[str, Any]:
    normalized_external_userid = str(external_userid or "").strip()
    normalized_owner_userid = str(owner_userid or "").strip()
    if not normalized_external_userid:
        return {"ok": True, "refreshed": False, "reason": "missing_external_userid"}
    normalized_scoped_tag_ids = sorted({str(item or "").strip() for item in (scoped_tag_ids or []) if str(item or "").strip()})
    scoped_all_tags = not normalized_scoped_tag_ids
    tag_name_map: dict[str, str] = {}
    if scoped_all_tags:
        rows = _user_ops_contact_client().get_contact(normalized_external_userid)
        detail = rows
    else:
        scoped_mappings = [item for item in _list_active_class_term_mappings() if str(item.get("tag_id") or "").strip()]
        known_tag_name_map = {
            str(item.get("tag_id") or "").strip(): str(item.get("tag_name") or "").strip()
            for item in scoped_mappings
            if str(item.get("tag_id") or "").strip()
        }
        for tag_id in normalized_scoped_tag_ids:
            if tag_id in known_tag_name_map:
                tag_name_map[tag_id] = known_tag_name_map[tag_id]
        detail = _user_ops_contact_client().get_contact(normalized_external_userid)
    follow_users = detail.get("follow_user") or []
    refreshed_userids: list[str] = []
    snapshot_count = 0
    for follow_user in follow_users:
        follow_user_userid = str((follow_user or {}).get("userid") or "").strip()
        if not follow_user_userid:
            continue
        if normalized_owner_userid and follow_user_userid != normalized_owner_userid:
            continue
        refreshed_userids.append(follow_user_userid)
        current_tag_ids: list[str] = []
        for tag in ((follow_user or {}).get("tags") or []):
            current_tag_id = str((tag or {}).get("tag_id") or (tag or {}).get("id") or "").strip()
            current_tag_name = str((tag or {}).get("tag_name") or (tag or {}).get("name") or "").strip()
            if not current_tag_id:
                continue
            if not scoped_all_tags and current_tag_id not in normalized_scoped_tag_ids:
                continue
            current_tag_ids.append(current_tag_id)
            if current_tag_name:
                tag_name_map[current_tag_id] = current_tag_name
        current_tag_ids = sorted(set(current_tag_ids))
        save_tag_snapshot(follow_user_userid, normalized_external_userid, current_tag_ids, tag_name_map)
        existing_tag_ids = _list_contact_tag_ids_for_user(normalized_external_userid, follow_user_userid)
        removable_tag_ids = [
            tag_id for tag_id in existing_tag_ids
            if (scoped_all_tags or tag_id in normalized_scoped_tag_ids) and tag_id not in current_tag_ids
        ]
        remove_tag_snapshot(
            follow_user_userid,
            normalized_external_userid,
            removable_tag_ids,
        )
        snapshot_count += len(current_tag_ids)

    if normalized_owner_userid and normalized_owner_userid not in refreshed_userids:
        missing_owner_existing = _list_contact_tag_ids_for_user(normalized_external_userid, normalized_owner_userid)
        removable_missing_owner = [
            tag_id for tag_id in missing_owner_existing
            if scoped_all_tags or tag_id in normalized_scoped_tag_ids
        ]
        remove_tag_snapshot(normalized_owner_userid, normalized_external_userid, removable_missing_owner)
    if scoped_all_tags:
        remove_all_tag_snapshots_for_other_users(normalized_external_userid, refreshed_userids)

    return {
        "ok": True,
        "refreshed": True,
        "external_userid": normalized_external_userid,
        "owner_userid": normalized_owner_userid,
        "follow_user_count": len(follow_users),
        "refreshed_userids": refreshed_userids,
        "scoped_tag_count": len(normalized_scoped_tag_ids),
        "scoped_all_tags": scoped_all_tags,
        "snapshot_count": snapshot_count,
    }

def refresh_user_ops_contact_tags_for_external_userid(
    *,
    external_userid: str,
    owner_userid: str = "",
) -> dict[str, Any]:
    scoped_tag_ids = sorted(
        {
            str(item.get("tag_id") or "").strip()
            for item in _list_active_class_term_mappings()
            if str(item.get("tag_id") or "").strip()
        }
    )
    if not scoped_tag_ids:
        return {"ok": True, "refreshed": False, "reason": "no_active_class_term_tag_ids"}
    return refresh_contact_tags_for_external_userid(
        external_userid=external_userid,
        owner_userid=owner_userid,
        scoped_tag_ids=scoped_tag_ids,
    )

def refresh_user_ops_contact_tags_for_owner(owner_userid: str) -> dict[str, Any]:
    normalized_owner_userid = str(owner_userid or "").strip()
    if not normalized_owner_userid:
        raise ValueError("owner_userid is required")
    external_userids = _list_user_ops_pool_external_userids_for_owner(normalized_owner_userid)
    items: list[dict[str, Any]] = []
    refreshed_count = 0
    for external_userid in external_userids:
        result = refresh_user_ops_contact_tags_for_external_userid(
            external_userid=external_userid,
            owner_userid=normalized_owner_userid,
        )
        items.append(result)
        if result.get("refreshed"):
            refreshed_count += 1
    return {
        "ok": True,
        "owner_userid": normalized_owner_userid,
        "external_user_count": len(external_userids),
        "refreshed_count": refreshed_count,
        "items": items,
    }

def _build_user_ops_backfill_preview(owner_userid: str) -> list[dict[str, Any]]:
    normalized_owner_userid = str(owner_userid or "").strip()
    if not normalized_owner_userid:
        raise ValueError("owner_userid is required")
    _ensure_class_term_tag_mapping_seed()
    rows = get_db().execute(
        """
        SELECT
            current.id AS pool_id,
            current.mobile,
            current.external_userid,
            current.customer_name,
            current.owner_userid,
            current.class_term_no AS current_class_term_no,
            current.class_term_label AS current_class_term_label,
            COALESCE(tags.tag_id, '') AS tag_id,
            COALESCE(tags.tag_name, '') AS tag_name,
            COALESCE(mappings.tag_id, '') AS mapped_tag_id,
            mappings.class_term_no AS mapped_class_term_no,
            COALESCE(mappings.class_term_label, '') AS mapped_class_term_label
        FROM user_ops_pool_current current
        LEFT JOIN contact_tags tags
          ON tags.external_userid = current.external_userid
         AND tags.userid = current.owner_userid
        LEFT JOIN class_term_tag_mapping mappings
          ON mappings.tag_id = tags.tag_id
         AND mappings.tag_group_name = ?
         AND mappings.is_active = ?
         AND COALESCE(mappings.tag_id, '') <> ''
        WHERE current.owner_userid = ?
          AND COALESCE(current.external_userid, '') <> ''
        ORDER BY current.id ASC, mappings.class_term_no ASC, tags.tag_id ASC, tags.tag_name ASC
        """,
        (USER_OPS_CLASS_TERM_TAG_GROUP_NAME, _db_bool(True), normalized_owner_userid),
    ).fetchall()
    preview_by_pool_id: dict[int, dict[str, Any]] = {}
    for row in rows:
        pool_id = int(row["pool_id"])
        preview = preview_by_pool_id.setdefault(
            pool_id,
            {
                "pool_id": pool_id,
                "mobile": str(row.get("mobile") or "").strip(),
                "external_userid": str(row.get("external_userid") or "").strip(),
                "customer_name": str(row.get("customer_name") or "").strip(),
                "owner_userid": str(row.get("owner_userid") or "").strip(),
                "current_class_term_no": int(row["current_class_term_no"]) if row.get("current_class_term_no") not in (None, "") else None,
                "current_class_term_label": str(row.get("current_class_term_label") or "").strip(),
                "matched_terms": [],
                "matched_term_keys": set(),
                "tag_ids": [],
                "tag_names": [],
            },
        )
        tag_id = str(row.get("tag_id") or "").strip()
        tag_name = str(row.get("tag_name") or "").strip()
        if tag_id and tag_id not in preview["tag_ids"]:
            preview["tag_ids"].append(tag_id)
        if tag_name and tag_name not in preview["tag_names"]:
            preview["tag_names"].append(tag_name)
        mapped_no = row.get("mapped_class_term_no")
        mapped_label = str(row.get("mapped_class_term_label") or "").strip()
        if mapped_no in (None, ""):
            continue
        mapped_tag_id = str(row.get("mapped_tag_id") or "").strip()
        key = f"{int(mapped_no)}:{mapped_label}:{mapped_tag_id}"
        if key in preview["matched_term_keys"]:
            continue
        preview["matched_term_keys"].add(key)
        preview["matched_terms"].append(
            {
                "class_term_no": int(mapped_no),
                "class_term_label": mapped_label,
                "tag_id": mapped_tag_id,
                "tag_name": tag_name,
            }
        )
    preview_items: list[dict[str, Any]] = []
    for item in preview_by_pool_id.values():
        matched_terms = list(item["matched_terms"])
        current_no = item["current_class_term_no"]
        current_label = item["current_class_term_label"]
        if len(matched_terms) > 1:
            decision = "conflict"
        elif len(matched_terms) == 1:
            matched = matched_terms[0]
            if current_no == matched["class_term_no"] and current_label == matched["class_term_label"]:
                decision = "unchanged"
            else:
                decision = "update"
        else:
            decision = "no_match"
        preview_items.append(
            {
                "pool_id": item["pool_id"],
                "mobile": item["mobile"],
                "external_userid": item["external_userid"],
                "customer_name": item["customer_name"],
                "owner_userid": item["owner_userid"],
                "current_class_term_no": current_no,
                "current_class_term_label": current_label,
                "matched_terms": matched_terms,
                "tag_ids": list(item["tag_ids"]),
                "tag_names": list(item["tag_names"]),
                "decision": decision,
            }
        )
    return preview_items

def backfill_class_term_for_owner(
    *,
    owner_userid: str,
    dry_run: bool = True,
    operator: str = "",
) -> dict[str, Any]:
    normalized_owner_userid = str(owner_userid or "").strip()
    if not normalized_owner_userid:
        raise ValueError("owner_userid is required")
    tag_definition_sync = sync_user_ops_class_term_tag_definitions()
    tag_refresh = refresh_user_ops_contact_tags_for_owner(normalized_owner_userid)
    preview_items = _build_user_ops_backfill_preview(normalized_owner_userid)
    mappings = _list_active_class_term_mappings()
    summary = {
        "owner_userid": normalized_owner_userid,
        "dry_run": bool(dry_run),
        "mapping_count": len(mappings),
        "tag_definition_sync": tag_definition_sync,
        "tag_refresh": tag_refresh,
        "total_candidates": len(preview_items),
        "update_count": sum(1 for item in preview_items if item["decision"] == "update"),
        "unchanged_count": sum(1 for item in preview_items if item["decision"] == "unchanged"),
        "no_match_count": sum(1 for item in preview_items if item["decision"] == "no_match"),
        "conflict_count": sum(1 for item in preview_items if item["decision"] == "conflict"),
        "items": preview_items,
    }
    if dry_run:
        return {"ok": True, **summary}

    db = get_db()
    actor = str(operator or _current_user_ops_operator()).strip() or "admin_user_ops"
    applied_count = 0
    conflict_logged = 0
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for item in preview_items:
        if item["decision"] == "conflict":
            db.execute(
                """
                INSERT INTO user_ops_pool_history (
                    pool_id, mobile, external_userid, action_type, old_payload_json, new_payload_json, operator, source_type, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["pool_id"],
                    item["mobile"],
                    item["external_userid"],
                    "class_term_backfill_conflict",
                    json.dumps(
                        {
                            "class_term_no": item["current_class_term_no"],
                            "class_term_label": item["current_class_term_label"],
                        },
                        ensure_ascii=False,
                    ),
                    json.dumps(
                        {
                            "matched_terms": item["matched_terms"],
                            "tag_names": item["tag_names"],
                        },
                        ensure_ascii=False,
                    ),
                    actor,
                    "class_term_backfill",
                    now,
                ),
            )
            conflict_logged += 1
            continue
        if item["decision"] != "update":
            continue
        matched = item["matched_terms"][0]
        db.execute(
            """
            UPDATE user_ops_pool_current
            SET class_term_no = ?, class_term_label = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                matched["class_term_no"],
                matched["class_term_label"],
                now,
                item["pool_id"],
            ),
        )
        db.execute(
            """
            INSERT INTO user_ops_pool_history (
                pool_id, mobile, external_userid, action_type, old_payload_json, new_payload_json, operator, source_type, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item["pool_id"],
                item["mobile"],
                item["external_userid"],
                "class_term_backfill_apply",
                json.dumps(
                    {
                        "class_term_no": item["current_class_term_no"],
                        "class_term_label": item["current_class_term_label"],
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "class_term_no": matched["class_term_no"],
                        "class_term_label": matched["class_term_label"],
                        "matched_terms": item["matched_terms"],
                    },
                    ensure_ascii=False,
                ),
                actor,
                "class_term_backfill",
                now,
            ),
        )
        applied_count += 1
    db.commit()
    return {
        "ok": True,
        **summary,
        "dry_run": False,
        "applied_count": applied_count,
        "conflict_logged_count": conflict_logged,
    }

def schedule_user_ops_auto_assign_class_term_job(
    *,
    external_userid: str,
    owner_userid: str,
    delay_seconds: int = 10,
    operator: str = "",
) -> dict[str, Any]:
    normalized_external_userid = str(external_userid or "").strip()
    normalized_owner_userid = str(owner_userid or "").strip()
    if not normalized_external_userid:
        return {"ok": True, "scheduled": False, "reason": "missing_external_userid"}
    if normalized_owner_userid != USER_OPS_TARGET_AUTO_ASSIGN_OWNER:
        return {"ok": True, "scheduled": False, "reason": "owner_not_supported"}

    now_dt = datetime.now()
    run_after_dt = now_dt + timedelta(seconds=max(int(delay_seconds or 0), 0))
    run_after = run_after_dt.strftime("%Y-%m-%d %H:%M:%S")
    actor = str(operator or _current_user_ops_operator()).strip() or "system_auto_assign"
    payload = {
        "external_userid": normalized_external_userid,
        "owner_userid": normalized_owner_userid,
        "delay_seconds": max(int(delay_seconds or 0), 0),
        "scheduled_by": actor,
    }
    row = get_db().execute(
        """
        INSERT INTO user_ops_deferred_jobs (
            job_type, external_userid, owner_userid, run_after, status,
            attempt_count, payload_json, result_json, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, 'pending', 0, ?, '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING id, job_type, external_userid, owner_userid, run_after, status, attempt_count, created_at, updated_at
        """,
        (
            USER_OPS_DEFERRED_JOB_TYPE_AUTO_ASSIGN_CLASS_TERM,
            normalized_external_userid,
            normalized_owner_userid,
            run_after,
            json.dumps(payload, ensure_ascii=False),
        ),
    ).fetchone()
    get_db().commit()
    return {
        "ok": True,
        "scheduled": True,
        "job": {
            "id": int(row["id"]),
            "job_type": str(row.get("job_type") or "").strip(),
            "external_userid": str(row.get("external_userid") or "").strip(),
            "owner_userid": str(row.get("owner_userid") or "").strip(),
            "run_after": _stringify_db_timestamp(row.get("run_after")),
            "status": str(row.get("status") or "").strip(),
            "attempt_count": int(row.get("attempt_count") or 0),
            "created_at": _stringify_db_timestamp(row.get("created_at")),
            "updated_at": _stringify_db_timestamp(row.get("updated_at")),
        },
    }

def _list_due_user_ops_deferred_jobs(limit: int, now_at: str) -> list[dict[str, Any]]:
    rows = get_db().execute(
        """
        SELECT
            id, job_type, external_userid, owner_userid, run_after, status,
            attempt_count, payload_json, result_json, created_at, updated_at
        FROM user_ops_deferred_jobs
        WHERE job_type = ?
          AND status = 'pending'
          AND run_after <= ?
        ORDER BY run_after ASC, id ASC
        LIMIT ?
        """,
        (
            USER_OPS_DEFERRED_JOB_TYPE_AUTO_ASSIGN_CLASS_TERM,
            now_at,
            max(int(limit or 0), 1),
        ),
    ).fetchall()
    return [dict(row) for row in rows]

def _get_user_ops_deferred_job(job_id: int) -> dict[str, Any] | None:
    row = get_db().execute(
        """
        SELECT
            id, job_type, external_userid, owner_userid, run_after, status,
            attempt_count, payload_json, result_json, created_at, updated_at
        FROM user_ops_deferred_jobs
        WHERE id = ?
        LIMIT 1
        """,
        (int(job_id),),
    ).fetchone()
    return dict(row) if row else None

def _mark_user_ops_deferred_job_running(job_id: int) -> dict[str, Any] | None:
    job = _get_user_ops_deferred_job(job_id)
    if not job or str(job.get("status") or "").strip() != "pending":
        return None
    get_db().execute(
        """
        UPDATE user_ops_deferred_jobs
        SET status = 'running',
            attempt_count = COALESCE(attempt_count, 0) + 1,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (int(job_id),),
    )
    get_db().commit()
    return _get_user_ops_deferred_job(job_id)

def _finish_user_ops_deferred_job(job_id: int, *, status: str, result_payload: dict[str, Any]) -> None:
    get_db().execute(
        """
        UPDATE user_ops_deferred_jobs
        SET status = ?,
            result_json = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            str(status or "").strip(),
            json.dumps(result_payload, ensure_ascii=False),
            int(job_id),
        ),
    )
    get_db().commit()

def _insert_user_ops_history_record(
    *,
    pool_id: int | None,
    mobile: str,
    external_userid: str,
    action_type: str,
    old_payload: dict[str, Any],
    new_payload: dict[str, Any],
    operator: str,
    source_type: str,
    created_at: str,
) -> None:
    get_db().execute(
        """
        INSERT INTO user_ops_pool_history (
            pool_id, mobile, external_userid, action_type, old_payload_json, new_payload_json, operator, source_type, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            pool_id,
            str(mobile or "").strip(),
            str(external_userid or "").strip(),
            str(action_type or "").strip(),
            json.dumps(old_payload, ensure_ascii=False),
            json.dumps(new_payload, ensure_ascii=False),
            str(operator or "").strip(),
            str(source_type or "").strip(),
            str(created_at or "").strip(),
        ),
    )

def _find_user_ops_backfill_preview_item(owner_userid: str, external_userid: str) -> dict[str, Any] | None:
    normalized_external_userid = str(external_userid or "").strip()
    if not normalized_external_userid:
        return None
    for item in _build_user_ops_backfill_preview(owner_userid):
        if str(item.get("external_userid") or "").strip() == normalized_external_userid:
            return item
    return None

def _execute_auto_assign_class_term_job(job: dict[str, Any], *, operator: str) -> dict[str, Any]:
    normalized_owner_userid = str(job.get("owner_userid") or "").strip()
    normalized_external_userid = str(job.get("external_userid") or "").strip()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    actor = str(operator or "").strip() or "system_auto_assign"

    if normalized_owner_userid != USER_OPS_TARGET_AUTO_ASSIGN_OWNER:
        return {
            "status": "skipped",
            "reason": "owner_not_supported",
            "external_userid": normalized_external_userid,
            "owner_userid": normalized_owner_userid,
        }

    tag_definition_sync = sync_user_ops_class_term_tag_definitions()
    tag_refresh = refresh_user_ops_contact_tags_for_external_userid(
        external_userid=normalized_external_userid,
        owner_userid=normalized_owner_userid,
    )
    preview_item = _find_user_ops_backfill_preview_item(normalized_owner_userid, normalized_external_userid)
    if preview_item is None:
        return {
            "status": "skipped",
            "reason": "pool_item_not_found",
            "external_userid": normalized_external_userid,
            "owner_userid": normalized_owner_userid,
            "tag_definition_sync": tag_definition_sync,
            "tag_refresh": tag_refresh,
        }

    current_payload = {
        "class_term_no": preview_item.get("current_class_term_no"),
        "class_term_label": preview_item.get("current_class_term_label"),
    }
    decision = str(preview_item.get("decision") or "").strip()
    if decision == "conflict":
        _insert_user_ops_history_record(
            pool_id=preview_item.get("pool_id"),
            mobile=str(preview_item.get("mobile") or "").strip(),
            external_userid=normalized_external_userid,
            action_type="class_term_auto_assign_conflict",
            old_payload=current_payload,
            new_payload={
                "matched_terms": preview_item.get("matched_terms") or [],
                "tag_names": preview_item.get("tag_names") or [],
            },
            operator=actor,
            source_type="class_term_auto_assign",
            created_at=now,
        )
        get_db().commit()
        return {
            "status": "conflict",
            "pool_id": preview_item.get("pool_id"),
            "external_userid": normalized_external_userid,
            "owner_userid": normalized_owner_userid,
            "matched_terms": preview_item.get("matched_terms") or [],
            "decision": decision,
            "tag_definition_sync": tag_definition_sync,
            "tag_refresh": tag_refresh,
        }

    if decision == "no_match":
        _insert_user_ops_history_record(
            pool_id=preview_item.get("pool_id"),
            mobile=str(preview_item.get("mobile") or "").strip(),
            external_userid=normalized_external_userid,
            action_type="class_term_auto_assign_skip",
            old_payload=current_payload,
            new_payload={
                "matched_terms": [],
                "tag_names": preview_item.get("tag_names") or [],
                "reason": "no_match",
            },
            operator=actor,
            source_type="class_term_auto_assign",
            created_at=now,
        )
        get_db().commit()
        return {
            "status": "skipped",
            "pool_id": preview_item.get("pool_id"),
            "external_userid": normalized_external_userid,
            "owner_userid": normalized_owner_userid,
            "decision": decision,
            "tag_definition_sync": tag_definition_sync,
            "tag_refresh": tag_refresh,
        }

    matched = (preview_item.get("matched_terms") or [{}])[0]
    next_payload = {
        "class_term_no": matched.get("class_term_no"),
        "class_term_label": matched.get("class_term_label"),
        "matched_terms": preview_item.get("matched_terms") or [],
    }
    if decision == "update":
        get_db().execute(
            """
            UPDATE user_ops_pool_current
            SET class_term_no = ?, class_term_label = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                matched.get("class_term_no"),
                matched.get("class_term_label"),
                now,
                preview_item.get("pool_id"),
            ),
        )
    _insert_user_ops_history_record(
        pool_id=preview_item.get("pool_id"),
        mobile=str(preview_item.get("mobile") or "").strip(),
        external_userid=normalized_external_userid,
        action_type="class_term_auto_assign",
        old_payload=current_payload,
        new_payload=next_payload,
        operator=actor,
        source_type="class_term_auto_assign",
        created_at=now,
    )
    get_db().commit()
    return {
        "status": "success",
        "pool_id": preview_item.get("pool_id"),
        "external_userid": normalized_external_userid,
        "owner_userid": normalized_owner_userid,
        "decision": decision,
        "class_term_no": matched.get("class_term_no"),
        "class_term_label": matched.get("class_term_label"),
        "tag_definition_sync": tag_definition_sync,
        "tag_refresh": tag_refresh,
    }

def run_due_user_ops_deferred_jobs(limit: int = 20) -> dict[str, Any]:
    normalized_limit = max(1, min(int(limit or 20), 200))
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    due_jobs = _list_due_user_ops_deferred_jobs(normalized_limit, now)
    summary = {
        "ok": True,
        "limit": normalized_limit,
        "scanned_count": len(due_jobs),
        "success_count": 0,
        "conflict_count": 0,
        "skipped_count": 0,
        "failed_count": 0,
        "items": [],
    }
    if not due_jobs:
        return summary

    reload_payload = reload_user_ops_pool()
    summary["reload"] = reload_payload
    actor = "system_auto_assign"
    for job in due_jobs:
        running_job = _mark_user_ops_deferred_job_running(int(job["id"]))
        if not running_job:
            continue
        try:
            result = _execute_auto_assign_class_term_job(running_job, operator=actor)
            status = str(result.get("status") or "").strip() or "failed"
        except Exception as exc:
            logging.getLogger("user_ops").exception("user ops deferred job failed id=%s", job["id"])
            status = "failed"
            result = {
                "status": "failed",
                "external_userid": str(job.get("external_userid") or "").strip(),
                "owner_userid": str(job.get("owner_userid") or "").strip(),
                "error": str(exc),
            }
        _finish_user_ops_deferred_job(int(job["id"]), status=status, result_payload=result)
        if status == "success":
            summary["success_count"] += 1
        elif status == "conflict":
            summary["conflict_count"] += 1
        elif status == "skipped":
            summary["skipped_count"] += 1
        else:
            summary["failed_count"] += 1
        summary["items"].append(
            {
                "job_id": int(job["id"]),
                "status": status,
                **result,
            }
        )
    return summary
