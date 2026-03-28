from __future__ import annotations

import base64
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from xml.sax.saxutils import escape as xml_escape

import requests
from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    jsonify,
    redirect,
    render_template,
    render_template_string,
    request,
    send_from_directory,
    session,
    url_for,
)
from xml.etree import ElementTree as ET

from .archive_adapter import ArchiveAdapterClient
from .customer_center.service import get_customer_detail, list_customers
from .customer_center.routes import parse_customer_filters
from .customer_timeline import get_customer_timeline, parse_timeline_filters
from .archive_sdk import WeComArchiveError
from .observability import (
    bind_background_context,
    generate_job_id,
    get_job_id,
    get_parent_request_id,
    get_request_id,
    get_task_name,
    unbind_background_context,
)
from .wecom_callback import (
    WeComCallbackError,
    build_encrypted_reply,
    decrypt_message,
    get_callback_config,
    parse_callback_xml,
    verify_signature,
)
from .db import get_db, get_db_backend, init_db
from .services import (
    ContactBindingConflictError,
    QuestionnaireAlreadySubmittedError,
    bind_openid_to_external_contact,
    bind_mobile_to_external_contact,
    backfill_class_term_for_owner,
    build_class_user_tag_view,
    apply_class_user_status_change,
    count_archived_messages,
    count_contacts,
    count_external_contact_identity_maps,
    count_group_chats,
    contact_description_state,
    create_sync_run,
    create_questionnaire,
    delete_questionnaire,
    disable_questionnaire,
    export_class_user_management_records,
    export_user_ops_pool,
    export_questionnaire_submissions,
    finish_sync_run,
    finish_external_contact_event_log,
    get_archive_last_seq,
    get_contact_binding_status,
    get_contact_by_external_userid,
    get_primary_follow_user_userid,
    get_class_user_snapshot,
    get_class_user_status_current,
    get_signup_status_definition,
    get_signup_status_definition_by_tag_name,
    get_signup_status_definitions,
    get_external_contact_event_log,
    get_group_chat_by_chat_id,
    get_last_contacts_sync_time,
    get_last_sync_run,
    get_public_questionnaire_by_slug,
    get_questionnaire_detail,
    get_latest_questionnaire_submit_debug,
    has_questionnaire_submission,
    get_recent_external_contact_event_logs,
    get_messages_by_user,
    get_recent_messages_by_user,
    get_user_ops_overview,
    import_activation_status_source,
    import_experience_leads,
    list_available_wecom_tags,
    list_archived_messages_by_window,
    list_class_user_management_records,
    list_class_user_status_history,
    list_contacts as list_contacts_from_db,
    list_group_chats as list_group_chats_from_db,
    list_signup_tag_rules,
    list_user_ops_history,
    list_user_ops_pool,
    list_questionnaires,
    list_settings_snapshot,
    log_external_contact_event,
    mark_external_contact_event_processing,
    needs_contact_description_update,
    normalize_contact_record,
    plan_contact_description_fix,
    normalize_external_contact_identity,
    normalize_group_chat_record,
    replace_external_contact_follow_users,
    run_due_user_ops_deferred_jobs,
    remove_tag_snapshots_for_other_users,
    remove_tag_snapshot,
    resolve_external_contact_identity,
    refresh_external_contact_identity_owner,
    save_outbound_task,
    save_tag_snapshot,
    search_messages,
    resolve_person_identity,
    reload_user_ops_pool,
    schedule_user_ops_auto_assign_class_term_job,
    set_settings,
    submit_questionnaire,
    upsert_signup_tag_rule,
    update_class_user_status_sync_result,
    target_contact_description,
    ThirdPartyUserSyncError,
    update_contact_description_snapshot,
    update_questionnaire,
    migrate_class_user_status_from_contact_tags,
    upsert_external_contact_identity,
    upsert_group_chats,
    upsert_contacts,
    mark_external_contact_identity_status,
    mark_external_contact_follow_user_status,
)
from .wecom_client import WeComClient, WeComClientError

bp = Blueprint("api", __name__)
background_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="wecom-bg")
callback_logger = logging.getLogger("callback")
archive_logger = logging.getLogger("archive_sync")
contacts_logger = logging.getLogger("contacts_sync")
wecom_logger = logging.getLogger("wecom_api")
APP_STARTED_AT = datetime.utcnow()
APP_STARTED_AT_TEXT = APP_STARTED_AT.replace(microsecond=0).isoformat() + "Z"


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


def _wecom_error_response(exc: WeComClientError):
    payload_json = request.get_json(silent=True) or {}
    owner_userid = payload_json.get("owner_userid") or payload_json.get("userid") or request.args.get("owner_userid", "")
    external_userid = payload_json.get("external_userid") or request.args.get("external_userid", "")
    chat_id = payload_json.get("chat_id") or payload_json.get("ChatId") or request.args.get("chat_id", "")
    _log_wecom_client_error(
        exc,
        owner_userid=owner_userid,
        external_userid=external_userid,
        chat_id=chat_id,
    )
    payload = {"ok": False, "error": str(exc)}
    if exc.category:
        payload["error_category"] = exc.category
    if exc.stage:
        payload["error_stage"] = exc.stage
    if exc.payload:
        payload["wecom_payload"] = exc.payload
    return jsonify(payload), 502


def _default_owner_userid() -> str:
    return current_app.config["WECOM_DEFAULT_OWNER_USERID"]


def _corp_id() -> str:
    return current_app.config["WECOM_CORP_ID"]


def _contact_sync_batch_size() -> int:
    return int(current_app.config.get("WECOM_SYNC_BATCH_SIZE", 100))


def _contact_sync_retry_limit() -> int:
    return int(current_app.config.get("WECOM_SYNC_RETRY_LIMIT", 3))


def _contact_client() -> WeComClient:
    return WeComClient.from_contact_app()


def _questionnaire_public_path(slug: str) -> str:
    return f"/s/{slug}"


def _questionnaire_submitted_path(slug: str) -> str:
    return f"/s/{slug}/submitted"


def _external_base_url() -> str:
    forwarded_proto = (request.headers.get("X-Forwarded-Proto") or "").split(",")[0].strip()
    forwarded_host = (request.headers.get("X-Forwarded-Host") or "").split(",")[0].strip()
    scheme = forwarded_proto or request.scheme or "http"
    host = forwarded_host or request.host
    return f"{scheme}://{host}".rstrip("/")


def _questionnaire_public_url(slug: str) -> str:
    return f"{_external_base_url()}{_questionnaire_public_path(slug)}"


def _attach_questionnaire_links(item: dict) -> dict:
    enriched = dict(item)
    slug = enriched.get("slug", "")
    if slug:
        enriched["public_path"] = _questionnaire_public_path(slug)
        enriched["public_url"] = _questionnaire_public_url(slug)
    return enriched


def _build_excel_xml(headers: list[str], rows: list[list[str]]) -> bytes:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<?mso-application progid="Excel.Sheet"?>',
        '<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"',
        ' xmlns:o="urn:schemas-microsoft-com:office:office"',
        ' xmlns:x="urn:schemas-microsoft-com:office:excel"',
        ' xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">',
        '<Worksheet ss:Name="Questionnaire">',
        "<Table>",
    ]

    def _render_row(values: list[str]) -> str:
        cells = "".join(
            f'<Cell><Data ss:Type="String">{xml_escape(str(value or ""))}</Data></Cell>'
            for value in values
        )
        return f"<Row>{cells}</Row>"

    lines.append(_render_row(headers))
    lines.extend(_render_row(row) for row in rows)
    lines.extend(["</Table>", "</Worksheet>", "</Workbook>"])
    return "\n".join(lines).encode("utf-8")


def _wechat_oauth_is_configured() -> bool:
    secret_key = str(current_app.config.get("SECRET_KEY", "") or "").strip()
    return bool(
        current_app.config.get("WECHAT_MP_APP_ID")
        and current_app.config.get("WECHAT_MP_APP_SECRET")
        and secret_key
        and secret_key != "dev-secret-key-change-me"
    )


def _questionnaire_source_params() -> dict[str, str]:
    payload = {}
    for key in ["source_channel", "campaign_id", "staff_id"]:
        value = request.args.get(key, "").strip()
        if value:
            payload[key] = value
    return payload


