from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from flask import current_app

from .archive_adapter import ArchiveAdapterClient
from .db import get_db, get_db_backend
from .services import (
    apply_class_user_status_change,
    build_class_user_tag_view,
    contact_description_state,
    count_contacts,
    count_external_contact_identity_maps,
    count_group_chats,
    create_sync_run,
    finish_sync_run,
    get_class_user_snapshot,
    get_contact_by_external_userid,
    get_primary_follow_user_userid,
    get_signup_status_definition,
    get_signup_status_definitions,
    list_available_wecom_tags,
    list_contacts as list_contacts_from_db,
    list_group_chats as list_group_chats_from_db,
    list_signup_tag_rules,
    normalize_contact_record,
    normalize_external_contact_identity,
    normalize_group_chat_record,
    plan_contact_description_fix,
    refresh_external_contact_identity_owner,
    remove_tag_snapshots_for_other_users,
    remove_tag_snapshot,
    replace_external_contact_follow_users,
    resolve_external_contact_identity,
    save_tag_snapshot,
    target_contact_description,
    upsert_contacts,
    upsert_external_contact_identity,
    upsert_group_chats,
    upsert_signup_tag_rule,
    update_class_user_status_sync_result,
    update_contact_description_snapshot,
)
from .wecom_client import WeComClient, WeComClientError

contacts_logger = logging.getLogger("contacts_sync")
archive_logger = logging.getLogger("archive_sync")
wecom_logger = logging.getLogger("wecom_api")

def _default_owner_userid() -> str:
    return current_app.config["WECOM_DEFAULT_OWNER_USERID"]

def _corp_id() -> str:
    return current_app.config["WECOM_CORP_ID"]

def _contact_sync_batch_size() -> int:
    return int(current_app.config.get("WECOM_SYNC_BATCH_SIZE", 100))


def _contact_client() -> WeComClient:
    return WeComClient.from_contact_app()

def _collect_owner_userids(client: WeComClient) -> list[str]:
    result = client.list_follow_userids()
    owner_userids = [userid for userid in (result.get("follow_user") or []) if userid]
    if not owner_userids:
        default_owner = _default_owner_userid()
        if default_owner:
            owner_userids = [default_owner]
    return owner_userids

def _log_wecom_client_error(
    exc: WeComClientError,
    *,
    owner_userid: str = "",
    external_userid: str = "",
    chat_id: str = "",
    stage: str = "",
) -> None:
    errcode = (exc.payload or {}).get("errcode")
    errmsg = (exc.payload or {}).get("errmsg")
    wecom_logger.error(
        "stage=%s errcode=%s errmsg=%s owner_userid=%s external_userid=%s chat_id=%s",
        stage or exc.stage or "",
        errcode,
        errmsg or str(exc),
        owner_userid,
        external_userid,
        chat_id,
    )

def _sync_contacts(*, only_new: bool) -> dict:
    client = WeComClient.from_app()
    owner_userids = _collect_owner_userids(client)
    existing_contacts = {row["external_userid"] for row in list_contacts_from_db(None)}
    records_by_external: dict[str, dict] = {}
    fetched_count = 0
    description_updated_count = 0

    for owner_userid in owner_userids:
        try:
            result = client.list_contacts(owner_userid)
        except WeComClientError as exc:
            _log_wecom_client_error(exc, owner_userid=owner_userid, stage="external_contact.list")
            continue
        for external_userid in result.get("external_userid") or []:
            if not external_userid:
                continue
            if only_new and external_userid in existing_contacts:
                continue
            if external_userid in records_by_external:
                continue
            detail = client.get_contact(external_userid)
            normalized, updated_description = _sync_contact_detail_with_description_fix(
                client,
                detail,
                owner_userid=owner_userid,
                default_owner_userid=_default_owner_userid(),
                tolerate_update_error=False,
                log_stage="external_contact.sync",
            )
            if updated_description:
                description_updated_count += 1
            records_by_external[external_userid] = normalized
            fetched_count += 1

    inserted_count, updated_count = upsert_contacts(list(records_by_external.values()))
    return {
        "fetched_count": fetched_count,
        "inserted_count": inserted_count,
        "updated_count": updated_count,
        "description_updated_count": description_updated_count,
        "contacts_total": count_contacts(),
    }

