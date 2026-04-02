from __future__ import annotations

import json
import logging
import re
import time
from io import BytesIO
from datetime import datetime, timedelta
from typing import Any
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import requests
from flask import current_app, has_request_context, session

from ...db import get_db, get_db_backend
from ...infra.constants import (
    LEGACY_USER_OPS_POOL_STATUS_ORDER,
    USER_OPS_ACTIVATION_STATUS_DEFINITIONS,
    USER_OPS_ACTIVATION_STATUS_LABELS,
    USER_OPS_CLASS_TERM_TAG_GROUP_NAME,
    USER_OPS_CONFIRMED_CLASS_TERM_MAPPINGS,
    USER_OPS_DEFERRED_JOB_TYPE_VERIFY_CLASS_TERM_TAG_AND_UPSERT_LEAD_POOL,
    USER_OPS_HUANGXIAOCAN_ACTIVATION_SOURCE_STATES,
    USER_OPS_LEAD_POOL_ACTIVATION_STATE_DEFINITIONS,
    USER_OPS_LEAD_POOL_ACTIVATION_STATE_LABELS,
    USER_OPS_LEAD_POOL_ACTIVATION_STATES,
)

owner_backfill_logger = logging.getLogger("owner_backfill")


class ThirdPartyUserSyncError(RuntimeError):
    pass


def get_user_ops_deferred_job_counts() -> dict[str, int]:
    from . import repo

    return repo.get_deferred_job_counts()
def _normalize_legacy_user_ops_current_status(signup_status: str) -> str:
    normalized = str(signup_status or "").strip()
    if normalized == "signed_3999":
        return "signed_3999"
    if normalized == "signed_999":
        return "signed_999"
    return "lead_trial"


def _legacy_user_ops_status_rank(current_status: str) -> int:
    return LEGACY_USER_OPS_POOL_STATUS_ORDER.get(str(current_status or "").strip(), 1)


def _user_ops_merge_key(row: dict[str, Any]) -> str:
    mobile = str(row.get("mobile") or "").strip()
    external_userid = str(row.get("external_userid") or "").strip()
    if mobile:
        return f"mobile:{mobile}"
    return f"external:{external_userid}"


def _user_ops_contact_client():
    from ...wecom_client import WeComClient

    return WeComClient.from_contact_app()


def _normalize_user_ops_strategy_tag_groups(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_groups = (
        payload.get("strategy_tag_group")
        or payload.get("strategy_tag_list")
        or payload.get("strategy_tag")
        or payload.get("tag_group")
        or []
    )
    normalized_groups: list[dict[str, Any]] = []
    for group in raw_groups:
        group_name = str((group or {}).get("group_name") or (group or {}).get("name") or "").strip()
        group_id = str((group or {}).get("group_id") or (group or {}).get("id") or "").strip()
        strategy_id = str((group or {}).get("strategy_id") or "").strip()
        normalized_tags: list[dict[str, Any]] = []
        for tag in ((group or {}).get("tag") or (group or {}).get("tag_list") or (group or {}).get("tags") or []):
            tag_id = str((tag or {}).get("tag_id") or (tag or {}).get("id") or "").strip()
            tag_name = str((tag or {}).get("tag_name") or (tag or {}).get("name") or "").strip()
            if not tag_id or not tag_name:
                continue
            normalized_tags.append(
                {
                    "tag_id": tag_id,
                    "tag_name": tag_name,
                }
            )
        if not group_name:
            continue
        normalized_groups.append(
            {
                "strategy_id": strategy_id,
                "group_id": group_id,
                "group_name": group_name,
                "tags": normalized_tags,
            }
        )
    return normalized_groups


def _ensure_class_term_tag_mapping_seed() -> None:
    db = get_db()
    active_value = _db_bool(True)
    existing_rows = db.execute(
        """
        SELECT id, strategy_id, group_id, tag_id, tag_group_name, tag_name, class_term_no, class_term_label, is_active
        FROM class_term_tag_mapping
        WHERE tag_group_name = ?
        ORDER BY id ASC
        """,
        (USER_OPS_CLASS_TERM_TAG_GROUP_NAME,),
    ).fetchall()
    by_tag_id = {
        str(row.get("tag_id") or "").strip(): dict(row)
        for row in existing_rows
        if str(row.get("tag_id") or "").strip()
    }
    by_group_name = {
        (str(row.get("tag_group_name") or "").strip(), str(row.get("tag_name") or "").strip()): dict(row)
        for row in existing_rows
    }
    for item in USER_OPS_CONFIRMED_CLASS_TERM_MAPPINGS:
        normalized_tag_id = str(item.get("tag_id") or "").strip()
        normalized_group_name = str(item.get("tag_group_name") or "").strip()
        normalized_tag_name = str(item.get("tag_name") or "").strip()
        existing = None
        if normalized_tag_id:
            existing = by_tag_id.get(normalized_tag_id)
        if existing is None:
            existing = by_group_name.get((normalized_group_name, normalized_tag_name))
        if existing is None:
            db.execute(
                """
                INSERT INTO class_term_tag_mapping (
                    strategy_id, group_id, tag_id, tag_group_name, tag_name, class_term_no, class_term_label, is_active, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (
                    str(item.get("strategy_id") or "").strip(),
                    str(item.get("group_id") or "").strip(),
                    normalized_tag_id,
                    normalized_group_name,
                    normalized_tag_name,
                    int(item["class_term_no"]),
                    item["class_term_label"],
                    active_value,
                ),
            )
            continue
        db.execute(
            """
            UPDATE class_term_tag_mapping
            SET strategy_id = ?,
                group_id = ?,
                tag_id = ?,
                tag_group_name = ?,
                tag_name = ?,
                class_term_no = ?,
                class_term_label = ?,
                is_active = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                str(existing.get("strategy_id") or "").strip() or str(item.get("strategy_id") or "").strip(),
                str(existing.get("group_id") or "").strip() or str(item.get("group_id") or "").strip(),
                str(existing.get("tag_id") or "").strip() or normalized_tag_id,
                normalized_group_name or str(existing.get("tag_group_name") or "").strip(),
                normalized_tag_name or str(existing.get("tag_name") or "").strip(),
                int(item["class_term_no"]),
                item["class_term_label"],
                active_value,
                int(existing["id"]),
            ),
        )
    db.commit()


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
    by_class_term_no = {
        int(row["class_term_no"]): dict(row)
        for row in rows
        if row.get("class_term_no") not in (None, "")
    }
    updated_count = 0
    discovered_count = 0
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
            by_class_term_no[int(existing["class_term_no"])] = dict(existing)
        for tag in group.get("tags") or []:
            tag_id = str(tag.get("tag_id") or "").strip()
            tag_name = str(tag.get("tag_name") or "").strip()
            inferred_no = _infer_user_ops_class_term_no_from_tag_name(tag_name)
            if not tag_id or inferred_no is None:
                continue
            if tag_id in by_tag_id or tag_name in by_tag_name or inferred_no in by_class_term_no:
                continue
            db.execute(
                """
                INSERT INTO class_term_tag_mapping (
                    strategy_id, group_id, tag_id, tag_group_name, tag_name, class_term_no, class_term_label, is_active, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (
                    strategy_id,
                    group_id,
                    tag_id,
                    USER_OPS_CLASS_TERM_TAG_GROUP_NAME,
                    tag_name,
                    inferred_no,
                    f"{inferred_no}期",
                    _db_bool(True),
                ),
            )
            inserted = db.execute(
                """
                SELECT id, strategy_id, group_id, tag_id, tag_name, class_term_no, class_term_label
                FROM class_term_tag_mapping
                WHERE tag_id = ?
                LIMIT 1
                """,
                (tag_id,),
            ).fetchone()
            inserted_payload = dict(inserted) if inserted else {}
            by_tag_id[tag_id] = inserted_payload
            by_tag_name[tag_name] = inserted_payload
            by_class_term_no[inferred_no] = inserted_payload
            discovered_count += 1
            synced_items.append(
                {
                    "mapping_id": int((inserted_payload or {}).get("id") or 0),
                    "strategy_id": strategy_id,
                    "group_id": group_id,
                    "tag_id": tag_id,
                    "tag_name": tag_name,
                    "class_term_no": inferred_no,
                    "class_term_label": f"{inferred_no}期",
                    "mapping_source": "live_discovered",
                }
            )
    db.commit()
    return {
        "ok": True,
        "group_count": len(target_groups),
        "synced_count": len(synced_items),
        "updated_count": updated_count,
        "discovered_count": discovered_count,
        "skipped_count": skipped_count,
        "items": synced_items,
    }


def _list_user_ops_crm_source_rows() -> list[dict[str, Any]]:
    rows = get_db().execute(
        """
        WITH candidate_external_userids AS (
            SELECT external_userid
            FROM class_user_status_current
            WHERE COALESCE(external_userid, '') <> ''
            UNION
            SELECT external_userid
            FROM contacts
            WHERE COALESCE(external_userid, '') <> ''
            UNION
            SELECT external_userid
            FROM external_contact_bindings
            WHERE COALESCE(external_userid, '') <> ''
        )
        SELECT
            'crm' AS source_kind,
            candidate.external_userid,
            COALESCE(status.signup_status, '') AS signup_status,
            COALESCE(status.signup_label_name, '') AS signup_label_name,
            COALESCE(status.customer_name_snapshot, '') AS status_customer_name,
            COALESCE(status.owner_userid_snapshot, '') AS status_owner_userid,
            COALESCE(status.mobile_snapshot, '') AS status_mobile,
            COALESCE(status.updated_at, status.set_at) AS status_updated_at,
            COALESCE(c.customer_name, '') AS contact_customer_name,
            COALESCE(c.owner_userid, '') AS contact_owner_userid,
            c.updated_at AS contact_updated_at,
            bindings.person_id,
            COALESCE(bindings.updated_at, bindings.created_at) AS binding_updated_at,
            COALESCE(p.mobile, '') AS bound_mobile,
            COALESCE(p.updated_at, p.created_at) AS person_updated_at,
            '' AS lead_mobile,
            '' AS lead_source_type,
            NULL AS lead_updated_at
        FROM candidate_external_userids candidate
        LEFT JOIN class_user_status_current status
          ON status.external_userid = candidate.external_userid
        LEFT JOIN contacts c
          ON c.external_userid = candidate.external_userid
        LEFT JOIN external_contact_bindings bindings
          ON bindings.external_userid = candidate.external_userid
        LEFT JOIN people p
          ON p.id = bindings.person_id
        ORDER BY candidate.external_userid ASC
        """
    ).fetchall()
    return [dict(row) for row in rows]


def _list_user_ops_experience_lead_rows() -> list[dict[str, Any]]:
    # W06/W09 note: class-term import currently reuses user_ops_experience_leads
    # as the phone anchor so phone-only rows can participate in pool reload.
    # The actual class-term values still land on the pool projection.
    rows = get_db().execute(
        """
        SELECT
            'experience_import' AS source_kind,
            COALESCE(bindings.external_userid, '') AS external_userid,
            COALESCE(status.signup_status, '') AS signup_status,
            COALESCE(status.signup_label_name, '') AS signup_label_name,
            COALESCE(status.customer_name_snapshot, '') AS status_customer_name,
            COALESCE(status.owner_userid_snapshot, '') AS status_owner_userid,
            COALESCE(status.mobile_snapshot, '') AS status_mobile,
            COALESCE(status.updated_at, status.set_at) AS status_updated_at,
            COALESCE(c.customer_name, '') AS contact_customer_name,
            COALESCE(c.owner_userid, '') AS contact_owner_userid,
            c.updated_at AS contact_updated_at,
            bindings.person_id,
            COALESCE(bindings.updated_at, bindings.created_at) AS binding_updated_at,
            COALESCE(p.mobile, '') AS bound_mobile,
            COALESCE(p.updated_at, p.created_at) AS person_updated_at,
            leads.mobile AS lead_mobile,
            COALESCE(leads.source_type, 'experience_import') AS lead_source_type,
            COALESCE(leads.updated_at, leads.created_at) AS lead_updated_at
        FROM user_ops_experience_leads leads
        LEFT JOIN people p
          ON p.mobile = leads.mobile
        LEFT JOIN external_contact_bindings bindings
          ON bindings.person_id = p.id
        LEFT JOIN contacts c
          ON c.external_userid = bindings.external_userid
        LEFT JOIN class_user_status_current status
          ON status.external_userid = bindings.external_userid
        WHERE leads.is_active = ?
        ORDER BY leads.mobile ASC, bindings.updated_at DESC, bindings.external_userid ASC
        """,
        (_db_bool(True),),
    ).fetchall()
    return [dict(row) for row in rows]


def _materialize_user_ops_crm_candidate(row: dict[str, Any]) -> dict[str, Any] | None:
    external_userid = str(row.get("external_userid") or "").strip()
    if not external_userid:
        return None
    bound_mobile = str(row.get("bound_mobile") or "").strip()
    status_mobile = str(row.get("status_mobile") or "").strip()
    mobile = bound_mobile or status_mobile
    customer_name = (
        str(row.get("status_customer_name") or "").strip()
        or str(row.get("contact_customer_name") or "").strip()
    )
    owner_userid = (
        str(row.get("status_owner_userid") or "").strip()
        or str(row.get("contact_owner_userid") or "").strip()
    )
    current_status = _normalize_legacy_user_ops_current_status(str(row.get("signup_status") or "").strip())
    is_wecom_bound = bool(external_userid and bound_mobile and row.get("person_id") is not None)
    updated_candidates = [
        _stringify_db_timestamp(row.get("status_updated_at")),
        _stringify_db_timestamp(row.get("contact_updated_at")),
        _stringify_db_timestamp(row.get("binding_updated_at")),
        _stringify_db_timestamp(row.get("person_updated_at")),
    ]
    updated_at = max([item for item in updated_candidates if item], default=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    return {
        "mobile": mobile,
        "external_userid": external_userid,
        "customer_name": customer_name,
        "owner_userid": owner_userid,
        "current_status": current_status,
        "is_wecom_bound": is_wecom_bound,
        "activation_status": "not_activated",
        "activation_remark": "",
        "activation_source_present": False,
        "class_term_no": None,
        "class_term_label": "",
        "source_type": "crm_bound",
        "updated_at": updated_at,
    }


def _materialize_user_ops_experience_candidate(row: dict[str, Any]) -> dict[str, Any] | None:
    mobile = str(row.get("lead_mobile") or "").strip()
    if not mobile:
        return None
    external_userid = str(row.get("external_userid") or "").strip()
    bound_mobile = str(row.get("bound_mobile") or "").strip()
    customer_name = (
        str(row.get("status_customer_name") or "").strip()
        or str(row.get("contact_customer_name") or "").strip()
    )
    owner_userid = (
        str(row.get("status_owner_userid") or "").strip()
        or str(row.get("contact_owner_userid") or "").strip()
    )
    current_status = _normalize_legacy_user_ops_current_status(str(row.get("signup_status") or "").strip())
    is_wecom_bound = bool(external_userid and bound_mobile and row.get("person_id") is not None and bound_mobile == mobile)
    updated_candidates = [
        _stringify_db_timestamp(row.get("lead_updated_at")),
        _stringify_db_timestamp(row.get("status_updated_at")),
        _stringify_db_timestamp(row.get("contact_updated_at")),
        _stringify_db_timestamp(row.get("binding_updated_at")),
        _stringify_db_timestamp(row.get("person_updated_at")),
    ]
    updated_at = max([item for item in updated_candidates if item], default=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    return {
        "mobile": mobile,
        "external_userid": external_userid,
        "customer_name": customer_name,
        "owner_userid": owner_userid,
        "current_status": current_status,
        "is_wecom_bound": is_wecom_bound,
        "activation_status": "not_activated",
        "activation_remark": "",
        "activation_source_present": False,
        "class_term_no": None,
        "class_term_label": "",
        "source_type": str(row.get("lead_source_type") or "").strip() or "experience_import",
        "updated_at": updated_at,
    }


def _materialize_user_ops_candidate(row: dict[str, Any]) -> dict[str, Any] | None:
    if str(row.get("source_kind") or "").strip() == "experience_import":
        return _materialize_user_ops_experience_candidate(row)
    return _materialize_user_ops_crm_candidate(row)


def _merge_user_ops_candidate(existing: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    if _legacy_user_ops_status_rank(candidate["current_status"]) >= _legacy_user_ops_status_rank(existing["current_status"]):
        merged["current_status"] = candidate["current_status"]
    if candidate.get("is_wecom_bound"):
        merged["is_wecom_bound"] = True
    for key in ["mobile", "external_userid", "customer_name", "owner_userid"]:
        if not merged.get(key) and candidate.get(key):
            merged[key] = candidate[key]
    if str(candidate.get("source_type") or "").strip() == "experience_import":
        merged["source_type"] = "experience_import"
    if candidate.get("updated_at", "") > merged.get("updated_at", ""):
        merged["updated_at"] = candidate["updated_at"]
    return merged


def _list_user_ops_activation_source_rows() -> list[dict[str, Any]]:
    rows = get_db().execute(
        """
        SELECT
            mobile,
            activation_status,
            activation_remark,
            import_batch_id,
            created_by,
            COALESCE(updated_at, created_at) AS source_updated_at
        FROM user_ops_activation_status_source
        WHERE is_active = ?
        ORDER BY mobile ASC
        """,
        (_db_bool(True),),
    ).fetchall()
    return [dict(row) for row in rows]


def _apply_user_ops_activation_sources(next_map: dict[str, dict[str, Any]]) -> None:
    # Activation import remains a separate phone-keyed source and never writes
    # external_userid directly.
    for row in _list_user_ops_activation_source_rows():
        mobile = str(row.get("mobile") or "").strip()
        if not mobile:
            continue
        merge_key = f"mobile:{mobile}"
        candidate = next_map.get(merge_key)
        if candidate is None:
            candidate = {
                "mobile": mobile,
                "external_userid": "",
                "customer_name": "",
                "owner_userid": "",
                "current_status": "lead_trial",
                "is_wecom_bound": False,
                "activation_status": "not_activated",
                "activation_remark": "",
                "activation_source_present": False,
                "class_term_no": None,
                "class_term_label": "",
                "source_type": "activation_import",
                "updated_at": _stringify_db_timestamp(row.get("source_updated_at")) or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        candidate["activation_status"] = str(row.get("activation_status") or "").strip() or "not_activated"
        candidate["activation_remark"] = str(row.get("activation_remark") or "").strip()
        candidate["activation_source_present"] = True
        candidate["updated_at"] = max(
            candidate.get("updated_at", ""),
            _stringify_db_timestamp(row.get("source_updated_at")) or candidate.get("updated_at", ""),
        )
        next_map[merge_key] = candidate


def _overlay_user_ops_previous_projection(candidate: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
    if not previous:
        return candidate
    merged = dict(candidate)
    previous_activation_status = str(previous.get("activation_status") or "").strip()
    previous_activation_remark = str(previous.get("activation_remark") or "").strip()
    previous_class_term_no = previous.get("class_term_no")
    previous_class_term_label = str(previous.get("class_term_label") or "").strip()
    if previous_activation_status and not merged.get("activation_source_present"):
        merged["activation_status"] = previous_activation_status
    if previous_activation_remark and not merged.get("activation_source_present"):
        merged["activation_remark"] = previous_activation_remark
    if previous_class_term_no not in (None, ""):
        merged["class_term_no"] = int(previous_class_term_no)
    if previous_class_term_label:
        merged["class_term_label"] = previous_class_term_label
    if str(previous.get("source_type") or "").strip() == "experience_import":
        merged["source_type"] = "experience_import"
    return merged


def _serialize_user_ops_current_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "mobile": str(row.get("mobile") or "").strip(),
        "external_userid": str(row.get("external_userid") or "").strip(),
        "customer_name": str(row.get("customer_name") or "").strip(),
        "owner_userid": str(row.get("owner_userid") or "").strip(),
        "current_status": str(row.get("current_status") or "").strip() or "lead_trial",
        "is_wecom_bound": bool(row.get("is_wecom_bound")),
        "activation_status": str(row.get("activation_status") or "").strip() or "not_activated",
        "activation_remark": str(row.get("activation_remark") or "").strip(),
        "activation_source_present": bool(row.get("activation_source_present")),
        "class_term_no": int(row["class_term_no"]) if row.get("class_term_no") not in (None, "") else None,
        "class_term_label": str(row.get("class_term_label") or "").strip(),
        "source_type": str(row.get("source_type") or "").strip() or "manual",
    }


def _load_existing_user_ops_pool_map() -> dict[str, dict[str, Any]]:
    rows = get_db().execute(
        """
        SELECT
            id,
            mobile,
            external_userid,
            customer_name,
            owner_userid,
            current_status,
            is_wecom_bound,
            activation_status,
            activation_remark,
            class_term_no,
            class_term_label,
            source_type,
            created_at,
            updated_at
        FROM user_ops_pool_current
        """
    ).fetchall()
    payload: dict[str, dict[str, Any]] = {}
    for row in rows:
        item = _serialize_user_ops_current_row(dict(row))
        item["id"] = row.get("id")
        item["created_at"] = _stringify_db_timestamp(row.get("created_at"))
        item["updated_at"] = _stringify_db_timestamp(row.get("updated_at"))
        payload[_user_ops_merge_key(item)] = item
    return payload


def reload_user_ops_pool() -> dict[str, Any]:
    # Legacy maintenance helper only. Admin V2 no longer reads or depends on
    # `user_ops_pool_current`; keep this helper only as rollback/migration
    # support while old tables remain in the schema.
    # Rebuild the phone-centric projection from CRM-bound rows, mobile-anchor
    # rows, and activation source rows. external_userid / is_wecom_bound always
    # come from existing binding relations; class term and activation are
    # overlaid back onto user_ops_pool_current as projection fields.
    _ensure_class_term_tag_mapping_seed()
    previous_map = _load_existing_user_ops_pool_map()
    candidates = _list_user_ops_crm_source_rows() + _list_user_ops_experience_lead_rows()
    next_map: dict[str, dict[str, Any]] = {}
    for source_row in candidates:
        candidate = _materialize_user_ops_candidate(source_row)
        if candidate is None:
            continue
        merge_key = _user_ops_merge_key(candidate)
        if merge_key in next_map:
            next_map[merge_key] = _merge_user_ops_candidate(next_map[merge_key], candidate)
        else:
            next_map[merge_key] = candidate
    _apply_user_ops_activation_sources(next_map)

    db = get_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.execute("DELETE FROM user_ops_pool_current")

    inserted_count = 0
    changed_count = 0
    removed_count = 0
    history_written = 0

    for merge_key, item in next_map.items():
        previous = previous_map.get(merge_key)
        item = _overlay_user_ops_previous_projection(item, previous)
        created_at = str((previous or {}).get("created_at") or now).strip()
        db.execute(
            """
            INSERT INTO user_ops_pool_current (
                mobile, external_userid, customer_name, owner_userid, current_status, is_wecom_bound,
                activation_status, activation_remark, class_term_no, class_term_label, source_type,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item["mobile"],
                item["external_userid"],
                item["customer_name"],
                item["owner_userid"],
                item["current_status"],
                _db_bool(bool(item["is_wecom_bound"])),
                item["activation_status"],
                item["activation_remark"],
                item["class_term_no"],
                item["class_term_label"],
                item["source_type"],
                created_at,
                now,
            ),
        )
        inserted_count += 1

        previous_payload = _serialize_user_ops_current_row(previous or {})
        next_payload = _serialize_user_ops_current_row(item)
        if previous is None or previous_payload != next_payload:
            changed_count += 1
            db.execute(
                """
                INSERT INTO user_ops_pool_history (
                    pool_id, mobile, external_userid, action_type, old_payload_json, new_payload_json, operator, source_type, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    None,
                    item["mobile"],
                    item["external_userid"],
                    "pool_reload_upsert",
                    json.dumps(previous_payload, ensure_ascii=False),
                    json.dumps(next_payload, ensure_ascii=False),
                    "system_reload",
                    item["source_type"],
                    now,
                ),
            )
            history_written += 1

    for merge_key, previous in previous_map.items():
        if merge_key in next_map:
            continue
        removed_count += 1
        db.execute(
            """
            INSERT INTO user_ops_pool_history (
                pool_id, mobile, external_userid, action_type, old_payload_json, new_payload_json, operator, source_type, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                previous.get("id"),
                previous.get("mobile", ""),
                previous.get("external_userid", ""),
                "pool_reload_remove",
                json.dumps(_serialize_user_ops_current_row(previous), ensure_ascii=False),
                json.dumps({}, ensure_ascii=False),
                "system_reload",
                str(previous.get("source_type") or "").strip() or "manual",
                now,
            ),
        )
        history_written += 1

    db.commit()
    return {
        "ok": True,
        "total": len(next_map),
        "inserted_count": inserted_count,
        "changed_count": changed_count,
        "removed_count": removed_count,
        "history_written": history_written,
        "reloaded_at": now,
    }


