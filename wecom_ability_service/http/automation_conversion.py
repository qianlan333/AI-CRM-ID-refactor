from __future__ import annotations

import base64
import imghdr
import json

from flask import jsonify, redirect, request, url_for

from ..domains.automation_conversion import (
    create_focus_send_batch,
    append_sop_v1_template_day,
    delete_sop_v1_template_day,
    generate_default_channel_qr,
    get_debug_payload,
    get_focus_send_batch_detail,
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
    mark_won,
    put_in_pool,
    push_openclaw,
    remove_from_pool,
    run_due_reply_monitor,
    run_due_focus_send_batches,
    run_due_sop,
    run_message_activity_sync,
    run_reply_monitor_capture,
    save_model_infra_prompt,
    save_model_infra_settings,
    save_reply_monitor_enabled,
    save_sop_v1_pool_config,
    save_sop_v1_template,
    save_settings,
    send_stage_manual_message,
    set_follow_type,
    test_model_infra_connection,
    unmark_won,
)
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


def _stage_send_payload(stage_key: str) -> dict[str, object]:
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


def _render_stage_send_page(
    stage_key: str,
    *,
    page_notice: str = "",
    page_error: str = "",
    send_result: dict[str, object] | None = None,
    focus_batch: dict[str, object] | None = None,
):
    payload_bundle = _stage_send_payload(stage_key)
    if not payload_bundle:
        return _render_admin_template(
            "placeholder.html",
            active_nav="automation_conversion",
            page_title="阶段不存在",
            page_summary="当前阶段不存在，请返回自动化转化首页重新选择。",
            breadcrumbs=_breadcrumb_items(
                ("客户管理后台", url_for("api.admin_console_home")),
                ("自动化转化", url_for("api.admin_automation_conversion")),
                ("阶段不存在", None),
            ),
            actions=[{"label": "返回自动化转化首页", "href": url_for("api.admin_automation_conversion"), "variant": "secondary"}],
            state_title="阶段不存在",
            state_body="请检查链接是否正确。",
            state_items=["支持查看：新用户池、未激活普通池、未激活重点跟进池、激活普通池、激活重点跟进池、沉默池、已成交。"],
            page_error="未找到对应阶段",
        ), 404
    payload = payload_bundle["stage_payload"]
    send_payload = payload_bundle["send_payload"]
    return _render_admin_template(
        "automation_conversion_stage_send.html",
        active_nav="automation_conversion",
        page_title=f"{payload['stage']['label']}创建群发",
        page_summary="所有阶段都从这里进入群发壳子；重点阶段走 AI 批量处理，其他阶段走官方群发。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("自动化转化", url_for("api.admin_automation_conversion")),
            (payload["stage"]["label"], url_for("api.admin_automation_conversion_stage_detail", stage_key=stage_key)),
            ("创建群发", None),
        ),
        stage_payload=payload,
        send_payload=send_payload,
        send_result=send_result or {},
        focus_batch=focus_batch or {},
        page_notice=page_notice,
        page_error=page_error,
        admin_action_token=ensure_admin_console_action_token(),
    )


def _render_settings_page(*, settings_payload: dict[str, object] | None = None, question_rules_json: str | None = None, page_error: str = ""):
    payload = settings_payload or get_settings_payload()
    return _render_admin_template(
        "automation_conversion_settings.html",
        active_nav="automation_conversion",
        page_title="自动化转化设置",
        page_summary="把问卷、关键题、沉默规则和默认二维码统一放到设置页维护。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("自动化转化", url_for("api.admin_automation_conversion")),
            ("设置", None),
        ),
        settings_payload=payload,
        question_rules_json=question_rules_json
        if question_rules_json is not None
        else json.dumps((payload.get("rule_editor") or {}).get("rules") or [], ensure_ascii=False, indent=2),
        show_debug_json_editor=_query_text("debug") == "1",
        page_notice=_settings_notice(),
        page_error=page_error,
        admin_action_token=ensure_admin_console_action_token(),
    )


def _render_model_infra_page(*, model_infra_payload: dict[str, object] | None = None, page_error: str = ""):
    payload = model_infra_payload or get_model_infra_payload()
    return _render_admin_template(
        "automation_conversion_model_infra.html",
        active_nav="automation_conversion",
        page_title="模型基础设施",
        page_summary="这里统一维护 DeepSeek 配置、5 个 Agent Prompt 和最近一次模型调用日志。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("自动化转化", url_for("api.admin_automation_conversion")),
            ("模型基础设施", None),
        ),
        model_infra_payload=payload,
        page_notice=_model_infra_notice(),
        page_error=page_error,
        admin_action_token=ensure_admin_console_action_token(),
    )