def _sync_external_contact_identity_map(*, only_new: bool) -> dict:
    client = _contact_client()
    corp_id = _corp_id()
    batch_size = _contact_sync_batch_size()
    owner_userids = _collect_owner_userids(client)
    existing_external_userids = set()
    if only_new:
        for row in get_db().execute(
            """
            SELECT external_userid
            FROM wecom_external_contact_identity_map
            WHERE corp_id = ?
            """,
            (corp_id,),
        ).fetchall():
            existing_external_userids.add(row["external_userid"])

    fetched_count = 0
    inserted_count = 0
    updated_count = 0
    counted_external_userids: set[str] = set()

    for owner_userid in owner_userids:
        try:
            result = client.list_contacts(owner_userid)
        except WeComClientError as exc:
            _log_wecom_client_error(
                exc,
                owner_userid=owner_userid,
                stage="external_contact.list",
            )
            continue
        external_userids = [value for value in (result.get("external_userid") or []) if value]
        for start in range(0, len(external_userids), batch_size):
            for external_userid in external_userids[start : start + batch_size]:
                if only_new and external_userid in existing_external_userids:
                    continue
                existing = resolve_external_contact_identity(corp_id, external_userid=external_userid)
                try:
                    detail = client.get_contact(external_userid)
                except WeComClientError as exc:
                    _log_wecom_client_error(
                        exc,
                        owner_userid=owner_userid,
                        external_userid=external_userid,
                        stage="external_contact.get",
                    )
                    continue
                identity = normalize_external_contact_identity(
                    corp_id,
                    detail,
                    follow_user_userid=owner_userid,
                    status="active",
                )
                upsert_external_contact_identity(identity)
                replace_external_contact_follow_users(
                    corp_id,
                    external_userid,
                    detail.get("follow_user") or [],
                    preferred_userid=owner_userid,
                )
                refresh_external_contact_identity_owner(corp_id, external_userid)
                if external_userid not in counted_external_userids:
                    fetched_count += 1
                    if existing:
                        updated_count += 1
                    else:
                        inserted_count += 1
                    counted_external_userids.add(external_userid)

    return {
        "fetched_count": fetched_count,
        "inserted_count": inserted_count,
        "updated_count": updated_count,
        "identity_map_total": count_external_contact_identity_maps(),
    }

def _ensure_contacts_for_external_userids(external_userids: list[str]) -> dict:
    client = WeComClient.from_app()
    existing_contacts = {row["external_userid"] for row in list_contacts_from_db(None)}
    records = []
    description_updated_count = 0
    fetched_count = 0
    skipped_count = 0
    for external_userid in dict.fromkeys([value for value in external_userids if value]):
        try:
            detail = client.get_contact(external_userid)
        except WeComClientError as exc:
            if exc.category == "external_userid 不存在":
                skipped_count += 1
                continue
            raise
        try:
            normalized, updated_description = _sync_contact_detail_with_description_fix(
                client,
                detail,
                default_owner_userid=_default_owner_userid(),
                tolerate_update_error=False,
                log_stage="external_contact.archive_sync",
            )
        except WeComClientError as exc:
            if exc.category == "external_userid 不存在":
                skipped_count += 1
                continue
            raise
        if updated_description:
            description_updated_count += 1
        records.append(normalized)
        fetched_count += 1
    inserted_count, updated_count = upsert_contacts(records)
    new_count = sum(1 for row in records if row["external_userid"] not in existing_contacts)
    return {
        "fetched_count": fetched_count,
        "inserted_count": inserted_count,
        "updated_count": updated_count,
        "description_updated_count": description_updated_count,
        "new_count": new_count,
        "skipped_count": skipped_count,
    }

