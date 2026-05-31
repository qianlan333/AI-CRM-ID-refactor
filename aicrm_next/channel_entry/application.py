from __future__ import annotations

import json
import os
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
from .schemas import (
    DiagnoseChannelRuntimeQuery,
    ProcessChannelEntryCommand,
    ProcessWeComExternalContactEventCommand,
    RepairChannelEntryCommand,
)
from .wecom_adapter import get_wecom_adapter
from .wecom_crypto import build_encrypted_reply, decrypt_message, parse_callback_xml, verify_signature


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
    channel = repo.find_channel_by_scene_value(scene)
    if channel:
        if persist_alias:
            repo.upsert_channel_scene_alias(
                channel_id=int(channel["id"]),
                scene_value=scene,
                corp_id=text(corp_id),
                qr_url=text(channel.get("qr_url")),
                carrier_type=text(channel.get("carrier_type")) or "qrcode",
                status="active",
                source="current_scene",
            )
        return channel, scene_match("current_scene", scene, channel)
    channel = repo.find_channel_by_scene_alias(text(corp_id), scene)
    if channel:
        if persist_alias:
            repo.update_alias_last_seen_at(text(corp_id), scene)
        return channel, scene_match("scene_alias", scene, channel)
    channel = repo.find_channel_by_historical_scene_value(scene)
    if channel:
        alias = repo.backfill_scene_alias_from_historical_vote(scene, int(channel["id"])) if persist_alias else {}
        return channel, scene_match("historical_vote", scene, alias or channel)
    return None, scene_match("not_found", scene)


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
        request_json=request_json or {},
        response_json=response_json or {},
    )


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
            if int(item or 0) > 0:
                attachments.append({"msgtype": msgtype, "material_id": int(item)})
    if len(attachments) > 9:
        return attachments, "attachment_limit_exceeded"
    return attachments, ""


def _send_welcome(command: ProcessChannelEntryCommand, *, channel: dict[str, Any], scene: str) -> dict[str, Any]:
    channel_id = int(channel.get("id") or 0)
    welcome_code = extract_welcome_code(command.payload_json)
    key = f"{extract_corp_id(command.payload_json)}:{command.external_contact_id}:{command.follow_user_userid}:{welcome_code}:welcome"
    if not command.send_welcome_message:
        result = {"attempted": False, "sent": False, "reason": "send_welcome_message_disabled"}
        _log_effect(command, effect_type="welcome_message", idempotency_key=key, status="skipped", channel_id=channel_id, scene_value=scene, reason=result["reason"], response_json=result)
        return result
    if effect_status_for_duplicate(repo.get_channel_entry_effect_log("welcome_message", key)):
        return {"attempted": False, "sent": False, "reason": "idempotent_success_exists", "welcome_code": welcome_code}
    if not welcome_code:
        result = {"attempted": True, "sent": False, "reason": "missing_welcome_code"}
        _log_effect(command, effect_type="welcome_message", idempotency_key=key, status="failed", channel_id=channel_id, scene_value=scene, reason=result["reason"], response_json=result)
        return result
    attachments, attachment_error = _welcome_attachments(channel)
    if attachment_error:
        result = {"attempted": True, "sent": False, "reason": attachment_error, "attachments": attachments}
        _log_effect(command, effect_type="welcome_message", idempotency_key=key, status="failed", channel_id=channel_id, scene_value=scene, reason=attachment_error, response_json=result)
        return result
    text_content = text(channel.get("welcome_message"))
    if not text_content and not attachments:
        result = {"attempted": False, "sent": False, "reason": "not_configured"}
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
        wecom_result = get_wecom_adapter().send_welcome_msg(payload)
    except Exception as exc:
        result = {"attempted": True, "sent": False, "reason": str(exc), "welcome_code": welcome_code}
        _log_effect(command, effect_type="welcome_message", idempotency_key=key, status="failed", channel_id=channel_id, scene_value=scene, reason=str(exc), request_json=payload, response_json=result)
        return result
    result = {"attempted": True, "sent": True, "welcome_code": welcome_code, "wecom_result": dict(wecom_result or {}), "attachments": attachments}
    _log_effect(command, effect_type="welcome_message", idempotency_key=key, status="success", channel_id=channel_id, scene_value=scene, reason="sent", request_json=payload, response_json=result)
    return result


