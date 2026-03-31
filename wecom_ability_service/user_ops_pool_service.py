
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from .class_user_service import (
    append_class_user_status_history,
    get_class_user_status_current,
    get_class_user_status_definition,
    upsert_class_user_status_current,
)
from .db import get_db, get_db_backend
from .services import (
    USER_OPS_CLASS_TERM_TAG_GROUP_NAME,
    USER_OPS_ACTIVATION_STATUS_DEFINITIONS,
    USER_OPS_ACTIVATION_STATUS_LABELS,
    USER_OPS_CURRENT_STATUS_DEFINITIONS,
    USER_OPS_CURRENT_STATUS_LABELS,
    get_signup_status_definition_by_tag_name,
)
from .user_ops_shared import (
    _db_bool,
    _ensure_class_term_tag_mapping_seed,
    _normalize_user_ops_current_status,
    _stringify_db_timestamp,
    _user_ops_merge_key,
    _user_ops_status_rank,
)

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
    current_status = _normalize_user_ops_current_status(str(row.get("signup_status") or "").strip())
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
    current_status = _normalize_user_ops_current_status(str(row.get("signup_status") or "").strip())
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
    if _user_ops_status_rank(candidate["current_status"]) >= _user_ops_status_rank(existing["current_status"]):
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

def _user_ops_owner_options() -> list[dict[str, str]]:
    rows = get_db().execute(
        """
        SELECT DISTINCT
            current.owner_userid,
            COALESCE(owner_map.display_name, '') AS display_name
        FROM user_ops_pool_current current
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
    current_status: str = "",
    is_wecom_bound: str = "",
    activation_status: str = "",
    class_term_no: str = "",
    owner_userid: str = "",
    query: str = "",
) -> dict[str, Any]:
    _ensure_class_term_tag_mapping_seed()
    normalized_current_status = str(current_status or "").strip()
    normalized_bound = str(is_wecom_bound or "").strip().lower()
    normalized_activation_status = str(activation_status or "").strip()
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
            current.current_status,
            current.is_wecom_bound,
            current.activation_status,
            current.activation_remark,
            current.class_term_no,
            current.class_term_label,
            current.source_type,
            current.created_at,
            current.updated_at,
            COALESCE(owner_map.display_name, '') AS owner_display_name
        FROM user_ops_pool_current current
        LEFT JOIN owner_role_map owner_map
          ON owner_map.userid = current.owner_userid
        WHERE 1 = 1
    """
    params: list[Any] = []
    if normalized_current_status:
        sql += " AND current.current_status = ?"
        params.append(normalized_current_status)
    if normalized_bound in {"1", "true", "yes"}:
        sql += " AND current.is_wecom_bound = ?"
        params.append(_db_bool(True))
    elif normalized_bound in {"0", "false", "no"}:
        sql += " AND current.is_wecom_bound = ?"
        params.append(_db_bool(False))
    if normalized_activation_status:
        sql += " AND current.activation_status = ?"
        params.append(normalized_activation_status)
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
            "current_status": str(row.get("current_status") or "").strip(),
            "current_status_label": USER_OPS_CURRENT_STATUS_LABELS.get(str(row.get("current_status") or "").strip(), str(row.get("current_status") or "").strip()),
            "is_wecom_bound": bool(row.get("is_wecom_bound")),
            "activation_status": str(row.get("activation_status") or "").strip(),
            "activation_status_label": USER_OPS_ACTIVATION_STATUS_LABELS.get(str(row.get("activation_status") or "").strip(), str(row.get("activation_status") or "").strip()),
            "activation_remark": str(row.get("activation_remark") or "").strip(),
            "class_term_no": int(row["class_term_no"]) if row.get("class_term_no") not in (None, "") else None,
            "class_term_label": str(row.get("class_term_label") or "").strip(),
            "source_type": str(row.get("source_type") or "").strip(),
            "created_at": _stringify_db_timestamp(row.get("created_at")),
            "updated_at": _stringify_db_timestamp(row.get("updated_at")),
        }
        for row in rows
    ]
    return {
        "items": items,
        "total": len(items),
        "filters": {
            "current_status": normalized_current_status,
            "is_wecom_bound": normalized_bound,
            "activation_status": normalized_activation_status,
            "class_term_no": normalized_class_term_no,
            "owner_userid": normalized_owner_userid,
            "query": normalized_query,
        },
        "filter_options": {
            "current_statuses": list(USER_OPS_CURRENT_STATUS_DEFINITIONS),
            "activation_statuses": list(USER_OPS_ACTIVATION_STATUS_DEFINITIONS),
            "class_terms": _user_ops_class_term_options(),
            "owners": _user_ops_owner_options(),
        },
        "meta": {
            "data_generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
    }

def get_user_ops_overview() -> dict[str, Any]:
    _ensure_class_term_tag_mapping_seed()
    rows = get_db().execute(
        """
        SELECT current_status, is_wecom_bound, activation_status
        FROM user_ops_pool_current
        """
    ).fetchall()
    total = len(rows)
    current_status_counts = {item["value"]: 0 for item in USER_OPS_CURRENT_STATUS_DEFINITIONS}
    activation_counts = {item["value"]: 0 for item in USER_OPS_ACTIVATION_STATUS_DEFINITIONS}
    bound_total = 0
    for row in rows:
        status = str(row.get("current_status") or "").strip()
        activation = str(row.get("activation_status") or "").strip()
        if status in current_status_counts:
            current_status_counts[status] += 1
        if activation in activation_counts:
            activation_counts[activation] += 1
        if bool(row.get("is_wecom_bound")):
            bound_total += 1
    return {
        "total_users": total,
        "lead_trial_count": current_status_counts["lead_trial"],
        "signed_999_count": current_status_counts["signed_999"],
        "signed_3999_count": current_status_counts["signed_3999"],
        "wecom_bound_count": bound_total,
        "wecom_unbound_count": total - bound_total,
        "activated_count": activation_counts["activated"],
        "high_intent_count": activation_counts["high_intent"],
        "cards": [
            {"key": "total_users", "label": "总用户数", "value": total},
            {"key": "lead_trial_count", "label": "报名引流品", "value": current_status_counts["lead_trial"]},
            {"key": "signed_999_count", "label": "已报名999", "value": current_status_counts["signed_999"]},
            {"key": "signed_3999_count", "label": "已报名3999", "value": current_status_counts["signed_3999"]},
            {"key": "wecom_bound_count", "label": "已加微人数", "value": bound_total},
            {"key": "wecom_unbound_count", "label": "未加微人数", "value": total - bound_total},
        ],
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

def list_user_ops_history(limit: int = 100) -> dict[str, Any]:
    normalized_limit = max(1, min(int(limit or 100), 500))
    rows = get_db().execute(
        """
        SELECT
            id,
            pool_id,
            mobile,
            external_userid,
            action_type,
            old_payload_json,
            new_payload_json,
            operator,
            source_type,
            created_at
        FROM user_ops_pool_history
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (normalized_limit,),
    ).fetchall()
    total_row = get_db().execute("SELECT COUNT(*) AS total FROM user_ops_pool_history").fetchone()
    return {
        "items": [
            {
                "id": int(row["id"]),
                "pool_id": int(row["pool_id"]) if row.get("pool_id") is not None else None,
                "mobile": str(row.get("mobile") or "").strip(),
                "external_userid": str(row.get("external_userid") or "").strip(),
                "action_type": str(row.get("action_type") or "").strip(),
                "old_payload_json": str(row.get("old_payload_json") or "").strip() or "{}",
                "new_payload_json": str(row.get("new_payload_json") or "").strip() or "{}",
                "operator": str(row.get("operator") or "").strip(),
                "source_type": str(row.get("source_type") or "").strip(),
                "created_at": _stringify_db_timestamp(row.get("created_at")),
            }
            for row in rows
        ],
        "total": int((total_row or {}).get("total") or 0),
        "limit": normalized_limit,
    }

def export_user_ops_pool(
    *,
    current_status: str = "",
    is_wecom_bound: str = "",
    activation_status: str = "",
    class_term_no: str = "",
    owner_userid: str = "",
    query: str = "",
) -> dict[str, Any]:
    result = list_user_ops_pool(
        current_status=current_status,
        is_wecom_bound=is_wecom_bound,
        activation_status=activation_status,
        class_term_no=class_term_no,
        owner_userid=owner_userid,
        query=query,
    )
    headers = ["客户昵称", "手机号", "跟进人", "当前状态", "是否加微", "激活状态", "高意向备注", "班期", "external_userid", "更新时间"]
    rows = [
        [
            item.get("customer_name", ""),
            item.get("mobile", ""),
            item.get("owner_display_name", ""),
            item.get("current_status_label", ""),
            "已加微" if item.get("is_wecom_bound") else "未加微",
            item.get("activation_status_label", ""),
            item.get("activation_remark", ""),
            item.get("class_term_label", "") or (f"{item['class_term_no']}期" if item.get("class_term_no") else ""),
            item.get("external_userid", ""),
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
