from __future__ import annotations

import re
from typing import Any

from ...db import get_db
from . import program_repo, repo
from .channel_service import save_default_channel_settings
from .customer_acquisition_service import create_customer_acquisition_link, list_customer_acquisition_links
from .program_service import (
    PROGRAM_STATUS_ACTIVE,
    get_automation_program,
    get_default_automation_program_id,
    update_automation_program_status,
)
from .service import _normalized_text, get_settings_payload
from .workflow_service import list_conversion_workflows

BLOCK_BASIC = "basic"
BLOCK_ENTRY_CHANNEL = "entry_channel"
BLOCK_SEGMENTATION = "questionnaire_segmentation"
BLOCK_AUDIENCE_ENTRY_RULE = "audience_entry_rule"
BLOCK_PUBLISH_STATE = "publish_state"
CONFIG_BLOCK_KEYS = (
    BLOCK_BASIC,
    BLOCK_ENTRY_CHANNEL,
    BLOCK_SEGMENTATION,
    BLOCK_AUDIENCE_ENTRY_RULE,
    BLOCK_PUBLISH_STATE,
)

SETUP_STEPS = (
    ("basic", "基础信息"),
    ("entry", "入口渠道"),
    ("segmentation", "分层规则"),
    ("entry-rule", "入池规则"),
    ("operations", "运营编排"),
    ("publish", "检查并发布"),
)

DEFAULT_AUDIENCE_ENTRY_RULES = [
    {
        "event": "channel_enter",
        "condition": "any_entry_channel",
        "target_audience_code": "pending_questionnaire",
        "enabled": True,
    },
    {
        "event": "questionnaire_submitted",
        "condition": "questionnaire_id_matched",
        "target_audience_code": "operating",
        "enabled": True,
    },
]


def _program_code(value: Any) -> str:
    text = _normalized_text(value).lower()
    text = re.sub(r"[^a-z0-9_]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_")


def _is_default_program(program_id: int) -> bool:
    try:
        return int(program_id) == int(get_default_automation_program_id())
    except Exception:
        return False


def initialize_empty_config_blocks(program_id: int) -> None:
    for block_key in CONFIG_BLOCK_KEYS:
        if program_repo.get_config_block_row(int(program_id), block_key):
            continue
        program_repo.upsert_config_block_row(int(program_id), block_key, {}, status="draft")


def copy_config_blocks(source_program_id: int, target_program_id: int) -> list[dict[str, Any]]:
    return program_repo.copy_config_blocks(int(source_program_id), int(target_program_id))


def _blocks_by_key(program_id: int) -> dict[str, dict[str, Any]]:
    return {str(item.get("block_key") or ""): item for item in program_repo.list_config_block_rows(int(program_id))}


def _legacy_segmentation_payload() -> dict[str, Any]:
    settings = get_settings_payload(program_id=None)
    return {
        "questionnaire_id": int(((settings.get("config") or {}).get("questionnaire_id")) or 0) or None,
        "default_strategy": "normal_question_rules",
        "strategies": {
            "normal_question_rules": {
                "enabled": True,
                "core_threshold": int(((settings.get("config") or {}).get("core_threshold")) or 0),
                "rules": list(((settings.get("rule_editor") or {}).get("rules")) or []),
            },
            "score_segments": {"enabled": False, "ranges": []},
            "profile_dimension": {"enabled": False, "usage": "content_variable_only"},
        },
        "priority": ["normal_question_rules", "score_segments"],
        "source": "legacy_singleton",
    }


def _payload_from_block(blocks: dict[str, dict[str, Any]], block_key: str) -> dict[str, Any]:
    return dict((blocks.get(block_key) or {}).get("payload_json") or {})


def _program_entry_payload(program_id: int) -> dict[str, Any]:
    channels = repo.list_channels_by_program(int(program_id), include_inactive=True)
    qrcode_channels = [
        item
        for item in channels
        if not _normalized_text(item.get("channel_code")).startswith("wecom_customer_acquisition_")
    ]
    return {
        "channels": channels,
        "qrcode_channel": qrcode_channels[0] if qrcode_channels else {},
        "customer_acquisition_links": list_customer_acquisition_links(program_id=int(program_id)),
    }


def get_program_setup_payload(program_id: int, *, step: str = "basic") -> dict[str, Any]:
    program = get_automation_program(int(program_id))
    blocks = _blocks_by_key(int(program_id))
    segmentation = _payload_from_block(blocks, BLOCK_SEGMENTATION)
    legacy_fallback_used = False
    if not segmentation and _is_default_program(int(program_id)):
        segmentation = _legacy_segmentation_payload()
        legacy_fallback_used = True
    return {
        "program": program,
        "step": normalize_setup_step(step),
        "steps": [{"key": key, "label": label} for key, label in SETUP_STEPS],
        "is_default_program": _is_default_program(int(program_id)),
        "legacy_fallback_used": legacy_fallback_used,
        "blocks": blocks,
        "basic": _payload_from_block(blocks, BLOCK_BASIC),
        "entry_channel": _payload_from_block(blocks, BLOCK_ENTRY_CHANNEL),
        "entry": _program_entry_payload(int(program_id)),
        "segmentation": segmentation,
        "audience_entry_rule": _payload_from_block(blocks, BLOCK_AUDIENCE_ENTRY_RULE),
        "publish_state": _payload_from_block(blocks, BLOCK_PUBLISH_STATE),
        "publish_check": build_publish_check(program_id),
    }


