from __future__ import annotations

import json
import logging
import os
import re
import secrets
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from . import repo
from .domain import (
    ENTRY_CHANGE_TYPES,
    channel_enabled,
    channel_payload,
    effect_status_for_duplicate,
    extract_corp_id,
    extract_scene,
    extract_welcome_code,
    scene_match,
    text,
)
from .identity_bridge import sync_external_contact_identity_for_event
from .schemas import (
    DiagnoseChannelRuntimeQuery,
    GenerateChannelQrCodeCommand,
    ProcessChannelEntryCommand,
    ProcessWeComExternalContactEventCommand,
    RepairChannelEntryCommand,
)
from .wecom_adapter import WeComAdapterBlocked, WeComApiError, get_wecom_adapter, wecom_adapter_diagnostics
from .wecom_crypto import build_encrypted_reply, decrypt_message, parse_callback_xml, verify_signature
from aicrm_next.platform_foundation.command_bus.models import CommandContext
from aicrm_next.platform_foundation.external_effects import (
    ExternalEffectService,
    WECOM_CONTACT_TAG_MARK,
    WECOM_WELCOME_MESSAGE_SEND,
)
from aicrm_next.platform_foundation.external_effects.worker import ExternalEffectWorker
from aicrm_next.platform_foundation.internal_events import InternalEventService
from aicrm_next.shared.runtime_settings import runtime_bool, runtime_csv

CUSTOMER_NAME_PLACEHOLDER_RE = re.compile(r"\{\{\s*客户名\s*\}\}")
LOGGER = logging.getLogger(__name__)
_WELCOME_EFFECT_EXECUTOR = ThreadPoolExecutor(
    max_workers=2,
    thread_name_prefix="channel-entry-welcome-effect",
)


def callback_config() -> dict[str, str]:
    return {
        "corp_id": text(os.getenv("WECOM_CORP_ID")),
        "token": text(os.getenv("WECOM_CALLBACK_TOKEN")),
        "aes_key": text(os.getenv("WECOM_CALLBACK_AES_KEY")),
    }


def _event_key(corp_id: str, event_data: dict[str, Any]) -> str:
    fields = [
        corp_id,
        text(event_data.get("Event")),
        text(event_data.get("ChangeType")),
        text(event_data.get("ExternalUserID")),
        text(event_data.get("UserID")),
        text(event_data.get("CreateTime")),
        text(event_data.get("WelcomeCode")),
        text(event_data.get("State")),
    ]
    return "|".join(fields)


def decrypt_callback_body(*, query: dict[str, str], body: bytes) -> tuple[dict[str, Any], str]:
    config = callback_config()
    xml_text = body.decode("utf-8")
    envelope = parse_callback_xml(xml_text)
    encrypted = text(envelope.get("Encrypt"))
    verify_signature(config["token"], text(query.get("timestamp")), text(query.get("nonce")), encrypted, text(query.get("msg_signature")))
    plain_xml = decrypt_message(encrypted, config["aes_key"], config["corp_id"])
    return parse_callback_xml(plain_xml), plain_xml


def verify_callback_echostr(query: dict[str, str]) -> str:
    config = callback_config()
    echostr = text(query.get("echostr"))
    verify_signature(config["token"], text(query.get("timestamp")), text(query.get("nonce")), echostr, text(query.get("msg_signature")))
    return decrypt_message(echostr, config["aes_key"], config["corp_id"])


def encrypted_success_reply(query: dict[str, str]) -> str:
    config = callback_config()
    return build_encrypted_reply("success", config["token"], config["aes_key"], config["corp_id"], nonce=text(query.get("nonce")))


def resolve_channel_for_scene(*, scene_value: str, corp_id: str = "", persist_alias: bool = True) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    scene = text(scene_value)
    if not scene:
        return None, scene_match("missing_scene", "")
    asset = repo.find_qrcode_asset_by_scene(text(corp_id), scene)
    if asset:
        asset_status = text(asset.get("status"))
        match = scene_match(f"qrcode_asset_{asset_status or 'unknown'}", scene, {"id": asset.get("channel_id"), "scene_alias_id": asset.get("id"), "status": asset_status, "source": asset.get("generation_source")})
        match["qrcode_asset_id"] = int(asset.get("id") or 0) or None
        if asset_status in {"stale", "quarantined", "revoked"}:
            match["reason"] = "qrcode_asset_not_acceptable"
            return None, match
        if int(asset.get("id") or 0) > 0 and persist_alias:
            repo.touch_qrcode_asset_callback(int(asset["id"]))
        channel = {
            **asset,
            "id": int(asset.get("channel_id") or asset.get("channel_row_id") or 0),
            "scene_value": text(asset.get("channel_scene_value") or asset.get("scene_value")),
            "qr_url": text(asset.get("channel_qr_url") or asset.get("qr_url")),
            "status": text(asset.get("channel_status") or asset.get("status")),
        }
        if asset_status == "retired":
            match["reason"] = "retired_qrcode_asset_used"
        return channel, match
    channel = repo.find_confirmed_channel_by_scene_alias(text(corp_id), scene)
    if channel:
        if persist_alias:
            repo.update_alias_last_seen_at(text(corp_id), scene)
        return channel, scene_match("scene_alias", scene, channel)
    suggestion = repo.find_channel_by_historical_scene_value(scene)
    match = scene_match("not_found", scene)
    match["reason"] = "qrcode_scene_unrecognized"
    if suggestion:
        match["historical_vote"] = {
            "suggested_channel_id": int(suggestion.get("id") or 0) or None,
            "requires_admin_confirmation": True,
        }
    return None, match