def _mask_identity_value(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    if len(normalized) <= 6:
        return "*" * len(normalized)
    return f"{normalized[:3]}***{normalized[-2:]}"


def _questionnaire_session_identity() -> dict[str, str]:
    identity = session.get("questionnaire_h5_identity") or {}
    if not isinstance(identity, dict):
        return {}
    return {
        "openid": str(identity.get("openid") or "").strip(),
        "unionid": str(identity.get("unionid") or "").strip(),
        "respondent_key": str(identity.get("respondent_key") or "").strip(),
    }


def _questionnaire_request_identity() -> dict[str, str]:
    session_identity = _questionnaire_session_identity()
    return {
        "respondent_key": session_identity.get("respondent_key") or request.args.get("respondent_key", "").strip(),
        "openid": session_identity.get("openid") or request.args.get("openid", "").strip(),
        "unionid": session_identity.get("unionid") or request.args.get("unionid", "").strip(),
        "external_userid": request.args.get("external_userid", "").strip(),
    }


def _is_wechat_browser() -> bool:
    user_agent = (request.headers.get("User-Agent") or "").lower()
    return "micromessenger" in user_agent


def _require_wechat_browser_page():
    if _is_wechat_browser():
        return None
    return render_template("open_in_wechat.html"), 200


def _require_wechat_browser_api():
    if _is_wechat_browser():
        return None
    return jsonify({"ok": False, "error": "please_open_in_wechat"}), 403


def _encode_oauth_state(payload: dict[str, str]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _decode_oauth_state(value: str) -> dict[str, str]:
    if not value:
        return {}
    padded = value + "=" * (-len(value) % 4)
    try:
        decoded = base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8")
        payload = json.loads(decoded)
    except (ValueError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {str(key): str(item) for key, item in payload.items() if item not in (None, "")}


def _wechat_oauth_callback_url() -> str:
    return _external_base_url() + url_for("api.h5_wechat_oauth_callback")


def _questionnaire_logger() -> logging.Logger:
    return logging.getLogger("questionnaire")


def _wechat_oauth_scope() -> str:
    return str(current_app.config.get("WECHAT_MP_OAUTH_SCOPE", "snsapi_base") or "snsapi_base").strip() or "snsapi_base"


def _fetch_wechat_userinfo(access_token: str, openid: str) -> dict:
    response = requests.get(
        "https://api.weixin.qq.com/sns/userinfo",
        params={
            "access_token": access_token,
            "openid": openid,
            "lang": "zh_CN",
        },
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def _collect_owner_userids(client: WeComClient) -> list[str]:
    result = client.list_follow_userids()
    owner_userids = [userid for userid in (result.get("follow_user") or []) if userid]
    if not owner_userids:
        default_owner = _default_owner_userid()
        if default_owner:
            owner_userids = [default_owner]
    return owner_userids


def _build_external_contact_event_key(corp_id: str, event_data: dict[str, str]) -> str:
    change_type = (event_data.get("ChangeType") or "").strip()
    external_userid = (event_data.get("ExternalUserID") or "").strip()
    user_id = (event_data.get("UserID") or "").strip()
    create_time = (event_data.get("CreateTime") or "").strip()
    return "|".join([corp_id, change_type, external_userid, user_id, create_time])


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


def _run_app_task(
    app,
    task_name: str,
    task_fn,
    *args,
    job_id: str = "",
    parent_request_id: str = "",
    **kwargs,
) -> None:
    with app.app_context():
        context_tokens = bind_background_context(
            job_id=job_id,
            parent_request_id=parent_request_id,
            task_name=task_name,
        )
        try:
            callback_logger.info(
                "background task started job_id=%s task_name=%s parent_request_id=%s",
                job_id,
                task_name,
                parent_request_id,
            )
            task_fn(*args, **kwargs)
            callback_logger.info(
                "background task finished job_id=%s task_name=%s parent_request_id=%s",
                job_id,
                task_name,
                parent_request_id,
            )
        except Exception:
            callback_logger.exception(
                "background task failed job_id=%s task_name=%s parent_request_id=%s",
                job_id,
                task_name,
                parent_request_id,
            )
        finally:
            unbind_background_context(context_tokens)


def _dispatch_background_task(task_name: str, task_fn, *args, **kwargs) -> None:
    app = current_app._get_current_object()
    job_id = generate_job_id()
    parent_request_id = get_request_id()
    if current_app.config.get("CALLBACK_ASYNC_ENABLED", True):
        background_executor.submit(
            _run_app_task,
            app,
            task_name,
            task_fn,
            *args,
            job_id=job_id,
            parent_request_id=parent_request_id,
            **kwargs,
        )
    else:
        _run_app_task(
            app,
            task_name,
            task_fn,
            *args,
            job_id=job_id,
            parent_request_id=parent_request_id,
            **kwargs,
        )


def _run_user_ops_deferred_jobs_after_delay(wait_seconds: int = 10, limit: int = 20) -> None:
    delay = max(int(wait_seconds or 0), 0)
    if delay:
        time.sleep(delay)
    result = run_due_user_ops_deferred_jobs(limit=limit)
    callback_logger.info(
        "background task summary job_id=%s task_name=%s parent_request_id=%s "
        "stage=user_ops_auto_assign scanned=%s success=%s conflict=%s skipped=%s failed=%s",
        get_job_id(),
        get_task_name(),
        get_parent_request_id(),
        result.get("scanned_count", 0),
        result.get("success_count", 0),
        result.get("conflict_count", 0),
        result.get("skipped_count", 0),
        result.get("failed_count", 0),
    )


def _handle_group_chat_change(event_data: dict[str, str]) -> dict:
    chat_id = event_data.get("ChatId") or event_data.get("chat_id") or event_data.get("ChatID") or ""
    change_type = (event_data.get("ChangeType") or event_data.get("change_type") or "").lower()
    if not chat_id:
        return {"handled": False, "reason": "missing chat_id"}
    if "dismiss" in change_type:
        existing = get_group_chat_by_chat_id(chat_id) or {"chat_id": chat_id}
        upsert_group_chats(
            [
                {
                    "chat_id": chat_id,
                    "group_name": existing.get("group_name", ""),
                    "owner_userid": existing.get("owner_userid", ""),
                    "notice": existing.get("notice", ""),
                    "member_count": existing.get("member_count", 0),
                    "status": "dismissed",
                    "create_time": existing.get("create_time", ""),
                    "dismissed_at": existing.get("dismissed_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "raw_payload": existing.get("raw_payload", "{}"),
                }
            ]
        )
        return {"handled": True, "chat_id": chat_id, "change_type": change_type}

    wecom_client = WeComClient.from_app()
    detail = wecom_client.get_group_chat(chat_id)
    upsert_group_chats([normalize_group_chat_record(detail)])
    return {"handled": True, "chat_id": chat_id, "change_type": change_type}


def _process_external_contact_event(event_log_id: int) -> dict:
    event_log = get_external_contact_event_log(event_log_id)
    if not event_log:
        return {"ok": False, "error": "event_log_not_found"}
    if event_log.get("process_status") == "success":
        return {"ok": True, "status": "success", "event_log_id": event_log_id, "duplicate": True}

    mark_external_contact_event_processing(event_log_id)
    event_log = get_external_contact_event_log(event_log_id) or event_log
    retry_limit = _contact_sync_retry_limit()
    corp_id = event_log.get("corp_id", "")
    external_userid = event_log.get("external_userid", "")
    user_id = event_log.get("user_id", "")
    change_type = (event_log.get("change_type") or "").lower()
    client = _contact_client()
    scheduled_auto_assign_job: dict[str, object] | None = None

    try:
        if change_type in {"add_external_contact", "add_half_external_contact", "edit_external_contact"}:
            detail = client.get_contact(external_userid)
            normalized_contact, _ = _sync_contact_detail_with_description_fix(
                client,
                detail,
                owner_userid=user_id,
                default_owner_userid=_default_owner_userid(),
                tolerate_update_error=True,
                log_stage="external_contact.callback",
            )
            upsert_contacts([normalized_contact])
            identity = normalize_external_contact_identity(
                corp_id,
                detail,
                follow_user_userid=user_id,
                status="active",
            )
            upsert_external_contact_identity(identity)
            replace_external_contact_follow_users(
                corp_id,
                external_userid,
                detail.get("follow_user") or [],
                preferred_userid=user_id,
            )
            refresh_external_contact_identity_owner(corp_id, external_userid)
            if change_type in {"add_external_contact", "add_half_external_contact"}:
                scheduled_auto_assign_job = schedule_user_ops_auto_assign_class_term_job(
                    external_userid=external_userid,
                    owner_userid=str(normalized_contact.get("owner_userid") or user_id or "").strip(),
                    delay_seconds=10,
                    operator="system_auto_assign",
                )
        elif change_type in {"del_external_contact", "del_follow_user"}:
            mark_external_contact_identity_status(
                corp_id,
                external_userid,
                status="inactive",
                follow_user_userid=user_id,
            )
            mark_external_contact_follow_user_status(
                corp_id,
                external_userid,
                user_id=user_id if change_type == "del_follow_user" else "",
                status="inactive",
            )
            refresh_external_contact_identity_owner(corp_id, external_userid)
        else:
            finish_external_contact_event_log(event_log_id, status="ignored")
            callback_logger.info(
                "stage=external_contact_callback errcode=0 errmsg=ignored_change_type change_type=%s owner_userid=%s external_userid=%s chat_id=",
                change_type,
                user_id,
                external_userid,
            )
            return {"ok": True, "status": "ignored", "event_log_id": event_log_id}

        finish_external_contact_event_log(event_log_id, status="success")
        if scheduled_auto_assign_job and scheduled_auto_assign_job.get("scheduled"):
            _dispatch_background_task(
                "user_ops_auto_assign_class_term",
                _run_user_ops_deferred_jobs_after_delay,
                11,
                20,
            )
        callback_logger.info(
            "stage=external_contact_callback errcode=0 errmsg=success owner_userid=%s external_userid=%s chat_id=",
            user_id,
            external_userid,
        )
        return {"ok": True, "status": "success", "event_log_id": event_log_id}
    except Exception as exc:
        latest = get_external_contact_event_log(event_log_id) or event_log
        next_retry = int(latest.get("retry_count") or 0) + 1
        final_status = "failed" if next_retry >= retry_limit else "pending"
        finish_external_contact_event_log(
            event_log_id,
            status=final_status,
            error_message=str(exc),
            increment_retry=True,
        )
        callback_logger.error(
            "stage=external_contact_callback errcode=1 errmsg=%s owner_userid=%s external_userid=%s chat_id=",
            str(exc),
            user_id,
            external_userid,
        )
        if final_status == "pending":
            return _process_external_contact_event(event_log_id)
        return {"ok": False, "status": final_status, "event_log_id": event_log_id, "error": str(exc)}


def _sidebar_person_detail_url(binding: dict[str, object] | None) -> str:
    if not binding:
        return ""
    template = str(current_app.config.get("SIDEBAR_PERSON_DETAIL_URL_TEMPLATE", "") or "").strip()
    if not template:
        return ""
    try:
        return template.format(
            person_id=binding.get("person_id", ""),
            external_userid=binding.get("external_userid", ""),
            owner_userid=binding.get("owner_userid", ""),
            mobile=binding.get("mobile", ""),
            third_party_user_id=binding.get("third_party_user_id", ""),
        )
    except Exception:
        return ""


def _normalize_jssdk_url(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError("url is required")
    return normalized.split("#", 1)[0]


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


@bp.route("/sidebar/bind-mobile", methods=["GET"])
def sidebar_bind_mobile_page():
    return render_template_string(
        """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>客户档案绑定</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f5f2ea;
      --panel: rgba(255,255,255,0.94);
      --line: rgba(81, 63, 34, 0.12);
      --text: #2f2416;
      --muted: #7b6c57;
      --primary: #91643b;
      --primary-strong: #754d28;
      --soft: #f4e9da;
      --danger: #b24e37;
      --ok: #2f7d57;
      --shadow: 0 18px 50px rgba(76, 53, 28, 0.08);
      --radius: 18px;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: "PingFang SC", "Helvetica Neue", -apple-system, BlinkMacSystemFont, sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at top left, rgba(201, 153, 96, 0.18), transparent 24%),
        linear-gradient(180deg, #f9f6ef 0%, var(--bg) 100%);
    }
    .shell { max-width: 720px; margin: 0 auto; padding: 20px 16px 28px; }
    .hero { margin-bottom: 16px; }
    .hero h1 { margin: 0 0 8px; font-size: 24px; line-height: 1.15; }
    .hero p { margin: 0; color: var(--muted); font-size: 14px; line-height: 1.6; }
    .customer-title {
      margin-top: 10px;
      font-size: 18px;
      font-weight: 700;
      line-height: 1.4;
    }
    .card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      padding: 18px;
      backdrop-filter: blur(8px);
    }
    .grid { display: grid; gap: 12px; }
    label { display: grid; gap: 8px; font-size: 14px; }
    input {
      width: 100%;
      border: 1px solid rgba(81, 63, 34, 0.18);
      border-radius: 14px;
      padding: 14px 15px;
      font-size: 16px;
      background: #fffdf8;
      color: var(--text);
    }
    button {
      border: 0;
      border-radius: 14px;
      padding: 14px 16px;
      font-size: 15px;
      font-weight: 600;
      background: linear-gradient(135deg, var(--primary), var(--primary-strong));
      color: #fff;
      cursor: pointer;
    }
    button[disabled] { opacity: 0.55; cursor: not-allowed; }
    .status {
      margin-top: 14px;
      min-height: 22px;
      font-size: 13px;
      color: var(--muted);
    }
    .status.error { color: var(--danger); }
    .status.success { color: var(--ok); }
    .hidden { display: none; }
    .actions { display: flex; gap: 10px; flex-wrap: wrap; }
    .muted-note {
      color: var(--muted);
      font-size: 14px;
      line-height: 1.6;
    }
    .ghost {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border-radius: 12px;
      padding: 11px 14px;
      text-decoration: none;
      color: var(--primary-strong);
      background: var(--soft);
      font-size: 14px;
      font-weight: 600;
    }
    .tag-quick-card { margin-top: 14px; }
    .section-title {
      margin: 0 0 6px;
      font-size: 16px;
      font-weight: 700;
    }
    .section-note {
      margin: 0 0 12px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.6;
    }
    .tag-quick-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
    }
    .tag-quick-btn {
      padding: 12px 10px;
      border-radius: 14px;
      border: 1px solid rgba(81, 63, 34, 0.14);
      background: #fffdf8;
      color: var(--text);
      font-weight: 700;
      font-size: 14px;
    }
    .tag-quick-btn.active {
      background: linear-gradient(135deg, var(--primary), var(--primary-strong));
      color: #fff;
      border-color: transparent;
    }
    .tag-quick-btn[disabled] { opacity: 0.58; cursor: not-allowed; }
    @media (max-width: 560px) {
      .kv { grid-template-columns: 1fr; gap: 6px; }
      .tag-quick-grid { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <section class="hero">
      <h1>客户档案绑定</h1>
      <p>识别当前客户是否已绑定手机号，未绑定则补充手机号，已绑定则直接查看绑定信息。</p>
      <div id="customer-title" class="customer-title">客户昵称：识别中</div>
    </section>

    <section id="loading-card" class="card">
      <div class="status">正在识别当前客户…</div>
    </section>

    <section id="unbind-card" class="card hidden">
      <div class="grid">
        <div class="muted-note">该客户暂未绑定手机号</div>
        <label>
          <span>手机号</span>
          <input id="mobile-input" inputmode="numeric" autocomplete="tel" maxlength="20" placeholder="请输入 11 位手机号">
        </label>
        <button id="bind-button" type="button">绑定手机号</button>
        <div id="bind-status" class="status"></div>
      </div>
    </section>

    <section id="bound-card" class="card hidden">
      <div class="grid">
        <div class="muted-note">该客户已完成手机号绑定</div>
        <div id="bound-mobile" class="customer-title"></div>
        <div class="actions">
          <button id="rebind-button" type="button" class="ghost">更换手机号</button>
        </div>
        <div id="rebind-form" class="grid hidden">
          <label>
            <span>新手机号</span>
            <input id="rebind-mobile-input" inputmode="numeric" autocomplete="tel" maxlength="20" placeholder="请输入新的 11 位手机号">
          </label>
          <button id="confirm-rebind-button" type="button">确认更换手机号</button>
        </div>
        <div id="bound-status" class="status success"></div>
      </div>
    </section>

    <section id="tag-quick-card" class="card tag-quick-card hidden">
      <h2 class="section-title">AI 产品报名情况</h2>
      <p class="section-note">点击即切换为当前唯一报名状态，并自动去掉这一组其他标签。</p>
      <div id="tag-quick-grid" class="tag-quick-grid"></div>
      <div id="tag-quick-status" class="status"></div>
    </section>

    <div id="debug-wrap" class="hidden"></div>
  </div>

  <script src="https://res.wx.qq.com/open/js/jweixin-1.6.0.js"></script>
  <script>
    const state = {
      external_userid: '',
      owner_userid: '',
      bind_by_userid: '',
    };

    const loadingCard = document.getElementById('loading-card');
    const unbindCard = document.getElementById('unbind-card');
    const boundCard = document.getElementById('bound-card');
    const bindStatus = document.getElementById('bind-status');
    const boundStatus = document.getElementById('bound-status');
    const bindButton = document.getElementById('bind-button');
    const mobileInput = document.getElementById('mobile-input');
    const rebindButton = document.getElementById('rebind-button');
    const rebindForm = document.getElementById('rebind-form');
    const rebindMobileInput = document.getElementById('rebind-mobile-input');
    const confirmRebindButton = document.getElementById('confirm-rebind-button');
    const customerTitle = document.getElementById('customer-title');
    const tagQuickCard = document.getElementById('tag-quick-card');
    const tagQuickGrid = document.getElementById('tag-quick-grid');
    const tagQuickStatus = document.getElementById('tag-quick-status');
    const debugWrap = document.getElementById('debug-wrap');
    const debugEnabled = new URLSearchParams(window.location.search).get('debug') === '1' || {{ debug_enabled|tojson }};
    state.signup_status = '';
    state.signupDefinitions = [];
    debugWrap.classList.toggle('hidden', !debugEnabled);

    function writeDebug(label, payload) {
      if (!debugEnabled) return;
      const line = '[' + new Date().toISOString() + '] ' + label + (payload === undefined ? '' : ' ' + (
        typeof payload === 'string' ? payload : JSON.stringify(payload, null, 2)
      ));
      console.log(line);
    }

    function setStatus(el, text, type) {
      el.textContent = text || '';
      el.className = 'status' + (type ? ' ' + type : '');
    }

    function showCard(name) {
      loadingCard.classList.toggle('hidden', name !== 'loading');
      unbindCard.classList.toggle('hidden', name !== 'unbind');
      boundCard.classList.toggle('hidden', name !== 'bound');
    }

    function getQueryValue(key) {
      return new URLSearchParams(window.location.search).get(key) || '';
    }

    function userMessage(error, fallbackText) {
      return fallbackText;
    }

    function updateCustomerTitle(data) {
      const displayName = String((data || {}).display_name || '').trim() || '当前客户';
      customerTitle.textContent = '客户昵称：' + displayName;
    }

    function renderBound(data) {
      updateCustomerTitle(data);
      document.getElementById('bound-mobile').textContent = '已绑定手机号：' + (data.mobile || '-');
      rebindForm.classList.add('hidden');
      rebindMobileInput.value = '';
      setStatus(boundStatus, '', 'success');
      showCard('bound');
    }

    async function fetchJson(url, options) {
      const response = await fetch(url, options);
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || payload.ok === false) {
        writeDebug('fetchJson fail', { url, status: response.status, payload });
        throw new Error(payload.error || ('请求失败(' + response.status + ')'));
      }
      return payload;
    }

    async function loadStatus() {
      const params = new URLSearchParams({
        external_userid: state.external_userid,
      });
      if (state.owner_userid) {
        params.set('owner_userid', state.owner_userid);
      }
      const result = await fetchJson('/api/sidebar/contact-binding-status?' + params.toString());
      if (result.is_bound) {
        renderBound(result);
        return;
      }
      updateCustomerTitle(result);
      setStatus(bindStatus, '', '');
      showCard('unbind');
    }

    function renderSignupQuickButtons() {
      tagQuickGrid.innerHTML = state.signupDefinitions.map((item) => {
        const activeClass = item.signup_status === state.signup_status ? ' active' : '';
        return '<button type="button" class="tag-quick-btn' + activeClass + '" data-signup-status="' + item.signup_status + '">' + item.label + '</button>';
      }).join('');
      Array.from(tagQuickGrid.querySelectorAll('.tag-quick-btn')).forEach((button) => {
        button.addEventListener('click', () => applySignupTag(button.getAttribute('data-signup-status') || ''));
      });
    }

    async function loadSignupQuickStatus() {
      const params = new URLSearchParams({
        external_userid: state.external_userid,
      });
      if (state.owner_userid) {
        params.set('owner_userid', state.owner_userid);
      }
      const result = await fetchJson('/api/sidebar/signup-tags/status?' + params.toString());
      state.signup_status = String(result.current_signup_status || '').trim();
      state.signupDefinitions = Array.isArray(result.definitions) ? result.definitions : [];
      renderSignupQuickButtons();
      tagQuickCard.classList.remove('hidden');
      setStatus(tagQuickStatus, result.current_tag ? ('当前标签：' + result.current_tag) : '当前未命中班期标签', result.current_tag ? 'success' : '');
    }

    async function applySignupTag(signupStatus) {
      if (!signupStatus) return;
      Array.from(tagQuickGrid.querySelectorAll('.tag-quick-btn')).forEach((button) => {
        button.disabled = true;
      });
      setStatus(tagQuickStatus, '正在更新标签...', '');
      try {
        const result = await fetchJson('/api/sidebar/signup-tags/mark', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            external_userid: state.external_userid,
            owner_userid: state.owner_userid,
            signup_status: signupStatus,
          }),
        });
        state.signup_status = String(result.signup_status || '').trim();
        renderSignupQuickButtons();
        setStatus(tagQuickStatus, '当前标签：' + (result.current_tag || '-'), 'success');
      } catch (error) {
        setStatus(tagQuickStatus, userMessage(error, '快捷打标失败，请稍后重试。'), 'error');
      } finally {
        Array.from(tagQuickGrid.querySelectorAll('.tag-quick-btn')).forEach((button) => {
          button.disabled = false;
        });
      }
    }

    async function resolveContextFromQuery() {
      state.external_userid = getQueryValue('external_userid').trim();
      state.owner_userid = getQueryValue('owner_userid').trim();
      state.bind_by_userid = getQueryValue('bind_by_userid').trim() || state.owner_userid;
      writeDebug('query context', state);
      return Boolean(state.external_userid && state.owner_userid);
    }

    async function initWeComSdk() {
      if (!window.wx) {
        writeDebug('wx missing');
        return false;
      }
      const currentUrl = window.location.href.split('#')[0];
      const configPayload = await fetchJson('/api/sidebar/jssdk-config?url=' + encodeURIComponent(currentUrl));
      writeDebug('jssdk config payload', configPayload);
      return await new Promise((resolve) => {
        let resolved = false;
        const finish = (ok) => {
          if (!resolved) {
            resolved = true;
            resolve(ok);
          }
        };
        window.wx.config({
          beta: true,
          debug: false,
          appId: configPayload.corp_id,
          timestamp: Number(configPayload.config.timestamp),
          nonceStr: configPayload.config.nonceStr,
          signature: configPayload.config.signature,
          jsApiList: ['getContext'],
        });
        window.wx.ready(function() {
          writeDebug('wx.config success', { url: configPayload.config.url });
          if (typeof window.wx.agentConfig !== 'function') {
            writeDebug('wx.agentConfig missing');
            finish(false);
            return;
          }
          window.wx.agentConfig({
            corpid: configPayload.corp_id,
            agentid: String(configPayload.agent_id),
            timestamp: Number(configPayload.agent_config.timestamp),
            nonceStr: configPayload.agent_config.nonceStr,
            signature: configPayload.agent_config.signature,
            jsApiList: ['getContext', 'getCurExternalContact'],
            success: function(res) {
              writeDebug('wx.agentConfig success', res || {});
              finish(true);
            },
            fail: function(err) {
              writeDebug('wx.agentConfig fail', err || {});
              finish(false);
            }
          });
        });
        window.wx.error(function(err) {
          writeDebug('wx.config fail', err || {});
          finish(false);
        });
      });
    }

    async function resolveContextFromWeCom() {
      const sdkReady = await initWeComSdk();
      if (!sdkReady || !window.wx || typeof window.wx.invoke !== 'function') {
        return false;
      }
      window.wx.invoke('getContext', {}, function(res) {
        writeDebug('getContext result', res || {});
      });
      return await new Promise((resolve) => {
        window.wx.invoke('getCurExternalContact', {}, function(res) {
          writeDebug('getCurExternalContact result', res || {});
          const externalUserid = String((res || {}).userId || (res || {}).external_userid || '').trim();
          if (!externalUserid) {
            writeDebug('getCurExternalContact fail', res || {});
            resolve(false);
            return;
          }
          state.external_userid = externalUserid;
          if (!state.owner_userid) {
            state.owner_userid = String((res || {}).owner_userid || '').trim();
          }
          if (!state.bind_by_userid) {
            state.bind_by_userid = String((res || {}).operator_userid || state.owner_userid || '').trim();
          }
          writeDebug('getCurExternalContact success', state);
          resolve(Boolean(state.external_userid));
        });
      });
    }

    async function boot() {
      const hasQueryContext = await resolveContextFromQuery();
      const hasWeComContext = hasQueryContext ? true : await resolveContextFromWeCom();
      if (!hasWeComContext) {
        setStatus(loadingCard.querySelector('.status'), '当前未识别到客户信息，请从企微客户侧边栏重新打开。', 'error');
        return;
      }
      try {
        await loadStatus();
        await loadSignupQuickStatus();
      } catch (error) {
        setStatus(loadingCard.querySelector('.status'), userMessage(error, '客户状态读取失败，请稍后重试。'), 'error');
      }
    }

    bindButton.addEventListener('click', async () => {
      bindButton.disabled = true;
      setStatus(bindStatus, '正在绑定手机号…', '');
      try {
        const result = await fetchJson('/api/sidebar/bind-mobile', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            external_userid: state.external_userid,
            owner_userid: state.owner_userid,
            bind_by_userid: state.bind_by_userid || state.owner_userid,
            mobile: mobileInput.value,
          }),
        });
        renderBound(result.binding || result);
      } catch (error) {
        setStatus(bindStatus, userMessage(error, '绑定失败，请检查手机号后重试。'), 'error');
      } finally {
        bindButton.disabled = false;
      }
    });

    rebindButton.addEventListener('click', () => {
      rebindForm.classList.toggle('hidden');
      setStatus(boundStatus, '', 'success');
    });

    confirmRebindButton.addEventListener('click', async () => {
      confirmRebindButton.disabled = true;
      setStatus(boundStatus, '正在更换手机号…', '');
      try {
        const result = await fetchJson('/api/sidebar/bind-mobile', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            external_userid: state.external_userid,
            owner_userid: state.owner_userid,
            bind_by_userid: state.bind_by_userid || state.owner_userid,
            mobile: rebindMobileInput.value,
            force_rebind: true,
          }),
        });
        renderBound(result.binding || result);
      } catch (error) {
        setStatus(boundStatus, userMessage(error, '更换手机号失败，请检查后重试。'), 'error');
      } finally {
        confirmRebindButton.disabled = false;
      }
    });

    boot();
  </script>
</body>
</html>
        """,
        debug_enabled=bool(current_app.config.get("DEBUG")),
    )


@bp.route("/api/sidebar/contact-binding-status", methods=["GET"])
def sidebar_contact_binding_status():
    external_userid = request.args.get("external_userid", "").strip()
    owner_userid = request.args.get("owner_userid", "").strip()
    if not external_userid:
        return jsonify({"ok": False, "error": "external_userid is required"}), 400
    status = get_contact_binding_status(external_userid, owner_userid)
    status["ok"] = True
    if status.get("is_bound"):
        status["detail_url"] = _sidebar_person_detail_url(status)
    return jsonify(status)


@bp.route("/api/sidebar/jssdk-config", methods=["GET"])
def sidebar_jssdk_config():
    raw_url = request.args.get("url", "")
    try:
        normalized_url = _normalize_jssdk_url(raw_url)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    try:
        client = WeComClient.from_app()
        config_signature = client.build_jsapi_signature(normalized_url, ticket_type="jsapi")
        agent_signature = client.build_jsapi_signature(normalized_url, ticket_type="agent_config")
    except (ValueError, WeComClientError) as exc:
        if isinstance(exc, WeComClientError):
            return _wecom_error_response(exc)
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify(
        {
            "ok": True,
            "corp_id": _corp_id(),
            "agent_id": str(current_app.config.get("WECOM_AGENT_ID", "") or ""),
            "config": config_signature,
            "agent_config": agent_signature,
        }
    )


@bp.route("/api/sidebar/bind-mobile", methods=["POST"])
def sidebar_bind_mobile():
    payload = request.get_json(silent=True) or {}
    try:
        binding = bind_mobile_to_external_contact(
            external_userid=str(payload.get("external_userid") or "").strip(),
            owner_userid=str(payload.get("owner_userid") or "").strip(),
            bind_by_userid=str(payload.get("bind_by_userid") or "").strip(),
            mobile=str(payload.get("mobile") or "").strip(),
            force_rebind=bool(payload.get("force_rebind")),
        )
    except ContactBindingConflictError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 409
    except (ValueError, ThirdPartyUserSyncError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    binding["detail_url"] = _sidebar_person_detail_url(binding)
    return jsonify({"ok": True, "binding": binding})


@bp.route("/api/sidebar/signup-tags/status", methods=["GET"])
def sidebar_signup_tag_status():
    external_userid = request.args.get("external_userid", "").strip()
    if not external_userid:
        return jsonify({"ok": False, "error": "external_userid is required"}), 400
    current_status = get_class_user_status_current(external_userid) or {}
    configured = _configured_signup_tag_rules_payload()
    return jsonify(
        {
            "ok": True,
            "definitions": configured.get("definitions") or [],
            "initialized": bool(configured.get("initialized")),
            "missing_statuses": configured.get("missing_statuses") or [],
            "current_signup_status": str(current_status.get("signup_status") or "").strip(),
            "current_tag": str(current_status.get("signup_label_name") or "").strip(),
            "wecom_tag_sync_status": str(current_status.get("wecom_tag_sync_status") or "").strip(),
            "wecom_tag_sync_error": str(current_status.get("wecom_tag_sync_error") or "").strip(),
        }
    )


@bp.route("/api/sidebar/signup-tags/mark", methods=["POST"])
def sidebar_signup_tag_mark():
    payload = request.get_json(silent=True) or {}
    try:
        result = _apply_signup_sidebar_tag(
            str(payload.get("external_userid") or "").strip(),
            str(payload.get("owner_userid") or "").strip(),
            str(payload.get("signup_status") or "").strip(),
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except WeComClientError as exc:
        return _wecom_error_response(exc)
    return jsonify({"ok": True, **result})


@bp.route("/api/identity/resolve", methods=["GET"])
def api_identity_resolve():
    external_userid = request.args.get("external_userid", "").strip()
    mobile = request.args.get("mobile", "").strip()
    try:
        payload = resolve_person_identity(external_userid=external_userid, mobile=mobile)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **payload})


@bp.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "service": "openclaw-wecom-ability-service"})


@bp.route("/<path:filename>", methods=["GET"])
def serve_root_verification_file(filename: str):
    is_supported_verify_file = (
        (filename.startswith("WW_verify_") or filename.startswith("MP_verify_"))
        and filename.endswith(".txt")
    )
    if not is_supported_verify_file:
        abort(404)
    project_root = Path(current_app.root_path).parent
    return send_from_directory(project_root, filename, mimetype="text/plain")


@bp.route("/archive/messages", methods=["GET"])
def archive_messages():
    start_time = request.args.get("start_time", "").strip()
    end_time = request.args.get("end_time", "").strip()
    owner_userid = request.args.get("owner_userid", "").strip() or current_app.config["WECOM_DEFAULT_OWNER_USERID"]
    cursor = request.args.get("cursor", "").strip()

    if not start_time or not end_time or not owner_userid:
        return jsonify({"ok": False, "error": "start_time, end_time and owner_userid are required"}), 400

    result = list_archived_messages_by_window(start_time, end_time, owner_userid, cursor=cursor)
    return jsonify(result)


@bp.route("/api/init-db", methods=["POST"])
def api_init_db():
    init_db()
    return jsonify({"ok": True})


@bp.route("/api/settings", methods=["GET"])
def get_settings():
    return jsonify({"ok": True, "settings": list_settings_snapshot(current_app.config)})


@bp.route("/api/settings", methods=["PUT"])
def update_settings():
    payload = request.get_json(silent=True) or {}
    settings = payload.get("settings") or {}
    if not isinstance(settings, dict):
        return jsonify({"ok": False, "error": "settings must be an object"}), 400
    set_settings(settings)
    return jsonify({"ok": True, "settings": list_settings_snapshot(current_app.config)})


@bp.route("/api/admin/questionnaires", methods=["GET"])
def admin_list_questionnaires():
    return jsonify({"ok": True, "questionnaires": [_attach_questionnaire_links(item) for item in list_questionnaires()]})


@bp.route("/api/admin/wecom/tags", methods=["GET"])
def admin_list_wecom_tags():
    try:
        return jsonify({"items": list_available_wecom_tags()})
    except WeComClientError as exc:
        return _wecom_error_response(exc)


@bp.route("/api/admin/user-ops/overview", methods=["GET"])
def admin_user_ops_overview():
    payload = get_user_ops_overview()
    return jsonify({"ok": True, **payload})


@bp.route("/api/admin/user-ops/list", methods=["GET"])
def admin_user_ops_list():
    payload = list_user_ops_pool(
        current_status=request.args.get("current_status", "").strip(),
        is_wecom_bound=request.args.get("is_wecom_bound", "").strip(),
        activation_status=request.args.get("activation_status", "").strip(),
        class_term_no=request.args.get("class_term_no", "").strip(),
        owner_userid=request.args.get("owner_userid", "").strip(),
        query=request.args.get("query", "").strip(),
    )
    return jsonify({"ok": True, **payload})


@bp.route("/api/admin/user-ops/history", methods=["GET"])
def admin_user_ops_history():
    try:
        limit = int(request.args.get("limit", "100").strip() or "100")
    except ValueError:
        return jsonify({"ok": False, "error": "limit must be an integer"}), 400
    payload = list_user_ops_history(limit=limit)
    return jsonify({"ok": True, **payload})


@bp.route("/api/admin/user-ops/reload", methods=["POST"])
def admin_user_ops_reload():
    payload = reload_user_ops_pool()
    return jsonify({"ok": True, **payload})


@bp.route("/api/admin/user-ops/import-experience-leads", methods=["POST"])
def admin_user_ops_import_experience_leads():
    uploaded_file = request.files.get("file")
    pasted_text = ""
    if uploaded_file and uploaded_file.filename:
        try:
            payload = import_experience_leads(
                file_name=uploaded_file.filename,
                file_bytes=uploaded_file.read(),
            )
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify(payload)

    if request.is_json:
        pasted_text = str((request.get_json(silent=True) or {}).get("pasted_text") or "").strip()
    elif request.mimetype == "text/plain":
        pasted_text = request.get_data(as_text=True).strip()
    else:
        pasted_text = str(request.form.get("pasted_text") or "").strip()
    if not pasted_text:
        return jsonify({"ok": False, "error": "file or pasted_text is required"}), 400
    try:
        payload = import_experience_leads(pasted_text=pasted_text)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify(payload)


@bp.route("/api/admin/user-ops/import-activation-status", methods=["POST"])
def admin_user_ops_import_activation_status():
    uploaded_file = request.files.get("file")
    pasted_text = ""
    if uploaded_file and uploaded_file.filename:
        try:
            payload = import_activation_status_source(
                file_name=uploaded_file.filename,
                file_bytes=uploaded_file.read(),
            )
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify(payload)

    if request.is_json:
        pasted_text = str((request.get_json(silent=True) or {}).get("pasted_text") or "").strip()
    elif request.mimetype == "text/plain":
        pasted_text = request.get_data(as_text=True).strip()
    else:
        pasted_text = str(request.form.get("pasted_text") or "").strip()
    if not pasted_text:
        return jsonify({"ok": False, "error": "file or pasted_text is required"}), 400
    try:
        payload = import_activation_status_source(pasted_text=pasted_text)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify(payload)


@bp.route("/api/admin/user-ops/backfill-class-term", methods=["POST"])
def admin_user_ops_backfill_class_term():
    payload_json = request.get_json(silent=True) or {}
    owner_userid = str(payload_json.get("owner_userid") or "").strip()
    dry_run_value = payload_json.get("dry_run", True)
    confirm_value = payload_json.get("confirm", False)
    if isinstance(dry_run_value, bool):
        dry_run = dry_run_value
    else:
        dry_run = str(dry_run_value or "").strip().lower() not in {"0", "false", "no"}
    if isinstance(confirm_value, bool):
        confirm = confirm_value
    else:
        confirm = str(confirm_value or "").strip().lower() in {"1", "true", "yes"}
    if not dry_run and not confirm:
        return jsonify({"ok": False, "error": "confirm_required"}), 400
    try:
        payload = backfill_class_term_for_owner(
            owner_userid=owner_userid,
            dry_run=dry_run,
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify(payload)


@bp.route("/api/admin/user-ops/run-deferred-jobs", methods=["POST"])
def admin_user_ops_run_deferred_jobs():
    payload_json = request.get_json(silent=True) or {}
    limit_value = payload_json.get("limit", 20)
    try:
        limit = int(limit_value)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "limit must be an integer"}), 400
    payload = run_due_user_ops_deferred_jobs(limit=limit)
    return jsonify(payload)


@bp.route("/api/admin/user-ops/export", methods=["GET"])
def admin_user_ops_export():
    export_payload = export_user_ops_pool(
        current_status=request.args.get("current_status", "").strip(),
        is_wecom_bound=request.args.get("is_wecom_bound", "").strip(),
        activation_status=request.args.get("activation_status", "").strip(),
        class_term_no=request.args.get("class_term_no", "").strip(),
        owner_userid=request.args.get("owner_userid", "").strip(),
        query=request.args.get("query", "").strip(),
    )
    content = _build_excel_xml(export_payload["headers"], export_payload["rows"])
    return Response(
        content,
        mimetype="application/vnd.ms-excel",
        headers={"Content-Disposition": f"attachment; filename={export_payload['filename']}"},
    )


@bp.route("/admin/user-ops/ui", methods=["GET"])
def admin_user_ops_ui():
    return render_template("admin_user_ops.html")


@bp.route("/api/admin/class-user-management/bootstrap", methods=["POST"])
def admin_class_user_management_bootstrap():
    try:
        payload = _signup_tag_bootstrap_payload()
    except WeComClientError as exc:
        return _wecom_error_response(exc)
    return jsonify({"ok": True, **payload})


@bp.route("/api/admin/class-user-management/migrate", methods=["POST"])
def admin_class_user_management_migrate():
    payload = migrate_class_user_status_from_contact_tags()
    return jsonify({"ok": True, **payload})


@bp.route("/api/admin/class-user-management", methods=["GET"])
def admin_class_user_management_list():
    signup_status = request.args.get("signup_status", "").strip()
    try:
        payload = list_class_user_management_records(signup_status=signup_status)
        payload["tag_initialization"] = _configured_signup_tag_rules_payload()
        payload["live_refresh"] = {}
        return jsonify({"ok": True, **payload})
    except WeComClientError as exc:
        return _wecom_error_response(exc)


@bp.route("/api/admin/class-user-management/export", methods=["GET"])
def admin_class_user_management_export():
    configured = _configured_signup_tag_rules_payload()
    if not configured.get("initialized"):
        return jsonify({"ok": False, "error": "signup tags are not initialized"}), 400
    signup_status = request.args.get("signup_status", "").strip()
    try:
        export_payload = export_class_user_management_records(signup_status=signup_status)
    except WeComClientError as exc:
        return _wecom_error_response(exc)
    content = _build_excel_xml(export_payload["headers"], export_payload["rows"])
    return Response(
        content,
        mimetype="application/vnd.ms-excel",
        headers={"Content-Disposition": f"attachment; filename={export_payload['filename']}"},
    )


@bp.route("/api/admin/class-user-management/history", methods=["GET"])
def admin_class_user_management_history():
    try:
        limit = int(request.args.get("limit", "100").strip() or "100")
    except ValueError:
        return jsonify({"ok": False, "error": "limit must be an integer"}), 400
    payload = list_class_user_status_history(limit=limit)
    return jsonify({"ok": True, **payload})


@bp.route("/api/admin/questionnaires/preflight", methods=["GET"])
def admin_questionnaires_preflight():
    payload = {
        "wechat_oauth_configured": False,
        "wecom_contact_configured": False,
        "debug_session_api_enabled": bool(current_app.config.get("ENABLE_DEBUG_QUESTIONNAIRE_SESSION_API")),
        "questionnaire_admin_ui_enabled": True,
        "wecom_tags_api_available": False,
        "identity_map_available": False,
    }

    payload["wechat_oauth_configured"] = _wechat_oauth_is_configured()
    payload["wecom_contact_configured"] = all(
        str(current_app.config.get(key, "") or "").strip()
        for key in ["WECOM_CORP_ID", "WECOM_CONTACT_SECRET"]
    )

    try:
        list_available_wecom_tags()
        payload["wecom_tags_api_available"] = True
    except Exception as exc:
        payload["wecom_tags_api_available"] = False
        payload["wecom_tags_api_error"] = str(exc)

    try:
        get_db().execute("SELECT COUNT(*) AS total FROM wecom_external_contact_identity_map").fetchone()
        payload["identity_map_available"] = True
    except Exception as exc:
        payload["identity_map_available"] = False
        payload["identity_map_error"] = str(exc)

    return jsonify(payload)


@bp.route("/api/customers", methods=["GET"])
def customer_center_list():
    filters = parse_customer_filters(request.args)
    try:
        payload = list_customers(filters)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **payload})


@bp.route("/api/customers/<external_userid>", methods=["GET"])
def customer_center_detail(external_userid: str):
    customer = get_customer_detail(external_userid)
    if not customer:
        return jsonify({"ok": False, "error": "customer not found"}), 404
    return jsonify({"ok": True, "customer": customer})


@bp.route("/api/customers/<external_userid>/timeline", methods=["GET"])
def customer_timeline_detail(external_userid: str):
    try:
        filters = parse_timeline_filters(request.args)
        timeline = get_customer_timeline(external_userid, filters)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    if not timeline:
        return jsonify({"ok": False, "error": "customer not found"}), 404
    return jsonify({"ok": True, "timeline": timeline})


@bp.route("/admin/class-user-management/ui", methods=["GET"])
def admin_class_user_management_ui():
    return render_template_string(
        """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>班期用户管理</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f3f1ea;
      --panel: rgba(255,255,255,0.95);
      --line: rgba(78, 62, 36, 0.12);
      --text: #2f2416;
      --muted: #776852;
      --primary: #8b6338;
      --primary-strong: #6e4c28;
      --soft: #f4eadb;
      --ok: #2f7d57;
      --danger: #a14e37;
      --shadow: 0 20px 48px rgba(65, 48, 24, 0.08);
      --radius: 22px;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "PingFang SC", "Helvetica Neue", -apple-system, BlinkMacSystemFont, sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at top left, rgba(197, 149, 92, 0.15), transparent 24%),
        linear-gradient(180deg, #f8f4ed 0%, var(--bg) 100%);
    }
    button, a { font: inherit; }
    .shell { max-width: 1320px; margin: 0 auto; padding: 24px 16px 36px; }
    .hero, .card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      backdrop-filter: blur(10px);
    }
    .hero { padding: 22px; margin-bottom: 16px; }
    .hero-head, .toolbar { display: flex; justify-content: space-between; gap: 12px; flex-wrap: wrap; align-items: center; }
    .hero h1 { margin: 0 0 8px; font-size: 28px; }
    .hero p { margin: 0; color: var(--muted); line-height: 1.7; }
    .stats { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin-top: 18px; }
    .stat {
      padding: 16px;
      border-radius: 18px;
      background: #fffdf8;
      border: 1px solid rgba(78, 62, 36, 0.1);
    }
    .stat-label { color: var(--muted); font-size: 13px; margin-bottom: 6px; }
    .stat-value { font-size: 28px; font-weight: 700; }
    .toolbar.card { padding: 16px 18px; margin-bottom: 16px; }
    .toolbar-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
      margin-bottom: 12px;
    }
    .filters { display: flex; flex-wrap: wrap; gap: 10px; }
    .chip {
      border: 1px solid rgba(78, 62, 36, 0.12);
      background: #fffdf8;
      color: var(--text);
      border-radius: 999px;
      padding: 10px 14px;
      cursor: pointer;
      font-weight: 700;
    }
    .chip.active {
      background: linear-gradient(135deg, var(--primary), var(--primary-strong));
      color: #fff;
      border-color: transparent;
    }
    .btn {
      border: 0;
      border-radius: 999px;
      padding: 11px 16px;
      cursor: pointer;
      font-weight: 700;
    }
    .btn.primary { color: #fff; background: linear-gradient(135deg, var(--primary), var(--primary-strong)); }
    .btn.ghost { color: var(--primary-strong); background: var(--soft); }
    .table-card { padding: 10px 0 0; overflow: hidden; }
    table { width: 100%; border-collapse: collapse; }
    th, td { padding: 14px 18px; text-align: left; border-bottom: 1px solid rgba(78, 62, 36, 0.08); font-size: 14px; }
    th { color: var(--muted); font-weight: 600; background: rgba(244, 234, 219, 0.35); }
    .tag-pill {
      display: inline-flex;
      align-items: center;
      padding: 6px 10px;
      border-radius: 999px;
      background: var(--soft);
      color: var(--primary-strong);
      font-weight: 700;
      font-size: 12px;
    }
    .empty, .status { padding: 18px; color: var(--muted); }
    .status.error { color: var(--danger); }
    .data-timestamp { color: var(--muted); font-size: 13px; }
    .ext-note {
      margin-top: 16px;
      padding: 16px 18px;
      border-radius: 18px;
      background: #fffaf2;
      border: 1px dashed rgba(78, 62, 36, 0.18);
      color: var(--muted);
      line-height: 1.7;
      font-size: 14px;
    }
    @media (max-width: 900px) {
      .stats { grid-template-columns: 1fr; }
      .hero-head, .toolbar { flex-direction: column; align-items: stretch; }
      .table-scroll { overflow-x: auto; }
      table { min-width: 900px; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <section class="hero">
      <div class="hero-head">
        <div>
          <h1>班期用户管理</h1>
          <p>聚焦 AI 产品报名情况这一个标签组，做筛选、统计、查看与导出。页面结构已为后续用户运营动作字段预留扩展位。</p>
        </div>
        <div class="hero-head">
          <button id="init-button" class="btn ghost" type="button">检查并补齐标签</button>
          <button id="refresh-button" class="btn ghost" type="button">重新加载页面数据</button>
        </div>
      </div>
      <div id="stats" class="stats"></div>
    </section>

    <section class="toolbar card">
      <div class="toolbar-head">
        <div id="data-timestamp" class="data-timestamp">数据更新时间：加载中...</div>
        <div>
          <button id="export-button" class="btn primary" type="button">导出当前筛选结果</button>
        </div>
      </div>
      <div id="filters" class="filters"></div>
    </section>

    <section class="card table-card">
      <div id="table-status" class="status">加载中...</div>
      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              <th>客户昵称</th>
              <th>手机号</th>
              <th>跟进人</th>
              <th>当前标签</th>
              <th>external_userid</th>
              <th>更新时间</th>
            </tr>
          </thead>
          <tbody id="table-body"></tbody>
        </table>
      </div>
    </section>

    <section class="ext-note">
      已预留 `status_fields.operation_flags`、`reserved_filters` 和表格扩展位，后续可以继续接“是否执行动作”“是否已加微”“是否已绑定手机号”“手机号批量比对结果”等运营字段。
    </section>
  </div>

  <script>
    const state = {
      filter: '',
      definitions: [],
      stats: [],
      items: [],
    };
    const statsEl = document.getElementById('stats');
    const filtersEl = document.getElementById('filters');
    const tableBodyEl = document.getElementById('table-body');
    const tableStatusEl = document.getElementById('table-status');
    const dataTimestampEl = document.getElementById('data-timestamp');
    const refreshButton = document.getElementById('refresh-button');
    const initButton = document.getElementById('init-button');
    const exportButton = document.getElementById('export-button');

    async function fetchJson(url, options) {
      const response = await fetch(url, options);
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || payload.ok === false) {
        throw new Error(payload.error || ('请求失败(' + response.status + ')'));
      }
      return payload;
    }

    function renderStats() {
      statsEl.innerHTML = state.stats.map((item) => (
        '<article class="stat"><div class="stat-label">' + item.label + '</div><div class="stat-value">' + item.count + '</div></article>'
      )).join('');
    }

    function renderFilters() {
      const chips = [
        '<button type="button" class="chip' + (state.filter ? '' : ' active') + '" data-filter="">全部</button>'
      ].concat(state.definitions.map((item) => (
        '<button type="button" class="chip' + (state.filter === item.signup_status ? ' active' : '') + '" data-filter="' + item.signup_status + '">' + item.label + '</button>'
      )));
      filtersEl.innerHTML = chips.join('');
      Array.from(filtersEl.querySelectorAll('.chip')).forEach((button) => {
        button.addEventListener('click', () => {
          state.filter = button.getAttribute('data-filter') || '';
          loadList();
        });
      });
    }

    function renderTable() {
      if (!state.items.length) {
        tableBodyEl.innerHTML = '<tr><td class="empty" colspan="6">当前筛选下暂无用户</td></tr>';
        tableStatusEl.textContent = '已加载 0 条';
        tableStatusEl.className = 'status';
        return;
      }
      tableBodyEl.innerHTML = state.items.map((item) => {
        const tagName = (((item || {}).status_fields || {}).current_tag_name) || '-';
        return '<tr>'
          + '<td>' + (item.customer_name || '-') + '</td>'
          + '<td>' + (item.mobile || '-') + '</td>'
          + '<td>' + (item.follow_user_display_name || item.follow_user_userid || '-') + '</td>'
          + '<td><span class="tag-pill">' + tagName + '</span></td>'
          + '<td>' + (item.external_userid || '-') + '</td>'
          + '<td>' + (item.updated_at || '-') + '</td>'
          + '</tr>';
      }).join('');
      tableStatusEl.textContent = '已加载 ' + state.items.length + ' 条';
      tableStatusEl.className = 'status';
    }

    async function loadList() {
      tableStatusEl.textContent = '加载中...';
      tableStatusEl.className = 'status';
      const params = new URLSearchParams();
      if (state.filter) params.set('signup_status', state.filter);
      try {
        const result = await fetchJson('/api/admin/class-user-management?' + params.toString());
        state.definitions = Array.isArray(result.status_definitions) ? result.status_definitions : [];
        state.stats = Array.isArray(result.stats) ? result.stats : [];
        state.items = Array.isArray(result.items) ? result.items : [];
        renderStats();
        renderFilters();
        renderTable();
        const generatedAt = ((((result || {}).meta || {}).data_generated_at) || '');
        dataTimestampEl.textContent = '数据更新时间：' + (generatedAt || '-');
        const initState = (result.tag_initialization || {});
        initButton.textContent = initState.initialized ? '重新检查标签' : '检查并补齐标签';
      } catch (error) {
        tableStatusEl.textContent = error.message || '加载失败';
        tableStatusEl.className = 'status error';
        tableBodyEl.innerHTML = '';
        dataTimestampEl.textContent = '数据更新时间：加载失败';
      }
    }

    exportButton.addEventListener('click', () => {
      const params = new URLSearchParams();
      if (state.filter) params.set('signup_status', state.filter);
      window.location.href = '/api/admin/class-user-management/export?' + params.toString();
    });

    refreshButton.addEventListener('click', async () => {
      refreshButton.disabled = true;
      try {
        await loadList();
      } finally {
        refreshButton.disabled = false;
      }
    });

    initButton.addEventListener('click', async () => {
      initButton.disabled = true;
      try {
        await fetchJson('/api/admin/class-user-management/bootstrap', { method: 'POST' });
        await loadList();
      } finally {
        initButton.disabled = false;
      }
    });

    loadList().catch((error) => {
      tableStatusEl.textContent = error.message || '初始化失败';
      tableStatusEl.className = 'status error';
    });
  </script>
</body>
</html>
        """
    )


@bp.route("/admin/class-user-backoffice/ui", methods=["GET"])
def admin_class_user_backoffice_ui():
    return render_template_string(
        """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>班期用户运营后台</title>
  <style>
    :root {
      --bg: #f4efe6;
      --panel: rgba(255,255,255,0.96);
      --line: rgba(62, 48, 25, 0.12);
      --text: #2a2012;
      --muted: #77654b;
      --brand: #8c5e31;
      --brand-strong: #684421;
      --soft: #f5e8d6;
      --danger: #ab533a;
      --ok: #2b7a57;
      --shadow: 0 20px 40px rgba(72, 54, 29, 0.08);
      --radius: 24px;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--text);
      font-family: "PingFang SC", "Helvetica Neue", -apple-system, BlinkMacSystemFont, sans-serif;
      background:
        radial-gradient(circle at top right, rgba(192, 140, 77, 0.16), transparent 28%),
        linear-gradient(180deg, #fbf8f3 0%, var(--bg) 100%);
    }
    button { font: inherit; }
    .shell { max-width: 1480px; margin: 0 auto; padding: 28px 16px 42px; }
    .hero, .card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      backdrop-filter: blur(10px);
    }
    .hero { padding: 24px; margin-bottom: 18px; }
    .hero-head, .toolbar, .split { display: flex; gap: 14px; flex-wrap: wrap; justify-content: space-between; align-items: center; }
    h1 { margin: 0 0 10px; font-size: 30px; }
    .hero p { margin: 0; color: var(--muted); line-height: 1.7; max-width: 760px; }
    .stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-top: 18px; }
    .stat { padding: 16px; border-radius: 18px; background: #fffdf9; border: 1px solid rgba(62, 48, 25, 0.08); }
    .stat .label { color: var(--muted); font-size: 13px; margin-bottom: 6px; }
    .stat .value { font-size: 28px; font-weight: 700; }
    .toolbar.card, .card { padding: 18px; margin-bottom: 16px; }
    .tabs, .filters, .actions { display: flex; gap: 10px; flex-wrap: wrap; }
    .pill, .chip, .btn {
      border-radius: 999px;
      border: 1px solid rgba(62, 48, 25, 0.12);
      background: #fffdfa;
      color: var(--text);
      padding: 10px 14px;
      cursor: pointer;
      font-weight: 700;
    }
    .pill.active, .chip.active, .btn.primary {
      color: #fff;
      border-color: transparent;
      background: linear-gradient(135deg, var(--brand), var(--brand-strong));
    }
    .btn.ghost { background: var(--soft); color: var(--brand-strong); border-color: transparent; }
    .caption { color: var(--muted); font-size: 13px; }
    .panel-title { margin: 0 0 6px; font-size: 18px; }
    .panel-subtitle { margin: 0; color: var(--muted); font-size: 14px; line-height: 1.6; }
    .status { color: var(--muted); padding: 12px 0 16px; }
    .status.error { color: var(--danger); }
    .table-wrap { overflow-x: auto; }
    table { width: 100%; border-collapse: collapse; min-width: 980px; }
    th, td { padding: 13px 14px; text-align: left; border-bottom: 1px solid rgba(62, 48, 25, 0.08); font-size: 14px; vertical-align: top; }
    th { color: var(--muted); background: rgba(245, 232, 214, 0.45); font-weight: 600; }
    .tag { display: inline-flex; align-items: center; padding: 6px 10px; border-radius: 999px; background: var(--soft); color: var(--brand-strong); font-weight: 700; font-size: 12px; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; }
    .two-col { display: grid; grid-template-columns: 1.6fr 1fr; gap: 16px; }
    @media (max-width: 1080px) {
      .stats, .two-col { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <section class="hero">
      <div class="hero-head">
        <div>
          <h1>班期用户运营后台</h1>
          <p>新后台直接围绕本地 `class_user_status_current` 和 `class_user_status_history` 两张表工作。当前页分成“当前状态池”和“操作历史”两个视图，后续接动作状态、进群、打卡都能在这层继续扩。</p>
        </div>
        <div class="actions">
          <button id="bootstrap-btn" class="btn ghost" type="button">检查标签</button>
          <button id="migrate-btn" class="btn ghost" type="button">执行迁移</button>
          <button id="reload-btn" class="btn ghost" type="button">重新加载</button>
          <button id="export-btn" class="btn primary" type="button">导出当前列表</button>
        </div>
      </div>
      <div id="stats" class="stats"></div>
    </section>

    <section class="toolbar card">
      <div class="split">
        <div class="tabs" id="tabs"></div>
        <div class="caption" id="data-timestamp">数据更新时间：加载中...</div>
      </div>
      <div id="filters" class="filters" style="margin-top:14px;"></div>
    </section>

    <section class="two-col">
      <article class="card">
        <h2 class="panel-title">当前状态池</h2>
        <p class="panel-subtitle">按当前唯一状态查看主数据。这个列表只来自 `class_user_status_current`。</p>
        <div id="current-status" class="status">加载中...</div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>客户昵称</th>
                <th>手机号</th>
                <th>跟进人</th>
                <th>当前状态</th>
                <th>external_userid</th>
                <th>更新时间</th>
              </tr>
            </thead>
            <tbody id="current-body"></tbody>
          </table>
        </div>
      </article>

      <article class="card">
        <h2 class="panel-title">最近操作历史</h2>
        <p class="panel-subtitle">最近 100 条变更日志，方便快速看谁改了什么、企微同步有没有失败。</p>
        <div id="history-status" class="status">加载中...</div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>变更时间</th>
                <th>客户</th>
                <th>旧状态</th>
                <th>新状态</th>
                <th>操作人</th>
                <th>企微同步</th>
              </tr>
            </thead>
            <tbody id="history-body"></tbody>
          </table>
        </div>
      </article>
    </section>
  </div>

  <script>
    const state = {
      tab: 'current',
      filter: '',
      definitions: [],
      stats: [],
      items: [],
      history: [],
    };

    const statsEl = document.getElementById('stats');
    const tabsEl = document.getElementById('tabs');
    const filtersEl = document.getElementById('filters');
    const currentStatusEl = document.getElementById('current-status');
    const currentBodyEl = document.getElementById('current-body');
    const historyStatusEl = document.getElementById('history-status');
    const historyBodyEl = document.getElementById('history-body');
    const timestampEl = document.getElementById('data-timestamp');

    async function fetchJson(url, options) {
      const response = await fetch(url, options);
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || payload.ok === false) {
        throw new Error(payload.error || ('请求失败(' + response.status + ')'));
      }
      return payload;
    }

    function renderStats() {
      const total = state.items.length;
      const cards = [
        { label: '当前总人数', value: total },
        ...state.stats.map((item) => ({ label: item.label, value: item.count }))
      ];
      statsEl.innerHTML = cards.map((item) => (
        '<article class="stat"><div class="label">' + item.label + '</div><div class="value">' + item.value + '</div></article>'
      )).join('');
    }

    function renderTabs() {
      const tabs = [
        { key: 'current', label: '当前状态池' },
        { key: 'history', label: '操作历史' },
      ];
      tabsEl.innerHTML = tabs.map((item) => (
        '<button type="button" class="pill' + (state.tab === item.key ? ' active' : '') + '" data-tab="' + item.key + '">' + item.label + '</button>'
      )).join('');
      Array.from(tabsEl.querySelectorAll('.pill')).forEach((button) => {
        button.addEventListener('click', () => {
          state.tab = button.getAttribute('data-tab') || 'current';
          syncTabVisibility();
        });
      });
    }

    function renderFilters() {
      const chips = [
        '<button type="button" class="chip' + (state.filter ? '' : ' active') + '" data-filter="">全部</button>'
      ].concat(state.definitions.map((item) => (
        '<button type="button" class="chip' + (state.filter === item.signup_status ? ' active' : '') + '" data-filter="' + item.signup_status + '">' + item.label + '</button>'
      )));
      filtersEl.innerHTML = chips.join('');
      Array.from(filtersEl.querySelectorAll('.chip')).forEach((button) => {
        button.addEventListener('click', () => {
          state.filter = button.getAttribute('data-filter') || '';
          loadCurrent();
        });
      });
    }

    function renderCurrent() {
      if (!state.items.length) {
        currentBodyEl.innerHTML = '<tr><td colspan="6">当前筛选下暂无数据</td></tr>';
        currentStatusEl.textContent = '已加载 0 条';
        currentStatusEl.className = 'status';
        return;
      }
      currentBodyEl.innerHTML = state.items.map((item) => (
        '<tr>'
        + '<td>' + (item.customer_name || '-') + '</td>'
        + '<td>' + (item.mobile || '-') + '</td>'
        + '<td>' + (item.follow_user_display_name || item.follow_user_userid || '-') + '</td>'
        + '<td><span class="tag">' + ((((item || {}).status_fields || {}).current_tag_name) || '-') + '</span></td>'
        + '<td class="mono">' + (item.external_userid || '-') + '</td>'
        + '<td>' + (item.updated_at || '-') + '</td>'
        + '</tr>'
      )).join('');
      currentStatusEl.textContent = '已加载 ' + state.items.length + ' 条';
      currentStatusEl.className = 'status';
    }

    function renderHistory() {
      if (!state.history.length) {
        historyBodyEl.innerHTML = '<tr><td colspan="6">暂无历史记录</td></tr>';
        historyStatusEl.textContent = '已加载 0 条';
        historyStatusEl.className = 'status';
        return;
      }
      historyBodyEl.innerHTML = state.history.map((item) => (
        '<tr>'
        + '<td>' + (item.set_at || item.created_at || '-') + '</td>'
        + '<td>' + ((item.customer_name_snapshot || '-') + '<div class="mono">' + (item.external_userid || '-') + '</div>') + '</td>'
        + '<td>' + (item.old_label_name || item.old_signup_status || '-') + '</td>'
        + '<td><span class="tag">' + (item.new_label_name || item.new_signup_status || '-') + '</span></td>'
        + '<td>' + (item.set_by_userid || '-') + '</td>'
        + '<td>' + ((item.wecom_tag_sync_status || '-') + ((item.wecom_tag_sync_error || '') ? '<div>' + item.wecom_tag_sync_error + '</div>' : '')) + '</td>'
        + '</tr>'
      )).join('');
      historyStatusEl.textContent = '已加载 ' + state.history.length + ' 条';
      historyStatusEl.className = 'status';
    }

    function syncTabVisibility() {
      const currentCard = currentStatusEl.closest('.card');
      const historyCard = historyStatusEl.closest('.card');
      currentCard.style.display = state.tab === 'current' ? '' : 'none';
      historyCard.style.display = state.tab === 'history' ? '' : 'none';
      filtersEl.style.display = state.tab === 'current' ? '' : 'none';
    }

    async function loadCurrent() {
      currentStatusEl.textContent = '加载中...';
      currentStatusEl.className = 'status';
      const params = new URLSearchParams();
      if (state.filter) params.set('signup_status', state.filter);
      const result = await fetchJson('/api/admin/class-user-management?' + params.toString());
      state.definitions = Array.isArray(result.status_definitions) ? result.status_definitions : [];
      state.stats = Array.isArray(result.stats) ? result.stats : [];
      state.items = Array.isArray(result.items) ? result.items : [];
      renderStats();
      renderFilters();
      renderCurrent();
      timestampEl.textContent = '数据更新时间：' + (((result.meta || {}).data_generated_at) || '-');
    }

    async function loadHistory() {
      historyStatusEl.textContent = '加载中...';
      historyStatusEl.className = 'status';
      const result = await fetchJson('/api/admin/class-user-management/history?limit=100');
      state.history = Array.isArray(result.items) ? result.items : [];
      renderHistory();
    }

    async function boot() {
      renderTabs();
      syncTabVisibility();
      await Promise.all([loadCurrent(), loadHistory()]);
    }

    document.getElementById('reload-btn').addEventListener('click', async () => {
      await Promise.all([loadCurrent(), loadHistory()]);
    });
    document.getElementById('bootstrap-btn').addEventListener('click', async () => {
      await fetchJson('/api/admin/class-user-management/bootstrap', { method: 'POST' });
      await loadCurrent();
    });
    document.getElementById('migrate-btn').addEventListener('click', async () => {
      await fetchJson('/api/admin/class-user-management/migrate', { method: 'POST' });
      await Promise.all([loadCurrent(), loadHistory()]);
    });
    document.getElementById('export-btn').addEventListener('click', () => {
      const params = new URLSearchParams();
      if (state.filter) params.set('signup_status', state.filter);
      window.location.href = '/api/admin/class-user-management/export?' + params.toString();
    });

    boot().catch((error) => {
      currentStatusEl.textContent = error.message || '初始化失败';
      currentStatusEl.className = 'status error';
      historyStatusEl.textContent = error.message || '初始化失败';
      historyStatusEl.className = 'status error';
    });
  </script>
</body>
</html>
        """
    )


@bp.route("/admin/questionnaires/ui", methods=["GET"])
def admin_questionnaires_ui():
    return render_template_string(
        """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>问卷后台</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f4f7f2;
      --panel: rgba(255, 255, 255, 0.96);
      --line: rgba(34, 65, 49, 0.10);
      --line-strong: rgba(34, 65, 49, 0.18);
      --text: #183025;
      --muted: #69796f;
      --soft: #eef5ef;
      --primary: #2f6d4c;
      --primary-strong: #24553b;
      --danger: #a34f39;
      --warning-bg: #fff6dc;
      --warning-text: #7a5a16;
      --shadow: 0 18px 42px rgba(24, 49, 38, 0.06);
      --shadow-soft: 0 10px 24px rgba(24, 49, 38, 0.04);
      --radius-xl: 24px;
      --radius-lg: 18px;
      --radius-md: 14px;
      --radius-sm: 10px;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: "PingFang SC", "Helvetica Neue", -apple-system, BlinkMacSystemFont, sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at top left, rgba(70, 129, 94, 0.10), transparent 26%),
        radial-gradient(circle at bottom right, rgba(47, 109, 76, 0.08), transparent 20%),
        var(--bg);
    }
    button, input, textarea, select { font: inherit; }
    button {
      cursor: pointer;
      border: 0;
      transition: transform 0.18s ease, box-shadow 0.18s ease, opacity 0.18s ease;
    }
    button:hover { transform: translateY(-1px); }
    button:disabled { opacity: 0.52; cursor: not-allowed; transform: none; box-shadow: none; }
    .hidden { display: none !important; }
    .shell { min-height: 100vh; padding: 18px; }
    .topbar {
      position: sticky;
      top: 0;
      z-index: 30;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin: 0 auto 14px;
      max-width: 1600px;
      min-height: 68px;
      padding: 12px 16px;
      border: 1px solid var(--line);
      border-radius: 18px;
      background: rgba(255, 255, 255, 0.88);
      backdrop-filter: blur(14px);
      box-shadow: var(--shadow-soft);
    }
    .topbar-meta-wrap { min-width: 0; display: flex; align-items: center; }
    .topbar h1 {
      margin: 0;
      font-size: clamp(20px, 2.2vw, 28px);
      line-height: 1.12;
      letter-spacing: -0.03em;
    }
    .topbar-actions,
    .mini-actions,
    .field-grid,
    .header-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
    .btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      min-height: 40px;
      padding: 10px 15px;
      border-radius: 999px;
      font-weight: 700;
    }
    .btn.primary {
      color: #fff;
      background: linear-gradient(135deg, var(--primary) 0%, var(--primary-strong) 100%);
      box-shadow: 0 12px 24px rgba(34, 79, 56, 0.16);
    }
    .btn.secondary {
      color: var(--primary);
      background: #e3eee5;
    }
    .btn.ghost {
      color: var(--text);
      background: #f7faf7;
      border: 1px solid var(--line);
    }
    .btn.danger {
      color: #fff;
      background: linear-gradient(135deg, #b45a41 0%, #98432e 100%);
    }
    .workspace {
      max-width: 1600px;
      margin: 0 auto;
      display: grid;
      grid-template-columns: 320px minmax(0, 1fr) 380px;
      gap: 16px;
      align-items: start;
    }
    .card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: var(--radius-xl);
      box-shadow: var(--shadow);
      backdrop-filter: blur(16px);
    }
    .sidebar,
    .inspector-column {
      position: sticky;
      top: 86px;
      display: grid;
      gap: 14px;
      max-height: calc(100vh - 104px);
      align-content: start;
    }
    .tag-status,
    .inline-alert {
      padding: 10px 12px;
      border-radius: var(--radius-md);
      font-size: 13px;
      line-height: 1.6;
      background: #eef6ee;
      color: var(--primary);
      white-space: pre-wrap;
    }
    .inline-alert.warning {
      background: var(--warning-bg);
      color: var(--warning-text);
    }
    .inline-alert.error {
      background: #fbebea;
      color: #8c4130;
    }
    .section-card { padding: 16px; }
    .section-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      margin-bottom: 12px;
    }
    .section-head h3,
    .section-head h2 {
      margin: 0;
      font-size: 16px;
    }
    .section-subtitle {
      margin: 2px 0 0;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.5;
    }
    .tool-grid {
      display: grid;
      gap: 8px;
    }
    .tool-card {
      display: flex;
      gap: 12px;
      width: 100%;
      padding: 14px;
      text-align: left;
      border-radius: 16px;
      background: #f8fbf8;
      border: 1px solid rgba(45, 107, 74, 0.10);
      color: var(--text);
    }
    .tool-card .tool-mark {
      width: 38px;
      height: 38px;
      border-radius: 12px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      background: #e9f2ea;
      color: var(--primary);
      font-weight: 800;
      font-size: 14px;
      flex-shrink: 0;
    }
    .tool-card strong {
      display: block;
      margin-bottom: 3px;
      font-size: 14px;
    }
    .tool-card span {
      display: block;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.5;
    }
    .questionnaire-list {
      display: grid;
      gap: 10px;
      max-height: 540px;
      overflow: auto;
      padding-right: 4px;
    }
    .list-item {
      padding: 12px;
      border-radius: 16px;
      border: 1px solid rgba(45, 107, 74, 0.10);
      background: #f9fbf8;
    }
    .list-item.active {
      border-color: rgba(45, 107, 74, 0.28);
      box-shadow: 0 8px 18px rgba(34, 79, 56, 0.06);
    }
    .list-item h4 {
      margin: 0 0 4px;
      font-size: 14px;
      line-height: 1.4;
    }
    .meta-row {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-bottom: 8px;
    }
    .pill {
      display: inline-flex;
      align-items: center;
      padding: 4px 8px;
      border-radius: 999px;
      background: #e8f1e7;
      color: var(--primary);
      font-size: 12px;
      font-weight: 700;
    }
    .pill.disabled {
      background: #f7e9e4;
      color: #93452f;
    }
    .list-item .muted {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.6;
      margin-bottom: 8px;
    }
    .mini-actions .mini-btn {
      padding: 7px 9px;
      border-radius: 10px;
      background: #ffffff;
      border: 1px solid rgba(45, 107, 74, 0.10);
      color: var(--text);
      font-size: 12px;
      font-weight: 700;
    }
    .mini-actions .mini-btn.danger {
      color: #8c4130;
      background: #fbefec;
      border-color: rgba(165, 79, 56, 0.12);
    }
    .preview-column { min-width: 0; }
    .phone-stage {
      min-height: calc(100vh - 104px);
      padding: 18px;
      display: grid;
      place-items: center;
    }
    .phone-frame {
      width: min(100%, 480px);
      padding: 12px;
      border-radius: 30px;
      background: linear-gradient(180deg, #edf3ed 0%, #dfe8df 100%);
      border: 1px solid rgba(45, 107, 74, 0.12);
      box-shadow: 0 24px 48px rgba(24, 49, 38, 0.08);
    }
    .phone-topbar {
      display: flex;
      justify-content: center;
      margin-bottom: 12px;
    }
    .phone-notch {
      width: 34%;
      height: 24px;
      border-radius: 999px;
      background: rgba(24, 49, 38, 0.88);
    }
    .phone-screen {
      min-height: 720px;
      padding: 16px 14px 18px;
      border-radius: 22px;
      background:
        radial-gradient(circle at top left, rgba(77, 132, 99, 0.10), transparent 26%),
        #fcfdfb;
      border: 1px solid rgba(255,255,255,0.65);
    }
    .preview-head {
      padding: 16px;
      border-radius: 18px;
      background: #ffffff;
      border: 1px solid rgba(45, 107, 74, 0.10);
      box-shadow: var(--shadow-soft);
      cursor: pointer;
    }
    .preview-head.active,
    .preview-question.active,
    .preview-rule.active {
      border-color: rgba(45, 107, 74, 0.34);
      box-shadow: 0 0 0 3px rgba(45, 107, 74, 0.08);
    }
    .preview-head h2 {
      margin: 8px 0 6px;
      font-size: 24px;
      line-height: 1.12;
      letter-spacing: -0.03em;
    }
    .preview-head p {
      margin: 0;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.7;
      white-space: pre-wrap;
    }
    .preview-stack {
      display: grid;
      gap: 10px;
      margin-top: 12px;
    }
    .preview-question,
    .preview-rule {
      padding: 14px;
      border-radius: 16px;
      background: #ffffff;
      border: 1px solid rgba(45, 107, 74, 0.10);
      cursor: pointer;
    }
    .preview-question h4,
    .preview-rule h4 {
      margin: 8px 0 6px;
      font-size: 16px;
      line-height: 1.5;
    }
    .preview-question .muted,
    .preview-rule .muted {
      color: var(--muted);
      font-size: 13px;
      line-height: 1.6;
    }
    .question-type {
      display: inline-flex;
      align-items: center;
      padding: 5px 10px;
      border-radius: 999px;
      background: var(--soft);
      color: var(--primary);
      font-size: 12px;
      font-weight: 700;
    }
    .preview-options {
      display: grid;
      gap: 8px;
      margin-top: 12px;
    }
    .option-pill {
      padding: 9px 11px;
      border-radius: 12px;
      background: #f7faf7;
      border: 1px solid rgba(45, 107, 74, 0.08);
      font-size: 13px;
      color: var(--text);
    }
    .preview-footer-note {
      margin-top: 14px;
      padding: 12px 14px;
      border-radius: 16px;
      background: linear-gradient(135deg, rgba(45, 107, 74, 0.08), rgba(45, 107, 74, 0.03));
      color: var(--muted);
      font-size: 13px;
      line-height: 1.7;
    }
    .inspector-card {
      padding: 16px;
      min-height: calc(100vh - 104px);
      overflow: auto;
    }
    .config-group {
      padding: 14px;
      border-radius: 16px;
      background: #f9fbf8;
      border: 1px solid rgba(45, 107, 74, 0.10);
      margin-bottom: 12px;
    }
    .config-group h3 {
      margin: 0;
      font-size: 16px;
    }
    .config-group p {
      margin: 6px 0 0;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.6;
    }
    .config-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      margin-bottom: 14px;
    }
    .field {
      display: block;
      margin-bottom: 12px;
      font-size: 13px;
      font-weight: 700;
      color: var(--text);
    }
    .field-grid.compact { display: grid; gap: 10px; grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .field-grid.triple { display: grid; gap: 10px; grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .field input[type="text"],
    .field textarea,
    .field select {
      width: 100%;
      margin-top: 7px;
      padding: 12px 13px;
      border-radius: 14px;
      border: 1px solid rgba(45, 107, 74, 0.14);
      background: #ffffff;
      color: var(--text);
      outline: none;
    }
    .field textarea { min-height: 96px; resize: vertical; }
    .field input[type="checkbox"] { margin-right: 8px; }
    .option-editor {
      padding: 12px;
      border-radius: 14px;
      background: #ffffff;
      border: 1px solid rgba(45, 107, 74, 0.10);
      margin-bottom: 12px;
    }
    .rule-nav-list {
      display: grid;
      gap: 10px;
      margin-bottom: 12px;
    }
    .rule-nav-item {
      width: 100%;
      padding: 12px 14px;
      text-align: left;
      border-radius: 14px;
      background: #ffffff;
      border: 1px solid rgba(45, 107, 74, 0.10);
      color: var(--text);
    }
    .rule-nav-item.active {
      border-color: rgba(45, 107, 74, 0.28);
      box-shadow: 0 0 0 3px rgba(45, 107, 74, 0.08);
    }
    .rule-nav-item strong {
      display: block;
      font-size: 14px;
      margin-bottom: 4px;
    }
    .rule-nav-item span {
      display: block;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.5;
    }
    .option-editor-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 10px;
    }
    .mini-label {
      color: var(--primary);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }
    .link-btn {
      padding: 0;
      background: transparent;
      color: var(--primary);
      font-size: 13px;
      font-weight: 700;
    }
    .link-btn.danger { color: #93452f; }
    .tag-badges {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 10px;
      min-height: 30px;
    }
    .tag-badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 7px 10px;
      border-radius: 999px;
      background: #e8f2e9;
      color: var(--primary);
      font-size: 12px;
      font-weight: 700;
    }
    .tag-badge.unknown {
      background: #f0f1ed;
      color: #6d746d;
    }
    .tag-inline { margin-top: 10px; }
    .tag-fallback {
      margin-top: 10px;
      border-top: 1px dashed rgba(45, 107, 74, 0.16);
      padding-top: 10px;
    }
    .tag-fallback summary {
      cursor: pointer;
      color: var(--muted);
      font-size: 13px;
      font-weight: 700;
    }
    .helper-note {
      margin-top: 10px;
      padding: 12px 14px;
      border-radius: 16px;
      background: #f4f7f2;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.6;
    }
    .empty-state {
      padding: 24px 18px;
      border-radius: 18px;
      border: 1px dashed rgba(45, 107, 74, 0.16);
      color: var(--muted);
      text-align: center;
      font-size: 14px;
      line-height: 1.7;
      background: rgba(255,255,255,0.7);
    }
    .tag-modal-overlay {
      position: fixed;
      inset: 0;
      z-index: 90;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 20px;
      background: rgba(14, 25, 18, 0.38);
      backdrop-filter: blur(8px);
    }
    .tag-modal {
      width: min(960px, 100%);
      max-height: calc(100vh - 40px);
      overflow: auto;
      padding: 18px;
      border-radius: 24px;
      border: 1px solid var(--line);
      background: #ffffff;
      box-shadow: 0 28px 72px rgba(14, 25, 18, 0.22);
    }
    .tag-modal-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 14px;
    }
    .tag-modal-head h3 {
      margin: 0;
      font-size: 22px;
      line-height: 1.15;
    }
    .tag-modal-search {
      width: 100%;
      margin: 12px 0 16px;
      padding: 12px 13px;
      border-radius: 14px;
      border: 1px solid rgba(45, 107, 74, 0.14);
      background: #fbfdfb;
    }
    .tag-modal-grid {
      display: grid;
      grid-template-columns: minmax(0, 1.3fr) minmax(260px, 0.9fr);
      gap: 14px;
    }
    .tag-group-list,
    .tag-selected-panel {
      padding: 14px;
      border-radius: 18px;
      background: #f8fbf8;
      border: 1px solid rgba(45, 107, 74, 0.10);
    }
    .tag-group {
      margin-bottom: 16px;
    }
    .tag-group:last-child { margin-bottom: 0; }
    .tag-group-title {
      margin: 0 0 10px;
      color: var(--text);
      font-size: 14px;
      font-weight: 700;
    }
    .tag-chip-grid {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
    .tag-chip {
      padding: 8px 10px;
      border-radius: 999px;
      border: 1px solid rgba(45, 107, 74, 0.14);
      background: #ffffff;
      color: var(--text);
      font-size: 12px;
      font-weight: 700;
    }
    .tag-chip.active {
      background: #e8f2e9;
      color: var(--primary);
      border-color: rgba(45, 107, 74, 0.24);
    }
    .tag-selected-panel h4 {
      margin: 0 0 10px;
      font-size: 14px;
    }
    .tag-modal-actions {
      display: flex;
      justify-content: flex-end;
      gap: 8px;
      margin-top: 16px;
    }
    .drawer-overlay {
      position: fixed;
      inset: 0;
      z-index: 60;
      display: flex;
      justify-content: flex-end;
      background: rgba(12, 23, 17, 0.34);
      backdrop-filter: blur(8px);
      padding: 16px;
    }
    .drawer-panel {
      width: min(460px, 100%);
      height: calc(100vh - 32px);
      border-radius: 28px;
      background: #ffffff;
      border: 1px solid rgba(45, 107, 74, 0.10);
      box-shadow: 0 30px 70px rgba(12, 23, 17, 0.20);
      padding: 20px;
      overflow: auto;
    }
    .drawer-panel h3 {
      margin: 6px 0 16px;
      font-size: 22px;
      line-height: 1.15;
    }
    .drawer-row {
      display: grid;
      gap: 4px;
      padding: 12px 0;
      border-bottom: 1px solid rgba(45, 107, 74, 0.08);
    }
    .drawer-row span {
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    .drawer-row strong {
      color: var(--text);
      font-size: 14px;
      line-height: 1.6;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .toast {
      position: fixed;
      top: 24px;
      right: 24px;
      z-index: 80;
      min-width: 220px;
      max-width: 320px;
      padding: 14px 16px;
      border-radius: 16px;
      background: rgba(24, 49, 38, 0.92);
      color: #fff;
      box-shadow: 0 20px 40px rgba(12, 23, 17, 0.18);
      font-size: 14px;
      line-height: 1.6;
    }
    .toast.error { background: rgba(148, 60, 42, 0.96); }
    @media (max-width: 1260px) {
      .workspace { grid-template-columns: 300px minmax(0, 1fr); }
      .inspector-column {
        position: static;
        max-height: none;
        grid-column: 1 / -1;
      }
      .inspector-card { min-height: auto; }
      .tag-modal-grid { grid-template-columns: 1fr; }
    }
    @media (max-width: 980px) {
      .shell { padding: 14px; }
      .topbar {
        position: static;
        padding: 12px 14px;
        border-radius: 16px;
      }
      .workspace { grid-template-columns: 1fr; }
      .sidebar {
        position: static;
        max-height: none;
      }
      .phone-stage { min-height: auto; padding: 16px; }
      .phone-screen { min-height: 0; }
      .field-grid.compact,
      .field-grid.triple { grid-template-columns: 1fr; }
      .topbar-actions { width: 100%; }
      .topbar-actions .btn { flex: 1 1 160px; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <header class="topbar">
      <div class="topbar-meta-wrap">
        <h1 id="topbar-title">新建问卷</h1>
      </div>
      <div class="topbar-actions">
        <button id="reset-btn" type="button" class="btn ghost">重置当前</button>
        <button id="copy-link-btn" type="button" class="btn secondary">复制链接</button>
        <button id="save-btn" type="button" class="btn primary">保存问卷</button>
      </div>
    </header>

    <div class="workspace">
      <aside class="sidebar">
        <section class="card section-card">
          <div class="section-head">
            <div>
              <h3>题型 / 组件区</h3>
              <p class="section-subtitle">向当前问卷添加题目和分数规则。</p>
            </div>
          </div>
          <div class="header-actions" style="margin-bottom:12px;">
            <button id="new-btn" type="button" class="btn secondary">新建问卷</button>
            <button id="preflight-btn" type="button" class="btn ghost">环境检查</button>
          </div>
          <div id="tag-catalog-message" class="inline-alert hidden" style="margin-bottom:12px;">企微标签加载失败，可稍后重试或手工填写 tag_id</div>
          <div class="tool-grid">
            <button id="add-single" type="button" class="tool-card">
              <span class="tool-mark">单</span>
              <span><strong>添加单选题</strong><span>适合唯一选择，支持分值和标签。</span></span>
            </button>
            <button id="add-multi" type="button" class="tool-card">
              <span class="tool-mark">多</span>
              <span><strong>添加多选题</strong><span>适合多项选择，支持累积分值与标签。</span></span>
            </button>
            <button id="add-textarea" type="button" class="tool-card">
              <span class="tool-mark">文</span>
              <span><strong>添加文本题</strong><span>只保存文本内容，不参与评分。</span></span>
            </button>
            <button id="add-mobile" type="button" class="tool-card">
              <span class="tool-mark">号</span>
              <span><strong>添加手机号题</strong><span>单行手机号输入，提交后可自动绑定侧边栏手机号。</span></span>
            </button>
            <button id="add-rule" type="button" class="tool-card">
              <span class="tool-mark">规</span>
              <span><strong>添加分数规则</strong><span>按总分区间追加标签，用于 SCRM 写回。</span></span>
            </button>
          </div>
        </section>

        <section class="card section-card">
          <div class="section-head">
            <div>
              <h3>问卷列表</h3>
              <p class="section-subtitle">编辑、停用、删除、导出、复制链接、最近提交调试。</p>
            </div>
            <button id="reload-list-btn" type="button" class="btn ghost">刷新</button>
          </div>
          <div id="questionnaire-list" class="questionnaire-list"></div>
        </section>
      </aside>

      <main class="preview-column">
        <section class="card phone-stage">
          <div class="phone-frame">
            <div class="phone-topbar"><div class="phone-notch"></div></div>
            <div class="phone-screen">
              <div id="preview-head" class="preview-head"></div>
              <div id="preview-questions" class="preview-stack"></div>
              <div id="preview-rules-wrap" class="preview-stack"></div>
              <div class="preview-footer-note">这是实时预览区。点击任一题目或分数规则，右侧会切换到对应配置；点击问卷头部，则编辑问卷基础设置。</div>
            </div>
          </div>
        </section>
      </main>

      <aside class="inspector-column">
        <section class="card inspector-card">
          <div class="section-head">
            <div>
              <div class="eyebrow">配置区</div>
              <h2 id="inspector-title" style="margin:12px 0 0;font-size:24px;">问卷基础设置</h2>
              <p id="inspector-subtitle" class="section-subtitle">右侧只编辑当前选中项。</p>
            </div>
          </div>
          <div id="inspector-body"></div>
        </section>
      </aside>
    </div>

    <div id="tag-modal-overlay" class="tag-modal-overlay hidden">
      <div class="tag-modal">
        <div class="tag-modal-head">
          <div>
            <h3>选择标签</h3>
            <p class="section-subtitle">按标签组选择，确认后仅保存 tag_id。</p>
          </div>
          <button id="tag-modal-close" type="button" class="btn ghost">关闭</button>
        </div>
        <input id="tag-modal-search" class="tag-modal-search" type="text" placeholder="搜索标签名称或标签组">
        <div class="tag-modal-grid">
          <div id="tag-modal-groups" class="tag-group-list"></div>
          <div class="tag-selected-panel">
            <h4>已选标签</h4>
            <div id="tag-modal-selected" class="tag-badges"></div>
            <details class="tag-fallback">
              <summary>手工填写 tag_id 兜底</summary>
              <input id="tag-modal-manual" type="text" placeholder='例如 ["etxxx1","etxxx2"]' style="width:100%;margin-top:10px;padding:11px 12px;border-radius:12px;border:1px solid rgba(45,107,74,0.14);">
            </details>
          </div>
        </div>
        <div class="tag-modal-actions">
          <button id="tag-modal-cancel" type="button" class="btn ghost">取消</button>
          <button id="tag-modal-confirm" type="button" class="btn primary">确认选择</button>
        </div>
      </div>
    </div>

    <div id="drawer-overlay" class="drawer-overlay hidden">
      <div class="drawer-panel">
        <div class="section-head">
          <div>
            <h3 id="drawer-title">面板</h3>
          </div>
          <button id="drawer-close" type="button" class="btn ghost">关闭</button>
        </div>
        <div id="drawer-body"></div>
      </div>
    </div>

    <div id="toast" class="toast hidden"></div>
  </div>
  <script>
    const listEl = document.getElementById('questionnaire-list');
    const previewHeadEl = document.getElementById('preview-head');
    const previewQuestionsEl = document.getElementById('preview-questions');
    const previewRulesWrapEl = document.getElementById('preview-rules-wrap');
    const inspectorBodyEl = document.getElementById('inspector-body');
    const inspectorTitleEl = document.getElementById('inspector-title');
    const inspectorSubtitleEl = document.getElementById('inspector-subtitle');
    const topbarTitleEl = document.getElementById('topbar-title');
    const tagCatalogMessageEl = document.getElementById('tag-catalog-message');
    const drawerOverlayEl = document.getElementById('drawer-overlay');
    const drawerTitleEl = document.getElementById('drawer-title');
    const drawerBodyEl = document.getElementById('drawer-body');
    const toastEl = document.getElementById('toast');
    const tagModalOverlayEl = document.getElementById('tag-modal-overlay');
    const tagModalGroupsEl = document.getElementById('tag-modal-groups');
    const tagModalSelectedEl = document.getElementById('tag-modal-selected');
    const tagModalSearchEl = document.getElementById('tag-modal-search');
    const tagModalManualEl = document.getElementById('tag-modal-manual');

    const state = {
      list: [],
      availableTags: [],
      availableTagMap: new Map(),
      questionnaire: null,
      currentId: null,
      selection: { kind: 'questionnaire' },
      ruleMode: false,
      lastRuleKey: '',
      loadingList: false,
      tagModal: {
        open: false,
        search: '',
        selected: [],
        target: null,
      },
    };
    let localSeq = 0;
    let toastTimer = null;

    function nextLocalKey(prefix) {
      localSeq += 1;
      return `${prefix}_${Date.now()}_${localSeq}`;
    }

    function escapeHtml(value) {
      return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
    }

    function normalizeTagIds(value) {
      if (Array.isArray(value)) {
        return [...new Set(value.map((item) => String(item || '').trim()).filter(Boolean))];
      }
      if (typeof value === 'string' && value.trim()) {
        try {
          const parsed = JSON.parse(value);
          if (Array.isArray(parsed)) return normalizeTagIds(parsed);
        } catch (error) {
          return [...new Set(value.split(',').map((item) => item.trim()).filter(Boolean))];
        }
      }
      return [];
    }

    function parseManualTagInput(value) {
      if (!String(value || '').trim()) return [];
      try {
        const parsed = JSON.parse(value);
        return Array.isArray(parsed) ? normalizeTagIds(parsed) : [];
      } catch (error) {
        return normalizeTagIds(value);
      }
    }

    function formatQuestionType(type) {
      if (type === 'single_choice') return '单选题';
      if (type === 'multi_choice') return '多选题';
      if (type === 'textarea') return '文本题';
      if (type === 'mobile') return '手机号题';
      return type || '题目';
    }

    function buildUnknownTag(tagId) {
      return { tag_id: tagId, tag_name: `未知标签（${tagId}）`, group_name: '未知标签' };
    }

    function ensureTagKnown(tagId) {
      return state.availableTagMap.get(tagId) || buildUnknownTag(tagId);
    }

    function formatTagLabel(tag) {
      return `${tag.group_name || '未分组'} / ${tag.tag_name}`;
    }

    function formatTagGroupName(tag) {
      return tag.group_name || '未分组';
    }

    function buildTagBadges(tagIds) {
      const ids = normalizeTagIds(tagIds);
      if (!ids.length) return '<span class="tag-picker-note">未选择标签</span>';
      return ids.map((tagId) => {
        const tag = ensureTagKnown(tagId);
        const isUnknown = !state.availableTagMap.has(tagId);
        return `<span class="tag-badge${isUnknown ? ' unknown' : ''}">${escapeHtml(formatTagLabel(tag))}</span>`;
      }).join('');
    }

    function buildPublicUrl(questionnaire = state.questionnaire) {
      if (!questionnaire) return '';
      if (questionnaire.public_url) return questionnaire.public_url;
      const slug = String(questionnaire.slug || '').trim();
      return slug ? `${window.location.origin}/s/${slug}` : '';
    }

    function fieldLabel(fieldName) {
      const labels = {
        name: '问卷名称',
        title: '问卷标题',
        description: '问卷说明',
        redirect_url: '提交后跳转地址',
        slug: '分享标识',
        min_score: '最低分',
        max_score: '最高分',
        sort_order: '排序',
        required: '必填',
        option_text: '选项文案',
        score: '分值',
        tag_codes: '标签',
      };
      return labels[fieldName] || fieldName;
    }

    function questionLabel(rawTitle) {
      const title = String(rawTitle || '').trim();
      return title ? `题目“${title}”` : '该题目';
    }

    function humanizeErrorMessage(rawMessage, fallback = '操作失败，请稍后重试') {
      const message = String(rawMessage || '').trim();
      if (!message) return fallback;
      if (/[\u4e00-\u9fa5]/.test(message) && !/ is required|must be|unknown_|already_submitted|wechat_oauth_not_configured/i.test(message)) {
        return message;
      }

      if (message === 'name is required') return '请输入问卷名称';
      if (message === 'title is required') return '请输入问卷标题';
      if (message === 'questions must be an array') return '题目数据格式不正确，请重新添加题目';
      if (message === 'score must be an integer') return '分值必须填写数字';
      if (message === 'tag_codes must be an array') return '标签数据格式不正确，请重新选择标签';
      if (message === 'answers is required') return '请先填写问卷内容再提交';
      if (message === 'unknown question_id') return '检测到异常题目数据，请刷新页面后重试';
      if (message === 'already_submitted') return '你已经提交过这份问卷';
      if (message === 'wechat_oauth_not_configured') return '当前未完成微信授权配置，暂时无法使用该功能';
      if (message === 'question type must be single_choice, multi_choice, textarea or mobile') return '题型不正确，请重新选择题型';
      if (message === 'min_score must be an integer') return '最低分必须填写数字';
      if (message === 'max_score must be an integer') return '最高分必须填写数字';
      if (message === 'option_text is required') return '请输入选项文案';
      if (message === 'score rule min_score cannot be greater than max_score') return '请检查分数规则：最低分不能大于最高分';
      if (message === 'score rule tag_codes must be an array') return '分数规则标签格式不正确，请重新选择标签';

      let matched = message.match(/^([a-z_]+) is required$/i);
      if (matched) return `请输入${fieldLabel(matched[1])}`;

      matched = message.match(/^([a-z_]+) must be an integer$/i);
      if (matched) return `${fieldLabel(matched[1])}必须填写数字`;

      matched = message.match(/^question ['"]?(.*?)['"]? is required$/i);
      if (matched) return `${questionLabel(matched[1])}还未填写，请补充后再保存`;

      matched = message.match(/^question ['"]?(.*?)['"]? must have options$/i);
      if (matched) return `${questionLabel(matched[1])}至少需要一个选项，请补充后再保存`;

      matched = message.match(/^question ['"]?(.*?)['"]? has an invalid option$/i);
      if (matched) return `${questionLabel(matched[1])}存在无效选项，请检查选项内容`;

      matched = message.match(/^question ['"]?(.*?)['"]? only allows one option$/i);
      if (matched) return `${questionLabel(matched[1])}只能选择一个选项，请检查当前配置`;

      matched = message.match(/^unknown question_id:?/i);
      if (matched) return '检测到异常题目数据，请刷新页面后重试';

      if (/Failed to fetch|NetworkError|Load failed/i.test(message)) return '网络连接异常，请稍后重试';
      if (/Unexpected token|JSON/i.test(message)) return fallback;

      return fallback;
    }

    function showToast(message, isError = false) {
      if (!message) return;
      toastEl.textContent = message;
      toastEl.className = `toast${isError ? ' error' : ''}`;
      clearTimeout(toastTimer);
      toastTimer = window.setTimeout(() => {
        toastEl.className = 'toast hidden';
      }, isError ? 7800 : 4200);
    }

    function openDrawer(title, rows = []) {
      drawerTitleEl.textContent = title;
      drawerBodyEl.innerHTML = rows.map((row) => `
        <div class="drawer-row">
          <span>${escapeHtml(row.label || '')}</span>
          <strong>${escapeHtml(row.value || '-')}</strong>
        </div>
      `).join('');
      drawerOverlayEl.classList.remove('hidden');
    }

    function closeDrawer() {
      drawerOverlayEl.classList.add('hidden');
    }

    function openTagModal(target, selectedTagIds = []) {
      state.tagModal = {
        open: true,
        search: '',
        selected: normalizeTagIds(selectedTagIds),
        target,
      };
      tagModalSearchEl.value = '';
      tagModalManualEl.value = '';
      renderTagModal();
      tagModalOverlayEl.classList.remove('hidden');
    }

    function closeTagModal() {
      state.tagModal.open = false;
      state.tagModal.target = null;
      tagModalOverlayEl.classList.add('hidden');
    }

    function toggleModalTag(tagId) {
      const selected = new Set(state.tagModal.selected);
      if (selected.has(tagId)) {
        selected.delete(tagId);
      } else {
        selected.add(tagId);
      }
      state.tagModal.selected = [...selected];
      renderTagModal();
    }

    function groupedTagsForModal() {
      const keyword = state.tagModal.search.trim().toLowerCase();
      const tags = state.availableTags.filter((tag) => {
        if (!keyword) return true;
        const haystack = `${tag.group_name || ''} ${tag.tag_name || ''} ${tag.tag_id || ''}`.toLowerCase();
        return haystack.includes(keyword);
      });
      const groups = new Map();
      tags.forEach((tag) => {
        const groupName = formatTagGroupName(tag);
        if (!groups.has(groupName)) groups.set(groupName, []);
        groups.get(groupName).push(tag);
      });
      return [...groups.entries()];
    }

    function renderTagModal() {
      const groups = groupedTagsForModal();
      tagModalGroupsEl.innerHTML = groups.length
        ? groups.map(([groupName, tags]) => `
            <section class="tag-group">
              <h4 class="tag-group-title">${escapeHtml(groupName)}</h4>
              <div class="tag-chip-grid">
                ${tags.map((tag) => `
                  <button type="button" class="tag-chip${state.tagModal.selected.includes(tag.tag_id) ? ' active' : ''}" data-tag-id="${escapeHtml(tag.tag_id)}">
                    ${escapeHtml(tag.tag_name)}
                  </button>
                `).join('')}
              </div>
            </section>
          `).join('')
        : '<div class="empty-state">没有匹配到标签</div>';
      tagModalSelectedEl.innerHTML = buildTagBadges(state.tagModal.selected);
      tagModalGroupsEl.querySelectorAll('[data-tag-id]').forEach((button) => {
        button.addEventListener('click', () => toggleModalTag(button.dataset.tagId));
      });
    }

    function createOption(option = {}, index = 0) {
      return {
        id: option.id ?? null,
        local_key: option.local_key || nextLocalKey('option'),
        option_text: option.option_text || '',
        score: option.score ?? 0,
        tag_codes: normalizeTagIds(option.tag_codes || []),
        sort_order: option.sort_order ?? (index + 1),
      };
    }

    function createQuestion(type = 'single_choice', question = {}, index = 0) {
      const normalizedType = question.type || type;
      return {
        id: question.id ?? null,
        local_key: question.local_key || nextLocalKey('question'),
        type: normalizedType,
        title: question.title || '',
        required: Boolean(question.required),
        sort_order: question.sort_order ?? (index + 1),
        options: ['textarea', 'mobile'].includes(normalizedType)
          ? []
          : (question.options || []).map((option, optionIndex) => createOption(option, optionIndex)).length
            ? (question.options || []).map((option, optionIndex) => createOption(option, optionIndex))
            : [createOption({}, 0)],
      };
    }

    function createRule(rule = {}, index = 0) {
      return {
        id: rule.id ?? null,
        local_key: rule.local_key || nextLocalKey('rule'),
        min_score: rule.min_score ?? '',
        max_score: rule.max_score ?? '',
        tag_codes: normalizeTagIds(rule.tag_codes || []),
        sort_order: rule.sort_order ?? (index + 1),
      };
    }

    function blankQuestionnaire() {
      return {
        id: null,
        public_url: '',
        name: '',
        title: '',
        description: '',
        redirect_url: '',
        slug: '',
        is_disabled: false,
        questions: [],
        score_rules: [],
      };
    }

    function hydrateQuestionnaire(source = null) {
      const draft = blankQuestionnaire();
      const questionnaire = source || {};
      return {
        ...draft,
        id: questionnaire.id ?? null,
        public_url: questionnaire.public_url || '',
        name: questionnaire.name || '',
        title: questionnaire.title || '',
        description: questionnaire.description || '',
        redirect_url: questionnaire.redirect_url || '',
        slug: questionnaire.slug || '',
        is_disabled: Boolean(questionnaire.is_disabled),
        questions: (questionnaire.questions || []).map((question, index) => createQuestion(question.type || 'single_choice', question, index)),
        score_rules: (questionnaire.score_rules || []).map((rule, index) => createRule(rule, index)),
      };
    }

    function currentQuestion() {
      if (state.selection.kind !== 'question') return null;
      return state.questionnaire.questions.find((item) => item.local_key === state.selection.key) || null;
    }

    function currentRule() {
      if (state.selection.kind !== 'rule') return null;
      return state.questionnaire.score_rules.find((item) => item.local_key === state.selection.key) || null;
    }

    function selectQuestionnaire() {
      state.ruleMode = false;
      state.selection = { kind: 'questionnaire' };
      renderWorkspace();
    }

    function selectQuestion(key) {
      state.ruleMode = false;
      state.selection = { kind: 'question', key };
      renderWorkspace();
    }

    function selectRule(key) {
      state.ruleMode = true;
      state.lastRuleKey = key;
      state.selection = { kind: 'rule', key };
      renderWorkspace();
    }

    function enterRuleMode() {
      state.ruleMode = true;
      if (state.questionnaire.score_rules.length) {
        const remembered = state.questionnaire.score_rules.find((item) => item.local_key === state.lastRuleKey);
        const target = remembered || state.questionnaire.score_rules[0];
        state.lastRuleKey = target.local_key;
        state.selection = { kind: 'rule', key: target.local_key };
      } else {
        state.lastRuleKey = '';
        state.selection = { kind: 'questionnaire' };
      }
      renderWorkspace();
    }

    function resetDraft(data = null) {
      state.questionnaire = hydrateQuestionnaire(data);
      state.currentId = state.questionnaire.id;
      state.ruleMode = false;
      state.lastRuleKey = state.questionnaire.score_rules[0]?.local_key || '';
      state.selection = { kind: 'questionnaire' };
      renderWorkspace();
    }

    function serializePayload() {
      return {
        name: state.questionnaire.name,
        title: state.questionnaire.title,
        description: state.questionnaire.description,
        redirect_url: state.questionnaire.redirect_url,
        slug: state.questionnaire.slug,
        is_disabled: state.questionnaire.is_disabled,
        questions: state.questionnaire.questions.map((question, index) => {
          const payload = {
            type: question.type,
            title: question.title,
            required: Boolean(question.required),
            sort_order: Number(question.sort_order || (index + 1)),
          };
          if (!['textarea', 'mobile'].includes(question.type)) {
            payload.options = question.options.map((option, optionIndex) => ({
              option_text: option.option_text,
              score: Number(option.score || 0),
              tag_codes: normalizeTagIds(option.tag_codes),
              sort_order: Number(option.sort_order || (optionIndex + 1)),
            }));
          }
          return payload;
        }),
        score_rules: state.questionnaire.score_rules.map((rule, index) => ({
          min_score: rule.min_score,
          max_score: rule.max_score,
          tag_codes: normalizeTagIds(rule.tag_codes),
          sort_order: Number(rule.sort_order || (index + 1)),
        })),
      };
    }

    async function fetchJson(url, options = {}) {
      const response = await fetch(url, options);
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data.ok === false) {
        throw new Error(humanizeErrorMessage(data.message || data.error || '', '请求失败，请稍后重试'));
      }
      return data;
    }

    async function loadAvailableTags() {
      try {
        const data = await fetchJson('/api/admin/wecom/tags');
        state.availableTags = data.items || [];
        state.availableTagMap = new Map(state.availableTags.map((item) => [item.tag_id, item]));
        if (!state.availableTags.length) {
          tagCatalogMessageEl.textContent = '当前未获取到企微标签，可手工填写 tag_id';
          tagCatalogMessageEl.className = 'inline-alert warning';
        } else {
          tagCatalogMessageEl.textContent = '';
          tagCatalogMessageEl.className = 'inline-alert hidden';
        }
      } catch (error) {
        state.availableTags = [];
        state.availableTagMap = new Map();
        tagCatalogMessageEl.textContent = '企微标签加载失败，可稍后重试或手工填写 tag_id';
        tagCatalogMessageEl.className = 'inline-alert error';
      }
      renderInspector();
    }

    async function loadList() {
      state.loadingList = true;
      listEl.innerHTML = '<div class="empty-state">问卷列表加载中...</div>';
      try {
        const data = await fetchJson('/api/admin/questionnaires');
        state.list = data.questionnaires || [];
        renderList();
      } catch (error) {
        state.list = [];
        listEl.innerHTML = `<div class="empty-state">${escapeHtml(error.message || '问卷列表加载失败，请稍后重试')}</div>`;
      } finally {
        state.loadingList = false;
      }
    }

    async function loadQuestionnaire(questionnaireId) {
      const data = await fetchJson(`/api/admin/questionnaires/${questionnaireId}`);
      resetDraft(data.questionnaire);
      renderList();
    }

    async function toggleQuestionnaire(item) {
      await fetchJson(`/api/admin/questionnaires/${item.id}/disable`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_disabled: !item.is_disabled }),
      });
      showToast(item.is_disabled ? '问卷已启用' : '问卷已停用');
      await loadList();
      if (state.currentId === item.id) {
        await loadQuestionnaire(item.id);
      }
    }

    async function deleteQuestionnaireItem(item) {
      if (!window.confirm(`确认删除问卷「${item.name}」吗？`)) return;
      await fetchJson(`/api/admin/questionnaires/${item.id}`, { method: 'DELETE' });
      showToast('问卷已删除');
      if (state.currentId === item.id) {
        resetDraft();
      }
      await loadList();
    }

    async function copyText(text, successMessage = '链接已复制') {
      if (!text) {
        showToast('当前还没有可复制的链接', true);
        return;
      }
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(text);
        } else {
          window.prompt('请复制以下链接', text);
        }
        showToast(successMessage);
      } catch (error) {
        window.prompt('请手动复制以下链接', text);
      }
    }

    async function showPreflight() {
      try {
        const result = await fetchJson('/api/admin/questionnaires/preflight');
        openDrawer('环境检查', Object.entries(result).map(([key, value]) => ({
          label: key,
          value: typeof value === 'object' ? JSON.stringify(value) : String(value),
        })));
      } catch (error) {
        openDrawer('环境检查', [{ label: '提示', value: error.message || '环境检查失败，请稍后再试' }]);
      }
    }

    async function showLatestDebug(questionnaireId) {
      try {
        const result = await fetchJson(`/api/admin/questionnaires/${questionnaireId}/latest-submit-debug`);
        openDrawer('最近提交调试', [
          { label: 'matched_by', value: result.matched_by || '-' },
          { label: 'external_userid', value: result.external_userid || '-' },
          { label: 'follow_user_userid', value: result.follow_user_userid || '-' },
          { label: 'total_score', value: String(result.total_score ?? '-') },
          { label: 'final_tags', value: (result.final_tags || []).join(', ') || '-' },
          { label: 'scrm_apply_status', value: result.scrm_apply_status || '-' },
        ]);
      } catch (error) {
        openDrawer('最近提交调试', [{ label: '提示', value: error.message || '最近提交调试获取失败，请稍后重试' }]);
      }
    }

    function renderList() {
      if (!state.list.length) {
        listEl.innerHTML = '<div class="empty-state">还没有问卷，点击上方“新建问卷”开始搭建。</div>';
        return;
      }
      listEl.innerHTML = '';
      state.list.forEach((item) => {
        const el = document.createElement('article');
        el.className = `list-item${state.currentId === item.id ? ' active' : ''}`;
        el.innerHTML = `
          <div class="meta-row">
            <span class="pill${item.is_disabled ? ' disabled' : ''}">${item.is_disabled ? '已停用' : '启用中'}</span>
            <span class="pill">提交 ${item.submission_count || 0}</span>
          </div>
          <h4>${escapeHtml(item.name || '未命名问卷')}</h4>
          <div class="muted">${escapeHtml(item.title || '未填写标题')}</div>
          <div class="mini-actions">
            <button type="button" class="mini-btn edit">编辑</button>
            <button type="button" class="mini-btn toggle">${item.is_disabled ? '启用' : '停用'}</button>
            <button type="button" class="mini-btn export">导出数据</button>
            <button type="button" class="mini-btn copy">复制链接</button>
            <button type="button" class="mini-btn latest-debug">最近提交调试</button>
            <button type="button" class="mini-btn danger remove">删除</button>
          </div>
        `;
        el.querySelector('.edit').addEventListener('click', () => loadQuestionnaire(item.id).catch((error) => showToast(error.message || '问卷加载失败，请稍后重试', true)));
        el.querySelector('.toggle').addEventListener('click', () => toggleQuestionnaire(item).catch((error) => showToast(error.message || '问卷状态更新失败，请稍后重试', true)));
        el.querySelector('.export').addEventListener('click', () => window.open(`/api/admin/questionnaires/${item.id}/export`, '_blank'));
        el.querySelector('.copy').addEventListener('click', () => copyText(item.public_url, '链接已复制'));
        el.querySelector('.latest-debug').addEventListener('click', () => showLatestDebug(item.id));
        el.querySelector('.remove').addEventListener('click', () => deleteQuestionnaireItem(item).catch((error) => showToast(error.message || '删除失败，请稍后重试', true)));
        listEl.appendChild(el);
      });
    }

    function renderTopbar() {
      const title = state.questionnaire.name || state.questionnaire.title || '新建问卷';
      topbarTitleEl.textContent = title;
      document.getElementById('copy-link-btn').disabled = !buildPublicUrl();
    }

    function renderPreview() {
      const questionnaire = state.questionnaire;
      const isQuestionnaireSelected = state.selection.kind === 'questionnaire';
      previewHeadEl.className = `preview-head${isQuestionnaireSelected ? ' active' : ''}`;
      previewHeadEl.innerHTML = `
        <div class="question-type">问卷设置</div>
        <h2>${escapeHtml(questionnaire.title || '未填写问卷标题')}</h2>
        <p>${escapeHtml(questionnaire.description || '点击当前卡片可在右侧编辑问卷名称、问卷标题、问卷说明、提交后跳转地址、分享标识和停用状态。')}</p>
      `;
      previewHeadEl.onclick = () => selectQuestionnaire();

      previewQuestionsEl.innerHTML = '';
      if (!questionnaire.questions.length) {
        previewQuestionsEl.innerHTML = '<div class="empty-state">左侧添加题目后，这里会实时生成手机端问卷预览。</div>';
      } else {
        questionnaire.questions.forEach((question) => {
          const card = document.createElement('article');
          card.className = `preview-question${state.selection.kind === 'question' && state.selection.key === question.local_key ? ' active' : ''}`;
          const optionPreview = question.type === 'textarea'
            ? '<div class="option-pill">多行文本输入框</div>'
            : question.type === 'mobile'
              ? '<div class="option-pill">手机号单行输入框</div>'
              : (question.options || []).map((option) => `<div class="option-pill">${escapeHtml(option.option_text || '未填写选项')} · ${escapeHtml(String(option.score ?? 0))} 分</div>`).join('');
          card.innerHTML = `
            <span class="question-type">${escapeHtml(formatQuestionType(question.type))}${question.required ? ' · 必填' : ''}</span>
            <h4>${escapeHtml(question.title || '未填写题目标题')}</h4>
            <div class="muted">排序：${escapeHtml(String(question.sort_order ?? ''))}</div>
            <div class="preview-options">${optionPreview}</div>
          `;
          card.addEventListener('click', () => selectQuestion(question.local_key));
          previewQuestionsEl.appendChild(card);
        });
      }

      previewRulesWrapEl.classList.add('hidden');
      previewRulesWrapEl.innerHTML = '';
    }

    function mountTagPicker(host, selectedTagIds, onChange, target) {
      const normalizedSelected = normalizeTagIds(selectedTagIds);
      host.innerHTML = `
        <div class="tag-inline">
          <button type="button" class="btn ghost open-tag-modal">选择标签</button>
          <div class="tag-badges">${buildTagBadges(normalizedSelected)}</div>
          <details class="tag-fallback">
            <summary>手工填写 tag_id 兜底</summary>
            <input class="manual-tag-input" type="text" placeholder='例如 ["etxxx1","etxxx2"]' style="width:100%;margin-top:10px;padding:11px 12px;border-radius:12px;border:1px solid rgba(45,107,74,0.14);">
          </details>
        </div>
      `;
      const manualInput = host.querySelector('.manual-tag-input');
      const openButton = host.querySelector('.open-tag-modal');
      manualInput.value = '';
      manualInput.addEventListener('input', () => {
        const merged = normalizeTagIds([...normalizedSelected, ...parseManualTagInput(manualInput.value || '')]);
        host.querySelector('.tag-badges').innerHTML = buildTagBadges(merged);
        onChange(merged);
      });
      openButton.addEventListener('click', () => openTagModal(target, onChange.currentValue ? onChange.currentValue() : normalizedSelected));
    }

    function renderQuestionnaireInspector() {
      inspectorTitleEl.textContent = '问卷设置';
      inspectorSubtitleEl.textContent = '这里只编辑当前问卷的基础信息，不在顶部重复展示字段。';
      inspectorBodyEl.innerHTML = `
        <section class="config-group">
          <div class="config-head">
            <div>
              <h3>基础信息</h3>
              <p>问卷本身的字段都放在这里集中维护。</p>
            </div>
          </div>
          <label class="field">问卷名称
            <input id="field-name" type="text" value="${escapeHtml(state.questionnaire.name)}">
          </label>
          <label class="field">问卷标题
            <input id="field-title" type="text" value="${escapeHtml(state.questionnaire.title)}">
          </label>
          <label class="field">问卷说明
            <textarea id="field-description">${escapeHtml(state.questionnaire.description)}</textarea>
          </label>
          <label class="field">提交后跳转地址
            <input id="field-redirect-url" type="text" value="${escapeHtml(state.questionnaire.redirect_url)}">
          </label>
          <div class="field-grid compact">
            <label class="field">分享标识
              <input id="field-slug" type="text" value="${escapeHtml(state.questionnaire.slug)}">
            </label>
            <label class="field"><span style="display:block;margin-bottom:7px;">问卷状态</span>
              <label class="field" style="margin-bottom:0;font-weight:600;">
                <input id="field-is-disabled" type="checkbox" ${state.questionnaire.is_disabled ? 'checked' : ''}> 停用问卷
              </label>
            </label>
          </div>
        </section>
        <div class="helper-note">复制链接按钮保留在顶部；如果已有对外链接，点击即可直接复制。</div>
      `;
      inspectorBodyEl.querySelector('#field-name').addEventListener('input', (event) => {
        state.questionnaire.name = event.target.value;
        renderTopbar();
      });
      inspectorBodyEl.querySelector('#field-title').addEventListener('input', (event) => {
        state.questionnaire.title = event.target.value;
        renderTopbar();
        renderPreview();
      });
      inspectorBodyEl.querySelector('#field-description').addEventListener('input', (event) => {
        state.questionnaire.description = event.target.value;
        renderPreview();
      });
      inspectorBodyEl.querySelector('#field-redirect-url').addEventListener('input', (event) => {
        state.questionnaire.redirect_url = event.target.value;
      });
      inspectorBodyEl.querySelector('#field-slug').addEventListener('input', (event) => {
        state.questionnaire.slug = event.target.value;
        renderTopbar();
      });
      inspectorBodyEl.querySelector('#field-is-disabled').addEventListener('change', (event) => {
        state.questionnaire.is_disabled = event.target.checked;
      });
    }

    function renderQuestionInspector(question) {
      inspectorTitleEl.textContent = formatQuestionType(question.type);
      inspectorSubtitleEl.textContent = '当前选中的是题目。这里维护题目标题、题型、必填、选项文案、分值和标签。';
      const optionsHtml = ['textarea', 'mobile'].includes(question.type)
        ? ''
        : (question.options || []).map((option, index) => `
            <div class="option-editor" data-option-key="${escapeHtml(option.local_key)}">
              <div class="option-editor-head">
                <span class="mini-label">选项 ${index + 1}</span>
                <button type="button" class="link-btn danger remove-option-btn" data-option-key="${escapeHtml(option.local_key)}">删除</button>
              </div>
              <div class="field-grid triple">
                <label class="field">选项文案
                  <input data-option-field="option_text" data-option-key="${escapeHtml(option.local_key)}" type="text" value="${escapeHtml(option.option_text)}">
                </label>
                <label class="field">分值
                  <input data-option-field="score" data-option-key="${escapeHtml(option.local_key)}" type="text" value="${escapeHtml(String(option.score ?? 0))}">
                </label>
                <label class="field">排序
                  <input data-option-field="sort_order" data-option-key="${escapeHtml(option.local_key)}" type="text" value="${escapeHtml(String(option.sort_order ?? index + 1))}">
                </label>
              </div>
              <div class="tag-picker-host" data-option-tag-host="${escapeHtml(option.local_key)}"></div>
            </div>
          `).join('');
      inspectorBodyEl.innerHTML = `
        <section class="config-group">
          <div class="config-head">
            <div>
              <h3>题目设置</h3>
              <p>点击中间预览区任意题目，右侧都会切换到这里。</p>
            </div>
            <button id="remove-question-btn" type="button" class="btn danger">删除题目</button>
          </div>
          <div class="field-grid compact">
            <label class="field">题型
              <select id="question-type">
                <option value="single_choice">单选题</option>
                <option value="multi_choice">多选题</option>
                <option value="textarea">文本题</option>
                <option value="mobile">手机号题</option>
              </select>
            </label>
            <label class="field">排序
              <input id="question-sort-order" type="text" value="${escapeHtml(String(question.sort_order ?? ''))}">
            </label>
          </div>
          <label class="field">题目标题
            <input id="question-title" type="text" value="${escapeHtml(question.title)}">
          </label>
          <label class="field" style="margin-bottom:0;">
            <input id="question-required" type="checkbox" ${question.required ? 'checked' : ''}> 必填
          </label>
        </section>
        <section class="config-group${['textarea', 'mobile'].includes(question.type) ? ' hidden' : ''}" id="question-options-group">
          <div class="config-head">
            <div>
              <h3>选项列表</h3>
              <p>单选题和多选题在这里维护选项文案、分值和标签。</p>
            </div>
            <button id="add-option-btn" type="button" class="btn secondary">添加选项</button>
          </div>
          ${optionsHtml || '<div class="empty-state">当前没有选项，点击“添加选项”开始配置。</div>'}
        </section>
        <div class="helper-note${question.type === 'textarea' ? '' : ' hidden'}" id="textarea-note">文本题只保存文本，不显示多余配置，也不会参与评分或自动打标签。</div>
        <div class="helper-note${question.type === 'mobile' ? '' : ' hidden'}" id="mobile-note">手机号题使用单行手机号输入，提交后会单独写入 submission 主记录，并在识别到客户时尝试复用侧边栏绑定逻辑。</div>
      `;
      inspectorBodyEl.querySelector('#question-type').value = question.type;

      inspectorBodyEl.querySelector('#question-title').addEventListener('input', (event) => {
        question.title = event.target.value;
        renderPreview();
      });
      inspectorBodyEl.querySelector('#question-sort-order').addEventListener('input', (event) => {
        question.sort_order = event.target.value;
        renderPreview();
      });
      inspectorBodyEl.querySelector('#question-required').addEventListener('change', (event) => {
        question.required = event.target.checked;
        renderPreview();
      });
      inspectorBodyEl.querySelector('#question-type').addEventListener('change', (event) => {
        question.type = event.target.value;
        if (['textarea', 'mobile'].includes(question.type)) {
          question.options = [];
        } else if (!question.options.length) {
          question.options = [createOption({}, 0)];
        }
        renderWorkspace();
      });
      inspectorBodyEl.querySelector('#remove-question-btn').addEventListener('click', () => {
        state.questionnaire.questions = state.questionnaire.questions.filter((item) => item.local_key !== question.local_key);
        state.selection = { kind: 'questionnaire' };
        renderWorkspace();
      });

      const addOptionBtn = inspectorBodyEl.querySelector('#add-option-btn');
      if (addOptionBtn) {
        addOptionBtn.addEventListener('click', () => {
          question.options.push(createOption({}, question.options.length));
          renderWorkspace();
        });
      }

      inspectorBodyEl.querySelectorAll('[data-option-field]').forEach((input) => {
        input.addEventListener('input', (event) => {
          const option = question.options.find((item) => item.local_key === event.target.dataset.optionKey);
          if (!option) return;
          option[event.target.dataset.optionField] = event.target.value;
          renderPreview();
        });
      });
      inspectorBodyEl.querySelectorAll('.remove-option-btn').forEach((button) => {
        button.addEventListener('click', () => {
          question.options = question.options.filter((item) => item.local_key !== button.dataset.optionKey);
          if (!question.options.length && !['textarea', 'mobile'].includes(question.type)) {
            question.options = [createOption({}, 0)];
          }
          renderWorkspace();
        });
      });
      question.options.forEach((option) => {
        const host = inspectorBodyEl.querySelector(`[data-option-tag-host="${option.local_key}"]`);
        if (!host) return;
        const apply = (tagIds) => {
          option.tag_codes = tagIds;
        };
        apply.currentValue = () => option.tag_codes;
        mountTagPicker(host, option.tag_codes, apply, {
          type: 'option',
          questionKey: question.local_key,
          optionKey: option.local_key,
        });
      });
    }

    function renderRuleInspector(rule) {
      inspectorTitleEl.textContent = '分数规则';
      inspectorSubtitleEl.textContent = '当前处于分数规则配置模式。左侧按钮只负责进入这里，真正新增规则请使用右侧入口。';
      const ruleListHtml = state.questionnaire.score_rules.length
        ? `
          <div class="rule-nav-list">
            ${state.questionnaire.score_rules.map((item, index) => `
              <button type="button" class="rule-nav-item${rule && item.local_key === rule.local_key ? ' active' : ''}" data-rule-key="${escapeHtml(item.local_key)}">
                <strong>规则 ${index + 1}</strong>
                <span>${escapeHtml(String(item.min_score ?? ''))} - ${escapeHtml(String(item.max_score ?? ''))}</span>
                <span>${normalizeTagIds(item.tag_codes).length ? normalizeTagIds(item.tag_codes).map((tagId) => formatTagLabel(ensureTagKnown(tagId))).join(' / ') : '未选择标签'}</span>
              </button>
            `).join('')}
          </div>
        `
        : `
          <div class="empty-state">
            <strong style="display:block;font-size:18px;margin-bottom:6px;">当前还没有分数规则</strong>
            <div class="muted" style="margin-bottom:14px;">点击下方按钮新增规则</div>
            <button id="empty-add-rule-btn" type="button" class="btn secondary">新增规则</button>
          </div>
        `;
      const editorHtml = rule ? `
        <section class="config-group">
          <div class="config-head">
            <div>
              <h3>规则设置</h3>
              <p>保存到数据库里的仍然是 tag_id 数组。</p>
            </div>
            <button id="remove-rule-btn" type="button" class="btn danger">删除规则</button>
          </div>
          <div class="field-grid triple">
            <label class="field">最低分
              <input id="rule-min-score" type="text" value="${escapeHtml(String(rule.min_score ?? ''))}">
            </label>
            <label class="field">最高分
              <input id="rule-max-score" type="text" value="${escapeHtml(String(rule.max_score ?? ''))}">
            </label>
            <label class="field">排序
              <input id="rule-sort-order" type="text" value="${escapeHtml(String(rule.sort_order ?? ''))}">
            </label>
          </div>
          <div id="rule-tag-host"></div>
        </section>
      ` : `
        <section class="config-group">
          <div class="config-head">
            <div>
              <h3>规则设置</h3>
              <p>先从上面的规则列表里选择一条，或直接新增规则。</p>
            </div>
          </div>
          <div class="helper-note">右侧规则配置区会一直保留在这里，你可以连续新增、删除和切换分数规则。</div>
        </section>
      `;
      inspectorBodyEl.innerHTML = `
        <section class="config-group">
          <div class="config-head">
            <div>
              <h3>规则列表</h3>
              <p>这里集中管理所有分数规则；新增后会继续往下累积，不会覆盖之前的规则。</p>
            </div>
            <button id="rule-list-add-btn" type="button" class="btn secondary">新增规则</button>
          </div>
          ${ruleListHtml}
        </section>
        ${editorHtml}
      `;
      inspectorBodyEl.querySelector('#rule-list-add-btn').addEventListener('click', () => addRule());
      inspectorBodyEl.querySelectorAll('[data-rule-key]').forEach((button) => {
        button.addEventListener('click', () => selectRule(button.dataset.ruleKey));
      });
      const emptyAddRuleBtn = inspectorBodyEl.querySelector('#empty-add-rule-btn');
      if (emptyAddRuleBtn) {
        emptyAddRuleBtn.addEventListener('click', () => addRule());
      }
      if (!rule) {
        return;
      }
      inspectorBodyEl.querySelector('#rule-min-score').addEventListener('input', (event) => {
        rule.min_score = event.target.value;
        renderPreview();
      });
      inspectorBodyEl.querySelector('#rule-max-score').addEventListener('input', (event) => {
        rule.max_score = event.target.value;
        renderPreview();
      });
      inspectorBodyEl.querySelector('#rule-sort-order').addEventListener('input', (event) => {
        rule.sort_order = event.target.value;
        renderPreview();
      });
      inspectorBodyEl.querySelector('#remove-rule-btn').addEventListener('click', () => {
        const currentIndex = state.questionnaire.score_rules.findIndex((item) => item.local_key === rule.local_key);
        state.questionnaire.score_rules = state.questionnaire.score_rules.filter((item) => item.local_key !== rule.local_key);
        state.ruleMode = true;
        if (state.questionnaire.score_rules.length) {
          const nextIndex = Math.min(currentIndex, state.questionnaire.score_rules.length - 1);
          state.lastRuleKey = state.questionnaire.score_rules[nextIndex].local_key;
          state.selection = { kind: 'rule', key: state.questionnaire.score_rules[nextIndex].local_key };
        } else {
          state.lastRuleKey = '';
          state.selection = { kind: 'questionnaire' };
        }
        renderWorkspace();
      });
      const apply = (tagIds) => {
        rule.tag_codes = tagIds;
        renderPreview();
      };
      apply.currentValue = () => rule.tag_codes;
      mountTagPicker(inspectorBodyEl.querySelector('#rule-tag-host'), rule.tag_codes, apply, {
        type: 'rule',
        ruleKey: rule.local_key,
      });
    }

    function renderInspector() {
      if (state.ruleMode) {
        const rule = currentRule();
        renderRuleInspector(rule);
        return;
      }
      if (state.selection.kind === 'questionnaire') {
        renderQuestionnaireInspector();
        return;
      }
      if (state.selection.kind === 'question') {
        const question = currentQuestion();
        if (!question) {
          state.selection = { kind: 'questionnaire' };
          renderInspector();
          return;
        }
        renderQuestionInspector(question);
        return;
      }
      renderQuestionnaireInspector();
    }

    function renderWorkspace() {
      renderTopbar();
      renderPreview();
      renderInspector();
      renderList();
    }

    function addQuestion(type) {
      const question = createQuestion(type, {}, state.questionnaire.questions.length);
      state.questionnaire.questions.push(question);
      state.ruleMode = false;
      state.selection = { kind: 'question', key: question.local_key };
      renderWorkspace();
    }

    function addRule() {
      const rule = createRule({}, state.questionnaire.score_rules.length);
      state.questionnaire.score_rules.push(rule);
      state.ruleMode = true;
      state.lastRuleKey = rule.local_key;
      state.selection = { kind: 'rule', key: rule.local_key };
      renderWorkspace();
    }

    async function saveQuestionnaire() {
      const wasEditing = Boolean(state.currentId);
      const payload = serializePayload();
      const url = state.currentId ? `/api/admin/questionnaires/${state.currentId}` : '/api/admin/questionnaires';
      const method = state.currentId ? 'PUT' : 'POST';
      const data = await fetchJson(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      resetDraft(data.questionnaire);
      await loadList();
      showToast(wasEditing ? '问卷已更新' : '问卷已创建');
    }

    document.getElementById('new-btn').addEventListener('click', () => resetDraft());
    document.getElementById('reset-btn').addEventListener('click', () => {
      if (state.currentId) {
        loadQuestionnaire(state.currentId).catch((error) => showToast(error.message || '重置失败，请稍后重试', true));
        return;
      }
      resetDraft();
    });
    document.getElementById('save-btn').addEventListener('click', () => saveQuestionnaire().catch((error) => showToast(error.message || '保存失败，请检查当前配置后重试', true)));
    document.getElementById('copy-link-btn').addEventListener('click', () => copyText(buildPublicUrl(), '链接已复制'));
    document.getElementById('preflight-btn').addEventListener('click', () => showPreflight());
    document.getElementById('reload-list-btn').addEventListener('click', () => loadList());
    document.getElementById('add-single').addEventListener('click', () => addQuestion('single_choice'));
    document.getElementById('add-multi').addEventListener('click', () => addQuestion('multi_choice'));
    document.getElementById('add-textarea').addEventListener('click', () => addQuestion('textarea'));
    document.getElementById('add-mobile').addEventListener('click', () => addQuestion('mobile'));
    document.getElementById('add-rule').addEventListener('click', () => enterRuleMode());
    document.getElementById('drawer-close').addEventListener('click', closeDrawer);
    document.getElementById('tag-modal-close').addEventListener('click', closeTagModal);
    document.getElementById('tag-modal-cancel').addEventListener('click', closeTagModal);
    document.getElementById('tag-modal-confirm').addEventListener('click', () => {
      const merged = normalizeTagIds([...state.tagModal.selected, ...parseManualTagInput(tagModalManualEl.value || '')]);
      if (state.tagModal.target?.type === 'option') {
        const question = state.questionnaire.questions.find((item) => item.local_key === state.tagModal.target.questionKey);
        const option = question?.options.find((item) => item.local_key === state.tagModal.target.optionKey);
        if (option) option.tag_codes = merged;
      }
      if (state.tagModal.target?.type === 'rule') {
        const rule = state.questionnaire.score_rules.find((item) => item.local_key === state.tagModal.target.ruleKey);
        if (rule) rule.tag_codes = merged;
      }
      closeTagModal();
      renderWorkspace();
    });
    tagModalSearchEl.addEventListener('input', (event) => {
      state.tagModal.search = event.target.value;
      renderTagModal();
    });
    tagModalOverlayEl.addEventListener('click', (event) => {
      if (event.target === tagModalOverlayEl) closeTagModal();
    });
    drawerOverlayEl.addEventListener('click', (event) => {
      if (event.target === drawerOverlayEl) closeDrawer();
    });

    resetDraft();
    Promise.all([
      loadAvailableTags(),
      loadList(),
    ]).then(() => {
      renderWorkspace();
    }).catch((error) => {
      showToast(error.message || '页面初始化失败，请刷新后重试', true);
      renderWorkspace();
    });
  </script>
</body>
</html>
        """
    )


@bp.route("/api/admin/questionnaires", methods=["POST"])
def admin_create_questionnaire():
    payload = request.get_json(silent=True) or {}
    try:
        questionnaire = create_questionnaire(payload)
        return jsonify({"ok": True, "questionnaire": _attach_questionnaire_links(questionnaire)})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@bp.route("/api/admin/questionnaires/<int:questionnaire_id>", methods=["GET"])
def admin_get_questionnaire(questionnaire_id: int):
    questionnaire = get_questionnaire_detail(questionnaire_id)
    if not questionnaire:
        return jsonify({"ok": False, "error": "questionnaire not found"}), 404
    return jsonify({"ok": True, "questionnaire": _attach_questionnaire_links(questionnaire)})


@bp.route("/api/admin/questionnaires/<int:questionnaire_id>/latest-submit-debug", methods=["GET"])
def admin_questionnaire_latest_submit_debug(questionnaire_id: int):
    result = get_latest_questionnaire_submit_debug(questionnaire_id)
    if not result:
        return jsonify({"ok": False, "error": "no_submission_found"})
    payload = {"ok": True}
    payload.update(result)
    return jsonify(payload)


@bp.route("/api/admin/questionnaires/<int:questionnaire_id>", methods=["PUT"])
def admin_update_questionnaire(questionnaire_id: int):
    payload = request.get_json(silent=True) or {}
    try:
        questionnaire = update_questionnaire(questionnaire_id, payload)
        if not questionnaire:
            return jsonify({"ok": False, "error": "questionnaire not found"}), 404
        return jsonify({"ok": True, "questionnaire": _attach_questionnaire_links(questionnaire)})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@bp.route("/api/admin/questionnaires/<int:questionnaire_id>/disable", methods=["POST"])
def admin_disable_questionnaire(questionnaire_id: int):
    payload = request.get_json(silent=True) or {}
    questionnaire = disable_questionnaire(questionnaire_id, payload.get("is_disabled", True))
    if not questionnaire:
        return jsonify({"ok": False, "error": "questionnaire not found"}), 404
    return jsonify({"ok": True, "questionnaire": _attach_questionnaire_links(questionnaire)})


@bp.route("/api/admin/questionnaires/<int:questionnaire_id>", methods=["DELETE"])
def admin_delete_questionnaire(questionnaire_id: int):
    deleted = delete_questionnaire(questionnaire_id)
    if not deleted:
        return jsonify({"ok": False, "error": "questionnaire not found"}), 404
    return jsonify({"ok": True, "deleted": True})


@bp.route("/api/admin/questionnaires/<int:questionnaire_id>/export", methods=["GET"])
def admin_export_questionnaire(questionnaire_id: int):
    try:
        export_payload = export_questionnaire_submissions(questionnaire_id)
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    content = _build_excel_xml(export_payload["headers"], export_payload["rows"])
    response = Response(content, mimetype="application/vnd.ms-excel")
    response.headers["Content-Disposition"] = f'attachment; filename="{export_payload["filename"]}"'
    return response


@bp.route("/s/<slug>", methods=["GET"])
def questionnaire_h5_page(slug: str):
    wechat_gate = _require_wechat_browser_page()
    if wechat_gate is not None:
        return wechat_gate
    questionnaire = get_public_questionnaire_by_slug(slug)
    if not questionnaire:
        abort(404)
    source_params = _questionnaire_source_params()
    session_identity = _questionnaire_session_identity()
    request_identity = _questionnaire_request_identity()
    if has_questionnaire_submission(int(questionnaire["id"]), request_identity):
        return redirect(_questionnaire_submitted_path(slug))
    is_wechat_browser = _is_wechat_browser()
    oauth_query = {"slug": slug, **source_params}
    oauth_start_url = f"{url_for('api.h5_wechat_oauth_start')}?{urlencode(oauth_query)}"
    page_mode = "questionnaire"
    env_notice = ""
    if is_wechat_browser and not session_identity.get("openid"):
        page_mode = "auth_gate"
        if _wechat_oauth_is_configured():
            env_notice = "授权后即可填写问卷信息。"
        else:
            env_notice = "当前为微信环境，但未配置公众号 OAuth，当前页面仅供测试。"
    page_state = {
        "slug": slug,
        "mode": page_mode,
        "api_url": f"/api/h5/questionnaires/{slug}",
        "submit_url": f"/api/h5/questionnaires/{slug}/submit",
        "submitted_url": _questionnaire_submitted_path(slug),
        "title": questionnaire.get("title", ""),
        "description": questionnaire.get("description", ""),
        "env_notice": env_notice,
        "oauth_start_url": oauth_start_url if _wechat_oauth_is_configured() else "",
        "is_wechat_browser": is_wechat_browser,
        "is_authorized": bool(session_identity.get("openid")),
    }
    return render_template_string(
        """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
  <title>{{ page_state.title }}</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f3f5f0;
      --panel: rgba(255,255,255,0.94);
      --line: rgba(41,73,54,0.12);
      --text: #193325;
      --muted: #607266;
      --primary: #2f6a4c;
      --primary-strong: #234f39;
      --soft: #edf4ef;
      --warning-bg: #fff6dc;
      --warning-text: #7a5a16;
      --shadow: 0 24px 60px rgba(25,51,37,0.10);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: "PingFang SC", "Helvetica Neue", -apple-system, BlinkMacSystemFont, sans-serif;
      background:
        radial-gradient(circle at top left, rgba(76, 132, 98, 0.16), transparent 28%),
        radial-gradient(circle at bottom right, rgba(47, 106, 76, 0.12), transparent 24%),
        var(--bg);
      color: var(--text);
    }
    .page-shell { max-width: 820px; margin: 0 auto; padding: 24px 16px 56px; }
    body.auth-mode .page-shell {
      min-height: 100vh;
      max-width: 560px;
      display: flex;
      align-items: center;
      justify-content: center;
      padding-top: 36px;
      padding-bottom: 36px;
    }
    .hero-card,
    .questionnaire-card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 28px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(14px);
    }
    .hero-card {
      padding: 36px 28px;
      text-align: center;
      margin-bottom: 18px;
      position: relative;
      overflow: hidden;
    }
    .hero-card::before {
      content: "";
      position: absolute;
      inset: -24% auto auto -16%;
      width: 180px;
      height: 180px;
      border-radius: 999px;
      background: radial-gradient(circle, rgba(47, 106, 76, 0.12), transparent 70%);
      pointer-events: none;
    }
    .hero-card::after {
      content: "";
      position: absolute;
      right: -40px;
      bottom: -36px;
      width: 150px;
      height: 150px;
      border-radius: 30px;
      transform: rotate(18deg);
      background: linear-gradient(135deg, rgba(47, 106, 76, 0.10), rgba(47, 106, 76, 0));
      pointer-events: none;
    }
    .eyebrow {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      margin: 0 0 16px;
      padding: 8px 14px;
      border-radius: 999px;
      background: var(--soft);
      color: var(--primary);
      font-size: 13px;
      font-weight: 700;
      letter-spacing: 0.04em;
    }
    h1 {
      margin: 0;
      font-size: clamp(28px, 7vw, 38px);
      line-height: 1.12;
      letter-spacing: -0.03em;
    }
    .hero-subtitle {
      max-width: 440px;
      margin: 14px auto 0;
      color: var(--muted);
      font-size: 15px;
      line-height: 1.7;
      position: relative;
      z-index: 1;
    }
    .hero-actions {
      display: flex;
      justify-content: center;
      margin-top: 28px;
      position: relative;
      z-index: 1;
    }
    .hero-actions a,
    .hero-actions button {
      display: inline-flex;
      justify-content: center;
      align-items: center;
      min-width: 220px;
      padding: 15px 24px;
      border-radius: 999px;
      border: 0;
      text-decoration: none;
      background: linear-gradient(135deg, var(--primary) 0%, var(--primary-strong) 100%);
      color: #fff;
      font-size: 16px;
      font-weight: 700;
      box-shadow: 0 18px 30px rgba(35, 79, 57, 0.18);
      position: relative;
      z-index: 1;
    }
    .hero-actions button[disabled] {
      opacity: 0.58;
      cursor: not-allowed;
      box-shadow: none;
    }
    .hero-note,
    .notice {
      margin: 18px 0 0;
      padding: 12px 14px;
      border-radius: 16px;
      background: var(--warning-bg);
      color: var(--warning-text);
      font-size: 14px;
      line-height: 1.6;
      position: relative;
      z-index: 1;
    }
    .hero-meta {
      margin-top: 18px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.6;
      position: relative;
      z-index: 1;
    }
    .questionnaire-card { padding: 22px 18px 24px; }
    .question {
      margin: 0 0 18px;
      padding: 18px 16px;
      border-radius: 22px;
      background: #f7faf7;
      border: 1px solid rgba(47, 106, 76, 0.10);
      box-shadow: inset 0 1px 0 rgba(255,255,255,0.7);
    }
    .question-title { margin: 0 0 14px; font-size: 16px; font-weight: 700; line-height: 1.5; }
    .required { color: #bb5433; margin-left: 4px; }
    label.option {
      display: flex;
      gap: 12px;
      align-items: flex-start;
      margin: 0 0 12px;
      padding: 12px 14px;
      border-radius: 16px;
      background: #fff;
      border: 1px solid rgba(47, 106, 76, 0.10);
      font-size: 15px;
      color: var(--text);
    }
    textarea {
      width: 100%;
      min-height: 132px;
      border-radius: 18px;
      border: 1px solid rgba(47, 106, 76, 0.18);
      padding: 14px 16px;
      font: inherit;
      resize: vertical;
      background: #fff;
    }
    .submit-btn {
      width: 100%;
      border: 0;
      border-radius: 999px;
      padding: 16px 20px;
      font: inherit;
      font-size: 16px;
      font-weight: 700;
      background: linear-gradient(135deg, var(--primary) 0%, var(--primary-strong) 100%);
      color: #fff;
      box-shadow: 0 18px 30px rgba(35, 79, 57, 0.18);
    }
    .submit-btn[disabled] { opacity: 0.6; box-shadow: none; }
    .state { margin-top: 16px; color: var(--muted); font-size: 14px; line-height: 1.6; }
    .error { color: #bb5433; }
    @media (max-width: 640px) {
      .page-shell { padding: 18px 14px 40px; }
      .hero-card { padding: 28px 20px; }
      .questionnaire-card { padding: 18px 14px 22px; }
      .question { padding: 16px 14px; border-radius: 18px; }
      .hero-actions a, .hero-actions button { width: 100%; }
    }
  </style>
</head>
<body class="{{ 'auth-mode' if page_state.mode == 'auth_gate' else 'questionnaire-mode' }}">
  <div class="page-shell">
    {% if page_state.mode == "auth_gate" %}
    <section class="hero-card">
      <p class="eyebrow">微信问卷入口</p>
      <h1>点击下方授权，登记表单</h1>
      <p class="hero-subtitle">授权后即可填写问卷信息</p>
      {% if page_state.description %}
      <p class="hero-subtitle">{{ page_state.description }}</p>
      {% endif %}
      <div class="hero-actions">
        {% if page_state.oauth_start_url %}
        <a href="{{ page_state.oauth_start_url }}">立即授权并填写</a>
        {% else %}
        <button type="button" disabled>暂时无法授权</button>
        {% endif %}
      </div>
      <div class="hero-meta">仅需一次授权，即可继续填写当前问卷</div>
      {% if page_state.env_notice %}
      <p class="hero-note">{{ page_state.env_notice }}</p>
      {% endif %}
    </section>
    {% else %}
    <section class="hero-card" style="text-align:left;padding:24px 22px;">
      <p class="eyebrow">问卷入口</p>
      <h1 style="font-size:32px;">{{ page_state.title }}</h1>
      {% if page_state.description %}
      <p class="hero-subtitle" style="margin-left:0;margin-right:0;">{{ page_state.description }}</p>
      {% endif %}
      {% if page_state.env_notice %}
      <p class="notice">{{ page_state.env_notice }}</p>
      {% endif %}
    </section>
    <section class="questionnaire-card">
      <form id="questionnaire-form"></form>
      <div id="state" class="state"></div>
    </section>
    {% endif %}
  </div>
  <script>
    const pageState = {{ page_state|tojson }};
    const slug = pageState.slug;
    const apiUrl = pageState.api_url;
    const submitUrl = pageState.submit_url;
    const formEl = document.getElementById('questionnaire-form');
    const stateEl = document.getElementById('state');
    let questionnaire = null;
    let submitInFlight = false;

    if (pageState.mode !== 'questionnaire') {
      window.pageState = pageState;
    } else {
      window.pageState = pageState;
      const submittedUrl = pageState.submitted_url;

      function setState(message, isError = false) {
        stateEl.textContent = message || '';
        stateEl.className = isError ? 'state error' : 'state';
      }

      function collectMetaFromQuery() {
        const params = new URLSearchParams(window.location.search);
        const fields = ['respondent_key', 'openid', 'unionid', 'external_userid', 'source_channel', 'campaign_id', 'staff_id'];
        return fields.reduce((acc, field) => {
          const value = params.get(field);
          if (value) acc[field] = value;
          return acc;
        }, {});
      }

      function renderQuestionnaire(data) {
        questionnaire = data;
        formEl.innerHTML = '';

        data.questions.forEach((question) => {
          const wrapper = document.createElement('section');
          wrapper.className = 'question';

          const title = document.createElement('h2');
          title.className = 'question-title';
          title.textContent = question.title;
          if (question.required) {
            const required = document.createElement('span');
            required.className = 'required';
            required.textContent = '*';
            title.appendChild(required);
          }
          wrapper.appendChild(title);

          if (question.type === 'textarea') {
            const textarea = document.createElement('textarea');
            textarea.name = `q_${question.id}`;
            wrapper.appendChild(textarea);
          } else if (question.type === 'mobile') {
            const input = document.createElement('input');
            input.type = 'tel';
            input.name = `q_${question.id}`;
            input.inputMode = 'numeric';
            input.autocomplete = 'tel';
            input.placeholder = '请输入手机号';
            input.maxLength = 20;
            input.style.width = '100%';
            input.style.borderRadius = '18px';
            input.style.border = '1px solid rgba(47, 106, 76, 0.18)';
            input.style.padding = '14px 16px';
            input.style.font = 'inherit';
            input.style.background = '#fff';
            wrapper.appendChild(input);
          } else {
            const type = question.type === 'single_choice' ? 'radio' : 'checkbox';
            question.options.forEach((option) => {
              const label = document.createElement('label');
              label.className = 'option';
              const input = document.createElement('input');
              input.type = type;
              input.name = `q_${question.id}`;
              input.value = String(option.id);
              const text = document.createElement('span');
              text.textContent = option.option_text;
              label.appendChild(input);
              label.appendChild(text);
              wrapper.appendChild(label);
            });
          }
          formEl.appendChild(wrapper);
        });

        const submitButton = document.createElement('button');
        submitButton.type = 'submit';
        submitButton.className = 'submit-btn';
        submitButton.textContent = '提交';
        formEl.appendChild(submitButton);
      }

      function collectAnswers() {
        const answers = {};
        questionnaire.questions.forEach((question) => {
          const name = `q_${question.id}`;
          if (question.type === 'single_choice') {
            const checked = formEl.querySelector(`input[name="${name}"]:checked`);
            if (checked) answers[question.id] = Number(checked.value);
            return;
          }
          if (question.type === 'multi_choice') {
            const checked = Array.from(formEl.querySelectorAll(`input[name="${name}"]:checked`));
            if (checked.length) answers[question.id] = checked.map((item) => Number(item.value));
            return;
          }
          if (question.type === 'textarea') {
            const textarea = formEl.querySelector(`textarea[name="${name}"]`);
            if (textarea && textarea.value.trim()) answers[question.id] = textarea.value.trim();
            return;
          }
          const input = formEl.querySelector(`input[name="${name}"]`);
          if (input && input.value.trim()) answers[question.id] = input.value.trim();
        });
        return answers;
      }

      formEl.addEventListener('submit', async (event) => {
        event.preventDefault();
        if (!questionnaire || submitInFlight) return;
        const submitButton = formEl.querySelector('button[type="submit"]');
        submitInFlight = true;
        submitButton.disabled = true;
        setState('提交中...');
        try {
          const response = await fetch(submitUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ...collectMetaFromQuery(), answers: collectAnswers() }),
          });
          const result = await response.json();
          if (result && result.error === 'already_submitted') {
            window.location.href = submittedUrl;
            return;
          }
          if (!response.ok || !result.success) {
            throw new Error(result.error || '提交失败');
          }
          if (result.redirect_url) {
            window.location.href = result.redirect_url;
            return;
          }
          window.location.href = submittedUrl;
        } catch (error) {
          setState(error.message || '提交失败，请稍后重试', true);
        } finally {
          submitInFlight = false;
          submitButton.disabled = false;
        }
      });

      fetch(apiUrl)
        .then((response) => response.json().then((data) => ({ ok: response.ok, data })))
        .then(({ ok, data }) => {
          if (data && data.error === 'already_submitted') {
            window.location.href = submittedUrl;
            return;
          }
          if (!ok || !data.ok) throw new Error(data.error || '问卷不存在');
          renderQuestionnaire(data.questionnaire);
        })
        .catch((error) => setState(error.message || '加载失败', true));
    }
  </script>
</body>
</html>
        """,
        page_state=page_state,
    )


@bp.route("/s/<slug>/submitted", methods=["GET"])
def questionnaire_h5_submitted(slug: str):
    questionnaire = get_public_questionnaire_by_slug(slug)
    if not questionnaire:
        abort(404)
    return render_template_string(
        """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
  <title>已经提交</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f3f5f0;
      --panel: rgba(255,255,255,0.94);
      --line: rgba(41,73,54,0.12);
      --text: #193325;
      --muted: #607266;
      --primary: #2f6a4c;
      --soft: #edf4ef;
      --shadow: 0 24px 60px rgba(25,51,37,0.10);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 24px 16px;
      font-family: "PingFang SC", "Helvetica Neue", -apple-system, BlinkMacSystemFont, sans-serif;
      background:
        radial-gradient(circle at top left, rgba(76, 132, 98, 0.16), transparent 28%),
        radial-gradient(circle at bottom right, rgba(47, 106, 76, 0.12), transparent 24%),
        var(--bg);
      color: var(--text);
    }
    .card {
      width: min(100%, 460px);
      padding: 40px 28px;
      text-align: center;
      border-radius: 28px;
      border: 1px solid var(--line);
      background: var(--panel);
      box-shadow: var(--shadow);
      backdrop-filter: blur(14px);
    }
    .eyebrow {
      display: inline-flex;
      align-items: center;
      padding: 8px 14px;
      border-radius: 999px;
      background: var(--soft);
      color: var(--primary);
      font-size: 13px;
      font-weight: 700;
      letter-spacing: 0.04em;
    }
    h1 {
      margin: 18px 0 0;
      font-size: clamp(32px, 8vw, 40px);
      line-height: 1.08;
      letter-spacing: -0.03em;
    }
    p {
      margin: 14px 0 0;
      color: var(--muted);
      font-size: 15px;
      line-height: 1.7;
    }
  </style>
</head>
<body>
  <main class="card">
    <div class="eyebrow">问卷提交状态</div>
    <h1>已经提交</h1>
    <p>感谢填写</p>
  </main>
</body>
</html>
        """
    )


@bp.route("/api/h5/questionnaires/<slug>", methods=["GET"])
def public_get_questionnaire(slug: str):
    wechat_gate = _require_wechat_browser_api()
    if wechat_gate is not None:
        return wechat_gate
    questionnaire = get_public_questionnaire_by_slug(slug)
    if not questionnaire:
        return jsonify({"ok": False, "error": "questionnaire not found"}), 404
    if has_questionnaire_submission(int(questionnaire["id"]), _questionnaire_request_identity()):
        return jsonify({"ok": False, "error": "already_submitted", "message": "已经提交"}), 409
    return jsonify({"ok": True, "questionnaire": questionnaire})


@bp.route("/api/h5/questionnaires/<slug>/submit", methods=["POST"])
def public_submit_questionnaire(slug: str):
    wechat_gate = _require_wechat_browser_api()
    if wechat_gate is not None:
        return wechat_gate
    payload = request.get_json(silent=True) or {}
    request_meta = {
        "ip": (request.headers.get("X-Forwarded-For", "").split(",")[0] or request.remote_addr or "").strip(),
        "user_agent": request.headers.get("User-Agent", ""),
    }
    try:
        result = submit_questionnaire(slug, payload, request_meta=request_meta)
        return jsonify(result)
    except LookupError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404
    except QuestionnaireAlreadySubmittedError as exc:
        return jsonify({"success": False, "error": "already_submitted", "message": str(exc) or "已经提交"}), 409
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400


@bp.route("/api/debug/questionnaire/session", methods=["GET"])
def debug_questionnaire_session():
    if not current_app.config.get("ENABLE_DEBUG_QUESTIONNAIRE_SESSION_API"):
        abort(404)
    return jsonify({"ok": True, "questionnaire_h5_identity": session.get("questionnaire_h5_identity") or {}})


@bp.route("/api/h5/wechat/oauth/start", methods=["GET"])
def h5_wechat_oauth_start():
    if not _wechat_oauth_is_configured():
        return jsonify({"ok": False, "error": "wechat_oauth_not_configured"}), 501
    slug = request.args.get("slug", "").strip()
    if not slug:
        return jsonify({"ok": False, "error": "slug is required"}), 400
    state = _encode_oauth_state({"slug": slug, **_questionnaire_source_params()})
    redirect_uri = _wechat_oauth_callback_url()
    _questionnaire_logger().info(
        "oauth start slug=%s source_channel=%s campaign_id=%s staff_id=%s redirect_uri=%s",
        slug,
        request.args.get("source_channel", "").strip(),
        request.args.get("campaign_id", "").strip(),
        request.args.get("staff_id", "").strip(),
        redirect_uri,
    )
    query = urlencode(
        {
            "appid": current_app.config["WECHAT_MP_APP_ID"],
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": _wechat_oauth_scope(),
            "state": state,
        }
    )
    authorize_url = f"https://open.weixin.qq.com/connect/oauth2/authorize?{query}#wechat_redirect"
    return redirect(authorize_url)


@bp.route("/api/h5/wechat/oauth/callback", methods=["GET"])
def h5_wechat_oauth_callback():
    if not _wechat_oauth_is_configured():
        return jsonify({"ok": False, "error": "wechat_oauth_not_configured"}), 501
    code = request.args.get("code", "").strip()
    state_payload = _decode_oauth_state(request.args.get("state", "").strip())
    slug = state_payload.get("slug", "").strip()
    if not code:
        _questionnaire_logger().warning("oauth callback failed reason=missing_code")
        return jsonify({"ok": False, "error": "code is required"}), 400
    if not slug:
        _questionnaire_logger().warning("oauth callback failed reason=invalid_state")
        return jsonify({"ok": False, "error": "invalid_state"}), 400

    try:
        response = requests.get(
            "https://api.weixin.qq.com/sns/oauth2/access_token",
            params={
                "appid": current_app.config["WECHAT_MP_APP_ID"],
                "secret": current_app.config["WECHAT_MP_APP_SECRET"],
                "code": code,
                "grant_type": "authorization_code",
            },
            timeout=15,
        )
        response.raise_for_status()
        oauth_payload = response.json()
    except requests.RequestException as exc:
        _questionnaire_logger().exception("oauth callback failed slug=%s code=%s", slug, code)
        return jsonify({"ok": False, "error": f"wechat_oauth_exchange_failed: {exc}"}), 502

    if oauth_payload.get("errcode") not in (None, 0):
        _questionnaire_logger().warning(
            "oauth callback failed slug=%s code=%s wechat_payload=%s",
            slug,
            code,
            oauth_payload,
        )
        return jsonify({"ok": False, "error": "wechat_oauth_exchange_failed", "wechat_payload": oauth_payload}), 502

    openid = str(oauth_payload.get("openid") or "").strip()
    unionid = str(oauth_payload.get("unionid") or "").strip()
    access_token = str(oauth_payload.get("access_token") or "").strip()
    oauth_scope = _wechat_oauth_scope()
    if not unionid and oauth_scope == "snsapi_userinfo" and access_token and openid:
        try:
            userinfo_payload = _fetch_wechat_userinfo(access_token, openid)
        except requests.RequestException:
            _questionnaire_logger().exception(
                "oauth callback userinfo fetch failed slug=%s openid=%s",
                slug,
                _mask_identity_value(openid),
            )
        else:
            if userinfo_payload.get("errcode") not in (None, 0):
                _questionnaire_logger().warning(
                    "oauth callback userinfo fetch failed slug=%s openid=%s wechat_payload=%s",
                    slug,
                    _mask_identity_value(openid),
                    userinfo_payload,
                )
            else:
                unionid = str(userinfo_payload.get("unionid") or "").strip()
    respondent_key = unionid or openid
    session["questionnaire_h5_identity"] = {
        "openid": openid,
        "unionid": unionid,
        "respondent_key": respondent_key,
        "oauth_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "slug": slug,
    }
    session.modified = True
    _questionnaire_logger().info(
        "oauth session written slug=%s respondent_key=%s openid=%s unionid=%s",
        slug,
        _mask_identity_value(respondent_key),
        _mask_identity_value(openid),
        _mask_identity_value(unionid),
    )
    _questionnaire_logger().info(
        "oauth callback success slug=%s openid=%s unionid=%s",
        slug,
        _mask_identity_value(openid),
        _mask_identity_value(unionid),
    )

    redirect_query = urlencode({key: value for key, value in state_payload.items() if key != "slug"})
    target = _questionnaire_public_path(slug)
    if redirect_query:
        target = f"{target}?{redirect_query}"
    return redirect(target, code=302)


@bp.route("/api/archive/health", methods=["GET"])
def archive_health():
    try:
        client = ArchiveAdapterClient.from_app()
        result = client.health()
        return jsonify({"ok": True, "adapter": result})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 502


@bp.route("/api/archive/sync", methods=["POST"])
def archive_sync():
    payload = request.get_json(silent=True) or {}
    start_time = payload.get("start_time")
    end_time = payload.get("end_time")
    owner_userid = payload.get("owner_userid") or current_app.config["WECOM_DEFAULT_OWNER_USERID"]
    cursor = payload.get("cursor", "")

    if not start_time or not end_time or not owner_userid:
        return jsonify({"ok": False, "error": "start_time, end_time and owner_userid are required"}), 400

    run_id = create_sync_run(start_time, end_time, owner_userid, cursor)

    try:
        archive_logger.info(
            "manual archive sync requested run_id=%s owner_userid=%s cursor=%s window=%s..%s",
            run_id,
            owner_userid,
            cursor,
            start_time,
            end_time,
        )
        client = ArchiveAdapterClient.from_app()
        result = client.sync_messages(start_time, end_time, owner_userid, cursor)
        if result.get("external_userids"):
            result["contacts_sync"] = _ensure_contacts_for_external_userids(result.get("external_userids") or [])
        if result.get("group_chat_ids"):
            wecom_client = WeComClient.from_app()
            group_records = []
            for chat_id in result.get("group_chat_ids") or []:
                try:
                    detail = wecom_client.get_group_chat(chat_id)
                except WeComClientError:
                    continue
                group_records.append(normalize_group_chat_record(detail))
            upsert_group_chats(group_records)
        fetched_count = int(result.get("fetched_count", 0))
        inserted_count = int(result.get("inserted_count", 0))
        finish_sync_run(run_id, "success", fetched_count, inserted_count, raw_response=result)
        archive_logger.info(
            "manual archive sync finished run_id=%s fetched=%s inserted=%s last_seq=%s",
            run_id,
            fetched_count,
            inserted_count,
            result.get("last_seq", 0),
        )
        return jsonify(
            {
                "ok": True,
                "sync_run": {
                    "id": run_id,
                    "status": "success",
                    "fetched_count": fetched_count,
                    "inserted_count": inserted_count,
                    "has_more": bool(result.get("has_more")),
                    "next_cursor": result.get("next_cursor", ""),
                    "last_seq": result.get("last_seq", 0),
                },
            }
        )
    except Exception as exc:
        archive_logger.exception("manual archive sync failed run_id=%s", run_id)
        finish_sync_run(run_id, "failed", 0, 0, error_message=str(exc))
        return jsonify({"ok": False, "error": str(exc), "sync_run_id": run_id}), 502


@bp.route("/api/messages/<external_userid>", methods=["GET"])
def list_messages(external_userid: str):
    chat_type = request.args.get("chat_type", "").strip() or None
    try:
        messages = get_messages_by_user(external_userid, chat_type=chat_type)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "messages": messages})


