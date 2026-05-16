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
from .workflow_service import list_conversion_profile_segment_templates, list_conversion_workflows

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

AUDIENCE_LABELS = {
    "pending_questionnaire": "待填问卷",
    "operating": "运营中",
    "converted": "已转化",
}

ENTRY_CONDITION_LABELS = {
    "any_entry_channel": "任意当前方案入口",
    "specific_qrcode_channel": "指定二维码入口",
    "specific_customer_acquisition_link": "指定获客助手入口",
}

QUESTIONNAIRE_CONDITION_LABELS = {
    "questionnaire_id_matched": "绑定问卷提交成功",
    "normal_question_rule_hit": "命中普通问卷规则",
    "score_segment_hit": "命中总分分层",
    "any_submission": "任意提交",
}


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


def _list_available_questionnaires() -> list[dict[str, Any]]:
    try:
        rows = get_db().execute(
            """
            SELECT
                q.id,
                q.title,
                q.name,
                q.slug,
                q.is_disabled,
                COUNT(qq.id) AS question_count
            FROM questionnaires q
            LEFT JOIN questionnaire_questions qq ON qq.questionnaire_id = q.id
            GROUP BY q.id, q.title, q.name, q.slug, q.is_disabled
            ORDER BY q.updated_at DESC, q.id DESC
            LIMIT 80
            """
        ).fetchall()
    except Exception:
        return []
    return [
        {
            "id": int(row["id"]),
            "title": _normalized_text(row["title"]) or _normalized_text(row["name"]) or _normalized_text(row["slug"]),
            "name": _normalized_text(row["name"]),
            "slug": _normalized_text(row["slug"]),
            "status": "停用" if row["is_disabled"] else "启用",
            "is_disabled": bool(row["is_disabled"]),
            "question_count": int(row["question_count"] or 0),
        }
        for row in rows
    ]


def _selected_questionnaire(questionnaire_id: int | None, available: list[dict[str, Any]]) -> dict[str, Any]:
    normalized_id = int(questionnaire_id or 0)
    if not normalized_id:
        return {}
    for item in available:
        if int(item.get("id") or 0) == normalized_id:
            return dict(item)
    try:
        row = get_db().execute(
            """
            SELECT q.id, q.title, q.name, q.slug, q.is_disabled, COUNT(qq.id) AS question_count
            FROM questionnaires q
            LEFT JOIN questionnaire_questions qq ON qq.questionnaire_id = q.id
            WHERE q.id = ?
            GROUP BY q.id, q.title, q.name, q.slug, q.is_disabled
            """,
            (normalized_id,),
        ).fetchone()
    except Exception:
        row = None
    if not row:
        return {"id": normalized_id, "title": f"问卷 {normalized_id}", "status": "未找到", "question_count": 0}
    return {
        "id": int(row["id"]),
        "title": _normalized_text(row["title"]) or _normalized_text(row["name"]) or _normalized_text(row["slug"]),
        "status": "停用" if row["is_disabled"] else "启用",
        "question_count": int(row["question_count"] or 0),
    }


def _questionnaire_questions(questionnaire_id: int | None) -> list[dict[str, Any]]:
    normalized_id = int(questionnaire_id or 0)
    if not normalized_id:
        return []
    try:
        question_rows = get_db().execute(
            """
            SELECT id, title, type, sort_order
            FROM questionnaire_questions
            WHERE questionnaire_id = ?
            ORDER BY sort_order ASC, id ASC
            """,
            (normalized_id,),
        ).fetchall()
        option_rows = get_db().execute(
            """
            SELECT o.id, o.question_id, o.option_text, o.sort_order
            FROM questionnaire_options o
            JOIN questionnaire_questions q ON q.id = o.question_id
            WHERE q.questionnaire_id = ?
            ORDER BY q.sort_order ASC, o.sort_order ASC, o.id ASC
            """,
            (normalized_id,),
        ).fetchall()
    except Exception:
        return []
    options_by_question: dict[int, list[dict[str, Any]]] = {}
    for row in option_rows:
        options_by_question.setdefault(int(row["question_id"]), []).append(
            {"id": int(row["id"]), "option_text": _normalized_text(row["option_text"])}
        )
    return [
        {
            "id": int(row["id"]),
            "title": _normalized_text(row["title"]),
            "question_type": _normalized_text(row["type"]),
            "sort_order": int(row["sort_order"] or 0),
            "options": options_by_question.get(int(row["id"]), []),
        }
        for row in question_rows
    ]