def _render_sop_page(*, sop_payload: dict[str, object] | None = None, page_error: str = ""):
    selected_day_index = _query_int("day", default=1, minimum=1, maximum=365)
    payload = sop_payload or get_sop_v1_management_payload(selected_pool_key=_query_text("pool"), selected_day_index=selected_day_index)
    return _render_admin_template(
        "automation_conversion_sop.html",
        active_nav="automation_conversion",
        page_title="自动 SOP 管理",
        page_summary="只覆盖新用户池、未激活普通池、激活普通池。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("自动化转化", url_for("api.admin_automation_conversion")),
            ("自动 SOP", None),
        ),
        sop_payload=payload,
        page_notice=_sop_page_notice(),
        page_error=page_error,
        admin_action_token=ensure_admin_console_action_token(),
    )


def admin_automation_conversion():
    overview_payload = get_overview_payload()
    return _render_admin_template(
        "automation_conversion.html",
        active_nav="automation_conversion",
        page_title="自动化转化",
        page_summary="概览页只展示成员结果和阶段名单，规则配置与单客试算已迁到独立页面。",
        breadcrumbs=_breadcrumb_items(("客户管理后台", url_for("api.admin_console_home")), ("自动化转化", None)),
        overview_payload=overview_payload,
        page_notice=_overview_notice(),
        admin_action_token=ensure_admin_console_action_token(),
    )


def admin_automation_conversion_reply_monitor_toggle():
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return _render_admin_template(
            "automation_conversion.html",
            active_nav="automation_conversion",
            page_title="自动化转化",
            page_summary="概览页只展示成员结果和阶段名单，规则配置与单客试算已迁到独立页面。",
            breadcrumbs=_breadcrumb_items(("客户管理后台", url_for("api.admin_console_home")), ("自动化转化", None)),
            overview_payload=get_overview_payload(),
            page_error=action_token_error,
            admin_action_token=ensure_admin_console_action_token(),
        )
    enabled = _json_bool(request.form.get("enabled") or request.values.get("enabled"))
    try:
        save_reply_monitor_enabled(enabled=enabled, operator_id=_operator_from_request())
    except ValueError as exc:
        return _render_admin_template(
            "automation_conversion.html",
            active_nav="automation_conversion",
            page_title="自动化转化",
            page_summary="概览页只展示成员结果和阶段名单，规则配置与单客试算已迁到独立页面。",
            breadcrumbs=_breadcrumb_items(("客户管理后台", url_for("api.admin_console_home")), ("自动化转化", None)),
            overview_payload=get_overview_payload(),
            page_error=str(exc),
            admin_action_token=ensure_admin_console_action_token(),
        )
    return redirect(
        url_for("api.admin_automation_conversion", reply_monitor="enabled" if enabled else "disabled"),
        code=302,
    )


def admin_automation_conversion_reply_monitor_capture():
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return _render_admin_template(
            "automation_conversion.html",
            active_nav="automation_conversion",
            page_title="自动化转化",
            page_summary="概览页只展示成员结果和阶段名单，规则配置与单客试算已迁到独立页面。",
            breadcrumbs=_breadcrumb_items(("客户管理后台", url_for("api.admin_console_home")), ("自动化转化", None)),
            overview_payload=get_overview_payload(),
            page_error=action_token_error,
            admin_action_token=ensure_admin_console_action_token(),
        )
    result = run_reply_monitor_capture(
        operator_id=_operator_from_request(),
        operator_type="user",
    )
    if result.get("ok"):
        return redirect(url_for("api.admin_automation_conversion", reply_monitor="captured"), code=302)
    return _render_admin_template(
        "automation_conversion.html",
        active_nav="automation_conversion",
        page_title="自动化转化",
        page_summary="概览页只展示成员结果和阶段名单，规则配置与单客试算已迁到独立页面。",
        breadcrumbs=_breadcrumb_items(("客户管理后台", url_for("api.admin_console_home")), ("自动化转化", None)),
        overview_payload=get_overview_payload(),
        page_error=str(result.get("error") or "自动接话监控扫描失败"),
        admin_action_token=ensure_admin_console_action_token(),
    )


