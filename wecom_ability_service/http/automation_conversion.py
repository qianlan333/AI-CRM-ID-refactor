from __future__ import annotations

import base64
import imghdr
import json

from flask import Response, jsonify, redirect, request, url_for

from ..domains.automation_conversion import (
    create_focus_send_batch,
    create_agent_output_export_job,
    append_sop_v1_template_day,
    append_agent_output,
    audit_agent_skill_call,
    delete_sop_v1_template_day,
    ensure_agent_orchestration_defaults,
    generate_default_channel_qr,
    get_agent_config_detail,
    get_agent_orchestration_payload,
    get_agent_output_detail,
    get_agent_output_export_file,
    get_agent_output_export_job,
    get_agent_outputs_by_request,
    get_agent_outputs_by_user,
    list_agent_configs,
    get_agent_replay_payload,
    get_agent_run_detail,
    get_all_agent_prompts,
    get_debug_payload,
    get_focus_send_batch_detail,
    get_focus_send_batches_payload,
    get_member_detail,
    get_model_infra_payload,
    get_overview_payload,
    get_sop_v1_batches_payload,
    get_sop_v1_config_payload,
    get_sop_v1_management_payload,
    get_sop_v1_templates_payload,
    preview_stage_manual_message,
    get_settings_payload,
    get_stage_detail_payload,
    get_pool_snapshot,
    handle_agent_router_callback,
    list_pending_agent_prompt_publish_requests,
    list_router_pending_callbacks,
    list_agent_outputs,
    mark_won,
    publish_agent_config,
    put_in_pool,
    push_openclaw,
    replay_router_callback,
    replay_agent_run,
    run_router_pending_callback_check,
    remove_from_pool,
    run_registered_due_jobs,
    run_due_reply_monitor,
    run_due_focus_send_batches,
    run_due_sop,
    run_message_activity_sync,
    run_router_test_dispatch,
    run_reply_monitor_capture,
    save_agent_config_draft,
    save_agent_router_settings,
    save_model_infra_prompt,
    save_model_infra_settings,
    save_reply_monitor_enabled,
    save_sop_v1_pool_config,
    save_sop_v1_template,
    save_settings,
    send_stage_manual_message,
    set_follow_type,
    suggest_pool_action,
    test_model_infra_connection,
    unmark_won,
)
from ..domains.automation_conversion.orchestration_service import DraftVersionConflictError, validate_router_callback_signature
from ..domains.tasks.private_message import MAX_PRIVATE_MESSAGE_IMAGES
from .admin_console import _breadcrumb_items, _render_admin_template
from .internal_auth import ensure_admin_console_action_token, require_internal_api_token, validate_admin_console_action_token


MAX_ONE_TIME_BATCH_SEND_IMAGE_SIZE_BYTES = 5 * 1024 * 1024
ALLOWED_ONE_TIME_BATCH_SEND_IMAGE_TYPES = {
    "png": "image/png",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
}


def _query_text(name: str) -> str:
    return str(request.args.get(name) or "").strip()


def _query_int(name: str, *, default: int, minimum: int = 0, maximum: int = 1000) -> int:
    try:
        value = int(request.args.get(name) or default)
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def _query_bool(name: str, *, default: bool = False) -> bool:
    raw_value = request.args.get(name)
    if raw_value is None:
        return bool(default)
    return str(raw_value or "").strip().lower() in {"1", "true", "yes", "on"}


def _operator_from_request() -> str:
    json_payload = request.get_json(silent=True) or {}
    return (
        str(request.headers.get("X-Admin-Operator") or "").strip()
        or str(request.values.get("operator") or "").strip()
        or str(json_payload.get("operator") or "").strip()
        or "crm_console"
    )


def _parse_question_rules_json(raw_value: str) -> list[dict]:
    text = str(raw_value or "").strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("关键题规则 JSON 格式不正确") from exc
    if not isinstance(parsed, list):
        raise ValueError("关键题规则必须是数组")
    return parsed


def _build_settings_form_payload() -> dict[str, object]:
    return {
        "enabled": str(request.form.get("enabled") or "").strip().lower() in {"1", "true", "yes", "on"},
        "questionnaire_id": request.form.get("questionnaire_id"),
        "core_threshold": request.form.get("core_threshold"),
        "top_threshold": request.form.get("top_threshold"),
        "day_start_hour": request.form.get("day_start_hour"),
        "quiet_hour_start": request.form.get("quiet_hour_start"),
        "timezone": request.form.get("timezone"),
        "welcome_message": str(request.form.get("welcome_message") or "").strip(),
        "auto_accept_friend": str(request.form.get("auto_accept_friend") or "").strip().lower() in {"1", "true", "yes", "on"},
        "silent_threshold_days_by_pool": {
            "new_user": request.form.get("silent_threshold_new_user"),
            "inactive_normal": request.form.get("silent_threshold_inactive_normal"),
            "inactive_focus": request.form.get("silent_threshold_inactive_focus"),
            "active_normal": request.form.get("silent_threshold_active_normal"),
            "active_focus": request.form.get("silent_threshold_active_focus"),
        },
        "question_rules": _parse_question_rules_json(request.form.get("question_rules_json", "")),
    }


def _build_model_infra_settings_form_payload() -> dict[str, object]:
    return {
        "enabled": str(request.form.get("deepseek_enabled") or "").strip().lower() in {"1", "true", "yes", "on"},
        "api_key": str(request.form.get("deepseek_api_key") or "").strip(),
        "base_url": str(request.form.get("deepseek_base_url") or "").strip(),
        "router_model": str(request.form.get("deepseek_router_model") or "").strip(),
        "execution_model": str(request.form.get("deepseek_execution_model") or "").strip(),
        "timeout_seconds": request.form.get("deepseek_timeout_seconds"),
    }


def _build_model_prompt_form_payload() -> dict[str, object]:
    return {
        "display_name": str(request.form.get("display_name") or "").strip(),
        "prompt_text": str(request.form.get("prompt_text") or "").strip(),
        "enabled": str(request.form.get("enabled") or "").strip().lower() in {"1", "true", "yes", "on"},
    }


def _build_agent_router_form_payload() -> dict[str, object]:
    return {
        "enabled": str(request.form.get("enabled") or "").strip().lower() in {"1", "true", "yes", "on"},
        "webhook_url": str(request.form.get("webhook_url") or "").strip(),
        "signature_token": str(request.form.get("signature_token") or "").strip(),
        "signature_secret": str(request.form.get("signature_secret") or "").strip(),
        "signature_header": str(request.form.get("signature_header") or "").strip() or "X-Lobster-Signature",
        "timeout_seconds": request.form.get("timeout_seconds"),
        "retry_count": request.form.get("retry_count"),
        "fallback_strategy": {
            "on_timeout": str(request.form.get("fallback_on_timeout") or "").strip(),
            "on_invalid_schema": str(request.form.get("fallback_on_invalid_schema") or "").strip(),
            "on_unknown_agent_code": str(request.form.get("fallback_on_unknown_agent_code") or "").strip(),
            "default_agent_code": str(request.form.get("fallback_default_agent_code") or "").strip(),
            "default_pool": str(request.form.get("fallback_default_pool") or "").strip(),
            "pending_callback_timeout_minutes": request.form.get("fallback_pending_callback_timeout_minutes"),
            "min_confidence": request.form.get("fallback_min_confidence"),
            "need_human_review": str(request.form.get("fallback_need_human_review") or "").strip().lower() in {"1", "true", "yes", "on"},
            "human_review_target_pool": str(request.form.get("fallback_human_review_target_pool") or "").strip(),
            "alert_channel": str(request.form.get("fallback_alert_channel") or "").strip() or "run_center",
            "fail_closed": str(request.form.get("fallback_fail_closed") or "").strip().lower() in {"1", "true", "yes", "on"},
        },
    }


def _build_agent_config_form_payload() -> dict[str, object]:
    variables_json = str(request.form.get("variables_json") or "").strip()
    output_schema_json = str(request.form.get("output_schema_json") or "").strip()
    try:
        variables = json.loads(variables_json or "[]")
    except ValueError as exc:
        raise ValueError("variables_json must be valid JSON array") from exc
    try:
        output_schema = json.loads(output_schema_json or "[]")
    except ValueError as exc:
        raise ValueError("output_schema_json must be valid JSON array") from exc
    if not isinstance(variables, list):
        raise ValueError("variables_json must be a JSON array")
    if not isinstance(output_schema, list):
        raise ValueError("output_schema_json must be a JSON array")
    return {
        "display_name": str(request.form.get("display_name") or "").strip(),
        "enabled": str(request.form.get("enabled") or "").strip().lower() in {"1", "true", "yes", "on"},
        "role_prompt": str(request.form.get("role_prompt") or "").strip(),
        "task_prompt": str(request.form.get("task_prompt") or "").strip(),
        "variables": variables,
        "output_schema": output_schema,
        "change_summary": str(request.form.get("change_summary") or "").strip(),
        "expected_draft_version": str(request.form.get("expected_draft_version") or "").strip(),
    }


def _build_agent_output_filters_from_request() -> dict[str, object]:
    return {
        "request_id": _query_text("request_id") or str(request.form.get("request_id") or "").strip(),
        "batch_id": _query_text("batch_id") or str(request.form.get("batch_id") or "").strip(),
        "agent_code": _query_text("agent_code") or str(request.form.get("agent_code") or "").strip(),
        "output_type": _query_text("output_type") or str(request.form.get("output_type") or "").strip(),
        "userid": _query_text("userid") or str(request.form.get("userid") or "").strip(),
        "external_contact_id": _query_text("external_contact_id") or str(request.form.get("external_contact_id") or "").strip(),
        "current_pool": _query_text("current_pool") or str(request.form.get("current_pool") or "").strip(),
        "target_pool": _query_text("target_pool") or str(request.form.get("target_pool") or "").strip(),
        "applied_status": _query_text("applied_status") or str(request.form.get("applied_status") or "").strip(),
        "date_from": _query_text("date_from") or str(request.form.get("date_from") or "").strip(),
        "date_to": _query_text("date_to") or str(request.form.get("date_to") or "").strip(),
        "min_confidence": _query_text("min_confidence") or str(request.form.get("min_confidence") or "").strip(),
        "max_confidence": _query_text("max_confidence") or str(request.form.get("max_confidence") or "").strip(),
        "has_error": _query_text("has_error")
        or _query_text("is_error")
        or str(request.form.get("has_error") or request.form.get("is_error") or "").strip(),
        "scripts_only": _query_bool("scripts_only") or str(request.form.get("scripts_only") or "").strip().lower() in {"1", "true", "yes", "on"},
    }


def _apply_agent_router_form_state(payload: dict[str, object]) -> dict[str, object]:
    router = dict((payload.get("router") or {}))
    config = dict(router.get("config") or {})
    fallback_strategy = dict(config.get("fallback_strategy") or {})
    config.update(
        {
            "enabled": str(request.form.get("enabled") or "").strip().lower() in {"1", "true", "yes", "on"},
            "webhook_url": str(request.form.get("webhook_url") or "").strip(),
            "signature_header": str(request.form.get("signature_header") or "").strip() or "X-Lobster-Signature",
            "timeout_seconds": str(request.form.get("timeout_seconds") or "").strip() or config.get("timeout_seconds") or 8,
            "retry_count": str(request.form.get("retry_count") or "").strip() or config.get("retry_count") or 1,
        }
    )
    fallback_strategy.update(
        {
            "on_timeout": str(request.form.get("fallback_on_timeout") or "").strip(),
            "on_invalid_schema": str(request.form.get("fallback_on_invalid_schema") or "").strip(),
            "on_unknown_agent_code": str(request.form.get("fallback_on_unknown_agent_code") or "").strip(),
            "default_agent_code": str(request.form.get("fallback_default_agent_code") or "").strip(),
            "default_pool": str(request.form.get("fallback_default_pool") or "").strip(),
            "pending_callback_timeout_minutes": str(request.form.get("fallback_pending_callback_timeout_minutes") or "").strip(),
            "min_confidence": str(request.form.get("fallback_min_confidence") or "").strip(),
            "need_human_review": str(request.form.get("fallback_need_human_review") or "").strip().lower() in {"1", "true", "yes", "on"},
            "human_review_target_pool": str(request.form.get("fallback_human_review_target_pool") or "").strip(),
            "alert_channel": str(request.form.get("fallback_alert_channel") or "").strip() or "run_center",
            "fail_closed": str(request.form.get("fallback_fail_closed") or "").strip().lower() in {"1", "true", "yes", "on"},
        }
    )
    config["fallback_strategy"] = fallback_strategy
    router["config"] = config
    payload["router"] = router
    return payload


def _apply_agent_config_form_state(payload: dict[str, object]) -> dict[str, object]:
    agents = dict((payload.get("agents") or {}))
    selected = dict((agents.get("selected") or {}))
    draft = dict(selected.get("draft") or {})

    display_name = str(request.form.get("display_name") or "").strip()
    if display_name:
        selected["display_name"] = display_name
    selected["enabled"] = str(request.form.get("enabled") or "").strip().lower() in {"1", "true", "yes", "on"}
    selected["last_change_summary"] = str(request.form.get("change_summary") or "").strip()
    selected["draft_version"] = str(request.form.get("expected_draft_version") or "").strip() or selected.get("draft_version")
    draft["role_prompt"] = str(request.form.get("role_prompt") or "").strip()
    draft["task_prompt"] = str(request.form.get("task_prompt") or "").strip()

    variables_json = str(request.form.get("variables_json") or "").strip()
    output_schema_json = str(request.form.get("output_schema_json") or "").strip()
    if variables_json:
        try:
            draft["variables"] = json.loads(variables_json)
        except ValueError:
            draft["variables_json_raw"] = variables_json
    if output_schema_json:
        try:
            draft["output_schema"] = json.loads(output_schema_json)
        except ValueError:
            draft["output_schema_json_raw"] = output_schema_json

    selected["draft"] = draft
    agents["selected"] = selected
    payload["agents"] = agents
    return payload


def _split_multiline_tokens(raw_value: str) -> list[str]:
    tokens: list[str] = []
    normalized = str(raw_value or "").replace("\r", "\n").replace(",", "\n")
    for item in normalized.split("\n"):
        token = item.strip()
        if token:
            tokens.append(token)
    return tokens


def _normalize_manual_send_images() -> list[dict[str, object]]:
    files = [item for item in list(request.files.getlist("images") or []) if getattr(item, "filename", "")]
    if len(files) > MAX_PRIVATE_MESSAGE_IMAGES:
        raise ValueError(f"at most {MAX_PRIVATE_MESSAGE_IMAGES} images are allowed")

    images: list[dict[str, object]] = []
    for index, file_storage in enumerate(files, start=1):
        file_name = str(getattr(file_storage, "filename", "") or f"image-{index}.png").strip() or f"image-{index}.png"
        mime_type = str(getattr(file_storage, "mimetype", "") or "").strip().lower()
        if not mime_type.startswith("image/"):
            raise ValueError("only image files are allowed")
        file_bytes = file_storage.read()
        if len(file_bytes) > MAX_ONE_TIME_BATCH_SEND_IMAGE_SIZE_BYTES:
            raise ValueError("image file is too large (max 5MB)")
        detected_type = ALLOWED_ONE_TIME_BATCH_SEND_IMAGE_TYPES.get(str(imghdr.what(None, h=file_bytes) or "").lower(), "")
        if not detected_type:
            raise ValueError("only image files are allowed")
        images.append(
            {
                "file_name": file_name,
                "content_type": detected_type,
                "data_base64": base64.b64encode(file_bytes).decode("ascii"),
            }
        )
    return images