def _apply_tag(command: ProcessChannelEntryCommand, *, channel: dict[str, Any], scene: str) -> dict[str, Any]:
    channel_id = int(channel.get("id") or 0)
    tag_id = text(channel.get("entry_tag_id"))
    key = f"{extract_corp_id(command.payload_json)}:{command.external_contact_id}:{command.follow_user_userid}:{tag_id}:{channel_id}:tag"
    if not tag_id:
        result = {"attempted": False, "applied": False, "reason": "not_configured"}
        _log_effect(command, effect_type="entry_tag", idempotency_key=key, status="skipped", channel_id=channel_id, scene_value=scene, reason=result["reason"], response_json=result)
        return result
    if effect_status_for_duplicate(repo.get_channel_entry_effect_log("entry_tag", key)):
        return {"attempted": False, "applied": False, "reason": "idempotent_success_exists", "entry_tag_id": tag_id}
    payload = {"external_userid": command.external_contact_id, "follow_user_userid": command.follow_user_userid, "add_tags": [tag_id], "remove_tags": []}
    if command.dry_run:
        return {"attempted": False, "applied": False, "reason": "dry_run", "request_payload": payload}
    try:
        wecom_result = get_wecom_adapter().mark_external_contact_tags(**payload)
        repo.save_tag_snapshot(command.follow_user_userid, command.external_contact_id, [tag_id], {tag_id: text(channel.get("entry_tag_name"))})
    except Exception as exc:
        result = {"attempted": True, "applied": False, "reason": str(exc), "entry_tag_id": tag_id}
        _log_effect(command, effect_type="entry_tag", idempotency_key=key, status="failed", channel_id=channel_id, scene_value=scene, reason=str(exc), request_json=payload, response_json=result)
        return result
    result = {"attempted": True, "applied": True, "entry_tag_id": tag_id, "wecom_result": dict(wecom_result or {})}
    _log_effect(command, effect_type="entry_tag", idempotency_key=key, status="success", channel_id=channel_id, scene_value=scene, reason="applied", request_json=payload, response_json=result)
    return result


def _admit(command: ProcessChannelEntryCommand, *, channel: dict[str, Any], scene: str) -> tuple[list[dict[str, Any]], bool, str]:
    channel_id = int(channel["id"])
    bindings = repo.list_active_bindings_for_channel(channel_id)
    if not bindings:
        if not command.dry_run:
            return [{"admission_status": "standalone_channel", "reason": "channel_without_active_binding"}], False, "no_active_binding"
        return [{"admission_status": "planned", "reason": "dry_run_no_active_binding"}], False, "no_active_binding"
    results: list[dict[str, Any]] = []
    member_written = False
    reason = "program_admission_rejected"
    for binding in bindings:
        program_id = int(binding.get("program_id") or 0)
        binding_id = int(binding.get("id") or 0)
        if text(binding.get("program_status")) == "archived":
            attempt = {} if command.dry_run else repo.insert_program_admission_attempt(
                program_id=program_id,
                channel_id=channel_id,
                binding_id=binding_id,
                external_contact_id=command.external_contact_id,
                trigger_type=command.event_action,
                trigger_event_id=str(command.event_log_id or ""),
                trigger_payload_json=command.payload_json,
                admission_status="rejected",
                entry_reason="program_archived",
            )
            results.append({"admission_status": "rejected", "reason": "program_archived", "program_id": program_id, "binding_id": binding_id, "admission_attempt": attempt})
            reason = "program_archived"
            continue
        if command.dry_run:
            results.append({"admission_status": "planned", "program_id": program_id, "binding_id": binding_id})
            reason = "planned"
            continue
        member = repo.upsert_program_member(program_id=program_id, channel_id=channel_id, binding_id=binding_id, external_contact_id=command.external_contact_id, payload=command.payload_json)
        attempt = repo.insert_program_admission_attempt(
            program_id=program_id,
            channel_id=channel_id,
            binding_id=binding_id,
            external_contact_id=command.external_contact_id,
            trigger_type=command.event_action,
            trigger_event_id=str(command.event_log_id or ""),
            trigger_payload_json=command.payload_json,
            admission_status="accepted",
            entry_reason="program_admission",
        )
        results.append({"admission_status": "accepted", "reason": "program_admission", "program_id": program_id, "binding_id": binding_id, "program_member": member, "admission_attempt": attempt})
        member_written = True
        reason = "program_member_written"
    return results, member_written, reason