@bp.route("/api/messages/<external_userid>/recent", methods=["GET"])
def list_recent_messages(external_userid: str):
    limit = request.args.get("limit", "20").strip() or "20"
    chat_type = request.args.get("chat_type", "").strip() or None
    try:
        messages = get_recent_messages_by_user(external_userid, int(limit), chat_type=chat_type)
    except ValueError as exc:
        if "chat_type" in str(exc):
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify({"ok": False, "error": "limit must be an integer"}), 400
    return jsonify({"ok": True, "messages": messages})


@bp.route("/api/messages/search", methods=["GET"])
def query_messages():
    external_userid = request.args.get("external_userid", "").strip()
    keyword = request.args.get("keyword", "").strip()
    if not external_userid or not keyword:
        return jsonify({"ok": False, "error": "external_userid and keyword are required"}), 400
    return jsonify({"ok": True, "messages": search_messages(external_userid, keyword)})


@bp.route("/api/contacts", methods=["GET"])
def list_contacts():
    owner_userid = request.args.get("owner_userid", "").strip() or _default_owner_userid()
    sync = request.args.get("sync", "1").strip().lower() not in {"0", "false", "no"}
    try:
        if sync:
            client = WeComClient.from_app()
            result = client.list_contacts(owner_userid)
            contact_ids = result.get("external_userid") or []
            records = []
            for external_userid in contact_ids:
                detail = client.get_contact(external_userid)
                normalized, _ = _sync_contact_detail_with_description_fix(
                    client,
                    detail,
                    owner_userid=owner_userid,
                    default_owner_userid=_default_owner_userid(),
                    tolerate_update_error=True,
                    log_stage="external_contact.read_list",
                )
                records.append(normalized)
            upsert_contacts(records)
        contacts = list_contacts_from_db(owner_userid)
        return jsonify({"ok": True, "contacts": contacts})
    except WeComClientError as exc:
        return _wecom_error_response(exc)


