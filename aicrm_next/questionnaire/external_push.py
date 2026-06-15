from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta
from typing import Any

from aicrm_next.platform_foundation.command_bus import CommandContext
from aicrm_next.platform_foundation.external_effects import ExternalEffectService, WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH
from aicrm_next.platform_foundation.external_effects.models import public_datetime, utcnow
from aicrm_next.shared.runtime_settings import runtime_setting

STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"
GLOBAL_ENABLED_KEY = "QUESTIONNAIRE_EXTERNAL_PUSH_GLOBAL_ENABLED"
TIMEOUT_SECONDS_KEY = "QUESTIONNAIRE_EXTERNAL_PUSH_TIMEOUT_SECONDS"
GLOBAL_DISABLED_REASON = "skipped by global external push switch"
QUESTIONNAIRE_EXTERNAL_PUSH_MODE_KEY = "AICRM_QUESTIONNAIRE_EXTERNAL_PUSH_MODE"
QUESTIONNAIRE_EXTERNAL_PUSH_MODES = {"legacy", "shadow", "queue"}


def deliver_questionnaire_external_push(
    *,
    repo: Any,
    questionnaire: dict[str, Any],
    submission: dict[str, Any],
    computed_result: dict[str, Any],
) -> dict[str, Any]:
    config = dict(questionnaire.get("external_push_config") or {})
    if not _bool(config.get("enabled") or questionnaire.get("external_push_enabled")):
        return {"enabled": False, "attempted": False, "ok": True, "reason": "external_push_disabled"}

    target_url = _text(config.get("webhook_url") or questionnaire.get("external_push_url"))
    payload = build_questionnaire_external_push_payload(
        questionnaire=questionnaire,
        submission=submission,
        computed_result=computed_result,
    )
    log = _log(
        repo=repo,
        questionnaire=questionnaire,
        submission=submission,
        target_url=target_url,
        payload=payload,
        response_status_code=None,
        response_body="",
        status=STATUS_SKIPPED,
        failure_reason="legacy_outbound_disabled_external_effect_required",
    )
    return {
        "enabled": True,
        "attempted": False,
        "ok": False,
        "reason": "legacy_outbound_disabled",
        "status": STATUS_SKIPPED,
        "log": log,
        "legacy_outbound_disabled": True,
        "external_effect_required": True,
        "migration_target": "external_effect_queue",
        "push_center_url": "/admin/push-center",
        "real_external_call_executed": False,
    }


def questionnaire_external_push_mode() -> str:
    # P0-1 收口后问卷外推只允许进入 External Effect Queue。旧 env 仍可存在
    # 作为回滚排查线索，但不能恢复同步外呼。
    _ = runtime_setting(QUESTIONNAIRE_EXTERNAL_PUSH_MODE_KEY, "queue").strip().lower()
    return "queue"


def plan_questionnaire_external_push_effect(
    *,
    questionnaire: dict[str, Any],
    submission: dict[str, Any],
    computed_result: dict[str, Any],
    context: CommandContext,
    source_command_id: str,
    source_event_id: str = "",
    idempotency_key: str = "",
    mode: str | None = None,
    external_push_result: dict[str, Any] | None = None,
    service: ExternalEffectService | None = None,
) -> dict[str, Any] | None:
    config = dict(questionnaire.get("external_push_config") or {})
    enabled = _bool(config.get("enabled") or questionnaire.get("external_push_enabled"))
    target_url = _text(config.get("webhook_url") or questionnaire.get("external_push_url"))
    if not enabled or not target_url:
        return None

    selected_mode = "queue"
    body = build_questionnaire_external_push_payload(
        questionnaire=questionnaire,
        submission=submission,
        computed_result=computed_result,
    )
    payload = build_questionnaire_external_effect_payload(
        questionnaire=questionnaire,
        submission=submission,
        computed_result=computed_result,
        target_url=target_url,
        body=body,
    )
    result = dict(external_push_result or {})
    try:
        job = (service or ExternalEffectService()).plan_effect(
            effect_type=WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH,
            adapter_name="outbound_webhook",
            operation="post",
            target_type="questionnaire_submission",
            target_id=_text(submission.get("submission_id")),
            business_type="questionnaire",
            business_id=_text(questionnaire.get("id")),
            payload=payload,
            payload_summary=_questionnaire_external_effect_payload_summary(
                questionnaire=questionnaire,
                submission=submission,
                body=body,
                payload=payload,
                mode=selected_mode,
                external_push_result=result,
            ),
            context=context,
            source_module="questionnaire.external_push",
            source_event_id=source_event_id,
            source_command_id=source_command_id,
            risk_level="medium",
            requires_approval=False,
            execution_mode="execute",
            status="queued",
            idempotency_key=idempotency_key
            or f"{source_command_id}:external-effect:{WEBHOOK_QUESTIONNAIRE_SUBMISSION_PUSH}",
        )
        return job
    except Exception:
        return None