def _build_manual_send_request_payload() -> dict[str, object]:
    json_payload = request.get_json(silent=True)
    if isinstance(json_payload, dict):
        raw_image_media_ids = json_payload.get("image_media_ids")
        if isinstance(raw_image_media_ids, list):
            image_media_ids = [str(item).strip() for item in raw_image_media_ids if str(item).strip()]
        else:
            image_media_ids = _split_multiline_tokens(str(raw_image_media_ids or ""))
        return {
            "content": str(json_payload.get("content") or "").strip(),
            "image_media_ids": image_media_ids,
            "operator_id": _operator_from_request(),
        }
    payload: dict[str, object] = {
        "content": str(request.form.get("content") or "").strip(),
        "image_media_ids": _split_multiline_tokens(request.form.get("image_media_ids", "")),
        "operator_id": _operator_from_request(),
    }
    images = _normalize_manual_send_images()
    if images:
        payload["images"] = images
    return payload


def _settings_notice() -> str:
    if _query_text("saved") == "1":
        return "设置已保存"
    if _query_text("channel_saved") == "1":
        return "默认渠道二维码已更新"
    if _query_text("message_activity_sync") == "1":
        return "消息活跃同步已完成"
    return ""


def _model_infra_notice() -> str:
    if _query_text("settings_saved") == "1":
        return "DeepSeek 配置已保存"
    if _query_text("prompt_saved"):
        return f"Prompt 已保存：{_query_text('prompt_saved')}"
    if _query_text("tested") == "1":
        return "DeepSeek 测试连接成功"
    return ""


def _overview_notice() -> str:
    reply_monitor_action = _query_text("reply_monitor")
    if reply_monitor_action == "enabled":
        return "自动接话监控已开启"
    if reply_monitor_action == "disabled":
        return "自动接话监控已关闭"
    if reply_monitor_action == "captured":
        return "自动接话监控已完成一次增量扫描"
    if reply_monitor_action == "dispatched":
        return "自动接话监控已尝试放行一条到期队列"
    return ""


def _sop_page_notice() -> str:
    if _query_text("saved") == "1":
        return "SOP 设置已保存"
    return ""


def _member_ops_notice() -> str:
    manual_send_notice = _query_text("manual_send_notice")
    if manual_send_notice == "sent":
        return "官方群发已创建"
    if manual_send_notice == "empty":
        return "当前阶段没有可发送客户"
    if _query_text("focus_batch_notice") == "created":
        return "AI 批任务已创建"
    return ""


def _normalize_stage_key(value: str) -> str:
    return str(value or "").strip().replace("_", "-")


_AUTOMATION_CONVERSION_WORKSPACE_TABS = (
    {
        "key": "overview",
        "label": "总览",
        "summary": "经营驾驶舱",
        "endpoint": "api.admin_automation_conversion",
        "params": {},
    },
    {
        "key": "flow_design",
        "label": "流程设计",
        "summary": "规则与 SOP 工作台",
        "endpoint": "api.admin_automation_conversion_flow_design",
        "params": {"section": "questionnaire"},
    },
    {
        "key": "member_ops",
        "label": "成员运营",
        "summary": "阶段名单与触达执行",
        "endpoint": "api.admin_automation_conversion_member_ops",
        "params": {"stage": "new-user", "panel": "members"},
    },
    {
        "key": "run_center",
        "label": "运行中心",
        "summary": "同步、监控与调试",
        "endpoint": "api.admin_automation_conversion_run_center",
        "params": {"tab": "overview"},
    },
)


def _run_center_notice() -> str:
    if _query_text("message_activity_sync") == "1":
        return "消息活跃同步已完成"
    if _query_text("router_saved") == "1":
        return "路由接入配置已保存"
    if _query_text("agent_draft_saved"):
        return f"{_query_text('agent_draft_saved')} 草稿已保存"
    if _query_text("agent_published"):
        return f"{_query_text('agent_published')} 已发布"
    if _query_text("agent_replayed"):
        return f"{_query_text('agent_replayed')} 已生成回放副本"
    if _query_text("callback_replayed"):
        return f"{_query_text('callback_replayed')} 已生成 callback replay 副本"
    if _query_text("pending_callback_checked") == "1":
        return f"pending callback 检查已完成，新增告警 {_query_text('pending_callback_alerted') or '0'} 条"
    if _query_text("agent_export_job"):
        return "输出导出任务已创建"
    return _model_infra_notice() or _overview_notice()


def _flow_design_section_from_query(default: str = "rules") -> str:
    return _flow_design_section_from_value(_query_text("section"), default=default)


def _flow_design_section_from_value(value: str, *, default: str = "rules") -> str:
    mapping = {
        "stage-model": "stage_model",
        "stage_model": "stage_model",
        "questionnaire": "rules",
        "rules": "rules",
        "sop": "sop",
        "global-rules": "global",
        "global_rules": "global",
        "global": "global",
        "channel": "channel",
        "publish": "publish",
    }
    return mapping.get(str(value or "").strip(), default)


def _canonical_flow_design_section(value: str, *, default: str = "questionnaire") -> str:
    mapping = {
        "stage-model": "stage-model",
        "stage_model": "stage-model",
        "questionnaire": "questionnaire",
        "rules": "questionnaire",
        "sop": "sop",
        "global-rules": "global-rules",
        "global_rules": "global-rules",
        "global": "global-rules",
        "channel": "channel",
        "publish": "publish",
    }
    return mapping.get(str(value or "").strip(), default)


def _member_ops_section_from_query(default: str = "members") -> str:
    mapping = {
        "stage-nav": "stage_nav",
        "stage_nav": "stage_nav",
        "members": "members",
        "list": "members",
        "send": "send",
        "batch": "send",
    }
    return mapping.get(_query_text("panel"), default)


def _run_center_section_from_query(default: str = "overview") -> str:
    mapping = {
        "overview": "overview",
        "sync": "sync",
        "reply-monitor": "reply_monitor",
        "reply_monitor": "reply_monitor",
        "agent-orchestration": "agent_orchestration",
        "agent_orchestration": "agent_orchestration",
        "model-infra": "model",
        "model_infra": "model",
        "model": "model",
        "debug": "debug",
        "logs": "logs",
    }
    return mapping.get(_query_text("tab"), default)


def _run_center_subtab_from_query(default: str = "router") -> str:
    mapping = {
        "router": "router",
        "metrics": "metrics",
        "skills": "skills",
        "agents": "agents",
        "replay": "replay",
        "outputs": "outputs",
    }
    return mapping.get(_query_text("subtab"), default)


def _redirect_to(endpoint: str, **params):
    compact_params = {key: value for key, value in params.items() if value not in (None, "", False)}
    return redirect(url_for(endpoint, **compact_params), code=302)


def _build_overview_dashboard(payload: dict[str, object], settings_payload: dict[str, object]) -> dict[str, object]:
    counts = dict(payload.get("counts") or {})
    stage_columns = list(payload.get("stage_columns") or [])
    sync_payload = dict(payload.get("message_activity_sync") or {})
    sync_run = dict(sync_payload.get("last_run") or {})
    sync_db = dict(sync_payload.get("db_status") or {})
    reply_monitor = dict(payload.get("reply_monitor") or {})
    reply_queue = dict(reply_monitor.get("queue_counts") or {})
    default_channel = dict(settings_payload.get("default_channel") or {})

    todo_items: list[dict[str, str]] = []
    questionnaire_pending = int(counts.get("questionnaire_pending") or 0)
    if questionnaire_pending > 0:
        todo_items.append(
            {
                "tone": "warning",
                "title": "待问卷积压",
                "body": f"当前有 {questionnaire_pending} 位成员仍停留在待问卷阶段，建议优先到成员运营查看新用户池。",
                "href": f"{url_for('api.admin_automation_conversion_member_ops', stage='new-user', panel='members')}#member-listing",
                "action": "查看新用户池",
            }
        )

    silent_total = int(counts.get("silent_total") or 0)
    if silent_total > 0:
        todo_items.append(
            {
                "tone": "warning",
                "title": "长时间未跟进",
                "body": f"当前沉默池已有 {silent_total} 位成员，可到成员运营继续筛查长期未触达客户。",
                "href": f"{url_for('api.admin_automation_conversion_member_ops', stage='silent', panel='members')}#member-listing",
                "action": "查看沉默池",
            }
        )

    sync_error_message = str(sync_run.get("error_message") or "").strip()
    if not bool(sync_db.get("configured")):
        missing_keys = "、".join(sync_db.get("missing_keys") or [])
        todo_items.append(
            {
                "tone": "danger",
                "title": "同步异常",
                "body": f"消息活跃同步尚未配置{f'，缺少 {missing_keys}' if missing_keys else ''}，当前同步摘要不可靠。",
                "href": f"{url_for('api.admin_automation_conversion_run_center', tab='sync')}#run-sync",
                "action": "查看数据同步",
            }
        )
    elif sync_error_message:
        todo_items.append(
            {
                "tone": "danger",
                "title": "同步异常",
                "body": sync_error_message,
                "href": f"{url_for('api.admin_automation_conversion_run_center', tab='sync')}#run-sync",
                "action": "处理同步异常",
            }
        )

    reply_error_message = str(reply_monitor.get("last_error") or "").strip()
    if reply_error_message:
        todo_items.append(
            {
                "tone": "danger",
                "title": "自动接话异常",
                "body": reply_error_message,
                "href": f"{url_for('api.admin_automation_conversion_run_center', tab='reply-monitor')}#run-reply-monitor",
                "action": "查看接话监控",
            }
        )
    elif int(reply_queue.get("active_total") or 0) > 0:
        todo_items.append(
            {
                "tone": "warning",
                "title": "自动接话待处理",
                "body": f"当前接话队列还有 {int(reply_queue.get('active_total') or 0)} 条待处理记录，建议到运行中心继续观察。",
                "href": f"{url_for('api.admin_automation_conversion_run_center', tab='reply-monitor')}#run-reply-monitor",
                "action": "查看接话监控",
            }
        )

    config_issue_title = ""
    config_issue_body = ""
    if bool(settings_payload.get("questionnaire_missing")):
        config_issue_title = "配置需关注"
        config_issue_body = f"当前已配置问卷 #{settings_payload.get('missing_questionnaire_id') or '-'} 已失效，建议在流程设计重新发布有效规则。"
    elif not str(default_channel.get("qr_url") or "").strip():
        config_issue_title = "配置需关注"
        if settings_payload.get("provider_available"):
            config_issue_body = "默认渠道入口尚未生成二维码，入口发布尚未完成。"
        else:
            config_issue_body = "默认渠道入口还未接入真实二维码 provider，发布前需要补齐接入能力。"
    elif str(default_channel.get("status") or "").strip() not in {"active", ""}:
        config_issue_title = "配置需关注"
        config_issue_body = f"默认渠道入口当前状态为 {default_channel.get('status') or 'unknown'}，建议到流程设计确认发布状态。"
    if config_issue_title:
        todo_items.append(
            {
                "tone": "warning",
                "title": config_issue_title,
                "body": config_issue_body,
                "href": f"{url_for('api.admin_automation_conversion_flow_design', section='publish')}#flow-publish",
                "action": "查看发布管理",
            }
        )

    has_danger = any(item["tone"] == "danger" for item in todo_items)
    has_warning = any(item["tone"] == "warning" for item in todo_items)
    if has_danger:
        current_status = {"label": "存在异常", "tone": "degraded"}
    elif has_warning:
        current_status = {"label": "运行中，需关注", "tone": "staging"}
    else:
        current_status = {"label": "稳定运行", "tone": "healthy"}

    latest_update_candidates = [
        str(sync_run.get("finished_at") or "").strip(),
        str(reply_monitor.get("last_capture_at") or "").strip(),
        str(reply_monitor.get("last_dispatch_at") or "").strip(),
    ]
    latest_update_at = max([item for item in latest_update_candidates if item], default="")

    largest_stage = {}
    if stage_columns:
        largest_stage = max(stage_columns, key=lambda item: int(item.get("total_count") or 0))

    return {
        "todo_items": todo_items,
        "current_status": current_status,
        "latest_update_at": latest_update_at or "暂无记录",
        "largest_stage": largest_stage,
    }


def _build_flow_design_workspace(
    settings_payload: dict[str, object],
    sop_payload: dict[str, object],
    overview_payload: dict[str, object],
) -> dict[str, object]:
    config = dict(settings_payload.get("config") or {})
    selected_questionnaire = dict(settings_payload.get("selected_questionnaire") or {})
    rule_editor = dict(settings_payload.get("rule_editor") or {})
    default_channel = dict(settings_payload.get("default_channel") or {})
    stage_columns = list(overview_payload.get("stage_columns") or [])
    pool_cards = list(sop_payload.get("pool_cards") or [])
    current_pool = dict(sop_payload.get("current_pool") or {})
    current_template = dict(current_pool.get("selected_template") or {})
    current_pool_config = dict(current_pool.get("config") or {})
    enabled_sop_pools = [item for item in pool_cards if item.get("enabled")]

    questionnaire_label = (
        str(selected_questionnaire.get("title") or "").strip()
        or str(selected_questionnaire.get("name") or "").strip()
        or (
            f"问卷 #{config.get('questionnaire_id')}"
            if config.get("questionnaire_id") not in (None, "")
            else ""
        )
    )
    rule_count = len(rule_editor.get("rules") or [])
    channel_status_label = "已生成二维码" if str(default_channel.get("qr_url") or "").strip() else (
        "待生成二维码" if settings_payload.get("provider_available") else "待接入 provider"
    )

    stage_map = {str(item.get("route_key") or ""): item for item in stage_columns}

    def _group_items(*route_keys: str) -> list[dict[str, object]]:
        return [stage_map[key] for key in route_keys if key in stage_map]

    stage_groups = [
        {
            "label": "进入自动化",
            "description": "默认入口或系统入池后，先进入新用户池并等待问卷完成。",
            "summary": "入口触发后先收集问卷，再决定后续分层。",
            "items": _group_items("new-user"),
        },
        {
            "label": "问卷分层",
            "description": "问卷提交后，根据关键题命中与阈值进入普通或重点跟进。",
            "summary": "关键题优先命中，阈值作为补充分层规则。",
            "items": _group_items("inactive-normal", "inactive-focus"),
        },
        {
            "label": "激活推进",
            "description": "消息活跃度变化后，成员推进到已激活池继续执行后续剧本。",
            "summary": "阶段推进依赖活跃结果，但同步动作已下沉到运行中心。",
            "items": _group_items("active-normal", "active-focus"),
        },
        {
            "label": "经营出口",
            "description": "长期无动作进入沉默池，人工确认成交后进入已成交。",
            "summary": "沉默阈值和人工判定共同决定最终去向。",
            "items": _group_items("silent", "won"),
        },
    ]

    flow_relations = [
        "默认入口或系统入池后先进入新用户池，等待问卷完成。",
        "问卷提交后，依据关键题命中结果和分层阈值进入未激活普通池或未激活重点跟进池。",
        "活跃状态更新后，成员推进到激活普通池或激活重点跟进池；同步执行动作已迁到运行中心。",
        "超过沉默阈值进入沉默池；人工确认成交后进入已成交。",
    ]

    publish_issues: list[str] = []
    if not bool(config.get("enabled")):
        publish_issues.append("自动化开关当前关闭")
    if settings_payload.get("questionnaire_missing"):
        publish_issues.append("当前问卷已失效")
    if not questionnaire_label:
        publish_issues.append("尚未选择有效问卷")
    if not enabled_sop_pools:
        publish_issues.append("尚未启用任何 SOP 池")
    if not str(default_channel.get("qr_url") or "").strip():
        publish_issues.append("默认渠道二维码尚未生成")

    draft_tone = "healthy"
    live_tone = "healthy"
    if publish_issues:
        draft_tone = "staging"
        live_tone = "staging"
    if settings_payload.get("questionnaire_missing"):
        draft_tone = "degraded"
        live_tone = "degraded"

    config_summaries = [
        {
            "label": "当前问卷",
            "value": questionnaire_label or "未选择",
            "detail": "先选问卷，再配置关键题和阈值。",
        },
        {
            "label": "关键题规则",
            "value": f"{rule_count} 条",
            "detail": "用于命中重点跟进的业务规则列表。",
        },
        {
            "label": "SOP 生效池",
            "value": f"{len(enabled_sop_pools)}/{len(pool_cards) or 0}",
            "detail": "、".join(str(item.get("pool_label") or "") for item in enabled_sop_pools) or "尚未启用",
        },
        {
            "label": "默认渠道入口",
            "value": channel_status_label,
            "detail": str(default_channel.get("owner_staff_id") or "未设置"),
        },
    ]

    return {
        "current_questionnaire": {
            "label": questionnaire_label or "未选择",
            "rule_count": rule_count,
        },
        "stage_groups": stage_groups,
        "stage_sequence": stage_columns,
        "flow_relations": flow_relations,
        "config_summaries": config_summaries,
        "enabled_sop_pools": enabled_sop_pools,
        "publish": {
            "draft_status": {
                "label": "草稿完整" if not publish_issues else "草稿待校验",
                "tone": draft_tone,
                "detail": "当前页面已预留草稿态结构，发布前应检查问卷、SOP 和默认入口是否齐备。",
            },
            "live_status": {
                "label": "兼容生效中" if not publish_issues else "当前生效配置需关注",
                "tone": live_tone,
                "detail": "当前环境仍采用保存即生效的兼容模式；正式发布/回滚位已在页面结构中预留。",
            },
            "issues": publish_issues,
            "recent_changes": [
                f"当前问卷：{questionnaire_label or '未选择'}",
                f"关键题规则 {rule_count} 条，重点门槛 {config.get('core_threshold') or 0}，Top 门槛 {config.get('top_threshold') or 0}",
                f"SOP 已启用 {len(enabled_sop_pools)}/{len(pool_cards) or 0} 个池子，当前定位在 {current_pool.get('pool_label') or '未知池子'} day{current_pool.get('selected_day_index') or 1}",
                f"默认渠道入口：{channel_status_label}",
            ],
            "history_placeholder": "历史版本、差异对比和回滚接口尚未接通，当前先展示结构占位。",
        },
        "global_summary": {
            "window": str((overview_payload.get("auto_start_window") or {}).get("description") or "未配置"),
            "silent_pool_count": 5,
        },
        "current_sop_context": {
            "pool_label": str(current_pool.get("pool_label") or ""),
            "day_index": int(current_pool.get("selected_day_index") or 1),
            "send_time": str(current_pool_config.get("send_time") or ""),
            "template_enabled": bool(current_template.get("enabled")),
            "template_count": int(current_pool.get("template_count") or 0),
            "recent_execution": dict(current_pool.get("recent_execution") or {}),
        },
    }