def _user_ops_class_term_options() -> list[dict[str, Any]]:
    _ensure_class_term_tag_mapping_seed()
    rows = get_db().execute(
        """
        SELECT class_term_no, class_term_label
        FROM class_term_tag_mapping
        WHERE is_active = ?
        ORDER BY class_term_no ASC, id ASC
        """,
        (_db_bool(True),),
    ).fetchall()
    return [
        {
            "class_term_no": int(row["class_term_no"]),
            "class_term_label": str(row.get("class_term_label") or "").strip(),
        }
        for row in rows
    ]


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


def _get_active_class_term_mapping_by_no(class_term_no: int | None) -> dict[str, Any] | None:
    if class_term_no in (None, ""):
        return None
    normalized_no = int(class_term_no)
    return next(
        (item for item in _list_active_class_term_mappings() if int(item["class_term_no"]) == normalized_no),
        None,
    )


def _confirmed_class_term_mappings_by_no() -> dict[int, dict[str, Any]]:
    return {
        int(item["class_term_no"]): {
            "strategy_id": str(item.get("strategy_id") or "").strip(),
            "group_id": str(item.get("group_id") or "").strip(),
            "tag_id": str(item.get("tag_id") or "").strip(),
            "tag_group_name": str(item.get("tag_group_name") or "").strip(),
            "tag_name": str(item.get("tag_name") or "").strip(),
            "class_term_no": int(item["class_term_no"]),
            "class_term_label": str(item.get("class_term_label") or "").strip(),
        }
        for item in USER_OPS_CONFIRMED_CLASS_TERM_MAPPINGS
    }


def _infer_user_ops_class_term_no_from_tag_name(tag_name: str) -> int | None:
    normalized_tag_name = str(tag_name or "").strip()
    if not normalized_tag_name:
        return None
    if "首期" in normalized_tag_name:
        return 1
    matched = re.search(r"第\s*(\d+)\s*期", normalized_tag_name)
    if matched:
        return int(matched.group(1))
    matched = re.fullmatch(r"(\d+)\s*期", normalized_tag_name)
    if matched:
        return int(matched.group(1))
    return None


def _list_live_user_ops_class_term_tags(tag_payload: dict[str, Any]) -> list[dict[str, Any]]:
    groups = _normalize_user_ops_strategy_tag_groups(tag_payload)
    items: list[dict[str, Any]] = []
    seen_tag_ids: set[str] = set()
    for group in groups:
        if str(group.get("group_name") or "").strip() != USER_OPS_CLASS_TERM_TAG_GROUP_NAME:
            continue
        for tag in group.get("tags") or []:
            tag_id = str(tag.get("tag_id") or "").strip()
            tag_name = str(tag.get("tag_name") or "").strip()
            if not tag_id or tag_id in seen_tag_ids:
                continue
            seen_tag_ids.add(tag_id)
            inferred_no = _infer_user_ops_class_term_no_from_tag_name(tag_name)
            items.append(
                {
                    "strategy_id": str(group.get("strategy_id") or "").strip(),
                    "group_id": str(group.get("group_id") or "").strip(),
                    "tag_group_name": USER_OPS_CLASS_TERM_TAG_GROUP_NAME,
                    "tag_id": tag_id,
                    "tag_name": tag_name,
                    "class_term_no": inferred_no,
                    "class_term_label": f"{inferred_no}期" if inferred_no is not None else "",
                }
            )
    return items


def _resolve_owner_backfill_class_term_mappings(
    *,
    class_term_min: int,
    class_term_max: int,
    tag_payload: dict[str, Any],
) -> dict[str, Any]:
    confirmed_by_no = _confirmed_class_term_mappings_by_no()
    live_tags = _list_live_user_ops_class_term_tags(tag_payload)
    live_by_tag_id = {
        str(item.get("tag_id") or "").strip(): item
        for item in live_tags
        if str(item.get("tag_id") or "").strip()
    }
    live_by_tag_name = {
        str(item.get("tag_name") or "").strip(): item
        for item in live_tags
        if str(item.get("tag_name") or "").strip()
    }
    live_by_term_no: dict[int, list[dict[str, Any]]] = {}
    for item in live_tags:
        class_term_no = item.get("class_term_no")
        if class_term_no in (None, ""):
            continue
        live_by_term_no.setdefault(int(class_term_no), []).append(item)

    effective_mappings: list[dict[str, Any]] = []
    warnings: list[str] = []
    for class_term_no in range(class_term_min, class_term_max + 1):
        confirmed = confirmed_by_no.get(class_term_no)
        resolved = None
        mapping_source = ""
        live_candidates = live_by_term_no.get(class_term_no, [])
        if confirmed:
            confirmed_tag_id = str(confirmed.get("tag_id") or "").strip()
            confirmed_tag_name = str(confirmed.get("tag_name") or "").strip()
            if confirmed_tag_id and confirmed_tag_id in live_by_tag_id:
                resolved = dict(live_by_tag_id[confirmed_tag_id])
                mapping_source = "confirmed_live_tag_id"
            elif confirmed_tag_name and confirmed_tag_name in live_by_tag_name:
                resolved = dict(live_by_tag_name[confirmed_tag_name])
                mapping_source = "confirmed_live_tag_name"
            elif len(live_candidates) == 1:
                resolved = dict(live_candidates[0])
                mapping_source = "confirmed_live_inferred"
            else:
                resolved = dict(confirmed)
                mapping_source = "confirmed_seed"
        elif len(live_candidates) == 1:
            resolved = dict(live_candidates[0])
            mapping_source = "live_discovered"
        elif len(live_candidates) > 1:
            warnings.append(f"{class_term_no}期 mapping ambiguous from real tags")
        else:
            warnings.append(f"{class_term_no}期 mapping missing")
        if resolved is None:
            continue
        resolved["class_term_no"] = class_term_no
        resolved["class_term_label"] = f"{class_term_no}期"
        resolved["mapping_source"] = mapping_source
        effective_mappings.append(resolved)

    effective_by_tag_id = {
        str(item.get("tag_id") or "").strip(): item
        for item in effective_mappings
        if str(item.get("tag_id") or "").strip()
    }
    effective_by_tag_name = {
        str(item.get("tag_name") or "").strip(): item
        for item in effective_mappings
        if str(item.get("tag_name") or "").strip()
    }
    term_two_mapping = next((item for item in effective_mappings if int(item["class_term_no"]) == 2), None)
    if term_two_mapping is None:
        warnings.extend(
            [
                "2期 mapping missing",
                "2期 skipped because no real tag mapping found",
            ]
        )

    return {
        "effective_mappings": effective_mappings,
        "effective_by_tag_id": effective_by_tag_id,
        "effective_by_tag_name": effective_by_tag_name,
        "live_tags": live_tags,
        "warnings": warnings,
        "term_2_mapping": {
            "exists": term_two_mapping is not None,
            "source": str((term_two_mapping or {}).get("mapping_source") or "missing"),
            "tag_id": str((term_two_mapping or {}).get("tag_id") or "").strip(),
            "tag_name": str((term_two_mapping or {}).get("tag_name") or "").strip(),
            "class_term_no": 2,
            "class_term_label": "2期" if term_two_mapping is not None else "",
        },
    }


def _list_owner_backfill_candidate_external_userids(owner_userid: str) -> list[dict[str, Any]]:
    normalized_owner_userid = str(owner_userid or "").strip()
    if not normalized_owner_userid:
        raise ValueError("owner_userid is required")
    rows = get_db().execute(
        """
        WITH candidates AS (
            SELECT external_userid, 1 AS from_follow_relation, 0 AS from_contact_owner
            FROM wecom_external_contact_follow_users
            WHERE user_id = ?
              AND relation_status = 'active'
              AND COALESCE(external_userid, '') <> ''
            UNION ALL
            SELECT external_userid, 0 AS from_follow_relation, 1 AS from_contact_owner
            FROM contacts
            WHERE owner_userid = ?
              AND COALESCE(external_userid, '') <> ''
        )
        SELECT
            external_userid,
            MAX(from_follow_relation) AS from_follow_relation,
            MAX(from_contact_owner) AS from_contact_owner
        FROM candidates
        GROUP BY external_userid
        ORDER BY external_userid ASC
        """,
        (normalized_owner_userid, normalized_owner_userid),
    ).fetchall()
    return [
        {
            "external_userid": str(row.get("external_userid") or "").strip(),
            "from_follow_relation": bool(row.get("from_follow_relation")),
            "from_contact_owner": bool(row.get("from_contact_owner")),
        }
        for row in rows
        if str(row.get("external_userid") or "").strip()
    ]


