from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from xml.sax.saxutils import escape as xml_escape
from typing import Any

import requests
from flask import current_app

from ...db import get_db
from ...infra.settings import mask_value
from ...services import get_recent_messages_by_user
from . import repo
from .agents import (
    AGENT_OUTPUT_TYPE_OPTIONS,
    CHILD_AGENT_CONFIG_MAP,
    CHILD_AGENT_ORDER,
    ROUTER_REQUEST_SAMPLE,
    ROUTER_RESPONSE_SAMPLE,
    ROUTER_FALLBACK_DEFAULT,
    SKILL_REGISTRY_ORDER,
    default_agent_config_payloads,
    default_agent_router_payload,
    default_skill_registry_payloads,
)
from .service import ensure_agent_prompt_defaults, get_member_detail, get_stage_detail_payload

_EXPORT_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="agent-output-export")

_POOL_TO_ROUTE_KEY = {
    "new_user": "new-user",
    "inactive_normal": "inactive-normal",
    "inactive_focus": "inactive-focus",
    "active_normal": "active-normal",
    "active_focus": "active-focus",
    "silent": "silent",
    "won": "won",
}

_DEFAULT_OUTPUT_HEADERS = [
    "时间",
    "request_id",
    "userid",
    "external_contact_id",
    "agent_code",
    "output_type",
    "target_agent_code",
    "target_pool",
    "confidence",
    "reason",
    "rendered_output_text",
    "applied_status",
]
_EXPORT_RATE_LIMIT_WINDOW_MINUTES = 10
_EXPORT_RATE_LIMIT_COUNT = 5


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return _normalized_text(value).lower() in {"1", "true", "yes", "y", "on"}


def _normalize_int(value: Any, *, default: int, minimum: int = 0, maximum: int = 10_000) -> int:
    try:
        resolved = int(value)
    except (TypeError, ValueError):
        resolved = int(default)
    return max(minimum, min(maximum, resolved))