def _build_member_ops_workspace(
    stage_payload: dict[str, object],
    overview_payload: dict[str, object],
    send_payload: dict[str, object],
    member_detail: dict[str, object] | None,
    member_debug_payload: dict[str, object] | None,
) -> dict[str, object]:
    stage = dict(stage_payload.get("stage") or {})
    stage_columns = list(overview_payload.get("stage_columns") or [])
    selected_stage_key = str(stage.get("route_key") or "")
    selected_stage = next((item for item in stage_columns if str(item.get("route_key") or "") == selected_stage_key), stage)
    selected_member = dict((member_detail or {}).get("profile") or {})
    selected_member_state = dict((member_detail or {}).get("member") or {})
    latest_manual_action = dict((member_detail or {}).get("latest_manual_action") or {})
    selected_questionnaire = dict((member_detail or {}).get("questionnaire") or {})
    debug_payload = dict(member_debug_payload or {})
    recent_events = list(debug_payload.get("recent_events") or [])
    current_panel = _member_ops_section_from_query("members")

    fixed_follow_type_map = {
        "inactive_focus": {"value": "focus", "label": "重点跟进", "hint": "当前阶段天然属于重点跟进，无需再切换筛选。"},
        "active_focus": {"value": "focus", "label": "重点跟进", "hint": "当前阶段天然属于重点跟进，无需再切换筛选。"},
        "inactive_normal": {"value": "normal", "label": "普通跟进", "hint": "当前阶段天然属于普通跟进，无需再切换筛选。"},
        "active_normal": {"value": "normal", "label": "普通跟进", "hint": "当前阶段天然属于普通跟进，无需再切换筛选。"},
        "new_user": {"value": "", "label": "待问卷分层", "hint": "新用户池还未完成分层，跟进类型筛选暂不可用。"},
        "silent": {"value": "", "label": "混合阶段", "hint": "沉默池可能混合普通与重点客户，细筛能力暂保留结构占位。"},
        "won": {"value": "", "label": "已成交", "hint": "已成交阶段不再按跟进类型操作，筛选位先保留结构占位。"},
    }
    follow_type_state = fixed_follow_type_map.get(str(stage.get("pool") or ""), {"value": "", "label": "全部", "hint": "更细跟进类型筛选暂未接通，当前先保留结构占位。"})

    matched_questions = [str(item).strip() for item in list(selected_questionnaire.get("matched_questions") or []) if str(item).strip()]
    decision_source_label = str(selected_member_state.get("decision_source_label") or "").strip() or "系统判定"
    follow_type_label = str(selected_member_state.get("follow_type_label") or "").strip() or "待判定"
    questionnaire_result_label = str(selected_questionnaire.get("result_label") or "").strip() or "未形成结果"
    if matched_questions:
        questionnaire_reason = f"命中 {len(matched_questions)} 条关键题：{'、'.join(matched_questions)}。当前按 {follow_type_label} 推进，判定来源为 {decision_source_label}。"
    elif questionnaire_result_label not in {"未知", "未形成结果"}:
        questionnaire_reason = f"当前问卷结果为 {questionnaire_result_label}，按 {follow_type_label} 推进，判定来源为 {decision_source_label}。"
    else:
        questionnaire_reason = f"当前尚未形成稳定分层结果，判定来源为 {decision_source_label}。"

    stage_pool = str(stage.get("pool") or "").strip()
    allow_follow_type_actions = stage_pool != "won"
    row_can_set_focus = allow_follow_type_actions and stage_pool not in {"inactive_focus", "active_focus"}
    row_can_set_normal = allow_follow_type_actions and stage_pool not in {"inactive_normal", "active_normal"}

    current_panel_href = "send" if current_panel == "send" else "members"
    customers = []
    for item in list(stage_payload.get("customers") or []):
        external_userid = str(item.get("external_userid") or "").strip()
        mobile = str(item.get("mobile") or "").strip()
        member_query = external_userid or mobile
        customers.append(
            {
                **item,
                "detail_href": url_for(
                    "api.admin_automation_conversion_member_ops",
                    stage=stage.get("route_key"),
                    panel="members",
                    keyword=(stage_payload.get("filters") or {}).get("keyword"),
                    offset=(stage_payload.get("pagination") or {}).get("offset"),
                    limit=(stage_payload.get("pagination") or {}).get("limit"),
                    member=member_query,
                ) + "#member-detail",
                "batch_href": url_for(
                    "api.admin_automation_conversion_member_ops",
                    stage=stage.get("route_key"),
                    panel="send",
                    member=member_query,
                ) + "#member-batch",
                "status_tags": [str(item.get("current_stage_label") or "").strip(), str(item.get("current_target_label") or "").strip()],
                "can_set_focus": row_can_set_focus,
                "can_set_normal": row_can_set_normal,
            }
        )

    current_panel_summary = {
        "label": "批量动作与触达" if str(send_payload.get("mode") or "") == "focus_ai" else "成员列表与单客动作",
        "detail": "当前阶段为重点池，批量动作会创建 AI 批任务。" if str(send_payload.get("mode") or "") == "focus_ai" else "当前阶段支持官方群发预览和单客手动干预。",
    }

    return {
        "current_panel": current_panel,
        "stage_summary": {
            "label": str(stage.get("label") or ""),
            "description": str(stage.get("description") or ""),
            "total_count": int(selected_stage.get("total_count") or 0),
            "today_new_count": int(selected_stage.get("today_new_count") or 0),
        },
        "filters": {
            "keyword": str((stage_payload.get("filters") or {}).get("keyword") or ""),
            "follow_type": follow_type_state,
            "status_placeholder": "状态筛选占位",
            "reset_href": url_for("api.admin_automation_conversion_member_ops", stage=stage.get("route_key"), panel="members"),
        },
        "customer_rows": customers,
        "stage_metrics": [
            {
                "label": "当前总人数",
                "value": int(selected_stage.get("total_count") or 0),
                "detail": f"{stage.get('label') or '当前阶段'}内全部成员数量。",
            },
            {
                "label": "今日新增",
                "value": int(selected_stage.get("today_new_count") or 0),
                "detail": "今天新进入当前阶段的成员数量。",
            },
            {
                "label": "重点跟进",
                "value": int(selected_stage.get("focus_count") or 0),
                "detail": "当前阶段内判定为重点跟进的成员。",
            },
            {
                "label": "普通跟进",
                "value": int(selected_stage.get("normal_count") or 0),
                "detail": "当前阶段内按普通跟进推进的成员。",
            },
        ],
        "selection_summary": {
            "selected_member_name": str(selected_member.get("customer_name") or "").strip() or "未选中成员",
            "selected_member_phone": str(selected_member.get("phone") or "").strip() or "暂无",
            "selected_member_external_contact_id": str(selected_member.get("external_contact_id") or "").strip() or "暂无",
            "selected_member_owner": str(selected_member.get("owner_display_name") or selected_member.get("owner_staff_id") or "").strip() or "暂无",
            "selected_member_pool": str(selected_member_state.get("current_pool_label") or "").strip() or "暂无",
            "selected_member_stage": str(selected_member_state.get("current_stage_label") or "").strip() or "暂无",
            "selected_member_target": str(selected_member_state.get("current_target_label") or "").strip() or "暂无",
            "selected_member_follow_type": str(selected_member_state.get("follow_type_label") or "").strip() or "暂无",
            "latest_manual_action": (
                f"{latest_manual_action.get('action_label') or latest_manual_action.get('action')} · {latest_manual_action.get('created_at') or '暂无时间'}"
                if latest_manual_action
                else "暂无人工动作"
            ),
        },
        "current_panel_summary": current_panel_summary,
        "member_detail_summary": {
            "manual_override_preferred": bool(str(selected_member_state.get("decision_source") or "").strip() == "manual"),
            "questionnaire_reason": questionnaire_reason,
            "matched_questions": matched_questions,
            "recent_events": recent_events,
            "recent_event_count": len(recent_events),
            "detail_lookup_query": str(selected_member.get("external_contact_id") or selected_member.get("phone") or "").strip(),
        },
        "batch_summary": {
            "mode": str(send_payload.get("mode") or ""),
            "label": "AI 批量处理" if str(send_payload.get("mode") or "") == "focus_ai" else "普通阶段触达",
            "description": "当前阶段属于重点池，点击后会创建 AI 批任务并按节奏推进。" if str(send_payload.get("mode") or "") == "focus_ai" else "当前阶段支持文本 / 图片官方群发，可先预览再确认发送。",
            "status_actions_placeholder": [
                "批量设重点",
                "批量设普通",
                "批量移池",
                "批量标记成交",
            ],
        },
        "stage_action_hints": [
            "先按阶段切换工作上下文，再在当前阶段内搜索和筛选成员。",
            "单成员详情与手动干预留在当前工作面，不需要跳去独立页面。",
            "批量触达继续复用现有接口，但已经收口到成员运营工作台。",
            "批量状态动作当前先做结构占位，不伪装成已接通的批量写接口。",
        ],
        "current_panel_href": current_panel_href,
    }


