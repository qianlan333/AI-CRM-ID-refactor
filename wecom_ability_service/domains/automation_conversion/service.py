from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from flask import current_app

from ...db import get_db
from ...infra.wecom_runtime import get_contact_runtime_client
from ...wecom_client import WeComClientError
from ..marketing_automation.service import get_customer_marketing_profile, get_signup_conversion_config, save_signup_conversion_config
from ..outbound_webhook.service import EVENT_OPENCLAW_FOCUS_MESSAGE, send_outbound_webhook
from ..questionnaire.service import get_questionnaire_detail, list_questionnaires
from ..tasks.service import dispatch_wecom_task
from ..user_ops import page_service as user_ops_page_service
from .message_activity_client import get_message_activity_db_status, query_message_activity_counts
from . import repo
from .provider import load_channel_provider

DEFAULT_OWNER_STAFF_ID = "QianLan"
DEFAULT_CHANNEL_CODE = "default_qrcode"
DEFAULT_CHANNEL_NAME = "默认渠道二维码"
AI_PUSH_SCENE_SIDEBAR_SCRIPT = "sidebar_script"
AI_PUSH_COOLDOWN_SECONDS = 30
FOCUS_SEND_INTERVAL_SECONDS = 20
MESSAGE_ACTIVITY_SYNC_SOURCE_MANUAL = "manual"
MESSAGE_ACTIVITY_SYNC_SOURCE_SCHEDULED = "scheduled"
ACTIVE_FOCUS_MESSAGE_THRESHOLD = 15
ACTIVE_MESSAGE_MIN_THRESHOLD = 2
CHANNEL_STATUS_NOT_GENERATED = "not_generated"
CHANNEL_STATUS_CONFIGURED = "configured"
CHANNEL_STATUS_ACTIVE = "active"

POOL_NEW_USER = "new_user"
POOL_INACTIVE_NORMAL = "inactive_normal"
POOL_INACTIVE_FOCUS = "inactive_focus"
POOL_ACTIVE_NORMAL = "active_normal"
POOL_ACTIVE_FOCUS = "active_focus"
POOL_SILENT = "silent"
POOL_WON = "won"
POOL_REMOVED = "removed"

FOLLOWUP_NORMAL = "normal"
FOLLOWUP_FOCUS = "focus"

QUESTIONNAIRE_PENDING = "pending"
QUESTIONNAIRE_SUBMITTED = "submitted"

QUESTIONNAIRE_RESULT_UNKNOWN = "unknown"
QUESTIONNAIRE_RESULT_NORMAL = "normal"
QUESTIONNAIRE_RESULT_FOCUS = "focus"

DECISION_SOURCE_QUESTIONNAIRE = "questionnaire"
DECISION_SOURCE_MANUAL = "manual"
DECISION_SOURCE_SYSTEM = "system"

ACTIVATION_UNKNOWN = "unknown"
ACTIVATION_INACTIVE = "inactive"
ACTIVATION_ACTIVE = "active"

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
    "qrcode_welcome_sent": "扫码欢迎语已发送",
    "qrcode_welcome_failed": "扫码欢迎语发送失败",
}

POOL_LABELS = {
    POOL_NEW_USER: "新用户池",
    POOL_INACTIVE_NORMAL: "未激活普通池",
    POOL_INACTIVE_FOCUS: "未激活重点跟进池",
    POOL_ACTIVE_NORMAL: "激活普通池",
    POOL_ACTIVE_FOCUS: "激活重点跟进池",
    POOL_SILENT: "沉默池",
    POOL_WON: "已成交",
    POOL_REMOVED: "已移出",
}

MANUAL_SEND_ALLOWED_POOLS = {
    POOL_NEW_USER,
    POOL_INACTIVE_NORMAL,
    POOL_ACTIVE_NORMAL,
    POOL_SILENT,
    POOL_WON,
}

STAGE_BY_POOL = {
    POOL_NEW_USER: "new_user_wait_questionnaire",
    POOL_INACTIVE_NORMAL: "inactive_normal_followup",
    POOL_INACTIVE_FOCUS: "inactive_focus_followup",
    POOL_ACTIVE_NORMAL: "active_normal_followup",
    POOL_ACTIVE_FOCUS: "active_focus_followup",
    POOL_SILENT: "silent_waiting",
    POOL_WON: "won",
    POOL_REMOVED: "removed",
}

TARGET_BY_POOL = {
    POOL_NEW_USER: "submit_questionnaire",
    POOL_INACTIVE_NORMAL: "activate",
    POOL_INACTIVE_FOCUS: "focus_activate",
    POOL_ACTIVE_NORMAL: "normal_followup",
    POOL_ACTIVE_FOCUS: "focus_followup",
    POOL_SILENT: "revive",
    POOL_WON: "post_deal",
    POOL_REMOVED: "none",
}

STAGE_LABELS = {
    "new_user_wait_questionnaire": "等待提交问卷",
    "inactive_normal_followup": "未激活普通跟进",
    "inactive_focus_followup": "未激活重点跟进",
    "active_normal_followup": "已激活普通跟进",
    "active_focus_followup": "已激活重点跟进",
    "silent_waiting": "沉默等待",
    "won": "已成交",
    "removed": "已移出",
}

TARGET_LABELS = {
    "submit_questionnaire": "推动提交问卷",
    "activate": "促活",
    "focus_activate": "重点促活",
    "normal_followup": "普通跟进",
    "focus_followup": "重点跟进",
    "revive": "唤醒",
    "post_deal": "成交后维护",
    "none": "无",
}

STAGE_DEFINITIONS = (
    {"pool": POOL_NEW_USER, "route_key": "new-user", "label": "新用户池", "description": "已入池但还没完成问卷的客户。"},
    {"pool": POOL_INACTIVE_NORMAL, "route_key": "inactive-normal", "label": "未激活普通池", "description": "问卷已提交，当前按普通跟进推进。"},
    {"pool": POOL_INACTIVE_FOCUS, "route_key": "inactive-focus", "label": "未激活重点跟进池", "description": "问卷已提交，当前按重点跟进推进。"},
    {"pool": POOL_ACTIVE_NORMAL, "route_key": "active-normal", "label": "激活普通池", "description": "已激活，当前按普通跟进推进。"},
    {"pool": POOL_ACTIVE_FOCUS, "route_key": "active-focus", "label": "激活重点跟进池", "description": "已激活，当前按重点跟进推进。"},
    {"pool": POOL_SILENT, "route_key": "silent", "label": "沉默池", "description": "达到沉默阈值后进入沉默池。"},
    {"pool": POOL_WON, "route_key": "won", "label": "已成交", "description": "人工确认成交后进入成交池。"},
)