def _get_owner_scoped_live_contact_tags(
    *,
    external_userid: str,
    owner_userid: str,
) -> dict[str, Any]:
    normalized_external_userid = str(external_userid or "").strip()
    normalized_owner_userid = str(owner_userid or "").strip()
    if not normalized_external_userid:
        return {
            "detail": {},
            "owner_userid": normalized_owner_userid,
            "owner_found": False,
            "tags": [],
            "tag_ids": [],
            "tag_names": [],
            "external_contact_name": "",
        }
    detail = _user_ops_contact_client().get_contact(normalized_external_userid)
    follow_users = detail.get("follow_user") or []
    owner_tags: list[dict[str, str]] = []
    owner_found = False
    for follow_user in follow_users:
        follow_user_userid = str((follow_user or {}).get("userid") or "").strip()
        if normalized_owner_userid and follow_user_userid != normalized_owner_userid:
            continue
        owner_found = True
        for tag in ((follow_user or {}).get("tags") or []):
            tag_id = str((tag or {}).get("tag_id") or (tag or {}).get("id") or "").strip()
            tag_name = str((tag or {}).get("tag_name") or (tag or {}).get("name") or "").strip()
            if not tag_id:
                continue
            owner_tags.append({"tag_id": tag_id, "tag_name": tag_name})
    deduped_tags: list[dict[str, str]] = []
    seen_tag_ids: set[str] = set()
    for tag in owner_tags:
        tag_id = str(tag.get("tag_id") or "").strip()
        if tag_id in seen_tag_ids:
            continue
        seen_tag_ids.add(tag_id)
        deduped_tags.append({"tag_id": tag_id, "tag_name": str(tag.get("tag_name") or "").strip()})
    return {
        "detail": detail,
        "owner_userid": normalized_owner_userid,
        "owner_found": owner_found,
        "tags": deduped_tags,
        "tag_ids": [str(item.get("tag_id") or "").strip() for item in deduped_tags],
        "tag_names": [str(item.get("tag_name") or "").strip() for item in deduped_tags if str(item.get("tag_name") or "").strip()],
        "external_contact_name": str(((detail.get("external_contact") or {}).get("name") or "")).strip(),
    }


def _persist_owner_scoped_live_contact_tags(
    *,
    external_userid: str,
    owner_userid: str,
    tags: list[dict[str, str]],
) -> None:
    normalized_external_userid = str(external_userid or "").strip()
    normalized_owner_userid = str(owner_userid or "").strip()
    if not normalized_external_userid or not normalized_owner_userid:
        return
    tag_ids = sorted({str(item.get("tag_id") or "").strip() for item in tags if str(item.get("tag_id") or "").strip()})
    tag_name_map = {
        str(item.get("tag_id") or "").strip(): str(item.get("tag_name") or "").strip()
        for item in tags
        if str(item.get("tag_id") or "").strip()
    }
    save_tag_snapshot(normalized_owner_userid, normalized_external_userid, tag_ids, tag_name_map)
    existing_tag_ids = _list_contact_tag_ids_for_user(normalized_external_userid, normalized_owner_userid)
    removable_tag_ids = [tag_id for tag_id in existing_tag_ids if tag_id not in tag_ids]
    remove_tag_snapshot(normalized_owner_userid, normalized_external_userid, removable_tag_ids)


def _plan_user_ops_lead_pool_member_upsert(
    *,
    mobile: str = "",
    external_userid: str = "",
    customer_name: str = "",
    owner_userid: str = "",
    is_wecom_added: bool | None = None,
    is_mobile_bound: bool | None = None,
    huangxiaocan_activation_state: str = "unknown",
    class_term_no: int | None = None,
    class_term_label: str = "",
    entry_source: str = "",
) -> dict[str, Any]:
    normalized_mobile = _normalize_mobile(mobile) if str(mobile or "").strip() else ""
    normalized_external_userid = str(external_userid or "").strip()
    if not normalized_mobile and not normalized_external_userid:
        raise ValueError("mobile or external_userid is required")

    normalized_entry_source = str(entry_source or "").strip() or "manual"
    normalized_customer_name = str(customer_name or "").strip()
    normalized_owner_userid = str(owner_userid or "").strip()
    normalized_class_term_label = str(class_term_label or "").strip()
    normalized_activation_state = _normalize_user_ops_lead_pool_activation_state(
        huangxiaocan_activation_state,
        allow_unknown=True,
    )
    matches = _list_user_ops_lead_pool_matches(mobile=normalized_mobile, external_userid=normalized_external_userid)
    target: dict[str, Any] | None = None
    if normalized_mobile:
        target = next((item for item in matches if item["mobile"] == normalized_mobile), None)
    if target is None and normalized_external_userid:
        target = next((item for item in matches if item["external_userid"] == normalized_external_userid), None)
    duplicate_ids = [item["id"] for item in matches if target is not None and item["id"] != target["id"]]

    merged = _serialize_user_ops_lead_pool_current_row(target or {})
    for item in matches:
        if not merged["mobile"] and item["mobile"]:
            merged["mobile"] = item["mobile"]
        if not merged["external_userid"] and item["external_userid"]:
            merged["external_userid"] = item["external_userid"]
        if not merged["customer_name"] and item["customer_name"]:
            merged["customer_name"] = item["customer_name"]
        if not merged["owner_userid"] and item["owner_userid"]:
            merged["owner_userid"] = item["owner_userid"]
        if not merged["first_entry_source"] and item["first_entry_source"]:
            merged["first_entry_source"] = item["first_entry_source"]
        if not merged["last_entry_source"] and item["last_entry_source"]:
            merged["last_entry_source"] = item["last_entry_source"]
        if merged["class_term_no"] is None and item["class_term_no"] is not None:
            merged["class_term_no"] = item["class_term_no"]
            merged["class_term_label"] = item["class_term_label"]
        if merged["huangxiaocan_activation_state"] == "unknown" and item["huangxiaocan_activation_state"] != "unknown":
            merged["huangxiaocan_activation_state"] = item["huangxiaocan_activation_state"]
        merged["is_wecom_added"] = bool(merged["is_wecom_added"] or item["is_wecom_added"])
        merged["is_mobile_bound"] = bool(merged["is_mobile_bound"] or item["is_mobile_bound"])

    if normalized_mobile:
        merged["mobile"] = normalized_mobile
    if normalized_external_userid:
        merged["external_userid"] = normalized_external_userid
    if normalized_customer_name:
        merged["customer_name"] = normalized_customer_name
    if normalized_owner_userid:
        merged["owner_userid"] = normalized_owner_userid
    if is_wecom_added is not None:
        merged["is_wecom_added"] = bool(is_wecom_added)
    if is_mobile_bound is not None:
        merged["is_mobile_bound"] = bool(is_mobile_bound)
    elif merged["mobile"] and merged["external_userid"]:
        merged["is_mobile_bound"] = True
    if normalized_activation_state != "unknown" or not target:
        merged["huangxiaocan_activation_state"] = normalized_activation_state
    if class_term_no is not None or normalized_class_term_label:
        merged["class_term_no"] = class_term_no
        merged["class_term_label"] = normalized_class_term_label
    if not merged["first_entry_source"]:
        merged["first_entry_source"] = normalized_entry_source
    merged["last_entry_source"] = normalized_entry_source

    before_payload = _serialize_user_ops_lead_pool_current_row(target) if target else {}
    action_type = "lead_pool_insert"
    if target is not None:
        action_type = "lead_pool_merge_upsert" if duplicate_ids else "lead_pool_update"
        if not duplicate_ids and before_payload == merged:
            action_type = "lead_pool_noop"
    return {
        "matches": matches,
        "target": target,
        "duplicate_ids": duplicate_ids,
        "before_payload": before_payload,
        "after_payload": merged,
        "action_type": action_type,
        "entry_source": normalized_entry_source,
    }


def _default_owner_class_term_backfill_entry_source(owner_userid: str) -> str:
    normalized_owner_userid = str(owner_userid or "").strip()
    override = get_owner_class_term_backfill_entry_source_override(normalized_owner_userid)
    if override:
        return override
    slug = re.sub(r"[^a-z0-9]+", "_", normalized_owner_userid.lower()).strip("_") or "owner"
    return f"{slug}_owner_backfill_20260329"


def _is_owner_backfill_invalid_test_candidate(external_userid: str) -> bool:
    normalized_external_userid = str(external_userid or "").strip().lower()
    return normalized_external_userid.startswith("wm_")


def backfill_owner_class_terms_into_lead_pool(
    *,
    owner_userid: str,
    class_term_min: int = 1,
    class_term_max: int = 5,
    dry_run: bool = True,
    operator: str = "",
    entry_source: str = "",
    sample_limit: int = 20,
    offset: int = 0,
    max_candidates: int | None = None,
) -> dict[str, Any]:
    started_at = time.time()
    normalized_owner_userid = str(owner_userid or "").strip()
    if not normalized_owner_userid:
        raise ValueError("owner_userid is required")
    normalized_class_term_min = int(class_term_min)
    normalized_class_term_max = int(class_term_max)
    if normalized_class_term_min <= 0 or normalized_class_term_max <= 0:
        raise ValueError("class_term_min and class_term_max must be positive integers")
    if normalized_class_term_min > normalized_class_term_max:
        raise ValueError("class_term_min must be <= class_term_max")

    actor = str(operator or _current_user_ops_operator()).strip() or "owner_class_term_backfill"
    normalized_entry_source = str(entry_source or "").strip() or _default_owner_class_term_backfill_entry_source(
        normalized_owner_userid
    )
    tag_payload = _user_ops_contact_client().list_external_contact_tags()
    mapping_scope = _resolve_owner_backfill_class_term_mappings(
        class_term_min=normalized_class_term_min,
        class_term_max=normalized_class_term_max,
        tag_payload=tag_payload,
    )
    effective_by_tag_id = dict(mapping_scope["effective_by_tag_id"])
    effective_by_tag_name = dict(mapping_scope["effective_by_tag_name"])
    candidates = _list_owner_backfill_candidate_external_userids(normalized_owner_userid)
    candidate_total = len(candidates)
    normalized_offset = max(int(offset or 0), 0)
    normalized_max_candidates = int(max_candidates) if max_candidates is not None else None
    if normalized_max_candidates is not None and normalized_max_candidates <= 0:
        raise ValueError("max_candidates must be positive when provided")
    selected_candidates = list(candidates[normalized_offset :]) if normalized_offset else list(candidates)
    if normalized_max_candidates is not None:
        selected_candidates = selected_candidates[:normalized_max_candidates]

    items: list[dict[str, Any]] = []
    invalid_test_candidate_samples: list[dict[str, Any]] = []
    owner_mismatch_samples: list[dict[str, Any]] = []
    class_term_distribution = {
        str(class_term_no): 0 for class_term_no in range(normalized_class_term_min, normalized_class_term_max + 1)
    }
    estimated_insert_total = 0
    estimated_update_total = 0
    estimated_mobile_bound_total = 0
    estimated_mobile_empty_total = 0
    single_match_total = 0
    conflict_total = 0
    skip_total = 0
    noop_total = 0
    error_total = 0
    invalid_test_candidate_total = 0
    owner_mismatch_total = 0
    processed_candidate_total = 0
    source_breakdown = {
        "follow_relation_only": 0,
        "contact_owner_only": 0,
        "both_sources": 0,
    }
    for candidate in selected_candidates:
        from_follow_relation = bool(candidate.get("from_follow_relation"))
        from_contact_owner = bool(candidate.get("from_contact_owner"))
        if from_follow_relation and from_contact_owner:
            source_breakdown["both_sources"] += 1
        elif from_follow_relation:
            source_breakdown["follow_relation_only"] += 1
        elif from_contact_owner:
            source_breakdown["contact_owner_only"] += 1

    if not dry_run:
        sync_user_ops_class_term_tag_definitions()

    for candidate in selected_candidates:
        processed_candidate_total += 1
        external_userid = str(candidate.get("external_userid") or "").strip()
        if not external_userid:
            continue
        target_owner_userid = normalized_owner_userid
        if processed_candidate_total % 100 == 0:
            owner_backfill_logger.info(
                "owner backfill progress owner_userid=%s processed=%s candidate_total=%s offset=%s max_candidates=%s",
                normalized_owner_userid,
                processed_candidate_total,
                candidate_total,
                normalized_offset,
                normalized_max_candidates if normalized_max_candidates is not None else "all",
            )
        if _is_owner_backfill_invalid_test_candidate(external_userid):
            invalid_test_candidate_total += 1
            invalid_item = {
                "external_userid": external_userid,
                "customer_name": "",
                "target_owner_userid": target_owner_userid,
                "resolved_owner_userid": target_owner_userid,
                "final_owner_userid": target_owner_userid,
                "owner_userid": target_owner_userid,
                "mobile": "",
                "is_mobile_bound": False,
                "matched_class_term_no": None,
                "matched_class_term_label": "",
                "decision": "skip",
                "decision_reason": "invalid_test_candidate",
            }
            items.append(invalid_item)
            if len(invalid_test_candidate_samples) < max(int(sample_limit or 20), 20):
                invalid_test_candidate_samples.append(dict(invalid_item))
            continue
        try:
            live_tag_payload = _get_owner_scoped_live_contact_tags(
                external_userid=external_userid,
                owner_userid=normalized_owner_userid,
            )
        except Exception as exc:
            error_total += 1
            items.append(
                {
                    "external_userid": external_userid,
                    "customer_name": "",
                    "target_owner_userid": target_owner_userid,
                    "resolved_owner_userid": target_owner_userid,
                    "final_owner_userid": target_owner_userid,
                    "owner_userid": target_owner_userid,
                    "mobile": "",
                    "is_mobile_bound": False,
                    "matched_class_term_no": None,
                    "matched_class_term_label": "",
                    "decision": "skip",
                    "decision_reason": f"tag_fetch_failed: {exc}",
                }
            )
            continue

        tags = list(live_tag_payload["tags"])
        matched_by_term_no: dict[int, dict[str, Any]] = {}
        for tag in tags:
            tag_id = str(tag.get("tag_id") or "").strip()
            tag_name = str(tag.get("tag_name") or "").strip()
            mapping = effective_by_tag_id.get(tag_id) or effective_by_tag_name.get(tag_name)
            if not mapping:
                continue
            matched_by_term_no[int(mapping["class_term_no"])] = {
                "class_term_no": int(mapping["class_term_no"]),
                "class_term_label": str(mapping.get("class_term_label") or "").strip(),
                "tag_id": tag_id,
                "tag_name": tag_name,
            }
        matched_terms = sorted(matched_by_term_no.values(), key=lambda item: int(item["class_term_no"]))
        identity = resolve_person_identity(external_userid=external_userid)
        customer_name = (
            str(identity.get("customer_name") or "").strip()
            or str(live_tag_payload.get("external_contact_name") or "").strip()
        )
        mobile = str(identity.get("mobile") or "").strip()
        is_mobile_bound = bool(identity.get("is_bound"))
        resolved_owner_userid = str(identity.get("owner_userid") or "").strip() or normalized_owner_userid
        final_owner_userid = target_owner_userid
        if resolved_owner_userid != target_owner_userid:
            owner_mismatch_total += 1
            mismatch_item = {
                "external_userid": external_userid,
                "customer_name": customer_name,
                "target_owner_userid": target_owner_userid,
                "resolved_owner_userid": resolved_owner_userid,
                "final_owner_userid": final_owner_userid,
                "mobile": mobile,
                "is_mobile_bound": is_mobile_bound,
            }
            if len(owner_mismatch_samples) < max(int(sample_limit or 20), 20):
                owner_mismatch_samples.append(dict(mismatch_item))

        if not matched_terms:
            skip_total += 1
            items.append(
                {
                    "external_userid": external_userid,
                    "customer_name": customer_name,
                    "target_owner_userid": target_owner_userid,
                    "resolved_owner_userid": resolved_owner_userid,
                    "final_owner_userid": final_owner_userid,
                    "owner_userid": final_owner_userid,
                    "mobile": mobile,
                    "is_mobile_bound": is_mobile_bound,
                    "matched_class_term_no": None,
                    "matched_class_term_label": "",
                    "decision": "skip",
                    "decision_reason": "no_match",
                    "tag_names": list(live_tag_payload["tag_names"]),
                }
            )
            continue

        if len(matched_terms) > 1:
            conflict_total += 1
            items.append(
                {
                    "external_userid": external_userid,
                    "customer_name": customer_name,
                    "target_owner_userid": target_owner_userid,
                    "resolved_owner_userid": resolved_owner_userid,
                    "final_owner_userid": final_owner_userid,
                    "owner_userid": final_owner_userid,
                    "mobile": mobile,
                    "is_mobile_bound": is_mobile_bound,
                    "matched_class_term_no": None,
                    "matched_class_term_label": "",
                    "decision": "conflict",
                    "decision_reason": "multiple_class_term_matches",
                    "matched_terms": matched_terms,
                    "tag_names": list(live_tag_payload["tag_names"]),
                }
            )
            continue

        single_match_total += 1
        matched = matched_terms[0]
        class_term_distribution[str(matched["class_term_no"])] += 1
        plan = _plan_user_ops_lead_pool_member_upsert(
            mobile=mobile,
            external_userid=str(identity.get("external_userid") or external_userid).strip(),
            customer_name=customer_name,
            owner_userid=final_owner_userid,
            is_wecom_added=True,
            is_mobile_bound=is_mobile_bound,
            class_term_no=int(matched["class_term_no"]),
            class_term_label=str(matched.get("class_term_label") or "").strip(),
            entry_source=normalized_entry_source,
        )
        decision = "insert"
        decision_reason = str(plan["action_type"])
        if plan["action_type"] == "lead_pool_insert":
            estimated_insert_total += 1
        elif plan["action_type"] == "lead_pool_noop":
            decision = "skip"
            decision_reason = "already_up_to_date"
            noop_total += 1
        else:
            decision = "update"
            estimated_update_total += 1
        if decision in {"insert", "update"}:
            if is_mobile_bound:
                estimated_mobile_bound_total += 1
            if not mobile:
                estimated_mobile_empty_total += 1
            if not dry_run:
                _persist_owner_scoped_live_contact_tags(
                    external_userid=external_userid,
                    owner_userid=normalized_owner_userid,
                    tags=tags,
                )
                upsert_user_ops_lead_pool_member(
                    mobile=mobile,
                    external_userid=str(identity.get("external_userid") or external_userid).strip(),
                    customer_name=customer_name,
                    owner_userid=final_owner_userid,
                    is_wecom_added=True,
                    is_mobile_bound=is_mobile_bound,
                    class_term_no=int(matched["class_term_no"]),
                    class_term_label=str(matched.get("class_term_label") or "").strip(),
                    entry_source=normalized_entry_source,
                    operator=actor,
                    remark=f"owner class-term backfill external_userid={external_userid}",
                )
        items.append(
            {
                "external_userid": external_userid,
                "customer_name": customer_name,
                "target_owner_userid": target_owner_userid,
                "resolved_owner_userid": resolved_owner_userid,
                "final_owner_userid": final_owner_userid,
                "owner_userid": final_owner_userid,
                "mobile": mobile,
                "is_mobile_bound": is_mobile_bound,
                "matched_class_term_no": int(matched["class_term_no"]),
                "matched_class_term_label": str(matched.get("class_term_label") or "").strip(),
                "decision": decision,
                "decision_reason": decision_reason,
                "tag_names": list(live_tag_payload["tag_names"]),
            }
        )

    decision_order = {"conflict": 0, "update": 1, "insert": 2, "skip": 3}
    sample_items = sorted(
        items,
        key=lambda item: (
            decision_order.get(str(item.get("decision") or "").strip(), 9),
            str(item.get("matched_class_term_no") or ""),
            str(item.get("external_userid") or ""),
        ),
    )[: max(int(sample_limit or 20), 20)]

    return {
        "ok": True,
        "owner_userid": normalized_owner_userid,
        "class_term_min": normalized_class_term_min,
        "class_term_max": normalized_class_term_max,
        "dry_run": bool(dry_run),
        "entry_source": normalized_entry_source,
        "candidate_total": candidate_total,
        "processed_candidate_total": processed_candidate_total,
        "offset": normalized_offset,
        "max_candidates": normalized_max_candidates,
        "matched_candidate_total": single_match_total + conflict_total,
        "single_match_total": single_match_total,
        "class_term_distribution": class_term_distribution,
        "conflict_total": conflict_total,
        "skip_total": skip_total,
        "noop_total": noop_total,
        "error_total": error_total,
        "invalid_test_candidate_total": invalid_test_candidate_total,
        "invalid_test_candidate_samples": invalid_test_candidate_samples,
        "owner_mismatch_total": owner_mismatch_total,
        "owner_mismatch_samples": owner_mismatch_samples,
        "estimated_insert_total": estimated_insert_total,
        "estimated_update_total": estimated_update_total,
        "estimated_mobile_bound_total": estimated_mobile_bound_total,
        "estimated_mobile_empty_total": estimated_mobile_empty_total,
        "term_2_mapping": mapping_scope["term_2_mapping"],
        "warnings": list(dict.fromkeys(mapping_scope["warnings"])),
        "elapsed_seconds": round(time.time() - started_at, 3),
        "source_breakdown": source_breakdown,
        "samples": sample_items,
        "applied_total": 0 if dry_run else estimated_insert_total + estimated_update_total,
    }


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