def _sync_group_chats(*, only_new: bool) -> dict:
    client = WeComClient.from_app()
    owner_userids = _collect_owner_userids(client)
    existing_chat_ids = set()
    if only_new:
        existing_chat_ids = {row["chat_id"] for row in list_group_chats_from_db(None)}
    records_by_chat_id: dict[str, dict] = {}
    fetched_count = 0

    for owner_userid in owner_userids:
        cursor = ""
        while True:
            payload = {"limit": 100, "status_filter": 0, "owner_filter": {"userid_list": [owner_userid]}}
            if cursor:
                payload["cursor"] = cursor
            result = client.list_group_chats(payload)
            for item in result.get("group_chat_list") or []:
                chat_id = item.get("chat_id", "")
                if not chat_id:
                    continue
                if only_new and chat_id in existing_chat_ids:
                    continue
                detail = client.get_group_chat(chat_id)
                records_by_chat_id[chat_id] = normalize_group_chat_record(detail, owner_userid=owner_userid)
                fetched_count += 1
            cursor = result.get("next_cursor", "")
            if not cursor:
                break

    inserted_count, updated_count = upsert_group_chats(list(records_by_chat_id.values()))
    return {
        "fetched_count": fetched_count,
        "inserted_count": inserted_count,
        "updated_count": updated_count,
        "group_chats_total": count_group_chats(),
    }

def _trigger_incremental_archive_sync() -> dict:
    archive_logger.info("incremental archive sync triggered by callback")
    start_time = "2000-01-01 00:00:00"
    end_time = "2099-12-31 23:59:59"
    owner_userid = _default_owner_userid()
    run_id = create_sync_run(start_time, end_time, owner_userid, "")
    client = ArchiveAdapterClient.from_app()
    try:
        result = client.sync_messages(start_time, end_time, owner_userid, "")
        contact_result = _ensure_contacts_for_external_userids(result.get("external_userids") or [])
        group_chat_ids = result.get("group_chat_ids") or []
        if group_chat_ids:
            wecom_client = WeComClient.from_app()
            group_records = []
            for chat_id in group_chat_ids:
                try:
                    detail = wecom_client.get_group_chat(chat_id)
                except WeComClientError as exc:
                    wecom_logger.error(
                        "stage=%s errcode=%s errmsg=%s owner_userid=%s external_userid=%s chat_id=%s",
                        exc.stage or "",
                        (exc.payload or {}).get("errcode"),
                        (exc.payload or {}).get("errmsg", str(exc)),
                        owner_userid,
                        "",
                        chat_id,
                    )
                    continue
                group_records.append(normalize_group_chat_record(detail))
            upsert_group_chats(group_records)
        result["contacts_sync"] = contact_result
        finish_sync_run(
            run_id,
            "success",
            int(result.get("fetched_count", 0)),
            int(result.get("inserted_count", 0)),
            raw_response=result,
        )
        archive_logger.info(
            "incremental archive sync completed fetched=%s inserted=%s last_seq=%s",
            result.get("fetched_count", 0),
            result.get("inserted_count", 0),
            result.get("last_seq", 0),
        )
        return result
    except Exception as exc:
        archive_logger.exception("incremental archive sync failed run_id=%s", run_id)
        finish_sync_run(run_id, "failed", 0, 0, error_message=str(exc))
        raise

def _normalize_contact_descriptions() -> dict:
    client = WeComClient.from_app()
    contacts = list_contacts_from_db(None)
    updated_count = 0
    skipped_count = 0
    untouched_count = 0

    for contact in contacts:
        external_userid = contact.get("external_userid", "")
        state = contact_description_state(contact.get("description"), external_userid)
        if state == "target":
            untouched_count += 1
            continue
        if state == "custom":
            skipped_count += 1
            continue

        owner_userid = contact.get("owner_userid") or _default_owner_userid()
        target_description = target_contact_description(external_userid)
        client.update_contact_description(
            {
                "userid": owner_userid,
                "external_userid": external_userid,
                "description": target_description,
            }
        )
        update_contact_description_snapshot(external_userid, target_description)
        updated_count += 1
        contacts_logger.info(
            "contact description normalized external_userid=%s previous_state=%s",
            external_userid,
            state,
        )

    return {
        "scanned_count": len(contacts),
        "updated_count": updated_count,
        "skipped_count": skipped_count,
        "untouched_count": untouched_count,
        "contacts_total": count_contacts(),
    }

