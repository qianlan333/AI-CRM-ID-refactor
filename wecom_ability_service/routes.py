from __future__ import annotations

import base64
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
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
    backfill_owner_class_terms_into_lead_pool,
    bind_openid_to_external_contact,
    bind_mobile_to_external_contact,
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
    get_sidebar_lead_pool_status,
    get_messages_by_user,
    get_recent_messages_by_user,
    get_user_ops_overview,
    import_mobile_class_term_source,
    import_activation_status_source,
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
    schedule_user_ops_auto_assign_class_term_job,
    set_settings,
    submit_questionnaire,
    upsert_signup_tag_rule,
    update_class_user_status_sync_result,
    target_contact_description,
    ThirdPartyUserSyncError,
    update_contact_description_snapshot,
    update_questionnaire,
    upsert_sidebar_lead_pool_class_term,
    migrate_class_user_status_from_contact_tags,
    upsert_external_contact_identity,
    upsert_group_chats,
    upsert_contacts,
    mark_external_contact_identity_status,
    mark_external_contact_follow_user_status,
)
from .wecom_client import WeComClient, WeComClientError
from .routes_support_service import (
    _apply_signup_sidebar_tag as _apply_signup_sidebar_tag_impl,
    _configured_signup_tag_rules_payload as _configured_signup_tag_rules_payload_impl,
    _ensure_contacts_for_external_userids as _ensure_contacts_for_external_userids_impl,
    _list_class_user_management_records_live as _list_class_user_management_records_live_impl,
    _normalize_contact_descriptions as _normalize_contact_descriptions_impl,
    _refresh_class_user_management_live_data as _refresh_class_user_management_live_data_impl,
    _signup_tag_bootstrap_payload as _signup_tag_bootstrap_payload_impl,
    _sync_contact_detail_with_description_fix as _sync_contact_detail_with_description_fix_impl,
    _sync_contacts as _sync_contacts_impl,
    _sync_external_contact_identity_map as _sync_external_contact_identity_map_impl,
    _sync_group_chats as _sync_group_chats_impl,
    _trigger_incremental_archive_sync as _trigger_incremental_archive_sync_impl,
)

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


def _coerce_request_bool(value: object, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


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
    return _sync_contacts_impl(only_new=only_new)


def _sync_external_contact_identity_map(*, only_new: bool) -> dict:
    return _sync_external_contact_identity_map_impl(only_new=only_new)


def _ensure_contacts_for_external_userids(external_userids: list[str]) -> dict:
    return _ensure_contacts_for_external_userids_impl(external_userids)


def _sync_group_chats(*, only_new: bool) -> dict:
    return _sync_group_chats_impl(only_new=only_new)


def _trigger_incremental_archive_sync() -> dict:
    return _trigger_incremental_archive_sync_impl()


def _normalize_contact_descriptions() -> dict:
    return _normalize_contact_descriptions_impl()


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
    return render_template(
        "sidebar_bind_mobile.html",
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


@bp.route("/api/sidebar/lead-pool/status", methods=["GET"])
def sidebar_lead_pool_status():
    external_userid = request.args.get("external_userid", "").strip()
    owner_userid = request.args.get("owner_userid", "").strip()
    if not external_userid:
        return jsonify({"ok": False, "error": "external_userid is required"}), 400
    try:
        payload = get_sidebar_lead_pool_status(external_userid=external_userid, owner_userid=owner_userid)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **payload})