def _normalize_float(value: Any, *, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _iso_now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _copy_json(value: Any, *, default: Any) -> Any:
    if value in (None, ""):
        return copy.deepcopy(default)
    try:
        return json.loads(json.dumps(value, ensure_ascii=False))
    except (TypeError, ValueError):
        return copy.deepcopy(default)


def _mask_phone(value: Any) -> str:
    text = _normalized_text(value)
    if len(text) < 7:
        return text
    return f"{text[:3]}****{text[-4:]}"


def _mask_external_contact_id(value: Any) -> str:
    text = _normalized_text(value)
    if len(text) <= 7:
        return text
    return f"{text[:4]}***{text[-3:]}"


def _mask_sensitive_value(key: str, value: Any) -> Any:
    normalized_key = _normalized_text(key).lower()
    if normalized_key in {"phone", "mobile"}:
        return _mask_phone(value)
    if normalized_key in {"external_contact_id", "external_userid", "userid"}:
        return _mask_external_contact_id(value)
    if normalized_key in {"signature_token", "signature_secret"}:
        return mask_value(key.upper(), _normalized_text(value))
    if isinstance(value, dict):
        return {item_key: _mask_sensitive_value(item_key, item_value) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [_mask_sensitive_value(key, item) for item in value]
    return value


def _redact_text_content(value: Any, *, max_length: int = 160) -> str:
    text = _normalized_text(value)
    if not text:
        return ""
    masked = text
    if len(masked) >= 7 and masked.isdigit():
        masked = _mask_phone(masked)
    if len(masked) > max_length:
        masked = f"{masked[:max_length]}..."
    return masked


def _mask_snapshot_by_visibility(key: str, value: Any, *, visibility: str) -> Any:
    if visibility == "full":
        return value
    normalized_key = _normalized_text(key).lower()
    if normalized_key in {"raw_output_text", "final_prompt_preview"}:
        return "敏感内容已隐藏，仅内部 API / Skill 可查看明文"
    if normalized_key in {"messages", "recent_messages", "newmessages"}:
        if isinstance(value, list):
            return {
                "count": len(value),
                "preview": [_redact_text_content(item if not isinstance(item, dict) else item.get("content") or item.get("text")) for item in value[:3]],
                "masked": True,
            }
        return {"count": 0, "preview": [], "masked": True}
    if normalized_key in {"content", "rendered_output_text"}:
        return _redact_text_content(value)
    if isinstance(value, dict):
        return {item_key: _mask_snapshot_by_visibility(item_key, item_value, visibility=visibility) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [_mask_snapshot_by_visibility(key, item, visibility=visibility) for item in value]
    return _mask_sensitive_value(key, value)


def _visible_output_text(value: Any, *, visibility: str) -> str:
    text = _normalized_text(value)
    if visibility == "full":
        return text
    if not text:
        return ""
    return "敏感内容已隐藏，仅内部 API / Skill 可查看明文"


def _visible_rendered_text(value: Any, *, visibility: str) -> str:
    text = _normalized_text(value)
    if visibility == "full":
        return text
    return _redact_text_content(text)


def _quantile(values: list[int], percentile: float) -> int:
    if not values:
        return 0
    ordered = sorted(int(item) for item in values)
    if len(ordered) == 1:
        return ordered[0]
    index = int(round((len(ordered) - 1) * percentile))
    index = max(0, min(len(ordered) - 1, index))
    return ordered[index]


def _build_excel_xml(headers: list[str], rows: list[list[str]]) -> bytes:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<?mso-application progid="Excel.Sheet"?>',
        '<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"',
        ' xmlns:o="urn:schemas-microsoft-com:office:office"',
        ' xmlns:x="urn:schemas-microsoft-com:office:excel"',
        ' xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">',
        '<Worksheet ss:Name="AgentOutputs">',
        "<Table>",
    ]

    def _render_row(values: list[str]) -> str:
        return "<Row>" + "".join(
            f'<Cell><Data ss:Type="String">{xml_escape(str(value or ""))}</Data></Cell>'
            for value in values
        ) + "</Row>"

    lines.append(_render_row(headers))
    lines.extend(_render_row(item) for item in rows)
    lines.extend(["</Table>", "</Worksheet>", "</Workbook>"])
    return "\n".join(lines).encode("utf-8")


def _request_env_label() -> str:
    if current_app.config.get("TESTING"):
        return "test"
    if current_app.debug:
        return "dev"
    return "prod"


def ensure_agent_orchestration_defaults() -> None:
    ensure_agent_prompt_defaults()
    if not repo.get_agent_router_config():
        payload = default_agent_router_payload()
        repo.insert_agent_router_config(
            {
                **payload,
                "fallback_strategy_json": payload.get("fallback_strategy") or {},
                "request_sample_json": payload.get("request_sample") or {},
                "response_sample_json": payload.get("response_sample") or {},
                "updated_by": "system",
                "updated_source": "seed",
                "last_status": "never_called",
            }
        )
    prompt_rows = {
        _normalized_text(item.get("agent_code")): repo.deserialize_agent_prompt_row(item)
        for item in repo.list_agent_prompt_rows()
    }
    existing_agent_codes = {
        _normalized_text(item.get("agent_code"))
        for item in repo.list_agent_config_rows()
        if _normalized_text(item.get("agent_code"))
    }
    for payload in default_agent_config_payloads():
        agent_code = _normalized_text(payload.get("agent_code"))
        if agent_code in existing_agent_codes:
            continue
        legacy_prompt = prompt_rows.get(agent_code, {})
        role_prompt = _normalized_text(payload.get("draft_role_prompt"))
        task_prompt = _normalized_text(legacy_prompt.get("prompt_text")) or _normalized_text(payload.get("draft_task_prompt"))
        display_name = _normalized_text(legacy_prompt.get("display_name")) or _normalized_text(payload.get("display_name"))
        repo.insert_agent_config_row(
            {
                **payload,
                "display_name": display_name,
                "draft_role_prompt": role_prompt,
                "draft_task_prompt": task_prompt,
                "published_role_prompt": role_prompt,
                "published_task_prompt": task_prompt,
                "enabled": legacy_prompt.get("enabled", payload.get("enabled", True)),
                "last_modified_at": _iso_now(),
                "last_modified_by": "system",
                "last_modified_source": "seed",
            }
        )
    existing_skill_codes = {
        _normalized_text(item.get("skill_code"))
        for item in repo.list_agent_skill_rows()
        if _normalized_text(item.get("skill_code"))
    }
    for payload in default_skill_registry_payloads():
        skill_code = _normalized_text(payload.get("skill_code"))
        if skill_code in existing_skill_codes:
            continue
        repo.insert_agent_skill_row(payload)
    get_db().commit()


def _serialize_router_config(row: dict[str, Any] | None) -> dict[str, Any]:
    deserialized = repo.deserialize_agent_router_config_row(row or {})
    fallback = dict(deserialized.get("fallback_strategy_json") or {})
    return {
        "enabled": bool(deserialized.get("enabled")),
        "webhook_url": _normalized_text(deserialized.get("webhook_url")),
        "signature_token_masked": mask_value("ROUTER_SIGNATURE_TOKEN", _normalized_text(deserialized.get("signature_token"))),
        "signature_secret_masked": mask_value("ROUTER_SIGNATURE_SECRET", _normalized_text(deserialized.get("signature_secret"))),
        "signature_token_configured": bool(_normalized_text(deserialized.get("signature_token"))),
        "signature_secret_configured": bool(_normalized_text(deserialized.get("signature_secret"))),
        "signature_header": _normalized_text(deserialized.get("signature_header")) or "X-Lobster-Signature",
        "timeout_seconds": int(deserialized.get("timeout_seconds") or 8),
        "retry_count": int(deserialized.get("retry_count") or 1),
        "fallback_strategy": fallback,
        "last_status": _normalized_text(deserialized.get("last_status")) or "never_called",
        "last_error": _normalized_text(deserialized.get("last_error")),
        "last_called_at": _normalized_text(deserialized.get("last_called_at")) or "暂无记录",
        "updated_by": _normalized_text(deserialized.get("updated_by")) or "system",
        "updated_source": _normalized_text(deserialized.get("updated_source")) or "seed",
        "request_sample": deserialized.get("request_sample_json") or dict(ROUTER_REQUEST_SAMPLE),
        "response_sample": deserialized.get("response_sample_json") or dict(ROUTER_RESPONSE_SAMPLE),
    }


def _agent_diff_summary(item: dict[str, Any]) -> list[str]:
    draft = dict(item.get("draft") or {})
    published = dict(item.get("published") or {})
    results: list[str] = []
    if _normalized_text(draft.get("role_prompt")) != _normalized_text(published.get("role_prompt")):
        results.append("角色提示词草稿与已发布版本不同")
    if _normalized_text(draft.get("task_prompt")) != _normalized_text(published.get("task_prompt")):
        results.append("任务提示词草稿与已发布版本不同")
    if json.dumps(draft.get("variables") or [], ensure_ascii=False, sort_keys=True) != json.dumps(
        published.get("variables") or [], ensure_ascii=False, sort_keys=True
    ):
        results.append("变量配置草稿尚未发布")
    if json.dumps(draft.get("output_schema") or [], ensure_ascii=False, sort_keys=True) != json.dumps(
        published.get("output_schema") or [], ensure_ascii=False, sort_keys=True
    ):
        results.append("输出协议草稿尚未发布")
    return results


def _serialize_agent_config(row: dict[str, Any] | None) -> dict[str, Any]:
    deserialized = repo.deserialize_agent_config_row(row or {})
    payload = {
        "agent_code": _normalized_text(deserialized.get("agent_code")),
        "display_name": _normalized_text(deserialized.get("display_name")) or _normalized_text(
            (CHILD_AGENT_CONFIG_MAP.get(_normalized_text(deserialized.get("agent_code"))) or {}).get("display_name")
        ),
        "pool_keys": list(deserialized.get("pool_keys_json") or []),
        "enabled": bool(deserialized.get("enabled")),
        "draft_version": int(deserialized.get("draft_version") or 1),
        "published_version": int(deserialized.get("published_version") or 0),
        "published_at": _normalized_text(deserialized.get("published_at")),
        "published_by": _normalized_text(deserialized.get("published_by")),
        "last_modified_at": _normalized_text(deserialized.get("last_modified_at")) or _normalized_text(deserialized.get("updated_at")),
        "last_modified_by": _normalized_text(deserialized.get("last_modified_by")) or "system",
        "last_modified_source": _normalized_text(deserialized.get("last_modified_source")) or "seed",
        "last_change_summary": _normalized_text(deserialized.get("last_change_summary")) or "暂无变更摘要",
        "draft": {
            "role_prompt": _normalized_text(deserialized.get("draft_role_prompt")),
            "task_prompt": _normalized_text(deserialized.get("draft_task_prompt")),
            "variables": list(deserialized.get("draft_variables_json") or []),
            "output_schema": list(deserialized.get("draft_output_schema_json") or []),
        },
        "published": {
            "role_prompt": _normalized_text(deserialized.get("published_role_prompt")),
            "task_prompt": _normalized_text(deserialized.get("published_task_prompt")),
            "variables": list(deserialized.get("published_variables_json") or []),
            "output_schema": list(deserialized.get("published_output_schema_json") or []),
        },
    }
    payload["diff_summary"] = _agent_diff_summary(payload)
    return payload


def _serialize_skill_row(row: dict[str, Any] | None) -> dict[str, Any]:
    deserialized = repo.deserialize_agent_skill_row(row or {})
    return {
        "skill_code": _normalized_text(deserialized.get("skill_code")),
        "agent_code": _normalized_text(deserialized.get("agent_code")) or "shared",
        "pool_keys": list(deserialized.get("pool_keys_json") or []),
        "read_capabilities": list(deserialized.get("read_capabilities_json") or []),
        "write_capabilities": list(deserialized.get("write_capabilities_json") or []),
        "enabled": bool(deserialized.get("enabled")),
        "input_schema": dict(deserialized.get("input_schema_json") or {}),
        "output_schema": dict(deserialized.get("output_schema_json") or {}),
        "permission_notes": _normalized_text(deserialized.get("permission_notes")),
        "idempotency_notes": _normalized_text(deserialized.get("idempotency_notes")),
        "audit_notes": _normalized_text(deserialized.get("audit_notes")),
        "example_request": dict(deserialized.get("example_request_json") or {}),
        "example_response": dict(deserialized.get("example_response_json") or {}),
        "last_call_status": _normalized_text(deserialized.get("last_call_status")) or "never_called",
        "last_error": _normalized_text(deserialized.get("last_error")),
        "last_called_at": _normalized_text(deserialized.get("last_called_at")) or "暂无记录",
    }


def _serialize_agent_run(row: dict[str, Any] | None, *, visibility: str = "masked") -> dict[str, Any]:
    deserialized = repo.deserialize_agent_run_row(row or {})
    return {
        "run_id": _normalized_text(deserialized.get("run_id")),
        "request_id": _normalized_text(deserialized.get("request_id")),
        "batch_id": _normalized_text(deserialized.get("batch_id")),
        "userid": _normalized_text(deserialized.get("userid")) if visibility == "full" else _mask_external_contact_id(deserialized.get("userid")),
        "external_contact_id": _normalized_text(deserialized.get("external_contact_id")) if visibility == "full" else _mask_external_contact_id(deserialized.get("external_contact_id")),
        "agent_code": _normalized_text(deserialized.get("agent_code")),
        "agent_type": _normalized_text(deserialized.get("agent_type")),
        "provider": _normalized_text(deserialized.get("provider")),
        "input_snapshot": _mask_snapshot_by_visibility("input_snapshot_json", deserialized.get("input_snapshot_json") or {}, visibility=visibility),
        "variables_snapshot": _mask_snapshot_by_visibility("variables_snapshot_json", deserialized.get("variables_snapshot_json") or {}, visibility=visibility),
        "final_prompt_preview": _visible_output_text(deserialized.get("final_prompt_preview"), visibility=visibility),
        "role_prompt_version": _normalized_text(deserialized.get("role_prompt_version")),
        "task_prompt_version": _normalized_text(deserialized.get("task_prompt_version")),
        "status": _normalized_text(deserialized.get("status")),
        "error_code": _normalized_text(deserialized.get("error_code")),
        "error_message": _normalized_text(deserialized.get("error_message")),
        "latency_ms": int(deserialized.get("latency_ms") or 0),
        "source": _normalized_text(deserialized.get("source")),
        "parent_run_id": _normalized_text(deserialized.get("parent_run_id")),
        "replay_of_run_id": _normalized_text(deserialized.get("replay_of_run_id")),
        "created_at": _normalized_text(deserialized.get("created_at")),
        "updated_at": _normalized_text(deserialized.get("updated_at")),
    }


def _serialize_agent_output(row: dict[str, Any] | None, *, visibility: str = "masked") -> dict[str, Any]:
    deserialized = repo.deserialize_agent_output_row(row or {})
    normalized_output = dict(deserialized.get("normalized_output_json") or {})
    return {
        "output_id": _normalized_text(deserialized.get("output_id")),
        "run_id": _normalized_text(deserialized.get("run_id")),
        "request_id": _normalized_text(deserialized.get("request_id")),
        "userid": _normalized_text(deserialized.get("userid")) if visibility == "full" else _mask_external_contact_id(deserialized.get("userid")),
        "external_contact_id": _normalized_text(deserialized.get("external_contact_id")) if visibility == "full" else _mask_external_contact_id(deserialized.get("external_contact_id")),
        "agent_code": _normalized_text(deserialized.get("agent_code")),
        "output_type": _normalized_text(deserialized.get("output_type")),
        "raw_output_text": _visible_output_text(deserialized.get("raw_output_text"), visibility=visibility),
        "normalized_output": _mask_snapshot_by_visibility("normalized_output_json", normalized_output, visibility=visibility),
        "rendered_output_text": _visible_rendered_text(deserialized.get("rendered_output_text"), visibility=visibility),
        "target_agent_code": _normalized_text(deserialized.get("target_agent_code")),
        "target_pool": _normalized_text(deserialized.get("target_pool")),
        "confidence": round(_normalize_float(deserialized.get("confidence"), default=0), 4),
        "reason": _normalized_text(deserialized.get("reason")),
        "need_human_review": bool(deserialized.get("need_human_review")),
        "applied_status": _normalized_text(deserialized.get("applied_status")) or "pending",
        "applied_at": _normalized_text(deserialized.get("applied_at")),
        "adopted_by": _normalized_text(deserialized.get("adopted_by")),
        "adopted_action": _normalized_text(deserialized.get("adopted_action")),
        "adopted_at": _normalized_text(deserialized.get("adopted_at")),
        "outcome_status": _normalized_text(deserialized.get("outcome_status")),
        "outcome_value": _visible_rendered_text(deserialized.get("outcome_value"), visibility=visibility),
        "revision_of_output_id": _normalized_text(deserialized.get("revision_of_output_id")),
        "error_code": _normalized_text(deserialized.get("error_code")),
        "error_message": _normalized_text(deserialized.get("error_message")),
        "created_at": _normalized_text(deserialized.get("created_at")),
        "is_error": bool(_normalized_text(deserialized.get("error_code")) or _normalized_text(deserialized.get("error_message"))),
    }


def _serialize_export_job(row: dict[str, Any] | None) -> dict[str, Any]:
    deserialized = repo.deserialize_agent_output_export_job_row(row or {})
    return {
        "job_id": _normalized_text(deserialized.get("job_id")),
        "requested_by": _normalized_text(deserialized.get("requested_by")) or "system",
        "filters": dict(deserialized.get("filters_json") or {}),
        "status": _normalized_text(deserialized.get("status")),
        "total_count": int(deserialized.get("total_count") or 0),
        "exported_count": int(deserialized.get("exported_count") or 0),
        "file_name": _normalized_text(deserialized.get("file_name")),
        "has_file": bool(_normalized_text(deserialized.get("file_content_base64"))),
        "error_message": _normalized_text(deserialized.get("error_message")),
        "created_at": _normalized_text(deserialized.get("created_at")),
        "updated_at": _normalized_text(deserialized.get("updated_at")),
        "finished_at": _normalized_text(deserialized.get("finished_at")),
    }


def _load_agent_list() -> list[dict[str, Any]]:
    ensure_agent_orchestration_defaults()
    rows = {
        _normalized_text(item.get("agent_code")): _serialize_agent_config(item)
        for item in repo.list_agent_config_rows()
    }
    return [rows.get(agent_code) or _serialize_agent_config({"agent_code": agent_code, **CHILD_AGENT_CONFIG_MAP[agent_code]}) for agent_code in CHILD_AGENT_ORDER]


def _load_skill_list() -> list[dict[str, Any]]:
    ensure_agent_orchestration_defaults()
    rows = {
        _normalized_text(item.get("skill_code")): _serialize_skill_row(item)
        for item in repo.list_agent_skill_rows()
    }
    return [rows.get(skill_code) or _serialize_skill_row({"skill_code": skill_code}) for skill_code in SKILL_REGISTRY_ORDER]


def _build_member_variable_snapshot(external_contact_id: str = "", phone: str = "") -> dict[str, Any]:
    detail = get_member_detail(external_contact_id=external_contact_id, phone=phone)
    profile = dict(detail.get("profile") or {})
    member = dict(detail.get("member") or {})
    questionnaire = dict(detail.get("questionnaire") or {})
    recent_messages = get_recent_messages_by_user(_normalized_text(profile.get("external_contact_id")), limit=20) if _normalized_text(profile.get("external_contact_id")) else []
    return {
        "recent_messages": [str(item.get("content") or item.get("message_text") or item.get("text") or "") for item in recent_messages[:20]],
        "current_pool": _normalized_text(member.get("current_pool")),
        "current_stage": _normalized_text(member.get("current_stage")),
        "questionnaire_result": _normalized_text(questionnaire.get("result")),
        "focus_reason": "、".join(questionnaire.get("matched_questions") or []),
        "owner_name": _normalized_text(profile.get("owner_display_name") or profile.get("owner_staff_id")),
        "last_touch_at": _normalized_text(member.get("updated_at")),
        "member_tags": [],
        "message_activity_level": _normalized_text(member.get("activation_status")),
        "latest_agent_outputs": [
            item["rendered_output_text"] or item["reason"]
            for item in get_agent_outputs_by_user(_normalized_text(profile.get("external_contact_id")), limit=3).get("rows", [])
        ],
        "member_snapshot": {
            "external_contact_id": _normalized_text(profile.get("external_contact_id")),
            "phone": _normalized_text(profile.get("phone")),
            "current_pool": _normalized_text(member.get("current_pool")),
            "current_stage": _normalized_text(member.get("current_stage")),
            "follow_type": _normalized_text(member.get("follow_type")),
            "questionnaire_result": _normalized_text(questionnaire.get("result")),
        },
    }


def _enabled_child_agents() -> list[str]:
    return [
        item["agent_code"]
        for item in _load_agent_list()
        if item.get("agent_code") and bool(item.get("enabled"))
    ]


def _router_message_entry(message: dict[str, Any], *, external_contact_id: str) -> dict[str, Any]:
    sender = _normalized_text(message.get("sender") or message.get("from"))
    role = "customer" if sender == _normalized_text(external_contact_id) else "staff"
    return {
        "role": role,
        "content": _normalized_text(message.get("content")),
        "created_at": _normalized_text(message.get("send_time")),
        "msgtype": _normalized_text(message.get("msgtype")) or "text",
        "chat_type": _normalized_text(message.get("chat_type")) or "private",
        "sender": sender,
    }


def _build_router_member_snapshot(detail: dict[str, Any]) -> dict[str, Any]:
    profile = dict(detail.get("profile") or {})
    member = dict(detail.get("member") or {})
    questionnaire = dict(detail.get("questionnaire") or {})
    return {
        "customer_name": _normalized_text(profile.get("customer_name")),
        "owner_staff_id": _normalized_text(profile.get("owner_staff_id")),
        "owner_display_name": _normalized_text(profile.get("owner_display_name")),
        "external_contact_id": _normalized_text(profile.get("external_contact_id") or member.get("external_contact_id")),
        "phone": _normalized_text(profile.get("phone") or member.get("phone")),
        "current_pool": _normalized_text(member.get("current_pool")),
        "current_stage": _normalized_text(member.get("current_stage")),
        "follow_type": _normalized_text(member.get("follow_type")),
        "questionnaire_status": _normalized_text(questionnaire.get("status")),
        "questionnaire_result": _normalized_text(questionnaire.get("result")),
        "decision_source": _normalized_text(member.get("decision_source")),
        "in_pool": bool(member.get("in_pool")),
    }


def _router_signature_headers(config: dict[str, Any], *, body_text: str, created_at: str) -> dict[str, str]:
    header_name = _normalized_text(config.get("signature_header")) or "X-Lobster-Signature"
    token = _normalized_text(config.get("signature_token"))
    secret = _normalized_text(config.get("signature_secret"))
    headers = {
        "Content-Type": "application/json",
        "X-Lobster-Timestamp": created_at,
        "X-Shadow-Mode": "1",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if secret:
        digest = hmac.new(secret.encode("utf-8"), body_text.encode("utf-8"), hashlib.sha256).hexdigest()
        headers[header_name] = f"sha256={digest}"
    return headers


def _touch_router_runtime_status(*, status: str, error_message: str = "", last_called_at: str = "") -> None:
    existing = repo.deserialize_agent_router_config_row(repo.get_agent_router_config() or {})
    if not existing:
        return
    repo.save_agent_router_config(
        {
            "enabled": bool(existing.get("enabled")),
            "webhook_url": _normalized_text(existing.get("webhook_url")),
            "signature_token": _normalized_text(existing.get("signature_token")),
            "signature_secret": _normalized_text(existing.get("signature_secret")),
            "signature_header": _normalized_text(existing.get("signature_header")) or "X-Lobster-Signature",
            "timeout_seconds": int(existing.get("timeout_seconds") or 8),
            "retry_count": int(existing.get("retry_count") or 1),
            "fallback_strategy_json": existing.get("fallback_strategy_json") or {},
            "request_sample_json": existing.get("request_sample_json") or {},
            "response_sample_json": existing.get("response_sample_json") or {},
            "last_status": _normalized_text(status),
            "last_error": _normalized_text(error_message),
            "last_called_at": _normalized_text(last_called_at),
            "updated_by": _normalized_text(existing.get("updated_by")) or "system",
            "updated_source": _normalized_text(existing.get("updated_source")) or "runtime",
        }
    )


def _validated_router_response(data: Any, *, allowed_agents: list[str]) -> tuple[dict[str, Any], str]:
    if not isinstance(data, dict):
        return {}, "invalid_schema_response"
    normalized = {
        "userid": _normalized_text(data.get("userid")),
        "external_contact_id": _normalized_text(data.get("external_contact_id")),
        "agent_code": _normalized_text(data.get("agent_code")),
        "confidence": _normalize_float(data.get("confidence"), default=0.0),
        "reason": _normalized_text(data.get("reason")),
        "target_pool": _normalized_text(data.get("target_pool")),
        "need_human_review": bool(data.get("need_human_review")),
        "response_version": _normalized_text(data.get("response_version")) or "router-v1",
    }
    if not normalized["agent_code"]:
        return {}, "invalid_schema_response"
    if normalized["agent_code"] not in allowed_agents:
        return normalized, "unknown_agent_code"
    return normalized, ""


def _router_fallback_payload(
    *,
    reason_code: str,
    error_message: str,
    router_config: dict[str, Any],
    request_payload: dict[str, Any],
    raw_response_text: str = "",
) -> dict[str, Any]:
    strategy = {**ROUTER_FALLBACK_DEFAULT, **dict(router_config.get("fallback_strategy_json") or {})}
    return {
        "userid": _normalized_text(request_payload.get("userid")),
        "external_contact_id": _normalized_text(request_payload.get("external_contact_id")),
        "agent_code": _normalized_text(strategy.get("default_agent_code")) or "welcome_agent",
        "confidence": 0.0,
        "reason": error_message or reason_code,
        "target_pool": _normalized_text(strategy.get("default_pool")) or "new_user",
        "need_human_review": bool(strategy.get("need_human_review")),
        "response_version": "router-fallback-v1",
        "fallback_reason_code": reason_code,
        "fallback_alert_channel": _normalized_text(strategy.get("alert_channel")) or "run_center",
        "fail_closed": bool(strategy.get("fail_closed")),
        "raw_response_text": raw_response_text,
    }


def run_agent_router_shadow_decision(
    *,
    external_contact_id: str,
    owner_userid: str = "",
    batch_id: str = "",
    source: str = "reply_monitor",
    recent_messages: list[dict[str, Any]] | None = None,
    member_detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ensure_agent_orchestration_defaults()
    router_config = repo.deserialize_agent_router_config_row(repo.get_agent_router_config() or {})
    if not bool(router_config.get("enabled")) or not _normalized_text(router_config.get("webhook_url")):
        return {"ok": False, "status": "shadow_disabled", "shadow_called": False}

    detail = member_detail or get_member_detail(external_contact_id=external_contact_id, phone="")
    if not detail:
        return {"ok": False, "status": "member_not_found", "shadow_called": False}
    owner_value = _normalized_text(owner_userid) or _normalized_text((detail.get("profile") or {}).get("owner_staff_id"))
    allowed_agents = _enabled_child_agents()
    now_text = _iso_now()
    request_id = f"router-shadow-{uuid.uuid4().hex}"
    run_id = f"arun-{uuid.uuid4().hex}"
    history_messages = list(recent_messages or get_recent_messages_by_user(external_contact_id, limit=20))
    request_payload = {
        "request_id": request_id,
        "batch_id": _normalized_text(batch_id),
        "tenant": "aicrm",
        "env": _request_env_label(),
        "messages": [_router_message_entry(item, external_contact_id=external_contact_id) for item in history_messages[:20]],
        "userid": owner_value,
        "external_contact_id": _normalized_text(external_contact_id),
        "member_snapshot": _build_router_member_snapshot(detail),
        "allowed_agents": allowed_agents,
        "context_version": "lobster-shadow-v1",
        "created_at": now_text,
    }
    variables_snapshot = _build_member_variable_snapshot(external_contact_id, _normalized_text((detail.get("profile") or {}).get("phone")))
    create_agent_run(
        {
            "run_id": run_id,
            "request_id": request_id,
            "batch_id": _normalized_text(batch_id),
            "userid": owner_value,
            "external_contact_id": _normalized_text(external_contact_id),
            "agent_code": "central_router_agent",
            "agent_type": "router",
            "provider": "lobster_shadow",
            "input_snapshot": request_payload,
            "variables_snapshot": variables_snapshot,
            "final_prompt_preview": "shadow_router_webhook",
            "role_prompt_version": "router-webhook",
            "task_prompt_version": "shadow-v1",
            "status": "pending",
            "source": source,
        }
    )
    started_at = time.perf_counter()
    body_text = json.dumps(request_payload, ensure_ascii=False, separators=(",", ":"))
    headers = _router_signature_headers(router_config, body_text=body_text, created_at=now_text)
    timeout_seconds = max(1, int(router_config.get("timeout_seconds") or 8))
    retry_count = max(0, int(router_config.get("retry_count") or 1))
    response_text = ""
    response_payload: dict[str, Any] = {}
    status = "success"
    error_code = ""
    error_message = ""
    decision: dict[str, Any] = {}

    try:
        response = None
        for attempt in range(retry_count + 1):
            try:
                response = requests.post(
                    _normalized_text(router_config.get("webhook_url")),
                    data=body_text.encode("utf-8"),
                    headers=headers,
                    timeout=timeout_seconds,
                )
                break
            except requests.Timeout as exc:
                error_code = "timeout"
                error_message = str(exc) or "router webhook timeout"
                if attempt >= retry_count:
                    raise
            except requests.RequestException as exc:
                error_code = "request_error"
                error_message = str(exc) or "router webhook request_error"
                if attempt >= retry_count:
                    raise
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        if response is None:
            raise requests.RequestException(error_message or "router webhook request_error")
        response_text = _normalized_text(response.text)
        if int(response.status_code) >= 400:
            status = "fallback"
            error_code = f"http_status_{int(response.status_code)}"
            error_message = response_text or error_code
            decision = _router_fallback_payload(
                reason_code=error_code,
                error_message=error_message,
                router_config=router_config,
                request_payload=request_payload,
                raw_response_text=response_text,
            )
        else:
            try:
                payload_data = response.json()
            except ValueError:
                payload_data = None
            normalized_response, schema_error = _validated_router_response(payload_data, allowed_agents=allowed_agents)
            if schema_error == "unknown_agent_code":
                status = "fallback"
                error_code = "unknown_agent_code"
                error_message = f"unknown agent_code: {normalized_response.get('agent_code')}"
                decision = _router_fallback_payload(
                    reason_code=error_code,
                    error_message=error_message,
                    router_config=router_config,
                    request_payload=request_payload,
                    raw_response_text=response_text or json.dumps(payload_data or {}, ensure_ascii=False),
                )
            elif schema_error:
                status = "fallback"
                error_code = "invalid_schema_response"
                error_message = "invalid_schema_response"
                decision = _router_fallback_payload(
                    reason_code=error_code,
                    error_message=error_message,
                    router_config=router_config,
                    request_payload=request_payload,
                    raw_response_text=response_text or json.dumps(payload_data or {}, ensure_ascii=False),
                )
            else:
                response_payload = normalized_response
                decision = normalized_response
        output_type = "route_decision" if status == "success" else "fallback_decision"
        update_agent_run_status(
            run_id,
            {
                "status": status,
                "error_code": error_code,
                "error_message": error_message,
                "latency_ms": latency_ms,
            },
        )
        output = append_agent_output(
            {
                "run_id": run_id,
                "request_id": request_id,
                "userid": owner_value,
                "external_contact_id": _normalized_text(external_contact_id),
                "agent_code": "central_router_agent",
                "output_type": output_type,
                "raw_output_text": response_text or json.dumps(decision or {}, ensure_ascii=False),
                "normalized_output": decision,
                "rendered_output_text": _normalized_text(decision.get("reason")) or response_text or output_type,
                "target_agent_code": _normalized_text(decision.get("agent_code")),
                "target_pool": _normalized_text(decision.get("target_pool")),
                "confidence": decision.get("confidence") or 0,
                "reason": _normalized_text(decision.get("reason")) or error_message,
                "need_human_review": bool(decision.get("need_human_review")),
                "applied_status": "shadow_recorded",
                "error_code": error_code,
                "error_message": error_message,
            }
        )
        _touch_router_runtime_status(
            status="success" if status == "success" else error_code or "fallback",
            error_message=error_message,
            last_called_at=now_text,
        )
        get_db().commit()
        return {
            "ok": status == "success",
            "status": status,
            "shadow_called": True,
            "run_id": run_id,
            "request_id": request_id,
            "output_id": output.get("output_id"),
            "decision": decision,
            "latency_ms": latency_ms,
        }
    except requests.Timeout as exc:
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        decision = _router_fallback_payload(
            reason_code="timeout",
            error_message=str(exc) or "router webhook timeout",
            router_config=router_config,
            request_payload=request_payload,
        )
        update_agent_run_status(
            run_id,
            {
                "status": "fallback",
                "error_code": "timeout",
                "error_message": str(exc) or "router webhook timeout",
                "latency_ms": latency_ms,
            },
        )
        output = append_agent_output(
            {
                "run_id": run_id,
                "request_id": request_id,
                "userid": owner_value,
                "external_contact_id": _normalized_text(external_contact_id),
                "agent_code": "central_router_agent",
                "output_type": "fallback_decision",
                "raw_output_text": "",
                "normalized_output": decision,
                "rendered_output_text": _normalized_text(decision.get("reason")) or "router webhook timeout",
                "target_agent_code": _normalized_text(decision.get("agent_code")),
                "target_pool": _normalized_text(decision.get("target_pool")),
                "confidence": 0,
                "reason": _normalized_text(decision.get("reason")),
                "need_human_review": bool(decision.get("need_human_review")),
                "applied_status": "shadow_recorded",
                "error_code": "timeout",
                "error_message": str(exc) or "router webhook timeout",
            }
        )
        _touch_router_runtime_status(status="timeout", error_message=str(exc) or "router webhook timeout", last_called_at=now_text)
        get_db().commit()
        return {
            "ok": False,
            "status": "fallback",
            "shadow_called": True,
            "run_id": run_id,
            "request_id": request_id,
            "output_id": output.get("output_id"),
            "decision": decision,
            "latency_ms": latency_ms,
        }
    except requests.RequestException as exc:
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        decision = _router_fallback_payload(
            reason_code="request_error",
            error_message=str(exc) or "router webhook request_error",
            router_config=router_config,
            request_payload=request_payload,
        )
        update_agent_run_status(
            run_id,
            {
                "status": "fallback",
                "error_code": "request_error",
                "error_message": str(exc) or "router webhook request_error",
                "latency_ms": latency_ms,
            },
        )
        output = append_agent_output(
            {
                "run_id": run_id,
                "request_id": request_id,
                "userid": owner_value,
                "external_contact_id": _normalized_text(external_contact_id),
                "agent_code": "central_router_agent",
                "output_type": "fallback_decision",
                "raw_output_text": "",
                "normalized_output": decision,
                "rendered_output_text": _normalized_text(decision.get("reason")) or "router webhook request_error",
                "target_agent_code": _normalized_text(decision.get("agent_code")),
                "target_pool": _normalized_text(decision.get("target_pool")),
                "confidence": 0,
                "reason": _normalized_text(decision.get("reason")),
                "need_human_review": bool(decision.get("need_human_review")),
                "applied_status": "shadow_recorded",
                "error_code": "request_error",
                "error_message": str(exc) or "router webhook request_error",
            }
        )
        _touch_router_runtime_status(status="request_error", error_message=str(exc) or "router webhook request_error", last_called_at=now_text)
        get_db().commit()
        return {
            "ok": False,
            "status": "fallback",
            "shadow_called": True,
            "run_id": run_id,
            "request_id": request_id,
            "output_id": output.get("output_id"),
            "decision": decision,
            "latency_ms": latency_ms,
        }


def record_agent_output_outcome(
    output_id: str,
    *,
    outcome_status: str,
    outcome_value: str = "",
    adopted_by: str = "",
    adopted_action: str = "",
    adopted_at: str = "",
    applied_status: str = "",
) -> dict[str, Any]:
    update_payload: dict[str, Any] = {
        "outcome_status": _normalized_text(outcome_status),
        "outcome_value": _normalized_text(outcome_value),
    }
    if _normalized_text(adopted_by):
        update_payload["adopted_by"] = _normalized_text(adopted_by)
    if _normalized_text(adopted_action):
        update_payload["adopted_action"] = _normalized_text(adopted_action)
    if _normalized_text(adopted_at):
        update_payload["adopted_at"] = _normalized_text(adopted_at)
    if _normalized_text(applied_status):
        update_payload["applied_status"] = _normalized_text(applied_status)
    row = repo.update_agent_output(
        _normalized_text(output_id),
        update_payload,
    )
    get_db().commit()
    return _serialize_agent_output(row)


def get_agent_orchestration_metrics(*, date_from: str = "", date_to: str = "") -> dict[str, Any]:
    ensure_agent_orchestration_defaults()
    run_filters = {
        "agent_code": "central_router_agent",
        "date_from": _normalized_text(date_from) or (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S"),
        "date_to": _normalized_text(date_to),
    }
    router_runs = [
        repo.deserialize_agent_run_row(item)
        for item in repo.list_agent_run_rows(filters=run_filters, limit=5000, offset=0)
        if _normalized_text(item.get("provider")) == "lobster_shadow"
    ]
    router_run_ids = {_normalized_text(item.get("run_id")) for item in router_runs if _normalized_text(item.get("run_id"))}
    raw_outputs = [
        repo.deserialize_agent_output_row(item)
        for item in repo.list_agent_output_rows(
            filters={
                "agent_code": "central_router_agent",
                "date_from": run_filters["date_from"],
                "date_to": run_filters["date_to"],
            },
            limit=5000,
            offset=0,
        )
        if _normalized_text(item.get("run_id")) in router_run_ids
    ]
    decision_outputs = [item for item in raw_outputs if _normalized_text(item.get("output_type")) in {"route_decision", "fallback_decision"}]
    success_count = sum(1 for item in router_runs if _normalized_text(item.get("status")) == "success")
    fallback_count = sum(1 for item in decision_outputs if _normalized_text(item.get("output_type")) == "fallback_decision")
    invalid_schema_count = sum(
        1
        for item in router_runs
        if _normalized_text(item.get("error_code")) == "invalid_schema_response"
    )
    latency_values = [int(item.get("latency_ms") or 0) for item in router_runs if int(item.get("latency_ms") or 0) > 0]
    agent_hits: dict[str, int] = {}
    confidence_buckets = {"0.00-0.49": 0, "0.50-0.69": 0, "0.70-0.84": 0, "0.85-1.00": 0}
    adopted_outputs = [
        item for item in decision_outputs if _normalized_text(item.get("applied_status")) in {"applied", "adopted", "replayed"}
    ]
    won_external_ids = {
        external_id
        for external_id in {
            _normalized_text(item.get("external_contact_id")) for item in adopted_outputs if _normalized_text(item.get("external_contact_id"))
        }
        if _normalized_text((repo.get_member_by_external_contact_id(external_id) or {}).get("current_pool")) == "won"
    }
    error_counts: dict[str, int] = {}
    for item in decision_outputs:
        target_agent = _normalized_text(item.get("target_agent_code")) or "unassigned"
        agent_hits[target_agent] = agent_hits.get(target_agent, 0) + 1
        confidence = _normalize_float(item.get("confidence"), default=0.0)
        if confidence < 0.5:
            confidence_buckets["0.00-0.49"] += 1
        elif confidence < 0.7:
            confidence_buckets["0.50-0.69"] += 1
        elif confidence < 0.85:
            confidence_buckets["0.70-0.84"] += 1
        else:
            confidence_buckets["0.85-1.00"] += 1
    for item in router_runs:
        error_key = _normalized_text(item.get("error_code")) or _normalized_text(item.get("error_message"))
        if error_key:
            error_counts[error_key] = error_counts.get(error_key, 0) + 1
    total_runs = len(router_runs)
    total_decisions = len(decision_outputs)
    adopted_conversion_count = sum(
        1 for item in adopted_outputs if _normalized_text(item.get("external_contact_id")) in won_external_ids
    )
    return {
        "window": {
            "date_from": run_filters["date_from"],
            "date_to": run_filters["date_to"] or "",
        },
        "call_volume": total_runs,
        "success_rate": round(success_count / total_runs, 4) if total_runs else 0.0,
        "fallback_rate": round(fallback_count / total_decisions, 4) if total_decisions else 0.0,
        "invalid_schema_rate": round(invalid_schema_count / total_runs, 4) if total_runs else 0.0,
        "latency": {
            "avg_ms": round(sum(latency_values) / len(latency_values), 2) if latency_values else 0.0,
            "p95_ms": _quantile(latency_values, 0.95),
        },
        "agent_hit_distribution": [
            {"agent_code": key, "count": value}
            for key, value in sorted(agent_hits.items(), key=lambda item: (-item[1], item[0]))
        ],
        "confidence_distribution": [
            {"bucket": key, "count": value}
            for key, value in confidence_buckets.items()
        ],
        "adoption_rate": round(len(adopted_outputs) / total_decisions, 4) if total_decisions else 0.0,
        "adoption_conversion_rate": round(adopted_conversion_count / len(adopted_outputs), 4) if adopted_outputs else 0.0,
        "top_errors": [
            {"error": key, "count": value}
            for key, value in sorted(error_counts.items(), key=lambda item: (-item[1], item[0]))[:5]
        ],
        "notes": [
            "当前 metrics 基于 lobster shadow mode 的中央路由调用，不会接管真实生产分流。",
            "采纳率当前只统计真正进入 applied / adopted / replayed 的输出；shadow 旁路观察不会被算作采纳。",
        ],
    }


def get_agent_orchestration_payload(
    *,
    subtab: str = "router",
    agent_code: str = "",
    skill_code: str = "",
    output_id: str = "",
    run_id: str = "",
    request_id: str = "",
    external_contact_id: str = "",
    userid: str = "",
    date_from: str = "",
    date_to: str = "",
    output_type: str = "",
    target_pool: str = "",
    applied_status: str = "",
    batch_id: str = "",
    current_pool: str = "",
    min_confidence: str = "",
    max_confidence: str = "",
    has_error: str = "",
    page: int = 1,
    page_size: int = 20,
    export_job_id: str = "",
) -> dict[str, Any]:
    ensure_agent_orchestration_defaults()
    router_row = repo.get_agent_router_config() or {}
    agent_items = _load_agent_list()
    skill_items = _load_skill_list()
    selected_agent_code = _normalized_text(agent_code) or (agent_items[0]["agent_code"] if agent_items else "")
    selected_skill_code = _normalized_text(skill_code) or (skill_items[0]["skill_code"] if skill_items else "")
    selected_agent = next((item for item in agent_items if item["agent_code"] == selected_agent_code), agent_items[0] if agent_items else {})
    selected_skill = next((item for item in skill_items if item["skill_code"] == selected_skill_code), skill_items[0] if skill_items else {})

    output_filters = {
        "request_id": request_id,
        "batch_id": batch_id,
        "external_contact_id": external_contact_id,
        "userid": userid,
        "agent_code": agent_code if subtab == "outputs" and agent_code else "",
        "output_type": output_type,
        "current_pool": current_pool,
        "target_pool": target_pool,
        "applied_status": applied_status,
        "date_from": date_from,
        "date_to": date_to,
        "min_confidence": min_confidence,
        "max_confidence": max_confidence,
        "has_error": has_error,
    }
    resolved_page = max(1, int(page or 1))
    resolved_page_size = max(1, min(100, int(page_size or 20)))
    total_outputs = repo.count_agent_output_rows(output_filters)
    output_rows = [_serialize_agent_output(item, visibility="masked") for item in repo.list_agent_output_rows(filters=output_filters, limit=resolved_page_size, offset=(resolved_page - 1) * resolved_page_size)]
    selected_output = (
        get_agent_output_detail(_normalized_text(output_id), visibility="masked")
        if _normalized_text(output_id)
        else (get_agent_output_detail(output_rows[0]["output_id"], visibility="masked") if output_rows else {})
    )

    replay_payload = get_agent_replay_payload(
        run_id=run_id,
        request_id=request_id,
        external_contact_id=external_contact_id,
        userid=userid,
        date_from=date_from,
        date_to=date_to,
        visibility="masked",
    )

    route_outputs = repo.list_agent_output_rows(filters={"agent_code": "central_router_agent"}, limit=20, offset=0)
    shadow_route_outputs = [
        item
        for item in route_outputs
        if _normalized_text((repo.get_agent_run_row(_normalized_text(item.get("run_id"))) or {}).get("provider")) == "lobster_shadow"
    ]
    fallback_outputs = sum(1 for item in shadow_route_outputs if _normalized_text(item.get("output_type")) == "fallback_decision")
    export_job = get_agent_output_export_job(_normalized_text(export_job_id)) if _normalized_text(export_job_id) else {}
    last_route_output = next(
        (
            _serialize_agent_output(item, visibility="masked")
            for item in shadow_route_outputs
            if _normalized_text(item.get("output_type")) in {"route_decision", "fallback_decision"}
        ),
        {},
    )
    metrics_payload = get_agent_orchestration_metrics(date_from=date_from, date_to=date_to)

    return {
        "subtab": _normalized_text(subtab) or "router",
        "router": {
            "config": _serialize_router_config(router_row),
            "input_protocol": dict(ROUTER_REQUEST_SAMPLE),
            "output_protocol": dict(ROUTER_RESPONSE_SAMPLE),
            "allowed_agents": [item["agent_code"] for item in agent_items],
            "last_route_output": last_route_output,
            "fallback_count": int(fallback_outputs),
            "notes": [
                "中央路由不再作为普通 Prompt Agent 配置，而是一个外部 webhook / 龙虾路由接入配置。",
                "当 webhook 超时、返回 schema 无效或 agent_code 不存在时，会按 fallback 策略进入默认 Agent 或人工复核队列。",
            ],
        },
        "skills": {
            "items": skill_items,
            "selected": selected_skill,
            "notes": [
                "Skill 按只读、草稿写入和建议能力分层；当前未开放高风险直接改池能力。",
                "每次 skill 调用都会写入审计表，并刷新最近调用状态。",
            ],
        },
        "agents": {
            "items": agent_items,
            "selected": selected_agent,
            "notes": [
                "子 Agent 配置已拆成角色提示词、任务提示词、变量配置和输出协议。",
                "当前支持草稿态与已发布态；回滚仍是最小结构占位，不伪装成完整版本系统。",
            ],
        },
        "outputs": {
            "filters": output_filters,
            "rows": output_rows,
            "page": resolved_page,
            "page_size": resolved_page_size,
            "total": total_outputs,
            "selected": selected_output,
            "export_job": export_job,
            "notes": [
                "所有结构化输出采用追加式入账；是否采用与输出本身分离。",
                "小量导出同步完成，大量导出会进入异步任务。",
            ],
        },
        "replay": replay_payload,
        "metrics": metrics_payload,
    }


def save_agent_router_settings(payload: dict[str, Any], *, operator_id: str, source: str = "admin_console") -> dict[str, Any]:
    ensure_agent_orchestration_defaults()
    existing = repo.deserialize_agent_router_config_row(repo.get_agent_router_config() or {})
    webhook_url = _normalized_text(payload.get("webhook_url"))
    if webhook_url and not webhook_url.startswith(("http://", "https://")):
        raise ValueError("router webhook_url must start with http:// or https://")
    timeout_seconds = _normalize_int(payload.get("timeout_seconds"), default=8, minimum=1, maximum=60)
    retry_count = _normalize_int(payload.get("retry_count"), default=1, minimum=0, maximum=5)
    fallback_strategy = _copy_json(payload.get("fallback_strategy") or {}, default={})
    default_agent_code = _normalized_text(fallback_strategy.get("default_agent_code"))
    if default_agent_code and default_agent_code not in CHILD_AGENT_CONFIG_MAP:
        raise ValueError("fallback default_agent_code is invalid")
    signature_token = _normalized_text(payload.get("signature_token")) or _normalized_text(existing.get("signature_token"))
    signature_secret = _normalized_text(payload.get("signature_secret")) or _normalized_text(existing.get("signature_secret"))
    saved = repo.save_agent_router_config(
        {
            "enabled": _normalize_bool(payload.get("enabled")),
            "webhook_url": webhook_url,
            "signature_token": signature_token,
            "signature_secret": signature_secret,
            "signature_header": _normalized_text(payload.get("signature_header")) or "X-Lobster-Signature",
            "timeout_seconds": timeout_seconds,
            "retry_count": retry_count,
            "fallback_strategy_json": fallback_strategy,
            "request_sample_json": payload.get("request_sample") or dict(ROUTER_REQUEST_SAMPLE),
            "response_sample_json": payload.get("response_sample") or dict(ROUTER_RESPONSE_SAMPLE),
            "last_status": _normalized_text(existing.get("last_status")) or "configured",
            "last_error": _normalized_text(existing.get("last_error")),
            "last_called_at": _normalized_text(existing.get("last_called_at")),
            "updated_by": operator_id,
            "updated_source": source,
        }
    )
    get_db().commit()
    return {"router": _serialize_router_config(saved)}


def get_agent_config_detail(agent_code: str) -> dict[str, Any]:
    ensure_agent_orchestration_defaults()
    row = repo.get_agent_config_row(_normalized_text(agent_code))
    if not row:
        raise LookupError("agent config not found")
    return _serialize_agent_config(row)


def save_agent_config_draft(agent_code: str, payload: dict[str, Any], *, operator_id: str, source: str = "admin_console") -> dict[str, Any]:
    ensure_agent_orchestration_defaults()
    normalized_agent_code = _normalized_text(agent_code)
    if normalized_agent_code not in CHILD_AGENT_CONFIG_MAP:
        raise ValueError("invalid agent_code")
    existing = repo.deserialize_agent_config_row(repo.get_agent_config_row(normalized_agent_code) or {})
    if not existing:
        raise LookupError("agent config not found")
    next_display_name = _normalized_text(payload.get("display_name")) or _normalized_text(existing.get("display_name"))
    next_role_prompt = _normalized_text(payload.get("role_prompt")) or _normalized_text(existing.get("draft_role_prompt"))
    next_task_prompt = _normalized_text(payload.get("task_prompt")) or _normalized_text(existing.get("draft_task_prompt"))
    if not next_role_prompt:
        raise ValueError("role_prompt is required")
    if not next_task_prompt:
        raise ValueError("task_prompt is required")
    next_variables = _copy_json(payload.get("variables"), default=list(existing.get("draft_variables_json") or []))
    next_output_schema = _copy_json(payload.get("output_schema"), default=list(existing.get("draft_output_schema_json") or []))
    changed = json.dumps(
        {
            "display_name": next_display_name,
            "role_prompt": next_role_prompt,
            "task_prompt": next_task_prompt,
            "variables": next_variables,
            "output_schema": next_output_schema,
            "enabled": _normalize_bool(payload.get("enabled", existing.get("enabled"))),
        },
        ensure_ascii=False,
        sort_keys=True,
    ) != json.dumps(
        {
            "display_name": _normalized_text(existing.get("display_name")),
            "role_prompt": _normalized_text(existing.get("draft_role_prompt")),
            "task_prompt": _normalized_text(existing.get("draft_task_prompt")),
            "variables": list(existing.get("draft_variables_json") or []),
            "output_schema": list(existing.get("draft_output_schema_json") or []),
            "enabled": bool(existing.get("enabled")),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    next_draft_version = int(existing.get("draft_version") or 1) + (1 if changed else 0)
    summary = _normalized_text(payload.get("change_summary")) or (
        "更新角色/任务提示词、变量配置与输出协议草稿" if changed else _normalized_text(existing.get("last_change_summary"))
    )
    saved = repo.update_agent_config_row(
        normalized_agent_code,
        {
            "display_name": next_display_name,
            "pool_keys": list(existing.get("pool_keys_json") or []),
            "enabled": _normalize_bool(payload.get("enabled", existing.get("enabled"))),
            "draft_role_prompt": next_role_prompt,
            "draft_task_prompt": next_task_prompt,
            "draft_variables": next_variables,
            "draft_output_schema": next_output_schema,
            "published_role_prompt": _normalized_text(existing.get("published_role_prompt")),
            "published_task_prompt": _normalized_text(existing.get("published_task_prompt")),
            "published_variables": list(existing.get("published_variables_json") or []),
            "published_output_schema": list(existing.get("published_output_schema_json") or []),
            "draft_version": next_draft_version,
            "published_version": int(existing.get("published_version") or 0),
            "published_at": _normalized_text(existing.get("published_at")),
            "published_by": _normalized_text(existing.get("published_by")),
            "last_modified_at": _iso_now(),
            "last_modified_by": operator_id,
            "last_modified_source": source,
            "last_change_summary": summary,
        },
    )
    legacy_prompt = repo.get_agent_prompt_row(normalized_agent_code)
    if legacy_prompt:
        repo.update_agent_prompt_row(
            normalized_agent_code,
            {
                "display_name": next_display_name,
                "prompt_text": next_task_prompt,
                "enabled": _normalize_bool(payload.get("enabled", existing.get("enabled"))),
                "version": int(legacy_prompt.get("version") or 1) + (1 if changed else 0),
            },
        )
    else:
        repo.insert_agent_prompt_row(
            {
                "agent_code": normalized_agent_code,
                "display_name": next_display_name,
                "prompt_text": next_task_prompt,
                "enabled": _normalize_bool(payload.get("enabled", existing.get("enabled"))),
                "version": 1,
            }
        )
    get_db().commit()
    return {"agent": _serialize_agent_config(saved)}


def publish_agent_config(agent_code: str, *, operator_id: str) -> dict[str, Any]:
    ensure_agent_orchestration_defaults()
    normalized_agent_code = _normalized_text(agent_code)
    existing = repo.deserialize_agent_config_row(repo.get_agent_config_row(normalized_agent_code) or {})
    if not existing:
        raise LookupError("agent config not found")
    saved = repo.update_agent_config_row(
        normalized_agent_code,
        {
            "display_name": _normalized_text(existing.get("display_name")),
            "pool_keys": list(existing.get("pool_keys_json") or []),
            "enabled": bool(existing.get("enabled")),
            "draft_role_prompt": _normalized_text(existing.get("draft_role_prompt")),
            "draft_task_prompt": _normalized_text(existing.get("draft_task_prompt")),
            "draft_variables": list(existing.get("draft_variables_json") or []),
            "draft_output_schema": list(existing.get("draft_output_schema_json") or []),
            "published_role_prompt": _normalized_text(existing.get("draft_role_prompt")),
            "published_task_prompt": _normalized_text(existing.get("draft_task_prompt")),
            "published_variables": list(existing.get("draft_variables_json") or []),
            "published_output_schema": list(existing.get("draft_output_schema_json") or []),
            "draft_version": int(existing.get("draft_version") or 1),
            "published_version": int(existing.get("draft_version") or 1),
            "published_at": _iso_now(),
            "published_by": operator_id,
            "last_modified_at": _iso_now(),
            "last_modified_by": operator_id,
            "last_modified_source": "publish",
            "last_change_summary": f"发布草稿版本 v{int(existing.get('draft_version') or 1)}",
        },
    )
    get_db().commit()
    return {"agent": _serialize_agent_config(saved)}


def create_agent_run(payload: dict[str, Any]) -> dict[str, Any]:
    row = repo.insert_agent_run(payload)
    get_db().commit()
    return _serialize_agent_run(row)


def update_agent_run_status(run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    existing = repo.deserialize_agent_run_row(repo.get_agent_run_row(run_id) or {})
    if not existing:
        raise LookupError("agent run not found")
    row = repo.update_agent_run(
        run_id,
        {
            "request_id": payload.get("request_id", existing.get("request_id")),
            "batch_id": payload.get("batch_id", existing.get("batch_id")),
            "userid": payload.get("userid", existing.get("userid")),
            "external_contact_id": payload.get("external_contact_id", existing.get("external_contact_id")),
            "agent_code": payload.get("agent_code", existing.get("agent_code")),
            "agent_type": payload.get("agent_type", existing.get("agent_type")),
            "provider": payload.get("provider", existing.get("provider")),
            "input_snapshot": payload.get("input_snapshot", existing.get("input_snapshot_json") or {}),
            "variables_snapshot": payload.get("variables_snapshot", existing.get("variables_snapshot_json") or {}),
            "final_prompt_preview": payload.get("final_prompt_preview", existing.get("final_prompt_preview")),
            "role_prompt_version": payload.get("role_prompt_version", existing.get("role_prompt_version")),
            "task_prompt_version": payload.get("task_prompt_version", existing.get("task_prompt_version")),
            "status": payload.get("status", existing.get("status")),
            "error_code": payload.get("error_code", existing.get("error_code")),
            "error_message": payload.get("error_message", existing.get("error_message")),
            "latency_ms": payload.get("latency_ms", existing.get("latency_ms")),
            "source": payload.get("source", existing.get("source")),
            "parent_run_id": payload.get("parent_run_id", existing.get("parent_run_id")),
            "replay_of_run_id": payload.get("replay_of_run_id", existing.get("replay_of_run_id")),
        },
    )
    get_db().commit()
    return _serialize_agent_run(row)


def append_agent_output(payload: dict[str, Any]) -> dict[str, Any]:
    output_id = _normalized_text(payload.get("output_id")) or f"aout-{uuid.uuid4().hex}"
    row = repo.insert_agent_output({**payload, "output_id": output_id})
    get_db().commit()
    return _serialize_agent_output(row, visibility="full")


def list_agent_outputs(
    filters: dict[str, Any] | None = None,
    *,
    page: int = 1,
    page_size: int = 20,
    visibility: str = "masked",
) -> dict[str, Any]:
    ensure_agent_orchestration_defaults()
    resolved_page = max(1, int(page or 1))
    resolved_page_size = max(1, min(100, int(page_size or 20)))
    total = repo.count_agent_output_rows(filters or {})
    rows = [
        _serialize_agent_output(item, visibility=visibility)
        for item in repo.list_agent_output_rows(filters=filters or {}, limit=resolved_page_size, offset=(resolved_page - 1) * resolved_page_size)
    ]
    return {
        "page": resolved_page,
        "page_size": resolved_page_size,
        "total": total,
        "rows": rows,
    }


def get_agent_output_detail(output_id: str, *, visibility: str = "masked") -> dict[str, Any]:
    row = repo.get_agent_output_row(_normalized_text(output_id))
    if not row:
        return {}
    serialized = _serialize_agent_output(row, visibility=visibility)
    run = get_agent_run_detail(serialized.get("run_id"), visibility=visibility)
    return {
        "output": serialized,
        "run": run,
    }


def get_agent_run_detail(run_id: str, *, visibility: str = "masked") -> dict[str, Any]:
    row = repo.get_agent_run_row(_normalized_text(run_id))
    if not row:
        return {}
    serialized = _serialize_agent_run(row, visibility=visibility)
    serialized["outputs"] = [_serialize_agent_output(item, visibility=visibility) for item in repo.list_agent_outputs_by_run_id(serialized["run_id"])]
    return serialized


def get_agent_outputs_by_request(request_id: str, *, visibility: str = "masked") -> dict[str, Any]:
    return list_agent_outputs({"request_id": request_id}, page=1, page_size=50, visibility=visibility)


def get_agent_outputs_by_user(userid: str, limit: int = 20, *, visibility: str = "masked") -> dict[str, Any]:
    normalized_user = _normalized_text(userid)
    if not normalized_user:
        resolved_page_size = min(100, max(1, int(limit or 20)))
        return {"page": 1, "page_size": resolved_page_size, "total": 0, "rows": []}
    external_match = list_agent_outputs(
        {"external_contact_id": normalized_user},
        page=1,
        page_size=min(100, max(1, int(limit or 20))),
        visibility=visibility,
    )
    if int(external_match.get("total") or 0) > 0:
        return external_match
    return list_agent_outputs(
        {"userid": normalized_user},
        page=1,
        page_size=min(100, max(1, int(limit or 20))),
        visibility=visibility,
    )


def _build_export_rows(filters: dict[str, Any]) -> tuple[list[str], list[list[str]], int]:
    total = repo.count_agent_output_rows(filters)
    rows = [
        _serialize_agent_output(item, visibility="export")
        for item in repo.list_agent_output_rows(filters=filters, limit=max(1, total or 1), offset=0)
    ]
    rendered_rows = [
        [
            item["created_at"],
            item["request_id"],
            item["userid"],
            item["external_contact_id"],
            item["agent_code"],
            item["output_type"],
            item["target_agent_code"],
            item["target_pool"],
            str(item["confidence"]),
            item["reason"],
            item["rendered_output_text"],
            item["applied_status"],
        ]
        for item in rows
    ]
    return _DEFAULT_OUTPUT_HEADERS, rendered_rows, total


def _complete_export_job(job_id: str) -> None:
    job = repo.deserialize_agent_output_export_job_row(repo.get_agent_output_export_job(job_id) or {})
    if not job:
        return
    filters = dict(job.get("filters_json") or {})
    headers, rows, total = _build_export_rows(filters)
    content = _build_excel_xml(headers, rows)
    repo.update_agent_output_export_job(
        job_id,
        {
            "requested_by": _normalized_text(job.get("requested_by")),
            "filters": filters,
            "status": "completed",
            "total_count": total,
            "exported_count": len(rows),
            "file_name": _normalized_text(job.get("file_name")) or f"agent-outputs-{job_id}.xls",
            "file_content_base64": base64.b64encode(content).decode("ascii"),
            "error_message": "",
            "finished_at": _iso_now(),
        },
    )
    get_db().commit()


def create_agent_output_export_job(filters: dict[str, Any], *, requested_by: str, async_threshold: int = 500) -> dict[str, Any]:
    ensure_agent_orchestration_defaults()
    window_start = (datetime.utcnow() - timedelta(minutes=_EXPORT_RATE_LIMIT_WINDOW_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")
    recent_count = repo.count_recent_agent_output_export_jobs(requested_by, since_text=window_start)
    if recent_count >= _EXPORT_RATE_LIMIT_COUNT:
        raise ValueError("export rate limited, please retry later")
    total = repo.count_agent_output_rows(filters or {})
    job_id = f"aexp-{uuid.uuid4().hex}"
    file_name = f"agent-outputs-{datetime.now().strftime('%Y%m%d-%H%M%S')}.xls"
    job_row = repo.insert_agent_output_export_job(
        {
            "job_id": job_id,
            "requested_by": requested_by,
            "filters": filters or {},
            "status": "queued",
            "total_count": total,
            "exported_count": 0,
            "file_name": file_name,
        }
    )
    get_db().commit()
    app = current_app._get_current_object()
    if total <= async_threshold:
        with app.app_context():
            _complete_export_job(job_id)
    else:
        def _worker() -> None:
            with app.app_context():
                try:
                    _complete_export_job(job_id)
                except Exception as exc:  # pragma: no cover - async fallback path
                    repo.update_agent_output_export_job(
                        job_id,
                        {
                            "requested_by": requested_by,
                            "filters": filters or {},
                            "status": "failed",
                            "total_count": total,
                            "exported_count": 0,
                            "file_name": file_name,
                            "error_message": str(exc),
                            "finished_at": _iso_now(),
                        },
                    )
                    get_db().commit()

        _EXPORT_EXECUTOR.submit(_worker)
    return get_agent_output_export_job(job_id)


def get_agent_output_export_job(job_id: str) -> dict[str, Any]:
    row = repo.get_agent_output_export_job(_normalized_text(job_id))
    if not row:
        return {}
    return _serialize_export_job(row)


def get_agent_output_export_file(job_id: str) -> dict[str, Any]:
    row = repo.deserialize_agent_output_export_job_row(repo.get_agent_output_export_job(_normalized_text(job_id)) or {})
    if not row:
        return {}
    content_base64 = _normalized_text(row.get("file_content_base64"))
    return {
        "job": _serialize_export_job(row),
        "file_name": _normalized_text(row.get("file_name")),
        "content_bytes": base64.b64decode(content_base64) if content_base64 else b"",
    }


def get_agent_replay_payload(
    *,
    run_id: str = "",
    request_id: str = "",
    external_contact_id: str = "",
    userid: str = "",
    date_from: str = "",
    date_to: str = "",
    visibility: str = "masked",
) -> dict[str, Any]:
    ensure_agent_orchestration_defaults()
    filters = {
        "run_id": run_id,
        "request_id": request_id,
        "external_contact_id": external_contact_id,
        "userid": userid,
        "date_from": date_from,
        "date_to": date_to,
    }
    run_filters = {key: value for key, value in filters.items() if key in {"request_id", "external_contact_id", "userid", "date_from", "date_to"} and _normalized_text(value)}
    selected_row = repo.get_agent_run_row(_normalized_text(run_id)) if _normalized_text(run_id) else None
    candidate_rows = repo.list_agent_run_rows(filters=run_filters, limit=20, offset=0)
    if not selected_row and candidate_rows:
        selected_row = candidate_rows[0]
    selected_run = _serialize_agent_run(selected_row, visibility=visibility) if selected_row else {}
    outputs = [_serialize_agent_output(item, visibility=visibility) for item in repo.list_agent_outputs_by_run_id(selected_run.get("run_id", ""))] if selected_run else []
    previous_rows = [item for item in candidate_rows if _normalized_text(item.get("run_id")) != _normalized_text(selected_run.get("run_id"))]
    previous_run = _serialize_agent_run(previous_rows[0], visibility=visibility) if previous_rows else {}
    previous_outputs = [_serialize_agent_output(item, visibility=visibility) for item in repo.list_agent_outputs_by_run_id(previous_run.get("run_id", ""))] if previous_run else []
    diff_items: list[str] = []
    if selected_run and previous_run:
        if _normalized_text(selected_run.get("agent_code")) != _normalized_text(previous_run.get("agent_code")):
            diff_items.append("当前回放与上一条 run 的 agent_code 不同")
        if _normalized_text(selected_run.get("status")) != _normalized_text(previous_run.get("status")):
            diff_items.append("当前回放与上一条 run 的状态不同")
        if json.dumps([item.get("output_type") for item in outputs], ensure_ascii=False) != json.dumps(
            [item.get("output_type") for item in previous_outputs], ensure_ascii=False
        ):
            diff_items.append("输出类型集合与上一条 run 不同")
    router_output = next((item for item in outputs if item.get("output_type") in {"route_decision", "fallback_decision"}), {})
    final_output = next((item for item in outputs if item.get("applied_status") in {"applied", "replayed"}), outputs[0] if outputs else {})
    return {
        "filters": filters,
        "runs": [_serialize_agent_run(item, visibility=visibility) for item in candidate_rows],
        "selected_run": selected_run,
        "selected_outputs": outputs,
        "router_output": router_output,
        "final_output": final_output,
        "previous_run": previous_run,
        "diff_items": diff_items,
        "notes": [
            "当前 replay 基于已记录输入快照、变量快照和输出账本重建上下文，不会重新请求外部 webhook。",
            "可以按 request_id 或用户查看最近一次 run，并区分“生成了什么”和“最终采用了什么”。",
        ],
    }


def replay_agent_run(run_id: str, *, operator_id: str) -> dict[str, Any]:
    existing = repo.deserialize_agent_run_row(repo.get_agent_run_row(_normalized_text(run_id)) or {})
    if not existing:
        raise LookupError("agent run not found")
    new_run_id = f"arun-{uuid.uuid4().hex}"
    copied_run = repo.insert_agent_run(
        {
            "run_id": new_run_id,
            "request_id": _normalized_text(existing.get("request_id")),
            "batch_id": _normalized_text(existing.get("batch_id")),
            "userid": _normalized_text(existing.get("userid")),
            "external_contact_id": _normalized_text(existing.get("external_contact_id")),
            "agent_code": _normalized_text(existing.get("agent_code")),
            "agent_type": _normalized_text(existing.get("agent_type")),
            "provider": _normalized_text(existing.get("provider")) or "replay",
            "input_snapshot": existing.get("input_snapshot_json") or {},
            "variables_snapshot": existing.get("variables_snapshot_json") or {},
            "final_prompt_preview": _normalized_text(existing.get("final_prompt_preview")),
            "role_prompt_version": _normalized_text(existing.get("role_prompt_version")),
            "task_prompt_version": _normalized_text(existing.get("task_prompt_version")),
            "status": "replayed",
            "error_code": "",
            "error_message": "",
            "latency_ms": 0,
            "source": f"replay:{operator_id}",
            "parent_run_id": _normalized_text(existing.get("run_id")),
            "replay_of_run_id": _normalized_text(existing.get("run_id")),
        }
    )
    copied_outputs: list[dict[str, Any]] = []
    for item in repo.list_agent_outputs_by_run_id(_normalized_text(existing.get("run_id"))):
        output = repo.deserialize_agent_output_row(item)
        copied_outputs.append(
            _serialize_agent_output(
                repo.insert_agent_output(
                    {
                        "output_id": f"aout-{uuid.uuid4().hex}",
                        "run_id": new_run_id,
                        "request_id": _normalized_text(output.get("request_id")),
                        "userid": _normalized_text(output.get("userid")),
                        "external_contact_id": _normalized_text(output.get("external_contact_id")),
                        "agent_code": _normalized_text(output.get("agent_code")),
                        "output_type": _normalized_text(output.get("output_type")),
                        "raw_output_text": _normalized_text(output.get("raw_output_text")),
                        "normalized_output": output.get("normalized_output_json") or {},
                        "rendered_output_text": _normalized_text(output.get("rendered_output_text")),
                        "target_agent_code": _normalized_text(output.get("target_agent_code")),
                        "target_pool": _normalized_text(output.get("target_pool")),
                        "confidence": output.get("confidence") or 0,
                        "reason": _normalized_text(output.get("reason")),
                        "need_human_review": bool(output.get("need_human_review")),
                        "applied_status": "replayed",
                        "applied_at": _iso_now(),
                        "revision_of_output_id": _normalized_text(output.get("output_id")),
                        "error_code": _normalized_text(output.get("error_code")),
                        "error_message": _normalized_text(output.get("error_message")),
                    }
                )
            )
        )
    get_db().commit()
    return {
        "run": _serialize_agent_run(copied_run),
        "outputs": copied_outputs,
    }


def get_pool_snapshot(pool_key: str, *, limit: int = 10) -> dict[str, Any]:
    route_key = _POOL_TO_ROUTE_KEY.get(_normalized_text(pool_key))
    if not route_key:
        raise ValueError("invalid pool_key")
    payload = get_stage_detail_payload(route_key=route_key, keyword="", offset=0, limit=max(1, min(50, int(limit or 10))))
    return {
        "pool_key": _normalized_text(pool_key),
        "stage": dict(payload.get("stage") or {}),
        "pagination": dict(payload.get("pagination") or {}),
        "filters": dict(payload.get("filters") or {}),
        "member_count": int((payload.get("pagination") or {}).get("total") or 0),
        "sample_members": list(payload.get("customers") or []),
    }


def suggest_pool_action(*, external_contact_id: str = "", phone: str = "", operator_id: str = "skill") -> dict[str, Any]:
    detail = get_member_detail(external_contact_id=external_contact_id, phone=phone)
    member = dict(detail.get("member") or {})
    questionnaire = dict(detail.get("questionnaire") or {})
    current_pool = _normalized_text(member.get("current_pool"))
    next_action = "keep_followup"
    target_pool = current_pool
    reason = "当前阶段无需额外改池，建议继续按照现有跟进节奏推进。"
    if not bool(member.get("in_pool")):
        next_action = "put_in_pool"
        target_pool = "new_user"
        reason = "成员当前不在自动化池内，建议先重新入池。"
    elif _normalized_text(questionnaire.get("status")) == "pending":
        next_action = "wait_questionnaire"
        target_pool = "new_user"
        reason = "成员尚未完成问卷，应继续停留在新用户池等待分层。"
    elif current_pool == "silent":
        next_action = "human_review"
        target_pool = "silent"
        reason = "成员已进入沉默池，建议先人工复核再决定是否唤醒。"
    elif current_pool == "won":
        next_action = "no_action"
        target_pool = "won"
        reason = "成员已经标记成交，不建议自动改池。"
    run_id = f"arun-{uuid.uuid4().hex}"
    request_id = f"skill-{uuid.uuid4().hex}"
    create_agent_run(
        {
            "run_id": run_id,
            "request_id": request_id,
            "userid": _normalized_text((detail.get("profile") or {}).get("owner_staff_id")),
            "external_contact_id": _normalized_text((detail.get("profile") or {}).get("external_contact_id")),
            "agent_code": "suggest_pool_action",
            "agent_type": "skill",
            "provider": "skill_registry",
            "input_snapshot": {"member": detail},
            "variables_snapshot": _build_member_variable_snapshot(external_contact_id, phone),
            "final_prompt_preview": "Skill suggestion only",
            "role_prompt_version": "skill",
            "task_prompt_version": "skill",
            "status": "success",
            "source": f"skill:{operator_id}",
        }
    )
    output = append_agent_output(
        {
            "run_id": run_id,
            "request_id": request_id,
            "userid": _normalized_text((detail.get("profile") or {}).get("owner_staff_id")),
            "external_contact_id": _normalized_text((detail.get("profile") or {}).get("external_contact_id")),
            "agent_code": "suggest_pool_action",
            "output_type": "pool_change_suggestion",
            "raw_output_text": reason,
            "normalized_output": {
                "next_action": next_action,
                "target_pool": target_pool,
                "reason": reason,
                "need_human_review": next_action == "human_review",
            },
            "rendered_output_text": reason,
            "target_pool": target_pool,
            "confidence": 0.61,
            "reason": reason,
            "need_human_review": next_action == "human_review",
            "applied_status": "suggested",
        }
    )
    return {
        "ok": True,
        "run_id": run_id,
        "request_id": request_id,
        "member_exists": bool(detail.get("member_exists")),
        "next_action": next_action,
        "target_pool": target_pool,
        "reason": reason,
        "output": output,
    }


def audit_agent_skill_call(
    *,
    skill_code: str,
    source: str,
    permissions_scope: str,
    request_payload: dict[str, Any],
    response_payload: dict[str, Any],
    status: str,
    error_code: str = "",
    error_message: str = "",
    latency_ms: int = 0,
    idempotency_key: str = "",
) -> dict[str, Any]:
    call_id = f"askill-{uuid.uuid4().hex}"
    row = repo.insert_agent_skill_call_audit(
        {
            "call_id": call_id,
            "skill_code": skill_code,
            "source": source,
            "permissions_scope": permissions_scope,
            "idempotency_key": idempotency_key,
            "request_payload": request_payload,
            "response_payload": response_payload,
            "status": status,
            "error_code": error_code,
            "error_message": error_message,
            "latency_ms": latency_ms,
        }
    )
    skill_row = repo.deserialize_agent_skill_row(repo.get_agent_skill_row(skill_code) or {})
    if skill_row:
        repo.update_agent_skill_row(
            skill_code,
            {
                "agent_code": _normalized_text(skill_row.get("agent_code")),
                "pool_keys": list(skill_row.get("pool_keys_json") or []),
                "read_capabilities": list(skill_row.get("read_capabilities_json") or []),
                "write_capabilities": list(skill_row.get("write_capabilities_json") or []),
                "enabled": bool(skill_row.get("enabled")),
                "input_schema": dict(skill_row.get("input_schema_json") or {}),
                "output_schema": dict(skill_row.get("output_schema_json") or {}),
                "permission_notes": _normalized_text(skill_row.get("permission_notes")),
                "idempotency_notes": _normalized_text(skill_row.get("idempotency_notes")),
                "audit_notes": _normalized_text(skill_row.get("audit_notes")),
                "example_request": dict(skill_row.get("example_request_json") or {}),
                "example_response": dict(skill_row.get("example_response_json") or {}),
                "last_call_status": status,
                "last_error": error_message,
                "last_called_at": _iso_now(),
            }
        )
    get_db().commit()
    return repo.deserialize_agent_skill_call_audit_row(row)