def _sync_contact_detail_with_description_fix(
    client: WeComClient,
    detail: dict,
    *,
    owner_userid: str = "",
    default_owner_userid: str = "",
    tolerate_update_error: bool,
    log_stage: str,
) -> tuple[dict, bool]:
    external_userid = str(((detail.get("external_contact") or detail).get("external_userid")) or "").strip()
    existing_contact = get_contact_by_external_userid(external_userid) if external_userid else None
    plan = plan_contact_description_fix(
        detail,
        owner_userid=owner_userid or None,
        existing_contact=existing_contact,
        default_owner_userid=default_owner_userid,
    )
    normalized = dict(plan["normalized"])
    if not plan["should_update"]:
        return normalized, False
    try:
        client.update_contact_description(plan["update_payload"])
        contacts_logger.info(
            "contact description updated external_userid=%s mode=%s",
            external_userid,
            log_stage,
        )
        return normalized, True
    except WeComClientError as exc:
        _log_wecom_client_error(
            exc,
            owner_userid=str(plan.get("resolved_owner_userid") or ""),
            external_userid=external_userid,
            stage=f"{log_stage}.update_description",
        )
        if not tolerate_update_error:
            raise
        return dict(plan["normalized_original"]), False

def _signup_tag_bootstrap_payload() -> dict[str, object]:
    definitions = get_signup_status_definitions()
    tag_items = list_available_wecom_tags()
    target_group_name = "AI 产品报名情况"
    existing_by_name = {
        str(item.get("tag_name") or "").strip(): item
        for item in tag_items
        if str(item.get("group_name") or "").strip() == target_group_name
    }
    missing_definitions = [item for item in definitions if item["tag_name"] not in existing_by_name]
    created_names: list[str] = []

    if missing_definitions:
        client = WeComClient.from_app()
        if existing_by_name:
            payload = {
                "group_id": next(iter(existing_by_name.values())).get("group_id", ""),
                "tag": [{"name": item["tag_name"]} for item in missing_definitions],
            }
        else:
            payload = {
                "group_name": target_group_name,
                "tag": [{"name": item["tag_name"]} for item in definitions],
            }
        client.create_tag(payload)
        created_names = [item["tag_name"] for item in missing_definitions] if existing_by_name else [item["tag_name"] for item in definitions]
        tag_items = list_available_wecom_tags()
        existing_by_name = {
            str(item.get("tag_name") or "").strip(): item
            for item in tag_items
            if str(item.get("group_name") or "").strip() == target_group_name
        }

    rules: list[dict[str, str]] = []
    for definition in definitions:
        matched = existing_by_name.get(definition["tag_name"])
        if not matched:
            continue
        upsert_signup_tag_rule(matched["tag_id"], matched["tag_name"], definition["signup_status"], active=True)
        rules.append(
            {
                "signup_status": definition["signup_status"],
                "tag_id": matched["tag_id"],
                "tag_name": matched["tag_name"],
                "group_id": matched.get("group_id", "") or "",
                "group_name": matched.get("group_name", "") or "",
            }
        )

    return {
        "group_name": target_group_name,
        "created_tag_names": created_names,
        "rules": rules,
        "definitions": definitions,
    }