@bp.route("/api/sidebar/lead-pool/upsert-class-term", methods=["POST"])
def sidebar_lead_pool_upsert_class_term():
    payload = request.get_json(silent=True) or {}
    try:
        result = upsert_sidebar_lead_pool_class_term(
            external_userid=str(payload.get("external_userid") or "").strip(),
            owner_userid=str(payload.get("owner_userid") or "").strip(),
            class_term_no=int(payload.get("class_term_no")),
            operator=str(payload.get("operator") or "").strip(),
        )
        status_payload = get_sidebar_lead_pool_status(
            external_userid=str(payload.get("external_userid") or "").strip(),
            owner_userid=str(payload.get("owner_userid") or "").strip(),
        )
    except (TypeError, ValueError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except WeComClientError as exc:
        return _wecom_error_response(exc)
    return jsonify({"ok": True, **status_payload, "upsert": result})


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
    unionid = request.args.get("unionid", "").strip()
    try:
        payload = resolve_person_identity(external_userid=external_userid, mobile=mobile, unionid=unionid)
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
        is_wecom_added=request.args.get("is_wecom_added", "").strip(),
        is_mobile_bound=request.args.get("is_mobile_bound", "").strip(),
        huangxiaocan_activation_state=request.args.get("huangxiaocan_activation_state", "").strip(),
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
    return (
        jsonify(
            {
                "ok": False,
                "error": "deprecated_internal_only",
                "message": "legacy user-ops reload is no longer part of admin V2; use internal maintenance helpers only",
            }
        ),
        410,
    )


@bp.route("/api/admin/user-ops/import-experience-leads", methods=["POST"])
def admin_user_ops_import_experience_leads():
    return (
        jsonify(
            {
                "ok": False,
                "error": "deprecated_internal_only",
                "message": "legacy experience-leads import is no longer exposed by admin V2",
            }
        ),
        410,
    )


@bp.route("/api/admin/user-ops/import-mobile-class-terms", methods=["POST"])
def admin_user_ops_import_mobile_class_terms():
    uploaded_file = request.files.get("file")
    pasted_text = ""
    if uploaded_file and uploaded_file.filename:
        try:
            payload = import_mobile_class_term_source(
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
        payload = import_mobile_class_term_source(pasted_text=pasted_text)
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
    return (
        jsonify(
            {
                "ok": False,
                "error": "deprecated_internal_only",
                "message": "legacy class-term backfill is no longer exposed by admin V2",
            }
        ),
        410,
    )


@bp.route("/api/internal/user-ops/lead-pool/backfill-owner-class-terms", methods=["POST"])
def internal_user_ops_backfill_owner_class_terms():
    payload_json = request.get_json(silent=True) or {}
    owner_userid = str(payload_json.get("owner_userid") or "ZhaoYanFang").strip()
    class_term_min_value = payload_json.get("class_term_min", 1)
    class_term_max_value = payload_json.get("class_term_max", 5)
    dry_run = _coerce_request_bool(payload_json.get("dry_run", True), default=True)
    try:
        class_term_min = int(class_term_min_value)
        class_term_max = int(class_term_max_value)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "class_term_min and class_term_max must be integers"}), 400
    try:
        payload = backfill_owner_class_terms_into_lead_pool(
            owner_userid=owner_userid,
            class_term_min=class_term_min,
            class_term_max=class_term_max,
            dry_run=dry_run,
            operator=str(payload_json.get("operator") or "").strip(),
            entry_source=str(payload_json.get("entry_source") or "").strip(),
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except WeComClientError as exc:
        return _wecom_error_response(exc)
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
        is_wecom_added=request.args.get("is_wecom_added", "").strip(),
        is_mobile_bound=request.args.get("is_mobile_bound", "").strip(),
        huangxiaocan_activation_state=request.args.get("huangxiaocan_activation_state", "").strip(),
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
    return render_template("admin_class_user_management.html")


@bp.route("/admin/class-user-backoffice/ui", methods=["GET"])
def admin_class_user_backoffice_ui():
    return render_template("admin_class_user_backoffice.html")


@bp.route("/admin/questionnaires/ui", methods=["GET"])
def admin_questionnaires_ui():
    return render_template("admin_questionnaires.html")


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
    return render_template("questionnaire_h5_page.html", page_state=page_state)


@bp.route("/s/<slug>/submitted", methods=["GET"])
def questionnaire_h5_submitted(slug: str):
    questionnaire = get_public_questionnaire_by_slug(slug)
    if not questionnaire:
        abort(404)
    return render_template("questionnaire_h5_submitted.html")


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
        "oauth_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
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