def _build_run_center_workspace(
    settings_payload: dict[str, object],
    overview_payload: dict[str, object],
    model_infra_payload: dict[str, object],
    orchestration_payload: dict[str, object],
    debug_payload: dict[str, object] | None,
    sop_batches_payload: dict[str, object],
    focus_batches_payload: dict[str, object],
) -> dict[str, object]:
    sync_payload = dict(settings_payload.get("message_activity_sync") or {})
    sync_db = dict(sync_payload.get("db_status") or {})
    sync_run = dict(sync_payload.get("last_run") or {})
    reply_monitor = dict(overview_payload.get("reply_monitor") or {})
    reply_queue = dict(reply_monitor.get("queue_counts") or {})
    deepseek = dict(model_infra_payload.get("deepseek") or {})
    model_logs = list(model_infra_payload.get("logs") or [])
    orchestration = dict(orchestration_payload or {})
    orchestration_router = dict((orchestration.get("router") or {}).get("config") or {})
    orchestration_agents = list((orchestration.get("agents") or {}).get("items") or [])
    orchestration_outputs = dict(orchestration.get("outputs") or {})
    sop_batches = list(sop_batches_payload.get("batches") or [])
    focus_batches = list(focus_batches_payload.get("batches") or [])
    debug = dict(debug_payload or {})
    debug_lookup = dict(debug.get("lookup") or {})
    debug_events = list(debug.get("recent_events") or [])

    sync_status = str(sync_run.get("status_label") or "").strip() or ("未配置" if not sync_db.get("configured") else "暂无记录")
    reply_status = str(reply_monitor.get("status_label") or "").strip() or ("已开启" if reply_monitor.get("enabled") else "已关闭")
    model_status = "已启用" if deepseek.get("enabled") else "未启用"
    router_status = str(orchestration_router.get("last_status") or "").strip() or ("enabled" if orchestration_router.get("enabled") else "disabled")
    debug_status = "已选择成员" if debug_lookup.get("external_contact_id") or debug_lookup.get("phone") else "待输入成员"
    audit_summary = f"SOP {len(sop_batches)} 条 / AI 批次 {len(focus_batches)} 条 / Agent 输出 {int(orchestration_outputs.get('total') or 0)} 条"

    attention_items: list[dict[str, str]] = []
    if not bool(sync_db.get("configured")):
        missing_keys = "、".join(str(item) for item in (sync_db.get("missing_keys") or []) if str(item).strip())
        attention_items.append(
            {
                "tone": "danger",
                "title": "数据同步尚未配置",
                "body": f"消息活跃同步还不能稳定运行{f'，缺少 {missing_keys}' if missing_keys else ''}。",
                "href": url_for('api.admin_automation_conversion_run_center', tab='sync'),
                "action": "处理数据同步",
            }
        )
    elif str(sync_run.get("error_message") or "").strip():
        attention_items.append(
            {
                "tone": "danger",
                "title": "最近一次同步失败",
                "body": str(sync_run.get("error_message") or "").strip(),
                "href": url_for('api.admin_automation_conversion_run_center', tab='sync'),
                "action": "查看同步明细",
            }
        )

    if str(reply_monitor.get("last_error") or "").strip():
        attention_items.append(
            {
                "tone": "danger",
                "title": "自动接话异常",
                "body": str(reply_monitor.get("last_error") or "").strip(),
                "href": url_for('api.admin_automation_conversion_run_center', tab='reply-monitor'),
                "action": "查看监控队列",
            }
        )
    elif int(reply_queue.get("active_total") or 0) > 0:
        attention_items.append(
            {
                "tone": "warning",
                "title": "自动接话仍有待处理队列",
                "body": f"当前还有 {int(reply_queue.get('active_total') or 0)} 条待处理记录，建议继续观察 capture / dispatch 结果。",
                "href": f"{url_for('api.admin_automation_conversion_run_center', tab='reply-monitor')}#run-reply-monitor",
                "action": "查看接话监控",
            }
        )

    if not bool(deepseek.get("enabled")):
        attention_items.append(
            {
                "tone": "warning",
                "title": "模型基础设施未启用",
                "body": "DeepSeek 当前关闭，涉及模型路由和执行 Agent 的能力不会真实生效。",
                "href": url_for('api.admin_automation_conversion_run_center', tab='model-infra'),
                "action": "查看模型配置",
            }
        )
    if orchestration_router.get("enabled") and router_status not in {"success", "never_called"}:
        attention_items.append(
            {
                "tone": "warning" if router_status != "http_error" else "danger",
                "title": "中央路由接入需关注",
                "body": str(orchestration_router.get("last_error") or f"最近一次路由状态为 {router_status}"),
                "href": url_for('api.admin_automation_conversion_run_center', tab='agent-orchestration', subtab='router'),
                "action": "查看路由接入",
            }
        )

    failed_log_items: list[dict[str, str]] = []
    for batch in sop_batches:
        if str(batch.get("status") or "").strip() == "failed":
            failed_log_items.append(
                {
                    "tone": "danger",
                    "title": "SOP 执行失败",
                    "body": f"{batch.get('pool_label') or batch.get('pool_key') or '未知池子'} day{batch.get('day_index') or '-'} 批次失败，时间 {batch.get('scheduled_for') or batch.get('created_at') or '暂无记录'}。",
                }
            )
    for batch in focus_batches:
        if int(batch.get("failed_count") or 0) > 0:
            failed_log_items.append(
                {
                    "tone": "warning",
                    "title": "AI 批任务存在失败",
                    "body": f"{batch.get('stage_key') or '未知阶段'} 批次失败 {batch.get('failed_count') or 0} 条，状态 {batch.get('status_label') or batch.get('status') or '未知'}。",
                }
            )
    if str(sync_run.get("error_message") or "").strip():
        failed_log_items.append(
            {
                "tone": "danger",
                "title": "同步任务失败",
                "body": str(sync_run.get("error_message") or "").strip(),
            }
        )

    has_danger = any(item["tone"] == "danger" for item in attention_items)
    has_warning = any(item["tone"] == "warning" for item in attention_items)
    if has_danger:
        current_status = {"label": "存在阻塞项", "tone": "degraded"}
    elif has_warning:
        current_status = {"label": "运行中，需关注", "tone": "staging"}
    else:
        current_status = {"label": "运行稳定", "tone": "healthy"}

    latest_update_candidates = [
        str(sync_run.get("finished_at") or "").strip(),
        str(reply_monitor.get("last_capture_at") or "").strip(),
        str(reply_monitor.get("last_dispatch_at") or "").strip(),
        str(deepseek.get("updated_at") or "").strip(),
        str(model_logs[0].get("created_at") or "").strip() if model_logs else "",
    ]
    latest_update_at = max([item for item in latest_update_candidates if item], default="暂无记录")

    section_tabs = [
        {
            "key": "overview",
            "tab": "overview",
            "label": "运行概况",
            "badge": current_status["label"],
            "detail": "先看同步、监控、模型和调试整体是否健康，再决定要进入哪个处理区。",
            "href": f"{url_for('api.admin_automation_conversion_run_center', tab='overview')}#run-overview",
        },
        {
            "key": "sync",
            "tab": "sync",
            "label": "数据同步",
            "badge": sync_status,
            "detail": "消息活跃同步配置、最近运行记录和同步明细都收口在这里。",
            "href": f"{url_for('api.admin_automation_conversion_run_center', tab='sync')}#run-sync",
        },
        {
            "key": "reply_monitor",
            "tab": "reply-monitor",
            "label": "自动接话监控",
            "badge": reply_status,
            "detail": "监控开关、扫描、放行和队列状态统一放在同一个监控面板。",
            "href": f"{url_for('api.admin_automation_conversion_run_center', tab='reply-monitor')}#run-reply-monitor",
        },
        {
            "key": "agent_orchestration",
            "tab": "agent-orchestration",
            "label": "Agent Orchestration",
            "badge": f"{len(orchestration_agents)} 个子 Agent / {int(orchestration_outputs.get('total') or 0)} 条输出",
            "detail": "统一维护龙虾路由接入、Skill Registry、子 Agent 配置、回放调试和输出账本。",
            "href": f"{url_for('api.admin_automation_conversion_run_center', tab='agent-orchestration', subtab='router')}#run-agent-orchestration",
        },
        {
            "key": "model",
            "tab": "model-infra",
            "label": "AI / 模型基础设施",
            "badge": model_status,
            "detail": "保留 DeepSeek 纯配置和模型调用日志兼容入口；Agent 编排已迁到独立子区。",
            "href": f"{url_for('api.admin_automation_conversion_run_center', tab='model-infra')}#run-model",
        },
        {
            "key": "debug",
            "tab": "debug",
            "label": "单客调试",
            "badge": debug_status,
            "detail": "通过 external_contact_id 或手机号查看成员实时状态和最近事件。",
                "href": url_for('api.admin_automation_conversion_run_center', tab='debug'),
        },
        {
            "key": "logs",
            "tab": "logs",
            "label": "执行日志 / 审计",
            "badge": f"{len(sop_batches)} 条 SOP / {len(focus_batches)} 条 AI 批次",
            "detail": "汇总最近 SOP 执行、AI 批任务、同步记录和失败提示，统一承接运行日志视图。",
                "href": url_for('api.admin_automation_conversion_run_center', tab='logs'),
        },
    ]

    overview_health_cards = [
        {
            "title": "消息活跃同步",
            "value": sync_status,
            "detail": f"最近完成：{sync_run.get('finished_at') or '暂无记录'}",
            "meta": f"更新 {sync_run.get('updated_count') or 0} 人，跳过 {(sync_run.get('skipped_count') or 0)} 人。",
            "href": f"{url_for('api.admin_automation_conversion_run_center', tab='sync')}#run-sync",
            "action": "进入数据同步",
        },
        {
            "title": "自动接话监控",
            "value": reply_status,
            "detail": f"待处理队列 {reply_queue.get('active_total') or 0} 条，最近扫描 {reply_monitor.get('last_capture_at') or '暂无记录'}",
            "meta": f"最近放行：{reply_monitor.get('last_dispatch_at') or '暂无记录'}",
            "href": f"{url_for('api.admin_automation_conversion_run_center', tab='reply-monitor')}#run-reply-monitor",
            "action": "进入接话监控",
        },
        {
            "title": "AI 模型",
            "value": model_status,
            "detail": f"Router：{deepseek.get('router_model') or '-'} / Execution：{deepseek.get('execution_model') or '-'}",
            "meta": f"最近模型日志：{model_logs[0].get('created_at') if model_logs else '暂无记录'}",
            "href": f"{url_for('api.admin_automation_conversion_run_center', tab='model-infra')}#run-model",
            "action": "进入模型配置",
        },
        {
            "title": "Agent 编排",
            "value": router_status,
            "detail": f"子 Agent {len(orchestration_agents)} 个，最近输出 {int(orchestration_outputs.get('total') or 0)} 条。",
            "meta": f"最近路由错误：{orchestration_router.get('last_error') or '无'}",
            "href": f"{url_for('api.admin_automation_conversion_run_center', tab='agent-orchestration', subtab='router')}#run-agent-orchestration",
            "action": "进入 Agent 编排",
        },
        {
            "title": "关键任务执行",
            "value": "存在失败任务" if failed_log_items else "暂无失败任务",
            "detail": f"SOP {len(sop_batches)} 条，AI 批任务 {len(focus_batches)} 条，最近同步 {sync_status}",
            "meta": failed_log_items[0]["title"] if failed_log_items else "最近没有新的失败提示",
            "href": f"{url_for('api.admin_automation_conversion_run_center', tab='logs')}#run-logs",
            "action": "查看执行日志",
        },
    ]

    sop_failed_count = sum(1 for batch in sop_batches if str(batch.get("status") or "").strip() == "failed")
    focus_failed_count = sum(1 for batch in focus_batches if int(batch.get("failed_count") or 0) > 0)

    logs_summary_cards = [
        {
            "label": "最近 SOP 执行摘要",
            "value": f"{len(sop_batches)} 条",
            "detail": f"失败 {sop_failed_count} 条，最近一条 {sop_batches[0].get('status_label') if sop_batches else '暂无记录'}",
        },
        {
            "label": "最近 AI 批任务摘要",
            "value": f"{len(focus_batches)} 条",
            "detail": f"存在失败的批次 {focus_failed_count} 条，最近一条 {focus_batches[0].get('status_label') if focus_batches else '暂无记录'}",
        },
        {
            "label": "最近同步任务摘要",
            "value": sync_status,
            "detail": f"最近完成：{sync_run.get('finished_at') or '暂无记录'}",
        },
        {
            "label": "最近失败任务提示",
            "value": str(len(failed_log_items)),
            "detail": failed_log_items[0]["title"] if failed_log_items else "当前没有失败提示",
        },
    ]

    summary_items = [
        {"label": "当前状态", "value": current_status["label"]},
        {"label": "最近更新时间", "value": latest_update_at},
        {"label": "当前调试对象", "value": str(debug_lookup.get("external_contact_id") or debug_lookup.get("phone") or "未选择成员")},
        {"label": "审计概览", "value": audit_summary},
    ]

    operation_hints = [
        "业务规则和发布动作留在流程设计，运行中心只承接同步、监控、模型和调试。",
        "旧 model-infra、debug 页面已并入这里；旧入口仍可访问，但最终都会落到当前工作台。",
        "执行日志当前优先复用 SOP batch、AI batch、同步记录；全链路统一检索仍是结构占位。",
    ]

    return {
        "current_status": current_status,
        "latest_update_at": latest_update_at,
        "audit_summary": audit_summary,
        "section_tabs": section_tabs,
        "overview_health_cards": overview_health_cards,
        "summary_items": summary_items,
        "attention_items": attention_items,
        "operation_hints": operation_hints,
        "sync_status": sync_status,
        "reply_status": reply_status,
        "model_status": model_status,
        "debug_status": debug_status,
        "logs_summary_cards": logs_summary_cards,
        "agent_orchestration_summary": {
            "router_status": router_status,
            "agent_count": len(orchestration_agents),
            "output_count": int(orchestration_outputs.get("total") or 0),
        },
        "logs_payload": {
            "sop_batches": sop_batches,
            "focus_batches": focus_batches,
            "sync_run": sync_run,
            "sync_items": list(sync_payload.get("recent_items") or []),
            "failed_items": failed_log_items,
        },
        "placeholder_notes": {
            "audit": "全量执行链路历史、聚合检索和版本化审计尚未接通，当前先展示真实可用的 SOP batch、AI batch、同步记录与失败提示。",
        },
    }


def _automation_conversion_workspace_tabs(active_key: str) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for item in _AUTOMATION_CONVERSION_WORKSPACE_TABS:
        items.append(
            {
                **item,
                "href": url_for(str(item["endpoint"]), **dict(item.get("params") or {})),
                "active": item["key"] == active_key,
            }
        )
    return items


def _wants_json_response() -> bool:
    accept = str(request.headers.get("Accept") or "").lower()
    requested_with = str(request.headers.get("X-Requested-With") or "").strip()
    return "application/json" in accept or requested_with == "XMLHttpRequest"


def _json_bool(value) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _parse_sop_images_payload(raw_payload) -> list[dict[str, str]]:
    if isinstance(raw_payload, str):
        text = raw_payload.strip()
        if text.startswith("["):
            try:
                raw_payload = json.loads(text)
            except ValueError:
                raw_payload = text
    if isinstance(raw_payload, list):
        results: list[dict[str, str]] = []
        for item in raw_payload:
            if isinstance(item, str):
                media_id = item.strip()
                if media_id:
                    results.append({"media_id": media_id})
                continue
            if not isinstance(item, dict):
                continue
            media_id = str(item.get("media_id") or item.get("image_media_id") or "").strip()
            data_url = str(item.get("data_url") or "").strip()
            data_base64 = str(item.get("data_base64") or item.get("base64") or "").strip()
            file_name = str(item.get("file_name") or item.get("name") or "").strip()
            content_type = str(item.get("content_type") or item.get("mime_type") or "").strip()
            if media_id:
                results.append({"media_id": media_id, "file_name": file_name, "content_type": content_type})
            elif data_url or data_base64:
                payload = {
                    "file_name": file_name,
                    "content_type": content_type,
                }
                if data_url:
                    payload["data_url"] = data_url
                if data_base64:
                    payload["data_base64"] = data_base64
                results.append(payload)
        return results
    return [{"media_id": media_id} for media_id in _split_multiline_tokens(str(raw_payload or ""))]


def _apply_settings_form_overrides(payload: dict[str, object]) -> dict[str, object]:
    config = dict(payload.get("config") or {})
    questionnaire_catalog = dict(payload.get("questionnaire_rule_catalog") or {})
    existing_missing = bool(payload.get("questionnaire_missing"))
    existing_missing_questionnaire_id = payload.get("missing_questionnaire_id")
    questionnaire_id_text = str(request.form.get("questionnaire_id") or "").strip()
    config.update(
        {
            "enabled": str(request.form.get("enabled") or "").strip().lower() in {"1", "true", "yes", "on"},
            "questionnaire_id": questionnaire_id_text or None,
            "core_threshold": str(request.form.get("core_threshold") or "").strip(),
            "top_threshold": str(request.form.get("top_threshold") or "").strip(),
            "day_start_hour": str(request.form.get("day_start_hour") or "").strip(),
            "quiet_hour_start": str(request.form.get("quiet_hour_start") or "").strip(),
            "timezone": str(request.form.get("timezone") or "").strip(),
            "silent_threshold_days_by_pool": {
                "new_user": str(request.form.get("silent_threshold_new_user") or "").strip(),
                "inactive_normal": str(request.form.get("silent_threshold_inactive_normal") or "").strip(),
                "inactive_focus": str(request.form.get("silent_threshold_inactive_focus") or "").strip(),
                "active_normal": str(request.form.get("silent_threshold_active_normal") or "").strip(),
                "active_focus": str(request.form.get("silent_threshold_active_focus") or "").strip(),
            },
        }
    )
    default_channel = dict(payload.get("default_channel") or {})
    default_channel.update(
        {
            "welcome_message": str(request.form.get("welcome_message") or "").strip(),
            "auto_accept_friend": str(request.form.get("auto_accept_friend") or "").strip().lower() in {"1", "true", "yes", "on"},
        }
    )
    payload["default_channel"] = default_channel
    selected_catalog_item = questionnaire_catalog.get(questionnaire_id_text) if questionnaire_id_text else None
    payload["config"] = config
    payload["selected_questionnaire"] = selected_catalog_item
    payload["questionnaire_missing"] = bool(questionnaire_id_text and selected_catalog_item is None) or (existing_missing and not questionnaire_id_text)
    payload["missing_questionnaire_id"] = (
        int(questionnaire_id_text)
        if questionnaire_id_text and payload["questionnaire_missing"] and questionnaire_id_text.isdigit()
        else existing_missing_questionnaire_id
    )
    payload["rule_editor"] = {
        **dict(payload.get("rule_editor") or {}),
        "selected_questionnaire_id": questionnaire_id_text,
        "selected_questionnaire": selected_catalog_item,
        "rules_invalidated": bool(payload["questionnaire_missing"]),
    }
    return payload