ROUTE_KEY_TO_POOL = {item["route_key"]: item["pool"] for item in STAGE_DEFINITIONS}
POOL_TO_STAGE_DEF = {item["pool"]: item for item in STAGE_DEFINITIONS}
MESSAGE_ACTIVITY_SYNC_POOLS = (
    POOL_INACTIVE_NORMAL,
    POOL_INACTIVE_FOCUS,
    POOL_ACTIVE_NORMAL,
    POOL_ACTIVE_FOCUS,
)
FOCUS_SEND_ALLOWED_POOLS = {
    POOL_INACTIVE_FOCUS,
    POOL_ACTIVE_FOCUS,
}
SOP_V1_ALLOWED_POOLS = (
    POOL_NEW_USER,
    POOL_INACTIVE_NORMAL,
    POOL_ACTIVE_NORMAL,
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
    return POOL_LABELS.get(_normalized_text(pool), _normalized_text(pool) or "未设置")


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
    return {definition["route_key"] for definition in STAGE_DEFINITIONS if definition["pool"] in MANUAL_SEND_ALLOWED_POOLS}


def _manual_send_stage_definition(route_key: str) -> dict[str, Any]:
    normalized_route_key = _normalized_text(route_key)
    pool = ROUTE_KEY_TO_POOL.get(normalized_route_key)
    if not pool:
        raise ValueError("invalid stage")
    if pool not in MANUAL_SEND_ALLOWED_POOLS:
        raise ValueError("focus stage must use focus send batches")
    return dict(POOL_TO_STAGE_DEF.get(pool) or {})


def _focus_send_stage_definition(route_key: str) -> dict[str, Any]:
    normalized_route_key = _normalized_text(route_key)
    pool = ROUTE_KEY_TO_POOL.get(normalized_route_key)
    if not pool:
        raise ValueError("invalid stage")
    if pool not in FOCUS_SEND_ALLOWED_POOLS:
        raise ValueError("stage does not support focus send batches")
    return dict(POOL_TO_STAGE_DEF.get(pool) or {})


def _normalize_manual_send_image_media_ids(image_media_ids: list[str] | None = None) -> list[str]:
    normalized_image_media_ids: list[str] = []
    for media_id in list(image_media_ids or []):
        normalized_media_id = _normalized_text(media_id)
        if normalized_media_id:
            normalized_image_media_ids.append(normalized_media_id)
    return normalized_image_media_ids


def _validate_sop_pool_key(pool_key: str) -> str:
    normalized_pool_key = _normalized_text(pool_key)
    if normalized_pool_key not in SOP_V1_ALLOWED_POOLS:
        raise ValueError("sop pool_key must be one of new_user, inactive_normal, active_normal")
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


def save_sop_v1_pool_config(*, pool_key: str, enabled: Any, send_time: Any) -> dict[str, Any]:
    normalized_pool_key = _validate_sop_pool_key(pool_key)
    _ensure_sop_template_day_exists(normalized_pool_key, 1)
    existing = _serialize_sop_pool_config(repo.get_sop_pool_config(normalized_pool_key))
    normalized_enabled = _normalize_bool(enabled)
    effective_start_at = _normalized_text(existing.get("effective_start_at")) if existing else ""
    if not effective_start_at or (existing and not _normalize_bool(existing.get("enabled")) and normalized_enabled):
        effective_start_at = _iso_now()
    template_count = max(_current_sop_template_day_count(normalized_pool_key), 1)
    saved = repo.save_sop_pool_config(
        {
            "pool_key": normalized_pool_key,
            "enabled": normalized_enabled,
            "max_day_count": template_count,
            "send_time": _normalize_sop_send_time(send_time),
            "timezone": SOP_V1_DEFAULT_TIMEZONE,
            "effective_start_at": effective_start_at,
        }
    )
    get_db().commit()
    return {
        "config": _serialize_sop_pool_config(saved),
        "templates": [_serialize_sop_template_for_ui(_serialize_sop_template(row)) for row in repo.list_sop_templates(pool_key=normalized_pool_key)],
        "template_count": template_count,
    }


def append_sop_v1_template_day(*, pool_key: str) -> dict[str, Any]:
    normalized_pool_key = _validate_sop_pool_key(pool_key)
    next_day_index = max(_current_sop_template_day_count(normalized_pool_key), 0) + 1
    repo.save_sop_template(_empty_sop_template(normalized_pool_key, next_day_index))
    existing_config = _serialize_sop_pool_config(repo.get_sop_pool_config(normalized_pool_key))
    repo.save_sop_pool_config(
        {
            "pool_key": normalized_pool_key,
            "enabled": _normalize_bool(existing_config.get("enabled")) if existing_config else True,
            "max_day_count": next_day_index,
            "send_time": _normalize_sop_send_time(existing_config.get("send_time") if existing_config else _default_sop_send_time()),
            "timezone": SOP_V1_DEFAULT_TIMEZONE,
            "effective_start_at": _normalized_text(existing_config.get("effective_start_at")) or _iso_now(),
        }
    )
    get_db().commit()
    return get_sop_v1_templates_payload(normalized_pool_key, selected_day_index=next_day_index)


def delete_sop_v1_template_day(*, pool_key: str, day_index: Any) -> dict[str, Any]:
    normalized_pool_key = _validate_sop_pool_key(pool_key)
    normalized_day_index = int(day_index or 0)
    if normalized_day_index < 1:
        raise ValueError("sop day_index must be >= 1")
    current_count = max(_current_sop_template_day_count(normalized_pool_key), 0)
    if current_count <= 1:
        raise ValueError("at least one sop day must remain")
    if not repo.get_sop_template(pool_key=normalized_pool_key, day_index=normalized_day_index):
        raise LookupError("sop template day not found")
    repo.delete_sop_template_day(pool_key=normalized_pool_key, day_index=normalized_day_index)
    new_count = max(_current_sop_template_day_count(normalized_pool_key), 1)
    existing_config = _serialize_sop_pool_config(repo.get_sop_pool_config(normalized_pool_key))
    repo.save_sop_pool_config(
        {
            "pool_key": normalized_pool_key,
            "enabled": _normalize_bool(existing_config.get("enabled")) if existing_config else True,
            "max_day_count": new_count,
            "send_time": _normalize_sop_send_time(existing_config.get("send_time") if existing_config else _default_sop_send_time()),
            "timezone": SOP_V1_DEFAULT_TIMEZONE,
            "effective_start_at": _normalized_text(existing_config.get("effective_start_at")) or _iso_now(),
        }
    )
    get_db().commit()
    return get_sop_v1_templates_payload(normalized_pool_key, selected_day_index=min(normalized_day_index, new_count))


def save_sop_v1_template(*, pool_key: str, day_index: Any, content: Any, images_json: list[dict[str, Any]] | None, enabled: Any) -> dict[str, Any]:
    normalized_pool_key = _validate_sop_pool_key(pool_key)
    normalized_day_index = int(day_index or 0)
    if normalized_day_index < 1:
        raise ValueError("sop day_index must be >= 1")
    saved = repo.save_sop_template(
        {
            "pool_key": normalized_pool_key,
            "day_index": normalized_day_index,
            "content": _normalized_text(content),
            "images_json": list(images_json or []),
            "enabled": _normalize_bool(enabled),
        }
    )
    existing_config = _serialize_sop_pool_config(repo.get_sop_pool_config(normalized_pool_key))
    repo.save_sop_pool_config(
        {
            "pool_key": normalized_pool_key,
            "enabled": _normalize_bool(existing_config.get("enabled")) if existing_config else True,
            "max_day_count": max(_current_sop_template_day_count(normalized_pool_key), normalized_day_index),
            "send_time": _normalize_sop_send_time(existing_config.get("send_time") if existing_config else _default_sop_send_time()),
            "timezone": SOP_V1_DEFAULT_TIMEZONE,
            "effective_start_at": _normalized_text(existing_config.get("effective_start_at")) or _iso_now(),
        }
    )
    get_db().commit()
    return _serialize_sop_template_for_ui(_serialize_sop_template(saved))


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
        "subtitle": "只覆盖新用户池、未激活普通池、激活普通池",
        "selected_pool_key": normalized_pool_key,
        "pool_cards": pool_cards,
        "current_pool": current_pool,
    }


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
    effective_dt = _parse_timestamp(_sop_effective_start_at(pool_config)) or entry_dt
    first_effective_dt = effective_dt if effective_dt > entry_dt else entry_dt
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
            entry_time=_later_timestamp_text(entry_time, _sop_effective_start_at(normalized_pool_config)) or entry_time,
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
    return STAGE_BY_POOL.get(_normalized_text(pool), "removed")


def _stage_label(stage: str) -> str:
    return STAGE_LABELS.get(_normalized_text(stage), _normalized_text(stage) or "未设置")