@bp.route("/api/contacts/<external_userid>", methods=["GET"])
def get_contact(external_userid: str):
    owner_userid = request.args.get("owner_userid", "").strip()
    sync = request.args.get("sync", "1").strip().lower() not in {"0", "false", "no"}
    try:
        if sync:
            local_contact = get_contact_by_external_userid(external_userid)
            resolved_owner = owner_userid or (local_contact.get("owner_userid") if local_contact else "") or _default_owner_userid()
            client = WeComClient.from_app()
            detail = client.get_contact(external_userid)
            normalized, _ = _sync_contact_detail_with_description_fix(
                client,
                detail,
                owner_userid=resolved_owner,
                default_owner_userid=_default_owner_userid(),
                tolerate_update_error=True,
                log_stage="external_contact.read_detail",
            )
            upsert_contacts([normalized])
        contact = get_contact_by_external_userid(external_userid)
        if not contact:
            return jsonify({"ok": False, "error": "contact not found"}), 404
        return jsonify({"ok": True, "contact": contact})
    except WeComClientError as exc:
        return _wecom_error_response(exc)


@bp.route("/api/contacts/description", methods=["POST"])
def update_contact_description():
    payload = request.get_json(silent=True) or {}
    external_userid = (payload.get("external_userid") or "").strip()
    description = payload.get("description")
    userid = (payload.get("userid") or _default_owner_userid()).strip()
    if not external_userid or description is None:
        return jsonify({"ok": False, "error": "external_userid and description are required"}), 400
    try:
        client = WeComClient.from_app()
        result = client.update_contact_description(
            {
                "userid": userid,
                "external_userid": external_userid,
                "description": description,
            }
        )
        detail = client.get_contact(external_userid)
        upsert_contacts([normalize_contact_record(detail, owner_userid=userid)])
        contact = get_contact_by_external_userid(external_userid)
        return jsonify({"ok": True, "result": result, "contact": contact})
    except WeComClientError as exc:
        return _wecom_error_response(exc)