def _log_effect(command: ProcessChannelEntryCommand, *, effect_type: str, idempotency_key: str, status: str, channel_id: int | None, scene_value: str, reason: str, request_json: dict[str, Any] | None = None, response_json: dict[str, Any] | None = None) -> dict[str, Any]:
    if command.dry_run:
        return {"effect_type": effect_type, "idempotency_key": idempotency_key, "status": "skipped", "reason": "dry_run"}
    return repo.upsert_channel_entry_effect_log(
        effect_type=effect_type,
        idempotency_key=idempotency_key,
        status=status,
        event_log_id=command.event_log_id,
        channel_id=channel_id,
        scene_value=scene_value,
        external_contact_id=command.external_contact_id,
        owner_staff_id=command.follow_user_userid,
        reason=reason,
        request_json=repo.json_safe(request_json or {}),
        response_json=repo.json_safe(response_json or {}),
    )


def _plan_channel_entry_effect(
    command: ProcessChannelEntryCommand,
    *,
    effect_type: str,
    adapter_name: str,
    operation: str,
    target_type: str,
    target_id: str,
    business_id: str,
    idempotency_key: str,
    payload: dict[str, Any],
    payload_summary: dict[str, Any],
) -> dict[str, Any]:
    return ExternalEffectService().plan_effect(
        effect_type=effect_type,
        adapter_name=adapter_name,
        operation=operation,
        target_type=target_type,
        target_id=target_id,
        business_type="channel_entry",
        business_id=business_id,
        source_module="channel_entry.application",
        source_event_id=str(command.event_log_id or ""),
        idempotency_key=f"channel_entry:{idempotency_key}",
        context=CommandContext(
            actor_id=text(command.operator_id or command.follow_user_userid),
            actor_type="channel_entry",
            request_id=str(command.event_log_id or ""),
            trace_id=f"channel-entry-{command.event_log_id}" if command.event_log_id else idempotency_key,
            source_route="channel_entry.process_channel_entry",
            dry_run=bool(command.dry_run),
        ),
        payload=payload,
        payload_summary=payload_summary,
        status="queued",
        execution_mode="execute",
    )


def _welcome_realtime_wakeup_enabled() -> bool:
    return runtime_bool("AICRM_EXTERNAL_EFFECT_WECOM_EXECUTE") and WECOM_WELCOME_MESSAGE_SEND in runtime_csv(
        "AICRM_EXTERNAL_EFFECT_ALLOWED_TYPES"
    )


def _dispatch_welcome_external_effect_job(job_id: int) -> None:
    try:
        ExternalEffectWorker(locked_by="channel-entry-welcome-realtime").dispatch_one(int(job_id))
    except Exception:
        LOGGER.exception(
            "channel entry welcome external effect realtime dispatch failed",
            extra={"external_effect_job_id": int(job_id or 0)},
        )


def _wake_welcome_external_effect_job(job_id: Any) -> bool:
    try:
        normalized_job_id = int(job_id or 0)
    except (TypeError, ValueError):
        normalized_job_id = 0
    if normalized_job_id <= 0 or not _welcome_realtime_wakeup_enabled():
        return False
    _WELCOME_EFFECT_EXECUTOR.submit(_dispatch_welcome_external_effect_job, normalized_job_id)
    return True