def _configured_signup_tag_rules_payload() -> dict[str, object]:
    rules_by_status = {
        str(item.get("signup_status") or "").strip(): {
            "signup_status": str(item.get("signup_status") or "").strip(),
            "tag_id": str(item.get("tag_id") or "").strip(),
            "tag_name": str(item.get("tag_name") or "").strip(),
        }
        for item in list_signup_tag_rules(active_only=True)
        if str(item.get("signup_status") or "").strip()
    }
    definitions = get_signup_status_definitions()
    rules = [rules_by_status[item["signup_status"]] for item in definitions if item["signup_status"] in rules_by_status]
    missing_statuses = [item["signup_status"] for item in definitions if item["signup_status"] not in rules_by_status]
    return {
        "definitions": definitions,
        "rules": rules,
        "missing_statuses": missing_statuses,
        "initialized": not missing_statuses,
    }

def _refresh_class_user_management_live_data() -> dict[str, object]:
    configured = _configured_signup_tag_rules_payload()
    if not configured.get("initialized"):
        return {"refreshed": False, "reason": "signup_tags_not_initialized"}

    rules = configured.get("rules") or []
    signup_tag_ids = sorted({str(item.get("tag_id") or "").strip() for item in rules if str(item.get("tag_id") or "").strip()})
    tag_name_map = {
        str(item.get("tag_id") or "").strip(): str(item.get("tag_name") or "").strip()
        for item in rules
        if str(item.get("tag_id") or "").strip()
    }
    if not signup_tag_ids:
        return {"refreshed": False, "reason": "no_signup_tag_rules"}

    corp_id = _corp_id()
    db = get_db()
    external_rows = db.execute(
        """
        SELECT external_userid
        FROM (
            SELECT external_userid FROM contacts
            UNION
            SELECT external_userid
            FROM wecom_external_contact_follow_users
            WHERE corp_id = ? AND relation_status = 'active'
            UNION
            SELECT external_userid
            FROM wecom_external_contact_identity_map
            WHERE corp_id = ? AND status = 'active'
        ) AS signup_scope
        WHERE external_userid IS NOT NULL AND external_userid <> ''
        ORDER BY external_userid ASC
        """,
        (corp_id, corp_id),
    ).fetchall()
    deduped_external_userids = [str(row.get("external_userid") or "").strip() for row in external_rows if str(row.get("external_userid") or "").strip()]
    client = WeComClient.from_app()
    contact_records: list[dict[str, object]] = []
    refreshed_count = 0
    for external_userid in deduped_external_userids:
        try:
            detail = client.get_contact(external_userid)
        except WeComClientError as exc:
            _log_wecom_client_error(exc, external_userid=external_userid, stage="external_contact.get")
            continue

        follow_users = detail.get("follow_user") or []
        primary_follow_userid = ""
        if follow_users:
            primary_follow_userid = str((follow_users[0] or {}).get("userid") or "").strip()
        contact_records.append(normalize_contact_record(detail, owner_userid=primary_follow_userid or None))
        identity = normalize_external_contact_identity(
            corp_id,
            detail,
            follow_user_userid=primary_follow_userid,
            status="active",
        )
        upsert_external_contact_identity(identity)
        replace_external_contact_follow_users(
            corp_id,
            external_userid,
            follow_users,
            preferred_userid=primary_follow_userid,
        )
        refresh_external_contact_identity_owner(corp_id, external_userid)

        current_follow_userids: list[str] = []
        for follow_user in follow_users:
            follow_user_userid = str((follow_user or {}).get("userid") or "").strip()
            if not follow_user_userid:
                continue
            current_follow_userids.append(follow_user_userid)
            current_tag_ids = sorted(
                {
                    str((tag or {}).get("tag_id") or (tag or {}).get("id") or "").strip()
                    for tag in ((follow_user or {}).get("tags") or [])
                    if str((tag or {}).get("tag_id") or (tag or {}).get("id") or "").strip() in tag_name_map
                }
            )
            if current_tag_ids:
                save_tag_snapshot(follow_user_userid, external_userid, current_tag_ids, tag_name_map)
            remove_tag_snapshot(
                follow_user_userid,
                external_userid,
                [tag_id for tag_id in signup_tag_ids if tag_id not in current_tag_ids],
            )
        remove_tag_snapshots_for_other_users(external_userid, current_follow_userids, signup_tag_ids)
        refreshed_count += 1

    if contact_records:
        upsert_contacts(contact_records)

    return {
        "refreshed": True,
        "owner_count": 0,
        "external_user_count": len(deduped_external_userids),
        "refreshed_count": refreshed_count,
    }