def admin_automation_conversion_reply_monitor_run_due():
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return _render_admin_template(
            "automation_conversion.html",
            active_nav="automation_conversion",
            page_title="自动化转化",
            page_summary="概览页只展示成员结果和阶段名单，规则配置与单客试算已迁到独立页面。",
            breadcrumbs=_breadcrumb_items(("客户管理后台", url_for("api.admin_console_home")), ("自动化转化", None)),
            overview_payload=get_overview_payload(),
            page_error=action_token_error,
            admin_action_token=ensure_admin_console_action_token(),
        )
    result = run_due_reply_monitor(
        operator_id=_operator_from_request(),
        operator_type="user",
    )
    if result.get("ok"):
        return redirect(url_for("api.admin_automation_conversion", reply_monitor="dispatched"), code=302)
    return _render_admin_template(
        "automation_conversion.html",
        active_nav="automation_conversion",
        page_title="自动化转化",
        page_summary="概览页只展示成员结果和阶段名单，规则配置与单客试算已迁到独立页面。",
        breadcrumbs=_breadcrumb_items(("客户管理后台", url_for("api.admin_console_home")), ("自动化转化", None)),
        overview_payload=get_overview_payload(),
        page_error=str(result.get("error") or "自动接话监控放行失败"),
        admin_action_token=ensure_admin_console_action_token(),
    )


def admin_automation_conversion_sop():
    return _render_sop_page()


def admin_automation_conversion_stage_detail(stage_key: str):
    try:
        payload = get_stage_detail_payload(
            route_key=stage_key,
            keyword=_query_text("keyword"),
            offset=_query_int("offset", default=0, minimum=0, maximum=100000),
            limit=_query_int("limit", default=50, minimum=1, maximum=100),
        )
    except ValueError:
        return _render_admin_template(
            "placeholder.html",
            active_nav="automation_conversion",
            page_title="阶段不存在",
            page_summary="当前阶段不存在，请返回自动化转化首页重新选择。",
            breadcrumbs=_breadcrumb_items(
                ("客户管理后台", url_for("api.admin_console_home")),
                ("自动化转化", url_for("api.admin_automation_conversion")),
                ("阶段不存在", None),
            ),
            actions=[{"label": "返回自动化转化首页", "href": url_for("api.admin_automation_conversion"), "variant": "secondary"}],
            state_title="阶段不存在",
            state_body="请检查链接是否正确。",
            state_items=["支持查看：新用户池、未激活普通池、未激活重点跟进池、激活普通池、激活重点跟进池、沉默池、已成交。"],
            page_error="未找到对应阶段",
        ), 404
    return _render_admin_template(
        "automation_conversion_stage.html",
        active_nav="automation_conversion",
        page_title=f"{payload['stage']['label']}客户",
        page_summary="按阶段查看自动化成员名单。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("自动化转化", url_for("api.admin_automation_conversion")),
            (payload["stage"]["label"], None),
        ),
        stage_payload=payload,
    )


def _stage_send_mode(stage_payload: dict[str, object]) -> str:
    pool = str(((stage_payload or {}).get("stage") or {}).get("pool") or "").strip()
    return "focus_ai" if pool in {"inactive_focus", "active_focus"} else "manual_send"


def admin_automation_conversion_stage_send(stage_key: str):
    return _render_stage_send_page(stage_key)


