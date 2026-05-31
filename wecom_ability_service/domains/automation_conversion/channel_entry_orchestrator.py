from __future__ import annotations

import json
import os
from typing import Any

from ...db import get_db
from ...infra.task_queue import get_queue_depth, is_rq_active
from ...wecom_client import WeComClientError
from ..callbacks.service import get_external_contact_event_log
from ..tags import repo as tags_repo
from . import repo, service as service_seams
from .admission_service import admit_channel_contact_to_program, record_standalone_channel_attempt
from .channel_binding_service import ensure_legacy_program_channel_bindings, list_active_bindings_for_channel, upsert_channel_contact
from .service import DEFAULT_OWNER_STAFF_ID, SOURCE_TYPE_QRCODE, _json_loads, _normalized_text


ACTIVE_CHANNEL_STATUSES = {"active", "configured"}


def _as_dict(value: Any) -> dict[str, Any]:
    parsed = _json_loads(value, default={})
    return parsed if isinstance(parsed, dict) else {}


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value, ensure_ascii=False, default=str)
        return value
    except TypeError:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _extract_scene(payload_json: dict[str, Any]) -> str:
    payload = _as_dict(payload_json)
    for key in ("state", "State", "scene", "scene_value", "channel_code"):
        value = _normalized_text(payload.get(key))
        if value:
            return value
    return ""


def _extract_welcome_code(payload_json: dict[str, Any]) -> str:
    payload = _as_dict(payload_json)
    for key in ("welcome_code", "WelcomeCode", "welcomeCode"):
        value = _normalized_text(payload.get(key))
        if value:
            return value
    return ""


def _extract_corp_id(payload_json: dict[str, Any]) -> str:
    payload = _as_dict(payload_json)
    for key in ("corp_id", "CorpId", "ToUserName"):
        value = _normalized_text(payload.get(key))
        if value:
            return value
    return ""


def _scene_match(match_type: str, scene: str, alias: dict[str, Any] | None = None) -> dict[str, Any]:
    alias = dict(alias or {})
    return {
        "match_type": match_type,
        "matched_scene": _normalized_text(scene),
        "alias_id": int(alias.get("scene_alias_id") or alias.get("id") or 0) or None,
        "alias_status": _normalized_text(alias.get("scene_alias_status") or alias.get("status")),
        "alias_source": _normalized_text(alias.get("scene_alias_source") or alias.get("source")),
    }


