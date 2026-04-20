from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from flask import current_app

from ...db import get_db
from ...infra.settings import (
    DEFAULT_DEEPSEEK_BASE_URL,
    DEFAULT_DEEPSEEK_EXECUTION_MODEL,
    DEFAULT_DEEPSEEK_REASONER_MODEL,
    DEFAULT_DEEPSEEK_ROUTER_MODEL,
    DEFAULT_DEEPSEEK_TIMEOUT_SECONDS,
    get_setting,
    mask_value,
    set_settings,
)
from ...infra.wecom_runtime import get_app_runtime_client, get_contact_runtime_client
from ...wecom_client import WeComClientError
from ..automation_state.renderer import business_pool_label
from ..automation_state.state_defs import (
    FOLLOWUP_SEGMENT_FOCUS as SHARED_FOLLOWUP_SEGMENT_FOCUS,
    FOLLOWUP_SEGMENT_NORMAL as SHARED_FOLLOWUP_SEGMENT_NORMAL,
)
from ..marketing_automation.service import get_signup_conversion_config, save_signup_conversion_config
from ..outbound_webhook.service import EVENT_OPENCLAW_FOCUS_MESSAGE, send_outbound_webhook
from ..questionnaire.service import get_questionnaire_detail, list_available_wecom_tags, list_questionnaires
from ..tags import repo as tags_repo
from ..tasks.service import dispatch_wecom_task
from ..user_ops import page_service as user_ops_page_service
from .agents import (
    AGENT_PROMPT_DEFINITION_MAP,
    AGENT_PROMPT_ORDER,
    CHILD_AGENT_CONFIG_MAP,
    DeepSeekClientError,
    call_deepseek_agent,
    default_agent_prompt_payloads,
    get_deepseek_runtime_config,
    test_deepseek_connection,
)
from .message_activity_client import get_message_activity_db_status, query_message_activity_counts
from . import local_projection
from . import repo
from .provider import load_channel_provider

DEFAULT_OWNER_STAFF_ID = "HuangYouCan"
DEFAULT_CHANNEL_CODE = "default_qrcode"
DEFAULT_CHANNEL_NAME = "默认渠道二维码"
AI_PUSH_SCENE_SIDEBAR_SCRIPT = "sidebar_script"
AI_PUSH_COOLDOWN_SECONDS = 30
FOCUS_SEND_INTERVAL_SECONDS = 20
MESSAGE_ACTIVITY_SYNC_SOURCE_MANUAL = "manual"
MESSAGE_ACTIVITY_SYNC_SOURCE_SCHEDULED = "scheduled"
ACTIVE_FOCUS_MESSAGE_THRESHOLD = 15
ACTIVE_MESSAGE_MIN_THRESHOLD = 2
REPLY_MONITOR_TRIGGER_TYPE = "reply_monitor"
REPLY_MONITOR_STATUS_PENDING = "pending"
REPLY_MONITOR_STATUS_DEFERRED = "deferred_quiet_hours"
REPLY_MONITOR_STATUS_DISPATCHED = "dispatched"
REPLY_MONITOR_STATUS_FAILED = "failed"
REPLY_MONITOR_STATUS_PAUSED = "paused"
REPLY_MONITOR_DEFAULT_QUIET_HOURS_START = "23:00"
REPLY_MONITOR_DEFAULT_QUIET_HOURS_END = "09:00"
REPLY_MONITOR_DEFAULT_DISPATCH_INTERVAL_SECONDS = 30
DEEPSEEK_SETTING_KEYS = (
    "DEEPSEEK_ENABLED",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_ROUTER_MODEL",
    "DEEPSEEK_EXECUTION_MODEL",
    "DEEPSEEK_REASONER_MODEL",
    "DEEPSEEK_TIMEOUT_SECONDS",
)
CHANNEL_STATUS_NOT_GENERATED = "not_generated"
CHANNEL_STATUS_CONFIGURED = "configured"
CHANNEL_STATUS_ACTIVE = "active"

POOL_WON = local_projection.POOL_WON
POOL_REMOVED = local_projection.POOL_REMOVED
POOL_NO_REPLY = local_projection.POOL_NO_REPLY
POOL_HUMAN_REPLY = local_projection.POOL_HUMAN_REPLY
POOL_PENDING_QUESTIONNAIRE = local_projection.POOL_PENDING_QUESTIONNAIRE
POOL_OPERATING = local_projection.POOL_OPERATING
POOL_CONVERTED = local_projection.POOL_CONVERTED

POOL_NEW_USER = POOL_PENDING_QUESTIONNAIRE
POOL_INACTIVE_NORMAL = POOL_OPERATING
POOL_INACTIVE_FOCUS = POOL_OPERATING
POOL_ACTIVE_NORMAL = POOL_OPERATING
POOL_ACTIVE_FOCUS = POOL_OPERATING
POOL_SILENT = POOL_OPERATING

FOLLOWUP_NORMAL = SHARED_FOLLOWUP_SEGMENT_NORMAL
FOLLOWUP_FOCUS = SHARED_FOLLOWUP_SEGMENT_FOCUS

QUESTIONNAIRE_PENDING = "pending"
QUESTIONNAIRE_SUBMITTED = "submitted"

DECISION_SOURCE_QUESTIONNAIRE = "questionnaire"
DECISION_SOURCE_MANUAL = "manual"
DECISION_SOURCE_SYSTEM = "system"

SOURCE_TYPE_MANUAL = "manual"
SOURCE_TYPE_QRCODE = "qrcode"
SOURCE_TYPE_IMPORT = "import"
SOURCE_TYPE_QUESTIONNAIRE = "questionnaire"
SOURCE_TYPE_SYSTEM = "system"

ACTION_LABELS = {
    "put_in_pool": "放入自动化转化池",
    "remove_from_pool": "移除自动化转化池",
    "set_focus": "转化为重点跟进",
    "set_normal": "转化为普通跟进",
    "mark_won": "确认已成交",
    "unmark_won": "移除已成交",
    "push_openclaw": "一键自动化写话术",
    "message_activity_sync": "消息活跃同步",
    "reply_monitor_capture": "自动接话扫描",
    "reply_monitor_dispatch": "自动接话触发",
    "router_apply_pool": "龙虾异步回调改池",
    "qrcode_welcome_sent": "扫码欢迎语已发送",
    "qrcode_welcome_failed": "扫码欢迎语发送失败",
    "qrcode_entry_tag_applied": "扫码渠道标签已打上",
    "qrcode_entry_tag_failed": "扫码渠道标签打标失败",
}

POOL_LABELS = local_projection.POOL_LABELS
MANUAL_SEND_ALLOWED_POOLS = local_projection.MANUAL_SEND_ALLOWED_POOLS
STAGE_BY_POOL = local_projection.STAGE_BY_POOL
TARGET_BY_POOL = local_projection.TARGET_BY_POOL
STAGE_LABELS = local_projection.STAGE_LABELS
TARGET_LABELS = local_projection.TARGET_LABELS
STAGE_DEFINITIONS = local_projection.STAGE_DEFINITIONS
ROUTE_KEY_TO_POOL = local_projection.ROUTE_KEY_TO_POOL
POOL_TO_STAGE_DEF = local_projection.POOL_TO_STAGE_DEF
MESSAGE_ACTIVITY_SYNC_POOLS = (
    POOL_OPERATING,
)
FOCUS_SEND_ALLOWED_POOLS = local_projection.FOCUS_SEND_ALLOWED_POOLS
SOP_V1_ALLOWED_POOLS = (
    POOL_PENDING_QUESTIONNAIRE,
    POOL_OPERATING,
    POOL_CONVERTED,
)
SOP_V1_DEFAULT_SEND_TIME = "09:00"
SOP_V1_DEFAULT_TIMEZONE = "Asia/Shanghai"
SOP_RUN_SKIPPED_REASON_LABELS = {
    "moved_out_of_pool": "成员已移出当前池子",
    "already_processed_today": "当天这个 day 已处理过",
    "no_template": "当天没有对应模板",
    "template_disabled": "对应 day 模板已禁用",
    "template_empty": "对应 day 模板内容为空",
    "missing_external_userid": "缺少 external_userid",
    "send_time_not_reached": "当前还未到发送时间",
}
SOP_BATCH_STATUS_LABELS = {
    "finished": "已完成",
    "running": "执行中",
    "pending": "待执行",
    "failed": "失败",
}


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return _normalized_text(value).lower() in {"1", "true", "yes", "y", "on"}