def _normalize_normal_rule_row(item: dict[str, Any], *, index: int = 0) -> dict[str, Any]:
    hit_option_ids = item.get("hit_option_ids_json")
    if hit_option_ids is None:
        hit_option_ids = item.get("hit_option_ids") or []
    return {
        "questionnaire_id": int(item.get("questionnaire_id") or 0) or None,
        "questionnaire_question_id": int(item.get("questionnaire_question_id") or item.get("question_id") or 0) or None,
        "question_title": _normalized_text(item.get("question_title")),
        "question_type": _normalized_text(item.get("question_type")) or "single_choice",
        "hit_option_ids_json": [int(value) for value in list(hit_option_ids or []) if str(value).strip().isdigit()],
        "hit_options": list(item.get("hit_options") or []),
        "segment_key": _normalized_text(item.get("segment_key")) or _normalized_text(item.get("hit_segment_key")) or "core",
        "segment_name": _normalized_text(item.get("segment_name")) or _normalized_text(item.get("hit_segment_name")) or "重点",
        "rule_note": _normalized_text(item.get("rule_note") or item.get("description")),
        "sort_order": int(item.get("sort_order") or index + 1),
    }


def _normalize_score_range_row(item: dict[str, Any], *, index: int = 0) -> dict[str, Any]:
    return {
        "min_score": item.get("min_score"),
        "max_score": item.get("max_score"),
        "segment_key": _normalized_text(item.get("segment_key")) or f"score_segment_{index + 1}",
        "segment_name": _normalized_text(item.get("segment_name")) or f"分层 {index + 1}",
        "diagnosis_text": _normalized_text(item.get("diagnosis_text")),
        "recommended_action": _normalized_text(item.get("recommended_action")),
    }


def _profile_templates_payload(program_id: int) -> list[dict[str, Any]]:
    try:
        payload = list_conversion_profile_segment_templates(enabled_only=False, program_id=int(program_id))
    except Exception:
        return []
    items = []
    for bundle in payload.get("items") or []:
        template = dict(bundle.get("template") or bundle or {})
        items.append(
            {
                "id": int(template.get("id") or 0),
                "template_name": _normalized_text(template.get("template_name")),
                "template_code": _normalized_text(template.get("template_code")),
                "enabled": bool(template.get("enabled", True)),
            }
        )
    return [item for item in items if item["id"]]


def _normalize_segmentation_payload(payload: dict[str, Any], *, program_id: int) -> dict[str, Any]:
    strategies = dict(payload.get("strategies") or {})
    normal = dict(strategies.get("normal_question_rules") or {})
    score = dict(strategies.get("score_segments") or {})
    profile = dict(strategies.get("profile_dimension") or {})
    normal_rows = payload.get("normal_question_rules_rows")
    if normal_rows is None:
        normal_rows = normal.get("rules") or []
    score_rows = payload.get("score_segment_rows")
    if score_rows is None:
        score_rows = score.get("ranges") or []
    return {
        "questionnaire_id": int(payload.get("questionnaire_id") or 0) or None,
        "default_strategy": _normalized_text(payload.get("default_strategy")) or "normal_question_rules",
        "strategies": {
            "normal_question_rules": {
                "enabled": bool(normal.get("enabled", payload.get("default_strategy") != "manual")),
                "core_threshold": int(normal.get("core_threshold") or payload.get("core_threshold") or 2),
                "rules": [
                    _normalize_normal_rule_row(dict(item or {}), index=index)
                    for index, item in enumerate(list(normal_rows or []))
                ],
            },
            "score_segments": {
                "enabled": bool(score.get("enabled", False)),
                "ranges": [
                    _normalize_score_range_row(dict(item or {}), index=index)
                    for index, item in enumerate(list(score_rows or []))
                ],
            },
            "profile_dimension": {
                "enabled": bool(profile.get("enabled", False)),
                "template_id": int(profile.get("template_id") or payload.get("profile_template_id") or 0) or None,
                "usage": _normalized_text(profile.get("usage")) or "content_variable_only",
            },
        },
        "priority": list(payload.get("priority") or ["normal_question_rules", "score_segments"]),
    }