def _list_class_user_management_records_live(signup_status: str = "") -> dict[str, object]:
    normalized_filter = str(signup_status or "").strip()
    status_definitions = get_signup_status_definitions()
    status_priority = {item["signup_status"]: index for index, item in enumerate(status_definitions)}
    configured = _configured_signup_tag_rules_payload()
    rules = configured.get("rules") or []
    rule_by_tag_id = {
        str(item.get("tag_id") or "").strip(): {
            "signup_status": str(item.get("signup_status") or "").strip(),
            "tag_id": str(item.get("tag_id") or "").strip(),
            "tag_name": str(item.get("tag_name") or "").strip(),
        }
        for item in rules
        if str(item.get("tag_id") or "").strip()
    }
    corp_id = _corp_id()
    db = get_db()
    base_rows = db.execute(
        """
        SELECT
            scope.external_userid,
            COALESCE(c.customer_name, '') AS customer_name,
            COALESCE(c.owner_userid, '') AS owner_userid,
            c.updated_at AS contact_updated_at,
            COALESCE(p.mobile, '') AS mobile,
            COALESCE(primary_fu.user_id, '') AS primary_follow_user_userid,
            COALESCE(owner_map.display_name, '') AS follow_user_display_name,
            COALESCE(identity_map.follow_user_userid, '') AS identity_follow_user_userid
        FROM (
            SELECT external_userid FROM contacts
            UNION
            SELECT external_userid
            FROM wecom_external_contact_follow_users
            WHERE corp_id = ? AND relation_status = 'active'
            UNION
            SELECT external_userid
            FROM wecom_external_contact_identity_map
            WHERE corp_id = ? AND status = 'active'
        ) AS scope
        LEFT JOIN contacts c
          ON c.external_userid = scope.external_userid
        LEFT JOIN external_contact_bindings bindings
          ON bindings.external_userid = scope.external_userid
        LEFT JOIN people p
          ON p.id = bindings.person_id
        LEFT JOIN wecom_external_contact_identity_map identity_map
          ON identity_map.corp_id = ? AND identity_map.external_userid = scope.external_userid
        LEFT JOIN wecom_external_contact_follow_users primary_fu
          ON primary_fu.corp_id = ?
         AND primary_fu.external_userid = scope.external_userid
         AND primary_fu.relation_status = 'active'
         AND primary_fu.is_primary = ?
        LEFT JOIN owner_role_map owner_map
          ON owner_map.userid = COALESCE(primary_fu.user_id, c.owner_userid, identity_map.follow_user_userid, '')
        ORDER BY scope.external_userid ASC
        """,
        (
            corp_id,
            corp_id,
            corp_id,
            corp_id,
            True if get_db_backend() == "postgres" else 1,
        ),
    ).fetchall()
    base_by_external = {}
    for row in base_rows:
        external_userid = str(row.get("external_userid") or "").strip()
        if not external_userid:
            continue
        follow_user_userid = (
            str(row.get("primary_follow_user_userid") or "").strip()
            or str(row.get("owner_userid") or "").strip()
            or str(row.get("identity_follow_user_userid") or "").strip()
        )
        base_by_external[external_userid] = {
            "external_userid": external_userid,
            "customer_name": str(row.get("customer_name") or "").strip(),
            "mobile": str(row.get("mobile") or "").strip(),
            "follow_user_userid": follow_user_userid,
            "follow_user_display_name": str(row.get("follow_user_display_name") or "").strip() or follow_user_userid,
            "updated_at": str(row.get("contact_updated_at") or "").strip(),
        }

    client = WeComClient.from_app()
    external_userids = list(base_by_external.keys())
    counts = {item["signup_status"]: 0 for item in status_definitions}
    items: list[dict[str, object]] = []

    def _fetch_live_signup_item(external_userid: str) -> dict[str, object] | None:
        detail = client.get_contact(external_userid)
        base_item = base_by_external.get(external_userid, {})
        preferred_userid = str(base_item.get("follow_user_userid") or "").strip()
        candidates = []
        for follow_user in detail.get("follow_user") or []:
            follow_user_userid = str((follow_user or {}).get("userid") or "").strip()
            for tag in ((follow_user or {}).get("tags") or []):
                tag_id = str((tag or {}).get("tag_id") or (tag or {}).get("id") or "").strip()
                rule = rule_by_tag_id.get(tag_id)
                if not rule:
                    continue
                candidates.append(
                    {
                        "follow_user_userid": follow_user_userid,
                        "signup_status": rule["signup_status"],
                        "tag_id": rule["tag_id"],
                        "tag_name": rule["tag_name"],
                    }
                )
        if not candidates:
            return None
        candidates.sort(
            key=lambda item: (
                0 if preferred_userid and item["follow_user_userid"] == preferred_userid else 1,
                status_priority.get(item["signup_status"], 999),
                item["tag_id"],
            )
        )
        chosen = candidates[0]
        item_follow_user_userid = chosen["follow_user_userid"] or preferred_userid
        item_follow_user_display_name = base_item.get("follow_user_display_name", "") if item_follow_user_userid == preferred_userid else item_follow_user_userid
        return {
            "customer_name": base_item.get("customer_name", "") or str((detail.get("external_contact") or {}).get("name") or "").strip(),
            "external_userid": external_userid,
            "follow_user_display_name": item_follow_user_display_name or item_follow_user_userid,
            "follow_user_userid": item_follow_user_userid,
            "mobile": base_item.get("mobile", ""),
            "status_fields": {
                "signup_status": chosen["signup_status"],
                "current_tag_id": chosen["tag_id"],
                "current_tag_name": chosen["tag_name"],
                "matched_tags": [
                    {
                        "signup_status": chosen["signup_status"],
                        "tag_id": chosen["tag_id"],
                        "tag_name": chosen["tag_name"],
                    }
                ],
                "operation_flags": {
                    "action_executed": None,
                    "added_wecom": None,
                    "mobile_bound": bool(base_item.get("mobile", "")),
                },
            },
            "updated_at": base_item.get("updated_at", ""),
        }

    max_workers = min(16, max(4, len(external_userids) or 1))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(_fetch_live_signup_item, external_userid): external_userid for external_userid in external_userids}
        for future in as_completed(future_map):
            external_userid = future_map[future]
            try:
                item = future.result()
            except WeComClientError as exc:
                _log_wecom_client_error(exc, external_userid=external_userid, stage="external_contact.get")
                continue
            except Exception as exc:
                wecom_logger.exception("class user live query failed external_userid=%s error=%s", external_userid, exc)
                continue
            if not item:
                continue
            resolved_status = str(((item.get("status_fields") or {}).get("signup_status")) or "").strip()
            if resolved_status in counts:
                counts[resolved_status] += 1
            if normalized_filter and resolved_status != normalized_filter:
                continue
            items.append(item)

    items.sort(key=lambda item: (str(item.get("updated_at") or ""), str(item.get("external_userid") or "")), reverse=True)
    return {
        "filter": normalized_filter,
        "status_definitions": status_definitions,
        "stats": [
            {
                "signup_status": item["signup_status"],
                "label": item["label"],
                "count": counts[item["signup_status"]],
            }
            for item in status_definitions
        ],
        "items": items,
        "total": len(items),
        "meta": {
            "module": "class_user_management",
            "reserved_filters": ["action_executed", "added_wecom", "mobile_bound", "phone_compare_status"],
            "reserved_fields": ["operation_flags", "binding_flags", "compare_flags"],
            "data_generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "query_mode": "live_wecom_tags",
            "scope_external_user_count": len(external_userids),
        },
        "tag_initialization": configured,
        "live_refresh": {
            "refreshed": True,
            "mode": "live_wecom_tags",
            "external_user_count": len(external_userids),
            "matched_count": len(items) if normalized_filter else sum(counts.values()),
        },
    }