def _emit_channel_entry_internal_event(
    command: ProcessChannelEntryCommand,
    *,
    channel_id: int,
    scene: str,
    channel_contact: dict[str, Any],
) -> dict[str, Any]:
    try:
        result = InternalEventService().emit_event(
            event_type="channel_entry.entered",
            aggregate_type="automation_channel",
            aggregate_id=str(channel_id),
            subject_type="external_userid",
            subject_id=text(command.external_contact_id),
            idempotency_key=f"channel_entry:{command.event_log_id or channel_id}:{command.external_contact_id}:{scene}",
            source_module="channel_entry.application",
            source_command_id=str(command.event_log_id or ""),
            payload={
                "source_type": "channel_entry",
                "source_key": f"channel:{channel_id}",
                "channel_id": channel_id,
                "scene_value": scene,
                "external_userid": command.external_contact_id,
                "owner_userid": command.follow_user_userid,
                "channel_contact_id": channel_contact.get("id"),
                "payload": repo.json_safe(command.payload_json or {}),
            },
            payload_summary={
                "channel_id": channel_id,
                "scene_value": scene,
                "external_userid": command.external_contact_id,
            },
            context=CommandContext(
                actor_id=text(command.follow_user_userid) or "channel_entry",
                actor_type="system",
                request_id=str(command.event_log_id or ""),
                trace_id=f"channel-entry-{command.event_log_id}" if command.event_log_id else "",
                source_route="channel_entry.process_channel_entry",
            ),
        )
        return {"ok": True, "event_id": text((result.get("event") or {}).get("event_id")), "consumer_run_count": len(result.get("consumer_runs") or [])}
    except Exception as exc:
        LOGGER.warning("channel entry internal event emit failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def _adapter_failure(exc: Exception) -> tuple[str, dict[str, Any]]:
    if isinstance(exc, WeComAdapterBlocked):
        payload: dict[str, Any] = {"reason": exc.reason}
        if exc.missing_config:
            payload["missing_config"] = exc.missing_config
        return exc.reason, payload
    if isinstance(exc, WeComApiError):
        payload = {"reason": "wecom_api_error", "message": exc.message}
        if exc.payload:
            payload["wecom_result"] = exc.payload
        return "wecom_api_error", payload
    return "wecom_api_error", {"reason": "wecom_api_error", "message": str(exc)}


def _welcome_attachments(channel: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    attachments: list[dict[str, Any]] = []
    for key, msgtype in (
        ("welcome_image_library_ids", "image"),
        ("welcome_attachment_library_ids", "file"),
        ("welcome_miniprogram_library_ids", "miniprogram"),
    ):
        raw = channel.get(key) or []
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except ValueError:
                raw = []
        for item in raw if isinstance(raw, list) else []:
            if isinstance(item, dict):
                if item.get("missing") or item.get("exists") is False:
                    return attachments, "material_resolve_failed"
                attachment = {"msgtype": msgtype}
                if msgtype == "miniprogram":
                    required = ("appid", "page", "title", "pic_media_id")
                    if any(not text(item.get(field)) for field in required):
                        return attachments, "material_resolve_failed"
                    attachment.update({field: text(item.get(field)) for field in required})
                else:
                    media_id = text(item.get("media_id") or item.get("material_id") or item.get("pic_media_id"))
                    if not media_id:
                        return attachments, "material_resolve_failed"
                    attachment["media_id"] = media_id
                attachments.append(attachment)
                continue
            try:
                material_id = int(item or 0)
            except (TypeError, ValueError):
                return attachments, "material_resolve_failed"
            if material_id <= 0:
                return attachments, "material_resolve_failed"
            attachments.append({"msgtype": msgtype, "material_id": material_id})
    if len(attachments) > 9:
        return attachments, "attachment_limit_exceeded"
    return attachments, ""


def _resolve_welcome_customer_name(command: ProcessChannelEntryCommand) -> str:
    try:
        return text(
            repo.resolve_external_contact_customer_name(
                command.external_contact_id,
                corp_id=extract_corp_id(command.payload_json),
            )
        )
    except Exception:
        return ""


def _render_welcome_message_template(message: Any, command: ProcessChannelEntryCommand) -> str:
    rendered = text(message)
    if not CUSTOMER_NAME_PLACEHOLDER_RE.search(rendered):
        return rendered
    return CUSTOMER_NAME_PLACEHOLDER_RE.sub(_resolve_welcome_customer_name(command), rendered)


def _send_welcome(command: ProcessChannelEntryCommand, *, channel: dict[str, Any], scene: str) -> dict[str, Any]:
    channel_id = int(channel.get("id") or 0)
    welcome_code = extract_welcome_code(command.payload_json)
    key = f"{extract_corp_id(command.payload_json)}:{command.external_contact_id}:{command.follow_user_userid}:{welcome_code}:welcome"
    if effect_status_for_duplicate(repo.get_channel_entry_effect_log("welcome_message", key)):
        return {"attempted": False, "sent": False, "reason": "idempotent_success_exists", "welcome_code": welcome_code}
    attachments, attachment_error = _welcome_attachments(channel)
    if attachment_error:
        result = {"attempted": True, "sent": False, "reason": attachment_error, "attachments": attachments}
        _log_effect(command, effect_type="welcome_message", idempotency_key=key, status="failed", channel_id=channel_id, scene_value=scene, reason=attachment_error, response_json=result)
        return result
    text_content = _render_welcome_message_template(channel.get("welcome_message"), command)
    if not text_content and not attachments:
        result = {"attempted": False, "sent": False, "reason": "no_welcome_message_configured"}
        _log_effect(command, effect_type="welcome_message", idempotency_key=key, status="skipped", channel_id=channel_id, scene_value=scene, reason=result["reason"], response_json=result)
        return result
    if not welcome_code:
        result = {"attempted": True, "sent": False, "reason": "welcome_code_missing"}
        _log_effect(command, effect_type="welcome_message", idempotency_key=key, status="skipped", channel_id=channel_id, scene_value=scene, reason=result["reason"], response_json=result)
        return result
    if not command.send_welcome_message:
        result = {"attempted": False, "sent": False, "reason": "send_welcome_message_disabled"}
        _log_effect(command, effect_type="welcome_message", idempotency_key=key, status="skipped", channel_id=channel_id, scene_value=scene, reason=result["reason"], response_json=result)
        return result
    payload: dict[str, Any] = {"welcome_code": welcome_code}
    if text_content:
        payload["text"] = {"content": text_content}
    if attachments:
        payload["attachments"] = attachments
    if command.dry_run:
        return {"attempted": False, "sent": False, "reason": "dry_run", "request_payload": payload}
    try:
        job = _plan_channel_entry_effect(
            command,
            effect_type=WECOM_WELCOME_MESSAGE_SEND,
            adapter_name="wecom_welcome_message",
            operation="send",
            target_type="external_user",
            target_id=command.external_contact_id,
            business_id=str(channel_id),
            idempotency_key=key,
            payload={
                **payload,
                "external_userid": command.external_contact_id,
                "follow_user_userid": command.follow_user_userid,
                "channel_id": channel_id,
                "scene_value": scene,
            },
            payload_summary={
                "external_userid": command.external_contact_id,
                "follow_user_userid": command.follow_user_userid,
                "channel_id": channel_id,
                "scene_value": scene,
                "welcome_code_present": bool(welcome_code),
                "text_present": bool(text_content),
                "attachment_count": len(attachments),
            },
        )
    except Exception as exc:
        result = {"attempted": True, "sent": False, "reason": "external_effect_queue_failed", "welcome_code": welcome_code, "message": str(exc)}
        _log_effect(command, effect_type="welcome_message", idempotency_key=key, status="failed", channel_id=channel_id, scene_value=scene, reason="external_effect_queue_failed", request_json=payload, response_json=result)
        return result
    result = {
        "attempted": True,
        "sent": False,
        "queued": True,
        "reason": "external_effect_job_queued",
        "welcome_code": welcome_code,
        "external_effect_job_id": job.get("id"),
        "immediate_dispatch_scheduled": _wake_welcome_external_effect_job(job.get("id")),
        "real_external_call_executed": False,
        "attachments": attachments,
    }
    _log_effect(command, effect_type="welcome_message", idempotency_key=key, status="queued", channel_id=channel_id, scene_value=scene, reason="external_effect_job_queued", request_json=payload, response_json=result)
    return result


def _apply_tag(command: ProcessChannelEntryCommand, *, channel: dict[str, Any], scene: str) -> dict[str, Any]:
    channel_id = int(channel.get("id") or 0)
    tag_id = text(channel.get("entry_tag_id"))
    key = f"{extract_corp_id(command.payload_json)}:{command.external_contact_id}:{command.follow_user_userid}:{tag_id}:{channel_id}:tag"
    if not tag_id:
        result = {"attempted": False, "applied": False, "reason": "no_entry_tag_configured"}
        _log_effect(command, effect_type="entry_tag", idempotency_key=key, status="skipped", channel_id=channel_id, scene_value=scene, reason=result["reason"], response_json=result)
        return result
    if effect_status_for_duplicate(repo.get_channel_entry_effect_log("entry_tag", key)):
        return {"attempted": False, "applied": False, "reason": "idempotent_success_exists", "entry_tag_id": tag_id}
    payload = {"external_userid": command.external_contact_id, "follow_user_userid": command.follow_user_userid, "add_tags": [tag_id], "remove_tags": []}
    if command.dry_run:
        return {"attempted": False, "applied": False, "reason": "dry_run", "request_payload": payload}
    try:
        job = _plan_channel_entry_effect(
            command,
            effect_type=WECOM_CONTACT_TAG_MARK,
            adapter_name="wecom_tag",
            operation="mark",
            target_type="external_user",
            target_id=command.external_contact_id,
            business_id=str(channel_id),
            idempotency_key=key,
            payload={
                **payload,
                "channel_id": channel_id,
                "scene_value": scene,
            },
            payload_summary={
                "external_userid": command.external_contact_id,
                "follow_user_userid": command.follow_user_userid,
                "channel_id": channel_id,
                "scene_value": scene,
                "tag_ids": [tag_id],
                "operation": "mark",
            },
        )
    except Exception as exc:
        result = {"attempted": True, "applied": False, "reason": "external_effect_queue_failed", "entry_tag_id": tag_id, "message": str(exc)}
        _log_effect(command, effect_type="entry_tag", idempotency_key=key, status="failed", channel_id=channel_id, scene_value=scene, reason="external_effect_queue_failed", request_json=payload, response_json=result)
        return result
    result = {
        "attempted": True,
        "applied": False,
        "queued": True,
        "reason": "external_effect_job_queued",
        "entry_tag_id": tag_id,
        "external_effect_job_id": job.get("id"),
        "real_external_call_executed": False,
    }
    _log_effect(command, effect_type="entry_tag", idempotency_key=key, status="queued", channel_id=channel_id, scene_value=scene, reason="external_effect_job_queued", request_json=payload, response_json=result)
    return result


def process_channel_entry(command: ProcessChannelEntryCommand) -> dict[str, Any]:
    scene = extract_scene(command.payload_json)
    corp_id = extract_corp_id(command.payload_json)
    channel, match = resolve_channel_for_scene(scene_value=scene, corp_id=corp_id, persist_alias=not command.dry_run)
    if not scene:
        return {"handled": False, "mode": "channel_not_found", "reason": "missing_channel_scene", "scene_match": match}
    if not channel:
        reason = text(match.get("reason")) or "channel_not_found"
        _log_effect(command, effect_type="channel_contact", idempotency_key=f"{corp_id}:{command.external_contact_id}:{scene}:not_found", status="failed", channel_id=None, scene_value=scene, reason=reason, response_json={"scene_match": match})
        return {"handled": False, "mode": "channel_not_found", "reason": reason, "scene_match": match}

    channel_id = int(channel["id"])
    assignment_result: dict[str, Any] = {}
    if not text(command.follow_user_userid) and text(channel.get("assignment_mode")) == "multi_staff":
        try:
            assignment_result = repo.choose_channel_assignee(
                channel_id,
                external_contact_id=command.external_contact_id,
                wecom_user_id="",
                write_event=not command.dry_run,
                source_payload=command.payload_json,
            )
        except Exception as exc:
            assignment_result = {"ok": False, "reason": text(str(exc)) or "assignment_failed"}
    command.follow_user_userid = (
        text(command.follow_user_userid)
        or text(assignment_result.get("assignee_staff_id"))
        or text(channel.get("owner_staff_id"))
        or "HuangYouCan"
    )
    if not channel_enabled(channel):
        for effect_type, response in {
            "channel_contact": {"attempted": False, "reason": "channel_disabled"},
            "welcome_message": {"attempted": False, "sent": False, "reason": "channel_disabled"},
            "entry_tag": {"attempted": False, "applied": False, "reason": "channel_disabled"},
        }.items():
            _log_effect(
                command,
                effect_type=effect_type,
                idempotency_key=f"{corp_id}:{command.external_contact_id}:{channel_id}:{effect_type}:channel_disabled",
                status="skipped",
                channel_id=channel_id,
                scene_value=scene,
                reason="channel_disabled",
                response_json=response,
            )
        return {
            "handled": False,
            "mode": "channel_disabled",
            "reason": "channel_disabled" if text(channel.get("status")) != "revoked" else "channel_revoked",
            "scene_match": match,
            "channel": channel_payload(channel),
            "baseline_effects": {
                "channel_contact": {"attempted": False, "reason": "channel_disabled"},
                "welcome_message": {"attempted": False, "sent": False, "reason": "channel_disabled"},
                "entry_tag": {"attempted": False, "applied": False, "reason": "channel_disabled"},
            },
        }

    if command.dry_run:
        channel_contact = {"planned": True, "channel_id": channel_id, "external_contact_id": command.external_contact_id}
    else:
        channel_contact = repo.upsert_channel_contact(channel_id=channel_id, external_contact_id=command.external_contact_id, owner_staff_id=command.follow_user_userid, source_payload=command.payload_json)
        channel_entry_event = _emit_channel_entry_internal_event(command, channel_id=channel_id, scene=scene, channel_contact=channel_contact)
        _log_effect(command, effect_type="channel_contact", idempotency_key=f"{corp_id}:{command.external_contact_id}:{command.follow_user_userid}:{channel_id}:contact", status="success", channel_id=channel_id, scene_value=scene, reason="upserted", response_json=channel_contact)
    if command.dry_run:
        channel_entry_event = {"ok": False, "reason": "dry_run"}

    welcome = _send_welcome(command, channel=channel, scene=scene)
    tag = _apply_tag(command, channel=channel, scene=scene)
    return {
        "handled": True,
        "mode": "channel_baseline_only",
        "reason": "channel_entry_baseline_recorded",
        "scene_match": match,
        "channel": channel_payload(channel),
        "baseline_effects": {"channel_contact": channel_contact, "welcome_message": welcome, "entry_tag": tag},
        "channel_contact": channel_contact,
        "welcome_message": welcome,
        "entry_tag": tag,
        "assignment": assignment_result,
        "channel_entry_internal_event": channel_entry_event,
    }


def process_wecom_external_contact_event(command: ProcessWeComExternalContactEventCommand) -> dict[str, Any]:
    event = command.event_data
    logged = repo.log_external_contact_event(
        corp_id=command.corp_id,
        event_type=text(event.get("Event")),
        change_type=text(event.get("ChangeType")),
        external_userid=text(event.get("ExternalUserID")),
        user_id=text(event.get("UserID")),
        event_time=int(text(event.get("CreateTime")) or 0),
        event_key=_event_key(command.corp_id, event),
        payload_xml=command.payload_xml,
        payload_json=event,
    )
    result = {"handled": False, "event_log": logged}
    try:
        identity_sync = sync_external_contact_identity_for_event(event, corp_id=command.corp_id)
        result["identity_sync"] = identity_sync
        if text(event.get("Event")) == "change_external_contact" and text(event.get("ChangeType")) in ENTRY_CHANGE_TYPES:
            if text(identity_sync.get("status")) != "success":
                reason = text(identity_sync.get("reason")) or text(identity_sync.get("status")) or "identity_sync_failed"
                raise RuntimeError(f"identity_sync_failed:{reason}")
            entry = process_channel_entry(
                ProcessChannelEntryCommand(
                    external_contact_id=text(event.get("ExternalUserID")),
                    payload_json={**event, "corp_id": command.corp_id},
                    follow_user_userid=text(event.get("UserID")),
                    event_action=text(event.get("ChangeType")),
                    send_welcome_message=bool(text(event.get("WelcomeCode"))),
                    event_log_id=int(logged.get("id") or 0) or None,
                )
            )
            repo.mark_event_status(int(logged["id"]), "success")
            result.update({"handled": bool(entry.get("handled")), "entry_result": entry})
        else:
            repo.mark_event_status(int(logged["id"]), "success")
    except Exception as exc:
        repo.mark_event_status(int(logged["id"]), "failed", str(exc))
        raise
    return result


def diagnose_channel_runtime(query: DiagnoseChannelRuntimeQuery) -> dict[str, Any]:
    channel = repo.get_channel_by_id(int(query.channel_id or 0)) if int(query.channel_id or 0) > 0 else None
    match: dict[str, Any] = {}
    if not channel and text(query.scene_value):
        channel, match = resolve_channel_for_scene(scene_value=query.scene_value, persist_alias=False)
    elif channel:
        match = scene_match("channel_id", text(channel.get("scene_value")), channel)
    channel_id = int((channel or {}).get("id") or 0)
    aliases = repo.list_channel_scene_aliases(channel_id) if channel_id else []
    effects = repo.list_channel_entry_effect_logs(channel_id=channel_id or None, scene_value=text(query.scene_value), limit=20)
    adapter = wecom_adapter_diagnostics()
    return {
        "ok": True,
        "scene_resolve_path": match,
        "scene_resolve": match,
        "current_scene": text((channel or {}).get("scene_value")),
        "aliases": aliases,
        "channel": channel_payload(channel or {}) if channel else {},
        "channel_status": text((channel or {}).get("status")),
        "welcome_configured": bool(text((channel or {}).get("welcome_message"))),
        "entry_tag_configured": bool(text((channel or {}).get("entry_tag_id"))),
        "recent_wecom_external_contact_event_logs": repo.list_recent_events(text(query.scene_value), limit=20) if text(query.scene_value) else [],
        "recent_automation_channel_entry_effect_log": effects,
        "expected_baseline_effects": {"channel_contact": bool(channel and channel_enabled(channel)), "welcome_message": bool(text((channel or {}).get("welcome_message"))), "entry_tag": bool(text((channel or {}).get("entry_tag_id")))},
        "real_wecom_adapter_enabled": adapter["real_wecom_adapter_enabled"],
        "real_wecom_adapter_reason": adapter["real_wecom_adapter_reason"],
        "can_send_welcome": adapter["can_send_welcome"],
        "can_mark_tag": adapter["can_mark_tag"],
        "can_create_contact_way": adapter["can_create_contact_way"],
        "missing_config": adapter["missing_config"],
        "runtime_route_map": runtime_route_map_payload(),
        "callback_route_owner": "aicrm_next.channel_entry",
        "web_release_sha": text(os.getenv("RELEASE_SHA") or os.getenv("GIT_SHA")) or "unknown",
        "worker_release_sha": text(os.getenv("WORKER_RELEASE_SHA")) or "unknown",
    }


def dry_run_channel_entry(command: ProcessChannelEntryCommand) -> dict[str, Any]:
    command.dry_run = True
    result = process_channel_entry(command)
    result["dry_run"] = True
    result["would_actions"] = result.get("baseline_effects", {})
    baseline = result.get("baseline_effects") or {}
    result["would_send_welcome"] = bool((baseline.get("welcome_message") or {}).get("request_payload"))
    result["would_apply_tag"] = bool((baseline.get("entry_tag") or {}).get("request_payload"))
    return result


def repair_channel_entry(command: RepairChannelEntryCommand) -> dict[str, Any]:
    event = repo.get_external_contact_event_log(int(command.event_log_id or 0)) if int(command.event_log_id or 0) > 0 else None
    corp_id = text(command.corp_id) or callback_config().get("corp_id", "")
    payload = repo.decode_payload_json((event or {}).get("payload_json")) if event else {"State": text(command.scene_value), "ToUserName": corp_id}
    if corp_id and not extract_corp_id(payload):
        payload["ToUserName"] = corp_id
    external = text((event or {}).get("external_userid")) or text(command.external_userid)
    owner = text((event or {}).get("user_id"))
    result = process_channel_entry(
        ProcessChannelEntryCommand(
            external_contact_id=external,
            payload_json=payload,
            follow_user_userid=owner,
            event_action="repair_channel_entry",
            send_welcome_message=bool(extract_welcome_code(payload)),
            event_log_id=int(command.event_log_id or 0) or None,
        )
    )
    if not extract_welcome_code(payload):
        result["welcome_repair"] = {"attempted": False, "reason": "welcome_code_unavailable_or_expired"}
    return result


def _generated_scene_value() -> str:
    from datetime import datetime

    return f"aqr_{datetime.now().strftime('%y%m%d')}_{secrets.token_hex(2)}"


def generate_channel_qrcode(command: GenerateChannelQrCodeCommand) -> dict[str, Any]:
    channel = repo.get_channel_by_id(int(command.channel_id))
    if not channel:
        raise LookupError("channel_not_found")
    if text(channel.get("carrier_type")) == "link" or text(channel.get("channel_type")) == "wecom_customer_acquisition":
        raise ValueError("link_channel_does_not_support_qrcode_generate")
    owner_staff_id = text(command.owner_staff_id) or text(channel.get("owner_staff_id"))
    payload_user_ids: list[str] = []
    if text(channel.get("assignment_mode")) == "multi_staff":
        payload_user_ids = [text(item.get("staff_id")) for item in repo.list_channel_assignees(int(command.channel_id), active_only=True) if text(item.get("staff_id"))]
    if not payload_user_ids and owner_staff_id:
        payload_user_ids = [owner_staff_id]
    if not payload_user_ids:
        raise ValueError("owner_staff_id_required")
    scene_value = text(command.scene_value) or _generated_scene_value()
    previous_scene = text(channel.get("scene_value"))
    corp_id = callback_config().get("corp_id", "")
    payload = {
        "type": 2 if len(payload_user_ids) > 1 else 1,
        "scene": 2,
        "style": 1,
        "skip_verify": bool(command.skip_verify if command.skip_verify is not None else channel.get("auto_accept_friend")),
        "state": scene_value,
        "user": payload_user_ids,
    }
    try:
        wecom_result = get_wecom_adapter().create_contact_way(payload)
    except Exception as exc:
        reason, failure = _adapter_failure(exc)
        repo.upsert_channel_entry_effect_log(
            effect_type="qrcode_generate",
            idempotency_key=f"{corp_id}:{command.channel_id}:{scene_value}:qrcode_generate",
            status="failed",
            channel_id=int(command.channel_id),
            scene_value=scene_value,
            external_contact_id="",
            owner_staff_id=owner_staff_id,
            reason=reason,
            request_json=payload,
            response_json=failure,
        )
        return {
            "ok": False,
            "reason": reason,
            "channel_id": int(command.channel_id),
            "scene_value": scene_value,
            "request_payload": payload,
            **failure,
            "source": "aicrm_next.channel_entry",
            "route_owner": "ai_crm_next",
        }
    config_id = text((wecom_result or {}).get("config_id"))
    qr_url = text((wecom_result or {}).get("qr_code") or (wecom_result or {}).get("qr_url"))
    if not config_id or not qr_url:
        response = {"reason": "wecom_api_error", "wecom_result": dict(wecom_result or {})}
        repo.upsert_channel_entry_effect_log(
            effect_type="qrcode_generate",
            idempotency_key=f"{corp_id}:{command.channel_id}:{scene_value}:qrcode_generate",
            status="failed",
            channel_id=int(command.channel_id),
            scene_value=scene_value,
            external_contact_id="",
            owner_staff_id=owner_staff_id,
            reason="wecom_api_error",
            request_json=payload,
            response_json=response,
        )
        return {
            "ok": False,
            "reason": "wecom_api_error",
            "channel_id": int(command.channel_id),
            "scene_value": scene_value,
            "wecom_result": response["wecom_result"],
            "source": "aicrm_next.channel_entry",
            "route_owner": "ai_crm_next",
        }
    asset = repo.insert_qrcode_asset(
        channel_id=int(command.channel_id),
        scene_value=scene_value,
        config_id=config_id,
        qr_url=qr_url,
        corp_id=corp_id,
        provider_payload_json=dict(wecom_result or {}),
        status="active",
        generation_source="next_create_contact_way",
        created_by=owner_staff_id,
    )
    if asset.get("conflict"):
        repo.upsert_channel_entry_effect_log(
            effect_type="qrcode_generate",
            idempotency_key=f"{corp_id}:{command.channel_id}:{scene_value}:qrcode_generate_conflict",
            status="failed",
            channel_id=int(command.channel_id),
            scene_value=scene_value,
            external_contact_id="",
            owner_staff_id=owner_staff_id,
            reason=text(asset.get("reason")) or "qrcode_asset_scene_channel_conflict",
            request_json=payload,
            response_json=asset,
        )
        return {
            "ok": False,
            "reason": text(asset.get("reason")) or "qrcode_asset_scene_channel_conflict",
            "channel_id": int(command.channel_id),
            "scene_value": scene_value,
            "source": "aicrm_next.channel_entry",
            "route_owner": "ai_crm_next",
        }
    if previous_scene and previous_scene != scene_value:
        repo.upsert_channel_scene_alias(
            channel_id=int(command.channel_id),
            scene_value=previous_scene,
            corp_id=corp_id,
            qr_url=text(channel.get("qr_url")),
            carrier_type=text(channel.get("carrier_type")) or "qrcode",
            status="retired",
            source="next_create_contact_way_previous_scene",
        )
    repo.retire_active_qrcode_assets(int(command.channel_id), except_asset_id=int(asset.get("id") or 0) or None)
    updated = repo.update_channel_qrcode(channel_id=int(command.channel_id), scene_value=scene_value, qr_url=qr_url, config_id=config_id)
    alias = repo.upsert_channel_scene_alias(
        channel_id=int(command.channel_id),
        scene_value=scene_value,
        corp_id=corp_id,
        config_id=config_id,
        qr_url=qr_url,
        carrier_type="qrcode",
        status="active",
        source="next_create_contact_way",
    )
    repo.upsert_channel_entry_effect_log(
        effect_type="qrcode_generate",
        idempotency_key=f"{corp_id}:{command.channel_id}:{scene_value}:qrcode_generate",
        status="success",
        channel_id=int(command.channel_id),
        scene_value=scene_value,
        external_contact_id="",
        owner_staff_id=owner_staff_id,
        reason="created",
        request_json=payload,
        response_json=dict(wecom_result or {}),
    )
    return {
        "ok": True,
        "channel_id": int(command.channel_id),
        "scene_value": scene_value,
        "config_id": config_id,
        "qr_url": qr_url,
        "alias_id": int(alias.get("id") or 0),
        "qrcode_asset_id": int(asset.get("id") or 0),
        "provider_payload_user_count": len(payload_user_ids),
        "channel": channel_payload(updated or {**channel, "scene_value": scene_value, "qr_url": qr_url, "qr_ticket": config_id}),
        "source": "aicrm_next.channel_entry",
        "route_owner": "ai_crm_next",
        "wecom_result": dict(wecom_result or {}),
    }


def runtime_route_map_payload() -> dict[str, Any]:
    return {
        "route_owner": "ai_crm_next",
        "wecom_callback_routes": {
            "/wecom/external-contact/callback": "aicrm_next.channel_entry.api",
            "/api/wecom/events": "aicrm_next.channel_entry.api",
            "/api/admin/channels/{channel_id}/qrcode/generate": "aicrm_next.channel_entry.api",
            "/api/admin/channels/{channel_id}/qrcode/status": "aicrm_next.automation_engine.channels_api",
            "/api/admin/channels/{channel_id}/qrcode/download": "aicrm_next.automation_engine.channels_api",
        },
        "next_live_callback_gateway_enabled": True,
        "callback_async_enabled": "next_task_queue",
        "legacy_callback_fallback_enabled": False,
        "web_release_sha": text(os.getenv("RELEASE_SHA") or os.getenv("GIT_SHA")) or "unknown",
        "worker_release_sha": text(os.getenv("WORKER_RELEASE_SHA")) or "unknown",
    }