def _json_loads(value: Any, *, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    text = _normalized_text(value)
    if not text:
        return default
    try:
        return json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _parse_timestamp(value: Any) -> datetime | None:
    text = _normalized_text(value)
    if not text:
        return None
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(text, pattern)
        except ValueError:
            continue
    return None


def _iso_now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _setting_bool_text(key: str, *, default: bool) -> bool:
    raw_value = get_setting(key)
    if raw_value is None:
        raw_value = current_app.config.get(key, default)
    if isinstance(raw_value, bool):
        return raw_value
    return _normalized_text(raw_value).lower() in {"1", "true", "yes", "y", "on"}


def _setting_int_value(key: str, *, default: int, minimum: int = 1) -> int:
    raw_value = get_setting(key)
    if raw_value is None:
        raw_value = current_app.config.get(key, default)
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        value = int(default)
    return max(int(minimum), value)


def _setting_text_value(key: str, *, default: str = "") -> str:
    return _normalized_text(get_setting(key) or current_app.config.get(key, "") or default)


def _phone_last4(phone: Any) -> str:
    text = _normalized_text(phone)
    return text[-4:] if len(text) >= 4 else ""


def _phone_prefix3(phone: Any) -> str:
    text = _normalized_text(phone)
    return text[:3] if len(text) >= 3 else ""


def _phone_match_key(phone: Any) -> str:
    text = _normalized_text(phone)
    if len(text) < 7:
        return ""
    return f"{text[:3]}_{text[-4:]}"


def default_owner_staff_id() -> str:
    return DEFAULT_OWNER_STAFF_ID


def _pool_label(pool: str) -> str:
    shared_label = business_pool_label(pool)
    if shared_label:
        return shared_label
    return local_projection.pool_label(pool)


def _auto_start_window_payload(config: dict[str, Any]) -> dict[str, Any]:
    day_start_hour = int(config.get("day_start_hour") or 9)
    quiet_hour_start = int(config.get("quiet_hour_start") or 23)
    timezone = _normalized_text(config.get("timezone")) or "Asia/Shanghai"
    return {
        "day_start_hour": day_start_hour,
        "quiet_hour_start": quiet_hour_start,
        "timezone": timezone,
        "label": f"{day_start_hour:02d}:00 - {quiet_hour_start:02d}:00",
        "description": f"按 {timezone} 时区，只有 {day_start_hour:02d}:00 - {quiet_hour_start:02d}:00 之间允许自动启动。",
    }


def _manual_send_allowed_route_keys() -> set[str]:
    return local_projection.manual_send_allowed_route_keys()


def _manual_send_stage_definition(route_key: str) -> dict[str, Any]:
    return local_projection.manual_send_stage_definition(route_key)


def _focus_send_stage_definition(route_key: str) -> dict[str, Any]:
    return local_projection.focus_send_stage_definition(route_key)


def _normalize_manual_send_image_media_ids(image_media_ids: list[str] | None = None) -> list[str]:
    normalized_image_media_ids: list[str] = []
    for media_id in list(image_media_ids or []):
        normalized_media_id = _normalized_text(media_id)
        if normalized_media_id:
            normalized_image_media_ids.append(normalized_media_id)
    return normalized_image_media_ids


def _validate_sop_pool_key(pool_key: str) -> str:
    normalized_pool_key = {
        "new_user": POOL_PENDING_QUESTIONNAIRE,
        "inactive_normal": POOL_OPERATING,
        "inactive_focus": POOL_OPERATING,
        "active_normal": POOL_OPERATING,
        "active_focus": POOL_OPERATING,
        "silent": POOL_OPERATING,
        "won": POOL_CONVERTED,
    }.get(_normalized_text(pool_key), _normalized_text(pool_key))
    if normalized_pool_key not in SOP_V1_ALLOWED_POOLS:
        raise ValueError("sop pool_key must be one of pending_questionnaire, operating, converted")
    return normalized_pool_key


def _normalize_sop_send_time(value: Any) -> str:
    text = _normalized_text(value) or SOP_V1_DEFAULT_SEND_TIME
    try:
        normalized = datetime.strptime(text, "%H:%M")
    except ValueError as exc:
        raise ValueError("sop send_time must use HH:MM") from exc
    return normalized.strftime("%H:%M")


def _default_sop_send_time() -> str:
    try:
        day_start_hour = int(get_signup_conversion_config().get("day_start_hour") or 9)
    except (TypeError, ValueError):
        day_start_hour = 9
    return f"{max(0, min(day_start_hour, 23)):02d}:00"


def _default_sop_pool_config(pool_key: str) -> dict[str, Any]:
    normalized_pool_key = _validate_sop_pool_key(pool_key)
    return {
        "pool_key": normalized_pool_key,
        "enabled": True,
        "max_day_count": 1,
        "send_time": _default_sop_send_time(),
        "timezone": SOP_V1_DEFAULT_TIMEZONE,
        "effective_start_at": _iso_now(),
    }


def _empty_sop_template(pool_key: str, day_index: int) -> dict[str, Any]:
    return {
        "pool_key": _validate_sop_pool_key(pool_key),
        "day_index": int(day_index),
        "content": "",
        "images_json": [],
        "enabled": True,
    }


def _serialize_sop_pool_config(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    return {
        "id": int(row.get("id") or 0),
        "pool_key": _normalized_text(row.get("pool_key")),
        "pool_label": _pool_label(row.get("pool_key")),
        "enabled": _normalize_bool(row.get("enabled")),
        "max_day_count": int(row.get("max_day_count") or 0),
        "send_time": _normalize_sop_send_time(row.get("send_time")),
        "effective_start_at": _normalized_text(row.get("effective_start_at")),
        "created_at": _normalized_text(row.get("created_at")),
        "updated_at": _normalized_text(row.get("updated_at")),
    }


def _serialize_sop_template(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    deserialized = repo.deserialize_sop_template_row(row)
    return {
        "id": int(deserialized.get("id") or 0),
        "pool_key": _normalized_text(deserialized.get("pool_key")),
        "pool_label": _pool_label(deserialized.get("pool_key")),
        "day_index": int(deserialized.get("day_index") or 0),
        "content": _normalized_text(deserialized.get("content")),
        "images_json": list(deserialized.get("images_json") or []),
        "enabled": _normalize_bool(deserialized.get("enabled")),
        "created_at": _normalized_text(deserialized.get("created_at")),
        "updated_at": _normalized_text(deserialized.get("updated_at")),
    }


def _template_image_preview_url(item: dict[str, Any]) -> str:
    data_url = _normalized_text(item.get("data_url"))
    if data_url:
        return data_url
    data_base64 = _normalized_text(item.get("data_base64"))
    if data_base64:
        content_type = _normalized_text(item.get("content_type")) or "image/png"
        return f"data:{content_type};base64,{data_base64}"
    return ""


def _serialize_sop_template_for_ui(template: dict[str, Any]) -> dict[str, Any]:
    images: list[dict[str, Any]] = []
    for index, raw_item in enumerate(list(template.get("images_json") or []), start=1):
        if isinstance(raw_item, str):
            item = {"media_id": _normalized_text(raw_item)}
        elif isinstance(raw_item, dict):
            item = dict(raw_item)
        else:
            continue
        images.append(
            {
                "id": f"{template.get('pool_key')}-{template.get('day_index')}-{index}",
                "file_name": _normalized_text(item.get("file_name")) or f"day{template.get('day_index')}-image-{index}.png",
                "content_type": _normalized_text(item.get("content_type")) or "image/png",
                "data_url": _normalized_text(item.get("data_url")),
                "data_base64": _normalized_text(item.get("data_base64")),
                "media_id": _normalized_text(item.get("media_id") or item.get("image_media_id")),
                "preview_url": _template_image_preview_url(item),
                "is_uploaded": bool(_template_image_preview_url(item)),
            }
        )
    return {
        **template,
        "images_json": images,
        "image_count": len(images),
    }


def _serialize_sop_progress(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    deserialized = repo.deserialize_sop_progress_row(row)
    return {
        "id": int(deserialized.get("id") or 0),
        "member_id": int(deserialized.get("member_id") or 0),
        "pool_key": _normalized_text(deserialized.get("pool_key")),
        "pool_label": _pool_label(deserialized.get("pool_key")),
        "first_entered_at": _normalized_text(deserialized.get("first_entered_at")),
        "last_entered_at": _normalized_text(deserialized.get("last_entered_at")),
        "sop_anchor_date": _normalized_text(deserialized.get("sop_anchor_date")),
        "first_effective_in_pool_at": _normalized_text(deserialized.get("first_effective_in_pool_at")),
        "last_in_pool_at": _normalized_text(deserialized.get("last_in_pool_at")),
        "last_sent_day": int(deserialized.get("last_sent_day") or 0),
        "last_sent_at": _normalized_text(deserialized.get("last_sent_at")),
        "completed_at": _normalized_text(deserialized.get("completed_at")),
        "created_at": _normalized_text(deserialized.get("created_at")),
        "updated_at": _normalized_text(deserialized.get("updated_at")),
    }


def _serialize_sop_batch(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    deserialized = repo.deserialize_sop_batch_row(row)
    return {
        "id": int(deserialized.get("id") or 0),
        "pool_key": _normalized_text(deserialized.get("pool_key")),
        "pool_label": _pool_label(deserialized.get("pool_key")),
        "day_index": int(deserialized.get("day_index") or 0),
        "template_id": int(deserialized.get("template_id") or 0) if deserialized.get("template_id") not in (None, "") else None,
        "scheduled_for": _normalized_text(deserialized.get("scheduled_for")),
        "status": _normalized_text(deserialized.get("status")),
        "total_count": int(deserialized.get("total_count") or 0),
        "success_count": int(deserialized.get("success_count") or 0),
        "skipped_count": int(deserialized.get("skipped_count") or 0),
        "failed_count": int(deserialized.get("failed_count") or 0),
        "summary_json": dict(deserialized.get("summary_json") or {}),
        "created_at": _normalized_text(deserialized.get("created_at")),
        "updated_at": _normalized_text(deserialized.get("updated_at")),
    }


def _serialize_sop_batch_item(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    deserialized = repo.deserialize_sop_batch_item_row(row)
    return {
        "id": int(deserialized.get("id") or 0),
        "batch_id": int(deserialized.get("batch_id") or 0),
        "member_id": int(deserialized.get("member_id") or 0) if deserialized.get("member_id") not in (None, "") else None,
        "pool_key": _normalized_text(deserialized.get("pool_key")),
        "day_index": int(deserialized.get("day_index") or 0),
        "day_index_snapshot": int(deserialized.get("day_index_snapshot") or 0),
        "external_userid": _normalized_text(deserialized.get("external_userid")),
        "status": _normalized_text(deserialized.get("status")),
        "error_message": _normalized_text(deserialized.get("error_message")),
        "content_snapshot": _normalized_text(deserialized.get("content_snapshot")),
        "images_snapshot": list(deserialized.get("images_snapshot") or []),
        "sent_record_id": int(deserialized.get("sent_record_id") or 0) if deserialized.get("sent_record_id") not in (None, "") else None,
        "created_at": _normalized_text(deserialized.get("created_at")),
        "updated_at": _normalized_text(deserialized.get("updated_at")),
    }


def _current_sop_template_day_count(pool_key: str) -> int:
    templates = [_serialize_sop_template(row) for row in repo.list_sop_templates(pool_key=pool_key)]
    return max([int(item.get("day_index") or 0) for item in templates] or [0])


def _ensure_sop_template_day_exists(pool_key: str, day_index: int) -> dict[str, Any]:
    normalized_pool_key = _validate_sop_pool_key(pool_key)
    normalized_day_index = max(1, int(day_index or 1))
    template = repo.get_sop_template(pool_key=normalized_pool_key, day_index=normalized_day_index)
    if template:
        return _serialize_sop_template(template)
    return _serialize_sop_template(repo.save_sop_template(_empty_sop_template(normalized_pool_key, normalized_day_index)))


def _latest_sop_execution_summary(pool_key: str) -> dict[str, Any]:
    latest_batch = next(iter([_serialize_sop_batch(row) for row in repo.list_sop_batches(pool_key=pool_key, limit=1)]), {})
    if not latest_batch:
        return {
            "has_record": False,
            "label": "暂无执行记录",
            "scheduled_for": "",
            "success_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
        }
    return {
        "has_record": True,
        "label": latest_batch.get("scheduled_for") or latest_batch.get("created_at") or "最近执行",
        "scheduled_for": _normalized_text(latest_batch.get("scheduled_for")),
        "status": _normalized_text(latest_batch.get("status")),
        "success_count": int(latest_batch.get("success_count") or 0),
        "skipped_count": int(latest_batch.get("skipped_count") or 0),
        "failed_count": int(latest_batch.get("failed_count") or 0),
    }


def ensure_sop_v1_defaults() -> dict[str, Any]:
    configs: list[dict[str, Any]] = []
    templates_by_pool: dict[str, list[dict[str, Any]]] = {}
    for pool_key in SOP_V1_ALLOWED_POOLS:
        _ensure_sop_template_day_exists(pool_key, 1)
        existing = _serialize_sop_pool_config(repo.get_sop_pool_config(pool_key))
        template_count = max(_current_sop_template_day_count(pool_key), 1)
        saved = repo.save_sop_pool_config(
            {
                "pool_key": pool_key,
                "enabled": _normalize_bool(existing.get("enabled")) if existing else True,
                "max_day_count": template_count,
                "send_time": _normalize_sop_send_time(existing.get("send_time") if existing else _default_sop_send_time()),
                "timezone": SOP_V1_DEFAULT_TIMEZONE,
                "effective_start_at": _normalized_text(existing.get("effective_start_at")) or _iso_now(),
            }
        )
        configs.append(_serialize_sop_pool_config(saved))
        templates_by_pool[pool_key] = [_serialize_sop_template(row) for row in repo.list_sop_templates(pool_key=pool_key)]
    get_db().commit()
    return {"configs": configs, "templates": templates_by_pool}


def _sop_batch_status_label(value: Any) -> str:
    normalized = _normalized_text(value)
    return SOP_BATCH_STATUS_LABELS.get(normalized, normalized or "未开始")


def get_sop_v1_config_payload() -> dict[str, Any]:
    defaults = ensure_sop_v1_defaults()
    return {
        "configs": [dict(item) for item in list(defaults.get("configs") or [])],
    }

def get_sop_v1_templates_payload(pool_key: str, *, selected_day_index: int = 0) -> dict[str, Any]:
    normalized_pool_key = _validate_sop_pool_key(pool_key)
    ensure_sop_v1_defaults()
    config = _serialize_sop_pool_config(repo.get_sop_pool_config(normalized_pool_key))
    templates = [_serialize_sop_template(row) for row in repo.list_sop_templates(pool_key=normalized_pool_key)]
    if not templates:
        _ensure_sop_template_day_exists(normalized_pool_key, 1)
        templates = [_serialize_sop_template(row) for row in repo.list_sop_templates(pool_key=normalized_pool_key)]
    template_count = max([int(item.get("day_index") or 0) for item in templates] or [1])
    selected_day = int(selected_day_index or 0)
    if selected_day < 1 or selected_day > template_count:
        selected_day = 1
    selected_template = next((item for item in templates if int(item.get("day_index") or 0) == selected_day), templates[0])
    day_tabs = []
    for template in templates:
        day_index = int(template.get("day_index") or 0)
        day_tabs.append(
            {
                "day_index": day_index,
                "label": f"day{day_index}",
                "is_selected": day_index == selected_day,
                "has_content": bool(_normalized_text(template.get("content")) or list(template.get("images_json") or [])),
                "enabled": _normalize_bool(template.get("enabled")),
            }
        )
    get_db().commit()
    return {
        "pool_key": normalized_pool_key,
        "pool_label": _pool_label(normalized_pool_key),
        "config": config,
        "template_count": template_count,
        "selected_day_index": selected_day,
        "day_tabs": day_tabs,
        "selected_template": _serialize_sop_template_for_ui(selected_template),
        "recent_execution": _latest_sop_execution_summary(normalized_pool_key),
    }


def get_sop_v1_batches_payload(*, limit: int = 20) -> dict[str, Any]:
    batches = [_serialize_sop_batch(row) for row in repo.list_sop_batches(limit=max(1, int(limit)))]
    return {
        "batches": [
            {
                **batch,
                "status_label": _sop_batch_status_label(batch.get("status")),
            }
            for batch in batches
        ]
    }


def get_focus_send_batches_payload(*, limit: int = 20) -> dict[str, Any]:
    batches = [_serialize_focus_send_batch(row) for row in repo.list_recent_focus_send_batches(limit=max(1, int(limit)))]
    return {
        "batches": batches,
    }


def get_sop_v1_management_payload(*, selected_pool_key: str = "", selected_day_index: int = 0) -> dict[str, Any]:
    ensure_sop_v1_defaults()
    normalized_pool_key = _validate_sop_pool_key(selected_pool_key) if _normalized_text(selected_pool_key) else SOP_V1_ALLOWED_POOLS[0]
    pool_cards: list[dict[str, Any]] = []
    for pool_key in SOP_V1_ALLOWED_POOLS:
        pool_payload = get_sop_v1_templates_payload(pool_key, selected_day_index=selected_day_index if pool_key == normalized_pool_key else 0)
        config = dict(pool_payload.get("config") or {})
        recent_execution = dict(pool_payload.get("recent_execution") or {})
        pool_cards.append(
            {
                "pool_key": pool_key,
                "pool_label": _pool_label(pool_key),
                "is_selected": pool_key == normalized_pool_key,
                "enabled": _normalize_bool(config.get("enabled")),
                "send_time": _normalize_sop_send_time(config.get("send_time")),
                "template_count": int(pool_payload.get("template_count") or 0),
                "recent_execution": recent_execution,
            }
        )
    current_pool = get_sop_v1_templates_payload(normalized_pool_key, selected_day_index=selected_day_index)
    return {
        "subtitle": "只覆盖未填问卷人群、运营中人群、已转化人群",
        "selected_pool_key": normalized_pool_key,
        "pool_cards": pool_cards,
        "current_pool": current_pool,
    }


def save_sop_v1_pool_config(
    *,
    pool_key: str,
    enabled: bool,
    send_time: str = SOP_V1_DEFAULT_SEND_TIME,
    timezone: str = SOP_V1_DEFAULT_TIMEZONE,
    effective_start_at: str = "",
) -> dict[str, Any]:
    normalized_pool_key = _validate_sop_pool_key(pool_key)
    ensure_sop_v1_defaults()
    existing = _serialize_sop_pool_config(repo.get_sop_pool_config(normalized_pool_key))
    saved = repo.save_sop_pool_config(
        {
            "pool_key": normalized_pool_key,
            "enabled": _normalize_bool(enabled),
            "max_day_count": max(_current_sop_template_day_count(normalized_pool_key), 1),
            "send_time": _normalize_sop_send_time(send_time or existing.get("send_time")),
            "timezone": _normalized_text(timezone) or SOP_V1_DEFAULT_TIMEZONE,
            "effective_start_at": _normalized_text(effective_start_at) or _normalized_text(existing.get("effective_start_at")) or _iso_now(),
        }
    )
    get_db().commit()
    return _serialize_sop_pool_config(saved)


def save_sop_v1_template(
    *,
    pool_key: str,
    day_index: int,
    content: str = "",
    images_json: list[dict[str, Any]] | None = None,
    enabled: bool = True,
) -> dict[str, Any]:
    normalized_pool_key = _validate_sop_pool_key(pool_key)
    normalized_day_index = max(1, int(day_index or 1))
    ensure_sop_v1_defaults()
    saved = repo.save_sop_template(
        {
            "pool_key": normalized_pool_key,
            "day_index": normalized_day_index,
            "content": _normalized_text(content),
            "images_json": list(images_json or []),
            "enabled": _normalize_bool(enabled),
        }
    )
    repo.save_sop_pool_config(
        {
            **(_serialize_sop_pool_config(repo.get_sop_pool_config(normalized_pool_key)) or _default_sop_pool_config(normalized_pool_key)),
            "pool_key": normalized_pool_key,
            "enabled": _normalize_bool((_serialize_sop_pool_config(repo.get_sop_pool_config(normalized_pool_key)) or {}).get("enabled", True)),
            "max_day_count": max(_current_sop_template_day_count(normalized_pool_key), normalized_day_index, 1),
            "send_time": _normalize_sop_send_time((_serialize_sop_pool_config(repo.get_sop_pool_config(normalized_pool_key)) or {}).get("send_time")),
            "timezone": SOP_V1_DEFAULT_TIMEZONE,
            "effective_start_at": _normalized_text((_serialize_sop_pool_config(repo.get_sop_pool_config(normalized_pool_key)) or {}).get("effective_start_at")) or _iso_now(),
        }
    )
    get_db().commit()
    return _serialize_sop_template_for_ui(_serialize_sop_template(saved))


def delete_sop_v1_template_day(*, pool_key: str, day_index: int) -> dict[str, Any]:
    normalized_pool_key = _validate_sop_pool_key(pool_key)
    normalized_day_index = max(1, int(day_index or 1))
    ensure_sop_v1_defaults()
    repo.delete_sop_template_day(pool_key=normalized_pool_key, day_index=normalized_day_index)
    if _current_sop_template_day_count(normalized_pool_key) <= 0:
        _ensure_sop_template_day_exists(normalized_pool_key, 1)
    repo.save_sop_pool_config(
        {
            **(_serialize_sop_pool_config(repo.get_sop_pool_config(normalized_pool_key)) or _default_sop_pool_config(normalized_pool_key)),
            "pool_key": normalized_pool_key,
            "enabled": _normalize_bool((_serialize_sop_pool_config(repo.get_sop_pool_config(normalized_pool_key)) or {}).get("enabled", True)),
            "max_day_count": max(_current_sop_template_day_count(normalized_pool_key), 1),
            "send_time": _normalize_sop_send_time((_serialize_sop_pool_config(repo.get_sop_pool_config(normalized_pool_key)) or {}).get("send_time")),
            "timezone": SOP_V1_DEFAULT_TIMEZONE,
            "effective_start_at": _normalized_text((_serialize_sop_pool_config(repo.get_sop_pool_config(normalized_pool_key)) or {}).get("effective_start_at")) or _iso_now(),
        }
    )
    get_db().commit()
    remaining_payload = get_sop_v1_templates_payload(
        normalized_pool_key,
        selected_day_index=min(normalized_day_index, max(_current_sop_template_day_count(normalized_pool_key), 1)),
    )
    return remaining_payload


def _later_timestamp_text(*values: Any) -> str:
    latest: datetime | None = None
    latest_text = ""
    for value in values:
        parsed = _parse_timestamp(value)
        if parsed is None:
            continue
        if latest is None or parsed > latest:
            latest = parsed
            latest_text = parsed.strftime("%Y-%m-%d %H:%M:%S")
    return latest_text


def _sop_effective_start_at(pool_config: dict[str, Any]) -> str:
    return _normalized_text(pool_config.get("effective_start_at")) or _iso_now()


def _sop_anchor_date_from_entry(*, entry_time: str, pool_config: dict[str, Any]) -> tuple[str, str]:
    entry_dt = _parse_timestamp(entry_time) or datetime.now()
    first_effective_dt = entry_dt
    hour, minute = _parse_sop_send_time(pool_config.get("send_time"))
    scheduled_same_day = first_effective_dt.replace(hour=hour, minute=minute, second=0, microsecond=0)
    anchor_dt = first_effective_dt if first_effective_dt < scheduled_same_day else first_effective_dt + timedelta(days=1)
    return anchor_dt.strftime("%Y-%m-%d"), first_effective_dt.strftime("%Y-%m-%d %H:%M:%S")


def _upsert_sop_progress_entry(*, member_id: int, pool_key: str, entered_at: str, pool_config: dict[str, Any] | None = None) -> dict[str, Any]:
    normalized_pool_key = _validate_sop_pool_key(pool_key)
    normalized_pool_config = dict(pool_config or _serialize_sop_pool_config(repo.get_sop_pool_config(normalized_pool_key)) or _default_sop_pool_config(normalized_pool_key))
    entry_time = _normalized_text(entered_at) or _iso_now()
    existing = _serialize_sop_progress(repo.get_sop_progress(member_id=int(member_id), pool_key=normalized_pool_key))
    sop_anchor_date = _normalized_text(existing.get("sop_anchor_date"))
    first_effective_in_pool_at = _normalized_text(existing.get("first_effective_in_pool_at"))
    if not sop_anchor_date or not first_effective_in_pool_at:
        sop_anchor_date, first_effective_in_pool_at = _sop_anchor_date_from_entry(
            entry_time=entry_time,
            pool_config=normalized_pool_config,
        )
    payload = {
        "member_id": int(member_id),
        "pool_key": normalized_pool_key,
        "first_entered_at": existing.get("first_entered_at") or entry_time,
        "last_entered_at": entry_time,
        "sop_anchor_date": sop_anchor_date,
        "first_effective_in_pool_at": first_effective_in_pool_at,
        "last_in_pool_at": entry_time,
        "last_sent_day": int(existing.get("last_sent_day") or 0),
        "last_sent_at": _normalized_text(existing.get("last_sent_at")),
        "completed_at": _normalized_text(existing.get("completed_at")),
    }
    return _serialize_sop_progress(repo.save_sop_progress(payload))


def record_sop_pool_entry(*, member_id: int, pool_key: str, entered_at: str = "") -> dict[str, Any]:
    saved = _upsert_sop_progress_entry(member_id=int(member_id), pool_key=pool_key, entered_at=entered_at)
    get_db().commit()
    return saved


def _focus_batch_status_label(value: str) -> str:
    normalized = _normalized_text(value)
    return {
        "pending": "待执行",
        "running": "执行中",
        "finished": "已完成",
        "cancelled": "已取消",
        "conflict": "冲突",
    }.get(normalized, normalized or "未知")


def _focus_batch_item_status_label(value: str) -> str:
    normalized = _normalized_text(value)
    return {
        "pending": "待执行",
        "running": "执行中",
        "sent": "已发送",
        "failed": "发送失败",
        "skipped": "已跳过",
        "cancelled": "已取消",
    }.get(normalized, normalized or "未知")


def _stage_from_pool(pool: str) -> str:
    return local_projection.stage_from_pool(pool)


def _stage_label(stage: str) -> str:
    return local_projection.stage_label(stage)


def _target_from_pool(pool: str) -> str:
    return local_projection.target_from_pool(pool)


def _target_label(target: str) -> str:
    return local_projection.target_label(target)


def _follow_type_label(value: str) -> str:
    normalized = _normalized_text(value)
    return {"normal": "普通跟进", "focus": "重点跟进"}.get(normalized, "未定")


def _normalized_follow_type_value(value: Any, *, default: str = "") -> str:
    normalized = _normalized_text(value)
    if normalized in {FOLLOWUP_NORMAL, FOLLOWUP_FOCUS}:
        return normalized
    return default


def _resolved_follow_type_for_member(
    member: dict[str, Any] | None,
    questionnaire: dict[str, Any] | None,
    *,
    default: str = "",
) -> str:
    serialized_member = _serialize_member(member or {})
    if _normalized_text(serialized_member.get("decision_source")) == DECISION_SOURCE_MANUAL:
        manual_follow_type = _normalized_follow_type_value(serialized_member.get("follow_type"))
        if manual_follow_type:
            return manual_follow_type
    questionnaire_follow_type = _normalized_follow_type_value((questionnaire or {}).get("resolved_follow_type"))
    if questionnaire_follow_type:
        return questionnaire_follow_type
    return _normalized_follow_type_value(serialized_member.get("follow_type"), default=default)


def _resolved_decision_source_for_member(member: dict[str, Any] | None, questionnaire: dict[str, Any] | None) -> str:
    serialized_member = _serialize_member(member or {})
    if (
        _normalized_text(serialized_member.get("decision_source")) == DECISION_SOURCE_MANUAL
        and _normalized_follow_type_value(serialized_member.get("follow_type"))
    ):
        return DECISION_SOURCE_MANUAL
    if (
        _normalized_text((questionnaire or {}).get("questionnaire_status")) == QUESTIONNAIRE_SUBMITTED
        and _normalized_follow_type_value((questionnaire or {}).get("resolved_follow_type"))
    ):
        return DECISION_SOURCE_QUESTIONNAIRE
    return DECISION_SOURCE_SYSTEM


def _questionnaire_status_label(value: str) -> str:
    normalized = _normalized_text(value)
    return {QUESTIONNAIRE_PENDING: "待提交", QUESTIONNAIRE_SUBMITTED: "已提交"}.get(normalized, "待提交")


def _decision_source_label(value: str) -> str:
    normalized = _normalized_text(value)
    return {
        DECISION_SOURCE_MANUAL: "人工改判",
        DECISION_SOURCE_QUESTIONNAIRE: "问卷初判",
        DECISION_SOURCE_SYSTEM: "系统",
    }.get(normalized, "系统")


def _automation_action_label(value: str) -> str:
    normalized = _normalized_text(value)
    return ACTION_LABELS.get(normalized, normalized or "未知操作")


def _serialize_member(member: dict[str, Any]) -> dict[str, Any]:
    serialized = {
        "id": int(member.get("id") or 0) if member.get("id") not in (None, "") else 0,
        "external_contact_id": _normalized_text(member.get("external_contact_id")),
        "phone": _normalized_text(member.get("phone")),
        "master_customer_id": member.get("master_customer_id"),
        "owner_staff_id": _normalized_text(member.get("owner_staff_id")),
        "in_pool": _normalize_bool(member.get("in_pool")),
        "current_pool": _normalized_text(member.get("current_pool")) or POOL_REMOVED,
        "follow_type": _normalized_follow_type_value(member.get("follow_type")),
        "questionnaire_status": _normalized_text(member.get("questionnaire_status")) or QUESTIONNAIRE_PENDING,
        "decision_source": _normalized_text(member.get("decision_source")) or DECISION_SOURCE_SYSTEM,
        "source_type": _normalized_text(member.get("source_type")) or SOURCE_TYPE_SYSTEM,
        "source_channel_id": member.get("source_channel_id"),
        "last_active_pool": _normalized_text(member.get("last_active_pool")),
        "joined_at": _normalized_text(member.get("joined_at")),
        "last_ai_push_at": _normalized_text(member.get("last_ai_push_at")),
        "ai_cooldown_until": _normalized_text(member.get("ai_cooldown_until")),
        "current_audience_code": _normalized_text(member.get("current_audience_code")),
        "current_audience_entered_at": _normalized_text(member.get("current_audience_entered_at")),
        "created_at": _normalized_text(member.get("created_at")),
        "updated_at": _normalized_text(member.get("updated_at")),
    }
    serialized["current_stage"] = _stage_from_pool(serialized["current_pool"])
    serialized["current_stage_label"] = _stage_label(serialized["current_stage"])
    serialized["current_target"] = _target_from_pool(serialized["current_pool"])
    serialized["current_target_label"] = _target_label(serialized["current_target"])
    serialized["current_pool_label"] = _pool_label(serialized["current_pool"])
    serialized["follow_type_label"] = _follow_type_label(serialized["follow_type"])
    serialized["questionnaire_status_label"] = _questionnaire_status_label(serialized["questionnaire_status"])
    serialized["decision_source_label"] = _decision_source_label(serialized["decision_source"])
    return serialized


def _member_snapshot(member: dict[str, Any]) -> dict[str, Any]:
    serialized = _serialize_member(member)
    return {
        "id": serialized["id"],
        "external_contact_id": serialized["external_contact_id"],
        "phone": serialized["phone"],
        "owner_staff_id": serialized["owner_staff_id"],
        "in_pool": serialized["in_pool"],
        "current_pool": serialized["current_pool"],
        "follow_type": serialized["follow_type"],
        "questionnaire_status": serialized["questionnaire_status"],
        "decision_source": serialized["decision_source"],
        "source_type": serialized["source_type"],
        "source_channel_id": serialized["source_channel_id"],
        "last_active_pool": serialized["last_active_pool"],
        "joined_at": serialized["joined_at"],
        "last_ai_push_at": serialized["last_ai_push_at"],
        "ai_cooldown_until": serialized["ai_cooldown_until"],
        "current_audience_code": serialized["current_audience_code"],
        "current_audience_entered_at": serialized["current_audience_entered_at"],
    }


def _question_answer_text(answer_row: dict[str, Any]) -> str:
    option_texts = _json_loads(answer_row.get("selected_option_texts_snapshot"), default=[])
    if isinstance(option_texts, list):
        normalized = [text for text in (_normalized_text(item) for item in option_texts) if text]
        if normalized:
            return " / ".join(normalized)
    text_value = _normalized_text(answer_row.get("text_value"))
    return text_value or "未填写"


def _resolve_lookup(external_contact_id: str = "", phone: str = "") -> dict[str, Any]:
    normalized_external_contact_id = _normalized_text(external_contact_id)
    normalized_phone = _normalized_text(phone)
    if not normalized_external_contact_id and normalized_phone:
        normalized_external_contact_id = repo.find_latest_external_contact_id_by_phone(normalized_phone)
    person_id = repo.lookup_person_id_by_external_contact_id(normalized_external_contact_id) or repo.lookup_person_id_by_phone(normalized_phone)
    return {
        "external_contact_id": normalized_external_contact_id,
        "phone": normalized_phone,
        "master_customer_id": person_id,
        "external_contact_ids": repo.list_external_contact_ids_by_person_id(person_id) if person_id else ([normalized_external_contact_id] if normalized_external_contact_id else []),
    }


def _load_profile(external_contact_id: str = "", phone: str = "") -> dict[str, Any]:
    from ..admin_console.customer_profile_repo import load_customer_base_profile

    profile = load_customer_base_profile(external_userid=external_contact_id, mobile=phone) or {}
    return {
        "external_contact_id": _normalized_text(profile.get("external_userid")) or _normalized_text(external_contact_id),
        "phone": _normalized_text(profile.get("mobile")) or _normalized_text(phone),
        "customer_name": _normalized_text(profile.get("customer_name")),
        "owner_staff_id": _normalized_text(profile.get("owner_userid")) or _normalized_text(profile.get("owner_display_name")),
        "owner_display_name": _normalized_text(profile.get("owner_display_name")) or _normalized_text(profile.get("owner_userid")),
        "unionid": _normalized_text(profile.get("unionid")),
    }


def _latest_questionnaire_context(external_contact_ids: list[str], phone: str) -> dict[str, Any]:
    def _submitted_context(
        submission: dict[str, Any],
        *,
        questionnaire_id: int | None,
        matched_question_ids: list[int] | None = None,
        matched_questions: list[str] | None = None,
        resolved_follow_type: str = "",
    ) -> dict[str, Any]:
        answer_rows = repo.list_questionnaire_submission_answers(int(submission["id"]))
        answers = [
            {
                "question": _normalized_text(row.get("question_title_snapshot")) or f"问题 {int(row.get('question_id') or 0)}",
                "answer": _question_answer_text(row),
            }
            for row in answer_rows
        ]
        return {
            "questionnaire_status": QUESTIONNAIRE_SUBMITTED,
            "resolved_follow_type": _normalized_follow_type_value(resolved_follow_type),
            "hit_count": len(matched_question_ids or []),
            "matched_question_ids": list(matched_question_ids or []),
            "matched_questions": list(matched_questions or []),
            "answers": answers,
            "submitted_at": _normalized_text(submission.get("submitted_at")),
            "questionnaire_id": questionnaire_id,
            "submission_id": int(submission["id"]),
        }

    settings = get_signup_conversion_config()
    questionnaire_id = settings.get("questionnaire_id")
    if not questionnaire_id:
        any_submission = repo.get_latest_any_questionnaire_submission(
            external_contact_ids=external_contact_ids,
            phone=phone,
        )
        if any_submission:
            return _submitted_context(
                any_submission,
                questionnaire_id=int(any_submission.get("questionnaire_id") or 0) or None,
            )
        return {
            "questionnaire_status": QUESTIONNAIRE_PENDING,
            "resolved_follow_type": "",
            "hit_count": 0,
            "matched_question_ids": [],
            "matched_questions": [],
            "answers": [],
            "submitted_at": "",
            "questionnaire_id": None,
        }
    submission = repo.get_latest_questionnaire_submission(
        questionnaire_id=int(questionnaire_id),
        external_contact_ids=external_contact_ids,
        phone=phone,
    )
    if not submission:
        any_submission = repo.get_latest_any_questionnaire_submission(
            external_contact_ids=external_contact_ids,
            phone=phone,
        )
        if any_submission:
            return _submitted_context(
                any_submission,
                questionnaire_id=int(any_submission.get("questionnaire_id") or 0) or None,
            )
        return {
            "questionnaire_status": QUESTIONNAIRE_PENDING,
            "resolved_follow_type": "",
            "hit_count": 0,
            "matched_question_ids": [],
            "matched_questions": [],
            "answers": [],
            "submitted_at": "",
            "questionnaire_id": int(questionnaire_id),
        }
    answer_rows = repo.list_questionnaire_submission_answers(int(submission["id"]))
    answer_option_map = {
        int(row.get("question_id") or 0): {
            int(option_id)
            for option_id in _json_loads(row.get("selected_option_ids"), default=[])
            if str(option_id).strip()
        }
        for row in answer_rows
    }
    matched_questions: list[str] = []
    matched_question_ids: list[int] = []
    for rule in settings.get("question_rules") or []:
        question_id = int(rule.get("questionnaire_question_id") or 0)
        if question_id <= 0:
            continue
        selected_option_ids = answer_option_map.get(question_id, set())
        hit_option_ids = {
            int(option_id)
            for option_id in rule.get("hit_option_ids_json") or []
            if str(option_id).strip()
        }
        if selected_option_ids and hit_option_ids and selected_option_ids.intersection(hit_option_ids):
            matched_question_ids.append(question_id)
            matched_questions.append(_normalized_text(rule.get("question_title")) or f"问题 {question_id}")
    return _submitted_context(
        submission,
        questionnaire_id=int(questionnaire_id),
        matched_question_ids=matched_question_ids,
        matched_questions=matched_questions,
        resolved_follow_type=FOLLOWUP_FOCUS if len(matched_question_ids) >= int(settings.get("core_threshold") or 0) else FOLLOWUP_NORMAL,
    )


def resolve_member_questionnaire_truth(
    *,
    external_contact_ids: list[str] | None = None,
    phone: str = "",
    member: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved = _latest_questionnaire_context(
        [_normalized_text(item) for item in (external_contact_ids or []) if _normalized_text(item)],
        _normalized_text(phone),
    )
    if resolved.get("questionnaire_id") is not None or member is None:
        return resolved
    fallback_member = _serialize_member(member)
    return {
        "questionnaire_status": _normalized_text(fallback_member.get("questionnaire_status")) or QUESTIONNAIRE_PENDING,
        "resolved_follow_type": _normalized_follow_type_value(fallback_member.get("follow_type")),
        "hit_count": 0,
        "matched_question_ids": [],
        "matched_questions": [],
        "answers": [],
        "submitted_at": "",
        "questionnaire_id": None,
    }


def _build_live_context(external_contact_id: str = "", phone: str = "") -> dict[str, Any]:
    lookup = _resolve_lookup(external_contact_id=external_contact_id, phone=phone)
    profile = _load_profile(lookup["external_contact_id"], lookup["phone"])
    resolved_external_contact_id = _normalized_text(profile.get("external_contact_id")) or lookup["external_contact_id"]
    resolved_phone = _normalized_text(profile.get("phone")) or lookup["phone"]
    external_contact_ids = list(dict.fromkeys([item for item in lookup["external_contact_ids"] + [resolved_external_contact_id] if _normalized_text(item)]))
    questionnaire = resolve_member_questionnaire_truth(external_contact_ids=external_contact_ids, phone=resolved_phone)
    return {
        "lookup": {**lookup, "external_contact_ids": external_contact_ids},
        "profile": profile,
        "questionnaire": questionnaire,
    }


def recompute_pool(member: dict[str, Any], context: dict[str, Any], *, action: str = "") -> str:
    current_pool = _normalized_text(member.get("current_pool"))
    if current_pool == POOL_WON and action != "unmark_won":
        return POOL_WON
    if current_pool in {POOL_NO_REPLY, POOL_HUMAN_REPLY} and action not in {
        "put_in_pool",
        "set_focus",
        "set_normal",
        "mark_won",
        "unmark_won",
        "remove_from_pool",
    }:
        return current_pool
    if not _normalize_bool(member.get("in_pool")):
        return POOL_REMOVED
    questionnaire_status = _normalized_text(member.get("questionnaire_status")) or QUESTIONNAIRE_PENDING
    if questionnaire_status != QUESTIONNAIRE_SUBMITTED:
        return POOL_PENDING_QUESTIONNAIRE
    return POOL_OPERATING


def _member_payload_from_context(
    existing: dict[str, Any] | None,
    context: dict[str, Any],
    *,
    source_type: str = "",
    source_channel_id: int | None = None,
    in_pool: bool | None = None,
) -> dict[str, Any]:
    existing_row = _serialize_member(existing or {})
    profile = context["profile"]
    questionnaire = context["questionnaire"]
    lookup = context["lookup"]
    resolved_follow_type = _resolved_follow_type_for_member(existing_row, questionnaire)
    base_payload = {
        "external_contact_id": _normalized_text(profile.get("external_contact_id")) or existing_row.get("external_contact_id") or lookup.get("external_contact_id"),
        "phone": _normalized_text(profile.get("phone")) or existing_row.get("phone") or lookup.get("phone"),
        "master_customer_id": lookup.get("master_customer_id") or existing_row.get("master_customer_id"),
        "owner_staff_id": _normalized_text(existing_row.get("owner_staff_id")) or _normalized_text(profile.get("owner_staff_id")) or DEFAULT_OWNER_STAFF_ID,
        "in_pool": existing_row.get("in_pool") if in_pool is None else bool(in_pool),
        "current_pool": existing_row.get("current_pool") or POOL_REMOVED,
        "follow_type": resolved_follow_type,
        "questionnaire_status": _normalized_text(questionnaire.get("questionnaire_status")) or existing_row.get("questionnaire_status") or QUESTIONNAIRE_PENDING,
        "decision_source": _resolved_decision_source_for_member(existing_row, questionnaire),
        "source_type": _normalized_text(source_type) or existing_row.get("source_type") or SOURCE_TYPE_SYSTEM,
        "source_channel_id": source_channel_id if source_channel_id is not None else existing_row.get("source_channel_id"),
        "last_active_pool": _normalized_text(existing_row.get("last_active_pool")),
        "joined_at": _normalized_text(existing_row.get("joined_at")),
        "updated_at": _normalized_text(existing_row.get("updated_at")),
        "last_ai_push_at": _normalized_text(existing_row.get("last_ai_push_at")),
        "ai_cooldown_until": _normalized_text(existing_row.get("ai_cooldown_until")),
    }
    return base_payload


def _substantive_member_changed(before: dict[str, Any], after: dict[str, Any]) -> bool:
    tracked_fields = (
        "external_contact_id",
        "phone",
        "master_customer_id",
        "owner_staff_id",
        "in_pool",
        "current_pool",
        "follow_type",
        "questionnaire_status",
        "decision_source",
        "source_type",
        "source_channel_id",
        "last_active_pool",
        "joined_at",
        "last_ai_push_at",
        "ai_cooldown_until",
        "current_audience_code",
        "current_audience_entered_at",
    )
    return any(before.get(field) != after.get(field) for field in tracked_fields)


def _sync_sop_progress_for_transition(before: dict[str, Any], after: dict[str, Any]) -> None:
    before_pool = _normalized_text(before.get("current_pool")) if _normalize_bool(before.get("in_pool")) else ""
    after_pool = _normalized_text(after.get("current_pool")) if _normalize_bool(after.get("in_pool")) else ""
    if after_pool not in SOP_V1_ALLOWED_POOLS:
        return
    if before_pool == after_pool and int(before.get("id") or 0) == int(after.get("id") or 0):
        return
    _upsert_sop_progress_entry(
        member_id=int(after.get("id") or 0),
        pool_key=after_pool,
        entered_at=_normalized_text(after.get("updated_at")) or _iso_now(),
    )


def _sync_sop_progress_for_transition_non_blocking(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    try:
        _sync_sop_progress_for_transition(before, after)
        get_db().commit()
        return {"attempted": True, "ok": True, "error": ""}
    except Exception as exc:
        get_db().rollback()
        current_app.logger.exception(
            "automation conversion sop progress sync failed member_id=%s before_pool=%s after_pool=%s",
            int(after.get("id") or 0),
            _normalized_text(before.get("current_pool")),
            _normalized_text(after.get("current_pool")),
        )
        return {"attempted": True, "ok": False, "error": str(exc)}


def _persist_member(member: dict[str, Any] | None, payload: dict[str, Any]) -> dict[str, Any]:
    db = get_db()
    try:
        before = _serialize_member(member or {})
        if member and member.get("id"):
            saved = repo.update_member(int(member["id"]), payload)
        else:
            saved = repo.insert_member(payload)
        from .workflow_runtime import sync_conversion_member_audience

        sync_conversion_member_audience(saved)
        saved = repo.get_member_by_id(int(saved["id"])) or saved
        db.commit()
    except Exception:
        db.rollback()
        raise
    _sync_sop_progress_for_transition_non_blocking(before, _serialize_member(saved))
    return repo.get_member_by_id(int(saved["id"])) or saved


def _write_event(
    *,
    member_id: int,
    action: str,
    operator_type: str,
    operator_id: str,
    before_snapshot: dict[str, Any],
    after_snapshot: dict[str, Any],
    remark: str = "",
) -> dict[str, Any]:
    db = get_db()
    try:
        saved = repo.insert_event(
            member_id=int(member_id),
            action=action,
            operator_type=operator_type,
            operator_id=operator_id,
            before_snapshot=before_snapshot,
            after_snapshot=after_snapshot,
            remark=remark,
        )
        db.commit()
        return saved
    except Exception:
        db.rollback()
        raise


def _send_channel_welcome_message(
    *,
    member: dict[str, Any],
    channel: dict[str, Any],
    payload_json: dict[str, Any] | None = None,
    operator_id: str = "",
) -> dict[str, Any]:
    welcome_message = _normalized_text(channel.get("welcome_message"))
    payload = _json_loads(payload_json, default={})
    if not isinstance(payload, dict):
        payload = {}
    welcome_code = ""
    for key in ("WelcomeCode", "welcome_code", "welcomeCode"):
        welcome_code = _normalized_text(payload.get(key))
        if welcome_code:
            break
    if not welcome_message:
        return {"attempted": False, "sent": False, "reason": "not_configured"}
    if not welcome_code:
        return {"attempted": False, "sent": False, "reason": "welcome_code_missing"}
    serialized_member = _serialize_member(member)
    request_payload = {
        "welcome_code": welcome_code,
        "text": {"content": welcome_message},
    }
    try:
        wecom_result = get_contact_runtime_client().send_welcome_msg(request_payload)
    except (WeComClientError, AttributeError, ValueError) as exc:
        _write_event(
            member_id=int(member["id"]),
            action="qrcode_welcome_failed",
            operator_type="system",
            operator_id=_normalized_text(operator_id) or "wecom_callback",
            before_snapshot=_member_snapshot(serialized_member),
            after_snapshot=_member_snapshot(serialized_member),
            remark=str(exc),
        )
        return {"attempted": True, "sent": False, "error": str(exc)}

    _write_event(
        member_id=int(member["id"]),
        action="qrcode_welcome_sent",
        operator_type="system",
        operator_id=_normalized_text(operator_id) or "wecom_callback",
        before_snapshot=_member_snapshot(serialized_member),
        after_snapshot=_member_snapshot(serialized_member),
        remark="official_send_welcome_msg",
    )
    return {
        "attempted": True,
        "sent": True,
        "via": "send_welcome_msg",
        "wecom_result": dict(wecom_result or {}),
    }


def _touch_member_from_sources(
    member: dict[str, Any],
    *,
    action: str,
    operator_type: str = "system",
    operator_id: str = "system",
    persist_event: bool = False,
) -> dict[str, Any]:
    serialized_before = _serialize_member(member)
    context = _build_live_context(serialized_before["external_contact_id"], serialized_before["phone"])
    next_payload = _member_payload_from_context(member, {**context, "settings": get_signup_conversion_config()})
    next_payload["joined_at"] = serialized_before.get("joined_at") or _iso_now()
    next_payload["current_pool"] = recompute_pool(next_payload, {**context, "settings": get_signup_conversion_config()}, action=action)
    if not _substantive_member_changed(serialized_before, next_payload):
        return member
    saved = _persist_member(member, next_payload)
    if persist_event:
        _write_event(
            member_id=int(saved["id"]),
            action=action,
            operator_type=operator_type,
            operator_id=operator_id,
            before_snapshot=_member_snapshot(serialized_before),
            after_snapshot=_member_snapshot(saved),
        )
    return saved


def refresh_expired_silent_members() -> dict[str, Any]:
    return {"refreshed_count": 0}


def _message_activity_pool(*, questionnaire_status: str) -> str:
    return POOL_OPERATING if _normalized_text(questionnaire_status) == QUESTIONNAIRE_SUBMITTED else POOL_PENDING_QUESTIONNAIRE


def _inactive_follow_type_from_member(before: dict[str, Any]) -> tuple[str, str, bool]:
    manual_preserved = (
        _normalized_text(before.get("decision_source")) == DECISION_SOURCE_MANUAL
        and _normalized_text(before.get("follow_type")) in {FOLLOWUP_NORMAL, FOLLOWUP_FOCUS}
    )
    if manual_preserved:
        return _normalized_text(before.get("follow_type")), _normalized_text(before.get("decision_source")) or DECISION_SOURCE_MANUAL, True
    questionnaire = resolve_member_questionnaire_truth(
        external_contact_ids=[_normalized_text(before.get("external_contact_id"))] if _normalized_text(before.get("external_contact_id")) else [],
        phone=_normalized_text(before.get("phone")),
        member=before,
    )
    next_follow_type = _resolved_follow_type_for_member(before, questionnaire, default=FOLLOWUP_NORMAL)
    next_decision_source = _resolved_decision_source_for_member(before, questionnaire)
    return next_follow_type, next_decision_source, False


def _message_activity_item_status_label(value: str) -> str:
    normalized = _normalized_text(value)
    return {
        "updated": "已更新",
        "unchanged": "无变化",
        "skipped_ambiguous": "匹配键冲突跳过",
        "skipped_unmatched": "未匹配跳过",
        "skipped_missing_phone": "手机号缺失跳过",
    }.get(normalized, normalized or "未知")


def _message_activity_sync_run_status_label(value: str) -> str:
    normalized = _normalized_text(value)
    return {
        "success": "成功",
        "failed": "失败",
        "running": "执行中",
    }.get(normalized, normalized or "暂无记录")


def _serialize_message_activity_sync_item(row: dict[str, Any]) -> dict[str, Any]:
    deserialized = repo.deserialize_message_activity_sync_item_row(row)
    return {
        "id": int(deserialized.get("id") or 0),
        "run_id": int(deserialized.get("run_id") or 0),
        "member_id": int(deserialized.get("member_id") or 0) if deserialized.get("member_id") not in (None, "") else 0,
        "external_contact_id": _normalized_text(deserialized.get("external_contact_id")),
        "phone": _normalized_text(deserialized.get("phone")),
        "phone_prefix3": _normalized_text(deserialized.get("phone_prefix3")),
        "phone_last4": _normalized_text(deserialized.get("phone_last4")),
        "phone_match_key": _normalized_text(deserialized.get("phone_match_key")),
        "message_count": int(deserialized.get("message_count") or 0),
        "status": _normalized_text(deserialized.get("status")),
        "status_label": _message_activity_item_status_label(deserialized.get("status")),
        "detail": _normalized_text(deserialized.get("detail")),
        "before_snapshot": deserialized.get("before_snapshot") or {},
        "after_snapshot": deserialized.get("after_snapshot") or {},
        "created_at": _normalized_text(deserialized.get("created_at")),
    }


def _serialize_message_activity_sync_run(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    deserialized = repo.deserialize_message_activity_sync_run_row(row)
    summary = dict(deserialized.get("summary_json") or {})
    skipped_ambiguous_count = int(deserialized.get("skipped_ambiguous_count") or 0)
    skipped_unmatched_count = int(deserialized.get("skipped_unmatched_count") or 0)
    skipped_missing_phone_count = int(deserialized.get("skipped_missing_phone_count") or 0)
    return {
        "id": int(deserialized.get("id") or 0),
        "trigger_source": _normalized_text(deserialized.get("trigger_source")),
        "operator_type": _normalized_text(deserialized.get("operator_type")),
        "operator_id": _normalized_text(deserialized.get("operator_id")),
        "status": _normalized_text(deserialized.get("status")),
        "status_label": _message_activity_sync_run_status_label(deserialized.get("status")),
        "candidate_count": int(deserialized.get("candidate_count") or 0),
        "matched_count": int(deserialized.get("matched_count") or 0),
        "updated_count": int(deserialized.get("updated_count") or 0),
        "skipped_ambiguous_count": skipped_ambiguous_count,
        "skipped_unmatched_count": skipped_unmatched_count,
        "skipped_missing_phone_count": skipped_missing_phone_count,
        "skipped_count": skipped_ambiguous_count + skipped_unmatched_count + skipped_missing_phone_count,
        "focus_count": int(deserialized.get("focus_count") or 0),
        "normal_count": int(deserialized.get("normal_count") or 0),
        "error_message": _normalized_text(deserialized.get("error_message")),
        "started_at": _normalized_text(deserialized.get("started_at")),
        "finished_at": _normalized_text(deserialized.get("finished_at")),
        "summary": summary,
    }


def _serialize_focus_send_batch_item(row: dict[str, Any]) -> dict[str, Any]:
    deserialized = repo.deserialize_focus_send_batch_item_row(row)
    return {
        "id": int(deserialized.get("id") or 0),
        "batch_id": int(deserialized.get("batch_id") or 0),
        "member_id": int(deserialized.get("member_id") or 0) if deserialized.get("member_id") not in (None, "") else 0,
        "external_contact_id": _normalized_text(deserialized.get("external_contact_id")),
        "phone": _normalized_text(deserialized.get("phone")),
        "position_index": int(deserialized.get("position_index") or 0),
        "status": _normalized_text(deserialized.get("status")),
        "status_label": _focus_batch_item_status_label(deserialized.get("status")),
        "detail": _normalized_text(deserialized.get("detail")),
        "result_payload": deserialized.get("result_payload") or {},
        "created_at": _normalized_text(deserialized.get("created_at")),
        "updated_at": _normalized_text(deserialized.get("updated_at")),
        "started_at": _normalized_text(deserialized.get("started_at")),
        "finished_at": _normalized_text(deserialized.get("finished_at")),
    }


def _serialize_focus_send_batch(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    deserialized = repo.deserialize_focus_send_batch_row(row)
    total_count = int(deserialized.get("total_count") or 0)
    sent_count = int(deserialized.get("sent_count") or 0)
    failed_count = int(deserialized.get("failed_count") or 0)
    skipped_count = int(deserialized.get("skipped_count") or 0)
    cancelled_count = int(deserialized.get("cancelled_count") or 0)
    remaining_count = max(0, total_count - sent_count - failed_count - skipped_count - cancelled_count)
    return {
        "id": int(deserialized.get("id") or 0),
        "stage_key": _normalized_text(deserialized.get("stage_key")),
        "pool_key": _normalized_text(deserialized.get("pool_key")),
        "operator_type": _normalized_text(deserialized.get("operator_type")),
        "operator_id": _normalized_text(deserialized.get("operator_id")),
        "status": _normalized_text(deserialized.get("status")),
        "status_label": _focus_batch_status_label(deserialized.get("status")),
        "total_count": total_count,
        "sent_count": sent_count,
        "failed_count": failed_count,
        "skipped_count": skipped_count,
        "cancelled_count": cancelled_count,
        "remaining_count": remaining_count,
        "next_run_at": _normalized_text(deserialized.get("next_run_at")),
        "last_run_at": _normalized_text(deserialized.get("last_run_at")),
        "created_at": _normalized_text(deserialized.get("created_at")),
        "updated_at": _normalized_text(deserialized.get("updated_at")),
        "finished_at": _normalized_text(deserialized.get("finished_at")),
    }


def _message_activity_sync_status_payload() -> dict[str, Any]:
    db_status = get_message_activity_db_status()
    last_run_row = repo.get_latest_message_activity_sync_run()
    last_run = _serialize_message_activity_sync_run(last_run_row)
    if (
        not db_status["configured"]
        and _normalized_text(last_run.get("error_message")) == "message activity db is not configured"
    ):
        last_run = {
            **last_run,
            "status": "not_configured",
            "status_label": _message_activity_sync_run_status_label("not_configured"),
            "finished_at": "",
            "error_message": "",
        }
    recent_items = (
        [_serialize_message_activity_sync_item(item) for item in repo.list_message_activity_sync_items(run_id=int(last_run["id"]), limit=12)]
        if last_run
        else []
    )
    return {
        "db_status": db_status,
        "scope_pools": [
            {"pool": pool, "label": _pool_label(pool)}
            for pool in MESSAGE_ACTIVITY_SYNC_POOLS
        ],
        "cron_script_path": _normalized_text(current_app.config.get("MESSAGE_ACTIVITY_SYNC_CRON_SCRIPT_PATH")),
        "last_run": last_run,
        "recent_items": recent_items,
    }


def _reply_monitor_status_label(value: str) -> str:
    normalized = _normalized_text(value)
    return {
        "idle": "空闲",
        "disabled": "已关闭",
        "success": "成功",
        "failed": "失败",
        "running": "执行中",
        "not_configured": "未配置",
    }.get(normalized, normalized or "暂无记录")


def _reply_monitor_queue_status_label(value: str) -> str:
    normalized = _normalized_text(value)
    return {
        REPLY_MONITOR_STATUS_PENDING: "待触发",
        REPLY_MONITOR_STATUS_DEFERRED: "夜间暂缓",
        REPLY_MONITOR_STATUS_DISPATCHED: "已触发",
        REPLY_MONITOR_STATUS_FAILED: "触发失败",
        REPLY_MONITOR_STATUS_PAUSED: "已暂停",
    }.get(normalized, normalized or "未知")


def _reply_monitor_default_config() -> dict[str, Any]:
    return {
        "enabled": False,
        "last_capture_cursor": 0,
        "last_capture_at": "",
        "last_capture_status": "disabled",
        "last_capture_summary_json": {},
        "last_dispatch_at": "",
        "last_dispatch_status": "disabled",
        "last_dispatch_summary_json": {},
        "last_error": "",
        "quiet_hours_start": REPLY_MONITOR_DEFAULT_QUIET_HOURS_START,
        "quiet_hours_end": REPLY_MONITOR_DEFAULT_QUIET_HOURS_END,
        "dispatch_interval_seconds": REPLY_MONITOR_DEFAULT_DISPATCH_INTERVAL_SECONDS,
    }


def _reply_monitor_config() -> dict[str, Any]:
    row = repo.get_reply_monitor_config()
    base = _reply_monitor_default_config()
    if not row:
        return dict(base)
    deserialized = repo.deserialize_reply_monitor_config_row(row)
    return {
        **base,
        **deserialized,
        "enabled": _normalize_bool(deserialized.get("enabled")),
        "last_capture_cursor": int(deserialized.get("last_capture_cursor") or 0),
        "last_capture_summary_json": dict(deserialized.get("last_capture_summary_json") or {}),
        "last_dispatch_summary_json": dict(deserialized.get("last_dispatch_summary_json") or {}),
        "quiet_hours_start": _normalized_text(deserialized.get("quiet_hours_start")) or REPLY_MONITOR_DEFAULT_QUIET_HOURS_START,
        "quiet_hours_end": _normalized_text(deserialized.get("quiet_hours_end")) or REPLY_MONITOR_DEFAULT_QUIET_HOURS_END,
        "dispatch_interval_seconds": int(deserialized.get("dispatch_interval_seconds") or REPLY_MONITOR_DEFAULT_DISPATCH_INTERVAL_SECONDS),
    }


def _save_reply_monitor_config(payload: dict[str, Any]) -> dict[str, Any]:
    current = _reply_monitor_config()
    merged = {
        **current,
        **payload,
        "enabled": _normalize_bool(payload.get("enabled", current.get("enabled"))),
        "last_capture_cursor": int(payload.get("last_capture_cursor", current.get("last_capture_cursor") or 0) or 0),
        "last_capture_summary_json": payload.get("last_capture_summary_json", current.get("last_capture_summary_json") or {}),
        "last_dispatch_summary_json": payload.get("last_dispatch_summary_json", current.get("last_dispatch_summary_json") or {}),
        "quiet_hours_start": _normalized_text(payload.get("quiet_hours_start", current.get("quiet_hours_start"))) or REPLY_MONITOR_DEFAULT_QUIET_HOURS_START,
        "quiet_hours_end": _normalized_text(payload.get("quiet_hours_end", current.get("quiet_hours_end"))) or REPLY_MONITOR_DEFAULT_QUIET_HOURS_END,
        "dispatch_interval_seconds": int(payload.get("dispatch_interval_seconds", current.get("dispatch_interval_seconds") or REPLY_MONITOR_DEFAULT_DISPATCH_INTERVAL_SECONDS) or REPLY_MONITOR_DEFAULT_DISPATCH_INTERVAL_SECONDS),
    }
    saved = repo.save_reply_monitor_config(merged)
    get_db().commit()
    return _reply_monitor_config() if not saved else {
        **_reply_monitor_default_config(),
        **repo.deserialize_reply_monitor_config_row(saved),
        "enabled": _normalize_bool(saved.get("enabled")),
        "last_capture_cursor": int(saved.get("last_capture_cursor") or 0),
        "last_capture_summary_json": dict(repo.deserialize_reply_monitor_config_row(saved).get("last_capture_summary_json") or {}),
        "last_dispatch_summary_json": dict(repo.deserialize_reply_monitor_config_row(saved).get("last_dispatch_summary_json") or {}),
        "quiet_hours_start": _normalized_text(saved.get("quiet_hours_start")) or REPLY_MONITOR_DEFAULT_QUIET_HOURS_START,
        "quiet_hours_end": _normalized_text(saved.get("quiet_hours_end")) or REPLY_MONITOR_DEFAULT_QUIET_HOURS_END,
        "dispatch_interval_seconds": int(saved.get("dispatch_interval_seconds") or REPLY_MONITOR_DEFAULT_DISPATCH_INTERVAL_SECONDS),
    }


def _serialize_reply_monitor_queue_item(row: dict[str, Any]) -> dict[str, Any]:
    deserialized = repo.deserialize_reply_monitor_queue_row(row)
    return {
        "id": int(deserialized.get("id") or 0),
        "member_id": int(deserialized.get("member_id") or 0) if deserialized.get("member_id") not in (None, "") else 0,
        "external_userid": _normalized_text(deserialized.get("external_userid")),
        "owner_userid": _normalized_text(deserialized.get("owner_userid")),
        "status": _normalized_text(deserialized.get("status")),
        "status_label": _reply_monitor_queue_status_label(deserialized.get("status")),
        "message_ids": [int(item) for item in list(deserialized.get("message_ids_json") or []) if str(item).strip()],
        "message_count": int(deserialized.get("message_count") or 0),
        "first_inbound_at": _normalized_text(deserialized.get("first_inbound_at")),
        "last_inbound_at": _normalized_text(deserialized.get("last_inbound_at")),
        "not_before": _normalized_text(deserialized.get("not_before")),
        "last_dispatch_at": _normalized_text(deserialized.get("last_dispatch_at")),
        "error_message": _normalized_text(deserialized.get("error_message")),
        "payload_snapshot": dict(deserialized.get("payload_snapshot_json") or {}),
        "created_at": _normalized_text(deserialized.get("created_at")),
        "updated_at": _normalized_text(deserialized.get("updated_at")),
    }


def _reply_monitor_status_payload() -> dict[str, Any]:
    config = _reply_monitor_config()
    queue_counts = repo.get_reply_monitor_queue_counts()
    recent_items = [_serialize_reply_monitor_queue_item(item) for item in repo.list_recent_reply_monitor_queue_items(limit=12)]
    enabled = _normalize_bool(config.get("enabled"))
    last_capture_status = _normalized_text(config.get("last_capture_status")) or ("disabled" if not enabled else "idle")
    last_dispatch_status = _normalized_text(config.get("last_dispatch_status")) or ("disabled" if not enabled else "idle")
    return {
        "enabled": enabled,
        "status": "enabled" if enabled else "disabled",
        "status_label": "开启中" if enabled else "已关闭",
        "description": "开启后自动监控自动化范围内用户的新私聊消息；夜间只入队不触发；关闭后停止自动触发但不影响聊天入库。",
        "last_capture_cursor": int(config.get("last_capture_cursor") or 0),
        "last_capture_at": _normalized_text(config.get("last_capture_at")),
        "last_capture_status": last_capture_status,
        "last_capture_status_label": _reply_monitor_status_label(last_capture_status),
        "last_capture_summary": dict(config.get("last_capture_summary_json") or {}),
        "last_dispatch_at": _normalized_text(config.get("last_dispatch_at")),
        "last_dispatch_status": last_dispatch_status,
        "last_dispatch_status_label": _reply_monitor_status_label(last_dispatch_status),
        "last_dispatch_summary": dict(config.get("last_dispatch_summary_json") or {}),
        "last_error": _normalized_text(config.get("last_error")),
        "quiet_hours_start": _normalized_text(config.get("quiet_hours_start")) or REPLY_MONITOR_DEFAULT_QUIET_HOURS_START,
        "quiet_hours_end": _normalized_text(config.get("quiet_hours_end")) or REPLY_MONITOR_DEFAULT_QUIET_HOURS_END,
        "dispatch_interval_seconds": int(config.get("dispatch_interval_seconds") or REPLY_MONITOR_DEFAULT_DISPATCH_INTERVAL_SECONDS),
        "queue_counts": queue_counts,
        "recent_items": recent_items,
    }


def _parse_clock_minutes(value: str, *, default_minutes: int) -> int:
    text = _normalized_text(value)
    if not text:
        return default_minutes
    try:
        parsed = datetime.strptime(text, "%H:%M")
    except ValueError:
        return default_minutes
    return parsed.hour * 60 + parsed.minute


def _is_reply_monitor_quiet_hours(config: dict[str, Any], *, now: datetime | None = None) -> bool:
    current = now or datetime.now()
    current_minutes = current.hour * 60 + current.minute
    start_minutes = _parse_clock_minutes(
        _normalized_text(config.get("quiet_hours_start")),
        default_minutes=23 * 60,
    )
    end_minutes = _parse_clock_minutes(
        _normalized_text(config.get("quiet_hours_end")),
        default_minutes=9 * 60,
    )
    if start_minutes == end_minutes:
        return False
    if start_minutes < end_minutes:
        return start_minutes <= current_minutes < end_minutes
    return current_minutes >= start_minutes or current_minutes < end_minutes


def _next_reply_monitor_daytime_start(config: dict[str, Any], *, now: datetime | None = None) -> datetime:
    current = now or datetime.now()
    end_minutes = _parse_clock_minutes(
        _normalized_text(config.get("quiet_hours_end")),
        default_minutes=9 * 60,
    )
    next_start = current.replace(hour=end_minutes // 60, minute=end_minutes % 60, second=0, microsecond=0)
    if _is_reply_monitor_quiet_hours(config, now=current):
        current_minutes = current.hour * 60 + current.minute
        if current_minutes >= _parse_clock_minutes(_normalized_text(config.get("quiet_hours_start")), default_minutes=23 * 60):
            next_start += timedelta(days=1)
    elif next_start <= current:
        next_start += timedelta(days=1)
    return next_start


def _reply_monitor_next_dispatch_dt(config: dict[str, Any], *, now_dt: datetime, seed_dt: datetime | None = None) -> datetime:
    interval_seconds = max(1, int(config.get("dispatch_interval_seconds") or REPLY_MONITOR_DEFAULT_DISPATCH_INTERVAL_SECONDS))
    latest_not_before_dt = _parse_timestamp(repo.get_latest_reply_monitor_not_before())
    last_dispatch_dt = _parse_timestamp(config.get("last_dispatch_at"))
    candidates = [now_dt]
    if seed_dt:
        candidates.append(seed_dt)
    if latest_not_before_dt:
        candidates.append(latest_not_before_dt)
    if last_dispatch_dt:
        candidates.append(last_dispatch_dt + timedelta(seconds=interval_seconds))
    next_dt = max(candidates)
    if _is_reply_monitor_quiet_hours(config, now=next_dt):
        next_dt = _next_reply_monitor_daytime_start(config, now=next_dt)
    return next_dt


def _build_reply_monitor_recent_messages(messages: list[dict[str, Any]], *, external_contact_id: str) -> list[dict[str, Any]]:
    normalized_external_contact_id = _normalized_text(external_contact_id)
    normalized_messages: list[dict[str, Any]] = []
    for item in list(messages or [])[-20:]:
        sender = _normalized_text(item.get("sender"))
        normalized_messages.append(
            {
                "role": "customer" if sender == normalized_external_contact_id else "staff",
                "content": _normalized_text(item.get("content")),
                "created_at": _normalized_text(item.get("send_time")),
            }
        )
    return normalized_messages


def save_reply_monitor_enabled(*, enabled: bool, operator_id: str = "") -> dict[str, Any]:
    current = _reply_monitor_config()
    next_enabled = _normalize_bool(enabled)
    payload = {
        "enabled": next_enabled,
        "last_error": "",
    }
    if next_enabled and not _normalize_bool(current.get("enabled")):
        payload["last_capture_cursor"] = repo.get_latest_archived_message_storage_id()
        payload["last_capture_at"] = _iso_now()
        payload["last_capture_status"] = "idle"
        payload["last_capture_summary_json"] = {
            "reset_reason": "enabled_from_current_cursor",
            "cursor": int(payload["last_capture_cursor"]),
        }
        payload["last_dispatch_status"] = "idle"
    if not next_enabled:
        payload["last_capture_status"] = "disabled"
        payload["last_dispatch_status"] = "disabled"
    config = _save_reply_monitor_config(payload)
    return _reply_monitor_status_payload() if config else _reply_monitor_status_payload()


def _reply_monitor_candidate_message(message: dict[str, Any]) -> bool:
    if _normalized_text(message.get("chat_type")) != "private":
        return False
    external_userid = _normalized_text(message.get("external_userid"))
    owner_userid = _normalized_text(message.get("owner_userid"))
    if not external_userid or not owner_userid:
        return False
    if _normalized_text(message.get("sender")) != external_userid:
        return False
    receiver = _normalized_text(message.get("receiver"))
    if receiver and receiver != owner_userid:
        return False
    if _normalized_text(message.get("msgtype")) in {"event", "revoke", "calendar", "vote"}:
        return False
    return True


def _safe_timestamp_min(*values: Any) -> str:
    candidates = [item for item in (_parse_timestamp(value) for value in values) if item is not None]
    if not candidates:
        return _normalized_text(values[0] if values else "")
    return min(candidates).strftime("%Y-%m-%d %H:%M:%S")


def _safe_timestamp_max(*values: Any) -> str:
    candidates = [item for item in (_parse_timestamp(value) for value in values) if item is not None]
    if not candidates:
        return _normalized_text(values[0] if values else "")
    return max(candidates).strftime("%Y-%m-%d %H:%M:%S")


def run_reply_monitor_capture(
    *,
    operator_id: str = "",
    operator_type: str = "system",
    limit: int = 500,
) -> dict[str, Any]:
    config = _reply_monitor_config()
    if not _normalize_bool(config.get("enabled")):
        return {
            "ok": False,
            "status": "disabled",
            "error": "reply monitor is disabled",
            "reply_monitor": _reply_monitor_status_payload(),
        }
    now_text = _iso_now()
    now_dt = _parse_timestamp(now_text) or datetime.now()
    after_cursor = int(config.get("last_capture_cursor") or 0)
    scanned_rows = repo.list_archived_messages_after_storage_cursor(after_id=after_cursor, limit=max(1, min(int(limit), 1000)))
    latest_cursor = max([after_cursor] + [int(item.get("id") or 0) for item in scanned_rows])
    candidate_rows = [dict(item) for item in scanned_rows if _reply_monitor_candidate_message(item)]
    active_members = repo.list_active_automation_members_by_external_contact_ids(
        list({ _normalized_text(item.get("external_userid")) for item in candidate_rows if _normalized_text(item.get("external_userid")) })
    )
    member_by_external = {
        _normalized_text(item.get("external_contact_id")): _serialize_member(item)
        for item in active_members
        if _normalized_text(item.get("external_contact_id"))
    }
    grouped_messages: dict[str, list[dict[str, Any]]] = {}
    message_owner_userids: dict[str, str] = {}
    for row in candidate_rows:
        external_userid = _normalized_text(row.get("external_userid"))
        member = member_by_external.get(external_userid)
        if not member:
            continue
        grouped_messages.setdefault(external_userid, []).append(dict(row))
        message_owner_userids[external_userid] = _normalized_text(row.get("owner_userid")) or _normalized_text(member.get("owner_staff_id"))

    created_count = 0
    merged_count = 0
    processed_users = 0
    seed_dt = _reply_monitor_next_dispatch_dt(config, now_dt=now_dt)
    quiet_now = _is_reply_monitor_quiet_hours(config, now=now_dt)
    for external_userid, message_rows in sorted(grouped_messages.items(), key=lambda item: int((item[1][0].get("id") or 0))):
        member = member_by_external[external_userid]
        owner_userid = message_owner_userids.get(external_userid) or _normalized_text(member.get("owner_staff_id"))
        message_ids = [int(item.get("id") or 0) for item in message_rows if int(item.get("id") or 0) > 0]
        if not message_ids:
            continue
        processed_users += 1
        existing = repo.get_active_reply_monitor_queue_item(external_userid)
        if existing:
            serialized_existing = _serialize_reply_monitor_queue_item(existing)
            merged_ids = sorted(set(list(serialized_existing.get("message_ids") or []) + message_ids))
            status = serialized_existing["status"]
            not_before = serialized_existing["not_before"]
            if status != REPLY_MONITOR_STATUS_PAUSED:
                if _is_reply_monitor_quiet_hours(config, now=now_dt):
                    status = REPLY_MONITOR_STATUS_DEFERRED
                    not_before = _safe_timestamp_max(not_before, _next_reply_monitor_daytime_start(config, now=now_dt).strftime("%Y-%m-%d %H:%M:%S"))
                else:
                    status = REPLY_MONITOR_STATUS_PENDING
                    not_before = not_before or seed_dt.strftime("%Y-%m-%d %H:%M:%S")
            repo.update_reply_monitor_queue_item(
                int(serialized_existing["id"]),
                {
                    "member_id": int(member.get("id") or 0) or None,
                    "external_userid": external_userid,
                    "owner_userid": owner_userid,
                    "status": status,
                    "message_ids_json": merged_ids,
                    "message_count": len(merged_ids),
                    "first_inbound_at": _safe_timestamp_min(serialized_existing.get("first_inbound_at"), *(item.get("send_time") for item in message_rows)),
                    "last_inbound_at": _safe_timestamp_max(serialized_existing.get("last_inbound_at"), *(item.get("send_time") for item in message_rows)),
                    "not_before": not_before,
                    "last_dispatch_at": serialized_existing.get("last_dispatch_at"),
                    "error_message": "",
                    "payload_snapshot_json": serialized_existing.get("payload_snapshot") or {},
                },
            )
            merged_count += 1
            continue

        next_not_before_dt = seed_dt
        if quiet_now:
            status = REPLY_MONITOR_STATUS_DEFERRED
            next_not_before_dt = _parse_timestamp(_next_reply_monitor_daytime_start(config, now=now_dt).strftime("%Y-%m-%d %H:%M:%S")) or next_not_before_dt
            if seed_dt > next_not_before_dt:
                next_not_before_dt = seed_dt
        else:
            status = REPLY_MONITOR_STATUS_PENDING
        repo.insert_reply_monitor_queue_item(
            {
                "member_id": int(member.get("id") or 0) or None,
                "external_userid": external_userid,
                "owner_userid": owner_userid,
                "status": status,
                "message_ids_json": message_ids,
                "message_count": len(message_ids),
                "first_inbound_at": _safe_timestamp_min(*(item.get("send_time") for item in message_rows)),
                "last_inbound_at": _safe_timestamp_max(*(item.get("send_time") for item in message_rows)),
                "not_before": next_not_before_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "last_dispatch_at": "",
                "error_message": "",
                "payload_snapshot_json": {},
            }
        )
        created_count += 1
        seed_dt = next_not_before_dt + timedelta(seconds=max(1, int(config.get("dispatch_interval_seconds") or REPLY_MONITOR_DEFAULT_DISPATCH_INTERVAL_SECONDS)))

    summary = {
        "cursor_from": after_cursor,
        "cursor_to": latest_cursor,
        "scanned_new_messages": len(scanned_rows),
        "candidate_messages": len(candidate_rows),
        "hit_users": processed_users,
        "created_queue_items": created_count,
        "merged_queue_items": merged_count,
    }
    saved_config = _save_reply_monitor_config(
        {
            "last_capture_cursor": latest_cursor,
            "last_capture_at": now_text,
            "last_capture_status": "success",
            "last_capture_summary_json": summary,
            "last_error": "",
        }
    )
    return {
        "ok": True,
        "status": "success",
        "summary": summary,
        "reply_monitor": _reply_monitor_status_payload() if saved_config else _reply_monitor_status_payload(),
    }


def run_due_reply_monitor(
    *,
    operator_id: str = "",
    operator_type: str = "system",
    limit: int = 20,
) -> dict[str, Any]:
    config = _reply_monitor_config()
    if not _normalize_bool(config.get("enabled")):
        return {
            "ok": False,
            "status": "disabled",
            "error": "reply monitor is disabled",
            "reply_monitor": _reply_monitor_status_payload(),
        }
    now_text = _iso_now()
    now_dt = _parse_timestamp(now_text) or datetime.now()
    interval_seconds = max(1, int(config.get("dispatch_interval_seconds") or REPLY_MONITOR_DEFAULT_DISPATCH_INTERVAL_SECONDS))
    if _is_reply_monitor_quiet_hours(config, now=now_dt):
        due_items = [_serialize_reply_monitor_queue_item(item) for item in repo.list_due_reply_monitor_queue_items(now_text=now_text, limit=max(1, min(int(limit), 100)))]
        next_start_text = _next_reply_monitor_daytime_start(config, now=now_dt).strftime("%Y-%m-%d %H:%M:%S")
        deferred_count = 0
        seed_dt = _parse_timestamp(next_start_text) or now_dt
        for item in due_items:
            repo.update_reply_monitor_queue_item(
                int(item["id"]),
                {
                    "member_id": item.get("member_id") or None,
                    "external_userid": item.get("external_userid"),
                    "owner_userid": item.get("owner_userid"),
                    "status": REPLY_MONITOR_STATUS_DEFERRED,
                    "message_ids_json": item.get("message_ids") or [],
                    "message_count": int(item.get("message_count") or 0),
                    "first_inbound_at": item.get("first_inbound_at"),
                    "last_inbound_at": item.get("last_inbound_at"),
                    "not_before": seed_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "last_dispatch_at": item.get("last_dispatch_at"),
                    "error_message": item.get("error_message"),
                    "payload_snapshot_json": item.get("payload_snapshot") or {},
                },
            )
            deferred_count += 1
            seed_dt = seed_dt + timedelta(seconds=interval_seconds)
        summary = {
            "processed_count": 0,
            "success_count": 0,
            "failed_count": 0,
            "deferred_count": deferred_count,
            "reason": "quiet_hours",
        }
        _save_reply_monitor_config(
            {
                "last_dispatch_status": "idle",
                "last_dispatch_summary_json": summary,
                "last_error": "",
            }
        )
        return {
            "ok": True,
            "status": "quiet_hours",
            "summary": summary,
            "reply_monitor": _reply_monitor_status_payload(),
        }

    last_dispatch_dt = _parse_timestamp(config.get("last_dispatch_at"))
    if last_dispatch_dt and now_dt < (last_dispatch_dt + timedelta(seconds=interval_seconds)):
        wait_seconds = max(1, int(((last_dispatch_dt + timedelta(seconds=interval_seconds)) - now_dt).total_seconds()))
        summary = {
            "processed_count": 0,
            "success_count": 0,
            "failed_count": 0,
            "pending_count": int(repo.get_reply_monitor_queue_counts().get("pending") or 0),
            "deferred_count": int(repo.get_reply_monitor_queue_counts().get("deferred_quiet_hours") or 0),
            "wait_seconds": wait_seconds,
        }
        _save_reply_monitor_config(
            {
                "last_dispatch_status": "idle",
                "last_dispatch_summary_json": summary,
                "last_error": "",
            }
        )
        return {
            "ok": True,
            "status": "throttled",
            "summary": summary,
            "reply_monitor": _reply_monitor_status_payload(),
        }

    due_items = [_serialize_reply_monitor_queue_item(item) for item in repo.list_due_reply_monitor_queue_items(now_text=now_text, limit=max(1, min(int(limit), 100)))]
    if not due_items:
        summary = {
            "processed_count": 0,
            "success_count": 0,
            "failed_count": 0,
            "pending_count": int(repo.get_reply_monitor_queue_counts().get("pending") or 0),
            "deferred_count": int(repo.get_reply_monitor_queue_counts().get("deferred_quiet_hours") or 0),
        }
        _save_reply_monitor_config(
            {
                "last_dispatch_status": "idle",
                "last_dispatch_summary_json": summary,
                "last_error": "",
            }
        )
        return {
            "ok": True,
            "status": "idle",
            "summary": summary,
            "reply_monitor": _reply_monitor_status_payload(),
        }

    queue_item = due_items[0]
    return _dispatch_reply_monitor_queue_item(
        queue_item,
        operator_id=operator_id,
        operator_type=operator_type,
        trigger_action="reply_monitor_dispatch",
        trigger_source="reply_monitor_shadow",
    )


def _dispatch_reply_monitor_queue_item(
    queue_item: dict[str, Any],
    *,
    operator_id: str = "",
    operator_type: str = "system",
    trigger_action: str = "reply_monitor_dispatch",
    trigger_source: str = "reply_monitor_shadow",
) -> dict[str, Any]:
    now_text = _iso_now()
    member = repo.get_member_by_id(int(queue_item.get("member_id") or 0)) if int(queue_item.get("member_id") or 0) > 0 else repo.get_member_by_external_contact_id(queue_item.get("external_userid") or "")
    if not member:
        repo.update_reply_monitor_queue_item(
            int(queue_item["id"]),
            {
                "member_id": queue_item.get("member_id") or None,
                "external_userid": queue_item.get("external_userid"),
                "owner_userid": queue_item.get("owner_userid"),
                "status": REPLY_MONITOR_STATUS_FAILED,
                "message_ids_json": queue_item.get("message_ids") or [],
                "message_count": int(queue_item.get("message_count") or 0),
                "first_inbound_at": queue_item.get("first_inbound_at"),
                "last_inbound_at": queue_item.get("last_inbound_at"),
                "not_before": queue_item.get("not_before"),
                "last_dispatch_at": "",
                "error_message": "automation_member_not_found",
                "payload_snapshot_json": queue_item.get("payload_snapshot") or {},
            }
        )
        _save_reply_monitor_config(
            {
                "last_dispatch_status": "failed",
                "last_dispatch_summary_json": {
                    "processed_count": 1,
                    "success_count": 0,
                    "failed_count": 1,
                    "queue_id": int(queue_item["id"]),
                },
                "last_error": "automation_member_not_found",
            }
        )
        return {
            "ok": False,
            "status": "failed",
            "error": "automation_member_not_found",
            "reply_monitor": _reply_monitor_status_payload(),
        }

    messages = repo.list_archived_messages_by_ids(queue_item.get("message_ids") or [])
    recent_messages = _build_reply_monitor_recent_messages(
        messages,
        external_contact_id=_normalized_text(queue_item.get("external_userid")),
    )
    router_ingress: dict[str, Any] = {}
    try:
        from .orchestration_service import run_agent_router_shadow_decision

        router_ingress = run_agent_router_shadow_decision(
            external_contact_id=_normalized_text(queue_item.get("external_userid")),
            owner_userid=_normalized_text(queue_item.get("owner_userid")),
            batch_id=f"reply_monitor_queue:{int(queue_item['id'])}",
            source=_normalized_text(trigger_source) or "reply_monitor_shadow",
        )
    except Exception:  # pragma: no cover - async ingress must not crash the job runner
        current_app.logger.exception("automation router ingress failed")
        router_ingress = {"ok": False, "status": "shadow_error", "shadow_called": False}
    delivery_reason = _normalized_text(router_ingress.get("status") or router_ingress.get("error"))
    delivery_ok = bool(router_ingress.get("ok"))
    next_status = REPLY_MONITOR_STATUS_DISPATCHED if delivery_ok else REPLY_MONITOR_STATUS_FAILED
    repo.update_reply_monitor_queue_item(
        int(queue_item["id"]),
        {
            "member_id": int(member.get("id") or 0) or None,
            "external_userid": queue_item.get("external_userid"),
            "owner_userid": queue_item.get("owner_userid"),
            "status": next_status,
            "message_ids_json": queue_item.get("message_ids") or [],
            "message_count": int(queue_item.get("message_count") or 0),
            "first_inbound_at": queue_item.get("first_inbound_at"),
            "last_inbound_at": queue_item.get("last_inbound_at"),
            "not_before": queue_item.get("not_before"),
            "last_dispatch_at": now_text,
            "error_message": "" if delivery_ok else delivery_reason,
            "payload_snapshot_json": {
                "request_id": _normalized_text(router_ingress.get("request_id")),
                "external_contact_id": _normalized_text(queue_item.get("external_userid")),
                "recent_messages": recent_messages,
            },
        }
    )
    _write_event(
        member_id=int(member["id"]),
        action=_normalized_text(trigger_action) or "reply_monitor_dispatch",
        operator_type=_normalized_text(operator_type) or "system",
        operator_id=_normalized_text(operator_id) or "reply_monitor_runner",
        before_snapshot=_member_snapshot(_serialize_member(member)),
        after_snapshot=_member_snapshot(_serialize_member(member)),
        remark=(
            f"queue_id={int(queue_item['id'])}; "
            f"trigger_type={REPLY_MONITOR_TRIGGER_TYPE}; "
            f"router_request_id={_normalized_text(router_ingress.get('request_id'))}; "
            f"status={'acked' if delivery_ok else 'failed'}"
        ),
    )
    queue_counts = repo.get_reply_monitor_queue_counts()
    summary = {
        "processed_count": 1,
        "success_count": 1 if delivery_ok else 0,
        "failed_count": 0 if delivery_ok else 1,
        "pending_count": int(queue_counts.get("pending") or 0),
        "deferred_count": int(queue_counts.get("deferred_quiet_hours") or 0),
        "queue_id": int(queue_item["id"]),
        "request_id": _normalized_text(router_ingress.get("request_id")),
    }
    _save_reply_monitor_config(
        {
            "last_dispatch_at": now_text,
            "last_dispatch_status": "success" if delivery_ok else "failed",
            "last_dispatch_summary_json": summary,
            "last_error": "" if delivery_ok else delivery_reason,
        }
    )
    return {
        "ok": delivery_ok,
        "status": "success" if delivery_ok else "failed",
        "queue_item": _serialize_reply_monitor_queue_item(repo.get_reply_monitor_queue_item(int(queue_item["id"])) or {}),
        "summary": summary,
        "reply_monitor": _reply_monitor_status_payload(),
        "error": "" if delivery_ok else delivery_reason,
        "router_ingress": router_ingress,
        "shadow_router": router_ingress,
    }


def run_router_test_dispatch(
    *,
    external_contact_id: str = "",
    phone: str = "",
    operator_id: str = "",
    mode: str = "",
    force_capture: bool = False,
    force_run_due: bool = False,
) -> dict[str, Any]:
    normalized_mode = _normalized_text(mode).lower() or "auto"
    normalized_phone = _normalized_text(phone)
    member = _resolve_existing_member(external_contact_id=external_contact_id, phone=normalized_phone)
    resolved_external_contact_id = (
        _normalized_text(external_contact_id)
        or _normalized_text((member or {}).get("external_contact_id"))
        or repo.find_latest_external_contact_id_by_phone(normalized_phone)
    )
    if not resolved_external_contact_id:
        return {
            "ok": False,
            "status": "member_not_found",
            "error": "member_not_found",
            "message": "未找到可触发的 external_contact_id，请提供有效 external_contact_id 或 phone。",
            "capture_result": {},
            "run_due_result": {},
            "request_id": "",
            "queue_id": 0,
            "member_id": 0,
        }
    if not member:
        member = repo.get_member_by_external_contact_id(resolved_external_contact_id)
    if not member:
        return {
            "ok": False,
            "status": "member_not_found",
            "error": "member_not_found",
            "message": f"成员 {resolved_external_contact_id} 不在自动化成员池中，无法触发 router 测试派发。",
            "capture_result": {},
            "run_due_result": {},
            "request_id": "",
            "queue_id": 0,
            "member_id": 0,
        }

    capture_requested = bool(force_capture) or normalized_mode in {"auto", "capture", "capture_and_run_due", "capture-run-due"}
    dispatch_requested = bool(force_run_due) or normalized_mode in {"auto", "queue", "run_due", "capture_and_run_due", "capture-run-due"}
    direct_requested = normalized_mode in {"direct", "router", "shadow"} or not dispatch_requested
    capture_result: dict[str, Any] = {
        "ok": True,
        "status": "skipped",
        "summary": {"reason": "capture_not_requested"},
    }
    if capture_requested:
        capture_result = run_reply_monitor_capture(
            operator_id=_normalized_text(operator_id) or "router_test_dispatch",
            operator_type="system",
            limit=500,
        )

    queue_row = repo.get_active_reply_monitor_queue_item(resolved_external_contact_id)
    queue_item = _serialize_reply_monitor_queue_item(queue_row) if queue_row else {}
    run_due_result: dict[str, Any] = {
        "ok": False,
        "status": "queue_not_found",
        "summary": {"reason": "queue_not_found"},
        "reply_monitor": _reply_monitor_status_payload(),
    }
    if queue_item and dispatch_requested:
        run_due_result = _dispatch_reply_monitor_queue_item(
            queue_item,
            operator_id=_normalized_text(operator_id) or "router_test_dispatch",
            operator_type="system",
            trigger_action="reply_monitor_test_dispatch",
            trigger_source="router_test_dispatch",
        )

    router_ingress = dict(run_due_result.get("router_ingress") or {})
    queue_id = int((run_due_result.get("queue_item") or {}).get("id") or queue_item.get("id") or 0)
    request_id = _normalized_text(router_ingress.get("request_id"))
    message = "已通过 reply-monitor 队列触发新的 router ingress。"

    if not request_id and (direct_requested or normalized_mode == "auto"):
        from .orchestration_service import run_agent_router_shadow_decision

        direct_ingress = run_agent_router_shadow_decision(
            external_contact_id=resolved_external_contact_id,
            owner_userid=_normalized_text((member or {}).get("owner_staff_id")),
            batch_id=f"router_test_dispatch:{resolved_external_contact_id}",
            source="router_test_dispatch",
        )
        router_ingress = dict(direct_ingress or {})
        request_id = _normalized_text(router_ingress.get("request_id"))
        run_due_result = {
            "ok": bool(router_ingress.get("ok")),
            "status": "success" if bool(router_ingress.get("ok")) else (_normalized_text(router_ingress.get("status")) or "failed"),
            "summary": {
                "processed_count": 1 if bool(router_ingress.get("ok")) else 0,
                "success_count": 1 if bool(router_ingress.get("ok")) else 0,
                "failed_count": 0 if bool(router_ingress.get("ok")) else 1,
                "request_id": request_id,
            },
            "reply_monitor": _reply_monitor_status_payload(),
            "error": "" if bool(router_ingress.get("ok")) else (_normalized_text(router_ingress.get("status")) or _normalized_text(router_ingress.get("error"))),
            "router_ingress": router_ingress,
            "shadow_router": router_ingress,
        }
        message = "未命中可直接派发的 reply-monitor 队列，本次已改为直接触发 router ingress。"

    current_app.logger.info(
        "router_test_dispatch external_contact_id=%s member_id=%s request_id=%s queue_id=%s mode=%s capture_requested=%s dispatch_requested=%s direct_requested=%s",
        resolved_external_contact_id,
        int(member.get("id") or 0),
        request_id,
        queue_id,
        normalized_mode,
        capture_requested,
        dispatch_requested,
        direct_requested,
    )
    return {
        "ok": bool(request_id),
        "status": "accepted" if request_id else (_normalized_text(run_due_result.get("status")) or "failed"),
        "capture_result": capture_result,
        "run_due_result": run_due_result,
        "request_id": request_id,
        "queue_id": queue_id,
        "member_id": int(member.get("id") or 0),
        "external_contact_id": resolved_external_contact_id,
        "message": message if request_id else "未触发新的 router ingress，请检查 capture / queue / router 配置。",
    }


def _channel_status_is_generated(status: str) -> bool:
    return _normalized_text(status) == CHANNEL_STATUS_ACTIVE


def _default_channel_field_statuses(
    *,
    provider: Any,
    channel_status: str,
    welcome_message: str,
    auto_accept_friend: bool,
    entry_tag_name: str,
) -> dict[str, dict[str, Any]]:
    support = (
        dict(provider.get_default_channel_field_support() or {})
        if provider is not None and hasattr(provider, "get_default_channel_field_support")
        else {}
    )
    welcome_supported = bool(support.get("welcome_message"))
    auto_accept_supported = bool(support.get("auto_accept_friend"))
    generated = _channel_status_is_generated(channel_status)

    if welcome_message:
        if welcome_supported:
            welcome_status = "applied" if generated else "pending"
            welcome_detail = (
                "欢迎语会在企微回调携带 welcome_code 时，通过官方 send_welcome_msg 自动发送。"
                if generated
                else "保存后需重新生成默认二维码，欢迎语能力才会绑定到当前默认渠道。"
            )
        else:
            welcome_status = "unsupported"
            welcome_detail = "当前默认永久二维码 provider 不支持欢迎语透传。"
    else:
        welcome_status = "not_set"
        welcome_detail = "当前未配置欢迎语。"

    if auto_accept_supported:
        if auto_accept_friend:
            auto_accept_status = "applied" if generated else "pending"
            auto_accept_detail = (
                "免验证直接添加好友已在最近一次生成时透传。"
                if generated
                else "保存后需重新生成默认二维码，免验证开关才会真正生效。"
            )
        else:
            auto_accept_status = "applied" if generated else "not_set"
            auto_accept_detail = (
                "当前默认二维码继续走好友验证。"
                if generated
                else "当前未开启免验证直接添加好友。"
            )
    else:
        auto_accept_status = "unsupported" if auto_accept_friend else "not_set"
        auto_accept_detail = (
            "当前 provider 不支持免验证直接添加好友。"
            if auto_accept_friend
            else "当前未开启免验证直接添加好友。"
        )

    if entry_tag_name:
        entry_tag_status = "applied"
        entry_tag_detail = "扫码回调命中当前渠道码后，会直接给客户打上这个标签。"
    else:
        entry_tag_status = "not_set"
        entry_tag_detail = "当前未配置扫码自动打标签。"

    return {
        "welcome_message": {
            "status": welcome_status,
            "supported": welcome_supported,
            "detail": welcome_detail,
        },
        "auto_accept_friend": {
            "status": auto_accept_status,
            "supported": auto_accept_supported,
            "detail": auto_accept_detail,
        },
        "entry_tag": {
            "status": entry_tag_status,
            "supported": True,
            "detail": entry_tag_detail,
        },
    }


def _resolve_channel_entry_tag_payload(
    *,
    entry_tag_id: Any,
    entry_tag_name: Any,
    entry_tag_group_name: Any,
) -> dict[str, str]:
    normalized_tag_id = _normalized_text(entry_tag_id)
    normalized_tag_name = _normalized_text(entry_tag_name)
    normalized_group_name = _normalized_text(entry_tag_group_name)
    if not normalized_tag_id and not normalized_tag_name and not normalized_group_name:
        return {
            "entry_tag_id": "",
            "entry_tag_name": "",
            "entry_tag_group_name": "",
        }
    live_tags = list_available_wecom_tags()
    matched_tag: dict[str, Any] | None = None
    if normalized_tag_id:
        matched_tag = next((item for item in live_tags if _normalized_text(item.get("tag_id")) == normalized_tag_id), None)
        if not matched_tag:
            raise ValueError("扫码自动打标签未找到对应的企微标签 ID")
    else:
        matched_tags = [
            item
            for item in live_tags
            if _normalized_text(item.get("tag_name")) == normalized_tag_name
            and (not normalized_group_name or _normalized_text(item.get("group_name")) == normalized_group_name)
        ]
        if not matched_tags:
            raise ValueError("扫码自动打标签未找到对应的企微标签")
        if len(matched_tags) > 1:
            raise ValueError("存在多个同名企微标签，请补充标签分组")
        matched_tag = matched_tags[0]
    return {
        "entry_tag_id": _normalized_text((matched_tag or {}).get("tag_id")),
        "entry_tag_name": _normalized_text((matched_tag or {}).get("tag_name")),
        "entry_tag_group_name": _normalized_text((matched_tag or {}).get("group_name")),
    }


def _effective_channel_entry_tag_payload(payload: dict[str, Any], existing: dict[str, Any]) -> dict[str, str]:
    if any(key in payload for key in ("entry_tag_id", "entry_tag_name", "entry_tag_group_name")):
        return _resolve_channel_entry_tag_payload(
            entry_tag_id=payload.get("entry_tag_id"),
            entry_tag_name=payload.get("entry_tag_name"),
            entry_tag_group_name=payload.get("entry_tag_group_name"),
        )
    return {
        "entry_tag_id": _normalized_text(existing.get("entry_tag_id")),
        "entry_tag_name": _normalized_text(existing.get("entry_tag_name")),
        "entry_tag_group_name": _normalized_text(existing.get("entry_tag_group_name")),
    }


def run_message_activity_sync(
    *,
    operator_id: str = "",
    operator_type: str = "system",
    trigger_source: str = MESSAGE_ACTIVITY_SYNC_SOURCE_SCHEDULED,
    current_pools: tuple[str, ...] = MESSAGE_ACTIVITY_SYNC_POOLS,
) -> dict[str, Any]:
    db = get_db()
    db_status = get_message_activity_db_status()
    if not db_status["configured"]:
        return {
            "ok": False,
            "status": "not_configured",
            "error": "message activity db is not configured",
            "missing_keys": list(db_status.get("missing_keys") or []),
            "run": {},
        }
    started_at = _iso_now()
    normalized_trigger_source = _normalized_text(trigger_source) or MESSAGE_ACTIVITY_SYNC_SOURCE_SCHEDULED
    normalized_operator_type = _normalized_text(operator_type) or "system"
    normalized_operator_id = _normalized_text(operator_id) or ("cron" if normalized_operator_type == "system" else "crm_console")
    base_run_payload = {
        "trigger_source": normalized_trigger_source,
        "operator_type": normalized_operator_type,
        "operator_id": normalized_operator_id,
        "status": "running",
        "candidate_count": 0,
        "matched_count": 0,
        "updated_count": 0,
        "skipped_ambiguous_count": 0,
        "skipped_unmatched_count": 0,
        "skipped_missing_phone_count": 0,
        "focus_count": 0,
        "normal_count": 0,
        "error_message": "",
        "summary_json": {},
        "started_at": started_at,
        "finished_at": started_at,
    }
    run_row = repo.insert_message_activity_sync_run(base_run_payload)
    db.commit()
    run_id = int(run_row.get("id") or 0)
    counters = {
        "candidate_count": 0,
        "matched_count": 0,
        "updated_count": 0,
        "skipped_ambiguous_count": 0,
        "skipped_unmatched_count": 0,
        "skipped_missing_phone_count": 0,
        "focus_count": 0,
        "normal_count": 0,
    }
    summary: dict[str, Any] = {
        "candidate_pools": list(current_pools),
        "message_source_rows": 0,
        "active_focus_message_threshold": ACTIVE_FOCUS_MESSAGE_THRESHOLD,
        "active_message_min_threshold": ACTIVE_MESSAGE_MIN_THRESHOLD,
        "ambiguous_phone_match_keys": [],
        "ambiguous_phone_last4": [],
    }
    try:
        eligible_members = sorted(
            [_serialize_member(row) for row in repo.list_members_for_message_activity_sync(current_pools=list(current_pools))],
            key=lambda item: (_normalized_text(item.get("external_contact_id")), int(item.get("id") or 0)),
        )
        counters["candidate_count"] = len(eligible_members)
        message_counts = {
            _normalized_text(row.get("phone_match_key")): {
                "phone_prefix3": _normalized_text(row.get("phone_prefix3")),
                "phone_last4": _normalized_text(row.get("phone_last4")),
                "phone_match_key": _normalized_text(row.get("phone_match_key")),
                "message_count": int(row.get("message_count") or 0),
            }
            for row in query_message_activity_counts()
            if _normalized_text(row.get("phone_match_key"))
        }
        summary["message_source_rows"] = len(message_counts)
        members_by_match_key: dict[str, list[dict[str, Any]]] = {}
        for member in eligible_members:
            match_key = _phone_match_key(member.get("phone"))
            if not match_key:
                continue
            members_by_match_key.setdefault(match_key, []).append(member)
        ambiguous_groups = {key: rows for key, rows in members_by_match_key.items() if len(rows) > 1}
        summary["ambiguous_phone_match_keys"] = sorted(ambiguous_groups.keys())
        summary["ambiguous_phone_last4"] = [_normalized_text(item).split("_", 1)[-1] for item in summary["ambiguous_phone_match_keys"]]

        matched_members: list[dict[str, Any]] = []
        for member in eligible_members:
            match_key = _phone_match_key(member.get("phone"))
            member_id = int(member.get("id") or 0)
            phone_prefix3 = _phone_prefix3(member.get("phone"))
            phone_last4 = _phone_last4(member.get("phone"))
            if not match_key:
                counters["skipped_missing_phone_count"] += 1
                repo.insert_message_activity_sync_item(
                    {
                        "run_id": run_id,
                        "member_id": member_id,
                        "external_contact_id": member.get("external_contact_id"),
                        "phone": member.get("phone"),
                        "phone_prefix3": phone_prefix3,
                        "phone_last4": phone_last4,
                        "phone_match_key": "",
                        "message_count": 0,
                        "status": "skipped_missing_phone",
                        "detail": "member phone is empty or shorter than 7 digits, cannot build phone_match_key",
                        "before_snapshot": _member_snapshot(member),
                        "after_snapshot": _member_snapshot(member),
                        "created_at": _iso_now(),
                    }
                )
                continue
            if match_key in ambiguous_groups:
                counters["skipped_ambiguous_count"] += 1
                conflict_members = ",".join(
                    _normalized_text(item.get("external_contact_id")) or f"id:{int(item.get('id') or 0)}"
                    for item in sorted(
                        ambiguous_groups[match_key],
                        key=lambda item: (_normalized_text(item.get("external_contact_id")), int(item.get("id") or 0)),
                    )
                )
                repo.insert_message_activity_sync_item(
                    {
                        "run_id": run_id,
                        "member_id": member_id,
                        "external_contact_id": member.get("external_contact_id"),
                        "phone": member.get("phone"),
                        "phone_prefix3": phone_prefix3,
                        "phone_last4": phone_last4,
                        "phone_match_key": match_key,
                        "message_count": 0,
                        "status": "skipped_ambiguous",
                        "detail": f"phone_match_key={match_key} matched multiple automation members: {conflict_members}",
                        "before_snapshot": _member_snapshot(member),
                        "after_snapshot": _member_snapshot(member),
                        "created_at": _iso_now(),
                    }
                )
                continue
            if match_key not in message_counts:
                counters["skipped_unmatched_count"] += 1
                repo.insert_message_activity_sync_item(
                    {
                        "run_id": run_id,
                        "member_id": member_id,
                        "external_contact_id": member.get("external_contact_id"),
                        "phone": member.get("phone"),
                        "phone_prefix3": phone_prefix3,
                        "phone_last4": phone_last4,
                        "phone_match_key": match_key,
                        "message_count": 0,
                        "status": "skipped_unmatched",
                        "detail": f"phone_match_key={match_key} not found in message activity source",
                        "before_snapshot": _member_snapshot(member),
                        "after_snapshot": _member_snapshot(member),
                        "created_at": _iso_now(),
                    }
                )
                continue
            matched_members.append(
                {
                    "member": member,
                    "phone_prefix3": phone_prefix3,
                    "phone_last4": phone_last4,
                    "phone_match_key": match_key,
                    "message_count": int((message_counts.get(match_key) or {}).get("message_count") or 0),
                }
            )

        counters["matched_count"] = len(matched_members)
        ranked_members = sorted(
            matched_members,
            key=lambda item: (-int(item["message_count"]), int((item["member"].get("id") or 0))),
        )

        for index, item in enumerate(ranked_members):
            before = item["member"]
            message_count = int(item["message_count"])
            if message_count >= ACTIVE_FOCUS_MESSAGE_THRESHOLD:
                next_follow_type = FOLLOWUP_FOCUS
                next_decision_source = DECISION_SOURCE_SYSTEM
                bucket_label = "active_focus_threshold"
                manual_preserved = False
            elif message_count >= ACTIVE_MESSAGE_MIN_THRESHOLD:
                next_follow_type = FOLLOWUP_NORMAL
                next_decision_source = DECISION_SOURCE_SYSTEM
                bucket_label = "active_normal_threshold"
                manual_preserved = False
            else:
                next_follow_type, next_decision_source, manual_preserved = _inactive_follow_type_from_member(before)
                bucket_label = "inactive_questionnaire_or_manual"
            if next_follow_type == FOLLOWUP_FOCUS:
                counters["focus_count"] += 1
            else:
                counters["normal_count"] += 1
            questionnaire_status = _normalized_text(before.get("questionnaire_status")) or QUESTIONNAIRE_PENDING
            next_payload = {
                **before,
                "follow_type": next_follow_type,
                "decision_source": next_decision_source,
                "current_pool": _message_activity_pool(questionnaire_status=questionnaire_status),
            }
            changed = _substantive_member_changed(before, next_payload)
            if changed:
                saved = _persist_member(before, next_payload)
                after = _serialize_member(saved)
                repo.insert_event(
                    member_id=int(after["id"]),
                    action="message_activity_sync",
                    operator_type=normalized_operator_type,
                    operator_id=normalized_operator_id,
                    before_snapshot=_member_snapshot(before),
                    after_snapshot=_member_snapshot(after),
                    remark=(
                        f"message_count={message_count}; phone_match_key={item['phone_match_key']}; "
                        f"rank={index + 1}/{len(ranked_members)}; "
                        f"bucket={bucket_label}; "
                        f"follow_type={'manual_preserved' if manual_preserved else next_follow_type}"
                    ),
                )
                counters["updated_count"] += 1
            else:
                after = before
            repo.insert_message_activity_sync_item(
                {
                    "run_id": run_id,
                    "member_id": int(before["id"]),
                    "external_contact_id": before.get("external_contact_id"),
                    "phone": before.get("phone"),
                    "phone_prefix3": item["phone_prefix3"],
                    "phone_last4": item["phone_last4"],
                    "phone_match_key": item["phone_match_key"],
                    "message_count": message_count,
                    "status": "updated" if changed else "unchanged",
                    "detail": (
                        f"rank={index + 1}/{len(ranked_members)}; "
                        f"bucket={bucket_label}; "
                        f"effective_follow_type={next_follow_type}; "
                        f"manual_preserved={'yes' if manual_preserved else 'no'}"
                    ),
                    "before_snapshot": _member_snapshot(before),
                    "after_snapshot": _member_snapshot(after),
                    "created_at": _iso_now(),
                }
            )

        finished_at = _iso_now()
        summary["processed_at"] = finished_at
        final_run_row = repo.update_message_activity_sync_run(
            run_id,
            {
                **base_run_payload,
                **counters,
                "status": "success",
                "summary_json": summary,
                "finished_at": finished_at,
            },
        )
        db.commit()
        return {
            "ok": True,
            "run": _serialize_message_activity_sync_run(final_run_row),
            "items": [
                _serialize_message_activity_sync_item(item)
                for item in repo.list_message_activity_sync_items(run_id=run_id, limit=50)
            ],
        }
    except Exception as exc:
        db.rollback()
        failed_at = _iso_now()
        failed_run_row = repo.update_message_activity_sync_run(
            run_id,
            {
                **base_run_payload,
                **counters,
                "status": "failed",
                "error_message": str(exc),
                "summary_json": {**summary, "processed_at": failed_at},
                "finished_at": failed_at,
            },
        )
        db.commit()
        return {
            "ok": False,
            "error": str(exc),
            "run": _serialize_message_activity_sync_run(failed_run_row),
        }


def _questionnaire_rule_editor_question(question: dict[str, Any]) -> dict[str, Any] | None:
    question_type = _normalized_text(question.get("type"))
    if question_type not in {"single_choice", "multi_choice"}:
        return None
    options = [
        {
            "id": int(option.get("id") or 0),
            "option_text": _normalized_text(option.get("option_text")) or f"选项 {int(option.get('id') or 0)}",
        }
        for option in question.get("options") or []
        if int(option.get("id") or 0) > 0
    ]
    return {
        "id": int(question.get("id") or 0),
        "title": _normalized_text(question.get("title")) or f"问题 {int(question.get('id') or 0)}",
        "type": question_type,
        "options": options,
    }


def _build_questionnaire_rule_catalog(questionnaires: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    catalog: dict[str, dict[str, Any]] = {}
    for item in questionnaires:
        questionnaire_id = int(item.get("id") or 0)
        if questionnaire_id <= 0:
            continue
        try:
            detail = get_questionnaire_detail(questionnaire_id)
        except Exception:
            detail = None
        if not detail:
            continue
        catalog[str(questionnaire_id)] = {
            "id": questionnaire_id,
            "title": _normalized_text(detail.get("title")) or _normalized_text(detail.get("name")) or f"问卷 #{questionnaire_id}",
            "is_disabled": _normalize_bool(detail.get("is_disabled")),
            "questions": [
                editor_question
                for question in detail.get("questions") or []
                for editor_question in [_questionnaire_rule_editor_question(question)]
                if editor_question
            ],
        }
    return catalog


def ensure_agent_prompt_defaults() -> None:
    existing_codes = {
        _normalized_text(item.get("agent_code"))
        for item in repo.list_agent_prompt_rows()
        if _normalized_text(item.get("agent_code"))
    }
    for payload in default_agent_prompt_payloads():
        agent_code = _normalized_text(payload.get("agent_code"))
        if agent_code in existing_codes:
            continue
        repo.insert_agent_prompt_row(payload)


def _serialize_agent_prompt_row(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    definition = AGENT_PROMPT_DEFINITION_MAP.get(_normalized_text(row.get("agent_code")), {})
    deserialized = repo.deserialize_agent_prompt_row(dict(row))
    return {
        "id": int(deserialized.get("id") or 0),
        "agent_code": _normalized_text(deserialized.get("agent_code")),
        "display_name": _normalized_text(deserialized.get("display_name")) or _normalized_text(definition.get("display_name")),
        "prompt_text": _normalized_text(deserialized.get("prompt_text")),
        "enabled": _normalize_bool(deserialized.get("enabled")),
        "version": int(deserialized.get("version") or 1),
        "updated_at": _normalized_text(deserialized.get("updated_at")),
        "created_at": _normalized_text(deserialized.get("created_at")),
    }


def _serialize_agent_llm_call_log(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    return {
        "id": int(row.get("id") or 0),
        "agent_code": _normalized_text(row.get("agent_code")),
        "model_name": _normalized_text(row.get("model_name")),
        "request_id": _normalized_text(row.get("request_id")),
        "status": _normalized_text(row.get("status")),
        "latency_ms": int(row.get("latency_ms") or 0),
        "error_message": _normalized_text(row.get("error_message")),
        "created_at": _normalized_text(row.get("created_at")),
    }


def _deepseek_settings_payload() -> dict[str, Any]:
    config = get_deepseek_runtime_config()
    setting_rows = repo.list_app_setting_rows(list(DEEPSEEK_SETTING_KEYS))
    latest_updated_at = _normalized_text(setting_rows[0].get("updated_at")) if setting_rows else ""
    api_key = _normalized_text(config.get("api_key"))
    return {
        "enabled": bool(config.get("enabled")),
        "api_key_configured": bool(api_key),
        "api_key_masked": mask_value("DEEPSEEK_API_KEY", api_key),
        "base_url": _normalized_text(config.get("base_url")) or DEFAULT_DEEPSEEK_BASE_URL,
        "router_model": _normalized_text(config.get("router_model")) or DEFAULT_DEEPSEEK_ROUTER_MODEL,
        "execution_model": _normalized_text(config.get("execution_model")) or DEFAULT_DEEPSEEK_EXECUTION_MODEL,
        "reasoner_model": _normalized_text(config.get("reasoner_model")) or DEFAULT_DEEPSEEK_REASONER_MODEL,
        "timeout_seconds": int(config.get("timeout_seconds") or DEFAULT_DEEPSEEK_TIMEOUT_SECONDS),
        "updated_at": latest_updated_at,
    }


def get_model_infra_payload(*, limit_logs: int = 20) -> dict[str, Any]:
    ensure_agent_prompt_defaults()
    db = get_db()
    db.commit()
    prompt_rows = {
        _normalized_text(item.get("agent_code")): _serialize_agent_prompt_row(item)
        for item in repo.list_agent_prompt_rows()
    }
    prompts = [
        prompt_rows.get(agent_code)
        or _serialize_agent_prompt_row({"agent_code": agent_code, **AGENT_PROMPT_DEFINITION_MAP[agent_code]})
        for agent_code in AGENT_PROMPT_ORDER
    ]
    logs = [_serialize_agent_llm_call_log(item) for item in repo.list_recent_agent_llm_call_logs(limit=limit_logs)]
    return {
        "deepseek": _deepseek_settings_payload(),
        "prompts": prompts,
        "logs": logs,
    }


def save_model_infra_settings(payload: dict[str, Any]) -> dict[str, Any]:
    next_enabled = _normalize_bool(payload.get("enabled"))
    next_api_key = _normalized_text(payload.get("api_key"))
    if not next_api_key:
        next_api_key = _setting_text_value("DEEPSEEK_API_KEY")
    next_base_url = _normalized_text(payload.get("base_url")) or DEFAULT_DEEPSEEK_BASE_URL
    if next_base_url and not next_base_url.startswith(("http://", "https://")):
        raise ValueError("DEEPSEEK_BASE_URL must start with http:// or https://")
    next_router_model = _normalized_text(payload.get("router_model")) or DEFAULT_DEEPSEEK_ROUTER_MODEL
    next_execution_model = _normalized_text(payload.get("execution_model")) or DEFAULT_DEEPSEEK_EXECUTION_MODEL
    next_reasoner_model = _normalized_text(payload.get("reasoner_model")) or DEFAULT_DEEPSEEK_REASONER_MODEL
    try:
        next_timeout_seconds = max(1, int(payload.get("timeout_seconds") or DEFAULT_DEEPSEEK_TIMEOUT_SECONDS))
    except (TypeError, ValueError):
        raise ValueError("DEEPSEEK_TIMEOUT_SECONDS must be a positive integer") from None
    set_settings(
        {
            "DEEPSEEK_ENABLED": "true" if next_enabled else "false",
            "DEEPSEEK_API_KEY": next_api_key,
            "DEEPSEEK_BASE_URL": next_base_url,
            "DEEPSEEK_ROUTER_MODEL": next_router_model,
            "DEEPSEEK_EXECUTION_MODEL": next_execution_model,
            "DEEPSEEK_REASONER_MODEL": next_reasoner_model,
            "DEEPSEEK_TIMEOUT_SECONDS": str(next_timeout_seconds),
        }
    )
    return get_model_infra_payload()


def get_default_channel_settings_payload() -> dict[str, Any]:
    payload = get_settings_payload()
    return {
        "default_channel": dict(payload.get("default_channel") or {}),
        "provider_available": bool(payload.get("provider_available")),
    }


def save_default_channel_settings(payload: dict[str, Any]) -> dict[str, Any]:
    existing = repo.get_default_channel() or {}
    entry_tag_payload = _effective_channel_entry_tag_payload(payload, existing)
    next_channel_name = _normalized_text(payload.get("channel_name")) or _normalized_text(existing.get("channel_name")) or DEFAULT_CHANNEL_NAME
    next_welcome_message = (
        _normalized_text(payload.get("welcome_message"))
        if "welcome_message" in payload
        else _normalized_text(existing.get("welcome_message"))
    )
    next_auto_accept_friend = (
        _normalize_bool(payload.get("auto_accept_friend"))
        if "auto_accept_friend" in payload
        else _normalize_bool(existing.get("auto_accept_friend"))
    )
    current_channel_name = _normalized_text(existing.get("channel_name")) or DEFAULT_CHANNEL_NAME
    current_welcome_message = _normalized_text(existing.get("welcome_message"))
    current_auto_accept_friend = _normalize_bool(existing.get("auto_accept_friend"))
    channel_settings_changed = (
        next_channel_name != current_channel_name
        or next_welcome_message != current_welcome_message
        or next_auto_accept_friend != current_auto_accept_friend
        or entry_tag_payload["entry_tag_id"] != _normalized_text(existing.get("entry_tag_id"))
        or entry_tag_payload["entry_tag_name"] != _normalized_text(existing.get("entry_tag_name"))
        or entry_tag_payload["entry_tag_group_name"] != _normalized_text(existing.get("entry_tag_group_name"))
    )
    repo.save_channel(
        {
            "channel_code": DEFAULT_CHANNEL_CODE,
            "channel_name": next_channel_name,
            "qr_url": _normalized_text(payload.get("qr_url")) or _normalized_text(existing.get("qr_url")),
            "qr_ticket": _normalized_text(payload.get("qr_ticket")) or _normalized_text(existing.get("qr_ticket")),
            "scene_value": _normalized_text(payload.get("scene_value")) or _normalized_text(existing.get("scene_value")),
            "welcome_message": next_welcome_message,
            "auto_accept_friend": next_auto_accept_friend,
            "entry_tag_id": entry_tag_payload["entry_tag_id"],
            "entry_tag_name": entry_tag_payload["entry_tag_name"],
            "entry_tag_group_name": entry_tag_payload["entry_tag_group_name"],
            "owner_staff_id": DEFAULT_OWNER_STAFF_ID,
            "status": (
                CHANNEL_STATUS_CONFIGURED
                if channel_settings_changed
                else (_normalized_text(payload.get("channel_status")) or _normalized_text(existing.get("status")) or CHANNEL_STATUS_CONFIGURED)
            ),
        }
    )
    get_db().commit()
    return get_default_channel_settings_payload()


def save_model_infra_prompt(*, agent_code: str, display_name: str, prompt_text: str, enabled: bool) -> dict[str, Any]:
    normalized_agent_code = _normalized_text(agent_code)
    if normalized_agent_code not in AGENT_PROMPT_DEFINITION_MAP:
        raise ValueError("invalid agent_code")
    next_display_name = _normalized_text(display_name) or _normalized_text(AGENT_PROMPT_DEFINITION_MAP[normalized_agent_code].get("display_name"))
    next_prompt_text = _normalized_text(prompt_text)
    if not next_prompt_text:
        raise ValueError("prompt_text is required")
    existing = repo.get_agent_prompt_row(normalized_agent_code)
    if existing:
        changed = (
            _normalized_text(existing.get("display_name")) != next_display_name
            or _normalized_text(existing.get("prompt_text")) != next_prompt_text
            or _normalize_bool(existing.get("enabled")) != bool(enabled)
        )
        next_version = int(existing.get("version") or 1) + (1 if changed else 0)
        saved = repo.update_agent_prompt_row(
            normalized_agent_code,
            {
                "display_name": next_display_name,
                "prompt_text": next_prompt_text,
                "enabled": bool(enabled),
                "version": next_version,
            },
        )
    else:
        saved = repo.insert_agent_prompt_row(
            {
                "agent_code": normalized_agent_code,
                "display_name": next_display_name,
                "prompt_text": next_prompt_text,
                "enabled": bool(enabled),
                "version": 1,
            }
        )
    if normalized_agent_code in CHILD_AGENT_CONFIG_MAP:
        from .orchestration_service import get_agent_config_detail, save_agent_config_draft

        current_config = get_agent_config_detail(normalized_agent_code)
        save_agent_config_draft(
            normalized_agent_code,
            {
                "display_name": next_display_name,
                "enabled": bool(enabled),
                "role_prompt": str(((current_config.get("draft") or {}).get("role_prompt")) or ""),
                "task_prompt": next_prompt_text,
                "variables": list(((current_config.get("draft") or {}).get("variables")) or []),
                "output_schema": list(((current_config.get("draft") or {}).get("output_schema")) or []),
                "change_summary": "从 legacy Prompt Registry 同步任务提示词",
            },
            operator_id="legacy_model_infra",
            source="legacy_prompt_registry",
        )
    get_db().commit()
    return _serialize_agent_prompt_row(saved)


def test_model_infra_connection() -> dict[str, Any]:
    try:
        result = test_deepseek_connection()
        return {
            "ok": True,
            "request_id": _normalized_text(result.get("request_id")),
            "model_name": _normalized_text(result.get("model_name")),
            "latency_ms": int(result.get("latency_ms") or 0),
            "parsed_output": result.get("parsed_output") if isinstance(result.get("parsed_output"), dict) else {},
        }
    except DeepSeekClientError as exc:
        return {
            "ok": False,
            "error": str(exc),
            "deepseek": _deepseek_settings_payload(),
        }


def get_settings_payload() -> dict[str, Any]:
    config = get_signup_conversion_config()
    channel = repo.get_default_channel() or {}
    provider = load_channel_provider()
    questionnaires = list_questionnaires()
    questionnaire_rule_catalog = _build_questionnaire_rule_catalog(questionnaires)
    questionnaire = None
    questionnaire_missing = bool(config.get("questionnaire_missing"))
    questionnaire_id = config.get("questionnaire_id") or config.get("missing_questionnaire_id")
    if questionnaire_id not in (None, ""):
        if not questionnaire_missing:
            try:
                questionnaire = get_questionnaire_detail(int(questionnaire_id))
            except Exception:
                questionnaire = None
                questionnaire_missing = True
            else:
                questionnaire_missing = not bool(questionnaire)
    rule_editor_questionnaire_id = (
        _normalized_text(config.get("questionnaire_id"))
        if not questionnaire_missing and config.get("questionnaire_id") not in (None, "")
        else ""
    )
    selected_catalog_item = questionnaire_rule_catalog.get(rule_editor_questionnaire_id)
    return {
        "questionnaires": questionnaires,
        "selected_questionnaire": questionnaire,
        "questionnaire_missing": questionnaire_missing,
        "missing_questionnaire_id": int(questionnaire_id) if questionnaire_missing and questionnaire_id not in (None, "") else None,
        "config": config,
        "questionnaire_rule_catalog": questionnaire_rule_catalog,
        "rule_editor": {
            "selected_questionnaire_id": rule_editor_questionnaire_id,
            "selected_questionnaire": selected_catalog_item,
            "rules": list(config.get("question_rules") or []) if not questionnaire_missing else [],
            "rules_invalidated": questionnaire_missing,
        },
        "default_channel": {
            "channel_code": _normalized_text(channel.get("channel_code")) or DEFAULT_CHANNEL_CODE,
            "channel_name": _normalized_text(channel.get("channel_name")) or DEFAULT_CHANNEL_NAME,
            "qr_url": _normalized_text(channel.get("qr_url")),
            "qr_ticket": _normalized_text(channel.get("qr_ticket")),
            "scene_value": _normalized_text(channel.get("scene_value")),
            "welcome_message": _normalized_text(channel.get("welcome_message")),
            "auto_accept_friend": _normalize_bool(channel.get("auto_accept_friend")),
            "entry_tag_id": _normalized_text(channel.get("entry_tag_id")),
            "entry_tag_name": _normalized_text(channel.get("entry_tag_name")),
            "entry_tag_group_name": _normalized_text(channel.get("entry_tag_group_name")),
            "owner_staff_id": _normalized_text(channel.get("owner_staff_id")) or DEFAULT_OWNER_STAFF_ID,
            "status": _normalized_text(channel.get("status")) or CHANNEL_STATUS_NOT_GENERATED,
            "field_statuses": _default_channel_field_statuses(
                provider=provider,
                channel_status=_normalized_text(channel.get("status")) or CHANNEL_STATUS_NOT_GENERATED,
                welcome_message=_normalized_text(channel.get("welcome_message")),
                auto_accept_friend=_normalize_bool(channel.get("auto_accept_friend")),
                entry_tag_name=_normalized_text(channel.get("entry_tag_name")),
            ),
        },
        "default_owner_staff_id": DEFAULT_OWNER_STAFF_ID,
        "provider_available": provider is not None,
        "message_activity_sync": _message_activity_sync_status_payload(),
        "reply_monitor": _reply_monitor_status_payload(),
    }


def _coerce_legacy_settings_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized_payload = dict(payload or {})

    if "question_rules" not in normalized_payload and "question_rules_json" in normalized_payload:
        raw_question_rules = normalized_payload.get("question_rules_json")
        normalized_payload["question_rules"] = _json_loads(
            raw_question_rules,
            default=raw_question_rules,
        )

    if "silent_threshold_days_by_pool" not in normalized_payload:
        legacy_threshold_keys = {
            "silent_threshold_new_user": "new_user",
            "silent_threshold_inactive_normal": "inactive_normal",
            "silent_threshold_inactive_focus": "inactive_focus",
            "silent_threshold_active_normal": "active_normal",
            "silent_threshold_active_focus": "active_focus",
        }
        legacy_thresholds = {
            pool_key: normalized_payload.get(legacy_key)
            for legacy_key, pool_key in legacy_threshold_keys.items()
            if legacy_key in normalized_payload
        }
        if legacy_thresholds:
            normalized_payload["silent_threshold_days_by_pool"] = legacy_thresholds

    return normalized_payload


def save_settings(payload: dict[str, Any]) -> dict[str, Any]:
    normalized_payload = _coerce_legacy_settings_payload(payload or {})
    config_payload = {
        "enabled": _normalize_bool(normalized_payload.get("enabled", True)),
        "questionnaire_id": normalized_payload.get("questionnaire_id"),
        "core_threshold": normalized_payload.get("core_threshold"),
        "top_threshold": normalized_payload.get("top_threshold", normalized_payload.get("core_threshold")),
        "day_start_hour": normalized_payload.get("day_start_hour"),
        "quiet_hour_start": normalized_payload.get("quiet_hour_start"),
        "timezone": normalized_payload.get("timezone"),
        "silent_threshold_days_by_pool": normalized_payload.get("silent_threshold_days_by_pool"),
        "question_rules": normalized_payload.get("question_rules"),
    }
    save_signup_conversion_config(config_payload, enforce_required_mobile_question=True)
    existing = repo.get_default_channel() or {}
    entry_tag_payload = _effective_channel_entry_tag_payload(normalized_payload, existing)
    next_channel_name = _normalized_text(normalized_payload.get("channel_name")) or _normalized_text(existing.get("channel_name")) or DEFAULT_CHANNEL_NAME
    next_welcome_message = (
        _normalized_text(normalized_payload.get("welcome_message"))
        if "welcome_message" in normalized_payload
        else _normalized_text(existing.get("welcome_message"))
    )
    next_auto_accept_friend = (
        _normalize_bool(normalized_payload.get("auto_accept_friend"))
        if "auto_accept_friend" in normalized_payload
        else _normalize_bool(existing.get("auto_accept_friend"))
    )
    current_channel_name = _normalized_text(existing.get("channel_name")) or DEFAULT_CHANNEL_NAME
    current_welcome_message = _normalized_text(existing.get("welcome_message"))
    current_auto_accept_friend = _normalize_bool(existing.get("auto_accept_friend"))
    channel_settings_changed = (
        next_channel_name != current_channel_name
        or next_welcome_message != current_welcome_message
        or next_auto_accept_friend != current_auto_accept_friend
        or entry_tag_payload["entry_tag_id"] != _normalized_text(existing.get("entry_tag_id"))
        or entry_tag_payload["entry_tag_name"] != _normalized_text(existing.get("entry_tag_name"))
        or entry_tag_payload["entry_tag_group_name"] != _normalized_text(existing.get("entry_tag_group_name"))
    )
    repo.save_channel(
        {
            "channel_code": DEFAULT_CHANNEL_CODE,
            "channel_name": next_channel_name,
            "qr_url": _normalized_text(normalized_payload.get("qr_url")) or _normalized_text(existing.get("qr_url")),
            "qr_ticket": _normalized_text(normalized_payload.get("qr_ticket")) or _normalized_text(existing.get("qr_ticket")),
            "scene_value": _normalized_text(normalized_payload.get("scene_value")) or _normalized_text(existing.get("scene_value")),
            "welcome_message": next_welcome_message,
            "auto_accept_friend": next_auto_accept_friend,
            "entry_tag_id": entry_tag_payload["entry_tag_id"],
            "entry_tag_name": entry_tag_payload["entry_tag_name"],
            "entry_tag_group_name": entry_tag_payload["entry_tag_group_name"],
            "owner_staff_id": DEFAULT_OWNER_STAFF_ID,
            "status": (
                CHANNEL_STATUS_CONFIGURED
                if channel_settings_changed
                else (
                    _normalized_text(normalized_payload.get("channel_status"))
                    or _normalized_text(existing.get("status"))
                    or CHANNEL_STATUS_CONFIGURED
                )
            ),
        }
    )
    get_db().commit()
    return get_settings_payload()


def generate_default_channel_qr(*, operator: str = "") -> dict[str, Any]:
    provider = load_channel_provider()
    existing = repo.get_default_channel() or {}
    if provider is None:
        return {
            "generated": False,
            "provider_available": False,
            "channel": existing,
            "error": "二维码 provider 未接入，当前仓库无法生成真实企微渠道二维码",
            "operator": _normalized_text(operator),
            "status_code": 501,
            "error_code": "provider_missing",
        }
    welcome_message = _normalized_text(existing.get("welcome_message"))
    auto_accept_friend = _normalize_bool(existing.get("auto_accept_friend"))
    entry_tag_id = _normalized_text(existing.get("entry_tag_id"))
    entry_tag_name = _normalized_text(existing.get("entry_tag_name"))
    entry_tag_group_name = _normalized_text(existing.get("entry_tag_group_name"))
    try:
        channel_payload = provider.create_default_channel(
            owner_staff_id=DEFAULT_OWNER_STAFF_ID,
            welcome_message=welcome_message,
            auto_accept_friend=auto_accept_friend,
        )
    except ValueError as exc:
        saved = repo.save_channel(
            {
                "channel_code": _normalized_text(existing.get("channel_code")) or DEFAULT_CHANNEL_CODE,
                "channel_name": _normalized_text(existing.get("channel_name")) or DEFAULT_CHANNEL_NAME,
                "qr_url": _normalized_text(existing.get("qr_url")),
                "qr_ticket": _normalized_text(existing.get("qr_ticket")),
                "scene_value": _normalized_text(existing.get("scene_value")),
                "welcome_message": welcome_message,
                "auto_accept_friend": auto_accept_friend,
                "entry_tag_id": entry_tag_id,
                "entry_tag_name": entry_tag_name,
                "entry_tag_group_name": entry_tag_group_name,
                "owner_staff_id": DEFAULT_OWNER_STAFF_ID,
                "status": "generation_failed",
            }
        )
        get_db().commit()
        return {
            "generated": False,
            "provider_available": True,
            "channel": saved,
            "error": str(exc),
            "operator": _normalized_text(operator),
            "status_code": 400,
            "error_code": "invalid_state",
            "field_statuses": _default_channel_field_statuses(
                provider=provider,
                channel_status=_normalized_text(saved.get("status")) or "generation_failed",
                welcome_message=welcome_message,
                auto_accept_friend=auto_accept_friend,
                entry_tag_name=entry_tag_name,
            ),
        }
    except WeComClientError as exc:
        saved = repo.save_channel(
            {
                "channel_code": _normalized_text(existing.get("channel_code")) or DEFAULT_CHANNEL_CODE,
                "channel_name": _normalized_text(existing.get("channel_name")) or DEFAULT_CHANNEL_NAME,
                "qr_url": _normalized_text(existing.get("qr_url")),
                "qr_ticket": _normalized_text(existing.get("qr_ticket")),
                "scene_value": _normalized_text(existing.get("scene_value")),
                "welcome_message": welcome_message,
                "auto_accept_friend": auto_accept_friend,
                "entry_tag_id": entry_tag_id,
                "entry_tag_name": entry_tag_name,
                "entry_tag_group_name": entry_tag_group_name,
                "owner_staff_id": DEFAULT_OWNER_STAFF_ID,
                "status": "config_incomplete" if "not configured" in str(exc).lower() else "generation_failed",
            }
        )
        get_db().commit()
        return {
            "generated": False,
            "provider_available": True,
            "channel": saved,
            "error": str(exc),
            "operator": _normalized_text(operator),
            "status_code": 400 if "not configured" in str(exc).lower() else 502,
            "error_code": (
                "config_incomplete"
                if "not configured" in str(exc).lower()
                else (_normalized_text(exc.category) or "generation_failed")
            ),
            "field_statuses": _default_channel_field_statuses(
                provider=provider,
                channel_status=_normalized_text(saved.get("status")) or "generation_failed",
                welcome_message=welcome_message,
                auto_accept_friend=auto_accept_friend,
                entry_tag_name=entry_tag_name,
            ),
        }
    saved = repo.save_channel(
        {
            "channel_code": DEFAULT_CHANNEL_CODE,
            "channel_name": _normalized_text(channel_payload.get("channel_name")) or DEFAULT_CHANNEL_NAME,
            "qr_url": _normalized_text(channel_payload.get("qr_url")),
            "qr_ticket": _normalized_text(channel_payload.get("qr_ticket")),
            "scene_value": _normalized_text(channel_payload.get("scene_value")),
            "welcome_message": welcome_message,
            "auto_accept_friend": auto_accept_friend,
            "entry_tag_id": entry_tag_id,
            "entry_tag_name": entry_tag_name,
            "entry_tag_group_name": entry_tag_group_name,
            "owner_staff_id": DEFAULT_OWNER_STAFF_ID,
            "status": _normalized_text(channel_payload.get("status")) or CHANNEL_STATUS_ACTIVE,
        }
    )
    get_db().commit()
    return {
        "generated": True,
        "provider_available": True,
        "channel": saved,
        "field_statuses": (
            dict(channel_payload.get("field_statuses") or {})
            or _default_channel_field_statuses(
                provider=provider,
                channel_status=_normalized_text(saved.get("status")) or CHANNEL_STATUS_ACTIVE,
                welcome_message=welcome_message,
                auto_accept_friend=auto_accept_friend,
                entry_tag_name=entry_tag_name,
            )
        ),
    }


def _resolve_existing_member(external_contact_id: str = "", phone: str = "") -> dict[str, Any] | None:
    normalized_external_contact_id = _normalized_text(external_contact_id)
    normalized_phone = _normalized_text(phone)
    return repo.get_member_by_external_contact_id(normalized_external_contact_id) or repo.get_member_by_phone(normalized_phone)


def get_member_detail(*, external_contact_id: str = "", phone: str = "") -> dict[str, Any]:
    refresh_expired_silent_members()
    member = _resolve_existing_member(external_contact_id=external_contact_id, phone=phone)
    if member:
        member = _touch_member_from_sources(member, action="system_view_sync", persist_event=False)
    context = _build_live_context(external_contact_id, phone)
    profile = context["profile"]
    if member:
        serialized_member = _serialize_member(member)
    else:
        preview_payload = _member_payload_from_context(
            None,
            {**context, "settings": get_signup_conversion_config()},
            in_pool=False,
            source_type=SOURCE_TYPE_SYSTEM,
        )
        preview_payload["current_pool"] = POOL_REMOVED
        serialized_member = _serialize_member(preview_payload)
    resolved_questionnaire = resolve_member_questionnaire_truth(
        external_contact_ids=context["lookup"].get("external_contact_ids") or [],
        phone=_normalized_text(profile.get("phone")) or serialized_member["phone"],
        member=serialized_member,
    )
    latest_manual_event = repo.get_latest_manual_event(int(member["id"])) if member else None
    cooldown_until = _parse_timestamp(serialized_member.get("ai_cooldown_until"))
    cooldown_remaining_seconds = max(0, int((cooldown_until - datetime.now()).total_seconds())) if cooldown_until else 0
    return {
        "member_exists": bool(member),
        "member": serialized_member,
        "profile": {
            "customer_name": _normalized_text(profile.get("customer_name")) or serialized_member["external_contact_id"] or "未命名客户",
            "owner_staff_id": _normalized_text(profile.get("owner_staff_id")) or serialized_member["owner_staff_id"],
            "owner_display_name": _normalized_text(profile.get("owner_display_name")) or _normalized_text(profile.get("owner_staff_id")),
            "external_contact_id": serialized_member["external_contact_id"],
            "phone": serialized_member["phone"],
            "unionid": _normalized_text(profile.get("unionid")),
        },
        "questionnaire": {
            "status": resolved_questionnaire.get("questionnaire_status") or serialized_member["questionnaire_status"],
            "status_label": _questionnaire_status_label(resolved_questionnaire.get("questionnaire_status") or serialized_member["questionnaire_status"]),
            "hit_count": int(resolved_questionnaire.get("hit_count") or 0),
            "matched_questions": resolved_questionnaire.get("matched_questions") or [],
            "submitted_at": _normalized_text(resolved_questionnaire.get("submitted_at")),
        },
        "latest_manual_action": (
            {
                "action": _normalized_text(latest_manual_event.get("action")),
                "action_label": _automation_action_label(latest_manual_event.get("action")),
                "operator_id": _normalized_text(latest_manual_event.get("operator_id")),
                "remark": _normalized_text(latest_manual_event.get("remark")),
                "created_at": _normalized_text(latest_manual_event.get("created_at")),
            }
            if latest_manual_event
            else {}
        ),
        "last_ai_push_at": serialized_member["last_ai_push_at"],
        "ai_cooldown_until": serialized_member["ai_cooldown_until"],
        "ai_cooldown_remaining_seconds": cooldown_remaining_seconds,
        "actions": _button_state(serialized_member),
    }


def _button_state(member: dict[str, Any]) -> dict[str, Any]:
    return local_projection.button_state(
        current_pool=_normalized_text(member.get("current_pool")),
        in_pool=bool(member.get("in_pool")),
    )


def _mutate_member(
    *,
    external_contact_id: str = "",
    phone: str = "",
    action: str,
    operator_id: str,
    operator_type: str = "user",
    include_detail: bool = True,
    mutate,
) -> dict[str, Any]:
    member = _resolve_existing_member(external_contact_id=external_contact_id, phone=phone)
    if not member and action != "put_in_pool":
        raise LookupError("automation member not found")
    context = _build_live_context(external_contact_id, phone)
    before = _serialize_member(member or _member_payload_from_context(None, {**context, "settings": get_signup_conversion_config()}, in_pool=False))
    current = _member_payload_from_context(member, {**context, "settings": get_signup_conversion_config()})
    if not current.get("joined_at") and action == "put_in_pool":
        current["joined_at"] = _iso_now()
    mutation_result = mutate(current, context)
    if isinstance(mutation_result, tuple) and len(mutation_result) == 3:
        next_payload, remark, should_recompute_pool = mutation_result
    else:
        next_payload, remark = mutation_result
        should_recompute_pool = True
    if should_recompute_pool:
        next_payload["current_pool"] = recompute_pool(next_payload, {**context, "settings": get_signup_conversion_config()}, action=action)
    saved = _persist_member(member, next_payload)
    after = _serialize_member(saved)
    _write_event(
        member_id=int(saved["id"]),
        action=action,
        operator_type=operator_type,
        operator_id=operator_id,
        before_snapshot=_member_snapshot(before),
        after_snapshot=_member_snapshot(after),
        remark=remark,
    )
    return {
        "member": after,
        "remark": remark,
        "detail": (
            get_member_detail(external_contact_id=after["external_contact_id"], phone=after["phone"])
            if include_detail
            else {}
        ),
    }


def apply_router_target_pool(
    *,
    external_contact_id: str = "",
    phone: str = "",
    target_pool: str,
    operator_id: str = "",
    operator_type: str = "system",
) -> dict[str, Any]:
    legacy_target_pool_aliases = {
        "new_user": POOL_PENDING_QUESTIONNAIRE,
        "inactive_normal": POOL_OPERATING,
        "inactive_focus": POOL_OPERATING,
        "active_normal": POOL_OPERATING,
        "active_focus": POOL_OPERATING,
        "silent": POOL_OPERATING,
        "won": POOL_CONVERTED,
    }
    normalized_target_pool = legacy_target_pool_aliases.get(_normalized_text(target_pool), _normalized_text(target_pool))
    allowed_pools = {
        POOL_PENDING_QUESTIONNAIRE,
        POOL_OPERATING,
        POOL_WON,
        POOL_NO_REPLY,
        POOL_HUMAN_REPLY,
    }
    if normalized_target_pool not in allowed_pools:
        raise ValueError("invalid target_pool")

    def mutate(current: dict[str, Any], context: dict[str, Any]) -> tuple[dict[str, Any], str, bool]:
        previous_pool = _normalized_text(current.get("current_pool"))
        if previous_pool not in {POOL_REMOVED, POOL_WON, POOL_NO_REPLY, POOL_HUMAN_REPLY}:
            current["last_active_pool"] = previous_pool

        current["source_type"] = SOURCE_TYPE_SYSTEM
        current["decision_source"] = DECISION_SOURCE_SYSTEM
        current["joined_at"] = current.get("joined_at") or _iso_now()

        if normalized_target_pool == POOL_WON:
            current["in_pool"] = True
            current["current_pool"] = POOL_WON
            current["questionnaire_status"] = QUESTIONNAIRE_SUBMITTED
            return current, f"router_target_pool={normalized_target_pool}", False

        current["in_pool"] = True
        current["current_pool"] = normalized_target_pool

        if normalized_target_pool == POOL_OPERATING:
            current["follow_type"] = FOLLOWUP_NORMAL
            current["questionnaire_status"] = QUESTIONNAIRE_SUBMITTED
        elif normalized_target_pool == POOL_PENDING_QUESTIONNAIRE:
            current["questionnaire_status"] = QUESTIONNAIRE_PENDING

        return current, f"router_target_pool={normalized_target_pool}", False

    return _mutate_member(
        external_contact_id=external_contact_id,
        phone=phone,
        action="router_apply_pool",
        operator_id=_normalized_text(operator_id) or "lobster_callback",
        operator_type=_normalized_text(operator_type) or "system",
        include_detail=False,
        mutate=mutate,
    )


def put_in_pool(*, external_contact_id: str = "", phone: str = "", operator_id: str = "") -> dict[str, Any]:
    def mutate(current: dict[str, Any], context: dict[str, Any]) -> tuple[dict[str, Any], str]:
        if _normalized_text(current.get("current_pool")) == POOL_WON:
            current["in_pool"] = False
            return current, "已成交客户保持已成交状态，不自动恢复到活跃池"
        current["in_pool"] = True
        current["source_type"] = SOURCE_TYPE_MANUAL
        current["joined_at"] = current.get("joined_at") or _iso_now()
        if not current.get("decision_source"):
            current["decision_source"] = DECISION_SOURCE_SYSTEM
        return current, ""

    return _mutate_member(
        external_contact_id=external_contact_id,
        phone=phone,
        action="put_in_pool",
        operator_id=_normalized_text(operator_id) or "crm_console",
        mutate=mutate,
    )


def remove_from_pool(*, external_contact_id: str = "", phone: str = "", operator_id: str = "") -> dict[str, Any]:
    def mutate(current: dict[str, Any], context: dict[str, Any]) -> tuple[dict[str, Any], str]:
        current["in_pool"] = False
        current["current_pool"] = POOL_REMOVED
        return current, ""

    return _mutate_member(
        external_contact_id=external_contact_id,
        phone=phone,
        action="remove_from_pool",
        operator_id=_normalized_text(operator_id) or "crm_console",
        mutate=mutate,
    )


def set_follow_type(*, external_contact_id: str = "", phone: str = "", follow_type: str, operator_id: str = "") -> dict[str, Any]:
    normalized_follow_type = _normalized_text(follow_type)
    if normalized_follow_type not in {FOLLOWUP_NORMAL, FOLLOWUP_FOCUS}:
        raise ValueError("follow_type must be normal or focus")

    def mutate(current: dict[str, Any], context: dict[str, Any]) -> tuple[dict[str, Any], str]:
        current["follow_type"] = normalized_follow_type
        current["decision_source"] = DECISION_SOURCE_MANUAL
        return current, ""

    return _mutate_member(
        external_contact_id=external_contact_id,
        phone=phone,
        action="set_focus" if normalized_follow_type == FOLLOWUP_FOCUS else "set_normal",
        operator_id=_normalized_text(operator_id) or "crm_console",
        mutate=mutate,
    )


def mark_won(*, external_contact_id: str = "", phone: str = "", operator_id: str = "") -> dict[str, Any]:
    def mutate(current: dict[str, Any], context: dict[str, Any]) -> tuple[dict[str, Any], str]:
        current["last_active_pool"] = _normalized_text(current.get("current_pool")) if _normalized_text(current.get("current_pool")) not in {POOL_WON, POOL_REMOVED} else _normalized_text(current.get("last_active_pool"))
        current["in_pool"] = True
        current["current_pool"] = POOL_WON
        current["questionnaire_status"] = QUESTIONNAIRE_SUBMITTED
        return current, ""

    return _mutate_member(
        external_contact_id=external_contact_id,
        phone=phone,
        action="mark_won",
        operator_id=_normalized_text(operator_id) or "crm_console",
        mutate=mutate,
    )


def unmark_won(*, external_contact_id: str = "", phone: str = "", operator_id: str = "") -> dict[str, Any]:
    def mutate(current: dict[str, Any], context: dict[str, Any]) -> tuple[dict[str, Any], str, bool]:
        current["in_pool"] = True
        restore_pool = _normalized_text(current.get("last_active_pool"))
        if restore_pool and restore_pool != POOL_WON:
            current["current_pool"] = restore_pool
            current["last_active_pool"] = restore_pool
        else:
            current["current_pool"] = recompute_pool({**current, "current_pool": POOL_REMOVED}, {**context, "settings": get_signup_conversion_config()}, action="unmark_won")
            current["last_active_pool"] = _normalized_text(current.get("current_pool"))
        return current, "", False

    return _mutate_member(
        external_contact_id=external_contact_id,
        phone=phone,
        action="unmark_won",
        operator_id=_normalized_text(operator_id) or "crm_console",
        mutate=mutate,
    )


def _build_openclaw_payload(member: dict[str, Any]) -> dict[str, Any]:
    from ..admin_console.customer_profile_service import (
        get_customer_messages_payload,
        get_customer_profile_tags_payload,
        get_customer_questionnaire_answers_payload,
    )

    serialized = _serialize_member(member)
    external_contact_id = serialized["external_contact_id"]
    phone = serialized["phone"]
    tags_payload = get_customer_profile_tags_payload(external_userid=external_contact_id) if external_contact_id else {"tags": []}
    questionnaire_payload = get_customer_questionnaire_answers_payload(external_userid=external_contact_id, mobile=phone)
    messages_payload = get_customer_messages_payload(external_userid=external_contact_id, mobile=phone, limit=20)
    return {
        "externalContactId": external_contact_id,
        "currentPool": serialized["current_pool"],
        "currentStage": serialized["current_stage"],
        "currentTarget": serialized["current_target"],
        "tags": [(_normalized_text(item.get("tag_name")) or _normalized_text(item.get("tag_id"))) for item in tags_payload.get("tags") or []],
        "questionnaire": {
            "status": serialized["questionnaire_status"],
            "answers": [
                {
                    "question": _normalized_text(item.get("question")),
                    "answer": _normalized_text(item.get("answer")),
                }
                for item in (questionnaire_payload.get("answers") or [])
            ],
        },
        "recentChats": [
            {
                "role": "customer" if _normalized_text(item.get("sender")) == external_contact_id else "staff",
                "time": _normalized_text(item.get("send_time")),
                "content": _normalized_text(item.get("content")),
            }
            for item in messages_payload.get("messages") or []
        ][:20],
    }


def push_openclaw(*, external_contact_id: str = "", phone: str = "", operator_id: str = "") -> dict[str, Any]:
    member = _resolve_existing_member(external_contact_id=external_contact_id, phone=phone)
    if not member:
        raise LookupError("automation member not found")
    serialized = _serialize_member(member)
    if serialized["current_pool"] == POOL_REMOVED:
        raise ValueError("removed member cannot push openclaw")
    cooldown_until = _parse_timestamp(serialized["ai_cooldown_until"])
    now = datetime.now()
    if cooldown_until and cooldown_until > now:
        remaining_seconds = max(1, int((cooldown_until - now).total_seconds()))
        repo.insert_ai_push_log(
            member_id=int(serialized["id"]),
            scene=AI_PUSH_SCENE_SIDEBAR_SCRIPT,
            request_payload={"memberId": str(serialized["id"])},
            status="cooldown_blocked",
            error_message=f"cooldown:{remaining_seconds}",
            pushed_at=_iso_now(),
            cooldown_until=serialized["ai_cooldown_until"],
        )
        get_db().commit()
        return {"accepted": False, "status": "cooldown_blocked", "remaining_seconds": remaining_seconds}
    payload = _build_openclaw_payload(member)
    delivery = send_outbound_webhook(
        event_type=EVENT_OPENCLAW_FOCUS_MESSAGE,
        payload=payload,
        source_key="automation_member",
        source_id=str(serialized["id"]),
    )
    now_text = _iso_now()
    if delivery.get("ok"):
        cooldown_until_text = (datetime.now() + timedelta(seconds=AI_PUSH_COOLDOWN_SECONDS)).strftime("%Y-%m-%d %H:%M:%S")
        updated = _persist_member(
            member,
            {
                **serialized,
                "last_ai_push_at": now_text,
                "ai_cooldown_until": cooldown_until_text,
            },
        )
        repo.insert_ai_push_log(
            member_id=int(serialized["id"]),
            scene=AI_PUSH_SCENE_SIDEBAR_SCRIPT,
            request_payload=payload,
            status="accepted",
            request_id=str(((delivery.get("delivery") or {}).get("id") or "")),
            pushed_at=now_text,
            cooldown_until=cooldown_until_text,
        )
        get_db().commit()
        return {
            "accepted": True,
            "status": "accepted",
            "member": _serialize_member(updated),
            "cooldown_until": cooldown_until_text,
        }
    repo.insert_ai_push_log(
        member_id=int(serialized["id"]),
        scene=AI_PUSH_SCENE_SIDEBAR_SCRIPT,
        request_payload=payload,
        status="failed",
        request_id=str(((delivery.get("delivery") or {}).get("id") or "")),
        error_message=_normalized_text(delivery.get("reason")),
        pushed_at=now_text,
        cooldown_until="",
    )
    get_db().commit()
    return {"accepted": False, "status": "failed", "error": _normalized_text(delivery.get("reason")) or "openclaw webhook failed"}


def get_overview_payload() -> dict[str, Any]:
    refresh_expired_silent_members()
    counts = repo.get_overview_counts()
    metrics_map = {_normalized_text(item.get("current_pool")): item for item in repo.get_stage_metrics()}
    message_activity_sync = _message_activity_sync_status_payload()
    reply_monitor = _reply_monitor_status_payload()
    config = get_signup_conversion_config()
    cards = [
        {"key": "in_pool_total", "label": "在池总人数", "value": counts["in_pool_total"], "description": "当前仍在自动化池里的成员数量。"},
        {"key": "today_joined", "label": "今日入池", "value": counts["today_joined"], "description": "今天新进入自动化池的成员数量。"},
        {"key": "questionnaire_pending", "label": "未填问卷人群", "value": counts["questionnaire_pending"], "description": "已入池但还没提交问卷。"},
        {"key": "operating_total", "label": "运营中人群", "value": counts["operating_total"], "description": "问卷提交后的统一运营人群。"},
        {"key": "converted_total", "label": "已转化人群", "value": counts["converted_total"], "description": "确认转化后的成员数量。"},
    ]
    stage_columns = []
    for definition in STAGE_DEFINITIONS:
        metric = metrics_map.get(definition["pool"], {})
        stage_columns.append(
            {
                "route_key": definition["route_key"],
                "pool": definition["pool"],
                "label": definition["label"],
                "description": definition["description"],
                "total_count": int(metric.get("total_count") or 0),
                "focus_count": int(metric.get("focus_count") or 0),
                "normal_count": int(metric.get("normal_count") or 0),
                "today_new_count": int(metric.get("today_new_count") or 0),
            }
        )
    return {
        "cards": cards,
        "stage_columns": stage_columns,
        "counts": counts,
        "message_activity_sync": message_activity_sync,
        "reply_monitor": reply_monitor,
        "auto_start_window": _auto_start_window_payload(config),
    }


def get_stage_detail_payload(*, route_key: str, keyword: str = "", limit: int = 50, offset: int = 0) -> dict[str, Any]:
    refresh_expired_silent_members()
    pool = ROUTE_KEY_TO_POOL.get(_normalized_text(route_key))
    if not pool:
        raise ValueError("invalid stage")
    definition = POOL_TO_STAGE_DEF[pool]
    metrics_map = {_normalized_text(item.get("current_pool")): item for item in repo.get_stage_metrics()}
    metric = metrics_map.get(pool, {})
    rows = repo.list_stage_members(current_pool=pool, keyword=keyword, limit=limit, offset=offset)
    customers = []
    for row in rows:
        serialized = _serialize_member(row)
        profile = _load_profile(serialized["external_contact_id"], serialized["phone"])
        customers.append(
            {
                "member_id": serialized["id"],
                "external_userid": serialized["external_contact_id"],
                "customer_name": _normalized_text(profile.get("customer_name")) or serialized["external_contact_id"],
                "owner_display_name": _normalized_text(profile.get("owner_display_name"))
                or _normalized_text(profile.get("owner_staff_id"))
                or serialized["owner_staff_id"],
                "owner_userid": _normalized_text(profile.get("owner_staff_id")) or serialized["owner_staff_id"],
                "mobile": serialized["phone"],
                "last_touch_at": serialized["updated_at"] or serialized["joined_at"],
                "current_stage_label": serialized["current_stage_label"],
                "current_target_label": serialized["current_target_label"],
            }
        )
    total = repo.count_stage_members(current_pool=pool, keyword=keyword)
    return {
        "stage": {
            "pool": pool,
            "route_key": definition["route_key"],
            "label": definition["label"],
            "description": definition["description"],
            "total_count": int(metric.get("total_count") or 0),
            "focus_count": int(metric.get("focus_count") or 0),
            "normal_count": int(metric.get("normal_count") or 0),
            "today_new_count": int(metric.get("today_new_count") or 0),
        },
        "filters": {"keyword": _normalized_text(keyword)},
        "customers": customers,
        "pagination": {
            "total": int(total),
            "offset": int(offset),
            "limit": int(limit),
            "has_prev": int(offset) > 0,
            "has_next": int(offset) + int(limit) < int(total),
            "prev_offset": max(int(offset) - int(limit), 0),
            "next_offset": int(offset) + int(limit),
        },
    }


def _dispatch_private_message_batch(
    *,
    target_items: list[dict[str, Any]],
    content: str,
    image_media_ids: list[str] | None = None,
    images: list[dict[str, Any]] | None = None,
    operator_id: str,
    filter_snapshot: dict[str, Any],
) -> dict[str, Any]:
    normalized_content = _normalized_text(content)
    normalized_image_media_ids = _normalize_manual_send_image_media_ids(image_media_ids)
    task_payload, content_preview, image_count = user_ops_page_service._build_private_message_payload(
        {
            "content": normalized_content,
            "image_media_ids": normalized_image_media_ids,
            "images": list(images or []),
        }
    )
    outbound_task_ids: list[int] = []
    task_results: list[dict[str, Any]] = []
    fail_external_userids: list[str] = []
    request_payload = {
        "sender": DEFAULT_OWNER_STAFF_ID,
        "external_userid": [_normalized_text(item.get("external_userid")) for item in target_items if _normalized_text(item.get("external_userid"))],
        **task_payload,
    }
    try:
        wecom_result = dispatch_wecom_task("private_message", "create_private_message_task", request_payload)
        fail_external_userids = [
            _normalized_text(item)
            for item in (wecom_result.get("wecom_result") or {}).get("fail_list", [])
            if _normalized_text(item)
        ]
        outbound_task_ids.append(int(wecom_result["task_id"]))
        task_results.append(user_ops_page_service._build_sender_success_result(DEFAULT_OWNER_STAFF_ID, target_items, wecom_result))
    except (WeComClientError, AttributeError) as exc:
        task_results.append(user_ops_page_service._build_sender_failure_result(DEFAULT_OWNER_STAFF_ID, target_items, exc))

    if fail_external_userids:
        sent_count = max(0, len(target_items) - len(set(fail_external_userids)))
        if sent_count > 0:
            status = "partial_failed"
        else:
            status = "failed"
    else:
        sent_count = sum(int(item.get("target_count") or 0) for item in task_results if _normalized_text(item.get("status")) != "failed")
        status = user_ops_page_service._derive_record_status(task_results, eligible_count=len(target_items))
    record_id = user_ops_page_service._insert_send_record(
        outbound_task_ids=outbound_task_ids,
        task_results=task_results,
        selected_count=len(target_items),
        eligible_count=len(target_items),
        sent_count=sent_count,
        skipped_count=0,
        skipped_reasons={},
        include_do_not_disturb=False,
        content_preview=content_preview,
        image_count=image_count,
        sender_userids=[DEFAULT_OWNER_STAFF_ID],
        filter_snapshot=filter_snapshot,
        operator=_normalized_text(operator_id) or "crm_console",
        status=status,
    )
    return {
        "ok": status != "failed",
        "status": status,
        "record_id": int(record_id),
        "task_ids": outbound_task_ids,
        "task_results": task_results,
        "content_preview": content_preview,
        "image_count": image_count,
        "sent_count": sent_count,
        "fail_external_userids": fail_external_userids,
        "error": (
            _normalized_text(task_results[0].get("error_message"))
            if status == "failed" and task_results
            else ""
        ),
    }


def _stage_manual_send_targets(route_key: str) -> dict[str, Any]:
    definition = _manual_send_stage_definition(route_key)
    pool_key = _normalized_text(definition.get("pool"))
    rows = [_serialize_member(row) for row in repo.list_stage_members_for_manual_send(current_pool=pool_key)]
    final_targets: list[dict[str, Any]] = []
    sendable_targets: list[dict[str, Any]] = []
    skipped_reasons: dict[str, int] = {}
    for member in rows:
        external_userid = _normalized_text(member.get("external_contact_id"))
        target = {
            "member_id": int(member.get("id") or 0),
            "external_userid": external_userid,
            "owner_userid": DEFAULT_OWNER_STAFF_ID,
            "owner_display_name": DEFAULT_OWNER_STAFF_ID,
            "mobile": _normalized_text(member.get("phone")),
        }
        final_targets.append(target)
        if not external_userid:
            skipped_reasons["missing_external_userid"] = int(skipped_reasons.get("missing_external_userid") or 0) + 1
            continue
        sendable_targets.append(target)
    return {
        "definition": definition,
        "pool_key": pool_key,
        "rows": rows,
        "final_targets": final_targets,
        "sendable_targets": sendable_targets,
        "selected_count": len(rows),
        "eligible_count": len(sendable_targets),
        "skipped_count": sum(int(value or 0) for value in skipped_reasons.values()),
        "skipped_reasons": skipped_reasons,
    }


def preview_stage_manual_send(
    *,
    route_key: str,
    content: str = "",
    image_media_ids: list[str] | None = None,
    images: list[dict[str, Any]] | None = None,
    attachments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    targets_payload = _stage_manual_send_targets(route_key)
    task_payload, content_preview, image_count = user_ops_page_service._build_private_message_payload(
        {
            "content": _normalized_text(content),
            "image_media_ids": list(image_media_ids or []),
            "images": list(images or []),
            "attachments": list(attachments or []),
        }
    )
    return {
        "ok": True,
        "stage_key": _normalized_text(route_key),
        "pool_key": _normalized_text(targets_payload.get("pool_key")),
        "stage_label": _normalized_text((targets_payload.get("definition") or {}).get("label")),
        "selected_count": int(targets_payload.get("selected_count") or 0),
        "eligible_count": int(targets_payload.get("eligible_count") or 0),
        "skipped_count": int(targets_payload.get("skipped_count") or 0),
        "skipped_reasons": dict(targets_payload.get("skipped_reasons") or {}),
        "final_targets": list(targets_payload.get("final_targets") or []),
        "task_payload": task_payload,
        "content_preview": content_preview,
        "image_count": image_count,
    }


def send_stage_manual_message(
    *,
    route_key: str,
    content: str = "",
    image_media_ids: list[str] | None = None,
    images: list[dict[str, Any]] | None = None,
    attachments: list[dict[str, Any]] | None = None,
    operator_id: str = "",
) -> dict[str, Any]:
    user_ops_page_service._build_private_message_payload(
        {
            "content": _normalized_text(content),
            "image_media_ids": list(image_media_ids or []),
            "images": list(images or []),
            "attachments": list(attachments or []),
        }
    )
    targets_payload = _stage_manual_send_targets(route_key)
    dispatch_result = _dispatch_private_message_batch(
        target_items=list(targets_payload.get("sendable_targets") or []),
        content=_normalized_text(content),
        image_media_ids=list(image_media_ids or []),
        images=list(images or []),
        operator_id=_normalized_text(operator_id) or "crm_console",
        filter_snapshot={
            "selection_mode": "automation_conversion_stage",
            "stage_key": _normalized_text(route_key),
            "pool_key": _normalized_text(targets_payload.get("pool_key")),
        },
    ) if int(targets_payload.get("eligible_count") or 0) > 0 else {
        "ok": False,
        "status": "skipped",
        "record_id": 0,
        "task_ids": [],
        "task_results": [],
        "content_preview": _normalized_text(content),
        "image_count": len(list(image_media_ids or [])) + len(list(images or [])),
        "sent_count": 0,
        "fail_external_userids": [],
        "error": "",
    }
    return {
        "ok": bool(dispatch_result.get("ok")) or int(targets_payload.get("eligible_count") or 0) == 0,
        "stage_key": _normalized_text(route_key),
        "pool_key": _normalized_text(targets_payload.get("pool_key")),
        "stage_label": _normalized_text((targets_payload.get("definition") or {}).get("label")),
        "total_target_count": int(targets_payload.get("selected_count") or 0),
        "eligible_count": int(targets_payload.get("eligible_count") or 0),
        "sent_count": int(dispatch_result.get("sent_count") or 0),
        "skipped_count": int(targets_payload.get("skipped_count") or 0),
        "skipped_reasons": dict(targets_payload.get("skipped_reasons") or {}),
        "record_id": int(dispatch_result.get("record_id") or 0),
        "task_ids": list(dispatch_result.get("task_ids") or []),
        "task_results": list(dispatch_result.get("task_results") or []),
        "content_preview": _normalized_text(dispatch_result.get("content_preview")),
        "image_count": int(dispatch_result.get("image_count") or 0),
        "error": _normalized_text(dispatch_result.get("error")),
    }


def _sop_skip_reason_label(reason: str) -> str:
    normalized_reason = _normalized_text(reason)
    return SOP_RUN_SKIPPED_REASON_LABELS.get(normalized_reason, normalized_reason or "未知原因")


def _parse_sop_send_time(send_time: str) -> tuple[int, int]:
    normalized = _normalize_sop_send_time(send_time)
    hour_text, minute_text = normalized.split(":", 1)
    return int(hour_text), int(minute_text)


def _next_sop_send_slot(reference: datetime, *, send_time: str) -> datetime:
    hour, minute = _parse_sop_send_time(send_time)
    scheduled = reference.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if reference < scheduled:
        return scheduled
    return scheduled + timedelta(days=1)


def _scheduled_sop_datetime_for_date(day_text: str, *, send_time: str) -> datetime | None:
    normalized_day_text = _normalized_text(day_text)
    if not normalized_day_text:
        return None
    try:
        return datetime.strptime(f"{normalized_day_text} {_normalize_sop_send_time(send_time)}", "%Y-%m-%d %H:%M")
    except ValueError:
        return None


def _current_sop_day_index(progress: dict[str, Any], *, now_dt: datetime) -> int:
    anchor_dt = _scheduled_sop_datetime_for_date(_normalized_text(progress.get("sop_anchor_date")), send_time="00:00")
    if anchor_dt is None:
        return 0
    return (now_dt.date() - anchor_dt.date()).days + 1


def _progress_anchor_timestamp(member: dict[str, Any], progress: dict[str, Any], *, now_text: str) -> str:
    return (
        _normalized_text(progress.get("last_in_pool_at"))
        or _normalized_text(progress.get("last_entered_at"))
        or _normalized_text(progress.get("first_entered_at"))
        or _normalized_text(member.get("joined_at"))
        or _normalized_text(member.get("created_at"))
        or now_text
    )


def _get_or_create_sop_progress(member: dict[str, Any], *, pool_config: dict[str, Any], now_text: str) -> dict[str, Any]:
    pool_key = _validate_sop_pool_key(pool_config.get("pool_key"))
    member_id = int(member.get("id") or 0)
    progress = _serialize_sop_progress(repo.get_sop_progress(member_id=member_id, pool_key=pool_key))
    if progress and _normalized_text(progress.get("sop_anchor_date")) and _normalized_text(progress.get("first_effective_in_pool_at")):
        return progress
    return _upsert_sop_progress_entry(
        member_id=member_id,
        pool_key=pool_key,
        entered_at=_progress_anchor_timestamp(member, progress, now_text=now_text),
        pool_config=pool_config,
    )


def _evaluate_sop_due(
    *,
    member: dict[str, Any],
    progress: dict[str, Any],
    pool_config: dict[str, Any],
    now_dt: datetime,
    now_text: str,
) -> dict[str, Any]:
    pool_key = _validate_sop_pool_key(pool_config.get("pool_key"))
    last_sent_day = int(progress.get("last_sent_day") or 0)
    current_day_index = max(_current_sop_day_index(progress, now_dt=now_dt), last_sent_day)
    max_template_day = max(_current_sop_template_day_count(pool_key), 1)
    current_day_index = max(min(current_day_index, max_template_day), last_sent_day)
    send_time = _normalize_sop_send_time(pool_config.get("send_time"))
    today_scheduled_dt = _scheduled_sop_datetime_for_date(now_dt.strftime("%Y-%m-%d"), send_time=send_time)
    if current_day_index <= 0:
        anchor_scheduled_dt = _scheduled_sop_datetime_for_date(_normalized_text(progress.get("sop_anchor_date")), send_time=send_time)
        return {
            "member": member,
            "progress": progress,
            "day_index": 0,
            "scheduled_for": anchor_scheduled_dt.strftime("%Y-%m-%d %H:%M:%S") if anchor_scheduled_dt else now_text,
            "skip_reason": "send_time_not_reached",
        }
    scheduled_for = today_scheduled_dt.strftime("%Y-%m-%d %H:%M:%S") if today_scheduled_dt else now_text
    skip_reason = "send_time_not_reached" if today_scheduled_dt and now_dt < today_scheduled_dt else ""
    return {
        "member": member,
        "progress": progress,
        "day_index": current_day_index,
        "scheduled_for": scheduled_for,
        "skip_reason": skip_reason,
    }


def _normalize_sop_template_images(template: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    image_media_ids: list[str] = []
    images: list[dict[str, Any]] = []
    for item in list(template.get("images_json") or []):
        if isinstance(item, str):
            normalized_media_id = _normalized_text(item)
            if normalized_media_id:
                image_media_ids.append(normalized_media_id)
            continue
        if not isinstance(item, dict):
            continue
        normalized_media_id = _normalized_text(item.get("media_id") or item.get("image_media_id"))
        if normalized_media_id:
            image_media_ids.append(normalized_media_id)
            continue
        if _normalized_text(item.get("data_base64")) or _normalized_text(item.get("data_url")):
            images.append(
                {
                    "file_name": _normalized_text(item.get("file_name")) or "sop-image.png",
                    "content_type": _normalized_text(item.get("content_type")) or "image/png",
                    "data_base64": _normalized_text(item.get("data_base64")),
                    "data_url": _normalized_text(item.get("data_url")),
                }
            )
    deduped_media_ids: list[str] = []
    seen_media_ids: set[str] = set()
    for media_id in image_media_ids:
        if media_id in seen_media_ids:
            continue
        seen_media_ids.add(media_id)
        deduped_media_ids.append(media_id)
    return deduped_media_ids, images


def _template_skip_reason(template: dict[str, Any]) -> str:
    if not template:
        return "no_template"
    if not _normalize_bool(template.get("enabled")):
        return "template_disabled"
    content = _normalized_text(template.get("content"))
    image_media_ids, images = _normalize_sop_template_images(template)
    if not content and not image_media_ids and not images:
        return "template_empty"
    return ""


def _create_sop_batch(
    *,
    pool_key: str,
    day_index: int,
    template: dict[str, Any] | None,
    scheduled_for: str,
    total_count: int,
    summary_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _serialize_sop_batch(
        repo.insert_sop_batch(
            {
                "pool_key": pool_key,
                "day_index": int(day_index),
                "template_id": template.get("id") if template else None,
                "scheduled_for": _normalized_text(scheduled_for),
                "status": "finished",
                "total_count": int(total_count),
                "success_count": 0,
                "skipped_count": 0,
                "failed_count": 0,
                "summary_json": dict(summary_json or {}),
            }
        )
    )


def _record_sop_batch_item(
    *,
    batch_id: int,
    member: dict[str, Any] | None,
    pool_key: str,
    day_index: int,
    external_userid: str,
    status: str,
    content_snapshot: str = "",
    images_snapshot: list[dict[str, Any]] | None = None,
    error_message: str = "",
    sent_record_id: int | None = None,
) -> dict[str, Any]:
    return _serialize_sop_batch_item(
        repo.insert_sop_batch_item(
            {
                "batch_id": int(batch_id),
                "member_id": int(member.get("id") or 0) if member else None,
                "pool_key": pool_key,
                "day_index": int(day_index),
                "day_index_snapshot": int(day_index),
                "external_userid": _normalized_text(external_userid),
                "status": _normalized_text(status),
                "error_message": _normalized_text(error_message),
                "content_snapshot": _normalized_text(content_snapshot),
                "images_snapshot": list(images_snapshot or []),
                "sent_record_id": sent_record_id,
            }
        )
    )


def _finalize_sop_batch(
    batch: dict[str, Any],
    *,
    success_count: int,
    skipped_count: int,
    failed_count: int,
    skipped_reasons: dict[str, int],
    success_record_ids: list[int],
) -> dict[str, Any]:
    total_count = int(batch.get("total_count") or 0)
    updated = repo.update_sop_batch(
        int(batch["id"]),
        {
            **batch,
            "status": "finished",
            "success_count": int(success_count),
            "skipped_count": int(skipped_count),
            "failed_count": int(failed_count),
            "summary_json": {
                "pool_key": _normalized_text(batch.get("pool_key")),
                "day_index": int(batch.get("day_index") or 0),
                "total_count": total_count,
                "success_count": int(success_count),
                "skipped_count": int(skipped_count),
                "failed_count": int(failed_count),
                "skipped_reasons": dict(skipped_reasons),
                "skipped_reason_labels": {key: _sop_skip_reason_label(key) for key in skipped_reasons},
                "success_record_ids": list(success_record_ids),
            },
        },
    )
    return _serialize_sop_batch(updated)


def _update_sop_progress_day(
    progress: dict[str, Any],
    *,
    day_index: int,
    sent_at: str,
) -> dict[str, Any]:
    return _serialize_sop_progress(
        repo.save_sop_progress(
            {
                "member_id": int(progress.get("member_id") or 0),
                "pool_key": _normalized_text(progress.get("pool_key")),
                "first_entered_at": _normalized_text(progress.get("first_entered_at")),
                "last_entered_at": _normalized_text(progress.get("last_entered_at")),
                "sop_anchor_date": _normalized_text(progress.get("sop_anchor_date")),
                "first_effective_in_pool_at": _normalized_text(progress.get("first_effective_in_pool_at")),
                "last_in_pool_at": _normalized_text(progress.get("last_in_pool_at")),
                "last_sent_day": int(day_index),
                "last_sent_at": _normalized_text(sent_at),
                "completed_at": _normalized_text(progress.get("completed_at")),
            }
        )
    )


def run_due_sop(
    *,
    operator_id: str = "",
    operator_type: str = "system",
) -> dict[str, Any]:
    ensure_sop_v1_defaults()
    now_text = _iso_now()
    now_dt = _parse_timestamp(now_text) or datetime.now()
    enabled_configs = [
        dict(item)
        for item in (get_sop_v1_config_payload().get("configs") or [])
        if _normalize_bool(item.get("enabled"))
    ]
    batch_ids: list[int] = []
    batches_payload: list[dict[str, Any]] = []
    total_success_count = 0
    total_skipped_count = 0
    total_failed_count = 0
    created_batch_count = 0

    for pool_config in enabled_configs:
        pool_key = _validate_sop_pool_key(pool_config.get("pool_key"))
        if not repo.try_acquire_sop_pool_run_lock(pool_key=pool_key):
            continue

        members = [_serialize_member(row) for row in repo.list_stage_members_for_manual_send(current_pool=pool_key)]
        due_members: list[dict[str, Any]] = []
        for member in members:
            progress = _get_or_create_sop_progress(member, pool_config=pool_config, now_text=now_text)
            due_payload = _evaluate_sop_due(
                member=member,
                progress=progress,
                pool_config=pool_config,
                now_dt=now_dt,
                now_text=now_text,
            )
            if _normalized_text(due_payload.get("skip_reason")) == "send_time_not_reached":
                continue
            day_index = int(due_payload.get("day_index") or 0)
            if day_index <= 0:
                continue
            if repo.get_sop_batch_item_for_member_day(
                member_id=int(member.get("id") or 0),
                pool_key=pool_key,
                day_index_snapshot=day_index,
            ):
                continue
            template = _serialize_sop_template(repo.get_sop_template(pool_key=pool_key, day_index=day_index))
            template_skip_reason = _template_skip_reason(template)
            due_members.append(
                {
                    "member": member,
                    "progress": progress,
                    "day_index": day_index,
                    "scheduled_for": _normalized_text(due_payload.get("scheduled_for")) or now_text,
                    "template": template,
                    "template_skip_reason": template_skip_reason,
                }
            )

        groups: dict[tuple[str, int], list[dict[str, Any]]] = {}
        for candidate in due_members:
            group_key = (pool_key, int(candidate.get("day_index") or 0))
            groups.setdefault(group_key, []).append(candidate)

        for (_, day_index), candidates in sorted(groups.items(), key=lambda item: item[0][1]):
            template = dict((candidates[0] or {}).get("template") or {})
            batch = _create_sop_batch(
                pool_key=pool_key,
                day_index=day_index,
                template=template or None,
                scheduled_for=_normalized_text((candidates[0] or {}).get("scheduled_for")) or now_text,
                total_count=len(candidates),
                summary_json={"operator_type": _normalized_text(operator_type) or "system", "operator_id": _normalized_text(operator_id) or "sop_runner"},
            )
            created_batch_count += 1
            batch_ids.append(int(batch.get("id") or 0))

            sendable_targets: list[dict[str, Any]] = []
            sendable_candidates: list[dict[str, Any]] = []
            skipped_count = 0
            failed_count = 0
            success_count = 0
            skipped_reasons: dict[str, int] = {}
            success_record_ids: list[int] = []

            for candidate in candidates:
                member = dict(candidate.get("member") or {})
                progress = dict(candidate.get("progress") or {})
                external_userid = _normalized_text(member.get("external_contact_id"))
                skip_reason = _normalized_text(candidate.get("template_skip_reason"))
                if not external_userid:
                    skip_reason = "missing_external_userid"
                if skip_reason:
                    _record_sop_batch_item(
                        batch_id=int(batch.get("id") or 0),
                        member=member,
                        pool_key=pool_key,
                        day_index=day_index,
                        external_userid=external_userid,
                        status="skipped",
                        error_message=skip_reason,
                    )
                    _update_sop_progress_day(progress, day_index=day_index, sent_at=now_text)
                    skipped_count += 1
                    skipped_reasons[skip_reason] = int(skipped_reasons.get(skip_reason) or 0) + 1
                    continue
                sendable_targets.append(
                    {
                        "member_id": int(member.get("id") or 0),
                        "external_userid": external_userid,
                        "owner_userid": DEFAULT_OWNER_STAFF_ID,
                        "owner_display_name": DEFAULT_OWNER_STAFF_ID,
                        "mobile": _normalized_text(member.get("phone")),
                    }
                )
                sendable_candidates.append(candidate)

            dispatch_result = None
            if sendable_targets:
                image_media_ids, images = _normalize_sop_template_images(template)
                dispatch_result = _dispatch_private_message_batch(
                    target_items=sendable_targets,
                    content=_normalized_text(template.get("content")),
                    image_media_ids=image_media_ids,
                    images=images,
                    operator_id=_normalized_text(operator_id) or "sop_runner",
                    filter_snapshot={
                        "selection_mode": "automation_conversion_sop",
                        "pool_key": pool_key,
                        "day_index": day_index,
                    },
                )
                if int(dispatch_result.get("record_id") or 0) > 0:
                    success_record_ids.append(int(dispatch_result["record_id"]))
                failed_external_userids = {
                    _normalized_text(item)
                    for item in list(dispatch_result.get("fail_external_userids") or [])
                    if _normalized_text(item)
                }
                for target, candidate in zip(sendable_targets, sendable_candidates):
                    member = dict(candidate.get("member") or {})
                    progress = dict(candidate.get("progress") or {})
                    external_userid = _normalized_text(target.get("external_userid"))
                    if external_userid in failed_external_userids:
                        _record_sop_batch_item(
                            batch_id=int(batch.get("id") or 0),
                            member=member,
                            pool_key=pool_key,
                            day_index=day_index,
                            external_userid=external_userid,
                            status="failed",
                            error_message="dispatch_failed",
                            sent_record_id=int(dispatch_result.get("record_id") or 0) or None,
                        )
                        failed_count += 1
                    else:
                        _record_sop_batch_item(
                            batch_id=int(batch.get("id") or 0),
                            member=member,
                            pool_key=pool_key,
                            day_index=day_index,
                            external_userid=external_userid,
                            status="success",
                            content_snapshot=_normalized_text(template.get("content")),
                            images_snapshot=list(template.get("images_json") or []),
                            sent_record_id=int(dispatch_result.get("record_id") or 0) or None,
                        )
                        success_count += 1
                    _update_sop_progress_day(progress, day_index=day_index, sent_at=now_text)

            finalized = _finalize_sop_batch(
                batch,
                success_count=success_count,
                skipped_count=skipped_count,
                failed_count=failed_count,
                skipped_reasons=skipped_reasons,
                success_record_ids=success_record_ids,
            )
            batches_payload.append({"batch": finalized})
            total_success_count += success_count
            total_skipped_count += skipped_count
            total_failed_count += failed_count

    get_db().commit()
    return {
        "ok": True,
        "status": "completed",
        "scanned_pool_count": len(enabled_configs),
        "created_batch_count": created_batch_count,
        "total_success_count": total_success_count,
        "total_skipped_count": total_skipped_count,
        "total_failed_count": total_failed_count,
        "batch_ids": batch_ids,
        "batches": batches_payload,
    }


def list_registered_due_jobs() -> list[dict[str, Any]]:
    return [
        {
            "job_code": "sop",
            "label": "自动化转化 SOP",
            "frequency_minutes": 15,
            "description": "轮询未填问卷人群、运营中人群、已转化人群的 SOP day 模板，到点后按自然日批量发送。",
        },
        {
            "job_code": "conversion_workflow",
            "label": "自动化转化任务流",
            "frequency_minutes": 15,
            "description": "轮询启用中的自动化转化任务流节点，到点后按当前大人群和第 N 天执行发送。",
        }
    ]


def run_registered_due_jobs(
    *,
    job_codes: list[str] | None = None,
    operator_id: str = "",
    operator_type: str = "system",
) -> dict[str, Any]:
    registry = {item["job_code"]: dict(item) for item in list_registered_due_jobs()}
    selected_job_codes = [
        _normalized_text(item)
        for item in (job_codes if job_codes is not None else ["conversion_workflow"])
        if _normalized_text(item)
    ]
    if not selected_job_codes:
        selected_job_codes = ["conversion_workflow"]

    invalid_job_codes = [item for item in selected_job_codes if item not in registry]
    if invalid_job_codes:
        raise ValueError(f"unsupported due jobs: {', '.join(sorted(dict.fromkeys(invalid_job_codes)))}")

    jobs_payload: list[dict[str, Any]] = []
    executed_job_count = 0
    failed_job_count = 0
    total_success_count = 0
    total_skipped_count = 0
    total_failed_count = 0
    batch_ids: list[int] = []

    for job_code in selected_job_codes:
        definition = registry[job_code]
        try:
            if job_code == "sop":
                payload = run_due_sop(
                    operator_id=operator_id or "automation_conversion_due_runner",
                    operator_type=operator_type,
                )
            elif job_code == "conversion_workflow":
                from .workflow_runtime import run_due_conversion_workflows

                payload = run_due_conversion_workflows(
                    operator_id=operator_id or "automation_conversion_due_runner",
                    operator_type=operator_type,
                )
            else:
                raise ValueError(f"unsupported due job runner: {job_code}")
        except Exception as exc:
            failed_job_count += 1
            jobs_payload.append(
                {
                    **definition,
                    "ok": False,
                    "error": str(exc),
                }
            )
            continue

        executed_job_count += 1
        payload_success_count = int(payload.get("total_success_count") or 0)
        payload_skipped_count = int(payload.get("total_skipped_count") or 0)
        payload_failed_count = int(payload.get("total_failed_count") or 0)
        if not payload_success_count and not payload_skipped_count and not payload_failed_count:
            for execution_result in payload.get("executions") or []:
                execution_row = dict((execution_result or {}).get("execution") or {})
                payload_success_count += int(execution_row.get("success_count") or 0)
                payload_skipped_count += int(execution_row.get("skipped_count") or 0)
                payload_failed_count += int(execution_row.get("failed_count") or 0)
        total_success_count += payload_success_count
        total_skipped_count += payload_skipped_count
        total_failed_count += payload_failed_count
        batch_ids.extend(int(item) for item in (payload.get("batch_ids") or []) if int(item or 0))
        jobs_payload.append(
            {
                **definition,
                "ok": bool(payload.get("ok")),
                "result": payload,
            }
        )

    return {
        "ok": failed_job_count == 0,
        "operator_type": _normalized_text(operator_type) or "system",
        "operator_id": _normalized_text(operator_id) or "automation_conversion_due_runner",
        "requested_job_codes": selected_job_codes,
        "executed_job_count": executed_job_count,
        "failed_job_count": failed_job_count,
        "total_success_count": total_success_count,
        "total_skipped_count": total_skipped_count,
        "total_failed_count": total_failed_count,
        "batch_ids": list(dict.fromkeys(batch_ids)),
        "jobs": jobs_payload,
    }


def _focus_batch_detail_payload(batch_row: dict[str, Any] | None, *, item_limit: int = 12) -> dict[str, Any]:
    serialized_batch = _serialize_focus_send_batch(batch_row)
    if not serialized_batch:
        return {}
    items = [
        _serialize_focus_send_batch_item(row)
        for row in repo.list_focus_send_batch_items(batch_id=int(serialized_batch["id"]), limit=max(1, int(item_limit)), descending=False)
    ]
    return {
        "batch": serialized_batch,
        "items": items[-max(1, int(item_limit)) :],
    }


def create_focus_send_batch(
    *,
    route_key: str,
    operator_id: str = "",
    operator_type: str = "user",
) -> dict[str, Any]:
    definition = local_projection.focus_send_stage_definition(route_key)
    existing = repo.find_active_focus_send_batch_by_stage(_normalized_text(route_key))
    if existing:
        detail = _focus_batch_detail_payload(existing)
        return {
            "ok": True,
            "status": "existing",
            **detail,
        }
    now_text = _iso_now()
    pool_key = _normalized_text(definition.get("pool"))
    members = [_serialize_member(row) for row in repo.list_stage_members_for_manual_send(current_pool=pool_key)]
    batch_status = "pending" if members else "finished"
    batch = _serialize_focus_send_batch(
        repo.insert_focus_send_batch(
            {
                "stage_key": _normalized_text(route_key),
                "pool_key": pool_key,
                "operator_type": _normalized_text(operator_type) or "user",
                "operator_id": _normalized_text(operator_id) or "crm_console",
                "status": batch_status,
                "total_count": len(members),
                "sent_count": 0,
                "failed_count": 0,
                "skipped_count": 0,
                "cancelled_count": 0,
                "next_run_at": now_text if members else "",
                "last_run_at": "",
                "created_at": now_text,
                "updated_at": now_text,
                "finished_at": now_text if not members else "",
            }
        )
    )
    items: list[dict[str, Any]] = []
    for position_index, member in enumerate(members, start=1):
        items.append(
            _serialize_focus_send_batch_item(
                repo.insert_focus_send_batch_item(
                    {
                        "batch_id": int(batch.get("id") or 0),
                        "member_id": int(member.get("id") or 0) or None,
                        "external_contact_id": _normalized_text(member.get("external_contact_id")),
                        "phone": _normalized_text(member.get("phone")),
                        "position_index": position_index,
                        "status": "pending",
                        "detail": "",
                        "result_payload": {},
                        "created_at": now_text,
                        "updated_at": now_text,
                        "started_at": "",
                        "finished_at": "",
                    }
                )
            )
        )
    get_db().commit()
    return {
        "ok": True,
        "status": "created",
        "batch": batch,
        "items": items,
    }


def _update_focus_batch_counters(
    batch: dict[str, Any],
    *,
    sent_delta: int = 0,
    failed_delta: int = 0,
    skipped_delta: int = 0,
    status: str = "",
    next_run_at: str = "",
    finished_at: str = "",
    last_run_at: str = "",
) -> dict[str, Any]:
    sent_count = int(batch.get("sent_count") or 0) + int(sent_delta)
    failed_count = int(batch.get("failed_count") or 0) + int(failed_delta)
    skipped_count = int(batch.get("skipped_count") or 0) + int(skipped_delta)
    total_count = int(batch.get("total_count") or 0)
    remaining_count = max(0, total_count - sent_count - failed_count - skipped_count - int(batch.get("cancelled_count") or 0))
    next_status = _normalized_text(status) or ("finished" if remaining_count <= 0 else "running")
    saved = repo.update_focus_send_batch(
        int(batch.get("id") or 0),
        {
            "stage_key": _normalized_text(batch.get("stage_key")),
            "pool_key": _normalized_text(batch.get("pool_key")),
            "operator_type": _normalized_text(batch.get("operator_type")),
            "operator_id": _normalized_text(batch.get("operator_id")),
            "status": next_status,
            "total_count": total_count,
            "sent_count": sent_count,
            "failed_count": failed_count,
            "skipped_count": skipped_count,
            "cancelled_count": int(batch.get("cancelled_count") or 0),
            "next_run_at": _normalized_text(next_run_at),
            "last_run_at": _normalized_text(last_run_at),
            "updated_at": _normalized_text(last_run_at) or _iso_now(),
            "finished_at": _normalized_text(finished_at),
        },
    )
    return _serialize_focus_send_batch(saved)


def run_due_focus_send_batches(
    *,
    operator_id: str = "",
    operator_type: str = "system",
    limit: int = 20,
) -> dict[str, Any]:
    now_text = _iso_now()
    now_dt = _parse_timestamp(now_text) or datetime.now()
    processed_count = 0
    batches_payload: list[dict[str, Any]] = []
    for row in repo.list_due_focus_send_batches(due_at=now_text, limit=max(1, int(limit))):
        batch = _serialize_focus_send_batch(row)
        item = repo.claim_next_focus_send_batch_item(batch_id=int(batch.get("id") or 0), started_at=now_text)
        if not item:
            finalized = _update_focus_batch_counters(
                batch,
                status="finished",
                next_run_at="",
                finished_at=now_text,
                last_run_at=now_text,
            )
            batches_payload.append(_focus_batch_detail_payload(finalized, item_limit=12))
            continue
        serialized_item = _serialize_focus_send_batch_item(item)
        external_contact_id = _normalized_text(serialized_item.get("external_contact_id"))
        push_result = push_openclaw(
            external_contact_id=external_contact_id,
            operator_id=_normalized_text(operator_id) or "focus_send_runner",
        )
        accepted = bool(push_result.get("accepted"))
        item_status = "sent" if accepted else "failed"
        repo.update_focus_send_batch_item(
            int(serialized_item.get("id") or 0),
            {
                **serialized_item,
                "status": item_status,
                "detail": "" if accepted else (_normalized_text(push_result.get("error")) or _normalized_text(push_result.get("status"))),
                "result_payload": dict(push_result or {}),
                "updated_at": now_text,
                "started_at": _normalized_text(serialized_item.get("started_at")) or now_text,
                "finished_at": now_text,
            },
        )
        processed_count += 1
        refreshed_batch = _update_focus_batch_counters(
            batch,
            sent_delta=1 if accepted else 0,
            failed_delta=0 if accepted else 1,
            next_run_at=(
                ""
                if (int(batch.get("remaining_count") or 0) - 1) <= 0
                else (now_dt + timedelta(seconds=FOCUS_SEND_INTERVAL_SECONDS)).strftime("%Y-%m-%d %H:%M:%S")
            ),
            finished_at=now_text if (int(batch.get("remaining_count") or 0) - 1) <= 0 else "",
            last_run_at=now_text,
        )
        batches_payload.append(_focus_batch_detail_payload(refreshed_batch, item_limit=12))
    get_db().commit()
    return {
        "ok": True,
        "processed_count": processed_count,
        "batches": batches_payload,
    }


def get_focus_send_batch_detail(*, batch_id: int, item_limit: int = 12) -> dict[str, Any]:
    batch_row = repo.get_focus_send_batch(int(batch_id))
    if not batch_row:
        raise LookupError("focus send batch not found")
    return _focus_batch_detail_payload(batch_row, item_limit=item_limit)


def _event_payloads(member_id: int, limit: int = 10) -> list[dict[str, Any]]:
    return [repo.deserialize_event_row(row) for row in repo.list_recent_events(member_id, limit=limit)]


def get_debug_payload(*, external_contact_id: str = "", phone: str = "") -> dict[str, Any]:
    normalized_external_contact_id = _normalized_text(external_contact_id)
    normalized_phone = _normalized_text(phone)
    if not normalized_external_contact_id and not normalized_phone:
        empty_member = _serialize_member({})
        return {
            "lookup": {"external_contact_id": "", "phone": ""},
            "member_exists": False,
            "member": empty_member,
            "profile": {
                "customer_name": "未命名客户",
                "owner_staff_id": "",
                "owner_display_name": "",
                "external_contact_id": "",
                "phone": "",
                "unionid": "",
            },
            "questionnaire": {
                "status": QUESTIONNAIRE_PENDING,
                "status_label": _questionnaire_status_label(QUESTIONNAIRE_PENDING),
                "hit_count": 0,
                "matched_questions": [],
                "submitted_at": "",
            },
            "current_pool": empty_member["current_pool"],
            "current_stage": empty_member["current_stage"],
            "current_target": empty_member["current_target"],
            "manual_override_preferred": False,
            "recent_events": [],
        }
    detail = get_member_detail(external_contact_id=external_contact_id, phone=phone)
    member = detail["member"]
    events = _event_payloads(int(member["id"]), 10) if detail["member_exists"] and int(member["id"] or 0) > 0 else []
    return {
        "lookup": {"external_contact_id": _normalized_text(external_contact_id), "phone": _normalized_text(phone)},
        "member_exists": detail["member_exists"],
        "member": member,
        "profile": detail["profile"],
        "questionnaire": detail["questionnaire"],
        "current_pool": member["current_pool"],
        "current_stage": member["current_stage"],
        "current_target": member["current_target"],
        "manual_override_preferred": member["decision_source"] == DECISION_SOURCE_MANUAL,
        "recent_events": events,
    }


def sync_member_from_questionnaire_submission(*, external_contact_id: str = "", phone: str = "", operator_id: str = "system") -> dict[str, Any]:
    member = _resolve_existing_member(external_contact_id=external_contact_id, phone=phone)
    if not member:
        return {"updated": False, "reason": "member_not_found"}
    before = _serialize_member(member)
    saved = _touch_member_from_sources(
        member,
        action="questionnaire_update",
        operator_type="system",
        operator_id=_normalized_text(operator_id) or "questionnaire",
        persist_event=True,
    )
    after = _serialize_member(saved)
    return {"updated": before != after, "member": after}


def sync_member_activation(*, external_contact_id: str = "", phone: str = "", operator_id: str = "system") -> dict[str, Any]:
    member = _resolve_existing_member(external_contact_id=external_contact_id, phone=phone)
    if not member:
        return {"updated": False, "reason": "member_not_found"}
    before = _serialize_member(member)
    saved = _touch_member_from_sources(
        member,
        action="member_refresh",
        operator_type="system",
        operator_id=_normalized_text(operator_id) or "member_refresh",
        persist_event=True,
    )
    after = _serialize_member(saved)
    return {"updated": before != after, "member": after}


def _extract_channel_scene(payload_json: dict[str, Any]) -> str:
    payload = _json_loads(payload_json, default={})
    if not isinstance(payload, dict):
        payload = {}
    for key in ("state", "State", "scene", "scene_value", "channel_code"):
        value = _normalized_text(payload.get(key))
        if value:
            return value
    return ""


def _extract_welcome_code(payload_json: dict[str, Any]) -> str:
    payload = _json_loads(payload_json, default={})
    if not isinstance(payload, dict):
        payload = {}
    for key in ("welcome_code", "WelcomeCode", "welcomeCode"):
        value = _normalized_text(payload.get(key))
        if value:
            return value
    return ""


def _send_channel_welcome_message(
    *,
    member: dict[str, Any],
    channel: dict[str, Any],
    payload_json: dict[str, Any] | None = None,
    operator_id: str = "",
) -> dict[str, Any]:
    welcome_message = _normalized_text(channel.get("welcome_message"))
    welcome_code = _extract_welcome_code(payload_json or {})
    serialized_member = _serialize_member(member)
    if not welcome_message:
        return {"attempted": False, "sent": False, "reason": "not_configured"}
    if not welcome_code:
        _write_event(
            member_id=int(member["id"]),
            action="qrcode_welcome_failed",
            operator_type="system",
            operator_id=_normalized_text(operator_id) or "wecom_callback",
            before_snapshot=_member_snapshot(serialized_member),
            after_snapshot=_member_snapshot(serialized_member),
            remark="missing_welcome_code",
        )
        return {"attempted": True, "sent": False, "error": "missing_welcome_code"}

    request_payload = {
        "welcome_code": welcome_code,
        "text": {"content": welcome_message},
    }
    try:
        wecom_result = get_contact_runtime_client().send_welcome_msg(request_payload)
    except (WeComClientError, AttributeError, ValueError) as exc:
        _write_event(
            member_id=int(member["id"]),
            action="qrcode_welcome_failed",
            operator_type="system",
            operator_id=_normalized_text(operator_id) or "wecom_callback",
            before_snapshot=_member_snapshot(serialized_member),
            after_snapshot=_member_snapshot(serialized_member),
            remark=str(exc),
        )
        return {"attempted": True, "sent": False, "error": str(exc)}

    _write_event(
        member_id=int(member["id"]),
        action="qrcode_welcome_sent",
        operator_type="system",
        operator_id=_normalized_text(operator_id) or "wecom_callback",
        before_snapshot=_member_snapshot(serialized_member),
        after_snapshot=_member_snapshot(serialized_member),
        remark="official_send_welcome_msg",
    )
    return {
        "attempted": True,
        "sent": True,
        "welcome_code": welcome_code,
        "wecom_result": dict(wecom_result or {}),
    }


def _apply_channel_entry_tag(
    *,
    member: dict[str, Any],
    channel: dict[str, Any],
    operator_id: str = "",
) -> dict[str, Any]:
    entry_tag_id = _normalized_text(channel.get("entry_tag_id"))
    entry_tag_name = _normalized_text(channel.get("entry_tag_name"))
    entry_tag_group_name = _normalized_text(channel.get("entry_tag_group_name"))
    serialized_member = _serialize_member(member)
    external_contact_id = _normalized_text(serialized_member.get("external_contact_id"))
    owner_staff_id = _normalized_text(serialized_member.get("owner_staff_id"))
    if not entry_tag_id:
        return {"attempted": False, "applied": False, "reason": "not_configured"}
    if not external_contact_id:
        return {"attempted": False, "applied": False, "reason": "missing_external_contact_id"}
    if not owner_staff_id:
        return {"attempted": False, "applied": False, "reason": "missing_owner_staff_id"}
    try:
        wecom_result = get_app_runtime_client().mark_external_contact_tags(
            external_userid=external_contact_id,
            follow_user_userid=owner_staff_id,
            add_tags=[entry_tag_id],
            remove_tags=[],
        )
        tags_repo.save_tag_snapshot(owner_staff_id, external_contact_id, [entry_tag_id], {entry_tag_id: entry_tag_name})
    except (WeComClientError, AttributeError, ValueError) as exc:
        _write_event(
            member_id=int(member["id"]),
            action="qrcode_entry_tag_failed",
            operator_type="system",
            operator_id=_normalized_text(operator_id) or "wecom_callback",
            before_snapshot=_member_snapshot(serialized_member),
            after_snapshot=_member_snapshot(serialized_member),
            remark=str(exc),
        )
        return {
            "attempted": True,
            "applied": False,
            "error": str(exc),
            "entry_tag_id": entry_tag_id,
            "entry_tag_name": entry_tag_name,
            "entry_tag_group_name": entry_tag_group_name,
        }
    _write_event(
        member_id=int(member["id"]),
        action="qrcode_entry_tag_applied",
        operator_type="system",
        operator_id=_normalized_text(operator_id) or "wecom_callback",
        before_snapshot=_member_snapshot(serialized_member),
        after_snapshot=_member_snapshot(serialized_member),
        remark=entry_tag_name or entry_tag_id,
    )
    return {
        "attempted": True,
        "applied": True,
        "entry_tag_id": entry_tag_id,
        "entry_tag_name": entry_tag_name,
        "entry_tag_group_name": entry_tag_group_name,
        "wecom_result": dict(wecom_result or {}),
    }


def handle_qrcode_enter_from_callback(
    *,
    external_contact_id: str,
    phone: str = "",
    payload_json: dict[str, Any] | None = None,
    operator_id: str = "",
    send_welcome_message: bool = False,
) -> dict[str, Any]:
    channel_scene = _extract_channel_scene(payload_json or {})
    if not channel_scene:
        return {"handled": False, "reason": "missing_channel_scene"}
    channel = repo.find_channel_by_scene_value(channel_scene)
    if not channel:
        return {"handled": False, "reason": "channel_not_found"}
    member = _resolve_existing_member(external_contact_id=external_contact_id, phone=phone)
    context = _build_live_context(external_contact_id, phone)
    before = _serialize_member(member or _member_payload_from_context(None, {**context, "settings": get_signup_conversion_config()}, in_pool=False))
    current = _member_payload_from_context(
        member,
        {**context, "settings": get_signup_conversion_config()},
        source_type=SOURCE_TYPE_QRCODE,
        source_channel_id=int(channel["id"]),
        in_pool=True,
    )
    current["owner_staff_id"] = DEFAULT_OWNER_STAFF_ID
    current["joined_at"] = current.get("joined_at") or _iso_now()
    if before["current_pool"] == POOL_WON:
        saved = _persist_member(member, {**current, "in_pool": False, "current_pool": POOL_WON})
        _write_event(
            member_id=int(saved["id"]),
            action="qrcode_enter",
            operator_type="system",
            operator_id=_normalized_text(operator_id) or "wecom_callback",
            before_snapshot=_member_snapshot(before),
            after_snapshot=_member_snapshot(saved),
            remark="member already won; qrcode entry only recorded",
        )
        welcome_result = (
            _send_channel_welcome_message(
                member=saved,
                channel=channel,
                payload_json=payload_json,
                operator_id=operator_id,
            )
            if send_welcome_message
            else {"attempted": False, "sent": False, "reason": "disabled"}
        )
        entry_tag_result = _apply_channel_entry_tag(
            member=saved,
            channel=channel,
            operator_id=operator_id,
        )
        return {
            "handled": True,
            "member": _serialize_member(saved),
            "won_kept": True,
            "welcome_message": welcome_result,
            "entry_tag": entry_tag_result,
        }
    current["current_pool"] = recompute_pool(current, {**context, "settings": get_signup_conversion_config()}, action="qrcode_enter")
    saved = _persist_member(member, current)
    _write_event(
        member_id=int(saved["id"]),
        action="qrcode_enter",
        operator_type="system",
        operator_id=_normalized_text(operator_id) or "wecom_callback",
        before_snapshot=_member_snapshot(before),
        after_snapshot=_member_snapshot(saved),
    )
    welcome_result = (
        _send_channel_welcome_message(
            member=saved,
            channel=channel,
            payload_json=payload_json,
            operator_id=operator_id,
        )
        if send_welcome_message
        else {"attempted": False, "sent": False, "reason": "disabled"}
    )
    entry_tag_result = _apply_channel_entry_tag(
        member=saved,
        channel=channel,
        operator_id=operator_id,
    )
    return {
        "handled": True,
        "member": _serialize_member(saved),
        "welcome_message": welcome_result,
        "entry_tag": entry_tag_result,
    }