def _stage_send_payload(stage_key: str, *, stage_payload: dict[str, object] | None = None) -> dict[str, object]:
    payload = stage_payload
    if payload is None:
        try:
            payload = get_stage_detail_payload(
                route_key=stage_key,
                keyword="",
                offset=0,
                limit=20,
            )
        except ValueError:
            return {}
    send_mode = _stage_send_mode(payload)
    return {
        "stage_payload": payload,
        "send_payload": {
            "mode": send_mode,
            "manual_send_url": url_for("api.api_admin_automation_conversion_stage_manual_send", stage_key=stage_key),
            "manual_send_preview_url": url_for("api.api_admin_automation_conversion_stage_manual_send_preview", stage_key=stage_key),
            "manual_send_form_action": url_for("api.admin_automation_conversion_stage_send_submit", stage_key=stage_key),
            "focus_send_batches_url": url_for("api.api_admin_automation_conversion_stage_focus_send_batches", stage_key=stage_key),
            "focus_send_batches_form_action": url_for("api.admin_automation_conversion_stage_send_submit", stage_key=stage_key),
            "focus_send_batch_detail_url_template": "/api/admin/automation-conversion/focus-send-batches/<batch_id>",
            "form": {
                "content": str(request.form.get("content") or "").strip(),
                "image_media_ids": request.form.get("image_media_ids", ""),
                "operator": str(request.form.get("operator") or "").strip(),
            },
        },
    }


def _render_invalid_stage_page():
    return _render_admin_template(
        "placeholder.html",
        active_nav="automation_conversion",
        page_title="阶段不存在",
        page_summary="当前阶段不存在，请返回成员运营重新选择。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("自动化转化", url_for("api.admin_automation_conversion")),
            ("成员运营", url_for("api.admin_automation_conversion_member_ops")),
            ("阶段不存在", None),
        ),
        actions=[{"label": "返回成员运营", "href": url_for("api.admin_automation_conversion_member_ops"), "variant": "secondary"}],
        state_title="阶段不存在",
        state_body="请检查链接是否正确。",
        state_items=["支持查看：新用户池、未激活普通池、未激活重点跟进池、激活普通池、激活重点跟进池、沉默池、已成交。"],
        page_error="未找到对应阶段",
    ), 404


def _render_overview_page(*, overview_payload: dict[str, object] | None = None, page_error: str = ""):
    payload = overview_payload or get_overview_payload()
    settings_payload = get_settings_payload()
    return _render_admin_template(
        "automation_conversion_overview_workspace.html",
        active_nav="automation_conversion",
        page_title="自动化转化",
        page_summary="这是自动化转化的经营驾驶舱，只展示经营结果、阶段卡点、异常待办和最近运行摘要。",
        breadcrumbs=_breadcrumb_items(("客户管理后台", url_for("api.admin_console_home")), ("自动化转化", None)),
        overview_payload=payload,
        settings_payload=settings_payload,
        overview_dashboard=_build_overview_dashboard(payload, settings_payload),
        page_notice=_overview_notice(),
        page_error=page_error,
        show_shell_meta=False,
    )


def _render_flow_design_page(
    *,
    settings_payload: dict[str, object] | None = None,
    sop_payload: dict[str, object] | None = None,
    question_rules_json: str | None = None,
    page_error: str = "",
    entry_section: str = "rules",
):
    resolved_entry_section = _flow_design_section_from_query(entry_section)
    settings = settings_payload or get_settings_payload()
    selected_day_index = _query_int("day", default=1, minimum=1, maximum=365)
    sop = sop_payload or get_sop_v1_management_payload(selected_pool_key=_query_text("pool"), selected_day_index=selected_day_index)
    overview = get_overview_payload()
    return _render_admin_template(
        "automation_conversion_flow_design_workspace.html",
        active_nav="automation_conversion",
        page_title="流程设计",
        page_summary="把规则、问卷、SOP、全局规则和渠道入口收敛到一个配置工作台，避免来回跳页。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("自动化转化", url_for("api.admin_automation_conversion")),
            ("流程设计", None),
        ),
        workspace_tabs=_automation_conversion_workspace_tabs("flow_design"),
        flow_design_entry_section=resolved_entry_section,
        flow_design_workspace=_build_flow_design_workspace(settings, sop, overview),
        overview_payload=overview,
        settings_payload=settings,
        question_rules_json=question_rules_json
        if question_rules_json is not None
        else json.dumps((settings.get("rule_editor") or {}).get("rules") or [], ensure_ascii=False, indent=2),
        show_debug_json_editor=_query_text("debug") == "1",
        sop_payload=sop,
        page_notice=_settings_notice() or _sop_page_notice(),
        page_error=page_error,
        admin_action_token=ensure_admin_console_action_token(),
    )


def _load_member_ops_detail() -> dict[str, object] | None:
    external_contact_id = _query_text("member") or _query_text("external_contact_id")
    phone = _query_text("phone")
    if not external_contact_id and not phone:
        return None
    return get_member_detail(external_contact_id=external_contact_id, phone=phone)


def _load_member_ops_debug(member_detail: dict[str, object] | None) -> dict[str, object] | None:
    if not member_detail:
        return None
    profile = dict(member_detail.get("profile") or {})
    external_contact_id = str(profile.get("external_contact_id") or "").strip()
    phone = str(profile.get("phone") or "").strip()
    if not external_contact_id and not phone:
        return None
    return get_debug_payload(external_contact_id=external_contact_id, phone=phone)


def _member_action_urls() -> dict[str, str]:
    return {
        "put_in_pool": url_for("api.api_admin_automation_conversion_put_in_pool"),
        "remove_from_pool": url_for("api.api_admin_automation_conversion_remove_from_pool"),
        "set_focus": url_for("api.api_admin_automation_conversion_set_focus"),
        "set_normal": url_for("api.api_admin_automation_conversion_set_normal"),
        "mark_won": url_for("api.api_admin_automation_conversion_mark_won"),
        "unmark_won": url_for("api.api_admin_automation_conversion_unmark_won"),
        "push_openclaw": url_for("api.api_admin_automation_conversion_push_openclaw"),
    }


def _member_ops_query_send_result() -> dict[str, object]:
    if not _query_text("manual_send_notice"):
        return {}
    task_ids = []
    for item in _query_text("manual_send_task_ids").split(","):
        item = item.strip()
        if item.isdigit():
            task_ids.append(int(item))
    return {
        "status": _query_text("manual_send_status") or "unknown",
        "total_target_count": _query_int("manual_send_total", default=0, minimum=0, maximum=100000),
        "sent_count": _query_int("manual_send_sent", default=0, minimum=0, maximum=100000),
        "skipped_count": _query_int("manual_send_skipped", default=0, minimum=0, maximum=100000),
        "record_id": _query_int("manual_send_record_id", default=0, minimum=0, maximum=100000000) or None,
        "task_ids": task_ids,
    }


def _member_ops_query_focus_batch() -> dict[str, object]:
    batch_id = _query_int("focus_batch_id", default=0, minimum=0, maximum=100000000)
    if batch_id <= 0:
        return {}
    try:
        return get_focus_send_batch_detail(batch_id=batch_id)
    except LookupError:
        return {}


def _render_member_ops_page(
    stage_key: str = "",
    *,
    page_notice: str = "",
    page_error: str = "",
    send_result: dict[str, object] | None = None,
    focus_batch: dict[str, object] | None = None,
    entry_section: str = "members",
):
    resolved_entry_section = _member_ops_section_from_query(entry_section)
    selected_stage_key = _normalize_stage_key(stage_key or _query_text("stage") or "new-user") or "new-user"
    try:
        stage_payload = get_stage_detail_payload(
            route_key=selected_stage_key,
            keyword=_query_text("keyword"),
            offset=_query_int("offset", default=0, minimum=0, maximum=100000),
            limit=_query_int("limit", default=50, minimum=1, maximum=100),
        )
    except ValueError:
        return _render_invalid_stage_page()
    send_bundle = _stage_send_payload(selected_stage_key, stage_payload=stage_payload)
    overview = get_overview_payload()
    member_detail = _load_member_ops_detail()
    member_debug = _load_member_ops_debug(member_detail)
    send_payload = send_bundle.get("send_payload") or {}
    effective_send_result = send_result or _member_ops_query_send_result()
    effective_focus_batch = focus_batch or _member_ops_query_focus_batch()
    return _render_admin_template(
        "automation_conversion_member_ops_workspace.html",
        active_nav="automation_conversion",
        page_title="成员运营",
        page_summary=f"围绕 {stage_payload['stage']['label']} 在一个工作面内连续完成看名单、看详情、做动作和批量触达。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("自动化转化", url_for("api.admin_automation_conversion")),
            ("成员运营", None),
        ),
        workspace_tabs=_automation_conversion_workspace_tabs("member_ops"),
        member_ops_entry_section=resolved_entry_section,
        member_ops_workspace=_build_member_ops_workspace(
            stage_payload=stage_payload,
            overview_payload=overview,
            send_payload=send_payload,
            member_detail=member_detail,
            member_debug_payload=member_debug,
        ),
        overview_payload=overview,
        stage_payload=stage_payload,
        send_payload=send_payload,
        send_result=effective_send_result,
        focus_batch=effective_focus_batch,
        member_detail=member_detail,
        member_debug_payload=member_debug,
        member_action_urls=_member_action_urls(),
        member_ops_base_url=url_for("api.admin_automation_conversion_member_ops"),
        page_notice=page_notice or _member_ops_notice(),
        page_error=page_error,
        admin_action_token=ensure_admin_console_action_token(),
    )


def _render_run_center_page(
    *,
    settings_payload: dict[str, object] | None = None,
    model_infra_payload: dict[str, object] | None = None,
    orchestration_payload: dict[str, object] | None = None,
    overview_payload: dict[str, object] | None = None,
    debug_payload: dict[str, object] | None = None,
    page_error: str = "",
    entry_section: str = "overview",
):
    resolved_entry_section = _run_center_section_from_query(entry_section)
    orchestration_default_subtab = str((orchestration_payload or {}).get("subtab") or "router").strip() or "router"
    resolved_subtab = _run_center_subtab_from_query(orchestration_default_subtab)
    default_scripts_only = (
        resolved_subtab == "outputs"
        and not any(
            [
                _query_text("output_id"),
                _query_text("request_id"),
                _query_text("batch_id"),
                _query_text("external_contact_id"),
                _query_text("userid"),
                _query_text("agent_code"),
                _query_text("output_type"),
                _query_text("current_pool"),
                _query_text("target_pool"),
                _query_text("applied_status"),
                _query_text("date_from"),
                _query_text("date_to"),
                _query_text("min_confidence"),
                _query_text("max_confidence"),
                _query_text("has_error") or _query_text("is_error"),
            ]
        )
    )
    settings = settings_payload or get_settings_payload()
    overview = overview_payload or get_overview_payload()
    model_infra = model_infra_payload or get_model_infra_payload()
    orchestration = orchestration_payload or get_agent_orchestration_payload(
        subtab=resolved_subtab,
        agent_code=_query_text("agent"),
        skill_code=_query_text("skill"),
        output_id=_query_text("output_id"),
        run_id=_query_text("run_id"),
        request_id=_query_text("request_id"),
        batch_id=_query_text("batch_id"),
        external_contact_id=_query_text("external_contact_id"),
        userid=_query_text("userid"),
        date_from=_query_text("date_from"),
        date_to=_query_text("date_to"),
        output_type=_query_text("output_type"),
        current_pool=_query_text("current_pool"),
        target_pool=_query_text("target_pool"),
        applied_status=_query_text("applied_status"),
        min_confidence=_query_text("min_confidence"),
        max_confidence=_query_text("max_confidence"),
        has_error=_query_text("has_error") or _query_text("is_error"),
        scripts_only=_query_bool("scripts_only", default=default_scripts_only),
        page=_query_int("page", default=1, minimum=1, maximum=100000),
        page_size=_query_int("page_size", default=20, minimum=1, maximum=100),
        export_job_id=_query_text("export_job"),
    )
    sop_batches = get_sop_v1_batches_payload(limit=8)
    focus_batches = get_focus_send_batches_payload(limit=8)
    debug = debug_payload
    if debug is None and resolved_entry_section == "debug":
        external_contact_id = _query_text("external_contact_id")
        phone = _query_text("phone")
        if external_contact_id or phone:
            debug = get_debug_payload(external_contact_id=external_contact_id, phone=phone)
    return _render_admin_template(
        "automation_conversion_run_center_workspace.html",
        active_nav="automation_conversion",
        page_title="运行中心",
        page_summary="把同步、监控、模型基础设施和单客调试统一下沉到运行中心，避免业务首页被技术入口占满。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("自动化转化", url_for("api.admin_automation_conversion")),
            ("运行中心", None),
        ),
        workspace_tabs=_automation_conversion_workspace_tabs("run_center"),
        run_center_entry_section=resolved_entry_section,
        run_center_subtab=resolved_subtab,
        run_center_workspace=_build_run_center_workspace(
            settings_payload=settings,
            overview_payload=overview,
            model_infra_payload=model_infra,
            orchestration_payload=orchestration,
            debug_payload=debug,
            sop_batches_payload=sop_batches,
            focus_batches_payload=focus_batches,
        ),
        settings_payload=settings,
        overview_payload=overview,
        model_infra_payload=model_infra,
        orchestration_payload=orchestration,
        sop_batches_payload=sop_batches,
        focus_batches_payload=focus_batches,
        debug_payload=debug,
        page_notice=_run_center_notice(),
        page_error=page_error,
        admin_action_token=ensure_admin_console_action_token(),
    )


def _render_stage_send_page(
    stage_key: str,
    *,
    page_notice: str = "",
    page_error: str = "",
    send_result: dict[str, object] | None = None,
    focus_batch: dict[str, object] | None = None,
):
    return _render_member_ops_page(
        stage_key,
        page_notice=page_notice,
        page_error=page_error,
        send_result=send_result,
        focus_batch=focus_batch,
        entry_section="send",
    )


def _render_settings_page(
    *,
    settings_payload: dict[str, object] | None = None,
    question_rules_json: str | None = None,
    page_error: str = "",
    entry_section: str = "rules",
):
    return _render_flow_design_page(
        settings_payload=settings_payload,
        question_rules_json=question_rules_json,
        page_error=page_error,
        entry_section=entry_section,
    )


def _render_model_infra_page(*, model_infra_payload: dict[str, object] | None = None, page_error: str = ""):
    return _render_run_center_page(
        model_infra_payload=model_infra_payload,
        page_error=page_error,
        entry_section="model",
    )


def _render_sop_page(*, sop_payload: dict[str, object] | None = None, page_error: str = ""):
    return _render_flow_design_page(
        sop_payload=sop_payload,
        page_error=page_error,
        entry_section="sop",
    )


def admin_automation_conversion():
    return _render_overview_page()


def admin_automation_conversion_overview():
    return _render_overview_page()


def admin_automation_conversion_flow_design():
    return _render_flow_design_page()


def admin_automation_conversion_member_ops():
    return _render_member_ops_page()


def admin_automation_conversion_run_center():
    return _render_run_center_page()