def _target_from_pool(pool: str) -> str:
    return TARGET_BY_POOL.get(_normalized_text(pool), "none")


def _target_label(target: str) -> str:
    return TARGET_LABELS.get(_normalized_text(target), _normalized_text(target) or "无")


def _follow_type_label(value: str) -> str:
    normalized = _normalized_text(value)
    return {"normal": "普通跟进", "focus": "重点跟进"}.get(normalized, "未定")


def _questionnaire_result_label(value: str) -> str:
    normalized = _normalized_text(value)
    return {
        QUESTIONNAIRE_RESULT_UNKNOWN: "未知",
        QUESTIONNAIRE_RESULT_NORMAL: "普通跟进",
        QUESTIONNAIRE_RESULT_FOCUS: "重点跟进",
    }.get(normalized, "未知")


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


def _activation_status_label(value: str) -> str:
    normalized = _normalized_text(value)
    return {
        ACTIVATION_UNKNOWN: "未知",
        ACTIVATION_INACTIVE: "未激活",
        ACTIVATION_ACTIVE: "已激活",
    }.get(normalized, "未知")


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
        "follow_type": _normalized_text(member.get("follow_type")),
        "activation_status": _normalized_text(member.get("activation_status")) or ACTIVATION_UNKNOWN,
        "questionnaire_status": _normalized_text(member.get("questionnaire_status")) or QUESTIONNAIRE_PENDING,
        "questionnaire_result": _normalized_text(member.get("questionnaire_result")) or QUESTIONNAIRE_RESULT_UNKNOWN,
        "decision_source": _normalized_text(member.get("decision_source")) or DECISION_SOURCE_SYSTEM,
        "source_type": _normalized_text(member.get("source_type")) or SOURCE_TYPE_SYSTEM,
        "source_channel_id": member.get("source_channel_id"),
        "last_active_pool": _normalized_text(member.get("last_active_pool")),
        "joined_at": _normalized_text(member.get("joined_at")),
        "last_ai_push_at": _normalized_text(member.get("last_ai_push_at")),
        "ai_cooldown_until": _normalized_text(member.get("ai_cooldown_until")),
        "created_at": _normalized_text(member.get("created_at")),
        "updated_at": _normalized_text(member.get("updated_at")),
    }
    serialized["current_stage"] = _stage_from_pool(serialized["current_pool"])
    serialized["current_stage_label"] = _stage_label(serialized["current_stage"])
    serialized["current_target"] = _target_from_pool(serialized["current_pool"])
    serialized["current_target_label"] = _target_label(serialized["current_target"])
    serialized["current_pool_label"] = _pool_label(serialized["current_pool"])
    serialized["follow_type_label"] = _follow_type_label(serialized["follow_type"])
    serialized["activation_status_label"] = _activation_status_label(serialized["activation_status"])
    serialized["questionnaire_status_label"] = _questionnaire_status_label(serialized["questionnaire_status"])
    serialized["questionnaire_result_label"] = _questionnaire_result_label(serialized["questionnaire_result"])
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
        "activation_status": serialized["activation_status"],
        "questionnaire_status": serialized["questionnaire_status"],
        "questionnaire_result": serialized["questionnaire_result"],
        "decision_source": serialized["decision_source"],
        "source_type": serialized["source_type"],
        "source_channel_id": serialized["source_channel_id"],
        "last_active_pool": serialized["last_active_pool"],
        "joined_at": serialized["joined_at"],
        "last_ai_push_at": serialized["last_ai_push_at"],
        "ai_cooldown_until": serialized["ai_cooldown_until"],
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


def _activation_status_from_live(external_contact_id: str) -> dict[str, Any]:
    normalized_external_contact_id = _normalized_text(external_contact_id)
    if not normalized_external_contact_id:
        return {"activation_status": ACTIVATION_UNKNOWN, "last_activation_at": ""}
    try:
        marketing_profile = get_customer_marketing_profile(normalized_external_contact_id)
    except Exception:
        return {"activation_status": ACTIVATION_UNKNOWN, "last_activation_at": ""}
    marketing_state = dict((marketing_profile or {}).get("marketing_state") or {})
    activated = bool(marketing_state.get("activated")) or bool(_normalized_text(marketing_state.get("last_activation_at")))
    return {
        "activation_status": ACTIVATION_ACTIVE if activated else ACTIVATION_INACTIVE,
        "last_activation_at": _normalized_text(marketing_state.get("last_activation_at")),
    }