@bp.route("/api/contacts/full-sync", methods=["POST"])
def full_sync_contacts():
    try:
        result = _sync_contacts(only_new=False)
        return jsonify({"ok": True, **result})
    except WeComClientError as exc:
        return _wecom_error_response(exc)


@bp.route("/api/contacts/sync-new", methods=["POST"])
def sync_new_contacts():
    try:
        result = _sync_contacts(only_new=True)
        return jsonify({"ok": True, **result})
    except WeComClientError as exc:
        return _wecom_error_response(exc)


@bp.route("/api/contacts/normalize-description", methods=["POST"])
def normalize_contact_descriptions():
    try:
        result = _normalize_contact_descriptions()
        return jsonify({"ok": True, **result})
    except WeComClientError as exc:
        return _wecom_error_response(exc)


@bp.route("/internal/wecom/external-contact/full-sync", methods=["POST"])
def full_sync_external_contact_identity():
    try:
        result = _sync_external_contact_identity_map(only_new=False)
        return jsonify({"ok": True, **result})
    except WeComClientError as exc:
        return _wecom_error_response(exc)


def _get_user_ops_deferred_job_counts() -> dict[str, int]:
    row = get_db().execute(
        """
        SELECT
            COUNT(*) AS total_count,
            COALESCE(SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END), 0) AS pending_count,
            COALESCE(SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END), 0) AS running_count,
            COALESCE(SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END), 0) AS success_count,
            COALESCE(SUM(CASE WHEN status = 'conflict' THEN 1 ELSE 0 END), 0) AS conflict_count,
            COALESCE(SUM(CASE WHEN status = 'skipped' THEN 1 ELSE 0 END), 0) AS skipped_count,
            COALESCE(SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END), 0) AS failed_count
        FROM user_ops_deferred_jobs
        """
    ).fetchone()
    return {
        "total_count": int(row["total_count"] or 0),
        "pending_count": int(row["pending_count"] or 0),
        "running_count": int(row["running_count"] or 0),
        "success_count": int(row["success_count"] or 0),
        "conflict_count": int(row["conflict_count"] or 0),
        "skipped_count": int(row["skipped_count"] or 0),
        "failed_count": int(row["failed_count"] or 0),
    }