def admin_automation_conversion_reply_monitor_toggle():
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return _render_run_center_page(page_error=action_token_error, entry_section="reply_monitor")
    enabled = _json_bool(request.form.get("enabled") or request.values.get("enabled"))
    try:
        save_reply_monitor_enabled(enabled=enabled, operator_id=_operator_from_request())
    except ValueError as exc:
        return _render_run_center_page(page_error=str(exc), entry_section="reply_monitor")
    return redirect(
        url_for(
            "api.admin_automation_conversion_run_center",
            tab="reply-monitor",
            reply_monitor="enabled" if enabled else "disabled",
        ),
        code=302,
    )


def admin_automation_conversion_reply_monitor_capture():
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return _render_run_center_page(page_error=action_token_error, entry_section="reply_monitor")
    result = run_reply_monitor_capture(
        operator_id=_operator_from_request(),
        operator_type="user",
    )
    if result.get("ok"):
        return redirect(
            url_for("api.admin_automation_conversion_run_center", tab="reply-monitor", reply_monitor="captured"),
            code=302,
        )
    return _render_run_center_page(page_error=str(result.get("error") or "自动接话监控扫描失败"), entry_section="reply_monitor")


def admin_automation_conversion_reply_monitor_run_due():
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return _render_run_center_page(page_error=action_token_error, entry_section="reply_monitor")
    result = run_due_reply_monitor(
        operator_id=_operator_from_request(),
        operator_type="user",
    )
    if result.get("ok"):
        return redirect(
            url_for("api.admin_automation_conversion_run_center", tab="reply-monitor", reply_monitor="dispatched"),
            code=302,
        )
    return _render_run_center_page(page_error=str(result.get("error") or "自动接话监控放行失败"), entry_section="reply_monitor")


def admin_automation_conversion_sop():
    return _redirect_to(
        "api.admin_automation_conversion_flow_design",
        section="sop",
        pool=_query_text("pool"),
        day=request.args.get("day"),
        saved=_query_text("saved"),
    )


def admin_automation_conversion_stage_detail(stage_key: str):
    return _redirect_to(
        "api.admin_automation_conversion_member_ops",
        stage=_normalize_stage_key(stage_key),
        panel="members",
        keyword=_query_text("keyword"),
        offset=request.args.get("offset"),
        limit=request.args.get("limit"),
        external_contact_id=_query_text("external_contact_id"),
        phone=_query_text("phone"),
    )


def _stage_send_mode(stage_payload: dict[str, object]) -> str:
    pool = str(((stage_payload or {}).get("stage") or {}).get("pool") or "").strip()
    return "focus_ai" if pool in {"inactive_focus", "active_focus"} else "manual_send"


def admin_automation_conversion_stage_send(stage_key: str):
    return _redirect_to(
        "api.admin_automation_conversion_member_ops",
        stage=_normalize_stage_key(stage_key),
        panel="send",
        external_contact_id=_query_text("external_contact_id"),
        phone=_query_text("phone"),
    )


def admin_automation_conversion_stage_send_submit(stage_key: str):
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return _render_stage_send_page(stage_key, page_error=action_token_error)
    payload_bundle = _stage_send_payload(stage_key)
    if not payload_bundle:
        return _render_stage_send_page(stage_key, page_error="未找到对应阶段")
    normalized_stage_key = _normalize_stage_key(stage_key)
    send_mode = str(((payload_bundle.get("send_payload") or {}).get("mode") or "")).strip()
    if send_mode == "focus_ai":
        try:
            result = create_focus_send_batch(route_key=stage_key, operator_id=_operator_from_request(), operator_type="user")
        except ValueError as exc:
            return _render_stage_send_page(stage_key, page_error=str(exc))
        if result.get("ok"):
            return _redirect_to(
                "api.admin_automation_conversion_member_ops",
                stage=normalized_stage_key,
                panel="send",
                focus_batch_notice="created",
                focus_batch_id=str((result.get("batch") or {}).get("id") or ""),
            )
        return _render_stage_send_page(
            stage_key,
            page_error=str(result.get("error") or "AI 批任务创建失败"),
            focus_batch={"batch": result.get("batch") or {}, "items": result.get("items") or []},
        )
    try:
        result = send_stage_manual_message(route_key=stage_key, **_build_manual_send_request_payload())
    except ValueError as exc:
        return _render_stage_send_page(stage_key, page_error=str(exc))
    if result.get("ok"):
        status = str(result.get("status") or "")
        return _redirect_to(
            "api.admin_automation_conversion_member_ops",
            stage=normalized_stage_key,
            panel="send",
            manual_send_notice="sent" if status == "sent" else "empty",
            manual_send_status=status,
            manual_send_total=str(result.get("total_target_count") or 0),
            manual_send_sent=str(result.get("sent_count") or 0),
            manual_send_skipped=str(result.get("skipped_count") or 0),
            manual_send_record_id=str(result.get("record_id") or ""),
            manual_send_task_ids=",".join(str(item) for item in (result.get("task_ids") or [])),
        )
    return _render_stage_send_page(
        stage_key,
        page_error=str(result.get("error") or "官方群发创建失败"),
        send_result=result,
    )


def admin_automation_conversion_settings():
    return _redirect_to(
        "api.admin_automation_conversion_flow_design",
        section=_query_text("section") or "questionnaire",
        saved=_query_text("saved"),
        channel_saved=_query_text("channel_saved"),
        message_activity_sync=_query_text("message_activity_sync"),
        debug=_query_text("debug"),
    )


def admin_automation_conversion_model_infra():
    return _redirect_to(
        "api.admin_automation_conversion_run_center",
        tab="model-infra",
        settings_saved=_query_text("settings_saved"),
        prompt_saved=_query_text("prompt_saved"),
        tested=_query_text("tested"),
    )


def admin_automation_conversion_save_settings():
    section = _canonical_flow_design_section(request.form.get("section") or "")
    flow_entry_section = _flow_design_section_from_value(section, default="rules")
    flow_redirect_params: dict[str, object] = {"section": section}
    if section == "sop":
        flow_redirect_params["pool"] = str(request.form.get("pool") or "").strip()
        flow_redirect_params["day"] = str(request.form.get("day") or "").strip()
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        payload = _apply_settings_form_overrides(get_settings_payload())
        return _render_flow_design_page(
            settings_payload=payload,
            question_rules_json=request.form.get("question_rules_json", ""),
            page_error=action_token_error,
            entry_section=flow_entry_section,
        )
    try:
        save_settings(_build_settings_form_payload())
        return redirect(
            url_for("api.admin_automation_conversion_flow_design", **{**flow_redirect_params, "saved": 1}),
            code=302,
        )
    except ValueError as exc:
        payload = _apply_settings_form_overrides(get_settings_payload())
        return _render_flow_design_page(
            settings_payload=payload,
            question_rules_json=request.form.get("question_rules_json", ""),
            page_error=str(exc),
            entry_section=flow_entry_section,
        )


def admin_automation_conversion_save_model_infra_settings():
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return _render_model_infra_page(page_error=action_token_error)
    try:
        save_model_infra_settings(_build_model_infra_settings_form_payload())
        return redirect(
            url_for("api.admin_automation_conversion_run_center", tab="model-infra", settings_saved=1),
            code=302,
        )
    except ValueError as exc:
        return _render_model_infra_page(page_error=str(exc))


def admin_automation_conversion_test_model_infra():
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return _render_model_infra_page(page_error=action_token_error)
    result = test_model_infra_connection()
    if result.get("ok"):
        return redirect(
            url_for("api.admin_automation_conversion_run_center", tab="model-infra", tested=1),
            code=302,
        )
    return _render_model_infra_page(page_error=str(result.get("error") or "DeepSeek 测试连接失败"))


def admin_automation_conversion_save_model_prompt(agent_code: str):
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return _render_model_infra_page(page_error=action_token_error)
    try:
        save_model_infra_prompt(agent_code=agent_code, **_build_model_prompt_form_payload())
        return redirect(
            url_for("api.admin_automation_conversion_run_center", tab="model-infra", prompt_saved=agent_code),
            code=302,
        )
    except ValueError as exc:
        return _render_model_infra_page(page_error=str(exc))


def admin_automation_conversion_save_agent_router_settings():
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        payload = _apply_agent_router_form_state(get_agent_orchestration_payload(subtab="router"))
        return _render_run_center_page(
            page_error=action_token_error,
            entry_section="agent_orchestration",
            orchestration_payload=payload,
        )
    try:
        save_agent_router_settings(_build_agent_router_form_payload(), operator_id=_operator_from_request())
        return redirect(
            url_for("api.admin_automation_conversion_run_center", tab="agent-orchestration", subtab="router", router_saved=1),
            code=302,
        )
    except ValueError as exc:
        payload = _apply_agent_router_form_state(get_agent_orchestration_payload(subtab="router"))
        return _render_run_center_page(
            page_error=str(exc),
            entry_section="agent_orchestration",
            orchestration_payload=payload,
        )


def admin_automation_conversion_save_agent_config_draft(agent_code: str):
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        payload = _apply_agent_config_form_state(get_agent_orchestration_payload(subtab="agents", agent_code=agent_code))
        return _render_run_center_page(
            page_error=action_token_error,
            entry_section="agent_orchestration",
            orchestration_payload=payload,
        )
    try:
        save_agent_config_draft(agent_code, _build_agent_config_form_payload(), operator_id=_operator_from_request())
        return redirect(
            url_for(
                "api.admin_automation_conversion_run_center",
                tab="agent-orchestration",
                subtab="agents",
                agent=agent_code,
                agent_draft_saved=agent_code,
            ),
            code=302,
        )
    except DraftVersionConflictError as exc:
        payload = _apply_agent_config_form_state(get_agent_orchestration_payload(subtab="agents", agent_code=agent_code))
        return _render_run_center_page(
            page_error=(
                f"草稿版本冲突：当前版本 v{exc.current_draft_version}，提交基线 v{exc.expected_draft_version}。"
                "请先刷新最新配置后再保存。"
            ),
            entry_section="agent_orchestration",
            orchestration_payload=payload,
        )
    except (ValueError, LookupError) as exc:
        payload = _apply_agent_config_form_state(get_agent_orchestration_payload(subtab="agents", agent_code=agent_code))
        return _render_run_center_page(
            page_error=str(exc),
            entry_section="agent_orchestration",
            orchestration_payload=payload,
        )


def admin_automation_conversion_publish_agent_config(agent_code: str):
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return _render_run_center_page(
            page_error=action_token_error,
            entry_section="agent_orchestration",
            orchestration_payload=get_agent_orchestration_payload(subtab="agents", agent_code=agent_code),
        )
    try:
        publish_agent_config(agent_code, operator_id=_operator_from_request())
        return redirect(
            url_for(
                "api.admin_automation_conversion_run_center",
                tab="agent-orchestration",
                subtab="agents",
                agent=agent_code,
                agent_published=agent_code,
            ),
            code=302,
        )
    except (ValueError, LookupError) as exc:
        return _render_run_center_page(
            page_error=str(exc),
            entry_section="agent_orchestration",
            orchestration_payload=get_agent_orchestration_payload(subtab="agents", agent_code=agent_code),
        )


def admin_automation_conversion_replay_agent_run(run_id: str):
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return _render_run_center_page(
            page_error=action_token_error,
            entry_section="agent_orchestration",
            orchestration_payload=get_agent_orchestration_payload(subtab="replay", run_id=run_id),
        )
    try:
        replay = replay_agent_run(run_id, operator_id=_operator_from_request())
        return redirect(
            url_for(
                "api.admin_automation_conversion_run_center",
                tab="agent-orchestration",
                subtab="replay",
                run_id=str((replay.get("run") or {}).get("run_id") or ""),
                request_id=str((replay.get("run") or {}).get("request_id") or ""),
                agent_replayed=run_id,
            ),
            code=302,
        )
    except LookupError as exc:
        return _render_run_center_page(
            page_error=str(exc),
            entry_section="agent_orchestration",
            orchestration_payload=get_agent_orchestration_payload(subtab="replay", run_id=run_id),
        )


def admin_automation_conversion_replay_router_callback(run_id: str):
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return _render_run_center_page(
            page_error=action_token_error,
            entry_section="agent_orchestration",
            orchestration_payload=get_agent_orchestration_payload(subtab="router"),
        )
    try:
        replay = replay_router_callback(run_id, operator_id=_operator_from_request())
        return redirect(
            url_for(
                "api.admin_automation_conversion_run_center",
                tab="agent-orchestration",
                subtab="router",
                callback_replayed=str((replay.get("run") or {}).get("run_id") or run_id),
            ),
            code=302,
        )
    except (LookupError, ValueError) as exc:
        return _render_run_center_page(
            page_error=str(exc),
            entry_section="agent_orchestration",
            orchestration_payload=get_agent_orchestration_payload(subtab="router"),
        )


def admin_automation_conversion_check_router_pending_callbacks():
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return _render_run_center_page(
            page_error=action_token_error,
            entry_section="agent_orchestration",
            orchestration_payload=get_agent_orchestration_payload(subtab="router"),
        )
    try:
        result = run_router_pending_callback_check(operator_id=_operator_from_request())
    except ValueError as exc:
        return _render_run_center_page(
            page_error=str(exc),
            entry_section="agent_orchestration",
            orchestration_payload=get_agent_orchestration_payload(subtab="router"),
        )
    return redirect(
        url_for(
            "api.admin_automation_conversion_run_center",
            tab="agent-orchestration",
            subtab="router",
            pending_callback_checked=1,
            pending_callback_alerted=int(result.get("alerted_count") or 0),
        ),
        code=302,
    )


def admin_automation_conversion_export_agent_outputs():
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return _render_run_center_page(page_error=action_token_error, entry_section="agent_orchestration")
    filters = _build_agent_output_filters_from_request()
    try:
        job = create_agent_output_export_job(filters, requested_by=_operator_from_request())
    except ValueError as exc:
        return _render_run_center_page(
            page_error=str(exc),
            entry_section="agent_orchestration",
            orchestration_payload=get_agent_orchestration_payload(
                subtab="outputs",
                request_id=str(filters.get("request_id") or ""),
                batch_id=str(filters.get("batch_id") or ""),
                external_contact_id=str(filters.get("external_contact_id") or ""),
                userid=str(filters.get("userid") or ""),
                agent_code=str(filters.get("agent_code") or ""),
                output_type=str(filters.get("output_type") or ""),
                current_pool=str(filters.get("current_pool") or ""),
                target_pool=str(filters.get("target_pool") or ""),
                applied_status=str(filters.get("applied_status") or ""),
                min_confidence=str(filters.get("min_confidence") or ""),
                max_confidence=str(filters.get("max_confidence") or ""),
                has_error=str(filters.get("has_error") or ""),
                date_from=str(filters.get("date_from") or ""),
                date_to=str(filters.get("date_to") or ""),
            ),
        )
    return redirect(
        url_for(
            "api.admin_automation_conversion_run_center",
            tab="agent-orchestration",
            subtab="outputs",
            export_job=str(job.get("job_id") or ""),
            agent_export_job=1,
        ),
        code=302,
    )


def admin_automation_conversion_download_agent_output_export(job_id: str):
    payload = get_agent_output_export_file(job_id)
    if not payload:
        return _render_run_center_page(page_error="未找到对应导出任务", entry_section="agent_orchestration"), 404
    if not payload.get("content_bytes"):
        return _render_run_center_page(page_error="导出任务尚未完成", entry_section="agent_orchestration")
    response = Response(payload["content_bytes"], mimetype="application/vnd.ms-excel")
    response.headers["Content-Disposition"] = f"attachment; filename={payload.get('file_name') or 'agent-outputs.xls'}"
    return response


