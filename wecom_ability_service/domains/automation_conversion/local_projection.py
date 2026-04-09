from __future__ import annotations

from typing import Any

from ..automation_state.state_defs import (
    FOCUS_POOL_KEYS as SHARED_FOCUS_POOL_KEYS,
    POOL_ACTIVE_FOCUS,
    POOL_ACTIVE_NORMAL,
    POOL_INACTIVE_FOCUS,
    POOL_INACTIVE_NORMAL,
    POOL_LABELS as SHARED_POOL_LABELS,
    POOL_NEW_USER,
    POOL_SILENT,
)

POOL_WON = "won"
POOL_REMOVED = "removed"

POOL_LABELS = {
    **SHARED_POOL_LABELS,
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

FOCUS_SEND_ALLOWED_POOLS = set(SHARED_FOCUS_POOL_KEYS)

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


def _text(value: Any) -> str:
    return str(value or "").strip()


def pool_label(pool: Any) -> str:
    return POOL_LABELS.get(_text(pool), _text(pool) or "未设置")


def stage_from_pool(pool: Any) -> str:
    return STAGE_BY_POOL.get(_text(pool), "removed")


def stage_label(stage: Any) -> str:
    return STAGE_LABELS.get(_text(stage), _text(stage) or "未设置")


def target_from_pool(pool: Any) -> str:
    return TARGET_BY_POOL.get(_text(pool), "none")


def target_label(target: Any) -> str:
    return TARGET_LABELS.get(_text(target), _text(target) or "无")


def button_state(*, current_pool: Any, in_pool: Any) -> dict[str, Any]:
    normalized_current_pool = _text(current_pool)
    in_pool_bool = bool(in_pool)
    won = normalized_current_pool == POOL_WON
    ai_enabled = normalized_current_pool != POOL_REMOVED
    return {
        "put_in_pool": {"enabled": (not in_pool_bool) and (not won)},
        "remove_from_pool": {"enabled": in_pool_bool and not won},
        "set_focus": {"enabled": in_pool_bool and not won},
        "set_normal": {"enabled": in_pool_bool and not won},
        "mark_won": {"enabled": in_pool_bool and not won},
        "unmark_won": {"enabled": won},
        "push_openclaw": {"enabled": ai_enabled},
        "ai_push": {"enabled": ai_enabled},
    }


def manual_send_allowed_route_keys() -> set[str]:
    return {definition["route_key"] for definition in STAGE_DEFINITIONS if definition["pool"] in MANUAL_SEND_ALLOWED_POOLS}


def manual_send_stage_definition(route_key: str) -> dict[str, Any]:
    normalized_route_key = _text(route_key)
    pool = ROUTE_KEY_TO_POOL.get(normalized_route_key)
    if not pool:
        raise ValueError("invalid stage")
    if pool not in MANUAL_SEND_ALLOWED_POOLS:
        raise ValueError("focus stage must use focus send batches")
    return dict(POOL_TO_STAGE_DEF.get(pool) or {})


def focus_send_stage_definition(route_key: str) -> dict[str, Any]:
    normalized_route_key = _text(route_key)
    pool = ROUTE_KEY_TO_POOL.get(normalized_route_key)
    if not pool:
        raise ValueError("invalid stage")
    if pool not in FOCUS_SEND_ALLOWED_POOLS:
        raise ValueError("stage does not support focus send batches")
    return dict(POOL_TO_STAGE_DEF.get(pool) or {})