@bp.route("/api/ops/status", methods=["GET"])
def ops_status():
    last_sync = get_last_sync_run() or {}
    callback_enabled = bool(
        (get_callback_config().get("token") and get_callback_config().get("aes_key") and get_callback_config().get("corp_id"))
    )
    payload = {
        "ok": True,
        "service_ok": True,
        "request_id": get_request_id(),
        "release_sha": str(current_app.config.get("RELEASE_SHA", "") or "").strip(),
        "app_started_at": APP_STARTED_AT_TEXT,
        "uptime_seconds": max(int((datetime.utcnow() - APP_STARTED_AT).total_seconds()), 0),
        "background_async_enabled": bool(current_app.config.get("CALLBACK_ASYNC_ENABLED", True)),
        "archived_messages_count": count_archived_messages(),
        "contacts_count": count_contacts(),
        "group_chats_count": count_group_chats(),
        "database_backend": get_db_backend(),
        "last_seq": get_archive_last_seq(),
        "last_archive_sync_run_id": last_sync.get("id"),
        "last_archive_sync_status": last_sync.get("status", ""),
        "last_archive_sync_time": last_sync.get("finished_at") or last_sync.get("created_at") or "",
        "last_contacts_sync_time": get_last_contacts_sync_time(),
        "callback_enabled": callback_enabled,
        "user_ops_deferred_jobs": _get_user_ops_deferred_job_counts(),
        "cron_script_path": current_app.config["CRON_SCRIPT_PATH"],
        "env_file_path": current_app.config["ENV_FILE_PATH"],
    }
    if get_db_backend() == "postgres":
        payload["database_url_configured"] = bool(current_app.config.get("DATABASE_URL"))
    else:
        payload["sqlite_path"] = current_app.config["DATABASE_PATH"]
    return jsonify(payload)