def normalize_setup_step(step: str) -> str:
    allowed = {key for key, _ in SETUP_STEPS}
    normalized = _normalized_text(step) or "basic"
    return normalized if normalized in allowed else "basic"


def save_setup_basic(program_id: int, payload: dict[str, Any], *, operator_id: str) -> dict[str, Any]:
    existing = get_automation_program(int(program_id))
    name = _normalized_text(payload.get("program_name")) or _normalized_text(existing.get("program_name"))
    code = _program_code(payload.get("program_code")) or _program_code(existing.get("program_code"))
    if not name:
        raise ValueError("方案名称不能为空")
    if not code:
        raise ValueError("方案编码不能为空")
    duplicate = program_repo.get_program_row_by_code(code)
    if duplicate and int(duplicate.get("id") or 0) != int(program_id):
        raise ValueError("方案编码已存在")
    status = _normalized_text(payload.get("status")) or _normalized_text(existing.get("status")) or "draft"
    if status not in {"draft", "active", "paused", "archived"}:
        raise ValueError("方案状态不正确")
    program = program_repo.update_program_row(
        int(program_id),
        {
            "program_code": code,
            "program_name": name,
            "description": _normalized_text(payload.get("description")),
            "status": status,
            "config_json": dict(existing.get("config_json") or {}),
            "updated_by": operator_id,
        },
    )
    block = program_repo.upsert_config_block_row(
        int(program_id),
        BLOCK_BASIC,
        {
            "program_name": name,
            "program_code": code,
            "description": _normalized_text(payload.get("description")),
            "status": status,
            "creation_mode": _normalized_text(payload.get("creation_mode")) or "blank",
        },
        status="saved",
    )
    get_db().commit()
    return {"program": program, "block": block}