def resolve_channel_for_scene(
    *,
    scene_value: str,
    corp_id: str = "",
    persist_alias: bool = True,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    scene = _normalized_text(scene_value)
    if not scene:
        return None, _scene_match("missing_scene", "")
    channel = repo.find_channel_by_scene_value(scene)
    if channel:
        if persist_alias:
            repo.upsert_channel_scene_alias(
                channel_id=int(channel["id"]),
                scene_value=scene,
                corp_id=_normalized_text(corp_id),
                qr_url=_normalized_text(channel.get("qr_url")),
                carrier_type=_normalized_text(channel.get("carrier_type")) or "qrcode",
                status="active",
                source="current_scene",
            )
        return channel, _scene_match("current_scene", scene)
    channel = repo.find_channel_by_scene_alias(_normalized_text(corp_id), scene)
    if channel:
        return channel, _scene_match("scene_alias", scene, channel)
    channel = repo.find_channel_by_historical_scene_value(scene)
    if channel:
        alias = repo.backfill_scene_alias_from_historical_vote(scene, int(channel["id"])) if persist_alias else {}
        return channel, _scene_match("historical_vote", scene, alias)
    return None, _scene_match("not_found", scene)


def _log_effect(
    *,
    effect_type: str,
    idempotency_key: str,
    status: str,
    event_log_id: int | None = None,
    channel_id: int | None = None,
    scene_value: str = "",
    external_contact_id: str = "",
    owner_staff_id: str = "",
    reason: str = "",
    request_json: dict[str, Any] | None = None,
    response_json: dict[str, Any] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    if dry_run:
        return {
            "effect_type": effect_type,
            "idempotency_key": idempotency_key,
            "status": "skipped",
            "reason": "dry_run",
        }
    return repo.upsert_channel_entry_effect_log(
        effect_type=effect_type,
        idempotency_key=idempotency_key,
        status=status,
        event_log_id=event_log_id,
        channel_id=channel_id,
        scene_value=scene_value,
        external_contact_id=external_contact_id,
        owner_staff_id=owner_staff_id,
        reason=reason,
        request_json=_json_safe(request_json or {}),
        response_json=_json_safe(response_json or {}),
    )


def _channel_with_historical_entry_tag(
    channel: dict[str, Any],
    *,
    channel_scene: str = "",
    owner_staff_id: str = "",
) -> dict[str, Any]:
    if _normalized_text(channel.get("entry_tag_id")):
        return channel
    historical_tag = repo.find_entry_tag_by_historical_scene_value(
        channel_scene,
        owner_staff_id=_normalized_text(owner_staff_id),
    )
    if not _normalized_text(historical_tag.get("entry_tag_id")):
        return channel
    return {
        **channel,
        "entry_tag_id": _normalized_text(historical_tag.get("entry_tag_id")),
        "entry_tag_name": _normalized_text(historical_tag.get("entry_tag_name")),
        "entry_tag_group_name": _normalized_text(historical_tag.get("entry_tag_group_name")),
    }


def _send_channel_welcome_message_for_contact(
    *,
    channel: dict[str, Any],
    payload_json: dict[str, Any] | None = None,
    send_welcome_message: bool = False,
    event_log_id: int | None = None,
    scene_value: str = "",
    external_contact_id: str = "",
    owner_staff_id: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    welcome_message = _normalized_text(channel.get("welcome_message"))
    welcome_code = _extract_welcome_code(payload_json or {})
    channel_id = int(channel.get("id") or 0)
    key = f"channel:{channel_id}:welcome:{welcome_code or 'missing'}"
    if not send_welcome_message:
        result = {"attempted": False, "sent": False, "reason": "disabled"}
        _log_effect(
            effect_type="welcome_message",
            idempotency_key=key,
            status="skipped",
            event_log_id=event_log_id,
            channel_id=channel_id,
            scene_value=scene_value,
            external_contact_id=external_contact_id,
            owner_staff_id=owner_staff_id,
            reason="send_welcome_message_disabled",
            response_json=result,
            dry_run=dry_run,
        )
        return result
    if not welcome_message:
        result = {"attempted": False, "sent": False, "reason": "not_configured"}
        _log_effect(
            effect_type="welcome_message",
            idempotency_key=key,
            status="skipped",
            event_log_id=event_log_id,
            channel_id=channel_id,
            scene_value=scene_value,
            external_contact_id=external_contact_id,
            owner_staff_id=owner_staff_id,
            reason="not_configured",
            response_json=result,
            dry_run=dry_run,
        )
        return result
    if not welcome_code:
        result = {"attempted": True, "sent": False, "error": "missing_welcome_code"}
        _log_effect(
            effect_type="welcome_message",
            idempotency_key=key,
            status="failed",
            event_log_id=event_log_id,
            channel_id=channel_id,
            scene_value=scene_value,
            external_contact_id=external_contact_id,
            owner_staff_id=owner_staff_id,
            reason="missing_welcome_code",
            response_json=result,
            dry_run=dry_run,
        )
        return result
    existing = repo.get_channel_entry_effect_log("welcome_message", key)
    if existing and _normalized_text(existing.get("status")) == "success":
        return {"attempted": False, "sent": False, "reason": "idempotent_success_exists", "welcome_code": welcome_code}
    request_payload = {"welcome_code": welcome_code, "text": {"content": welcome_message}}
    if dry_run:
        return {"attempted": False, "sent": False, "reason": "dry_run", "request_payload": request_payload}
    try:
        result = service_seams.get_contact_runtime_client().send_welcome_msg(request_payload)
    except (WeComClientError, AttributeError, ValueError) as exc:
        payload = {"attempted": True, "sent": False, "error": str(exc), "welcome_code": welcome_code}
        _log_effect(
            effect_type="welcome_message",
            idempotency_key=key,
            status="failed",
            event_log_id=event_log_id,
            channel_id=channel_id,
            scene_value=scene_value,
            external_contact_id=external_contact_id,
            owner_staff_id=owner_staff_id,
            reason=str(exc),
            request_json=request_payload,
            response_json=payload,
        )
        return payload
    payload = {"attempted": True, "sent": True, "welcome_code": welcome_code, "wecom_result": dict(result or {})}
    _log_effect(
        effect_type="welcome_message",
        idempotency_key=key,
        status="success",
        event_log_id=event_log_id,
        channel_id=channel_id,
        scene_value=scene_value,
        external_contact_id=external_contact_id,
        owner_staff_id=owner_staff_id,
        reason="sent",
        request_json=request_payload,
        response_json=payload,
    )
    return payload


def _apply_channel_entry_tag_for_contact(
    *,
    external_contact_id: str,
    owner_staff_id: str,
    channel: dict[str, Any],
    event_log_id: int | None = None,
    scene_value: str = "",
    dry_run: bool = False,
) -> dict[str, Any]:
    entry_tag_id = _normalized_text(channel.get("entry_tag_id"))
    entry_tag_name = _normalized_text(channel.get("entry_tag_name"))
    entry_tag_group_name = _normalized_text(channel.get("entry_tag_group_name"))
    channel_id = int(channel.get("id") or 0)
    key = f"channel:{channel_id}:tag:{_normalized_text(external_contact_id)}:{_normalized_text(owner_staff_id)}:{entry_tag_id or 'missing'}"
    if not entry_tag_id:
        result = {"attempted": False, "applied": False, "reason": "not_configured"}
        _log_effect(
            effect_type="entry_tag",
            idempotency_key=key,
            status="skipped",
            event_log_id=event_log_id,
            channel_id=channel_id,
            scene_value=scene_value,
            external_contact_id=external_contact_id,
            owner_staff_id=owner_staff_id,
            reason="not_configured",
            response_json=result,
            dry_run=dry_run,
        )
        return result
    if not _normalized_text(external_contact_id):
        return {"attempted": False, "applied": False, "reason": "missing_external_contact_id"}
    if not _normalized_text(owner_staff_id):
        return {"attempted": False, "applied": False, "reason": "missing_owner_staff_id"}
    existing = repo.get_channel_entry_effect_log("entry_tag", key)
    if existing and _normalized_text(existing.get("status")) == "success":
        return {
            "attempted": False,
            "applied": False,
            "reason": "idempotent_success_exists",
            "entry_tag_id": entry_tag_id,
            "entry_tag_name": entry_tag_name,
            "entry_tag_group_name": entry_tag_group_name,
        }
    request_payload = {
        "external_userid": _normalized_text(external_contact_id),
        "follow_user_userid": _normalized_text(owner_staff_id),
        "add_tags": [entry_tag_id],
        "remove_tags": [],
    }
    if dry_run:
        return {
            "attempted": False,
            "applied": False,
            "reason": "dry_run",
            "entry_tag_id": entry_tag_id,
            "entry_tag_name": entry_tag_name,
            "entry_tag_group_name": entry_tag_group_name,
            "request_payload": request_payload,
        }
    try:
        result = service_seams.get_app_runtime_client().mark_external_contact_tags(**request_payload)
        tags_repo.save_tag_snapshot(
            _normalized_text(owner_staff_id),
            _normalized_text(external_contact_id),
            [entry_tag_id],
            {entry_tag_id: entry_tag_name},
        )
    except (WeComClientError, AttributeError, ValueError) as exc:
        payload = {
            "attempted": True,
            "applied": False,
            "error": str(exc),
            "entry_tag_id": entry_tag_id,
            "entry_tag_name": entry_tag_name,
            "entry_tag_group_name": entry_tag_group_name,
        }
        _log_effect(
            effect_type="entry_tag",
            idempotency_key=key,
            status="failed",
            event_log_id=event_log_id,
            channel_id=channel_id,
            scene_value=scene_value,
            external_contact_id=external_contact_id,
            owner_staff_id=owner_staff_id,
            reason=str(exc),
            request_json=request_payload,
            response_json=payload,
        )
        return payload
    payload = {
        "attempted": True,
        "applied": True,
        "entry_tag_id": entry_tag_id,
        "entry_tag_name": entry_tag_name,
        "entry_tag_group_name": entry_tag_group_name,
        "wecom_result": dict(result or {}),
    }
    _log_effect(
        effect_type="entry_tag",
        idempotency_key=key,
        status="success",
        event_log_id=event_log_id,
        channel_id=channel_id,
        scene_value=scene_value,
        external_contact_id=external_contact_id,
        owner_staff_id=owner_staff_id,
        reason="applied",
        request_json=request_payload,
        response_json=payload,
    )
    return payload


def _program_admission_status(admission_results: list[dict[str, Any]]) -> tuple[bool, str]:
    if not admission_results:
        return False, "no_active_binding"
    if any(item.get("legacy_member") or item.get("program_member") for item in admission_results):
        return True, "program_member_written"
    reasons = [_normalized_text(item.get("reason")) for item in admission_results]
    return False, ",".join(reason for reason in reasons if reason) or "program_admission_rejected"


def _channel_payload(channel: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(channel.get("id") or 0),
        "channel_code": _normalized_text(channel.get("channel_code")),
        "channel_name": _normalized_text(channel.get("channel_name")),
        "scene_value": _normalized_text(channel.get("scene_value")),
        "status": _normalized_text(channel.get("status")),
        "owner_staff_id": _normalized_text(channel.get("owner_staff_id")),
    }


def handle_channel_entry_from_callback(
    *,
    external_contact_id: str,
    phone: str = "",
    payload_json: dict[str, Any] | None = None,
    operator_id: str = "",
    follow_user_userid: str = "",
    source_type: str = SOURCE_TYPE_QRCODE,
    event_action: str = "qrcode_enter",
    send_welcome_message: bool = False,
    event_log_id: int | None = None,
    dry_run: bool = False,
    channel: dict[str, Any] | None = None,
    initial_audience_code: str = "",
) -> dict[str, Any]:
    del phone, initial_audience_code
    payload = _as_dict(payload_json or {})
    scene = _extract_scene(payload)
    corp_id = _extract_corp_id(payload)
    scene_match = _scene_match("provided_channel", scene) if channel else {}
    if not channel:
        channel, scene_match = resolve_channel_for_scene(scene_value=scene, corp_id=corp_id, persist_alias=not dry_run)
    if not scene:
        return {"handled": False, "mode": "channel_not_found", "reason": "missing_channel_scene", "scene_match": scene_match}
    if not channel:
        return {"handled": False, "mode": "channel_not_found", "reason": "channel_not_found", "scene_match": scene_match}

    status = _normalized_text(channel.get("status"))
    owner_staff_id = _normalized_text(follow_user_userid) or _normalized_text(channel.get("owner_staff_id")) or DEFAULT_OWNER_STAFF_ID
    channel = _channel_with_historical_entry_tag(channel, channel_scene=scene, owner_staff_id=owner_staff_id)
    if status not in ACTIVE_CHANNEL_STATUSES:
        return {
            "handled": False,
            "mode": "channel_disabled",
            "reason": "channel_disabled",
            "channel": _channel_payload(channel),
            "scene_match": scene_match,
            "baseline_effects": {
                "channel_contact": {"attempted": False, "reason": "channel_disabled"},
                "welcome_message": {"attempted": False, "sent": False, "reason": "channel_disabled"},
                "entry_tag": {"attempted": False, "applied": False, "reason": "channel_disabled"},
            },
            "admission_results": [],
            "program_member_written": False,
        }

    trigger_time = service_seams._iso_now()
    master_customer_id = repo.lookup_person_id_by_external_contact_id(external_contact_id)
    channel_contact = {}
    if dry_run:
        channel_contact = {"planned": True, "channel_id": int(channel["id"]), "external_contact_id": _normalized_text(external_contact_id)}
    else:
        channel_contact = upsert_channel_contact(
            channel_id=int(channel["id"]),
            external_contact_id=external_contact_id,
            master_customer_id=master_customer_id,
            owner_staff_id=owner_staff_id,
            source_payload=payload,
            entered_at=trigger_time,
        )
        _log_effect(
            effect_type="channel_contact",
            idempotency_key=f"channel:{int(channel['id'])}:contact:{_normalized_text(external_contact_id)}",
            status="success",
            event_log_id=event_log_id,
            channel_id=int(channel["id"]),
            scene_value=scene,
            external_contact_id=external_contact_id,
            owner_staff_id=owner_staff_id,
            reason="upserted",
            request_json={"source_payload": payload},
            response_json=channel_contact,
        )

    welcome_result = _send_channel_welcome_message_for_contact(
        channel=channel,
        payload_json=payload,
        send_welcome_message=send_welcome_message,
        event_log_id=event_log_id,
        scene_value=scene,
        external_contact_id=external_contact_id,
        owner_staff_id=owner_staff_id,
        dry_run=dry_run,
    )
    entry_tag_result = _apply_channel_entry_tag_for_contact(
        external_contact_id=external_contact_id,
        owner_staff_id=owner_staff_id,
        channel=channel,
        event_log_id=event_log_id,
        scene_value=scene,
        dry_run=dry_run,
    )

    active_bindings = list_active_bindings_for_channel(int(channel["id"]))
    legacy_binding_report: dict[str, Any] = {}
    if not active_bindings and not dry_run:
        legacy_binding_report = ensure_legacy_program_channel_bindings(channel_id=int(channel["id"]))
        active_bindings = list_active_bindings_for_channel(int(channel["id"]))

    admission_results: list[dict[str, Any]] = []
    if active_bindings and not dry_run:
        trigger_payload = {
            **payload,
            "source_type": source_type,
            "event_log_id": str(event_log_id or ""),
            "master_customer_id": master_customer_id,
        }
        for binding in active_bindings:
            admission_results.append(
                admit_channel_contact_to_program(
                    int(binding["program_id"]),
                    int(channel["id"]),
                    int(binding["id"]),
                    external_contact_id,
                    follow_user_userid=owner_staff_id,
                    trigger_payload=trigger_payload,
                    trigger_time=trigger_time,
                    trigger_type=event_action,
                )
            )
    elif active_bindings and dry_run:
        admission_results = [
            {
                "admission_status": "planned",
                "program_id": int(binding.get("program_id") or 0),
                "binding_id": int(binding.get("id") or 0),
            }
            for binding in active_bindings
        ]
    elif not dry_run:
        admission_attempt = record_standalone_channel_attempt(
            channel_id=int(channel["id"]),
            external_contact_id=external_contact_id,
            master_customer_id=master_customer_id,
            trigger_type=event_action,
            trigger_payload={**payload, "source_type": source_type, "event_log_id": str(event_log_id or "")},
        )
        admission_results = [{"admission_status": "standalone_channel", "reason": "channel_without_active_binding", "admission_attempt": admission_attempt}]

    program_member_written, admission_reason = _program_admission_status(admission_results)
    _log_effect(
        effect_type="program_admission",
        idempotency_key=f"channel:{int(channel['id'])}:admission:{_normalized_text(external_contact_id)}:{event_log_id or scene}",
        status="success" if program_member_written else ("skipped" if not active_bindings else "attempted"),
        event_log_id=event_log_id,
        channel_id=int(channel["id"]),
        scene_value=scene,
        external_contact_id=external_contact_id,
        owner_staff_id=owner_staff_id,
        reason=admission_reason,
        request_json={"active_binding_count": len(active_bindings), "event_action": event_action},
        response_json={"admission_results": admission_results},
        dry_run=dry_run,
    )
    mode = "program_admission" if program_member_written else ("standalone_channel" if not active_bindings else "channel_baseline_only")
    projected_member = next((item.get("legacy_member") for item in admission_results if item.get("legacy_member")), None)
    result = {
        "handled": True,
        "mode": mode,
        "reason": admission_reason if mode != "program_admission" else "program_admission_processed",
        "member": projected_member or {},
        "channel": _channel_payload(channel),
        "channel_contact": channel_contact,
        "baseline_effects": {
            "channel_contact": channel_contact,
            "welcome_message": welcome_result,
            "entry_tag": entry_tag_result,
        },
        "welcome_message": welcome_result,
        "entry_tag": entry_tag_result,
        "admission_results": admission_results,
        "program_member_written": bool(program_member_written),
        "scene_match": scene_match,
        "legacy_binding_report": legacy_binding_report,
    }
    return result


def build_channel_runtime_diagnosis(*, scene_value: str = "", channel_id: int | None = None) -> dict[str, Any]:
    channel = repo.get_channel_by_id(int(channel_id or 0)) if int(channel_id or 0) > 0 else None
    scene_match: dict[str, Any] = {}
    if not channel and _normalized_text(scene_value):
        channel, scene_match = resolve_channel_for_scene(scene_value=scene_value, persist_alias=False)
    elif channel:
        scene_match = _scene_match("channel_id", _normalized_text(channel.get("scene_value")))
    aliases = repo.get_channel_scene_aliases(int(channel.get("id") or 0)) if channel else []
    bindings = list_active_bindings_for_channel(int(channel.get("id") or 0)) if channel else []
    program_rows: list[dict[str, Any]] = []
    for binding in bindings:
        row = get_db().execute("SELECT id, program_code, program_name, status FROM automation_program WHERE id = ?", (int(binding.get("program_id") or 0),)).fetchone()
        if row:
            program_rows.append(dict(row))
    recent_events = []
    if _normalized_text(scene_value):
        recent_events = [
            dict(row)
            for row in get_db().execute(
                """
                SELECT id, change_type, external_userid, user_id, process_status, created_at
                FROM wecom_external_contact_event_logs
                WHERE COALESCE(NULLIF(payload_json->>'State', ''), NULLIF(payload_json->>'state', '')) = ?
                ORDER BY created_at DESC, id DESC
                LIMIT 20
                """,
                (_normalized_text(scene_value),),
            ).fetchall()
        ]
    effect_logs = repo.list_channel_entry_effect_logs(
        channel_id=int(channel.get("id") or 0) if channel else None,
        scene_value=_normalized_text(scene_value),
        limit=20,
    )
    return {
        "ok": True,
        "scene_resolve": scene_match,
        "channel": _channel_payload(channel or {}) if channel else {},
        "aliases": aliases,
        "channel_status": _normalized_text((channel or {}).get("status")),
        "welcome_configured": bool(_normalized_text((channel or {}).get("welcome_message"))),
        "entry_tag_configured": bool(_normalized_text((channel or {}).get("entry_tag_id"))),
        "active_bindings": bindings,
        "bound_programs": program_rows,
        "expected_baseline_effects": {
            "channel_contact": bool(channel and _normalized_text((channel or {}).get("status")) in ACTIVE_CHANNEL_STATUSES),
            "welcome_message": bool(channel and _normalized_text((channel or {}).get("welcome_message"))),
            "entry_tag": bool(channel and _normalized_text((channel or {}).get("entry_tag_id"))),
        },
        "expected_program_admission_result": "program_archived" if any(_normalized_text(row.get("status")) == "archived" for row in program_rows) else ("active_binding" if bindings else "standalone_channel"),
        "recent_wecom_external_contact_event_logs": recent_events,
        "recent_automation_channel_entry_effect_log": effect_logs,
        "runtime": runtime_route_map_payload(),
    }


def repair_channel_entry(*, event_log_id: int | None = None, external_userid: str = "", scene_value: str = "") -> dict[str, Any]:
    payload: dict[str, Any] = {"state": _normalized_text(scene_value)}
    owner = ""
    external = _normalized_text(external_userid)
    if int(event_log_id or 0) > 0:
        event = get_external_contact_event_log(int(event_log_id or 0)) or {}
        payload = _as_dict(event.get("payload_json") or {})
        owner = _normalized_text(event.get("user_id"))
        external = _normalized_text(event.get("external_userid")) or external
    if not _extract_welcome_code(payload):
        payload["_repair_welcome_note"] = "welcome_code_unavailable_or_expired"
    result = handle_channel_entry_from_callback(
        external_contact_id=external,
        payload_json=payload,
        operator_id="channel_entry_repair",
        follow_user_userid=owner,
        send_welcome_message=bool(_extract_welcome_code(payload)),
        event_log_id=event_log_id,
    )
    if not _extract_welcome_code(payload):
        result["welcome_repair"] = {"attempted": False, "reason": "welcome_code_unavailable_or_expired"}
    return result


def runtime_route_map_payload() -> dict[str, Any]:
    return {
        "web_release_sha": _normalized_text(os.environ.get("RELEASE_SHA") or os.environ.get("GIT_SHA")) or "unknown",
        "worker_release_sha": _normalized_text(os.environ.get("WORKER_RELEASE_SHA") or os.environ.get("RELEASE_SHA")) or "unknown",
        "route_owner": "legacy_flask",
        "app_name": _normalized_text(os.environ.get("APP_NAME")) or "wecom_ability_service",
        "task_queue_backend": "rq" if is_rq_active() else "thread_pool",
        "task_queue_pending": get_queue_depth(),
        "callback_async_enabled": _normalized_text(os.environ.get("CALLBACK_ASYNC_ENABLED")) or "app_config",
        "redis_url_active": bool(_normalized_text(os.environ.get("REDIS_URL"))),
    }