def admin_automation_conversion_stage_send_submit(stage_key: str):
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return _render_stage_send_page(stage_key, page_error=action_token_error)
    payload_bundle = _stage_send_payload(stage_key)
    if not payload_bundle:
        return _render_stage_send_page(stage_key, page_error="未找到对应阶段")
    send_mode = str(((payload_bundle.get("send_payload") or {}).get("mode") or "")).strip()
    if send_mode == "focus_ai":
        try:
            result = create_focus_send_batch(route_key=stage_key, operator_id=_operator_from_request(), operator_type="user")
        except ValueError as exc:
            return _render_stage_send_page(stage_key, page_error=str(exc))
        if result.get("ok"):
            return _render_stage_send_page(
                stage_key,
                page_notice="AI 批任务已创建",
                focus_batch={"batch": result.get("batch") or {}, "items": result.get("items") or []},
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
        notice = "官方群发已创建" if status == "sent" else "当前阶段没有可发送客户"
        return _render_stage_send_page(stage_key, page_notice=notice, send_result=result)
    return _render_stage_send_page(
        stage_key,
        page_error=str(result.get("error") or "官方群发创建失败"),
        send_result=result,
    )


def admin_automation_conversion_settings():
    return _render_settings_page()


def admin_automation_conversion_model_infra():
    return _render_model_infra_page()


def admin_automation_conversion_save_settings():
    try:
        save_settings(_build_settings_form_payload())
        return redirect(url_for("api.admin_automation_conversion_settings", saved=1), code=302)
    except ValueError as exc:
        payload = _apply_settings_form_overrides(get_settings_payload())
        return _render_settings_page(
            settings_payload=payload,
            question_rules_json=request.form.get("question_rules_json", ""),
            page_error=str(exc),
        )


def admin_automation_conversion_save_model_infra_settings():
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return _render_model_infra_page(page_error=action_token_error)
    try:
        save_model_infra_settings(_build_model_infra_settings_form_payload())
        return redirect(url_for("api.admin_automation_conversion_model_infra", settings_saved=1), code=302)
    except ValueError as exc:
        return _render_model_infra_page(page_error=str(exc))


def admin_automation_conversion_test_model_infra():
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return _render_model_infra_page(page_error=action_token_error)
    result = test_model_infra_connection()
    if result.get("ok"):
        return redirect(url_for("api.admin_automation_conversion_model_infra", tested=1), code=302)
    return _render_model_infra_page(page_error=str(result.get("error") or "DeepSeek 测试连接失败"))


def admin_automation_conversion_save_model_prompt(agent_code: str):
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        return _render_model_infra_page(page_error=action_token_error)
    try:
        save_model_infra_prompt(agent_code=agent_code, **_build_model_prompt_form_payload())
        return redirect(url_for("api.admin_automation_conversion_model_infra", prompt_saved=agent_code), code=302)
    except ValueError as exc:
        return _render_model_infra_page(page_error=str(exc))


def admin_automation_conversion_generate_default_channel():
    result = generate_default_channel_qr(operator=_operator_from_request())
    if result.get("generated"):
        return redirect(url_for("api.admin_automation_conversion_settings", channel_saved=1), code=302)
    return _render_settings_page(page_error=str(result.get("error") or "默认渠道二维码生成失败"))


def admin_automation_conversion_run_message_activity_sync():
    action_token_error = validate_admin_console_action_token()
    if action_token_error:
        if _wants_json_response():
            return jsonify({"ok": False, "error": action_token_error}), 400
        return _render_settings_page(page_error=action_token_error)
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
        return redirect(url_for("api.admin_automation_conversion_settings", message_activity_sync=1), code=302)
    if result.get("status") == "not_configured":
        missing_keys = "、".join(result.get("missing_keys") or [])
        return _render_settings_page(page_error=f"消息库尚未配置，请先补齐 {missing_keys}")
    return _render_settings_page(page_error=str(result.get("error") or "消息活跃同步失败"))


def admin_automation_conversion_debug():
    payload = None
    external_contact_id = _query_text("external_contact_id")
    phone = _query_text("phone")
    if external_contact_id or phone:
        payload = get_debug_payload(external_contact_id=external_contact_id, phone=phone)
    return _render_admin_template(
        "automation_conversion_debug.html",
        active_nav="automation_conversion",
        page_title="自动化转化调试",
        page_summary="单客试算与状态诊断已经迁到这个管理员调试页。",
        breadcrumbs=_breadcrumb_items(
            ("客户管理后台", url_for("api.admin_console_home")),
            ("自动化转化", url_for("api.admin_automation_conversion")),
            ("调试", None),
        ),
        debug_payload=payload,
    )


def admin_automation_conversion_preview():
    target = url_for("api.admin_automation_conversion_debug")
    query_string = request.query_string.decode("utf-8").strip()
    if query_string:
        target = f"{target}?{query_string}"
    return redirect(target, code=302)


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
    auth_failure = require_internal_api_token()
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
    auth_failure = require_internal_api_token()
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
    auth_failure = require_internal_api_token()
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


def api_admin_automation_conversion_sop_run_due():
    auth_failure = require_internal_api_token()
    if auth_failure is not None:
        return auth_failure
    result = run_due_sop(
        operator_id=_operator_from_request(),
        operator_type="system",
    )
    return jsonify(result)


def api_admin_automation_conversion_debug_member():
    external_contact_id = _query_text("external_contact_id")
    phone = _query_text("phone")
    if not external_contact_id and not phone:
        return jsonify({"ok": False, "error": "external_contact_id or phone is required"}), 400
    return jsonify({"ok": True, "debug": get_debug_payload(external_contact_id=external_contact_id, phone=phone)})


def register_routes(bp):
    bp.route("/admin/automation-conversion", methods=["GET"])(admin_automation_conversion)
    bp.route("/admin/automation-conversion/model-infra", methods=["GET"])(admin_automation_conversion_model_infra)
    bp.route("/admin/automation-conversion/model-infra/save-settings", methods=["POST"])(admin_automation_conversion_save_model_infra_settings)
    bp.route("/admin/automation-conversion/model-infra/test", methods=["POST"])(admin_automation_conversion_test_model_infra)
    bp.route("/admin/automation-conversion/model-infra/prompts/<agent_code>/save", methods=["POST"])(admin_automation_conversion_save_model_prompt)
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
    bp.route("/api/admin/automation-conversion/sop/run-due", methods=["POST"])(api_admin_automation_conversion_sop_run_due)
    bp.route("/api/admin/automation-conversion/debug/member", methods=["GET"])(api_admin_automation_conversion_debug_member)