def _segmentation_view_model(payload: dict[str, Any], *, program_id: int) -> dict[str, Any]:
    normalized = _normalize_segmentation_payload(payload, program_id=int(program_id)) if payload else {
        "questionnaire_id": None,
        "default_strategy": "normal_question_rules",
        "strategies": {
            "normal_question_rules": {"enabled": True, "core_threshold": 2, "rules": []},
            "score_segments": {"enabled": False, "ranges": []},
            "profile_dimension": {"enabled": False, "template_id": None, "usage": "content_variable_only"},
        },
        "priority": ["normal_question_rules", "score_segments"],
    }
    available = _list_available_questionnaires()
    questionnaire_id = normalized.get("questionnaire_id")
    return {
        **normalized,
        "available_questionnaires": available,
        "selected_questionnaire": _selected_questionnaire(questionnaire_id, available),
        "question_rows": _questionnaire_questions(questionnaire_id),
        "normal_question_rules": {
            "core_threshold": int((normalized["strategies"]["normal_question_rules"]).get("core_threshold") or 2),
            "rows": list((normalized["strategies"]["normal_question_rules"]).get("rules") or []),
        },
        "score_segments": {
            "enabled": bool((normalized["strategies"]["score_segments"]).get("enabled")),
            "rows": list((normalized["strategies"]["score_segments"]).get("ranges") or []),
        },
        "profile_dimension": {
            **dict(normalized["strategies"]["profile_dimension"]),
            "available_templates": _profile_templates_payload(int(program_id)),
        },
    }


def _audience_rule_view_model(payload: dict[str, Any], *, program_id: int) -> dict[str, Any]:
    rules = list((payload or {}).get("rules") or DEFAULT_AUDIENCE_ENTRY_RULES)
    by_event = {str(item.get("event") or ""): dict(item or {}) for item in rules}
    entry_rule = by_event.get("channel_enter") or DEFAULT_AUDIENCE_ENTRY_RULES[0]
    submit_rule = by_event.get("questionnaire_submitted") or DEFAULT_AUDIENCE_ENTRY_RULES[1]
    return {
        "rules": rules,
        "normalized_cards": {
            "channel_enter": {
                "event": "channel_enter",
                "event_label": "用户通过入口进入",
                "condition_type": _normalized_text(entry_rule.get("condition_type") or entry_rule.get("condition")) or "any_entry_channel",
                "condition_options": ENTRY_CONDITION_LABELS,
                "target_audience_code": _normalized_text(entry_rule.get("target_audience_code")) or "pending_questionnaire",
                "target_options": AUDIENCE_LABELS,
                "enabled": bool(entry_rule.get("enabled", True)),
            },
            "questionnaire_submitted": {
                "event": "questionnaire_submitted",
                "event_label": "绑定问卷提交成功",
                "condition_type": _normalized_text(submit_rule.get("condition_type") or submit_rule.get("condition")) or "questionnaire_id_matched",
                "condition_options": QUESTIONNAIRE_CONDITION_LABELS,
                "target_audience_code": _normalized_text(submit_rule.get("target_audience_code")) or "operating",
                "target_options": {"operating": "运营中", "converted": "已转化"},
                "enabled": bool(submit_rule.get("enabled", True)),
            },
        },
        "manual_cards": [
            {"event_label": "人工移除", "target_label": "退出当前方案"},
            {"event_label": "成交标记", "target_label": "已转化"},
            {"event_label": "取消成交", "target_label": "运营中"},
        ],
    }


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
    segmentation_view = _segmentation_view_model(segmentation, program_id=int(program_id))
    audience_payload = _payload_from_block(blocks, BLOCK_AUDIENCE_ENTRY_RULE)
    operations = list_conversion_workflows(program_id=int(program_id))
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
        "segmentation": segmentation_view,
        "audience_entry_rule": _audience_rule_view_model(audience_payload, program_id=int(program_id)),
        "operations": {"workflows": [dict((item.get("workflow") or item or {})) for item in operations.get("items") or []]},
        "publish_state": _payload_from_block(blocks, BLOCK_PUBLISH_STATE),
        "publish_check": build_publish_check(program_id),
    }