def process_channel_entry(command: ProcessChannelEntryCommand) -> dict[str, Any]:
    scene = extract_scene(command.payload_json)
    corp_id = extract_corp_id(command.payload_json)
    channel, match = resolve_channel_for_scene(scene_value=scene, corp_id=corp_id, persist_alias=not command.dry_run)
    if not scene:
        return {"handled": False, "mode": "channel_not_found", "reason": "missing_channel_scene", "scene_match": match}
    if not channel:
        _log_effect(command, effect_type="channel_contact", idempotency_key=f"{corp_id}:{command.external_contact_id}:{scene}:not_found", status="failed", channel_id=None, scene_value=scene, reason="channel_not_found")
        return {"handled": False, "mode": "channel_not_found", "reason": "channel_not_found", "scene_match": match}

    command.follow_user_userid = text(command.follow_user_userid) or text(channel.get("owner_staff_id")) or "HuangYouCan"
    channel_id = int(channel["id"])
    if not channel_enabled(channel):
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
            "admission_results": [],
            "program_member_written": False,
            "workflow_triggered": False,
        }

    if command.dry_run:
        channel_contact = {"planned": True, "channel_id": channel_id, "external_contact_id": command.external_contact_id}
    else:
        channel_contact = repo.upsert_channel_contact(channel_id=channel_id, external_contact_id=command.external_contact_id, owner_staff_id=command.follow_user_userid, source_payload=command.payload_json)
        _log_effect(command, effect_type="channel_contact", idempotency_key=f"{corp_id}:{command.external_contact_id}:{command.follow_user_userid}:{channel_id}:contact", status="success", channel_id=channel_id, scene_value=scene, reason="upserted", response_json=channel_contact)

    welcome = _send_welcome(command, channel=channel, scene=scene)
    tag = _apply_tag(command, channel=channel, scene=scene)
    admission_results, member_written, admission_reason = _admit(command, channel=channel, scene=scene)
    _log_effect(command, effect_type="program_admission", idempotency_key=f"{corp_id}:{command.external_contact_id}:{channel_id}:{command.event_log_id or scene}:admission", status="success" if member_written else "attempted", channel_id=channel_id, scene_value=scene, reason=admission_reason, response_json={"admission_results": admission_results})
    mode = "program_admission" if member_written else ("standalone_channel" if admission_reason == "no_active_binding" else "channel_baseline_only")
    return {
        "handled": True,
        "mode": mode,
        "reason": "program_admission_processed" if member_written else admission_reason,
        "scene_match": match,
        "channel": channel_payload(channel),
        "baseline_effects": {"channel_contact": channel_contact, "welcome_message": welcome, "entry_tag": tag},
        "admission_results": admission_results,
        "program_member_written": bool(member_written),
        "workflow_triggered": False,
        "channel_contact": channel_contact,
        "welcome_message": welcome,
        "entry_tag": tag,
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
        if text(event.get("Event")) == "change_external_contact" and text(event.get("ChangeType")) in ENTRY_CHANGE_TYPES:
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
    bindings = repo.list_active_bindings_for_channel(channel_id) if channel_id else []
    effects = repo.list_channel_entry_effect_logs(channel_id=channel_id or None, scene_value=text(query.scene_value), limit=20)
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
        "active_bindings": bindings,
        "bound_program_status": [text(item.get("program_status")) for item in bindings],
        "expected_baseline_effects": {"channel_contact": bool(channel and channel_enabled(channel)), "welcome_message": bool(text((channel or {}).get("welcome_message"))), "entry_tag": bool(text((channel or {}).get("entry_tag_id")))},
        "expected_program_admission_result": "program_archived" if any(text(item.get("program_status")) == "archived" for item in bindings) else ("active_binding" if bindings else "standalone_channel"),
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
    return result


def repair_channel_entry(command: RepairChannelEntryCommand) -> dict[str, Any]:
    event = repo.get_external_contact_event_log(int(command.event_log_id or 0)) if int(command.event_log_id or 0) > 0 else None
    payload = repo.decode_payload_json((event or {}).get("payload_json")) if event else {"State": text(command.scene_value)}
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


def runtime_route_map_payload() -> dict[str, Any]:
    fallback_enabled = text(os.getenv("AICRM_ALLOW_LEGACY_WECOM_CALLBACK_FALLBACK")).lower() in {"1", "true", "yes", "on"}
    return {
        "route_owner": "ai_crm_next",
        "wecom_callback_routes": {
            "/wecom/external-contact/callback": "aicrm_next.channel_entry.api",
            "/api/wecom/events": "aicrm_next.channel_entry.api",
        },
        "next_live_callback_gateway_enabled": True,
        "callback_async_enabled": "next_task_queue",
        "legacy_callback_fallback_enabled": fallback_enabled,
        "web_release_sha": text(os.getenv("RELEASE_SHA") or os.getenv("GIT_SHA")) or "unknown",
        "worker_release_sha": text(os.getenv("WORKER_RELEASE_SHA")) or "unknown",
    }