def admin_automation_conversion_generate_default_channel():
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return _render_settings_page(page_error=action_token_error, entry_section="channel")
    result = generate_default_channel_qr(operator=_operator_from_request())
    if result.get("generated"):
        return redirect(
            url_for("api.admin_automation_conversion_flow_design", section="channel", channel_saved=1),
            code=302,
        )
    return _render_settings_page(page_error=str(result.get("error") or "默认渠道二维码生成失败"), entry_section="channel")


def admin_automation_conversion_run_message_activity_sync():
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        if _wants_json_response():
            return jsonify({"ok": False, "error": action_token_error}), 400
        return _render_run_center_page(page_error=action_token_error, entry_section="sync")
    result = run_message_activity_sync(
        operator_id=_operator_from_request(),
        operator_type="user",
        trigger_source="manual",
    )
    if _wants_json_response():
        overview_payload = get_overview_payload()
        message_activity_sync = dict(overview_payload.get("message_activity_sync") or {})
        status_code = 200 if result.get("ok") else 400
        return (
            jsonify(
                {
                    "ok": bool(result.get("ok")),
                    "message": "消息活跃同步已完成" if result.get("ok") else str(result.get("error") or "消息活跃同步失败"),
                    "run": result.get("run") or {},
                    "message_activity_sync": message_activity_sync,
                }
            ),
            status_code,
        )
    if result.get("ok"):
        return redirect(
            url_for("api.admin_automation_conversion_run_center", tab="sync", message_activity_sync=1),
            code=302,
        )
    if result.get("status") == "not_configured":
        missing_keys = "、".join(result.get("missing_keys") or [])
        return _render_run_center_page(page_error=f"消息库尚未配置，请先补齐 {missing_keys}", entry_section="sync")
    return _render_run_center_page(page_error=str(result.get("error") or "消息活跃同步失败"), entry_section="sync")


def admin_automation_conversion_debug():
    return _redirect_to(
        "api.admin_automation_conversion_run_center",
        tab="debug",
        external_contact_id=_query_text("external_contact_id"),
        phone=_query_text("phone"),
    )


def admin_automation_conversion_preview():
    return _redirect_to(
        "api.admin_automation_conversion_run_center",
        tab="debug",
        external_contact_id=_query_text("external_contact_id"),
        phone=_query_text("phone"),
    )


def api_admin_automation_conversion_overview():
    return jsonify({"ok": True, "overview": get_overview_payload()})


def api_admin_automation_conversion_member():
    external_contact_id = _query_text("external_contact_id")
    phone = _query_text("phone")
    if not external_contact_id and not phone:
        return jsonify({"ok": False, "error": "external_contact_id or phone is required"}), 400
    return jsonify({"ok": True, "detail": get_member_detail(external_contact_id=external_contact_id, phone=phone)})


def _json_action_payload() -> dict[str, str]:
    payload = request.get_json(silent=True) or {}
    return {
        "external_contact_id": str(payload.get("external_contact_id") or "").strip(),
        "phone": str(payload.get("phone") or "").strip(),
        "operator_id": _operator_from_request(),
    }


def _run_member_action(action_fn):
    payload = _json_action_payload()
    try:
        result = action_fn(**payload)
        return jsonify({"ok": True, **result})
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def api_admin_automation_conversion_put_in_pool():
    return _run_member_action(put_in_pool)


def api_admin_automation_conversion_remove_from_pool():
    return _run_member_action(remove_from_pool)


def api_admin_automation_conversion_set_focus():
    return _run_member_action(lambda **payload: set_follow_type(**payload, follow_type="focus"))


def api_admin_automation_conversion_set_normal():
    return _run_member_action(lambda **payload: set_follow_type(**payload, follow_type="normal"))


def api_admin_automation_conversion_mark_won():
    return _run_member_action(mark_won)


def api_admin_automation_conversion_unmark_won():
    return _run_member_action(unmark_won)


def api_admin_automation_conversion_push_openclaw():
    payload = _json_action_payload()
    try:
        result = push_openclaw(**payload)
        if result.get("accepted"):
            return jsonify({"ok": True, **result}), 202
        if result.get("status") == "cooldown_blocked":
            return jsonify({"ok": False, "error": f"OpenClaw 冷却中，还剩 {result.get('remaining_seconds') or 0} 秒", **result}), 429
        return jsonify({"ok": False, "error": str(result.get("error") or "OpenClaw 推送失败"), **result}), 400
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def api_admin_automation_conversion_settings():
    return jsonify({"ok": True, "settings": get_settings_payload()})


def api_admin_automation_conversion_model_infra():
    return jsonify({"ok": True, "model_infra": get_model_infra_payload()})


def api_admin_automation_conversion_agent_outputs():
    auth_failure = require_internal_api_token()
    if auth_failure is not None:
        return auth_failure
    page = _query_int("page", default=1, minimum=1, maximum=100000)
    page_size = _query_int("page_size", default=20, minimum=1, maximum=100)
    filters = _build_agent_output_filters_from_request()
    return jsonify({"ok": True, **list_agent_outputs(filters, page=page, page_size=page_size, visibility="full")})


def api_admin_automation_conversion_agent_output_detail(output_id: str):
    auth_failure = require_internal_api_token()
    if auth_failure is not None:
        return auth_failure
    detail = get_agent_output_detail(output_id, visibility="full")
    if not detail:
        return jsonify({"ok": False, "error": "output not found"}), 404
    return jsonify({"ok": True, **detail})


def api_admin_automation_conversion_agent_run_detail(run_id: str):
    auth_failure = require_internal_api_token()
    if auth_failure is not None:
        return auth_failure
    detail = get_agent_run_detail(run_id, visibility="full")
    if not detail:
        return jsonify({"ok": False, "error": "run not found"}), 404
    return jsonify({"ok": True, "run": detail})


def api_admin_automation_conversion_agent_replay():
    auth_failure = require_internal_api_token()
    if auth_failure is not None:
        return auth_failure
    payload = get_agent_replay_payload(
        run_id=_query_text("run_id"),
        request_id=_query_text("request_id"),
        external_contact_id=_query_text("external_contact_id"),
        userid=_query_text("userid"),
        date_from=_query_text("date_from"),
        date_to=_query_text("date_to"),
        visibility="full",
    )
    return jsonify({"ok": True, **payload})


def api_admin_automation_conversion_router_pending_callbacks():
    auth_failure = require_internal_api_token()
    if auth_failure is not None:
        return auth_failure
    payload = list_router_pending_callbacks(
        older_than_minutes=_query_int("older_than_minutes", default=15, minimum=1, maximum=24 * 60),
        limit=_query_int("limit", default=20, minimum=1, maximum=100),
        visibility="full",
    )
    return jsonify({"ok": True, **payload})


def api_admin_automation_conversion_router_pending_callback_check():
    auth_failure = require_internal_api_token()
    if auth_failure is not None:
        return auth_failure
    payload = request.get_json(silent=True) or {}
    result = run_router_pending_callback_check(
        older_than_minutes=payload.get("older_than_minutes"),
        limit=int(payload.get("limit") or 100),
        operator_id=_operator_from_request(),
    )
    return jsonify(result)


def api_admin_automation_conversion_pending_agent_prompt_publish_requests():
    auth_failure = require_internal_api_token()
    if auth_failure is not None:
        return auth_failure
    payload = list_pending_agent_prompt_publish_requests(
        agent_code=_query_text("agent_code"),
        enabled_only=_query_text("enabled_only") in {"1", "true", "yes"},
        page=_query_int("page", default=1, minimum=1, maximum=100000),
        page_size=_query_int("page_size", default=20, minimum=1, maximum=100),
    )
    return jsonify({"ok": True, **payload})


def api_admin_automation_conversion_router_callback_replay(run_id: str):
    auth_failure = require_internal_api_token()
    if auth_failure is not None:
        return auth_failure
    try:
        replay = replay_router_callback(run_id, operator_id=_operator_from_request())
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **replay})


def api_admin_automation_conversion_agent_outputs_export():
    auth_failure = require_internal_api_token()
    if auth_failure is not None:
        return auth_failure
    payload = request.get_json(silent=True) or {}
    filters = dict(payload.get("filters") or {})
    requested_by = str(payload.get("requested_by") or _operator_from_request() or "internal_api").strip() or "internal_api"
    try:
        job = create_agent_output_export_job(filters, requested_by=requested_by)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 429
    return jsonify({"ok": True, "job": job}), 202


def api_admin_automation_conversion_agent_output_export_job(job_id: str):
    auth_failure = require_internal_api_token()
    if auth_failure is not None:
        return auth_failure
    if str(request.args.get("download") or "").strip() in {"1", "true"}:
        payload = get_agent_output_export_file(job_id)
        if not payload:
            return jsonify({"ok": False, "error": "export job not found"}), 404
        if not payload.get("content_bytes"):
            return jsonify({"ok": False, "error": "export job not completed", "job": payload.get("job") or {}}), 409
        response = Response(payload["content_bytes"], mimetype="application/vnd.ms-excel")
        response.headers["Content-Disposition"] = f"attachment; filename={payload.get('file_name') or 'agent-outputs.xls'}"
        return response
    job = get_agent_output_export_job(job_id)
    if not job:
        return jsonify({"ok": False, "error": "export job not found"}), 404
    return jsonify({"ok": True, "job": job})


def api_admin_automation_conversion_agent_router_save():
    payload = request.get_json(silent=True) or {}
    try:
        result = save_agent_router_settings(payload, operator_id=_operator_from_request(), source="api")
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})


def api_admin_automation_conversion_agent_config_detail(agent_code: str):
    try:
        result = get_agent_config_detail(agent_code)
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, "agent": result})


def api_admin_automation_conversion_agent_config_save_draft(agent_code: str):
    payload = request.get_json(silent=True) or {}
    try:
        result = save_agent_config_draft(agent_code, payload, operator_id=_operator_from_request(), source="api")
    except DraftVersionConflictError as exc:
        return jsonify({"ok": False, "error": exc.error_code, "message": str(exc), **exc.to_payload()}), 409
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, **result})


def api_admin_automation_conversion_agent_config_publish(agent_code: str):
    try:
        result = publish_agent_config(agent_code, operator_id=_operator_from_request())
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, **result})


def api_admin_automation_conversion_save_settings():
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify({"ok": True, "settings": save_settings(payload)})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def api_admin_automation_conversion_save_model_infra_settings():
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify({"ok": True, "model_infra": save_model_infra_settings(payload)})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


def api_admin_automation_conversion_test_model_infra():
    result = test_model_infra_connection()
    status_code = 200 if result.get("ok") else 400
    return jsonify(result), status_code


def api_admin_automation_conversion_save_model_prompt(agent_code: str):
    payload = request.get_json(silent=True) or {}
    try:
        prompt = save_model_infra_prompt(
            agent_code=agent_code,
            display_name=str(payload.get("display_name") or "").strip(),
            prompt_text=str(payload.get("prompt_text") or "").strip(),
            enabled=_json_bool(payload.get("enabled")),
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "prompt": prompt})


def api_admin_automation_conversion_sop_config():
    return jsonify({"ok": True, **get_sop_v1_config_payload()})


def api_admin_automation_conversion_sop_config_save(pool_key: str):
    payload = request.get_json(silent=True) or {}
    try:
        result = save_sop_v1_pool_config(
            pool_key=pool_key,
            enabled=payload.get("enabled"),
            send_time=payload.get("send_time"),
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})


def api_admin_automation_conversion_sop_templates(pool_key: str):
    try:
        result = get_sop_v1_templates_payload(pool_key, selected_day_index=_query_int("day", default=1, minimum=1, maximum=365))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})


def api_admin_automation_conversion_sop_template_append(pool_key: str):
    try:
        result = append_sop_v1_template_day(pool_key=pool_key)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result}), 201


def api_admin_automation_conversion_sop_template_save(pool_key: str, day_index: int):
    payload = request.get_json(silent=True) or {}
    if not payload and request.form:
        payload = {
            "content": request.form.get("content"),
            "enabled": _json_bool(request.form.get("enabled")),
            "images_json": request.form.get("images_json"),
        }
    try:
        result = save_sop_v1_template(
            pool_key=pool_key,
            day_index=day_index,
            content=payload.get("content"),
            images_json=_parse_sop_images_payload(payload.get("images_json") or payload.get("image_media_ids") or payload.get("image_media_ids_text")),
            enabled=payload.get("enabled"),
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, "template": result})


def api_admin_automation_conversion_sop_template_delete(pool_key: str, day_index: int):
    try:
        result = delete_sop_v1_template_day(pool_key=pool_key, day_index=day_index)
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": True, **result})


def api_admin_automation_conversion_sop_batches():
    limit = _query_int("limit", default=20, minimum=1, maximum=100)
    return jsonify({"ok": True, **get_sop_v1_batches_payload(limit=limit)})


def api_admin_automation_conversion_generate_default_channel():
    result = generate_default_channel_qr(operator=_operator_from_request())
    status_code = 200 if result.get("generated") else int(result.get("status_code") or 400)
    return jsonify({"ok": bool(result.get("generated")), **result}), status_code


def api_admin_automation_conversion_stage_manual_send(stage_key: str):
    try:
        result = send_stage_manual_message(route_key=stage_key, **_build_manual_send_request_payload())
    except ValueError as exc:
        message = str(exc)
        if message == "invalid stage":
            return jsonify({"ok": False, "error": message}), 404
        return jsonify({"ok": False, "error": message}), 400
    status_code = 200 if result.get("ok") else 502
    return jsonify(result), status_code


def api_admin_automation_conversion_stage_manual_send_preview(stage_key: str):
    try:
        payload = _build_manual_send_request_payload()
        payload.pop("operator_id", None)
        result = preview_stage_manual_message(route_key=stage_key, **payload)
    except ValueError as exc:
        message = str(exc)
        if message == "invalid stage":
            return jsonify({"ok": False, "error": message}), 404
        return jsonify({"ok": False, "error": message}), 400
    return jsonify(result)


def api_admin_automation_conversion_stage_focus_send_batches(stage_key: str):
    try:
        result = create_focus_send_batch(route_key=stage_key, operator_id=_operator_from_request(), operator_type="user")
    except ValueError as exc:
        message = str(exc)
        if message == "invalid stage":
            return jsonify({"ok": False, "error": message}), 404
        return jsonify({"ok": False, "error": message}), 400
    status_code = 201 if result.get("ok") else 409
    return jsonify(result), status_code


def api_admin_automation_conversion_focus_send_batch_detail(batch_id: str):
    try:
        result = get_focus_send_batch_detail(batch_id=int(batch_id))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "invalid batch_id"}), 400
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    return jsonify({"ok": True, **result})


def api_admin_automation_conversion_focus_send_batches_run_due():
    auth_failure = require_internal_api_token()
    if auth_failure is not None:
        return auth_failure
    payload = request.get_json(silent=True) or {}
    result = run_due_focus_send_batches(
        operator_id=_operator_from_request(),
        operator_type="system",
        limit=int(payload.get("limit") or 20),
    )
    return jsonify(result)


def api_admin_automation_conversion_run_message_activity_sync():
    auth_failure = require_internal_api_token(require_configured=True)
    if auth_failure is not None:
        return auth_failure
    payload = request.get_json(silent=True) or {}
    result = run_message_activity_sync(
        operator_id=_operator_from_request(),
        operator_type="system",
        trigger_source=str(payload.get("trigger_source") or request.values.get("trigger_source") or "scheduled").strip() or "scheduled",
    )
    if result.get("ok"):
        status_code = 200
    elif result.get("status") == "not_configured":
        status_code = 400
    else:
        status_code = 502
    return jsonify(result), status_code


