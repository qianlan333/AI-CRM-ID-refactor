from __future__ import annotations

from flask import jsonify, request

from ..domains.automation_conversion.channel_entry_orchestrator import (
    build_channel_runtime_diagnosis,
    handle_channel_entry_from_callback,
    repair_channel_entry,
)


def api_admin_channel_runtime_diagnosis():
    return jsonify(
        build_channel_runtime_diagnosis(
            scene_value=str(request.args.get("scene_value") or "").strip(),
        )
    )


def api_admin_channel_runtime_diagnosis_by_channel(channel_id: int):
    return jsonify(build_channel_runtime_diagnosis(channel_id=int(channel_id)))


def api_admin_channel_runtime_diagnosis_dry_run():
    payload = request.get_json(silent=True) or {}
    state = str(payload.get("state") or payload.get("scene_value") or "").strip()
    welcome_code_present = bool(payload.get("welcome_code_present"))
    callback_payload = {"State": state}
    if welcome_code_present:
        callback_payload["WelcomeCode"] = str(payload.get("welcome_code") or "dry-run-welcome-code")
    result = handle_channel_entry_from_callback(
        external_contact_id=str(payload.get("external_userid") or payload.get("external_contact_id") or "dry_run_external_userid").strip(),
        payload_json=callback_payload,
        operator_id="runtime_diagnosis_dry_run",
        follow_user_userid=str(payload.get("follow_user_userid") or "").strip(),
        event_action=str(payload.get("change_type") or "add_external_contact").strip(),
        send_welcome_message=welcome_code_present,
        dry_run=True,
    )
    return jsonify({"ok": True, "planned_actions": result})


def api_admin_channel_repair_entry():
    payload = request.get_json(silent=True) or {}
    result = repair_channel_entry(
        event_log_id=int(payload.get("event_log_id") or 0) or None,
        external_userid=str(payload.get("external_userid") or payload.get("external_contact_id") or "").strip(),
        scene_value=str(payload.get("scene_value") or payload.get("state") or "").strip(),
    )
    return jsonify({"ok": bool(result.get("handled")), "result": result})