def _latest_questionnaire_context(external_contact_ids: list[str], phone: str) -> dict[str, Any]:
    settings = get_signup_conversion_config()
    questionnaire_id = settings.get("questionnaire_id")
    if not questionnaire_id:
        return {
            "questionnaire_status": QUESTIONNAIRE_PENDING,
            "questionnaire_result": QUESTIONNAIRE_RESULT_UNKNOWN,
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
        return {
            "questionnaire_status": QUESTIONNAIRE_PENDING,
            "questionnaire_result": QUESTIONNAIRE_RESULT_UNKNOWN,
            "hit_count": 0,
            "matched_question_ids": [],
            "matched_questions": [],
            "answers": [],
            "submitted_at": "",
            "questionnaire_id": int(questionnaire_id),
        }
    answer_rows = repo.list_questionnaire_submission_answers(int(submission["id"]))
    answers = [
        {
            "question": _normalized_text(row.get("question_title_snapshot")) or f"问题 {int(row.get('question_id') or 0)}",
            "answer": _question_answer_text(row),
        }
        for row in answer_rows
    ]
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
    hit_count = len(matched_question_ids)
    questionnaire_result = QUESTIONNAIRE_RESULT_FOCUS if hit_count >= int(settings.get("core_threshold") or 0) else QUESTIONNAIRE_RESULT_NORMAL
    return {
        "questionnaire_status": QUESTIONNAIRE_SUBMITTED,
        "questionnaire_result": questionnaire_result,
        "hit_count": hit_count,
        "matched_question_ids": matched_question_ids,
        "matched_questions": matched_questions,
        "answers": answers,
        "submitted_at": _normalized_text(submission.get("submitted_at")),
        "questionnaire_id": int(questionnaire_id),
        "submission_id": int(submission["id"]),
    }


def _build_live_context(external_contact_id: str = "", phone: str = "") -> dict[str, Any]:
    lookup = _resolve_lookup(external_contact_id=external_contact_id, phone=phone)
    profile = _load_profile(lookup["external_contact_id"], lookup["phone"])
    resolved_external_contact_id = _normalized_text(profile.get("external_contact_id")) or lookup["external_contact_id"]
    resolved_phone = _normalized_text(profile.get("phone")) or lookup["phone"]
    external_contact_ids = list(dict.fromkeys([item for item in lookup["external_contact_ids"] + [resolved_external_contact_id] if _normalized_text(item)]))
    activation = _activation_status_from_live(resolved_external_contact_id)
    questionnaire = _latest_questionnaire_context(external_contact_ids, resolved_phone)
    return {
        "lookup": {**lookup, "external_contact_ids": external_contact_ids},
        "profile": profile,
        "activation": activation,
        "questionnaire": questionnaire,
    }


def _silent_threshold_days(pool_key: str, settings: dict[str, Any]) -> int:
    thresholds = dict(settings.get("silent_threshold_days_by_pool") or {})
    try:
        return int(thresholds.get(pool_key) or 7)
    except (TypeError, ValueError):
        return 7


def _should_be_silent(member: dict[str, Any], settings: dict[str, Any]) -> bool:
    current_pool = _normalized_text(member.get("current_pool"))
    if current_pool not in {POOL_NEW_USER, POOL_INACTIVE_NORMAL, POOL_INACTIVE_FOCUS, POOL_ACTIVE_NORMAL, POOL_ACTIVE_FOCUS}:
        return False
    base_timestamp = _parse_timestamp(member.get("updated_at")) or _parse_timestamp(member.get("joined_at"))
    if base_timestamp is None:
        return False
    return datetime.now() >= (base_timestamp + timedelta(days=_silent_threshold_days(current_pool, settings)))


def recompute_pool(member: dict[str, Any], context: dict[str, Any], *, action: str = "") -> str:
    current_pool = _normalized_text(member.get("current_pool"))
    if current_pool == POOL_WON and action != "unmark_won":
        return POOL_WON
    if not _normalize_bool(member.get("in_pool")):
        return POOL_REMOVED
    if current_pool == POOL_SILENT and action not in {"put_in_pool", "unmark_won"}:
        return POOL_SILENT
    questionnaire_status = _normalized_text(member.get("questionnaire_status")) or QUESTIONNAIRE_PENDING
    if questionnaire_status != QUESTIONNAIRE_SUBMITTED:
        next_pool = POOL_NEW_USER
    else:
        if _normalized_text(member.get("decision_source")) == DECISION_SOURCE_MANUAL and _normalized_text(member.get("follow_type")) in {FOLLOWUP_NORMAL, FOLLOWUP_FOCUS}:
            follow_type = _normalized_text(member.get("follow_type"))
        else:
            follow_type = _normalized_text(member.get("questionnaire_result"))
            if follow_type not in {FOLLOWUP_NORMAL, FOLLOWUP_FOCUS}:
                follow_type = FOLLOWUP_NORMAL
        activation_status = _normalized_text(member.get("activation_status")) or ACTIVATION_UNKNOWN
        if activation_status == ACTIVATION_ACTIVE:
            next_pool = POOL_ACTIVE_FOCUS if follow_type == FOLLOWUP_FOCUS else POOL_ACTIVE_NORMAL
        else:
            next_pool = POOL_INACTIVE_FOCUS if follow_type == FOLLOWUP_FOCUS else POOL_INACTIVE_NORMAL
    settings = context.get("settings") or get_signup_conversion_config()
    temp_member = {**member, "current_pool": next_pool}
    if _should_be_silent(temp_member, settings):
        return POOL_SILENT
    return next_pool


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
    activation = context["activation"]
    questionnaire = context["questionnaire"]
    lookup = context["lookup"]
    base_payload = {
        "external_contact_id": _normalized_text(profile.get("external_contact_id")) or existing_row.get("external_contact_id") or lookup.get("external_contact_id"),
        "phone": _normalized_text(profile.get("phone")) or existing_row.get("phone") or lookup.get("phone"),
        "master_customer_id": lookup.get("master_customer_id") or existing_row.get("master_customer_id"),
        "owner_staff_id": _normalized_text(existing_row.get("owner_staff_id")) or _normalized_text(profile.get("owner_staff_id")) or DEFAULT_OWNER_STAFF_ID,
        "in_pool": existing_row.get("in_pool") if in_pool is None else bool(in_pool),
        "current_pool": existing_row.get("current_pool") or POOL_REMOVED,
        "follow_type": _normalized_text(existing_row.get("follow_type")),
        "activation_status": _normalized_text(activation.get("activation_status")) or existing_row.get("activation_status") or ACTIVATION_UNKNOWN,
        "questionnaire_status": _normalized_text(questionnaire.get("questionnaire_status")) or existing_row.get("questionnaire_status") or QUESTIONNAIRE_PENDING,
        "questionnaire_result": _normalized_text(questionnaire.get("questionnaire_result")) or existing_row.get("questionnaire_result") or QUESTIONNAIRE_RESULT_UNKNOWN,
        "decision_source": _normalized_text(existing_row.get("decision_source")) or (
            DECISION_SOURCE_QUESTIONNAIRE if questionnaire.get("questionnaire_status") == QUESTIONNAIRE_SUBMITTED else DECISION_SOURCE_SYSTEM
        ),
        "source_type": _normalized_text(source_type) or existing_row.get("source_type") or SOURCE_TYPE_SYSTEM,
        "source_channel_id": source_channel_id if source_channel_id is not None else existing_row.get("source_channel_id"),
        "last_active_pool": _normalized_text(existing_row.get("last_active_pool")),
        "joined_at": _normalized_text(existing_row.get("joined_at")),
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
        "activation_status",
        "questionnaire_status",
        "questionnaire_result",
        "decision_source",
        "source_type",
        "source_channel_id",
        "last_active_pool",
        "joined_at",
        "last_ai_push_at",
        "ai_cooldown_until",
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


def _persist_member(member: dict[str, Any] | None, payload: dict[str, Any]) -> dict[str, Any]:
    db = get_db()
    try:
        before = _serialize_member(member or {})
        if member and member.get("id"):
            saved = repo.update_member(int(member["id"]), payload)
        else:
            saved = repo.insert_member(payload)
        _sync_sop_progress_for_transition(before, _serialize_member(saved))
        db.commit()
        return saved
    except Exception:
        db.rollback()
        raise


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
    settings = get_signup_conversion_config()
    refreshed = 0
    for row in repo.list_members_for_silent_refresh():
        serialized = _serialize_member(row)
        if not _should_be_silent(serialized, settings):
            continue
        next_payload = {
            **serialized,
            "current_pool": POOL_SILENT,
        }
        saved = _persist_member(serialized, next_payload)
        _write_event(
            member_id=int(saved["id"]),
            action="system_silent_refresh",
            operator_type="system",
            operator_id="system",
            before_snapshot=_member_snapshot(serialized),
            after_snapshot=_member_snapshot(saved),
            remark="silent threshold reached",
        )
        refreshed += 1
    return {"refreshed_count": refreshed}


def _message_activity_pool(*, activation_status: str, follow_type: str) -> str:
    normalized_follow_type = _normalized_text(follow_type)
    if normalized_follow_type not in {FOLLOWUP_NORMAL, FOLLOWUP_FOCUS}:
        normalized_follow_type = FOLLOWUP_NORMAL
    normalized_activation_status = _normalized_text(activation_status)
    if normalized_activation_status == ACTIVATION_ACTIVE:
        return POOL_ACTIVE_FOCUS if normalized_follow_type == FOLLOWUP_FOCUS else POOL_ACTIVE_NORMAL
    return POOL_INACTIVE_FOCUS if normalized_follow_type == FOLLOWUP_FOCUS else POOL_INACTIVE_NORMAL


def _inactive_follow_type_from_member(before: dict[str, Any]) -> tuple[str, str, bool]:
    manual_preserved = (
        _normalized_text(before.get("decision_source")) == DECISION_SOURCE_MANUAL
        and _normalized_text(before.get("follow_type")) in {FOLLOWUP_NORMAL, FOLLOWUP_FOCUS}
    )
    if manual_preserved:
        return _normalized_text(before.get("follow_type")), _normalized_text(before.get("decision_source")) or DECISION_SOURCE_MANUAL, True
    questionnaire_follow_type = _normalized_text(before.get("questionnaire_result"))
    if questionnaire_follow_type not in {FOLLOWUP_NORMAL, FOLLOWUP_FOCUS}:
        questionnaire_follow_type = FOLLOWUP_NORMAL
    return questionnaire_follow_type, DECISION_SOURCE_SYSTEM, False


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


def _channel_status_is_generated(status: str) -> bool:
    return _normalized_text(status) == CHANNEL_STATUS_ACTIVE


def _default_channel_field_statuses(
    *,
    provider: Any,
    channel_status: str,
    welcome_message: str,
    auto_accept_friend: bool,
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
        eligible_members = [_serialize_member(row) for row in repo.list_members_for_message_activity_sync(current_pools=list(current_pools))]
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
                    for item in ambiguous_groups[match_key]
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
                next_activation_status = ACTIVATION_ACTIVE
                next_follow_type = FOLLOWUP_FOCUS
                next_decision_source = DECISION_SOURCE_SYSTEM
                bucket_label = "active_focus_threshold"
                manual_preserved = False
            elif message_count >= ACTIVE_MESSAGE_MIN_THRESHOLD:
                next_activation_status = ACTIVATION_ACTIVE
                next_follow_type = FOLLOWUP_NORMAL
                next_decision_source = DECISION_SOURCE_SYSTEM
                bucket_label = "active_normal_threshold"
                manual_preserved = False
            else:
                next_activation_status = ACTIVATION_INACTIVE
                next_follow_type, next_decision_source, manual_preserved = _inactive_follow_type_from_member(before)
                bucket_label = "inactive_questionnaire_or_manual"
            if next_follow_type == FOLLOWUP_FOCUS:
                counters["focus_count"] += 1
            else:
                counters["normal_count"] += 1
            next_payload = {
                **before,
                "activation_status": next_activation_status,
                "follow_type": next_follow_type,
                "decision_source": next_decision_source,
                "current_pool": _message_activity_pool(
                    activation_status=next_activation_status,
                    follow_type=next_follow_type,
                ),
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
            "owner_staff_id": _normalized_text(channel.get("owner_staff_id")) or DEFAULT_OWNER_STAFF_ID,
            "status": _normalized_text(channel.get("status")) or CHANNEL_STATUS_NOT_GENERATED,
            "field_statuses": _default_channel_field_statuses(
                provider=provider,
                channel_status=_normalized_text(channel.get("status")) or CHANNEL_STATUS_NOT_GENERATED,
                welcome_message=_normalized_text(channel.get("welcome_message")),
                auto_accept_friend=_normalize_bool(channel.get("auto_accept_friend")),
            ),
        },
        "default_owner_staff_id": DEFAULT_OWNER_STAFF_ID,
        "provider_available": provider is not None,
        "message_activity_sync": _message_activity_sync_status_payload(),
    }


def save_settings(payload: dict[str, Any]) -> dict[str, Any]:
    config_payload = {
        "enabled": _normalize_bool(payload.get("enabled", True)),
        "questionnaire_id": payload.get("questionnaire_id"),
        "core_threshold": payload.get("core_threshold"),
        "top_threshold": payload.get("top_threshold", payload.get("core_threshold")),
        "day_start_hour": payload.get("day_start_hour"),
        "quiet_hour_start": payload.get("quiet_hour_start"),
        "timezone": payload.get("timezone"),
        "silent_threshold_days_by_pool": payload.get("silent_threshold_days_by_pool"),
        "question_rules": payload.get("question_rules"),
    }
    save_signup_conversion_config(config_payload, enforce_required_mobile_question=True)
    existing = repo.get_default_channel() or {}
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
            "owner_staff_id": DEFAULT_OWNER_STAFF_ID,
            "status": (
                CHANNEL_STATUS_CONFIGURED
                if channel_settings_changed
                else (_normalized_text(payload.get("channel_status")) or _normalized_text(existing.get("status")) or CHANNEL_STATUS_CONFIGURED)
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
    questionnaire = context["questionnaire"]
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
            "status": questionnaire.get("questionnaire_status") or serialized_member["questionnaire_status"],
            "status_label": _questionnaire_status_label(questionnaire.get("questionnaire_status") or serialized_member["questionnaire_status"]),
            "result": questionnaire.get("questionnaire_result") or serialized_member["questionnaire_result"],
            "result_label": _questionnaire_result_label(questionnaire.get("questionnaire_result") or serialized_member["questionnaire_result"]),
            "hit_count": int(questionnaire.get("hit_count") or 0),
            "matched_questions": questionnaire.get("matched_questions") or [],
            "submitted_at": _normalized_text(questionnaire.get("submitted_at")),
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
    current_pool = _normalized_text(member.get("current_pool"))
    in_pool = bool(member.get("in_pool"))
    won = current_pool == POOL_WON
    ai_enabled = current_pool != POOL_REMOVED
    states = {
        "put_in_pool": {"enabled": (not in_pool) and (not won)},
        "remove_from_pool": {"enabled": in_pool and not won},
        "set_focus": {"enabled": in_pool and not won},
        "set_normal": {"enabled": in_pool and not won},
        "mark_won": {"enabled": in_pool and not won},
        "unmark_won": {"enabled": won},
        "push_openclaw": {"enabled": ai_enabled},
        "ai_push": {"enabled": ai_enabled},
    }
    return states


def _mutate_member(
    *,
    external_contact_id: str = "",
    phone: str = "",
    action: str,
    operator_id: str,
    operator_type: str = "user",
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
        "detail": get_member_detail(external_contact_id=after["external_contact_id"], phone=after["phone"]),
    }


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
        current["in_pool"] = False
        current["current_pool"] = POOL_WON
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
    config = get_signup_conversion_config()
    cards = [
        {"key": "in_pool_total", "label": "在池总人数", "value": counts["in_pool_total"], "description": "当前仍在自动化池里的成员数量。"},
        {"key": "today_joined", "label": "今日入池", "value": counts["today_joined"], "description": "今天新进入自动化池的成员数量。"},
        {"key": "questionnaire_pending", "label": "待问卷", "value": counts["questionnaire_pending"], "description": "已入池但还没提交问卷。"},
        {"key": "normal_followup", "label": "普通跟进", "value": counts["normal_followup"], "description": "当前普通跟进成员数量。"},
        {"key": "focus_followup", "label": "重点跟进", "value": counts["focus_followup"], "description": "当前重点跟进成员数量。"},
        {"key": "silent_total", "label": "沉默池", "value": counts["silent_total"], "description": "达到沉默阈值后进入沉默池。"},
        {"key": "won_total", "label": "已成交", "value": counts["won_total"], "description": "确认已成交的成员数量。"},
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
    request_payload = {
        "sender": DEFAULT_OWNER_STAFF_ID,
        "external_userid": [_normalized_text(item.get("external_userid")) for item in target_items if _normalized_text(item.get("external_userid"))],
        **task_payload,
    }
    try:
        wecom_result = dispatch_wecom_task("private_message", "create_private_message_task", request_payload)
        outbound_task_ids.append(int(wecom_result["task_id"]))
        task_results.append(user_ops_page_service._build_sender_success_result(DEFAULT_OWNER_STAFF_ID, target_items, wecom_result))
    except (WeComClientError, AttributeError) as exc:
        task_results.append(user_ops_page_service._build_sender_failure_result(DEFAULT_OWNER_STAFF_ID, target_items, exc))

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
        "error": (
            _normalized_text(task_results[0].get("error_message"))
            if status == "failed" and task_results
            else ""
        ),
    }


def send_stage_manual_message(
    *,
    route_key: str,
    content: str = "",
    image_media_ids: list[str] | None = None,
    images: list[dict[str, Any]] | None = None,
    operator_id: str = "",
) -> dict[str, Any]:
    refresh_expired_silent_members()
    definition, pool, sendable_items, total_target_count, skipped_reasons = _build_stage_manual_send_plan(route_key)
    normalized_operator_id = _normalized_text(operator_id) or "crm_console"
    normalized_content = _normalized_text(content)
    normalized_image_media_ids = _normalize_manual_send_image_media_ids(image_media_ids)
    task_payload, content_preview, image_count = user_ops_page_service._build_private_message_payload(
        {
            "content": normalized_content,
            "image_media_ids": normalized_image_media_ids,
            "images": list(images or []),
        }
    )
    skipped_count = sum(int(value or 0) for value in skipped_reasons.values())
    result = {
        "ok": True,
        "stage_key": _normalized_text(definition.get("route_key")),
        "stage_label": _normalized_text(definition.get("label")),
        "pool_key": pool,
        "pool_label": _pool_label(pool),
        "sender_userid": DEFAULT_OWNER_STAFF_ID,
        "total_target_count": total_target_count,
        "sendable_count": len(sendable_items),
        "sent_count": 0,
        "skipped_count": skipped_count,
        "skipped_reasons": skipped_reasons,
        "record_id": None,
        "task_ids": [],
        "status": "empty",
        "content_preview": content_preview,
        "image_count": image_count,
        "error": "",
    }
    if not total_target_count:
        result["empty_reason"] = "no_customers_in_stage"
        return result
    if not sendable_items:
        result["empty_reason"] = "no_sendable_customers_in_stage"
        return result
    dispatch_result = _dispatch_private_message_batch(
        target_items=sendable_items,
        content=normalized_content,
        image_media_ids=normalized_image_media_ids,
        images=list(images or []),
        operator_id=normalized_operator_id,
        filter_snapshot={
            "selection_mode": "automation_conversion_stage",
            "stage_key": _normalized_text(definition.get("route_key")),
            "stage_label": _normalized_text(definition.get("label")),
            "pool_key": pool,
            "pool_label": _pool_label(pool),
        },
    )
    result.update(
        {
            "ok": bool(dispatch_result.get("ok")),
            "sent_count": int(dispatch_result.get("sent_count") or 0),
            "record_id": int(dispatch_result.get("record_id") or 0),
            "task_ids": list(dispatch_result.get("task_ids") or []),
            "status": _normalized_text(dispatch_result.get("status")),
            "error": _normalized_text(dispatch_result.get("error")),
        }
    )
    return result


def _build_stage_manual_send_plan(route_key: str) -> tuple[dict[str, Any], str, list[dict[str, Any]], int, dict[str, int]]:
    definition = _manual_send_stage_definition(route_key)
    pool = _normalized_text(definition.get("pool"))
    members = [_serialize_member(row) for row in repo.list_stage_members_for_manual_send(current_pool=pool)]
    skipped_reasons: dict[str, int] = {}
    sendable_items: list[dict[str, Any]] = []
    for member in members:
        external_userid = _normalized_text(member.get("external_contact_id"))
        if not external_userid:
            skipped_reasons["missing_external_userid"] = int(skipped_reasons.get("missing_external_userid") or 0) + 1
            continue
        profile = _load_profile(external_userid, _normalized_text(member.get("phone")))
        sendable_items.append(
            {
                "member_id": int(member.get("id") or 0),
                "external_userid": external_userid,
                "mobile": _normalized_text(profile.get("phone")) or _normalized_text(member.get("phone")),
                "customer_name": _normalized_text(profile.get("customer_name")) or external_userid,
                "owner_userid": DEFAULT_OWNER_STAFF_ID,
                "owner_display_name": DEFAULT_OWNER_STAFF_ID,
            }
        )
    return definition, pool, sendable_items, len(members), skipped_reasons


def preview_stage_manual_message(
    *,
    route_key: str,
    content: str = "",
    image_media_ids: list[str] | None = None,
    images: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    refresh_expired_silent_members()
    definition, pool, sendable_items, total_target_count, skipped_reasons = _build_stage_manual_send_plan(route_key)
    normalized_content = _normalized_text(content)
    normalized_image_media_ids = _normalize_manual_send_image_media_ids(image_media_ids)
    task_payload, content_preview, image_count = user_ops_page_service._build_private_message_payload(
        {
            "content": normalized_content,
            "image_media_ids": normalized_image_media_ids,
            "images": list(images or []),
        }
    )
    skipped_count = sum(int(value or 0) for value in skipped_reasons.values())
    return {
        "ok": True,
        "stage_key": _normalized_text(definition.get("route_key")),
        "stage_label": _normalized_text(definition.get("label")),
        "pool_key": pool,
        "pool_label": _pool_label(pool),
        "sender_userid": DEFAULT_OWNER_STAFF_ID,
        "selected_count": total_target_count,
        "total_target_count": total_target_count,
        "eligible_count": len(sendable_items),
        "sendable_count": len(sendable_items),
        "skipped_count": skipped_count,
        "skipped_reasons": skipped_reasons,
        "skipped_summary": user_ops_page_service._summarize_skipped_by_reason(skipped_reasons),
        "content_preview": content_preview,
        "image_count": image_count,
        "has_body": user_ops_page_service.has_private_message_body(task_payload),
        "final_targets": [
            {
                "member_id": int(item.get("member_id") or 0),
                "external_userid": _normalized_text(item.get("external_userid")),
                "customer_name": _normalized_text(item.get("customer_name")),
                "mobile": _normalized_text(item.get("mobile")),
                "owner_userid": DEFAULT_OWNER_STAFF_ID,
                "owner_display_name": DEFAULT_OWNER_STAFF_ID,
            }
            for item in sendable_items
        ],
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
    current_day_index = max(_current_sop_day_index(progress, now_dt=now_dt), int(progress.get("last_sent_day") or 0))
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


def _run_due_sop_for_pool(
    *,
    pool_config: dict[str, Any],
    now_dt: datetime,
    now_text: str,
    operator_id: str,
    operator_type: str,
) -> dict[str, Any]:
    pool_key = _validate_sop_pool_key(pool_config.get("pool_key"))
    live_members = [_serialize_member(row) for row in repo.list_stage_members_for_manual_send(current_pool=pool_key)]
    if not live_members:
        return {
            "batches": [],
            "success_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
        }

    grouped_candidates: dict[tuple[int, str], list[dict[str, Any]]] = {}
    for member in live_members:
        progress = _get_or_create_sop_progress(member, pool_config=pool_config, now_text=now_text)
        candidate = _evaluate_sop_due(
            member=member,
            progress=progress,
            pool_config=pool_config,
            now_dt=now_dt,
            now_text=now_text,
        )
        if int(candidate.get("day_index") or 0) <= 0 or _normalized_text(candidate.get("skip_reason")) == "send_time_not_reached":
            continue
        group_key = (int(candidate["day_index"]), _normalized_text(candidate["scheduled_for"]))
        grouped_candidates.setdefault(group_key, []).append(candidate)

    serialized_batches: list[dict[str, Any]] = []
    total_success_count = 0
    total_skipped_count = 0
    total_failed_count = 0
    for (day_index, scheduled_for), candidates in sorted(grouped_candidates.items(), key=lambda item: (item[0][1], item[0][0])):
        template = _serialize_sop_template(repo.get_sop_template(pool_key=pool_key, day_index=day_index))
        template_skip_reason = _template_skip_reason(template)
        current_template_count = max(_current_sop_template_day_count(pool_key), 1)
        content_snapshot = _normalized_text(template.get("content"))
        images_snapshot = list(template.get("images_json") or [])
        batch = _create_sop_batch(
            pool_key=pool_key,
            day_index=day_index,
            template=template,
            scheduled_for=scheduled_for,
            total_count=len(candidates),
            summary_json={
                "pool_key": pool_key,
                "day_index": day_index,
                "scheduled_for": scheduled_for,
            },
        )
        skipped_reasons: dict[str, int] = {}
        success_count = 0
        skipped_count = 0
        failed_count = 0
        success_record_ids: list[int] = []

        for candidate in candidates:
            original_member = candidate["member"]
            member_id = int(original_member.get("id") or 0)
            live_member = _serialize_member(repo.get_member_by_id(member_id))
            external_userid = _normalized_text(original_member.get("external_contact_id"))
            final_status = ""
            error_message = ""
            sent_record_id: int | None = None
            should_advance_progress = False

            if not live_member or not _normalize_bool(live_member.get("in_pool")) or _normalized_text(live_member.get("current_pool")) != pool_key:
                final_status = "skipped"
                error_message = "moved_out_of_pool"
            elif candidate.get("skip_reason"):
                final_status = "skipped"
                error_message = _normalized_text(candidate.get("skip_reason"))
            elif repo.get_sop_batch_item_for_member_day(member_id=member_id, pool_key=pool_key, day_index_snapshot=day_index):
                final_status = "skipped"
                error_message = "already_processed_today"
            elif not external_userid:
                final_status = "skipped"
                error_message = "missing_external_userid"
                should_advance_progress = True
            elif template_skip_reason:
                final_status = "skipped"
                error_message = template_skip_reason
                should_advance_progress = True
            else:
                image_media_ids, images = _normalize_sop_template_images(template)
                dispatch_result = _dispatch_private_message_batch(
                    target_items=[
                        {
                            "member_id": member_id,
                            "external_userid": external_userid,
                            "mobile": _normalized_text(live_member.get("phone")),
                            "customer_name": _normalized_text(_load_profile(external_userid, _normalized_text(live_member.get("phone"))).get("customer_name")) or external_userid,
                            "owner_userid": DEFAULT_OWNER_STAFF_ID,
                            "owner_display_name": DEFAULT_OWNER_STAFF_ID,
                        }
                    ],
                    content=content_snapshot,
                    image_media_ids=image_media_ids,
                    images=images,
                    operator_id=operator_id or f"sop:{pool_key}:{day_index}",
                    filter_snapshot={
                        "selection_mode": "automation_sop",
                        "pool_key": pool_key,
                        "day_index": day_index,
                        "scheduled_for": scheduled_for,
                        "operator_type": _normalized_text(operator_type) or "system",
                    },
                )
                if dispatch_result.get("ok") and int(dispatch_result.get("sent_count") or 0) > 0:
                    final_status = "success"
                    sent_record_id = int(dispatch_result.get("record_id") or 0) or None
                    success_record_ids.append(int(sent_record_id or 0))
                    should_advance_progress = True
                else:
                    final_status = "failed"
                    error_message = _normalized_text(dispatch_result.get("error")) or _normalized_text(dispatch_result.get("status")) or "dispatch_failed"
                    should_advance_progress = True

            if should_advance_progress:
                updated_progress = repo.save_sop_progress(
                    {
                        "member_id": member_id,
                        "pool_key": pool_key,
                        "first_entered_at": _normalized_text(candidate["progress"].get("first_entered_at")),
                        "last_entered_at": _normalized_text(candidate["progress"].get("last_entered_at")) or _normalized_text(candidate["progress"].get("last_in_pool_at")),
                        "sop_anchor_date": _normalized_text(candidate["progress"].get("sop_anchor_date")),
                        "first_effective_in_pool_at": _normalized_text(candidate["progress"].get("first_effective_in_pool_at")),
                        "last_in_pool_at": _normalized_text(candidate["progress"].get("last_in_pool_at")),
                        "last_sent_day": max(int(candidate["progress"].get("last_sent_day") or 0), day_index),
                        "last_sent_at": now_text if final_status == "success" else _normalized_text(candidate["progress"].get("last_sent_at")),
                        "completed_at": now_text if day_index >= current_template_count else _normalized_text(candidate["progress"].get("completed_at")),
                    }
                )
                candidate["progress"] = _serialize_sop_progress(updated_progress)

            if final_status == "success":
                success_count += 1
            elif final_status == "failed":
                failed_count += 1
            else:
                skipped_count += 1
                skipped_reasons[error_message] = int(skipped_reasons.get(error_message) or 0) + 1

            _record_sop_batch_item(
                batch_id=int(batch["id"]),
                member=live_member or original_member,
                pool_key=pool_key,
                day_index=day_index,
                external_userid=external_userid,
                status=final_status,
                content_snapshot=content_snapshot,
                images_snapshot=images_snapshot,
                error_message=error_message,
                sent_record_id=sent_record_id,
            )

        finalized = _finalize_sop_batch(
            batch,
            success_count=success_count,
            skipped_count=skipped_count,
            failed_count=failed_count,
            skipped_reasons=skipped_reasons,
            success_record_ids=[item for item in success_record_ids if item],
        )
        serialized_batches.append(finalized)
        total_success_count += success_count
        total_skipped_count += skipped_count
        total_failed_count += failed_count

    return {
        "batches": serialized_batches,
        "success_count": total_success_count,
        "skipped_count": total_skipped_count,
        "failed_count": total_failed_count,
    }


def run_due_sop(*, operator_id: str = "", operator_type: str = "system") -> dict[str, Any]:
    ensure_sop_v1_defaults()
    now_text = _iso_now()
    now_dt = _parse_timestamp(now_text) or datetime.now()
    scanned_pool_count = 0
    created_batch_count = 0
    total_success_count = 0
    total_skipped_count = 0
    total_failed_count = 0
    batches: list[dict[str, Any]] = []
    batch_ids: list[int] = []

    for row in repo.list_sop_pool_configs():
        pool_config = _serialize_sop_pool_config(row)
        if not pool_config or not _normalize_bool(pool_config.get("enabled")):
            continue
        scanned_pool_count += 1
        scheduled_today = _scheduled_sop_datetime_for_date(now_dt.strftime("%Y-%m-%d"), send_time=pool_config.get("send_time"))
        if scheduled_today is None or now_dt < scheduled_today:
            continue
        pool_result = _run_due_sop_for_pool(
            pool_config=pool_config,
            now_dt=now_dt,
            now_text=now_text,
            operator_id=operator_id,
            operator_type=operator_type,
        )
        for batch in pool_result["batches"]:
            batches.append(batch)
            batch_id = int(batch.get("id") or 0)
            if batch_id:
                batch_ids.append(batch_id)
        created_batch_count += len(pool_result["batches"])
        total_success_count += int(pool_result.get("success_count") or 0)
        total_skipped_count += int(pool_result.get("skipped_count") or 0)
        total_failed_count += int(pool_result.get("failed_count") or 0)

    get_db().commit()
    return {
        "ok": True,
        "operator_type": _normalized_text(operator_type) or "system",
        "operator_id": _normalized_text(operator_id) or "automation_sop_runner",
        "scanned_pool_count": scanned_pool_count,
        "created_batch_count": created_batch_count,
        "total_success_count": total_success_count,
        "total_skipped_count": total_skipped_count,
        "total_failed_count": total_failed_count,
        "batch_ids": batch_ids,
        "batches": batches,
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


def get_focus_send_batch_detail(*, batch_id: int, item_limit: int = 12) -> dict[str, Any]:
    batch_row = repo.get_focus_send_batch(int(batch_id))
    if not batch_row:
        raise LookupError("focus send batch not found")
    return _focus_batch_detail_payload(batch_row, item_limit=item_limit)


def create_focus_send_batch(*, route_key: str, operator_id: str = "", operator_type: str = "user") -> dict[str, Any]:
    refresh_expired_silent_members()
    definition = _focus_send_stage_definition(route_key)
    normalized_stage_key = _normalized_text(definition.get("route_key"))
    conflict_batch = repo.find_active_focus_send_batch_by_stage(normalized_stage_key)
    if conflict_batch:
        return {
            "ok": False,
            "status": "conflict",
            "error": "当前阶段已有进行中的 AI 批任务",
            "batch": _serialize_focus_send_batch(conflict_batch),
            "items": [
                _serialize_focus_send_batch_item(row)
                for row in repo.list_focus_send_batch_items(batch_id=int(conflict_batch["id"]), limit=12, descending=False)
            ],
        }

    now_text = _iso_now()
    members = [_serialize_member(row) for row in repo.list_stage_members_for_manual_send(current_pool=_normalized_text(definition.get("pool")))]
    pending_items: list[dict[str, Any]] = []
    skipped_count = 0
    batch_row = repo.insert_focus_send_batch(
        {
            "stage_key": normalized_stage_key,
            "pool_key": _normalized_text(definition.get("pool")),
            "operator_type": _normalized_text(operator_type) or "user",
            "operator_id": _normalized_text(operator_id) or "crm_console",
            "status": "pending",
            "total_count": len(members),
            "sent_count": 0,
            "failed_count": 0,
            "skipped_count": 0,
            "cancelled_count": 0,
            "next_run_at": "",
            "last_run_at": "",
            "created_at": now_text,
            "updated_at": now_text,
            "finished_at": "",
        }
    )
    batch_id = int(batch_row.get("id") or 0)
    for index, member in enumerate(members, start=1):
        external_contact_id = _normalized_text(member.get("external_contact_id"))
        item_status = "pending"
        detail = ""
        if not external_contact_id:
            item_status = "skipped"
            detail = "missing_external_userid"
            skipped_count += 1
        else:
            pending_items.append(member)
        repo.insert_focus_send_batch_item(
            {
                "batch_id": batch_id,
                "member_id": int(member.get("id") or 0) if member.get("id") not in (None, "") else None,
                "external_contact_id": external_contact_id,
                "phone": _normalized_text(member.get("phone")),
                "position_index": index,
                "status": item_status,
                "detail": detail,
                "result_payload": {},
                "created_at": now_text,
                "updated_at": now_text,
                "started_at": "",
                "finished_at": now_text if item_status == "skipped" else "",
            }
        )
    batch_status = "pending" if pending_items else "finished"
    finished_at = "" if pending_items else now_text
    updated_batch_row = repo.update_focus_send_batch(
        batch_id,
        {
            **batch_row,
            "status": batch_status,
            "total_count": len(members),
            "sent_count": 0,
            "failed_count": 0,
            "skipped_count": skipped_count,
            "cancelled_count": 0,
            "next_run_at": now_text if pending_items else "",
            "last_run_at": "",
            "updated_at": now_text,
            "finished_at": finished_at,
        },
    )
    get_db().commit()
    detail_payload = _focus_batch_detail_payload(updated_batch_row, item_limit=12)
    return {"ok": True, "status": "created", **detail_payload}


def _finalize_focus_send_batch(
    batch_row: dict[str, Any],
    *,
    now_text: str,
    sent_count: int,
    failed_count: int,
    skipped_count: int,
    cancelled_count: int = 0,
) -> dict[str, Any]:
    remaining_count = max(0, int(batch_row.get("total_count") or 0) - sent_count - failed_count - skipped_count - cancelled_count)
    status = "running" if remaining_count > 0 else "finished"
    base_time = _parse_timestamp(now_text) or datetime.now()
    next_run_at = (base_time + timedelta(seconds=FOCUS_SEND_INTERVAL_SECONDS)).strftime("%Y-%m-%d %H:%M:%S") if remaining_count > 0 else ""
    finished_at = "" if remaining_count > 0 else now_text
    return repo.update_focus_send_batch(
        int(batch_row["id"]),
        {
            **batch_row,
            "status": status,
            "sent_count": sent_count,
            "failed_count": failed_count,
            "skipped_count": skipped_count,
            "cancelled_count": cancelled_count,
            "next_run_at": next_run_at,
            "last_run_at": now_text,
            "updated_at": now_text,
            "finished_at": finished_at,
        },
    )


def _process_focus_send_batch_once(batch_row: dict[str, Any], *, now_text: str) -> dict[str, Any]:
    claimed_item = repo.claim_next_focus_send_batch_item(batch_id=int(batch_row["id"]), started_at=now_text)
    if not claimed_item:
        finalized = _finalize_focus_send_batch(
            batch_row,
            now_text=now_text,
            sent_count=int(batch_row.get("sent_count") or 0),
            failed_count=int(batch_row.get("failed_count") or 0),
            skipped_count=int(batch_row.get("skipped_count") or 0),
            cancelled_count=int(batch_row.get("cancelled_count") or 0),
        )
        return _focus_batch_detail_payload(finalized, item_limit=12)

    serialized_item = _serialize_focus_send_batch_item(claimed_item)
    next_status = "failed"
    detail = ""
    result_payload: dict[str, Any] = {}
    try:
        push_result = push_openclaw(
            external_contact_id=serialized_item["external_contact_id"],
            phone=serialized_item["phone"],
            operator_id=f"focus_batch:{int(batch_row['id'])}",
        )
        result_payload = dict(push_result or {})
        if push_result.get("accepted"):
            next_status = "sent"
        elif _normalized_text(push_result.get("status")) == "cooldown_blocked":
            next_status = "skipped"
            detail = f"cooldown_blocked:{int(push_result.get('remaining_seconds') or 0)}"
        else:
            next_status = "failed"
            detail = _normalized_text(push_result.get("error")) or _normalized_text(push_result.get("status")) or "openclaw_push_failed"
    except LookupError as exc:
        next_status = "skipped"
        detail = str(exc)
        result_payload = {"error": str(exc)}
    except ValueError as exc:
        next_status = "skipped"
        detail = str(exc)
        result_payload = {"error": str(exc)}
    except Exception as exc:
        next_status = "failed"
        detail = str(exc)
        result_payload = {"error": str(exc)}

    repo.update_focus_send_batch_item(
        int(claimed_item["id"]),
        {
            **claimed_item,
            "status": next_status,
            "detail": detail,
            "result_payload": result_payload,
            "updated_at": now_text,
            "started_at": _normalized_text(claimed_item.get("started_at")) or now_text,
            "finished_at": now_text,
        },
    )
    sent_count = int(batch_row.get("sent_count") or 0) + (1 if next_status == "sent" else 0)
    failed_count = int(batch_row.get("failed_count") or 0) + (1 if next_status == "failed" else 0)
    skipped_count = int(batch_row.get("skipped_count") or 0) + (1 if next_status == "skipped" else 0)
    finalized = _finalize_focus_send_batch(
        batch_row,
        now_text=now_text,
        sent_count=sent_count,
        failed_count=failed_count,
        skipped_count=skipped_count,
        cancelled_count=int(batch_row.get("cancelled_count") or 0),
    )
    return _focus_batch_detail_payload(finalized, item_limit=12)


def run_due_focus_send_batches(*, operator_id: str = "", operator_type: str = "system", limit: int = 20) -> dict[str, Any]:
    refresh_expired_silent_members()
    now_text = _iso_now()
    due_batches = repo.list_due_focus_send_batches(due_at=now_text, limit=max(1, int(limit)))
    results: list[dict[str, Any]] = []
    for batch_row in due_batches:
        results.append(_process_focus_send_batch_once(batch_row, now_text=now_text))
    get_db().commit()
    return {
        "ok": True,
        "processed_count": len(results),
        "operator_type": _normalized_text(operator_type) or "system",
        "operator_id": _normalized_text(operator_id) or "focus_batch_runner",
        "batches": results,
    }


def _event_payloads(member_id: int, limit: int = 10) -> list[dict[str, Any]]:
    return [repo.deserialize_event_row(row) for row in repo.list_recent_events(member_id, limit=limit)]


def get_debug_payload(*, external_contact_id: str = "", phone: str = "") -> dict[str, Any]:
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
        action="activation_refresh",
        operator_type="system",
        operator_id=_normalized_text(operator_id) or "activation_webhook",
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
        return {"handled": True, "member": _serialize_member(saved), "won_kept": True, "welcome_message": welcome_result}
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
    return {"handled": True, "member": _serialize_member(saved), "welcome_message": welcome_result}