def normalize_setup_step(step: str) -> str:
    allowed = {key for key, _ in SETUP_STEPS}
    normalized = _normalized_text(step) or "basic"
    return normalized if normalized in allowed else "basic"


def save_setup_basic(program_id: int, payload: dict[str, Any], *, operator_id: str) -> dict[str, Any]:
    existing = get_automation_program(int(program_id))
    existing_basic = program_repo.get_config_block_row(int(program_id), BLOCK_BASIC) or {}
    existing_basic_payload = dict(existing_basic.get("payload_json") or {})
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
            "creation_mode": _normalized_text(payload.get("creation_mode")) or _normalized_text(existing_basic_payload.get("creation_mode")) or "blank",
            "copied_from_program_id": existing_basic_payload.get("copied_from_program_id"),
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
    payload = _normalize_segmentation_payload(dict(payload or {}), program_id=int(program_id))
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
    if payload.get("cards"):
        cards = dict(payload.get("cards") or {})
        rules = []
        for event, defaults in (
            ("channel_enter", DEFAULT_AUDIENCE_ENTRY_RULES[0]),
            ("questionnaire_submitted", DEFAULT_AUDIENCE_ENTRY_RULES[1]),
        ):
            card = dict(cards.get(event) or {})
            rules.append(
                {
                    "event": event,
                    "condition_type": _normalized_text(card.get("condition_type") or defaults.get("condition")) or defaults["condition"],
                    "target_audience_code": _normalized_text(card.get("target_audience_code")) or defaults["target_audience_code"],
                    "enabled": bool(card.get("enabled", True)),
                }
            )
    else:
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
    def item(label: str, passed: bool, message: str, fix_step: str) -> dict[str, Any]:
        return {
            "label": label,
            "passed": bool(passed),
            "severity": "pass" if passed else "fail",
            "message": message if not passed else "已完成",
            "fix_step": fix_step,
            "fix_url": f"?step={fix_step}",
        }

    return {
        "entry": {
            "passed": entry_ok,
            "severity": "pass" if entry_ok else "fail",
            "items": [
                item("方案可用", bool(program), "方案不存在或已被删除", "basic"),
                item("方案未归档", _normalized_text(program.get("status")) != "archived", "归档方案不能发布入口", "basic"),
                item("当前方案未读取默认方案配置", _is_default_program(int(program_id)) or bool(setup), "请先保存当前方案配置", "basic"),
                item("至少有一个当前方案入口", _has_entry_channel(int(program_id)), "请先配置渠道二维码或获客助手入口", "entry"),
            ],
        },
        "full": {
            "passed": full_ok,
            "severity": "pass" if full_ok else ("warning" if entry_ok else "fail"),
            "items": [
                item("入口发布检查通过", entry_ok, "请先完成入口发布检查", "entry"),
                item("已绑定问卷", bool(segmentation.get("questionnaire_id")), "请选择当前方案使用的问卷", "segmentation"),
                item("已配置分层策略", _has_segmentation(segmentation), "请配置普通问卷规则或总分分层", "segmentation"),
                item("入池规则完整", bool(audience_rules), "请保存入池规则", "entry-rule"),
                item("存在启用中的运营动作", bool(workflows.get("items")), "请至少启用一个运营动作", "operations"),
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