def save_entry_channel(program_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    channel_payload = {
        "program_id": int(program_id),
        "channel_name": _normalized_text(payload.get("channel_name")),
        "welcome_message": _normalized_text(payload.get("welcome_message")),
        "auto_accept_friend": bool(payload.get("auto_accept_friend")),
        "entry_tag_id": _normalized_text(payload.get("entry_tag_id")),
        "entry_tag_name": _normalized_text(payload.get("entry_tag_name")),
        "entry_tag_group_name": _normalized_text(payload.get("entry_tag_group_name")),
    }
    channel_result = save_default_channel_settings(channel_payload, program_id=int(program_id))
    block = program_repo.upsert_config_block_row(
        int(program_id),
        BLOCK_ENTRY_CHANNEL,
        {"qrcode": channel_payload},
        status="saved",
    )
    get_db().commit()
    return {"entry_channel": channel_result, "block": block}


def create_program_customer_acquisition_link(program_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    result = create_customer_acquisition_link({**dict(payload or {}), "program_id": int(program_id)})
    existing = program_repo.get_config_block_row(int(program_id), BLOCK_ENTRY_CHANNEL)
    entry_payload = dict((existing or {}).get("payload_json") or {})
    link_ids = list(entry_payload.get("customer_acquisition_link_ids") or [])
    link_id = int((result.get("link") or {}).get("id") or 0)
    if link_id and link_id not in link_ids:
        link_ids.append(link_id)
    entry_payload["customer_acquisition_link_ids"] = link_ids
    block = program_repo.upsert_config_block_row(int(program_id), BLOCK_ENTRY_CHANNEL, entry_payload, status="saved")
    get_db().commit()
    return {**result, "block": block}


def _score_ranges(payload: dict[str, Any]) -> list[dict[str, Any]]:
    strategies = dict(payload.get("strategies") or {})
    score_segments = dict(strategies.get("score_segments") or {})
    return [dict(item or {}) for item in list(score_segments.get("ranges") or [])]


def validate_score_ranges(payload: dict[str, Any]) -> None:
    ranges = []
    for item in _score_ranges(payload):
        min_score = item.get("min_score")
        max_score = item.get("max_score")
        if min_score is None or max_score is None:
            raise ValueError("总分分层区间必须填写最低分和最高分")
        min_value = float(min_score)
        max_value = float(max_score)
        if min_value > max_value:
            raise ValueError("总分分层区间最低分不能大于最高分")
        ranges.append((min_value, max_value, _normalized_text(item.get("segment_name"))))
    ranges.sort(key=lambda item: (item[0], item[1]))
    for previous, current in zip(ranges, ranges[1:]):
        if current[0] <= previous[1]:
            raise ValueError("总分分层区间不能重叠")


def match_score_segment(payload: dict[str, Any], total_score: float) -> dict[str, Any] | None:
    for item in _score_ranges(payload):
        min_score = float(item.get("min_score"))
        max_score = float(item.get("max_score"))
        if min_score <= float(total_score) <= max_score:
            return item
    return None


def save_segmentation(program_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    validate_score_ranges(payload)
    block = program_repo.upsert_config_block_row(
        int(program_id),
        BLOCK_SEGMENTATION,
        dict(payload or {}),
        status="saved",
    )
    get_db().commit()
    return {"segmentation": block}


def save_audience_entry_rule(program_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    rules = list(payload.get("rules") or DEFAULT_AUDIENCE_ENTRY_RULES)
    block = program_repo.upsert_config_block_row(
        int(program_id),
        BLOCK_AUDIENCE_ENTRY_RULE,
        {"rules": rules},
        status="saved",
    )
    get_db().commit()
    return {"audience_entry_rule": block}


def _has_entry_channel(program_id: int) -> bool:
    channels = repo.list_channels_by_program(int(program_id), include_inactive=False)
    if any(_normalized_text(item.get("status")) in {"active", "configured"} for item in channels):
        return True
    return any(_normalized_text(item.get("status")) == "active" for item in list_customer_acquisition_links(program_id=int(program_id)))


def _has_segmentation(payload: dict[str, Any]) -> bool:
    strategies = dict(payload.get("strategies") or {})
    normal = dict(strategies.get("normal_question_rules") or {})
    score = dict(strategies.get("score_segments") or {})
    return bool(normal.get("enabled") and normal.get("rules")) or bool(score.get("enabled") and score.get("ranges"))


def build_publish_check(program_id: int) -> dict[str, Any]:
    program = get_automation_program(int(program_id))
    setup = _blocks_by_key(int(program_id))
    segmentation = _payload_from_block(setup, BLOCK_SEGMENTATION)
    if not segmentation and _is_default_program(int(program_id)):
        segmentation = _legacy_segmentation_payload()
    workflows = list_conversion_workflows(status="active", program_id=int(program_id))
    entry_ok = (
        _normalized_text(program.get("status")) != "archived"
        and (_is_default_program(int(program_id)) or bool(setup))
        and _has_entry_channel(int(program_id))
    )
    audience_rules = list(_payload_from_block(setup, BLOCK_AUDIENCE_ENTRY_RULE).get("rules") or [])
    full_ok = (
        entry_ok
        and bool(segmentation.get("questionnaire_id"))
        and _has_segmentation(segmentation)
        and bool(audience_rules)
        and bool(workflows.get("items"))
    )
    return {
        "entry": {
            "passed": entry_ok,
            "items": [
                {"label": "方案可用", "passed": bool(program)},
                {"label": "方案未归档", "passed": _normalized_text(program.get("status")) != "archived"},
                {"label": "未读取默认方案配置", "passed": _is_default_program(int(program_id)) or bool(setup)},
                {"label": "入口绑定当前方案", "passed": _has_entry_channel(int(program_id))},
            ],
        },
        "full": {
            "passed": full_ok,
            "items": [
                {"label": "入口发布检查通过", "passed": entry_ok},
                {"label": "已绑定问卷", "passed": bool(segmentation.get("questionnaire_id"))},
                {"label": "已配置分层策略", "passed": _has_segmentation(segmentation)},
                {"label": "入池规则完整", "passed": bool(audience_rules)},
                {"label": "存在启用中的运营动作", "passed": bool(workflows.get("items"))},
            ],
        },
    }


def publish_entry(program_id: int, *, operator_id: str) -> dict[str, Any]:
    check = build_publish_check(int(program_id))
    if not check["entry"]["passed"]:
        raise ValueError("入口发布检查未通过")
    block = program_repo.upsert_config_block_row(
        int(program_id),
        BLOCK_PUBLISH_STATE,
        {"entry_published": True, "full_published": False},
        status="published",
    )
    program = update_automation_program_status(int(program_id), status=PROGRAM_STATUS_ACTIVE, operator_id=operator_id)["program"]
    return {"program": program, "publish_state": block, "publish_check": build_publish_check(int(program_id))}


def publish_full(program_id: int, *, operator_id: str) -> dict[str, Any]:
    check = build_publish_check(int(program_id))
    if not check["full"]["passed"]:
        raise ValueError("完整自动化发布检查未通过")
    block = program_repo.upsert_config_block_row(
        int(program_id),
        BLOCK_PUBLISH_STATE,
        {"entry_published": True, "full_published": True},
        status="published",
    )
    program = update_automation_program_status(int(program_id), status=PROGRAM_STATUS_ACTIVE, operator_id=operator_id)["program"]
    return {"program": program, "publish_state": block, "publish_check": build_publish_check(int(program_id))}