def _list_other_ownerids_with_scoped_tag_snapshots(
    *,
    external_userid: str,
    owner_userid: str,
    scoped_tag_ids: list[str],
) -> list[str]:
    if not scoped_tag_ids:
        return []
    placeholders = ", ".join("?" for _ in scoped_tag_ids)
    rows = get_db().execute(
        f"""
        SELECT DISTINCT userid
        FROM contact_tags
        WHERE external_userid = ?
          AND userid <> ?
          AND tag_id IN ({placeholders})
        ORDER BY userid ASC
        """,
        (external_userid, owner_userid, *scoped_tag_ids),
    ).fetchall()
    return [
        str(row.get("userid") or "").strip()
        for row in rows
        if str(row.get("userid") or "").strip()
    ]


def _sync_sidebar_lead_pool_class_term_tag(
    *,
    external_userid: str,
    owner_userid: str,
    class_term_no: int,
) -> dict[str, Any]:
    # Import lazily here to avoid widening the existing services <-> wecom_client
    # dependency loop while still making the hot path explicit and testable.
    from ...wecom_client import WeComClient

    normalized_external_userid = str(external_userid or "").strip()
    normalized_owner_userid = str(owner_userid or "").strip()
    if not normalized_external_userid:
        raise ValueError("external_userid is required")
    if not normalized_owner_userid:
        raise ValueError("owner_userid is required")

    mapping = _get_active_class_term_mapping_by_no(class_term_no)
    if not mapping:
        raise ValueError("class_term_no is invalid")

    target_tag_id = str(mapping.get("tag_id") or "").strip()
    target_tag_name = str(mapping.get("tag_name") or mapping.get("class_term_label") or "").strip()
    if not target_tag_id:
        raise ValueError("class term tag is not initialized")

    remove_tag_ids = sorted(
        {
            str(item.get("tag_id") or "").strip()
            for item in _list_active_class_term_mappings()
            if str(item.get("tag_id") or "").strip() and int(item.get("class_term_no") or 0) != int(mapping["class_term_no"])
        }
    )
    scoped_class_term_tag_ids = sorted(
        {
            str(item.get("tag_id") or "").strip()
            for item in _list_active_class_term_mappings()
            if str(item.get("tag_id") or "").strip()
        }
    )

    testing_applier = current_app.config.get("SIDEBAR_LEAD_POOL_TAG_APPLIER")
    if callable(testing_applier):
        testing_applier(
            external_userid=normalized_external_userid,
            owner_userid=normalized_owner_userid,
            add_tags=[target_tag_id],
            remove_tags=remove_tag_ids,
        )
    else:
        client = WeComClient.from_app()
        client.mark_external_contact_tags(
            external_userid=normalized_external_userid,
            follow_user_userid=normalized_owner_userid,
            add_tags=[target_tag_id],
            remove_tags=remove_tag_ids,
        )

    other_follow_user_userids = _list_other_ownerids_with_scoped_tag_snapshots(
        external_userid=normalized_external_userid,
        owner_userid=normalized_owner_userid,
        scoped_tag_ids=scoped_class_term_tag_ids,
    )
    for other_follow_user_userid in other_follow_user_userids:
        if callable(testing_applier):
            testing_applier(
                external_userid=normalized_external_userid,
                owner_userid=other_follow_user_userid,
                add_tags=[],
                remove_tags=scoped_class_term_tag_ids,
            )
        else:
            client.mark_external_contact_tags(
                external_userid=normalized_external_userid,
                follow_user_userid=other_follow_user_userid,
                add_tags=[],
                remove_tags=scoped_class_term_tag_ids,
            )

    save_tag_snapshot(
        normalized_owner_userid,
        normalized_external_userid,
        [target_tag_id],
        {target_tag_id: target_tag_name},
    )
    if remove_tag_ids:
        remove_tag_snapshot(normalized_owner_userid, normalized_external_userid, remove_tag_ids)
    remove_tag_snapshots_for_other_users(
        normalized_external_userid,
        [normalized_owner_userid],
        scoped_class_term_tag_ids,
    )
    return {
        "class_term_no": int(mapping["class_term_no"]),
        "class_term_label": str(mapping.get("class_term_label") or "").strip(),
        "tag_id": target_tag_id,
        "tag_name": target_tag_name,
        "removed_tag_ids": remove_tag_ids,
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


def _build_backfill_class_term_summary(
    *,
    owner_userid: str,
    dry_run: bool,
    tag_definition_sync: dict[str, Any],
    tag_refresh: dict[str, Any],
    preview_items: list[dict[str, Any]],
    mappings: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "owner_userid": owner_userid,
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


def _log_backfill_class_term_conflict(db, item: dict[str, Any], *, actor: str, now: str) -> None:
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


def _apply_backfill_class_term_update(
    db,
    item: dict[str, Any],
    *,
    matched: dict[str, Any],
    actor: str,
    now: str,
) -> None:
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
    summary = _build_backfill_class_term_summary(
        owner_userid=normalized_owner_userid,
        dry_run=bool(dry_run),
        tag_definition_sync=tag_definition_sync,
        tag_refresh=tag_refresh,
        preview_items=preview_items,
        mappings=mappings,
    )
    if dry_run:
        return {"ok": True, **summary}

    db = get_db()
    actor = str(operator or _current_user_ops_operator()).strip() or "admin_user_ops"
    applied_count = 0
    conflict_logged = 0
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for item in preview_items:
        if item["decision"] == "conflict":
            _log_backfill_class_term_conflict(db, item, actor=actor, now=now)
            conflict_logged += 1
            continue
        if item["decision"] != "update":
            continue
        matched = item["matched_terms"][0]
        _apply_backfill_class_term_update(db, item, matched=matched, actor=actor, now=now)
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
            USER_OPS_DEFERRED_JOB_TYPE_VERIFY_CLASS_TERM_TAG_AND_UPSERT_LEAD_POOL,
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
            USER_OPS_DEFERRED_JOB_TYPE_VERIFY_CLASS_TERM_TAG_AND_UPSERT_LEAD_POOL,
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


def _list_class_term_matches_for_external_contact(external_userid: str, owner_userid: str = "") -> dict[str, Any]:
    normalized_external_userid = str(external_userid or "").strip()
    normalized_owner_userid = str(owner_userid or "").strip()
    if not normalized_external_userid:
        return {"matched_terms": [], "tag_ids": [], "tag_names": []}
    rows = get_db().execute(
        """
        SELECT
            COALESCE(tags.tag_id, '') AS tag_id,
            COALESCE(tags.tag_name, '') AS tag_name,
            mappings.class_term_no,
            COALESCE(mappings.class_term_label, '') AS class_term_label
        FROM contact_tags tags
        LEFT JOIN class_term_tag_mapping mappings
          ON mappings.tag_id = tags.tag_id
         AND mappings.tag_group_name = ?
         AND mappings.is_active = ?
         AND COALESCE(mappings.tag_id, '') <> ''
        WHERE tags.external_userid = ?
          AND (? = '' OR tags.userid = ?)
        ORDER BY mappings.class_term_no ASC, tags.tag_id ASC, tags.tag_name ASC
        """,
        (
            USER_OPS_CLASS_TERM_TAG_GROUP_NAME,
            _db_bool(True),
            normalized_external_userid,
            normalized_owner_userid,
            normalized_owner_userid,
        ),
    ).fetchall()
    tag_ids: list[str] = []
    tag_names: list[str] = []
    matched_terms: list[dict[str, Any]] = []
    seen_term_keys: set[str] = set()
    for row in rows:
        tag_id = str(row.get("tag_id") or "").strip()
        tag_name = str(row.get("tag_name") or "").strip()
        if tag_id and tag_id not in tag_ids:
            tag_ids.append(tag_id)
        if tag_name and tag_name not in tag_names:
            tag_names.append(tag_name)
        if row.get("class_term_no") in (None, ""):
            continue
        key = f"{int(row['class_term_no'])}:{str(row.get('class_term_label') or '').strip()}:{tag_id}"
        if key in seen_term_keys:
            continue
        seen_term_keys.add(key)
        matched_terms.append(
            {
                "class_term_no": int(row["class_term_no"]),
                "class_term_label": str(row.get("class_term_label") or "").strip(),
                "tag_id": tag_id,
                "tag_name": tag_name,
            }
        )
    return {"matched_terms": matched_terms, "tag_ids": tag_ids, "tag_names": tag_names}


def _upsert_lead_pool_from_verified_class_term_tag(
    *,
    external_userid: str,
    owner_userid: str = "",
    operator: str = "",
    source_type: str = USER_OPS_DEFERRED_JOB_TYPE_VERIFY_CLASS_TERM_TAG_AND_UPSERT_LEAD_POOL,
) -> dict[str, Any]:
    normalized_external_userid = str(external_userid or "").strip()
    normalized_owner_userid = str(owner_userid or "").strip()
    actor = str(operator or _current_user_ops_operator()).strip() or "system_auto_assign"
    tag_definition_sync = sync_user_ops_class_term_tag_definitions()
    tag_refresh = refresh_user_ops_contact_tags_for_external_userid(
        external_userid=normalized_external_userid,
        owner_userid=normalized_owner_userid,
    )
    match_payload = _list_class_term_matches_for_external_contact(
        normalized_external_userid,
        normalized_owner_userid,
    )
    matched_terms = list(match_payload["matched_terms"])
    if len(matched_terms) > 1:
        return {
            "status": "conflict",
            "external_userid": normalized_external_userid,
            "owner_userid": normalized_owner_userid,
            "matched_terms": matched_terms,
            "tag_definition_sync": tag_definition_sync,
            "tag_refresh": tag_refresh,
        }
    if not matched_terms:
        return {
            "status": "skipped",
            "reason": "no_match",
            "external_userid": normalized_external_userid,
            "owner_userid": normalized_owner_userid,
            "matched_terms": [],
            "tag_definition_sync": tag_definition_sync,
            "tag_refresh": tag_refresh,
        }

    identity = resolve_person_identity(external_userid=normalized_external_userid)
    matched = matched_terms[0]
    result = upsert_user_ops_lead_pool_member(
        mobile=str(identity.get("mobile") or "").strip(),
        external_userid=str(identity.get("external_userid") or normalized_external_userid).strip(),
        customer_name=str(identity.get("customer_name") or "").strip(),
        owner_userid=str(identity.get("owner_userid") or normalized_owner_userid).strip(),
        is_wecom_added=bool(str(identity.get("external_userid") or normalized_external_userid).strip()),
        is_mobile_bound=bool(identity.get("is_bound")),
        class_term_no=matched.get("class_term_no"),
        class_term_label=str(matched.get("class_term_label") or "").strip(),
        entry_source=source_type,
        operator=actor,
        remark=f"verified class term tag external_userid={normalized_external_userid}",
    )
    return {
        "status": "success",
        "external_userid": normalized_external_userid,
        "owner_userid": normalized_owner_userid,
        "matched_terms": matched_terms,
        "tag_definition_sync": tag_definition_sync,
        "tag_refresh": tag_refresh,
        "member": result.get("member"),
        "action_type": result.get("action_type"),
    }


def _execute_auto_assign_class_term_job(job: dict[str, Any], *, operator: str) -> dict[str, Any]:
    normalized_owner_userid = str(job.get("owner_userid") or "").strip()
    normalized_external_userid = str(job.get("external_userid") or "").strip()
    actor = str(operator or "").strip() or "system_auto_assign"
    return _upsert_lead_pool_from_verified_class_term_tag(
        external_userid=normalized_external_userid,
        owner_userid=normalized_owner_userid,
        operator=actor,
        source_type=USER_OPS_DEFERRED_JOB_TYPE_VERIFY_CLASS_TERM_TAG_AND_UPSERT_LEAD_POOL,
    )


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


def _user_ops_owner_options() -> list[dict[str, str]]:
    rows = get_db().execute(
        """
        SELECT DISTINCT
            current.owner_userid,
            COALESCE(owner_map.display_name, '') AS display_name
        FROM user_ops_lead_pool_current current
        LEFT JOIN owner_role_map owner_map
          ON owner_map.userid = current.owner_userid
        WHERE current.owner_userid <> ''
        ORDER BY current.owner_userid ASC
        """
    ).fetchall()
    return [
        {
            "owner_userid": str(row.get("owner_userid") or "").strip(),
            "label": str(row.get("display_name") or "").strip() or str(row.get("owner_userid") or "").strip(),
        }
        for row in rows
    ]


def list_user_ops_pool(
    *,
    is_wecom_added: str = "",
    is_mobile_bound: str = "",
    huangxiaocan_activation_state: str = "",
    class_term_no: str = "",
    owner_userid: str = "",
    query: str = "",
) -> dict[str, Any]:
    _ensure_class_term_tag_mapping_seed()
    normalized_is_wecom_added = str(is_wecom_added or "").strip().lower()
    normalized_is_mobile_bound = str(is_mobile_bound or "").strip().lower()
    normalized_activation_state = str(huangxiaocan_activation_state or "").strip()
    normalized_class_term_no = str(class_term_no or "").strip()
    normalized_owner_userid = str(owner_userid or "").strip()
    normalized_query = str(query or "").strip()

    sql = """
        SELECT
            current.id,
            current.mobile,
            current.external_userid,
            current.customer_name,
            current.owner_userid,
            current.is_wecom_added,
            current.is_mobile_bound,
            current.huangxiaocan_activation_state,
            current.class_term_no,
            current.class_term_label,
            current.first_entry_source,
            current.last_entry_source,
            current.created_at,
            current.updated_at,
            COALESCE(owner_map.display_name, '') AS owner_display_name
        FROM user_ops_lead_pool_current current
        LEFT JOIN owner_role_map owner_map
          ON owner_map.userid = current.owner_userid
        WHERE 1 = 1
    """
    params: list[Any] = []
    if normalized_is_wecom_added in {"1", "true", "yes"}:
        sql += " AND current.is_wecom_added = ?"
        params.append(_db_bool(True))
    elif normalized_is_wecom_added in {"0", "false", "no"}:
        sql += " AND current.is_wecom_added = ?"
        params.append(_db_bool(False))
    if normalized_is_mobile_bound in {"1", "true", "yes"}:
        sql += " AND current.is_mobile_bound = ?"
        params.append(_db_bool(True))
    elif normalized_is_mobile_bound in {"0", "false", "no"}:
        sql += " AND current.is_mobile_bound = ?"
        params.append(_db_bool(False))
    if normalized_activation_state:
        sql += " AND current.huangxiaocan_activation_state = ?"
        params.append(normalized_activation_state)
    if normalized_class_term_no:
        sql += " AND CAST(COALESCE(current.class_term_no, 0) AS TEXT) = ?"
        params.append(normalized_class_term_no)
    if normalized_owner_userid:
        sql += " AND current.owner_userid = ?"
        params.append(normalized_owner_userid)
    if normalized_query:
        sql += " AND (current.mobile LIKE ? OR current.external_userid LIKE ? OR current.customer_name LIKE ?)"
        like_value = f"%{normalized_query}%"
        params.extend([like_value, like_value, like_value])
    sql += " ORDER BY current.updated_at DESC, current.id DESC"

    rows = get_db().execute(sql, tuple(params)).fetchall()
    items = [
        {
            "id": int(row["id"]),
            "mobile": str(row.get("mobile") or "").strip(),
            "external_userid": str(row.get("external_userid") or "").strip(),
            "customer_name": str(row.get("customer_name") or "").strip(),
            "owner_userid": str(row.get("owner_userid") or "").strip(),
            "owner_display_name": str(row.get("owner_display_name") or "").strip() or str(row.get("owner_userid") or "").strip(),
            "is_wecom_added": bool(row.get("is_wecom_added")),
            "is_mobile_bound": bool(row.get("is_mobile_bound")),
            "huangxiaocan_activation_state": str(row.get("huangxiaocan_activation_state") or "").strip() or "unknown",
            "huangxiaocan_activation_state_label": USER_OPS_LEAD_POOL_ACTIVATION_STATE_LABELS.get(
                str(row.get("huangxiaocan_activation_state") or "").strip() or "unknown",
                str(row.get("huangxiaocan_activation_state") or "").strip() or "unknown",
            ),
            "class_term_no": int(row["class_term_no"]) if row.get("class_term_no") not in (None, "") else None,
            "class_term_label": str(row.get("class_term_label") or "").strip(),
            "first_entry_source": str(row.get("first_entry_source") or "").strip(),
            "last_entry_source": str(row.get("last_entry_source") or "").strip(),
            "created_at": _stringify_db_timestamp(row.get("created_at")),
            "updated_at": _stringify_db_timestamp(row.get("updated_at")),
        }
        for row in rows
    ]
    return {
        "items": items,
        "total": len(items),
        "filters": {
            "is_wecom_added": normalized_is_wecom_added,
            "is_mobile_bound": normalized_is_mobile_bound,
            "huangxiaocan_activation_state": normalized_activation_state,
            "class_term_no": normalized_class_term_no,
            "owner_userid": normalized_owner_userid,
            "query": normalized_query,
        },
        "filter_options": {
            "activation_states": list(USER_OPS_LEAD_POOL_ACTIVATION_STATE_DEFINITIONS),
            "class_terms": _user_ops_class_term_options(),
            "owners": _user_ops_owner_options(),
        },
        "meta": {
            "data_generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
    }


def get_user_ops_overview() -> dict[str, Any]:
    rows = get_db().execute(
        """
        SELECT
            mobile,
            external_userid,
            is_wecom_added,
            is_mobile_bound,
            huangxiaocan_activation_state,
            class_term_no,
            class_term_label
        FROM user_ops_lead_pool_current
        """
    ).fetchall()
    total = len(rows)
    wecom_added_count = 0
    mobile_bound_count = 0
    activated_count = 0
    not_activated_count = 0
    unknown_count = 0
    for row in rows:
        if bool(row.get("is_wecom_added")):
            wecom_added_count += 1
        if bool(row.get("is_mobile_bound")):
            mobile_bound_count += 1
        activation_state = str(row.get("huangxiaocan_activation_state") or "").strip() or "unknown"
        if activation_state == "activated":
            activated_count += 1
        elif activation_state == "not_activated":
            not_activated_count += 1
        else:
            unknown_count += 1
    return {
        "lead_pool_total_count": total,
        "wecom_added_count": wecom_added_count,
        "wecom_not_added_count": total - wecom_added_count,
        "mobile_bound_count": mobile_bound_count,
        "mobile_unbound_count": total - mobile_bound_count,
        "huangxiaocan_activated_count": activated_count,
        "huangxiaocan_not_activated_count": not_activated_count,
        "huangxiaocan_unknown_count": unknown_count,
        "cards": [
            {"key": "lead_pool_total_count", "label": "引流品总数", "value": total},
            {"key": "wecom_added_count", "label": "已加微", "value": wecom_added_count},
            {"key": "wecom_not_added_count", "label": "未加微", "value": total - wecom_added_count},
            {"key": "mobile_bound_count", "label": "已绑手机号", "value": mobile_bound_count},
            {"key": "mobile_unbound_count", "label": "未绑手机号", "value": total - mobile_bound_count},
            {"key": "huangxiaocan_activated_count", "label": "黄小璨已激活", "value": activated_count},
            {"key": "huangxiaocan_not_activated_count", "label": "黄小璨未激活", "value": not_activated_count},
            {"key": "huangxiaocan_unknown_count", "label": "激活待录入", "value": unknown_count},
        ],
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def list_user_ops_history(limit: int = 100) -> dict[str, Any]:
    normalized_limit = max(1, min(int(limit or 100), 500))
    rows = get_db().execute(
        """
        SELECT
            id,
            mobile,
            external_userid,
            action_type,
            before_json,
            after_json,
            operator,
            source_type,
            remark,
            created_at
        FROM user_ops_lead_pool_history
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (normalized_limit,),
    ).fetchall()
    total_row = get_db().execute("SELECT COUNT(*) AS total FROM user_ops_lead_pool_history").fetchone()
    return {
        "items": [
            {
                "id": int(row["id"]),
                "mobile": str(row.get("mobile") or "").strip(),
                "external_userid": str(row.get("external_userid") or "").strip(),
                "action_type": str(row.get("action_type") or "").strip(),
                "before_json": str(row.get("before_json") or "").strip() or "{}",
                "after_json": str(row.get("after_json") or "").strip() or "{}",
                "operator": str(row.get("operator") or "").strip(),
                "source_type": str(row.get("source_type") or "").strip(),
                "remark": str(row.get("remark") or "").strip(),
                "created_at": _stringify_db_timestamp(row.get("created_at")),
            }
            for row in rows
        ],
        "total": int((total_row or {}).get("total") or 0),
        "limit": normalized_limit,
    }


def export_user_ops_pool(
    *,
    is_wecom_added: str = "",
    is_mobile_bound: str = "",
    huangxiaocan_activation_state: str = "",
    class_term_no: str = "",
    owner_userid: str = "",
    query: str = "",
) -> dict[str, Any]:
    result = list_user_ops_pool(
        is_wecom_added=is_wecom_added,
        is_mobile_bound=is_mobile_bound,
        huangxiaocan_activation_state=huangxiaocan_activation_state,
        class_term_no=class_term_no,
        owner_userid=owner_userid,
        query=query,
    )
    headers = ["手机号", "是否已加微", "是否已绑手机号", "班期", "黄小璨激活状态", "客户昵称", "external_userid", "跟进人", "首次入表来源", "最后入表来源", "更新时间"]
    rows = [
        [
            item.get("mobile", ""),
            "已加微" if item.get("is_wecom_added") else "未加微",
            "已绑定" if item.get("is_mobile_bound") else "未绑定",
            item.get("class_term_label", "") or (f"{item['class_term_no']}期" if item.get("class_term_no") else ""),
            item.get("huangxiaocan_activation_state_label", ""),
            item.get("customer_name", ""),
            item.get("external_userid", ""),
            item.get("owner_display_name", ""),
            item.get("first_entry_source", ""),
            item.get("last_entry_source", ""),
            item.get("updated_at", ""),
        ]
        for item in result["items"]
    ]
    return {
        "headers": headers,
        "rows": rows,
        "filename": f"user-ops-pool-{datetime.now().strftime('%Y%m%d%H%M%S')}.xls",
    }


def migrate_class_user_status_from_contact_tags() -> dict[str, Any]:
    rows = get_db().execute(
        """
        SELECT
            ct.external_userid,
            COALESCE(ct.userid, '') AS tag_userid,
            COALESCE(ct.tag_id, '') AS tag_id,
            COALESCE(ct.tag_name, '') AS tag_name,
            ct.created_at AS tag_created_at,
            COALESCE(c.customer_name, '') AS customer_name,
            COALESCE(c.owner_userid, '') AS owner_userid,
            COALESCE(p.mobile, '') AS mobile
        FROM contact_tags ct
        INNER JOIN signup_tag_rules signup_rules
          ON signup_rules.tag_id = ct.tag_id
         AND signup_rules.active = ?
        LEFT JOIN contacts c
          ON c.external_userid = ct.external_userid
        LEFT JOIN external_contact_bindings bindings
          ON bindings.external_userid = ct.external_userid
        LEFT JOIN people p
          ON p.id = bindings.person_id
        ORDER BY ct.created_at DESC, ct.id DESC
        """,
        (True if get_db_backend() == "postgres" else 1,),
    ).fetchall()
    by_external: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        external_userid = str(row.get("external_userid") or "").strip()
        if not external_userid:
            continue
        by_external.setdefault(external_userid, []).append(dict(row))

    migrated = 0
    for external_userid, candidates in by_external.items():
        candidates.sort(
            key=lambda item: (
                str(item.get("tag_created_at") or ""),
                str(item.get("tag_id") or ""),
            ),
            reverse=True,
        )
        chosen = candidates[0]
        signup_status = str(get_signup_status_definition_by_tag_name(str(chosen.get("tag_name") or "").strip()).get("signup_status") if get_signup_status_definition_by_tag_name(str(chosen.get("tag_name") or "").strip()) else "").strip()
        definition = get_class_user_status_definition(signup_status)
        if not definition:
            continue
        existing = get_class_user_status_current(external_userid) or {}
        customer_name = str(chosen.get("customer_name") or "").strip()
        owner_userid = str(chosen.get("tag_userid") or "").strip() or str(chosen.get("owner_userid") or "").strip()
        mobile = str(chosen.get("mobile") or "").strip()
        upsert_class_user_status_current(
            external_userid=external_userid,
            signup_status=signup_status,
            signup_label_name=definition["label"],
            customer_name_snapshot=customer_name,
            owner_userid_snapshot=owner_userid,
            mobile_snapshot=mobile,
            set_by_userid=owner_userid,
            set_at=str(chosen.get("tag_created_at") or "").strip(),
            wecom_tag_sync_status="migrated",
            wecom_tag_sync_error="",
        )
        append_class_user_status_history(
            external_userid=external_userid,
            old_signup_status=str(existing.get("signup_status") or "").strip(),
            new_signup_status=signup_status,
            old_label_name=str(existing.get("signup_label_name") or "").strip(),
            new_label_name=definition["label"],
            customer_name_snapshot=customer_name,
            owner_userid_snapshot=owner_userid,
            mobile_snapshot=mobile,
            set_by_userid=owner_userid,
            set_at=str(chosen.get("tag_created_at") or "").strip(),
            wecom_tag_sync_status="migrated",
            wecom_tag_sync_error="",
        )
        migrated += 1
    return {"migrated_count": migrated}


def apply_class_user_status_change(
    *,
    external_userid: str,
    signup_status: str,
    set_by_userid: str,
    customer_name_snapshot: str,
    owner_userid_snapshot: str,
    mobile_snapshot: str,
) -> dict[str, Any]:
    definition = get_class_user_status_definition(signup_status)
    if not definition:
        raise ValueError("signup_status is invalid")
    existing = get_class_user_status_current(external_userid) or {}
    upsert_class_user_status_current(
        external_userid=external_userid,
        signup_status=signup_status,
        signup_label_name=definition["label"],
        customer_name_snapshot=customer_name_snapshot,
        owner_userid_snapshot=owner_userid_snapshot,
        mobile_snapshot=mobile_snapshot,
        set_by_userid=set_by_userid,
        wecom_tag_sync_status="pending",
        wecom_tag_sync_error="",
    )
    append_class_user_status_history(
        external_userid=external_userid,
        old_signup_status=str(existing.get("signup_status") or "").strip(),
        new_signup_status=signup_status,
        old_label_name=str(existing.get("signup_label_name") or "").strip(),
        new_label_name=definition["label"],
        customer_name_snapshot=customer_name_snapshot,
        owner_userid_snapshot=owner_userid_snapshot,
        mobile_snapshot=mobile_snapshot,
        set_by_userid=set_by_userid,
        wecom_tag_sync_status="pending",
        wecom_tag_sync_error="",
    )
    return get_class_user_status_current(external_userid) or {}

def _normalize_user_ops_lead_pool_activation_state(value: str, *, allow_unknown: bool = True) -> str:
    normalized = str(value or "").strip()
    if not normalized and allow_unknown:
        return "unknown"
    if normalized not in USER_OPS_LEAD_POOL_ACTIVATION_STATES:
        raise ValueError("huangxiaocan_activation_state must be unknown, activated, or not_activated")
    if normalized == "unknown" and not allow_unknown:
        raise ValueError("activation_state must be activated or not_activated")
    return normalized


def _serialize_user_ops_lead_pool_current_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "mobile": str(row.get("mobile") or "").strip(),
        "external_userid": str(row.get("external_userid") or "").strip(),
        "customer_name": str(row.get("customer_name") or "").strip(),
        "owner_userid": str(row.get("owner_userid") or "").strip(),
        "is_wecom_added": bool(row.get("is_wecom_added")),
        "is_mobile_bound": bool(row.get("is_mobile_bound")),
        "huangxiaocan_activation_state": _normalize_user_ops_lead_pool_activation_state(
            str(row.get("huangxiaocan_activation_state") or "").strip(),
            allow_unknown=True,
        ),
        "class_term_no": int(row["class_term_no"]) if row.get("class_term_no") not in (None, "") else None,
        "class_term_label": str(row.get("class_term_label") or "").strip(),
        "first_entry_source": str(row.get("first_entry_source") or "").strip(),
        "last_entry_source": str(row.get("last_entry_source") or "").strip(),
    }


def _get_user_ops_lead_pool_current_row_by_id(row_id: int) -> dict[str, Any] | None:
    row = get_db().execute(
        """
        SELECT
            id,
            mobile,
            external_userid,
            customer_name,
            owner_userid,
            is_wecom_added,
            is_mobile_bound,
            huangxiaocan_activation_state,
            class_term_no,
            class_term_label,
            first_entry_source,
            last_entry_source,
            created_at,
            updated_at
        FROM user_ops_lead_pool_current
        WHERE id = ?
        LIMIT 1
        """,
        (row_id,),
    ).fetchone()
    if not row:
        return None
    payload = _serialize_user_ops_lead_pool_current_row(dict(row))
    payload["id"] = row["id"]
    payload["created_at"] = _stringify_db_timestamp(row.get("created_at"))
    payload["updated_at"] = _stringify_db_timestamp(row.get("updated_at"))
    return payload


def _list_user_ops_lead_pool_matches(*, mobile: str, external_userid: str) -> list[dict[str, Any]]:
    conditions: list[str] = []
    params: list[Any] = []
    if mobile:
        conditions.append("mobile = ?")
        params.append(mobile)
    if external_userid:
        conditions.append("external_userid = ?")
        params.append(external_userid)
    if not conditions:
        return []
    rows = get_db().execute(
        f"""
        SELECT
            id,
            mobile,
            external_userid,
            customer_name,
            owner_userid,
            is_wecom_added,
            is_mobile_bound,
            huangxiaocan_activation_state,
            class_term_no,
            class_term_label,
            first_entry_source,
            last_entry_source,
            created_at,
            updated_at
        FROM user_ops_lead_pool_current
        WHERE {" OR ".join(conditions)}
        ORDER BY id ASC
        """,
        tuple(params),
    ).fetchall()
    items: list[dict[str, Any]] = []
    for row in rows:
        item = _serialize_user_ops_lead_pool_current_row(dict(row))
        item["id"] = row["id"]
        item["created_at"] = _stringify_db_timestamp(row.get("created_at"))
        item["updated_at"] = _stringify_db_timestamp(row.get("updated_at"))
        items.append(item)
    return items


def write_user_ops_lead_pool_history(
    *,
    mobile: str = "",
    external_userid: str = "",
    action_type: str,
    source_type: str,
    operator: str = "",
    before_payload: dict[str, Any] | None = None,
    after_payload: dict[str, Any] | None = None,
    remark: str = "",
) -> None:
    get_db().execute(
        """
        INSERT INTO user_ops_lead_pool_history (
            mobile, external_userid, action_type, source_type, operator, before_json, after_json, remark, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (
            str(mobile or "").strip(),
            str(external_userid or "").strip(),
            str(action_type or "").strip(),
            str(source_type or "").strip(),
            str(operator or _current_user_ops_operator()).strip() or "system",
            json.dumps(before_payload or {}, ensure_ascii=False),
            json.dumps(after_payload or {}, ensure_ascii=False),
            str(remark or "").strip(),
        ),
    )


def _insert_user_ops_lead_pool_member_row(db, payload: dict[str, Any]) -> int:
    db.execute(
        """
        INSERT INTO user_ops_lead_pool_current (
            mobile, external_userid, customer_name, owner_userid, is_wecom_added, is_mobile_bound,
            huangxiaocan_activation_state, class_term_no, class_term_label, first_entry_source, last_entry_source,
            created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """,
        (
            payload["mobile"],
            payload["external_userid"],
            payload["customer_name"],
            payload["owner_userid"],
            _db_bool(bool(payload["is_wecom_added"])),
            _db_bool(bool(payload["is_mobile_bound"])),
            payload["huangxiaocan_activation_state"],
            payload["class_term_no"],
            payload["class_term_label"],
            payload["first_entry_source"],
            payload["last_entry_source"],
        ),
    )
    if get_db_backend() != "postgres":
        return int(db.execute("SELECT last_insert_rowid() AS id").fetchone()["id"])
    row = db.execute(
        """
        SELECT id
        FROM user_ops_lead_pool_current
        WHERE mobile = ? OR external_userid = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (payload["mobile"], payload["external_userid"]),
    ).fetchone()
    return int(row["id"])


def _update_user_ops_lead_pool_member_row(db, row_id: int, payload: dict[str, Any]) -> None:
    db.execute(
        """
        UPDATE user_ops_lead_pool_current
        SET
            mobile = ?,
            external_userid = ?,
            customer_name = ?,
            owner_userid = ?,
            is_wecom_added = ?,
            is_mobile_bound = ?,
            huangxiaocan_activation_state = ?,
            class_term_no = ?,
            class_term_label = ?,
            first_entry_source = ?,
            last_entry_source = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            payload["mobile"],
            payload["external_userid"],
            payload["customer_name"],
            payload["owner_userid"],
            _db_bool(bool(payload["is_wecom_added"])),
            _db_bool(bool(payload["is_mobile_bound"])),
            payload["huangxiaocan_activation_state"],
            payload["class_term_no"],
            payload["class_term_label"],
            payload["first_entry_source"],
            payload["last_entry_source"],
            row_id,
        ),
    )


def _delete_user_ops_lead_pool_duplicate_rows(db, duplicate_ids: list[int]) -> None:
    if not duplicate_ids:
        return
    placeholders = ", ".join("?" for _ in duplicate_ids)
    db.execute(
        f"DELETE FROM user_ops_lead_pool_current WHERE id IN ({placeholders})",
        tuple(duplicate_ids),
    )


def _user_ops_lead_pool_history_remark(remark: str, duplicate_ids: list[int]) -> str:
    normalized_remark = str(remark or "").strip()
    if normalized_remark:
        return normalized_remark
    if duplicate_ids:
        return f"merged duplicate ids: {', '.join(str(item) for item in duplicate_ids)}"
    return ""


def upsert_user_ops_lead_pool_member(
    *,
    mobile: str = "",
    external_userid: str = "",
    customer_name: str = "",
    owner_userid: str = "",
    is_wecom_added: bool | None = None,
    is_mobile_bound: bool | None = None,
    huangxiaocan_activation_state: str = "unknown",
    class_term_no: int | None = None,
    class_term_label: str = "",
    entry_source: str = "",
    operator: str = "",
    remark: str = "",
) -> dict[str, Any]:
    plan = _plan_user_ops_lead_pool_member_upsert(
        mobile=mobile,
        external_userid=external_userid,
        customer_name=customer_name,
        owner_userid=owner_userid,
        is_wecom_added=is_wecom_added,
        is_mobile_bound=is_mobile_bound,
        huangxiaocan_activation_state=huangxiaocan_activation_state,
        class_term_no=class_term_no,
        class_term_label=class_term_label,
        entry_source=entry_source,
    )
    if plan["action_type"] == "lead_pool_noop":
        return {
            "ok": True,
            "action_type": plan["action_type"],
            "member": plan["target"],
            "merged_duplicate_ids": plan["duplicate_ids"],
        }

    merged = plan["after_payload"]
    db = get_db()
    target = plan["target"]
    if target is None:
        row_id = _insert_user_ops_lead_pool_member_row(db, merged)
    else:
        row_id = int(target["id"])
        _update_user_ops_lead_pool_member_row(db, row_id, merged)
    _delete_user_ops_lead_pool_duplicate_rows(db, plan["duplicate_ids"])

    current = _get_user_ops_lead_pool_current_row_by_id(row_id)
    write_user_ops_lead_pool_history(
        mobile=(current or {}).get("mobile", merged["mobile"]),
        external_userid=(current or {}).get("external_userid", merged["external_userid"]),
        action_type=plan["action_type"],
        source_type=plan["entry_source"],
        operator=operator,
        before_payload=plan["before_payload"],
        after_payload=_serialize_user_ops_lead_pool_current_row(current or merged),
        remark=_user_ops_lead_pool_history_remark(remark, plan["duplicate_ids"]),
    )
    db.commit()
    return {
        "ok": True,
        "action_type": plan["action_type"],
        "member": current,
        "merged_duplicate_ids": plan["duplicate_ids"],
    }


def apply_user_ops_huangxiaocan_activation_source_to_existing_member(
    *,
    mobile: str,
    activation_state: str,
    operator: str = "",
    source_type: str = "huangxiaocan_activation_source",
    remark: str = "",
) -> dict[str, Any]:
    normalized_mobile = _normalize_mobile(mobile)
    normalized_state = _normalize_user_ops_lead_pool_activation_state(activation_state, allow_unknown=False)
    current_row = get_db().execute(
        """
        SELECT id
        FROM user_ops_lead_pool_current
        WHERE mobile = ?
        LIMIT 1
        """,
        (normalized_mobile,),
    ).fetchone()
    if not current_row:
        get_db().commit()
        return {"ok": True, "matched_member": False, "created_member": False, "member": None}

    member = _get_user_ops_lead_pool_current_row_by_id(int(current_row["id"])) or {}
    before_payload = _serialize_user_ops_lead_pool_current_row(member)
    get_db().execute(
        """
        UPDATE user_ops_lead_pool_current
        SET huangxiaocan_activation_state = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (normalized_state, int(current_row["id"])),
    )
    current = _get_user_ops_lead_pool_current_row_by_id(int(current_row["id"]))
    write_user_ops_lead_pool_history(
        mobile=normalized_mobile,
        external_userid=(current or {}).get("external_userid", ""),
        action_type="lead_pool_activation_patch",
        source_type=source_type,
        operator=operator,
        before_payload=before_payload,
        after_payload=_serialize_user_ops_lead_pool_current_row(current or {}),
        remark=remark,
    )
    get_db().commit()
    return {"ok": True, "matched_member": True, "created_member": False, "member": current}


def upsert_user_ops_huangxiaocan_activation_source(
    *,
    mobile: str,
    activation_state: str,
    import_batch_id: str = "",
    created_by: str = "",
    is_active: bool = True,
) -> dict[str, Any]:
    normalized_mobile = _normalize_mobile(mobile)
    normalized_state = _normalize_user_ops_lead_pool_activation_state(activation_state, allow_unknown=False)
    operator = str(created_by or _current_user_ops_operator()).strip() or "admin_user_ops"
    db = get_db()
    existing = db.execute(
        """
        SELECT id, mobile, activation_state, import_batch_id, created_by, is_active
        FROM user_ops_huangxiaocan_activation_source
        WHERE mobile = ?
        LIMIT 1
        """,
        (normalized_mobile,),
    ).fetchone()
    db.execute(
        """
        INSERT INTO user_ops_huangxiaocan_activation_source (
            mobile, activation_state, import_batch_id, created_by, is_active, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT(mobile) DO UPDATE SET
            activation_state = excluded.activation_state,
            import_batch_id = excluded.import_batch_id,
            created_by = excluded.created_by,
            is_active = excluded.is_active,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            normalized_mobile,
            normalized_state,
            str(import_batch_id or "").strip(),
            operator,
            _db_bool(bool(is_active)),
        ),
    )
    apply_payload = apply_user_ops_huangxiaocan_activation_source_to_existing_member(
        mobile=normalized_mobile,
        activation_state=normalized_state,
        operator=operator,
        source_type="huangxiaocan_activation_import",
        remark="patched existing lead member from activation source",
    )
    source_row = db.execute(
        """
        SELECT mobile, activation_state, import_batch_id, created_by, is_active, created_at, updated_at
        FROM user_ops_huangxiaocan_activation_source
        WHERE mobile = ?
        LIMIT 1
        """,
        (normalized_mobile,),
    ).fetchone()
    db.commit()
    return {
        "ok": True,
        "action_type": "activation_source_insert" if existing is None else "activation_source_update",
        "matched_member": bool(apply_payload.get("matched_member")),
        "created_member": False,
        "source": {
            "mobile": normalized_mobile,
            "activation_state": normalized_state,
            "import_batch_id": str((source_row or {}).get("import_batch_id") or "").strip(),
            "created_by": str((source_row or {}).get("created_by") or "").strip(),
            "is_active": bool((source_row or {}).get("is_active")),
        },
        "member": apply_payload.get("member"),
    }


def _current_user_ops_operator() -> str:
    if has_request_context():
        for key in ("userid", "user_id", "username"):
            value = str(session.get(key) or "").strip()
            if value:
                return value
    return "admin_user_ops"


def _is_experience_lead_header(value: str) -> bool:
    normalized = str(value or "").strip().lower()
    return normalized in {"手机号", "手机", "mobile", "phone", "手机号列表"}


def _is_activation_status_header(value: str) -> bool:
    normalized = str(value or "").strip().lower().replace(" ", "")
    return normalized in {
        "手机号,状态",
        "手机号,状态,备注",
        "mobile,status",
        "mobile,status,remark",
    }


def _collect_experience_lead_mobiles(raw_values: list[str]) -> dict[str, Any]:
    valid_rows: list[str] = []
    invalid_rows: list[str] = []
    seen: set[str] = set()
    unique_mobiles: list[str] = []
    total_rows = 0
    for raw_value in raw_values:
        candidate = str(raw_value or "").strip()
        if not candidate or _is_experience_lead_header(candidate):
            continue
        total_rows += 1
        try:
            mobile = _normalize_mobile(candidate)
        except ValueError:
            invalid_rows.append(candidate)
            continue
        valid_rows.append(mobile)
        if mobile not in seen:
            seen.add(mobile)
            unique_mobiles.append(mobile)
    return {
        "total_rows": total_rows,
        "valid_rows": valid_rows,
        "unique_mobiles": unique_mobiles,
        "invalid_rows": invalid_rows,
        "duplicate_count": max(0, len(valid_rows) - len(unique_mobiles)),
    }


def _parse_experience_leads_from_text(pasted_text: str) -> dict[str, Any]:
    raw_values = [item for item in re.split(r"[\s,，;；]+", str(pasted_text or "").strip()) if item.strip()]
    result = _collect_experience_lead_mobiles(raw_values)
    result["input_mode"] = "pasted_text"
    return result


def _extract_xlsx_shared_strings(archive: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    namespace = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    values: list[str] = []
    for item in root.findall("a:si", namespace):
        values.append("".join(item.itertext()).strip())
    return values


def _parse_xlsx_rows(file_bytes: bytes) -> list[list[str]]:
    with ZipFile(BytesIO(file_bytes)) as archive:
        shared_strings = _extract_xlsx_shared_strings(archive)
        worksheet_name = "xl/worksheets/sheet1.xml"
        if worksheet_name not in archive.namelist():
            worksheet_candidates = sorted(name for name in archive.namelist() if name.startswith("xl/worksheets/") and name.endswith(".xml"))
            if not worksheet_candidates:
                return []
            worksheet_name = worksheet_candidates[0]
        root = ET.fromstring(archive.read(worksheet_name))
        namespace = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        rows: list[str] = []
        for row in root.findall(".//a:sheetData/a:row", namespace):
            cell_values: list[str] = []
            for cell in row.findall("a:c", namespace):
                cell_type = str(cell.attrib.get("t") or "").strip()
                if cell_type == "inlineStr":
                    text_value = "".join(cell.itertext()).strip()
                else:
                    value_node = cell.find("a:v", namespace)
                    text_value = str(value_node.text or "").strip() if value_node is not None else ""
                    if cell_type == "s" and text_value.isdigit():
                        index = int(text_value)
                        text_value = shared_strings[index] if 0 <= index < len(shared_strings) else ""
                cell_values.append(text_value)
            if any(value.strip() for value in cell_values):
                rows.append(cell_values)
        return rows


def _parse_experience_leads_from_file(*, file_name: str, file_bytes: bytes) -> dict[str, Any]:
    normalized_name = str(file_name or "").strip().lower()
    if normalized_name.endswith(".xlsx"):
        raw_values = [row[0] for row in _parse_xlsx_rows(file_bytes) if row]
    else:
        try:
            decoded = file_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("only .xlsx or utf-8 text files are supported") from exc
        raw_values = [item for item in re.split(r"[\r\n,，;；\t ]+", decoded) if item.strip()]
    result = _collect_experience_lead_mobiles(raw_values)
    result["input_mode"] = "file"
    result["file_name"] = str(file_name or "").strip()
    return result


def _is_class_term_header(value: str) -> bool:
    normalized = str(value or "").strip().lower().replace(" ", "")
    return normalized in {
        "手机号,班期",
        "mobile,classterm",
        "mobile,class_term",
        "phone,classterm",
    }


def _normalize_class_term_value(value: str) -> str:
    class_term_label = str(value or "").strip()
    if not class_term_label:
        raise ValueError("class_term is required")
    return class_term_label


def _extract_class_term_no(class_term_label: str) -> int | None:
    matched = re.fullmatch(r"(\d+)\s*期?", str(class_term_label or "").strip())
    if not matched:
        return None
    return int(matched.group(1))


def _parse_class_term_import_line(line: str) -> tuple[str, str, int | None]:
    parts = [item.strip() for item in re.split(r"[,\t，]+", str(line or "").strip())]
    parts = [item for item in parts if item]
    if not parts:
        raise ValueError("class term row is empty")
    mobile = _normalize_mobile(parts[0])
    if len(parts) < 2:
        raise ValueError("class_term is required")
    class_term_label = _normalize_class_term_value(parts[1])
    return mobile, class_term_label, _extract_class_term_no(class_term_label)


def _parse_class_term_source_from_text(pasted_text: str) -> dict[str, Any]:
    lines = [line.strip() for line in str(pasted_text or "").splitlines() if line.strip()]
    rows: list[dict[str, Any]] = []
    invalid_rows: list[str] = []
    total_rows = 0
    for line in lines:
        if _is_class_term_header(line):
            continue
        total_rows += 1
        try:
            mobile, class_term_label, class_term_no = _parse_class_term_import_line(line)
        except ValueError:
            invalid_rows.append(line)
            continue
        rows.append(
            {
                "mobile": mobile,
                "class_term_label": class_term_label,
                "class_term_no": class_term_no,
            }
        )
    return {
        "input_mode": "pasted_text",
        "total_rows": total_rows,
        "rows": rows,
        "invalid_rows": invalid_rows,
    }


def _parse_class_term_source_from_file(*, file_name: str, file_bytes: bytes) -> dict[str, Any]:
    normalized_name = str(file_name or "").strip().lower()
    if normalized_name.endswith(".xlsx"):
        raw_rows = _parse_xlsx_rows(file_bytes)
        lines = []
        for row in raw_rows:
            normalized_row = [str(item or "").strip() for item in row[:2]]
            if not any(normalized_row):
                continue
            lines.append(",".join(normalized_row))
    else:
        try:
            decoded = file_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("only .xlsx or utf-8 text files are supported") from exc
        lines = [line.strip() for line in decoded.splitlines() if line.strip()]
    result = _parse_class_term_source_from_text("\n".join(lines))
    result["input_mode"] = "file"
    result["file_name"] = str(file_name or "").strip()
    return result


def _normalize_activation_status_value(value: str) -> str:
    normalized = str(value or "").strip()
    mapping = {
        "未激活": "not_activated",
        "已激活": "activated",
        "激活": "activated",
    }
    result = mapping.get(normalized)
    if not result:
        raise ValueError(f"activation_status is invalid: {normalized} (allowed: 已激活, 未激活)")
    return result


def _normalize_legacy_user_ops_activation_for_lead_pool(value: str) -> str:
    normalized = str(value or "").strip()
    if normalized == "activated":
        return "activated"
    if normalized == "not_activated":
        return "not_activated"
    return "unknown"


def _resolve_lead_pool_binding_by_mobile(mobile: str) -> dict[str, Any]:
    normalized_mobile = _normalize_mobile(mobile)
    row = get_db().execute(
        """
        SELECT
            p.mobile,
            COALESCE(bindings.external_userid, '') AS external_userid,
            COALESCE(c.customer_name, status.customer_name_snapshot, '') AS customer_name,
            COALESCE(c.owner_userid, status.owner_userid_snapshot, '') AS owner_userid,
            bindings.person_id
        FROM people p
        LEFT JOIN external_contact_bindings bindings
          ON bindings.person_id = p.id
        LEFT JOIN contacts c
          ON c.external_userid = bindings.external_userid
        LEFT JOIN class_user_status_current status
          ON status.external_userid = bindings.external_userid
        WHERE p.mobile = ?
        ORDER BY COALESCE(bindings.updated_at, bindings.created_at) DESC, bindings.external_userid ASC
        LIMIT 1
        """,
        (normalized_mobile,),
    ).fetchone()
    external_userid = str((row or {}).get("external_userid") or "").strip()
    is_mobile_bound = bool(row and row.get("person_id") is not None and external_userid)
    return {
        "mobile": normalized_mobile,
        "external_userid": external_userid,
        "customer_name": str((row or {}).get("customer_name") or "").strip(),
        "owner_userid": str((row or {}).get("owner_userid") or "").strip(),
        "is_mobile_bound": is_mobile_bound,
        "is_wecom_added": bool(external_userid),
    }


def _parse_activation_status_line(line: str) -> tuple[str, str, str]:
    parts = [item.strip() for item in re.split(r"[,\t，]+", str(line or "").strip())]
    parts = [item for item in parts if item]
    if not parts:
        raise ValueError("activation row is empty")
    mobile = _normalize_mobile(parts[0])
    if len(parts) < 2:
        raise ValueError("activation_status is required")
    if len(parts) > 2:
        raise ValueError("activation_status rows must contain only mobile and activation_status")
    activation_status = _normalize_activation_status_value(parts[1])
    return mobile, activation_status, ""


def _parse_activation_status_from_text(pasted_text: str) -> dict[str, Any]:
    lines = [line.strip() for line in str(pasted_text or "").splitlines() if line.strip()]
    rows: list[dict[str, str]] = []
    invalid_rows: list[str] = []
    total_rows = 0
    for line in lines:
        if _is_activation_status_header(line):
            continue
        total_rows += 1
        try:
            mobile, activation_status, activation_remark = _parse_activation_status_line(line)
        except ValueError as exc:
            invalid_rows.append(f"{line} -> {exc}")
            continue
        rows.append(
            {
                "mobile": mobile,
                "activation_status": activation_status,
                "activation_remark": activation_remark,
            }
        )
    return {
        "input_mode": "pasted_text",
        "total_rows": total_rows,
        "rows": rows,
        "invalid_rows": invalid_rows,
    }


def _parse_activation_status_from_file(*, file_name: str, file_bytes: bytes) -> dict[str, Any]:
    normalized_name = str(file_name or "").strip().lower()
    if normalized_name.endswith(".xlsx"):
        raw_rows = _parse_xlsx_rows(file_bytes)
        lines = []
        for row in raw_rows:
            normalized_row = [str(item or "").strip() for item in row[:2]]
            if not any(normalized_row):
                continue
            lines.append(",".join(normalized_row))
    else:
        try:
            decoded = file_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("only .xlsx or utf-8 text files are supported") from exc
        lines = [line.strip() for line in decoded.splitlines() if line.strip()]
    result = _parse_activation_status_from_text("\n".join(lines))
    result["input_mode"] = "file"
    result["file_name"] = str(file_name or "").strip()
    return result


def _create_user_ops_import_batch(
    *,
    import_type: str,
    file_name: str,
    total_rows: int,
    success_rows: int,
    failed_rows: int,
    error_summary: str,
    created_by: str,
) -> int:
    row = get_db().execute(
        """
        INSERT INTO user_ops_import_batches (
            import_type, file_name, total_rows, success_rows, failed_rows, error_summary, created_by, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        RETURNING id
        """,
        (
            import_type,
            file_name,
            int(total_rows),
            int(success_rows),
            int(failed_rows),
            error_summary,
            created_by,
        ),
    ).fetchone()
    return int(row["id"])


def import_experience_leads(
    *,
    pasted_text: str = "",
    file_name: str = "",
    file_bytes: bytes | None = None,
    created_by: str = "",
) -> dict[str, Any]:
    operator = str(created_by or _current_user_ops_operator()).strip() or "admin_user_ops"
    if file_bytes is not None:
        parsed = _parse_experience_leads_from_file(file_name=file_name, file_bytes=file_bytes)
    else:
        parsed = _parse_experience_leads_from_text(pasted_text)

    unique_mobiles = list(parsed["unique_mobiles"])
    invalid_rows = list(parsed["invalid_rows"])
    total_rows = int(parsed["total_rows"])
    success_rows = len(parsed["valid_rows"])
    failed_rows = len(invalid_rows)
    duplicate_count = int(parsed["duplicate_count"])

    if not unique_mobiles:
        raise ValueError("no valid mobile numbers found")

    error_summary_parts: list[str] = []
    if invalid_rows:
        preview = " / ".join(invalid_rows[:5])
        suffix = " ..." if len(invalid_rows) > 5 else ""
        error_summary_parts.append(f"invalid: {preview}{suffix}")
    if duplicate_count:
        error_summary_parts.append(f"duplicates: {duplicate_count}")
    error_summary = "; ".join(error_summary_parts)

    db = get_db()
    batch_id = _create_user_ops_import_batch(
        import_type="experience_leads",
        file_name=str(parsed.get("file_name") or file_name or parsed.get("input_mode") or "").strip(),
        total_rows=total_rows,
        success_rows=success_rows,
        failed_rows=failed_rows,
        error_summary=error_summary,
        created_by=operator,
    )

    for mobile in unique_mobiles:
        existing = db.execute(
            """
            SELECT id, mobile, source_type, import_batch_id, created_by, is_active
            FROM user_ops_experience_leads
            WHERE mobile = ?
            LIMIT 1
            """,
            (mobile,),
        ).fetchone()
        db.execute(
            """
            INSERT INTO user_ops_experience_leads (
                mobile, source_type, import_batch_id, created_by, is_active, created_at, updated_at
            )
            VALUES (?, 'experience_import', ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(mobile) DO UPDATE SET
                source_type = excluded.source_type,
                import_batch_id = excluded.import_batch_id,
                created_by = excluded.created_by,
                is_active = excluded.is_active,
                updated_at = CURRENT_TIMESTAMP
            """,
            (mobile, batch_id, operator, _db_bool(True)),
        )
        db.execute(
            """
            INSERT INTO user_ops_pool_history (
                pool_id, mobile, external_userid, action_type, old_payload_json, new_payload_json, operator, source_type, created_at
            )
            VALUES (?, ?, '', ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                None,
                mobile,
                "experience_import_source_upsert",
                json.dumps(dict(existing or {}), ensure_ascii=False),
                json.dumps(
                    {
                        "mobile": mobile,
                        "source_type": "experience_import",
                        "import_batch_id": batch_id,
                        "created_by": operator,
                        "is_active": True,
                    },
                    ensure_ascii=False,
                ),
                operator,
                "experience_import",
            ),
        )
    db.commit()

    return {
        "ok": True,
        "import_type": "experience_leads",
        "input_mode": str(parsed.get("input_mode") or "").strip(),
        "batch_id": batch_id,
        "total_rows": total_rows,
        "success_rows": success_rows,
        "failed_rows": failed_rows,
        "duplicate_count": duplicate_count,
        "unique_mobile_count": len(unique_mobiles),
        "invalid_rows": invalid_rows,
        "reload": {"mode": "legacy_pool_disabled", "triggered": False},
    }


def _dedupe_user_ops_import_rows_by_mobile(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    deduped_by_mobile: dict[str, dict[str, Any]] = {}
    for row in rows:
        deduped_by_mobile[str(row["mobile"])] = row
    unique_rows = list(deduped_by_mobile.values())
    duplicate_count = max(0, len(rows) - len(unique_rows))
    return unique_rows, duplicate_count


def import_mobile_class_term_source(
    *,
    pasted_text: str = "",
    file_name: str = "",
    file_bytes: bytes | None = None,
    created_by: str = "",
) -> dict[str, Any]:
    # Phone-centric rule: mobile is the only import key, the last row wins per
    # mobile, and imports incrementally upsert the new lead pool instead of
    # rebuilding the legacy pool projection.
    operator = str(created_by or _current_user_ops_operator()).strip() or "admin_user_ops"
    if file_bytes is not None:
        parsed = _parse_class_term_source_from_file(file_name=file_name, file_bytes=file_bytes)
    else:
        parsed = _parse_class_term_source_from_text(pasted_text)

    rows = list(parsed["rows"])
    invalid_rows = list(parsed["invalid_rows"])
    total_rows = int(parsed["total_rows"])
    failed_rows = len(invalid_rows)

    if not rows:
        raise ValueError("no valid class term rows found")

    unique_rows, duplicate_count = _dedupe_user_ops_import_rows_by_mobile(rows)

    error_summary_parts: list[str] = []
    if invalid_rows:
        preview = " / ".join(invalid_rows[:5])
        suffix = " ..." if len(invalid_rows) > 5 else ""
        error_summary_parts.append(f"invalid: {preview}{suffix}")
    if duplicate_count:
        error_summary_parts.append(f"duplicates: {duplicate_count}")
    error_summary = "; ".join(error_summary_parts)

    db = get_db()
    batch_id = _create_user_ops_import_batch(
        import_type="class_term_source",
        file_name=str(parsed.get("file_name") or file_name or parsed.get("input_mode") or "").strip(),
        total_rows=total_rows,
        success_rows=len(rows),
        failed_rows=failed_rows,
        error_summary=error_summary,
        created_by=operator,
    )

    applied_count = 0
    bound_count = 0
    members: list[dict[str, Any]] = []
    for row in unique_rows:
        mobile = str(row["mobile"] or "").strip()
        resolved = _resolve_lead_pool_binding_by_mobile(mobile)
        result = upsert_user_ops_lead_pool_member(
            mobile=mobile,
            external_userid=resolved["external_userid"],
            customer_name=resolved["customer_name"],
            owner_userid=resolved["owner_userid"],
            is_wecom_added=resolved["is_wecom_added"],
            is_mobile_bound=resolved["is_mobile_bound"],
            class_term_no=row["class_term_no"],
            class_term_label=row["class_term_label"],
            entry_source="student_import",
            operator=operator,
            remark=f"class term import batch={batch_id}",
        )
        members.append(dict(result.get("member") or {}))
        applied_count += 1
        if bool((result.get("member") or {}).get("is_wecom_added")):
            bound_count += 1

    return {
        "ok": True,
        "import_type": "class_term_source",
        "input_mode": str(parsed.get("input_mode") or "").strip(),
        "batch_id": batch_id,
        "total_rows": total_rows,
        "success_rows": len(rows),
        "failed_rows": failed_rows,
        "duplicate_count": duplicate_count,
        "unique_mobile_count": len(unique_rows),
        "invalid_rows": invalid_rows,
        "applied_count": applied_count,
        "bound_count": bound_count,
        "members": members,
        "reload": {"mode": "incremental", "triggered": False},
    }


def import_activation_status_source(
    *,
    pasted_text: str = "",
    file_name: str = "",
    file_bytes: bytes | None = None,
    created_by: str = "",
) -> dict[str, Any]:
    # Phone-centric rule: activation import stays independent from class-term
    # import, keyed only by mobile. It writes the activation source first and
    # only patches already existing lead members.
    operator = str(created_by or _current_user_ops_operator()).strip() or "admin_user_ops"
    if file_bytes is not None:
        parsed = _parse_activation_status_from_file(file_name=file_name, file_bytes=file_bytes)
    else:
        parsed = _parse_activation_status_from_text(pasted_text)

    rows = list(parsed["rows"])
    invalid_rows = list(parsed["invalid_rows"])
    total_rows = int(parsed["total_rows"])
    failed_rows = len(invalid_rows)

    if invalid_rows:
        preview = " / ".join(invalid_rows[:5])
        suffix = " ..." if len(invalid_rows) > 5 else ""
        raise ValueError(f"invalid activation rows: {preview}{suffix}")
    if not rows:
        raise ValueError("no valid activation rows found")

    unique_rows, duplicate_count = _dedupe_user_ops_import_rows_by_mobile(rows)
    error_summary_parts: list[str] = []
    if invalid_rows:
        preview = " / ".join(invalid_rows[:5])
        suffix = " ..." if len(invalid_rows) > 5 else ""
        error_summary_parts.append(f"invalid: {preview}{suffix}")
    if duplicate_count:
        error_summary_parts.append(f"duplicates: {duplicate_count}")
    error_summary = "; ".join(error_summary_parts)

    db = get_db()
    batch_id = _create_user_ops_import_batch(
        import_type="activation_status",
        file_name=str(parsed.get("file_name") or file_name or parsed.get("input_mode") or "").strip(),
        total_rows=total_rows,
        success_rows=len(rows),
        failed_rows=failed_rows,
        error_summary=error_summary,
        created_by=operator,
    )

    matched_member_count = 0
    members: list[dict[str, Any]] = []
    for row in unique_rows:
        result = upsert_user_ops_huangxiaocan_activation_source(
            mobile=str(row["mobile"]),
            activation_state=str(row["activation_status"]),
            import_batch_id=str(batch_id),
            created_by=operator,
            is_active=True,
        )
        if result["matched_member"]:
            matched_member_count += 1
            if result.get("member"):
                members.append(dict(result["member"]))
    return {
        "ok": True,
        "import_type": "activation_status",
        "input_mode": str(parsed.get("input_mode") or "").strip(),
        "batch_id": batch_id,
        "total_rows": total_rows,
        "success_rows": len(rows),
        "failed_rows": failed_rows,
        "duplicate_count": duplicate_count,
        "unique_mobile_count": len(unique_rows),
        "invalid_rows": invalid_rows,
        "matched_member_count": matched_member_count,
        "created_member_count": 0,
        "members": members,
        "reload": {"mode": "incremental", "triggered": False},
    }


def migrate_legacy_user_ops_pool_to_lead_pool(*, operator: str = "") -> dict[str, Any]:
    rows = get_db().execute(
        """
        SELECT
            mobile,
            external_userid,
            customer_name,
            owner_userid,
            is_wecom_bound,
            activation_status,
            class_term_no,
            class_term_label,
            source_type
        FROM user_ops_pool_current
        WHERE class_term_no IS NOT NULL
           OR (
                COALESCE(mobile, '') <> ''
                AND COALESCE(source_type, '') = 'experience_import'
                AND COALESCE(is_wecom_bound, 0) = ?
           )
        ORDER BY id ASC
        """,
        (_db_bool(False),),
    ).fetchall()
    normalized_operator = str(operator or _current_user_ops_operator()).strip() or "admin_user_ops"
    migrated_count = 0
    for row in rows:
        upsert_user_ops_lead_pool_member(
            mobile=str(row.get("mobile") or "").strip(),
            external_userid=str(row.get("external_userid") or "").strip(),
            customer_name=str(row.get("customer_name") or "").strip(),
            owner_userid=str(row.get("owner_userid") or "").strip(),
            is_wecom_added=bool(str(row.get("external_userid") or "").strip()),
            is_mobile_bound=bool(row.get("is_wecom_bound")),
            huangxiaocan_activation_state=_normalize_legacy_user_ops_activation_for_lead_pool(
                str(row.get("activation_status") or "").strip()
            ),
            class_term_no=int(row["class_term_no"]) if row.get("class_term_no") not in (None, "") else None,
            class_term_label=str(row.get("class_term_label") or "").strip(),
            entry_source="legacy_pool_migration",
            operator=normalized_operator,
            remark=f"migrated from legacy source_type={str(row.get('source_type') or '').strip()}",
        )
        migrated_count += 1
    return {"ok": True, "migrated_count": migrated_count}


def _extract_third_party_user_id(payload: Any) -> str:
    if isinstance(payload, dict):
        for key in ("third_party_user_id", "user_id", "id"):
            value = str(payload.get(key) or "").strip()
            if value:
                return value
        for key in ("data", "result", "user", "person"):
            value = _extract_third_party_user_id(payload.get(key))
            if value:
                return value
    elif isinstance(payload, list):
        for item in payload:
            value = _extract_third_party_user_id(item)
            if value:
                return value
    return ""


def _resolve_third_party_user_id_by_mobile(mobile: str) -> str:
    existing = current_app.config.get("SIDEBAR_THIRD_PARTY_RESOLVER")
    if callable(existing):
        resolved = str(existing(mobile) or "").strip()
        if resolved:
            return resolved

    api_url = str(current_app.config.get("SIDEBAR_THIRD_PARTY_API_URL", "") or "").strip()
    api_token = str(current_app.config.get("SIDEBAR_THIRD_PARTY_API_TOKEN", "") or "").strip()
    timeout = int(current_app.config.get("SIDEBAR_THIRD_PARTY_TIMEOUT_SECONDS", 10))
    if api_url:
        headers = {"Content-Type": "application/json"}
        if api_token:
            headers["Authorization"] = f"Bearer {api_token}"
        try:
            response = requests.post(
                api_url,
                json={"mobile": mobile},
                headers=headers,
                timeout=timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise ThirdPartyUserSyncError(f"third-party sync request failed: {exc}") from exc
        except ValueError as exc:
            raise ThirdPartyUserSyncError("third-party sync returned invalid JSON") from exc

        third_party_user_id = _extract_third_party_user_id(payload)
        if third_party_user_id:
            return third_party_user_id
        raise ThirdPartyUserSyncError("third-party sync response missing third_party_user_id")

    if current_app.testing or current_app.config.get("DEBUG"):
        return f"mocktp_{mobile}"

    raise ThirdPartyUserSyncError("third-party resolver is not configured")


def _sidebar_contact_profile(external_userid: str, owner_userid: str = "") -> dict[str, str]:
    normalized_external_userid = str(external_userid or "").strip()
    normalized_owner_userid = str(owner_userid or "").strip()
    if not normalized_external_userid:
        return {
            "customer_name": "",
            "remark": "",
            "display_name": "",
            "owner_userid": normalized_owner_userid,
        }

    db = get_db()
    contact = db.execute(
        """
        SELECT external_userid, COALESCE(customer_name, '') AS customer_name, COALESCE(owner_userid, '') AS owner_userid,
               COALESCE(remark, '') AS remark
        FROM contacts
        WHERE external_userid = ?
        LIMIT 1
        """,
        (normalized_external_userid,),
    ).fetchone()
    if contact:
        fallback_owner_userid = str(contact.get("owner_userid") or "").strip()
        customer_name = str(contact.get("customer_name") or "").strip()
        remark = str(contact.get("remark") or "").strip()
    else:
        fallback_owner_userid = ""
        customer_name = ""
        remark = ""

    if not remark:
        follow_user = None
        if normalized_owner_userid:
            follow_user = db.execute(
                """
                SELECT COALESCE(remark, '') AS remark
                FROM wecom_external_contact_follow_users
                WHERE corp_id = ? AND external_userid = ? AND user_id = ?
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                (current_app.config.get("WECOM_CORP_ID", ""), normalized_external_userid, normalized_owner_userid),
            ).fetchone()
        if not follow_user:
            follow_user = db.execute(
                """
                SELECT COALESCE(remark, '') AS remark
                FROM wecom_external_contact_follow_users
                WHERE corp_id = ? AND external_userid = ?
                ORDER BY is_primary DESC, updated_at DESC, id DESC
                LIMIT 1
                """,
                (current_app.config.get("WECOM_CORP_ID", ""), normalized_external_userid),
            ).fetchone()
        remark = str((follow_user or {}).get("remark") or "").strip()

    display_name = customer_name or remark
    if not display_name:
        suffix = normalized_external_userid[-6:] if len(normalized_external_userid) > 6 else normalized_external_userid
        display_name = f"客户 {suffix}" if suffix else "当前客户"

    return {
        "customer_name": customer_name,
        "remark": remark,
        "display_name": display_name,
        "owner_userid": normalized_owner_userid or fallback_owner_userid,
    }


def _resolve_binding_owner_userid(external_userid: str, owner_userid: str = "") -> str:
    profile = _sidebar_contact_profile(external_userid, owner_userid)
    resolved_owner_userid = str(profile.get("owner_userid") or "").strip()
    if resolved_owner_userid:
        return resolved_owner_userid
    row = get_db().execute(
        """
        SELECT COALESCE(follow_user_userid, '') AS follow_user_userid
        FROM wecom_external_contact_identity_map
        WHERE corp_id = ? AND external_userid = ?
        ORDER BY updated_at DESC, id DESC
        LIMIT 1
        """,
        (current_app.config.get("WECOM_CORP_ID", ""), str(external_userid or "").strip()),
    ).fetchone()
    return str((row or {}).get("follow_user_userid") or "").strip()


def _select_user_ops_lead_pool_member_for_sidebar(
    *,
    external_userid: str,
    mobile: str = "",
    owner_userid: str = "",
) -> dict[str, Any] | None:
    normalized_external_userid = str(external_userid or "").strip()
    normalized_mobile = str(mobile or "").strip()
    normalized_owner_userid = str(owner_userid or "").strip()
    matches = _list_user_ops_lead_pool_matches(mobile=normalized_mobile, external_userid=normalized_external_userid)
    if normalized_owner_userid:
        matches = [item for item in matches if str(item.get("owner_userid") or "").strip() == normalized_owner_userid]
    if normalized_mobile:
        target = next((item for item in matches if item["mobile"] == normalized_mobile), None)
        if target is not None:
            return target
    if normalized_external_userid:
        target = next((item for item in matches if item["external_userid"] == normalized_external_userid), None)
        if target is not None:
            return target
    return matches[0] if matches else None


def get_sidebar_lead_pool_status(*, external_userid: str, owner_userid: str = "") -> dict[str, Any]:
    normalized_external_userid = str(external_userid or "").strip()
    if not normalized_external_userid:
        raise ValueError("external_userid is required")
    normalized_requested_owner_userid = str(owner_userid or "").strip()
    normalized_owner_userid = normalized_requested_owner_userid or _resolve_binding_owner_userid(
        normalized_external_userid,
        owner_userid,
    )
    binding = get_contact_binding_status(normalized_external_userid, normalized_owner_userid)
    member = _select_user_ops_lead_pool_member_for_sidebar(
        external_userid=normalized_external_userid,
        mobile=str(binding.get("mobile") or "").strip(),
        owner_userid=normalized_owner_userid,
    ) or {}
    match_payload = _list_class_term_matches_for_external_contact(
        normalized_external_userid,
        normalized_owner_userid,
    )
    matched_terms = list(match_payload["matched_terms"])
    current_class_term_no = member.get("class_term_no")
    current_class_term_label = str(member.get("class_term_label") or "").strip()
    if current_class_term_no in (None, "") and len(matched_terms) == 1:
        current_class_term_no = int(matched_terms[0]["class_term_no"])
        current_class_term_label = str(matched_terms[0].get("class_term_label") or "").strip()

    return {
        "external_userid": normalized_external_userid,
        "owner_userid": str(binding.get("owner_userid") or normalized_owner_userid).strip(),
        "display_name": str(binding.get("display_name") or "").strip(),
        "customer_name": str(binding.get("customer_name") or "").strip(),
        "mobile": str(binding.get("mobile") or "").strip(),
        "is_wecom_added": True,
        "is_mobile_bound": bool(binding.get("is_bound")),
        "class_term_options": _user_ops_class_term_options(),
        "current_class_term_no": int(current_class_term_no) if current_class_term_no not in (None, "") else None,
        "current_class_term_label": current_class_term_label,
        "current_tag_names": list(match_payload["tag_names"]),
        "member": member,
    }


def upsert_sidebar_lead_pool_class_term(
    *,
    external_userid: str,
    owner_userid: str = "",
    class_term_no: int,
    operator: str = "",
) -> dict[str, Any]:
    normalized_external_userid = str(external_userid or "").strip()
    if not normalized_external_userid:
        raise ValueError("external_userid is required")
    normalized_requested_owner_userid = str(owner_userid or "").strip()
    normalized_owner_userid = normalized_requested_owner_userid or _resolve_binding_owner_userid(
        normalized_external_userid,
        owner_userid,
    )
    actor = str(operator or _current_user_ops_operator()).strip() or "sidebar_class_term"
    mapping = _get_active_class_term_mapping_by_no(class_term_no)
    if not mapping:
        raise ValueError("class_term_no is invalid")

    binding = get_contact_binding_status(normalized_external_userid, normalized_owner_userid)
    upsert_result = upsert_user_ops_lead_pool_member(
        mobile=str(binding.get("mobile") or "").strip(),
        external_userid=normalized_external_userid,
        customer_name=str(binding.get("customer_name") or "").strip(),
        owner_userid=normalized_owner_userid,
        is_wecom_added=True,
        is_mobile_bound=bool(binding.get("is_bound")),
        class_term_no=int(mapping["class_term_no"]),
        class_term_label=str(mapping.get("class_term_label") or "").strip(),
        entry_source="sidebar_class_term",
        operator=actor,
        remark=f"sidebar class term set external_userid={normalized_external_userid}",
    )
    tag_result = _sync_sidebar_lead_pool_class_term_tag(
        external_userid=normalized_external_userid,
        owner_userid=normalized_owner_userid,
        class_term_no=int(mapping["class_term_no"]),
    )
    return {
        "ok": True,
        "member": upsert_result.get("member"),
        "action_type": upsert_result.get("action_type"),
        "tag_sync": tag_result,
    }


def _merge_lead_pool_after_mobile_bind(
    *,
    external_userid: str,
    owner_userid: str,
    mobile: str,
    operator: str = "",
) -> dict[str, Any]:
    normalized_external_userid = str(external_userid or "").strip()
    normalized_owner_userid = str(owner_userid or "").strip()
    normalized_mobile = _normalize_mobile(mobile)
    actor = str(operator or _current_user_ops_operator()).strip() or "sidebar_bind_mobile"

    matches = _list_user_ops_lead_pool_matches(mobile=normalized_mobile, external_userid=normalized_external_userid)
    external_row = next((item for item in matches if item["external_userid"] == normalized_external_userid), None)
    mobile_row = next((item for item in matches if item["mobile"] == normalized_mobile), None)
    profile = _sidebar_contact_profile(normalized_external_userid, normalized_owner_userid)
    merge_before_payload = _serialize_user_ops_lead_pool_current_row(external_row or {})
    merged_class_term_no = (
        mobile_row.get("class_term_no")
        if mobile_row and mobile_row.get("class_term_no") not in (None, "")
        else (external_row.get("class_term_no") if external_row else None)
    )
    merged_class_term_label = (
        str(mobile_row.get("class_term_label") or "").strip()
        if mobile_row and str(mobile_row.get("class_term_label") or "").strip()
        else str((external_row or {}).get("class_term_label") or "").strip()
    )
    merged_activation_state = (
        str(mobile_row.get("huangxiaocan_activation_state") or "").strip()
        if mobile_row and str(mobile_row.get("huangxiaocan_activation_state") or "").strip() not in ("", "unknown")
        else str((external_row or {}).get("huangxiaocan_activation_state") or "").strip()
    )
    merge_required = bool(
        external_row
        and (
            not str(external_row.get("mobile") or "").strip()
            or (mobile_row is not None and int(mobile_row["id"]) != int(external_row["id"]))
        )
    )

    if (
        external_row is not None
        and mobile_row is not None
        and int(external_row["id"]) != int(mobile_row["id"])
    ):
        get_db().execute(
            "DELETE FROM user_ops_lead_pool_current WHERE id = ?",
            (int(external_row["id"]),),
        )
        get_db().commit()

    result = upsert_user_ops_lead_pool_member(
        mobile=normalized_mobile,
        external_userid=normalized_external_userid,
        customer_name=str(profile.get("customer_name") or "").strip(),
        owner_userid=normalized_owner_userid,
        is_wecom_added=True,
        is_mobile_bound=True,
        huangxiaocan_activation_state=merged_activation_state or "unknown",
        class_term_no=int(merged_class_term_no) if merged_class_term_no not in (None, "") else None,
        class_term_label=merged_class_term_label,
        entry_source="mobile_bind",
        operator=actor,
        remark=f"bind mobile external_userid={normalized_external_userid}",
    )
    member = dict(result.get("member") or {})
    if merge_required:
        write_user_ops_lead_pool_history(
            mobile=str(member.get("mobile") or normalized_mobile).strip(),
            external_userid=str(member.get("external_userid") or normalized_external_userid).strip(),
            action_type="mobile_bind_merge",
            source_type="mobile_bind",
            operator=actor,
            before_payload=merge_before_payload,
            after_payload=_serialize_user_ops_lead_pool_current_row(member),
            remark=(
                f"canonical mobile={normalized_mobile}; "
                f"absorbed_external_row_id={int(external_row['id']) if external_row else 0}; "
                f"mobile_row_id={int(mobile_row['id']) if mobile_row else 0}"
            ),
        )
        get_db().commit()
    return {
        "ok": True,
        "merge_applied": merge_required,
        "member": member,
        "merged_duplicate_ids": list(result.get("merged_duplicate_ids") or []),
        "action_type": result.get("action_type"),
    }