@bp.route("/api/group-chats/full-sync", methods=["POST"])
def full_sync_group_chats():
    try:
        result = _sync_group_chats(only_new=False)
        return jsonify({"ok": True, **result})
    except WeComClientError as exc:
        return _wecom_error_response(exc)


@bp.route("/api/group-chats/sync-new", methods=["POST"])
def sync_new_group_chats():
    try:
        result = _sync_group_chats(only_new=True)
        return jsonify({"ok": True, **result})
    except WeComClientError as exc:
        return _wecom_error_response(exc)


@bp.route("/wecom/external-contact/callback", methods=["GET", "POST"])
def receive_external_contact_callback():
    config = get_callback_config()
    token = config["token"]
    aes_key = config["aes_key"]
    corp_id = config["corp_id"]
    if not token or not aes_key or not corp_id:
        return jsonify({"ok": False, "error": "callback config is not complete"}), 500

    msg_signature = request.args.get("msg_signature", "")
    timestamp = request.args.get("timestamp", "")
    nonce = request.args.get("nonce", "")

    try:
        if request.method == "GET":
            echostr = request.args.get("echostr", "")
            verify_signature(token, timestamp, nonce, echostr, msg_signature)
            callback_logger.info("external contact callback verify success timestamp=%s nonce=%s", timestamp, nonce)
            return Response(decrypt_message(echostr, aes_key, corp_id), mimetype="text/plain")

        xml_text = request.data.decode("utf-8")
        envelope = parse_callback_xml(xml_text)
        encrypted = envelope.get("Encrypt", "")
        verify_signature(token, timestamp, nonce, encrypted, msg_signature)
        plain_xml = decrypt_message(encrypted, aes_key, corp_id)
        event_data = parse_callback_xml(plain_xml)
        event_type = (event_data.get("Event") or "").strip()
        change_type = (event_data.get("ChangeType") or "").strip()
        external_userid = (event_data.get("ExternalUserID") or "").strip()
        user_id = (event_data.get("UserID") or "").strip()
        event_time = int((event_data.get("CreateTime") or "0").strip() or 0)
        event_key = _build_external_contact_event_key(corp_id, event_data)

        logged = log_external_contact_event(
            corp_id=corp_id,
            event_type=event_type,
            change_type=change_type,
            external_userid=external_userid,
            user_id=user_id,
            event_time=event_time,
            event_key=event_key,
            payload_xml=plain_xml,
            payload_json=event_data,
        )
        callback_logger.info(
            "external contact event received event=%s change_type=%s external_userid=%s user_id=%s duplicate=%s",
            event_type.lower(),
            change_type.lower(),
            external_userid,
            user_id,
            logged.get("is_duplicate", False),
        )

        if not (logged.get("is_duplicate") and logged.get("process_status") == "success"):
            _dispatch_background_task("external_contact_event", _process_external_contact_event, int(logged["id"]))

        reply_xml = build_encrypted_reply("success", token, aes_key, corp_id, nonce=nonce)
        return Response(reply_xml, mimetype="application/xml")
    except (WeComCallbackError, WeComClientError, ET.ParseError, ValueError) as exc:
        callback_logger.exception("external contact callback handling failed")
        return jsonify({"ok": False, "error": str(exc)}), 400