def _apply_signup_sidebar_tag(external_userid: str, owner_userid: str, signup_status: str) -> dict[str, object]:
    normalized_external_userid = str(external_userid or "").strip()
    normalized_owner_userid = str(owner_userid or "").strip() or get_primary_follow_user_userid(normalized_external_userid)
    normalized_status = str(signup_status or "").strip()
    definition = get_signup_status_definition(normalized_status)
    if not normalized_external_userid:
        raise ValueError("external_userid is required")
    if not normalized_owner_userid:
        raise ValueError("owner_userid is required")
    if not definition:
        raise ValueError("signup_status is invalid")

    configured = _configured_signup_tag_rules_payload()
    rules = configured.get("rules") or []
    target_rule = next((item for item in rules if item.get("signup_status") == normalized_status), None)
    if not target_rule:
        raise ValueError("signup tags are not initialized, please initialize them in admin first")
    snapshot = get_class_user_snapshot(normalized_external_userid, normalized_owner_userid)
    current_record = apply_class_user_status_change(
        external_userid=normalized_external_userid,
        signup_status=normalized_status,
        set_by_userid=normalized_owner_userid,
        customer_name_snapshot=str(snapshot.get("customer_name_snapshot") or "").strip(),
        owner_userid_snapshot=str(snapshot.get("owner_userid_snapshot") or "").strip() or normalized_owner_userid,
        mobile_snapshot=str(snapshot.get("mobile_snapshot") or "").strip(),
    )
    remove_tag_ids = sorted(
        {
            str(item.get("tag_id") or "").strip()
            for item in rules
            if str(item.get("tag_id") or "").strip() and str(item.get("signup_status") or "").strip() != normalized_status
        }
    )
    sync_status = "success"
    sync_error = ""
    result = {}
    try:
        client = WeComClient.from_app()
        result = client.mark_external_contact_tags(
            external_userid=normalized_external_userid,
            follow_user_userid=normalized_owner_userid,
            add_tags=[str(target_rule.get("tag_id") or "").strip()],
            remove_tags=remove_tag_ids,
        )
        save_tag_snapshot(
            normalized_owner_userid,
            normalized_external_userid,
            [str(target_rule.get("tag_id") or "").strip()],
            {str(target_rule.get("tag_id") or "").strip(): str(target_rule.get("tag_name") or "").strip()},
        )
        if remove_tag_ids:
            remove_tag_snapshot(normalized_owner_userid, normalized_external_userid, remove_tag_ids)
    except WeComClientError as exc:
        sync_status = "failed"
        sync_error = str(exc)
        result = {
            "ok": False,
            "error": str(exc),
            "error_category": exc.category or "",
            "error_stage": exc.stage or "",
        }
    update_class_user_status_sync_result(
        normalized_external_userid,
        wecom_tag_sync_status=sync_status,
        wecom_tag_sync_error=sync_error,
    )
    tag_view = build_class_user_tag_view(
        [
            {
                "tag_id": str(target_rule.get("tag_id") or "").strip(),
                "tag_name": str(target_rule.get("tag_name") or "").strip(),
            }
        ]
    )
    return {
        "result": result,
        "signup_status": normalized_status,
        "current_tag": tag_view.get("current_tag_name", ""),
        "tag_id": str(target_rule.get("tag_id") or "").strip(),
        "removed_tag_ids": remove_tag_ids,
        "local_current": current_record,
        "wecom_tag_sync_status": sync_status,
        "wecom_tag_sync_error": sync_error,
    }