def api_admin_automation_conversion_reply_monitor_capture():
    auth_failure = require_internal_api_token(require_configured=True)
    if auth_failure is not None:
        return auth_failure
    payload = request.get_json(silent=True) or {}
    result = run_reply_monitor_capture(
        operator_id=_operator_from_request(),
        operator_type="system",
        limit=int(payload.get("limit") or 500),
    )
    status_code = 200 if result.get("ok") or result.get("status") == "disabled" else 502
    return jsonify(result), status_code


def api_admin_automation_conversion_reply_monitor_run_due():
    auth_failure = require_internal_api_token(require_configured=True)
    if auth_failure is not None:
        return auth_failure
    payload = request.get_json(silent=True) or {}
    result = run_due_reply_monitor(
        operator_id=_operator_from_request(),
        operator_type="system",
        limit=int(payload.get("limit") or 20),
    )
    status_code = 200 if result.get("ok") or result.get("status") in {"disabled", "idle", "throttled", "quiet_hours"} else 502
    return jsonify(result), status_code


def api_internal_automation_conversion_lobster_results():
    auth_failure = require_internal_api_token(token_keys=("AUTOMATION_LOBSTER_CALLBACK_TOKEN",), require_configured=True)
    if auth_failure is not None:
        return auth_failure
    body_text = request.get_data(cache=True, as_text=True) or ""
    signature_ok, signature_error = validate_router_callback_signature(body_text=body_text, headers=dict(request.headers))
    if not signature_ok:
        return jsonify({"ok": False, "error": signature_error}), 401
    payload = request.get_json(silent=True) or {}
    result = handle_agent_router_callback(payload)
    if result.get("ok") and result.get("status") in {"applied", "idempotent"}:
        return jsonify(result), 200
    if result.get("status") == "rejected":
        status_code = 404 if result.get("error") == "request_not_found" else 409
        return jsonify(result), status_code
    return jsonify(result), 400


def api_internal_automation_conversion_router_test_dispatch():
    auth_failure = require_internal_api_token(require_configured=True)
    if auth_failure is not None:
        return auth_failure
    payload = request.get_json(silent=True) or {}
    result = run_router_test_dispatch(
        external_contact_id=str(payload.get("external_contact_id") or request.values.get("external_contact_id") or "").strip(),
        phone=str(payload.get("phone") or request.values.get("phone") or "").strip(),
        operator_id=str(payload.get("operator") or _operator_from_request() or "").strip(),
        mode=str(payload.get("mode") or request.values.get("mode") or "").strip(),
        force_capture=_json_bool(payload.get("force_capture")) or str(request.values.get("force_capture") or "").strip().lower() in {"1", "true", "yes", "on"},
        force_run_due=_json_bool(payload.get("force_run_due")) or str(request.values.get("force_run_due") or "").strip().lower() in {"1", "true", "yes", "on"},
    )
    status_code = 200 if result.get("ok") else (404 if result.get("error") == "member_not_found" else 409)
    return jsonify(result), status_code


def api_admin_automation_conversion_sop_run_due():
    auth_failure = require_internal_api_token(require_configured=True)
    if auth_failure is not None:
        return auth_failure
    result = run_registered_due_jobs(
        job_codes=["sop"],
        operator_id=_operator_from_request(),
        operator_type="system",
    )
    return jsonify(result)


def api_admin_automation_conversion_jobs_run_due():
    auth_failure = require_internal_api_token(require_configured=True)
    if auth_failure is not None:
        return auth_failure
    payload = request.get_json(silent=True) or {}
    try:
        result = run_registered_due_jobs(
            job_codes=list(payload.get("jobs") or []),
            operator_id=_operator_from_request(),
            operator_type="system",
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify(result)


def api_admin_automation_conversion_debug_member():
    external_contact_id = _query_text("external_contact_id")
    phone = _query_text("phone")
    if not external_contact_id and not phone:
        return jsonify({"ok": False, "error": "external_contact_id or phone is required"}), 400
    return jsonify({"ok": True, "debug": get_debug_payload(external_contact_id=external_contact_id, phone=phone)})


def register_routes(bp):
    bp.route("/admin/automation-conversion", methods=["GET"])(admin_automation_conversion)
    bp.route("/admin/automation-conversion/overview", methods=["GET"])(admin_automation_conversion_overview)
    bp.route("/admin/automation-conversion/flow-design", methods=["GET"])(admin_automation_conversion_flow_design)
    bp.route("/admin/automation-conversion/member-ops", methods=["GET"])(admin_automation_conversion_member_ops)
    bp.route("/admin/automation-conversion/run-center", methods=["GET"])(admin_automation_conversion_run_center)
    bp.route("/admin/automation-conversion/model-infra", methods=["GET"])(admin_automation_conversion_model_infra)
    bp.route("/admin/automation-conversion/model-infra/save-settings", methods=["POST"])(admin_automation_conversion_save_model_infra_settings)
    bp.route("/admin/automation-conversion/model-infra/test", methods=["POST"])(admin_automation_conversion_test_model_infra)
    bp.route("/admin/automation-conversion/model-infra/prompts/<agent_code>/save", methods=["POST"])(admin_automation_conversion_save_model_prompt)
    bp.route("/admin/automation-conversion/agent-orchestration/router/save", methods=["POST"])(admin_automation_conversion_save_agent_router_settings)
    bp.route("/admin/automation-conversion/agent-orchestration/agents/<agent_code>/save-draft", methods=["POST"])(admin_automation_conversion_save_agent_config_draft)
    bp.route("/admin/automation-conversion/agent-orchestration/agents/<agent_code>/publish", methods=["POST"])(admin_automation_conversion_publish_agent_config)
    bp.route("/admin/automation-conversion/agent-orchestration/replay/<run_id>", methods=["POST"])(admin_automation_conversion_replay_agent_run)
    bp.route("/admin/automation-conversion/agent-orchestration/router/replay-callback/<run_id>", methods=["POST"])(admin_automation_conversion_replay_router_callback)
    bp.route("/admin/automation-conversion/agent-orchestration/router/check-pending-callbacks", methods=["POST"])(admin_automation_conversion_check_router_pending_callbacks)
    bp.route("/admin/automation-conversion/agent-orchestration/outputs/export", methods=["POST"])(admin_automation_conversion_export_agent_outputs)
    bp.route("/admin/automation-conversion/agent-orchestration/outputs/export/<job_id>", methods=["GET"])(admin_automation_conversion_download_agent_output_export)
    bp.route("/admin/automation-conversion/sop", methods=["GET"])(admin_automation_conversion_sop)
    bp.route("/admin/automation-conversion/message-activity-sync/run", methods=["POST"])(admin_automation_conversion_run_message_activity_sync)
    bp.route("/admin/automation-conversion/reply-monitor/toggle", methods=["POST"])(admin_automation_conversion_reply_monitor_toggle)
    bp.route("/admin/automation-conversion/reply-monitor/capture", methods=["POST"])(admin_automation_conversion_reply_monitor_capture)
    bp.route("/admin/automation-conversion/reply-monitor/run-due", methods=["POST"])(admin_automation_conversion_reply_monitor_run_due)
    bp.route("/admin/automation-conversion/stage/<stage_key>", methods=["GET"])(admin_automation_conversion_stage_detail)
    bp.route("/admin/automation-conversion/stage/<stage_key>/send", methods=["GET"])(admin_automation_conversion_stage_send)
    bp.route("/admin/automation-conversion/stage/<stage_key>/send", methods=["POST"])(admin_automation_conversion_stage_send_submit)
    bp.route("/admin/automation-conversion/settings", methods=["GET"])(admin_automation_conversion_settings)
    bp.route("/admin/automation-conversion/settings/save", methods=["POST"])(admin_automation_conversion_save_settings)
    bp.route("/admin/automation-conversion/settings/default-channel/generate", methods=["POST"])(admin_automation_conversion_generate_default_channel)
    bp.route("/admin/automation-conversion/settings/message-activity-sync/run", methods=["POST"])(admin_automation_conversion_run_message_activity_sync)
    bp.route("/admin/automation-conversion/debug", methods=["GET"])(admin_automation_conversion_debug)
    bp.route("/admin/automation-conversion/preview", methods=["GET"])(admin_automation_conversion_preview)

    bp.route("/api/admin/automation-conversion/overview", methods=["GET"])(api_admin_automation_conversion_overview)
    bp.route("/api/admin/automation-conversion/member", methods=["GET"])(api_admin_automation_conversion_member)
    bp.route("/api/admin/automation-conversion/member/put-in-pool", methods=["POST"])(api_admin_automation_conversion_put_in_pool)
    bp.route("/api/admin/automation-conversion/member/remove-from-pool", methods=["POST"])(api_admin_automation_conversion_remove_from_pool)
    bp.route("/api/admin/automation-conversion/member/set-focus", methods=["POST"])(api_admin_automation_conversion_set_focus)
    bp.route("/api/admin/automation-conversion/member/set-normal", methods=["POST"])(api_admin_automation_conversion_set_normal)
    bp.route("/api/admin/automation-conversion/member/mark-won", methods=["POST"])(api_admin_automation_conversion_mark_won)
    bp.route("/api/admin/automation-conversion/member/unmark-won", methods=["POST"])(api_admin_automation_conversion_unmark_won)
    bp.route("/api/admin/automation-conversion/member/push-openclaw", methods=["POST"])(api_admin_automation_conversion_push_openclaw)
    bp.route("/api/admin/automation-conversion/settings", methods=["GET"])(api_admin_automation_conversion_settings)
    bp.route("/api/admin/automation-conversion/settings", methods=["POST"])(api_admin_automation_conversion_save_settings)
    bp.route("/api/admin/automation-conversion/agent-outputs", methods=["GET"])(api_admin_automation_conversion_agent_outputs)
    bp.route("/api/admin/automation-conversion/agent-outputs/<output_id>", methods=["GET"])(api_admin_automation_conversion_agent_output_detail)
    bp.route("/api/admin/automation-conversion/agent-runs/<run_id>", methods=["GET"])(api_admin_automation_conversion_agent_run_detail)
    bp.route("/api/admin/automation-conversion/agent-replay", methods=["GET"])(api_admin_automation_conversion_agent_replay)
    bp.route("/api/admin/automation-conversion/router-pending-callbacks", methods=["GET"])(api_admin_automation_conversion_router_pending_callbacks)
    bp.route("/api/admin/automation-conversion/router-pending-callback-check", methods=["POST"])(api_admin_automation_conversion_router_pending_callback_check)
    bp.route("/api/admin/automation-conversion/router-callback-replay/<run_id>", methods=["POST"])(api_admin_automation_conversion_router_callback_replay)
    bp.route("/api/admin/automation-conversion/agent-orchestration/pending-publish", methods=["GET"])(api_admin_automation_conversion_pending_agent_prompt_publish_requests)
    bp.route("/api/admin/automation-conversion/agent-outputs/export", methods=["POST"])(api_admin_automation_conversion_agent_outputs_export)
    bp.route("/api/admin/automation-conversion/agent-outputs/export/<job_id>", methods=["GET"])(api_admin_automation_conversion_agent_output_export_job)
    bp.route("/api/admin/automation-conversion/agent-orchestration/router", methods=["POST"])(api_admin_automation_conversion_agent_router_save)
    bp.route("/api/admin/automation-conversion/agent-orchestration/agents/<agent_code>", methods=["GET"])(api_admin_automation_conversion_agent_config_detail)
    bp.route("/api/admin/automation-conversion/agent-orchestration/agents/<agent_code>/draft", methods=["POST"])(api_admin_automation_conversion_agent_config_save_draft)
    bp.route("/api/admin/automation-conversion/agent-orchestration/agents/<agent_code>/publish", methods=["POST"])(api_admin_automation_conversion_agent_config_publish)
    bp.route("/api/admin/automation-conversion/model-infra", methods=["GET"])(api_admin_automation_conversion_model_infra)
    bp.route("/api/admin/automation-conversion/model-infra/settings", methods=["POST"])(api_admin_automation_conversion_save_model_infra_settings)
    bp.route("/api/admin/automation-conversion/model-infra/test-connection", methods=["POST"])(api_admin_automation_conversion_test_model_infra)
    bp.route("/api/admin/automation-conversion/model-infra/prompts/<agent_code>", methods=["POST"])(api_admin_automation_conversion_save_model_prompt)
    bp.route("/api/admin/automation-conversion/sop/config", methods=["GET"])(api_admin_automation_conversion_sop_config)
    bp.route("/api/admin/automation-conversion/sop/config/<pool_key>", methods=["PUT"])(api_admin_automation_conversion_sop_config_save)
    bp.route("/api/admin/automation-conversion/sop/templates/<pool_key>", methods=["GET"])(api_admin_automation_conversion_sop_templates)
    bp.route("/api/admin/automation-conversion/sop/templates/<pool_key>", methods=["POST"])(api_admin_automation_conversion_sop_template_append)
    bp.route("/api/admin/automation-conversion/sop/templates/<pool_key>/<int:day_index>", methods=["PUT"])(api_admin_automation_conversion_sop_template_save)
    bp.route("/api/admin/automation-conversion/sop/templates/<pool_key>/<int:day_index>", methods=["DELETE"])(api_admin_automation_conversion_sop_template_delete)
    bp.route("/api/admin/automation-conversion/sop/batches", methods=["GET"])(api_admin_automation_conversion_sop_batches)
    bp.route("/api/admin/automation-conversion/settings/default-channel/generate", methods=["POST"])(api_admin_automation_conversion_generate_default_channel)
    bp.route("/api/admin/automation-conversion/stage/<stage_key>/manual-send/preview", methods=["POST"])(api_admin_automation_conversion_stage_manual_send_preview)
    bp.route("/api/admin/automation-conversion/stage/<stage_key>/manual-send", methods=["POST"])(api_admin_automation_conversion_stage_manual_send)
    bp.route("/api/admin/automation-conversion/stage/<stage_key>/focus-send-batches", methods=["POST"])(api_admin_automation_conversion_stage_focus_send_batches)
    bp.route("/api/admin/automation-conversion/focus-send-batches/<batch_id>", methods=["GET"])(api_admin_automation_conversion_focus_send_batch_detail)
    bp.route("/api/admin/automation-conversion/focus-send-batches/run-due", methods=["POST"])(api_admin_automation_conversion_focus_send_batches_run_due)
    bp.route("/api/admin/automation-conversion/message-activity-sync/run", methods=["POST"])(api_admin_automation_conversion_run_message_activity_sync)
    bp.route("/api/admin/automation-conversion/reply-monitor/capture", methods=["POST"])(api_admin_automation_conversion_reply_monitor_capture)
    bp.route("/api/admin/automation-conversion/reply-monitor/run-due", methods=["POST"])(api_admin_automation_conversion_reply_monitor_run_due)
    bp.route("/api/internal/automation-conversion/lobster-results", methods=["POST"])(api_internal_automation_conversion_lobster_results)
    bp.route("/api/internal/automation-conversion/router-test-dispatch", methods=["POST"])(api_internal_automation_conversion_router_test_dispatch)
    bp.route("/api/admin/automation-conversion/sop/run-due", methods=["POST"])(api_admin_automation_conversion_sop_run_due)
    bp.route("/api/admin/automation-conversion/jobs/run-due", methods=["POST"])(api_admin_automation_conversion_jobs_run_due)
    bp.route("/api/admin/automation-conversion/debug/member", methods=["GET"])(api_admin_automation_conversion_debug_member)