@bp.route("/api/wecom/events", methods=["GET", "POST"])
def receive_wecom_event():
    config = get_callback_config()
    token = config["token"]
    aes_key = config["aes_key"]
    corp_id = config["corp_id"]
    if not token or not aes_key or not corp_id:
        return jsonify({"ok": False, "error": "callback config is not complete"}), 500

    msg_signature = request.args.get("msg_signature", "")
    timestamp = request.args.get("timestamp", "")
    nonce = request.args.get("nonce", "")

    try:
        if request.method == "GET":
            echostr = request.args.get("echostr", "")
            verify_signature(token, timestamp, nonce, echostr, msg_signature)
            callback_logger.info("callback verify success timestamp=%s nonce=%s", timestamp, nonce)
            return Response(decrypt_message(echostr, aes_key, corp_id), mimetype="text/plain")

        xml_text = request.data.decode("utf-8")
        envelope = parse_callback_xml(xml_text)
        encrypted = envelope.get("Encrypt", "")
        verify_signature(token, timestamp, nonce, encrypted, msg_signature)
        plain_xml = decrypt_message(encrypted, aes_key, corp_id)
        event_data = parse_callback_xml(plain_xml)
        event_name = (event_data.get("Event") or "").lower()
        callback_logger.info(
            "callback event received event=%s change_type=%s",
            event_name,
            (event_data.get("ChangeType") or "").lower(),
        )

        if event_name == "msgaudit_notify":
            _dispatch_background_task("msgaudit_notify", _trigger_incremental_archive_sync)
        elif event_name == "change_external_chat" or (event_data.get("ChangeType") or "").lower() in {"create", "update", "dismiss"}:
            _dispatch_background_task("change_external_chat", _handle_group_chat_change, event_data)

        reply_xml = build_encrypted_reply("success", token, aes_key, corp_id, nonce=nonce)
        return Response(reply_xml, mimetype="application/xml")
    except (WeComCallbackError, WeComClientError, WeComArchiveError, ET.ParseError) as exc:
        callback_logger.exception("callback handling failed")
        return jsonify({"ok": False, "error": str(exc)}), 400


def _handle_wecom_task(task_type: str, fn_name: str):
    payload = request.get_json(silent=True) or {}
    try:
        client = WeComClient.from_app()
        result = getattr(client, fn_name)(payload)
        local_id = save_outbound_task(task_type, payload, result)
        return jsonify({"ok": True, "task_id": local_id, "wecom_result": result})
    except (WeComClientError, AttributeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 502


@bp.route("/api/tasks/private-message", methods=["POST"])
def create_private_message_task():
    return _handle_wecom_task("private_message", "create_private_message_task")


@bp.route("/api/tasks/moment", methods=["POST"])
def create_moment_task():
    return _handle_wecom_task("moment", "create_moment_task")


@bp.route("/api/tasks/group-message", methods=["POST"])
def create_group_message_task():
    return _handle_wecom_task("group_message", "create_group_message_task")


@bp.route("/api/tags", methods=["GET"])
def list_tags():
    payload = {
        "tag_id": request.args.getlist("tag_id"),
        "group_id": request.args.getlist("group_id"),
    }
    payload = {key: value for key, value in payload.items() if value}
    try:
        client = WeComClient.from_app()
        result = client.list_tags(payload)
        return jsonify({"ok": True, "result": result})
    except WeComClientError as exc:
        return _wecom_error_response(exc)


@bp.route("/api/tags", methods=["POST"])
def create_tag():
    payload = request.get_json(silent=True) or {}
    try:
        client = WeComClient.from_app()
        result = client.create_tag(payload)
        return jsonify({"ok": True, "result": result})
    except WeComClientError as exc:
        return _wecom_error_response(exc)


@bp.route("/api/tags/mark", methods=["POST"])
def mark_tag():
    payload = request.get_json(silent=True) or {}
    userid = payload.get("userid")
    external_userid = payload.get("external_userid")
    add_tag = payload.get("add_tag") or []

    if not userid or not external_userid or not add_tag:
        return jsonify({"ok": False, "error": "userid, external_userid and add_tag are required"}), 400

    try:
        client = WeComClient.from_app()
        result = client.mark_tag(payload)
        save_tag_snapshot(userid, external_userid, add_tag)
        return jsonify({"ok": True, "result": result})
    except WeComClientError as exc:
        return _wecom_error_response(exc)


@bp.route("/api/tags/unmark", methods=["POST"])
def unmark_tag():
    payload = request.get_json(silent=True) or {}
    userid = payload.get("userid")
    external_userid = payload.get("external_userid")
    remove_tag = payload.get("remove_tag") or []

    if not userid or not external_userid or not remove_tag:
        return jsonify({"ok": False, "error": "userid, external_userid and remove_tag are required"}), 400

    try:
        client = WeComClient.from_app()
        result = client.mark_tag(payload)
        remove_tag_snapshot(userid, external_userid, remove_tag)
        return jsonify({"ok": True, "result": result})
    except WeComClientError as exc:
        return _wecom_error_response(exc)