def build_questionnaire_external_effect_payload(
    *,
    questionnaire: dict[str, Any],
    submission: dict[str, Any],
    computed_result: dict[str, Any],
    target_url: str,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = dict(questionnaire.get("external_push_config") or {})
    request_body = body or build_questionnaire_external_push_payload(
        questionnaire=questionnaire,
        submission=submission,
        computed_result=computed_result,
    )
    payload: dict[str, Any] = {
        "webhook_url": target_url,
        "body": request_body,
        "signature": {
            "enabled": bool(os.getenv("AICRM_EXTERNAL_EFFECT_WEBHOOK_SIGNING_SECRET")),
            "alg": "hmac-sha256",
            "header": "X-AICRM-External-Effect-Signature",
        },
    }
    _copy_test_loopback_config(payload, config, request_body)
    return payload


def build_questionnaire_external_push_payload(
    *,
    questionnaire: dict[str, Any],
    submission: dict[str, Any],
    computed_result: dict[str, Any],
) -> dict[str, Any]:
    config = dict(questionnaire.get("external_push_config") or {})
    answer_snapshots = list(submission.get("answer_snapshots") or computed_result.get("answer_snapshots") or [])
    payload: dict[str, Any] = {
        "user_id": _external_push_user_id(submission),
        "questionnaire_title": _text(questionnaire.get("title") or questionnaire.get("name")),
        "submitted_at": _iso_datetime(submission.get("submitted_at") or submission.get("created_at")),
        "phone_number": _phone_number(answer_snapshots),
        "answers": _serialized_answers(answer_snapshots),
    }
    _copy_int(payload, "day", config.get("day") if "day" in config else questionnaire.get("external_push_day"))
    _copy_int(payload, "frequency", config.get("frequency") if "frequency" in config else questionnaire.get("external_push_frequency"))
    _copy_int(
        payload,
        "expires_at_ts",
        config.get("expires_at_ts") if "expires_at_ts" in config else questionnaire.get("external_push_expires_at_ts"),
    )
    push_type = _text(config.get("type") or questionnaire.get("external_push_type"))
    if push_type:
        payload["type"] = push_type
    remark = _text(config.get("remark") or questionnaire.get("external_push_remark"))
    if remark:
        payload["remark"] = remark
    assessment_result = computed_result.get("assessment_result")
    if isinstance(assessment_result, dict) and assessment_result:
        payload["assessment_result_snapshot"] = assessment_result
    for item in _custom_params(config.get("custom_params") or questionnaire.get("external_push_custom_params")):
        payload[item["name"]] = item["value"]
    return payload


def _copy_test_loopback_config(payload: dict[str, Any], config: dict[str, Any], body: dict[str, Any]) -> None:
    receiver_token = _text(config.get("receiver_token") or config.get("test_receiver_token"))
    if not receiver_token:
        return
    payload["receiver_token"] = receiver_token
    payload["receiver_response_status"] = int(config.get("receiver_response_status") or config.get("test_receiver_response_status") or 200)
    payload["execution_scope"] = "test_loopback"
    payload["is_test"] = True
    payload["expected_payload_hash"] = _canonical_payload_hash(body)
    expires_at = _text(config.get("test_receiver_expires_at"))
    payload["test_receiver_expires_at"] = expires_at or public_datetime(utcnow() + timedelta(hours=12))


def _questionnaire_external_effect_payload_summary(
    *,
    questionnaire: dict[str, Any],
    submission: dict[str, Any],
    body: dict[str, Any],
    payload: dict[str, Any],
    mode: str,
    external_push_result: dict[str, Any],
) -> dict[str, Any]:
    answers = body.get("answers") if isinstance(body.get("answers"), list) else []
    return {
        "questionnaire_id": int(questionnaire.get("id") or 0),
        "slug": _text(questionnaire.get("slug")),
        "submission_id": _text(submission.get("submission_id")),
        "external_push_mode": mode,
        "external_push_enabled": bool(external_push_result.get("enabled", True)),
        "external_push_attempted_by_legacy_path": bool(external_push_result.get("attempted")),
        "external_push_status": _text(external_push_result.get("status")),
        "target_url_present": bool(payload.get("webhook_url")),
        "signature_configured": bool((payload.get("signature") or {}).get("enabled")) if isinstance(payload.get("signature"), dict) else False,
        "body_type": type(body).__name__,
        "answer_count": len(answers),
        "phone_number_present": bool(_text(body.get("phone_number")) and _text(body.get("phone_number")) != "NULL"),
        "user_id_present": bool(_text(body.get("user_id"))),
        "execution_scope": _text(payload.get("execution_scope")),
        "is_test": bool(payload.get("is_test")),
        "expected_payload_hash": _text(payload.get("expected_payload_hash")),
    }


def _canonical_payload_hash(body: dict[str, Any]) -> str:
    canonical = json.dumps(body or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _log(
    *,
    repo: Any,
    questionnaire: dict[str, Any],
    submission: dict[str, Any],
    target_url: str,
    payload: dict[str, Any],
    response_status_code: int | None,
    response_body: str,
    status: str,
    failure_reason: str,
) -> dict[str, Any]:
    create_log = getattr(repo, "create_external_push_log", None)
    if not callable(create_log):
        return {}
    try:
        return create_log(
            questionnaire_id=int(questionnaire["id"]),
            questionnaire_title_snapshot=_text(questionnaire.get("title") or questionnaire.get("name")),
            submission_record_id=submission.get("id") or submission.get("submission_id"),
            retry_from_log_id=None,
            retry_attempt=0,
            user_id=_text(payload.get("user_id")),
            target_url=target_url,
            request_payload=payload,
            response_status_code=response_status_code,
            response_body=response_body,
            status=status,
            failure_reason=failure_reason,
        )
    except Exception:
        return {}


def _global_enabled(repo: Any) -> bool:
    value = _setting(repo, GLOBAL_ENABLED_KEY)
    if value in (None, ""):
        return True
    return _bool(value)


def _timeout_seconds(repo: Any) -> float:
    value = _setting(repo, TIMEOUT_SECONDS_KEY)
    try:
        timeout = float(value if value not in (None, "") else 3)
    except (TypeError, ValueError):
        timeout = 3.0
    return max(0.5, min(timeout, 10.0))


def _setting(repo: Any, key: str) -> str | None:
    get_setting = getattr(repo, "get_app_setting", None)
    if not callable(get_setting):
        return None
    return get_setting(key)


def _serialized_answers(answer_snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    for item in answer_snapshots:
        question_type = _text(item.get("question_type"))
        title = _text(item.get("question_title_snapshot"))
        if question_type == "multi_choice":
            answer: str | list[str] = _dedupe([_text(value) for value in item.get("selected_option_texts_snapshot") or []])
        elif question_type == "single_choice":
            answer = (_dedupe([_text(value) for value in item.get("selected_option_texts_snapshot") or []]) or [""])[0]
        elif question_type in {"textarea", "mobile"}:
            answer = _text(item.get("text_value"))
        else:
            continue
        serialized.append({"title": title, "answer": answer})
    return serialized


def _phone_number(answer_snapshots: list[dict[str, Any]]) -> str:
    for item in answer_snapshots:
        if _text(item.get("question_type")) != "mobile":
            continue
        return _text(item.get("text_value")) or "NULL"
    return "NULL"


def _external_push_user_id(submission: dict[str, Any]) -> str:
    for field in ["respondent_key", "external_userid", "unionid", "openid"]:
        value = _text(submission.get(field))
        if value:
            return value
    return ""


def _copy_int(payload: dict[str, Any], key: str, value: Any) -> None:
    if value in (None, ""):
        return
    payload[key] = int(value)


def _custom_params(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, str]] = []
    reserved = {"user_id", "questionnaire_title", "submitted_at", "answers", "phone_number", "type", "expires_at_ts", "day", "frequency", "remark"}
    for item in value:
        if not isinstance(item, dict):
            continue
        name = _text(item.get("name"))
        if not name or name in reserved:
            continue
        result.append({"name": name, "value": _text(item.get("value"))})
    return result


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _iso_datetime(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return _text(value)


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _bool(value: Any) -> bool:
    return str(value if value is not None else "").strip().lower() in {"1", "true", "yes", "on", "t"}
