from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine, create_engine, text

from aicrm_next.shared.runtime import production_data_ready, raw_database_url


class AutomationProgramDataUnavailable(RuntimeError):
    pass


SETUP_STEPS: tuple[dict[str, str], ...] = (
    {"key": "basic", "label": "基础信息"},
    {"key": "entry", "label": "入口渠道"},
    {"key": "segmentation", "label": "分层规则"},
    {"key": "entry-rule", "label": "入池规则"},
    {"key": "operations", "label": "运营编排"},
    {"key": "publish", "label": "检查并发布"},
)

SETUP_STEP_KEYS = {item["key"] for item in SETUP_STEPS}
BLOCK_BASIC = "basic"
BLOCK_ENTRY_CHANNEL = "entry_channel"
BLOCK_SEGMENTATION = "questionnaire_segmentation"
BLOCK_AUDIENCE_ENTRY_RULE = "audience_entry_rule"
BLOCK_PUBLISH_STATE = "publish_state"
AUDIENCE_LABELS = {
    "pending_questionnaire": "待填问卷",
    "operating": "运营中",
    "converted": "已转化",
}
ENTRY_CONDITION_LABELS = {
    "any_entry_channel": "任一当前方案入口",
    "specific_entry_channel": "指定入口渠道",
}
QUESTIONNAIRE_CONDITION_LABELS = {
    "questionnaire_id_matched": "当前方案问卷提交",
    "any_questionnaire_submitted": "任一问卷提交",
}
DEFAULT_AUDIENCE_ENTRY_RULES = (
    {
        "event": "channel_enter",
        "condition_type": "any_entry_channel",
        "target_audience_code": "pending_questionnaire",
        "enabled": True,
    },
    {
        "event": "questionnaire_submitted",
        "condition_type": "questionnaire_id_matched",
        "target_audience_code": "operating",
        "enabled": True,
    },
)


_FIXTURE_PROGRAM = {
    "id": 1,
    "program_name": "自动化运营方案",
    "program_code": "next_local_preview",
    "description": "本地结构校验方案；生产环境读取 PostgreSQL。",
    "status": "active",
    "updated_at": "2026-05-20T12:00:00Z",
    "config_json": {},
}


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _json_loads(value: Any, *, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return deepcopy(value)
    if value is None:
        return deepcopy(default)
    text_value = str(value or "").strip()
    if not text_value:
        return deepcopy(default)
    try:
        return json.loads(text_value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return deepcopy(default)


def _json_text(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False)


def _stringify_datetime(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _sqlalchemy_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


def _program_summary(program: dict[str, Any], summary: dict[str, Any] | None = None) -> dict[str, Any]:
    summary = dict(summary or {})
    publish_state = dict(summary.get("publish_state") or {})
    full_published = bool(publish_state.get("full_published"))
    entry_published = bool(publish_state.get("entry_published"))
    publish_status = "full" if full_published else "entry" if entry_published else "unpublished"
    publish_label = "完整自动化已发布" if full_published else "入口已发布" if entry_published else "未发布"
    return {
        "channel_count": int(summary.get("channel_count") or 0),
        "workflow_count": int(summary.get("workflow_count") or 0),
        "latest_execution_at": _clean_text(summary.get("latest_execution_at")),
        "publish_state": publish_state,
        "publish_status": publish_status,
        "publish_status_label": publish_label,
    }


def _fixture_summary() -> dict[str, Any]:
    return _program_summary(
        _FIXTURE_PROGRAM,
        {
            "channel_count": 1,
            "workflow_count": 0,
            "latest_execution_at": "",
            "publish_state": {},
        },
    )


def _fixture_setup_payload(program_id: int, *, step: str = "basic") -> dict[str, Any]:
    normalized_step = step if step in SETUP_STEP_KEYS else "basic"
    program = deepcopy(_FIXTURE_PROGRAM)
    program["id"] = int(program_id)
    return {
        "program": program,
        "summary": _fixture_summary(),
        "step": normalized_step,
        "steps": list(SETUP_STEPS),
        "is_default_program": True,
        "legacy_fallback_used": False,
        "blocks": {},
        "basic": dict(program.get("config_json") or {}),
        "entry_channel": {},
        "entry": {
            "channels": [
                {
                    "id": 1,
                    "channel_name": "默认渠道二维码",
                    "channel_code": "next_local_qrcode",
                    "channel_type": "qrcode",
                    "carrier_type": "qrcode",
                    "status": "active",
                    "qr_url": "",
                    "scene_value": "next_local_preview",
                    "auto_accept_friend": False,
                    "welcome_message": "",
                    "initial_audience_code": "pending_questionnaire",
                    "binding_status": "active",
                }
            ],
            "qrcode_channel": {
                "id": 1,
                "channel_name": "默认渠道二维码",
                "channel_code": "next_local_qrcode",
                "channel_type": "qrcode",
                "carrier_type": "qrcode",
                "status": "active",
                "qr_url": "",
                "scene_value": "next_local_preview",
                "auto_accept_friend": False,
                "welcome_message": "",
                "initial_audience_code": "pending_questionnaire",
                "binding_status": "active",
            },
            "customer_acquisition_links": [],
        },
        "segmentation": _segmentation_view_model(
            {
                "questionnaire_id": None,
                "default_strategy": "normal_question_rules",
                "strategies": {},
            },
            program_id=int(program_id),
        ),
        "audience_entry_rule": _audience_rule_view_model({}, program_id=int(program_id)),
        "operations": {"tasks": []},
        "publish_state": {},
        "publish_check": _publish_check_from_parts(
            program,
            has_config=True,
            has_entry=True,
            segmentation={},
            audience_rules=list(DEFAULT_AUDIENCE_ENTRY_RULES),
            active_task_count=0,
        ),
    }


def _fixture_payload() -> dict[str, Any]:
    return {
        "ok": True,
        "items": [{"program": deepcopy(_FIXTURE_PROGRAM), "summary": _fixture_summary()}],
        "default_program": {"id": _FIXTURE_PROGRAM["id"], "program_name": _FIXTURE_PROGRAM["program_name"]},
        "total": 1,
        "source_status": "next_local_preview",
    }


def _payload_from_block(blocks: dict[str, dict[str, Any]], block_key: str) -> dict[str, Any]:
    payload = dict((blocks.get(block_key) or {}).get("payload") or {})
    return deepcopy(payload)


def _normalize_option_category_row(item: dict[str, Any], *, index: int = 0) -> dict[str, Any]:
    raw_option_ids = item.get("option_ids") or []
    if isinstance(raw_option_ids, str):
        raw_option_ids = [value.strip() for value in raw_option_ids.split(",")]
    option_ids: list[int] = []
    for value in list(raw_option_ids or []):
        try:
            option_id = int(value)
        except (TypeError, ValueError):
            continue
        if option_id:
            option_ids.append(option_id)
    snapshots_by_id = {
        int(snapshot.get("id") or 0): dict(snapshot)
        for snapshot in list(item.get("option_snapshots") or [])
        if int(snapshot.get("id") or 0)
    }
    option_snapshots = []
    for option_id in option_ids:
        option = snapshots_by_id.get(option_id) or {}
        option_snapshots.append(
            {
                "id": option_id,
                "option_text": _clean_text(option.get("option_text")) or f"选项 {option_id}",
            }
        )
    return {
        "category_key": _clean_text(item.get("category_key")) or f"category_{index + 1}",
        "category_name": _clean_text(item.get("category_name")) or f"分类 {index + 1}",
        "description": _clean_text(item.get("description")),
        "option_ids": option_ids,
        "option_snapshots": option_snapshots,
    }


def _normalize_normal_rule_row(item: dict[str, Any], *, index: int = 0) -> dict[str, Any]:
    hit_option_ids = item.get("hit_option_ids_json")
    if hit_option_ids is None:
        hit_option_ids = item.get("hit_option_ids") or []
    return {
        "questionnaire_id": int(item.get("questionnaire_id") or 0) or None,
        "questionnaire_question_id": int(item.get("questionnaire_question_id") or item.get("question_id") or 0) or None,
        "question_title": _clean_text(item.get("question_title")),
        "question_type": _clean_text(item.get("question_type")) or "single_choice",
        "hit_option_ids_json": [int(value) for value in list(hit_option_ids or []) if str(value).strip().isdigit()],
        "hit_options": list(item.get("hit_options") or []),
        "segment_key": _clean_text(item.get("segment_key")) or _clean_text(item.get("hit_segment_key")) or "core",
        "segment_name": _clean_text(item.get("segment_name")) or _clean_text(item.get("hit_segment_name")) or "重点",
        "rule_note": _clean_text(item.get("rule_note") or item.get("description")),
        "sort_order": int(item.get("sort_order") or index + 1),
    }


def _normalize_score_range_row(item: dict[str, Any], *, index: int = 0) -> dict[str, Any]:
    return {
        "min_score": item.get("min_score"),
        "max_score": item.get("max_score"),
        "segment_key": _clean_text(item.get("segment_key")) or f"score_segment_{index + 1}",
        "segment_name": _clean_text(item.get("segment_name")) or f"分层 {index + 1}",
        "diagnosis_text": _clean_text(item.get("diagnosis_text")),
        "recommended_action": _clean_text(item.get("recommended_action")),
    }


def _normalize_segmentation_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(payload or {})
    strategies = dict(payload.get("strategies") or {})
    normal = dict(strategies.get("normal_question_rules") or {})
    score = dict(strategies.get("score_segments") or {})
    profile = dict(strategies.get("profile_dimension") or {})
    questionnaire_id = int(payload.get("questionnaire_id") or 0) or None
    category_rows = payload.get("normal_question_categories")
    if category_rows is None:
        category_rows = normal.get("categories") or []
    normal_rows = payload.get("normal_question_rules_rows")
    if normal_rows is None:
        normal_rows = normal.get("rules") or []
    score_rows = payload.get("score_segment_rows")
    if score_rows is None:
        score_rows = score.get("ranges") or []
    segmentation_question_id = int(payload.get("segmentation_question_id") or normal.get("segmentation_question_id") or 0) or None
    return {
        "questionnaire_id": questionnaire_id,
        "default_strategy": _clean_text(payload.get("default_strategy")) or "normal_question_rules",
        "strategies": {
            "normal_question_rules": {
                "enabled": bool(normal.get("enabled", payload.get("default_strategy") != "manual")),
                "mode": _clean_text(payload.get("normal_question_mode") or normal.get("mode")) or "single_question_option_category",
                "segmentation_question_id": segmentation_question_id,
                "segmentation_question_title": _clean_text(normal.get("segmentation_question_title")),
                "categories": [
                    _normalize_option_category_row(dict(item or {}), index=index)
                    for index, item in enumerate(list(category_rows or []))
                ],
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
                "usage": _clean_text(profile.get("usage")) or "content_variable_only",
            },
        },
        "priority": list(payload.get("priority") or ["normal_question_rules", "score_segments"]),
    }


def _segmentation_view_model(payload: dict[str, Any], *, program_id: int) -> dict[str, Any]:
    del program_id
    normalized = _normalize_segmentation_payload(payload)
    normal = dict((normalized.get("strategies") or {}).get("normal_question_rules") or {})
    return {
        **normalized,
        "available_questionnaires": [],
        "selected_questionnaire": {},
        "question_rows": [],
        "selected_segmentation_question": {},
        "normal_question_rules": {
            "mode": _clean_text(normal.get("mode")) or "single_question_option_category",
            "core_threshold": int(normal.get("core_threshold") or 2),
            "segmentation_question_id": normal.get("segmentation_question_id"),
            "segmentation_question_title": _clean_text(normal.get("segmentation_question_title")),
            "selected_question": {},
            "category_rows": list(normal.get("categories") or []),
            "unassigned_options": [],
            "legacy_rows": list(normal.get("rules") or []),
            "rows": list(normal.get("rules") or []),
        },
        "score_segments": {
            "enabled": bool(((normalized.get("strategies") or {}).get("score_segments") or {}).get("enabled")),
            "rows": list(((normalized.get("strategies") or {}).get("score_segments") or {}).get("ranges") or []),
        },
        "profile_dimension": {
            **dict(((normalized.get("strategies") or {}).get("profile_dimension") or {})),
            "available_templates": [],
        },
    }


def _audience_rule_view_model(payload: dict[str, Any] | None, *, program_id: int) -> dict[str, Any]:
    del program_id
    payload = dict(payload or {})
    rules = list(payload.get("rules") or DEFAULT_AUDIENCE_ENTRY_RULES)
    cards_payload = dict(payload.get("cards") or {})
    by_event = {str(item.get("event") or ""): dict(item or {}) for item in rules}
    for event, card in cards_payload.items():
        by_event[str(event)] = {"event": str(event), **dict(card or {})}
    entry_rule = by_event.get("channel_enter") or dict(DEFAULT_AUDIENCE_ENTRY_RULES[0])
    submit_rule = by_event.get("questionnaire_submitted") or dict(DEFAULT_AUDIENCE_ENTRY_RULES[1])
    return {
        "rules": rules,
        "normalized_cards": {
            "channel_enter": {
                "event": "channel_enter",
                "event_label": "入口进入后",
                "condition_type": _clean_text(entry_rule.get("condition_type") or entry_rule.get("condition")) or "any_entry_channel",
                "condition_options": ENTRY_CONDITION_LABELS,
                "target_audience_code": _clean_text(entry_rule.get("target_audience_code")) or "pending_questionnaire",
                "target_options": AUDIENCE_LABELS,
                "enabled": bool(entry_rule.get("enabled", True)),
            },
            "questionnaire_submitted": {
                "event": "questionnaire_submitted",
                "event_label": "问卷提交后",
                "condition_type": _clean_text(submit_rule.get("condition_type") or submit_rule.get("condition")) or "questionnaire_id_matched",
                "condition_options": QUESTIONNAIRE_CONDITION_LABELS,
                "target_audience_code": _clean_text(submit_rule.get("target_audience_code")) or "operating",
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


def _has_segmentation(segmentation: dict[str, Any]) -> bool:
    normalized = _normalize_segmentation_payload(segmentation)
    strategies = dict(normalized.get("strategies") or {})
    normal = dict(strategies.get("normal_question_rules") or {})
    score = dict(strategies.get("score_segments") or {})
    return bool(normal.get("categories") or normal.get("rules") or score.get("ranges"))


def _publish_item(label: str, passed: bool, message: str, fix_step: str) -> dict[str, Any]:
    return {
        "label": label,
        "passed": bool(passed),
        "severity": "pass" if passed else "fail",
        "message": "已完成" if passed else message,
        "fix_step": fix_step,
        "fix_url": f"?step={fix_step}",
    }


def _publish_check_from_parts(
    program: dict[str, Any],
    *,
    has_config: bool,
    has_entry: bool,
    segmentation: dict[str, Any],
    audience_rules: list[dict[str, Any]],
    active_task_count: int,
) -> dict[str, Any]:
    archived = _clean_text(program.get("status")) == "archived"
    is_default = _clean_text(program.get("program_code")) == "signup_conversion_v1"
    entry_ok = bool(program) and not archived and (is_default or has_config) and has_entry
    full_ok = (
        entry_ok
        and bool(segmentation.get("questionnaire_id"))
        and _has_segmentation(segmentation)
        and bool(audience_rules)
        and int(active_task_count or 0) > 0
    )
    return {
        "entry": {
            "passed": entry_ok,
            "severity": "pass" if entry_ok else "fail",
            "items": [
                _publish_item("方案可用", bool(program), "方案不存在或已被删除", "basic"),
                _publish_item("方案未归档", not archived, "归档方案不能发布入口", "basic"),
                _publish_item("当前方案未读取默认方案配置", is_default or has_config, "请先保存当前方案配置", "basic"),
                _publish_item("至少有一个当前方案入口", has_entry, "请先配置渠道二维码或获客助手入口", "entry"),
            ],
        },
        "full": {
            "passed": full_ok,
            "severity": "pass" if full_ok else ("warning" if entry_ok else "fail"),
            "items": [
                _publish_item("入口发布检查通过", entry_ok, "请先完成入口发布检查", "entry"),
                _publish_item("已绑定问卷", bool(segmentation.get("questionnaire_id")), "请选择当前方案使用的问卷", "segmentation"),
                _publish_item("已配置分层策略", _has_segmentation(segmentation), "请配置普通问卷规则或总分分层", "segmentation"),
                _publish_item("入池规则完整", bool(audience_rules), "请保存入池规则", "entry-rule"),
                _publish_item("存在启用中的运营任务", int(active_task_count or 0) > 0, "请至少启用一个运营任务", "operations"),
            ],
        },
    }


def _project_entry_channel(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row.get("id") or 0),
        "binding_id": int(row.get("binding_id") or 0),
        "channel_code": _clean_text(row.get("channel_code")),
        "channel_name": _clean_text(row.get("channel_name")),
        "channel_type": _clean_text(row.get("channel_type")) or "qrcode",
        "carrier_type": _clean_text(row.get("carrier_type")) or "qrcode",
        "status": _clean_text(row.get("status")) or "inactive",
        "binding_status": _clean_text(row.get("binding_status")) or "active",
        "auto_enter_pool": bool(row.get("auto_enter_pool", True)),
        "initial_audience_code": _clean_text(row.get("initial_audience_code")) or "pending_questionnaire",
        "initial_audience_label": AUDIENCE_LABELS.get(_clean_text(row.get("initial_audience_code")), "待填问卷"),
        "priority": int(row.get("priority") or 0),
        "qr_url": _clean_text(row.get("qr_url")),
        "qr_ticket": _clean_text(row.get("qr_ticket")),
        "scene_value": _clean_text(row.get("scene_value")),
        "customer_channel": _clean_text(row.get("customer_channel")),
        "link_url": _clean_text(row.get("link_url")),
        "final_url": _clean_text(row.get("final_url")),
        "welcome_message": _clean_text(row.get("welcome_message")),
        "auto_accept_friend": bool(row.get("auto_accept_friend", False)),
        "entry_tag_id": _clean_text(row.get("entry_tag_id")),
        "entry_tag_name": _clean_text(row.get("entry_tag_name")),
        "entry_tag_group_name": _clean_text(row.get("entry_tag_group_name")),
        "owner_staff_id": _clean_text(row.get("owner_staff_id")),
        "updated_at": _stringify_datetime(row.get("updated_at")),
        "bound_at": _stringify_datetime(row.get("bound_at")),
    }


def _project_customer_acquisition_link(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row.get("id") or 0),
        "link_id": _clean_text(row.get("link_id")),
        "link_name": _clean_text(row.get("link_name")),
        "link_url": _clean_text(row.get("link_url")),
        "customer_channel": _clean_text(row.get("customer_channel")),
        "final_url": _clean_text(row.get("final_url")),
        "initial_audience_code": _clean_text(row.get("initial_audience_code")) or "pending_questionnaire",
        "workflow_id": int(row.get("workflow_id") or 0) or None,
        "skip_verify": bool(row.get("skip_verify", False)),
        "status": _clean_text(row.get("status")) or "active",
        "last_event_at": _stringify_datetime(row.get("last_event_at")),
        "updated_at": _stringify_datetime(row.get("updated_at")),
    }


def _project_operation_task(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row.get("id") or 0),
        "task_name": _clean_text(row.get("task_name")),
        "description": _clean_text(row.get("description")),
        "group_id": int(row.get("group_id") or 0) or None,
        "group_name": _clean_text(row.get("group_name")) or "未分组",
        "status": _clean_text(row.get("status")) or "draft",
        "trigger_type": _clean_text(row.get("trigger_type")) or "scheduled_daily",
        "send_time": _clean_text(row.get("send_time")),
        "timezone": _clean_text(row.get("timezone")) or "Asia/Shanghai",
        "target_audience_code": _clean_text(row.get("target_audience_code")) or "operating",
        "target_audience_label": AUDIENCE_LABELS.get(_clean_text(row.get("target_audience_code")), "运营中"),
        "target_stage_code": _clean_text(row.get("target_stage_code")),
        "audience_day_offset": int(row.get("audience_day_offset") or 0),
        "behavior_filter": _clean_text(row.get("behavior_filter")) or "none",
        "content_mode": _clean_text(row.get("content_mode")) or "unified",
        "profile_segment_template_id": int(row.get("profile_segment_template_id") or 0) or None,
        "updated_at": _stringify_datetime(row.get("updated_at")),
        "published_at": _stringify_datetime(row.get("published_at")),
    }


class PostgresAutomationProgramRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def list_payload(self) -> dict[str, Any]:
        rows = self._fetch_program_rows()
        items = [{"program": row["program"], "summary": row["summary"]} for row in rows]
        default = next((item["program"] for item in items if item["program"].get("program_code") == "signup_conversion_v1"), None)
        if default is None and items:
            default = items[0]["program"]
        return {
            "ok": True,
            "items": items,
            "default_program": {"id": default.get("id"), "program_name": default.get("program_name")} if default else {},
            "total": len(items),
            "source_status": "next_postgres",
        }

    def get_program_with_summary(self, program_id: int) -> dict[str, Any] | None:
        rows = self._fetch_program_rows(program_id=int(program_id))
        return rows[0] if rows else None

    def get_setup_payload(self, program_id: int, *, step: str = "basic") -> dict[str, Any]:
        current = self.get_program_with_summary(int(program_id))
        if not current:
            raise AutomationProgramDataUnavailable(f"automation program {program_id} not found")
        program = dict(current["program"])
        summary = dict(current["summary"])
        normalized_step = step if step in SETUP_STEP_KEYS else "basic"
        with self._engine.connect() as conn:
            blocks = self._fetch_config_blocks(conn, int(program_id))
            entry = self._fetch_entry_payload(conn, int(program_id))
            segmentation_payload = _payload_from_block(blocks, BLOCK_SEGMENTATION)
            segmentation = self._segmentation_view_model(conn, segmentation_payload, program_id=int(program_id))
            audience_payload = _payload_from_block(blocks, BLOCK_AUDIENCE_ENTRY_RULE)
            operations = self._fetch_operations_payload(conn, int(program_id))
        publish_check = _publish_check_from_parts(
            program,
            has_config=bool(blocks),
            has_entry=bool(entry.get("channels")),
            segmentation=segmentation_payload,
            audience_rules=list(audience_payload.get("rules") or []),
            active_task_count=int(operations.get("active_count") or 0),
        )
        return {
            "program": program,
            "summary": summary,
            "step": normalized_step,
            "steps": list(SETUP_STEPS),
            "is_default_program": str(program.get("program_code") or "") == "signup_conversion_v1",
            "legacy_fallback_used": False,
            "blocks": blocks,
            "basic": _payload_from_block(blocks, BLOCK_BASIC) or dict(program.get("config_json") or {}),
            "entry_channel": _payload_from_block(blocks, BLOCK_ENTRY_CHANNEL),
            "entry": entry,
            "segmentation": segmentation,
            "audience_entry_rule": _audience_rule_view_model(audience_payload, program_id=int(program_id)),
            "operations": operations,
            "publish_state": _payload_from_block(blocks, BLOCK_PUBLISH_STATE),
            "publish_check": publish_check,
        }

    def copy_program(self, program_id: int, *, operator_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = dict(payload or {})
        with self._engine.begin() as conn:
            source = conn.execute(
                text("SELECT * FROM automation_program WHERE id = :program_id LIMIT 1"),
                {"program_id": int(program_id)},
            ).mappings().first()
            if not source:
                raise AutomationProgramDataUnavailable(f"automation program {program_id} not found")
            source_dict = dict(source)
            timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
            program_name = _clean_text(payload.get("program_name")) or f"{source_dict.get('program_name') or '自动化运营方案'} 副本"
            program_code = _clean_text(payload.get("program_code")) or f"{source_dict.get('program_code') or 'program'}_copy_{timestamp}"
            inserted = conn.execute(
                text(
                    """
                    INSERT INTO automation_program (
                        program_code,
                        program_name,
                        description,
                        status,
                        config_json,
                        created_by,
                        updated_by,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        :program_code,
                        :program_name,
                        :description,
                        'draft',
                        CAST(:config_json AS jsonb),
                        :operator_id,
                        :operator_id,
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP
                    )
                    RETURNING *
                    """
                ),
                {
                    "program_code": program_code,
                    "program_name": program_name,
                    "description": _clean_text(source_dict.get("description")),
                    "config_json": _json_text(_json_loads(source_dict.get("config_json"), default={})),
                    "operator_id": _clean_text(operator_id),
                },
            ).mappings().first()
            if not inserted:
                raise AutomationProgramDataUnavailable("automation program copy insert failed")
            target_id = int(inserted["id"])
            blocks = conn.execute(
                text(
                    """
                    SELECT *
                    FROM automation_program_config_block
                    WHERE program_id = :program_id
                    ORDER BY block_key ASC
                    """
                ),
                {"program_id": int(program_id)},
            ).mappings().all()
            for block in blocks:
                block_dict = dict(block)
                block_payload = _json_loads(block_dict.get("payload_json"), default={})
                if _clean_text(block_dict.get("block_key")) == "entry_channel":
                    qrcode = dict(block_payload.get("qrcode") or {})
                    for key in ("qr_ticket", "qr_url", "scene_value", "config_id", "wecom_response"):
                        qrcode.pop(key, None)
                    block_payload["qrcode"] = qrcode
                    block_payload.pop("customer_acquisition_link_ids", None)
                conn.execute(
                    text(
                        """
                        INSERT INTO automation_program_config_block (
                            program_id,
                            block_key,
                            payload_json,
                            status,
                            version,
                            copied_from_program_id,
                            copied_from_block_id,
                            created_at,
                            updated_at
                        )
                        VALUES (
                            :target_id,
                            :block_key,
                            CAST(:payload_json AS jsonb),
                            :status,
                            1,
                            :source_program_id,
                            :source_block_id,
                            CURRENT_TIMESTAMP,
                            CURRENT_TIMESTAMP
                        )
                        """
                    ),
                    {
                        "target_id": target_id,
                        "block_key": _clean_text(block_dict.get("block_key")),
                        "payload_json": _json_text(block_payload),
                        "status": _clean_text(block_dict.get("status")) or "draft",
                        "source_program_id": int(program_id),
                        "source_block_id": int(block_dict.get("id") or 0),
                    },
                )
        copied = self.get_program_with_summary(target_id)
        if not copied:
            raise AutomationProgramDataUnavailable(f"copied automation program {target_id} not found")
        return copied

    def update_basic_info(self, program_id: int, payload: dict[str, Any], *, operator_id: str) -> dict[str, Any]:
        status = _clean_text(payload.get("status")) or "draft"
        if status not in {"draft", "active", "paused", "archived"}:
            status = "draft"
        with self._engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    UPDATE automation_program
                    SET program_name = :program_name,
                        program_code = :program_code,
                        description = :description,
                        status = :status,
                        updated_by = :operator_id,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :program_id
                    RETURNING *
                    """
                ),
                {
                    "program_id": int(program_id),
                    "program_name": _clean_text(payload.get("program_name")),
                    "program_code": _clean_text(payload.get("program_code")),
                    "description": _clean_text(payload.get("description")),
                    "status": status,
                    "operator_id": _clean_text(operator_id),
                },
            ).mappings().first()
        if not row:
            raise AutomationProgramDataUnavailable(f"automation program {program_id} not found")
        updated = self.get_program_with_summary(int(program_id))
        if not updated:
            raise AutomationProgramDataUnavailable(f"automation program {program_id} not found")
        return updated

    def update_status(self, program_id: int, *, status: str, operator_id: str) -> dict[str, Any]:
        if status not in {"draft", "active", "paused", "archived"}:
            raise AutomationProgramDataUnavailable(f"unsupported automation program status: {status}")
        with self._engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    UPDATE automation_program
                    SET status = :status,
                        updated_by = :operator_id,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :program_id
                    RETURNING id
                    """
                ),
                {"program_id": int(program_id), "status": status, "operator_id": _clean_text(operator_id)},
            ).mappings().first()
        if not row:
            raise AutomationProgramDataUnavailable(f"automation program {program_id} not found")
        updated = self.get_program_with_summary(int(program_id))
        if not updated:
            raise AutomationProgramDataUnavailable(f"automation program {program_id} not found")
        return updated

    def _fetch_program_rows(self, *, program_id: int | None = None) -> list[dict[str, Any]]:
        where_sql = "WHERE p.id = :program_id" if program_id is not None else "WHERE 1 = 1"
        params = {"program_id": int(program_id)} if program_id is not None else {}
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    f"""
                    SELECT
                        p.*,
                        COALESCE(bindings.channel_count, 0) AS channel_count,
                        COALESCE(workflows.workflow_count, 0) AS workflow_count,
                        executions.latest_execution_at AS latest_execution_at,
                        publish_state.payload_json AS publish_state
                    FROM automation_program p
                    LEFT JOIN LATERAL (
                        SELECT COUNT(*) AS channel_count
                        FROM automation_program_channel_binding b
                        WHERE b.program_id = p.id
                          AND b.binding_status <> 'archived'
                    ) bindings ON true
                    LEFT JOIN LATERAL (
                        SELECT COUNT(*) AS workflow_count
                        FROM automation_workflow w
                        WHERE w.program_id = p.id
                          AND w.status <> 'archived'
                    ) workflows ON true
                    LEFT JOIN LATERAL (
                        SELECT MAX(COALESCE(CAST(e.scheduled_for AS TEXT), CAST(e.updated_at AS TEXT), CAST(e.created_at AS TEXT), '')) AS latest_execution_at
                        FROM automation_workflow_execution e
                        WHERE e.program_id = p.id
                    ) executions ON true
                    LEFT JOIN automation_program_config_block publish_state
                      ON publish_state.program_id = p.id
                     AND publish_state.block_key = 'publish_state'
                    {where_sql}
                    ORDER BY
                        CASE p.status
                            WHEN 'active' THEN 0
                            WHEN 'draft' THEN 1
                            WHEN 'paused' THEN 2
                            ELSE 3
                        END,
                        p.updated_at DESC,
                        p.id DESC
                    """
                ),
                params,
            ).mappings().all()
        return [self._project_row(dict(row)) for row in rows]

    def _fetch_config_blocks(self, conn: Any, program_id: int) -> dict[str, dict[str, Any]]:
        rows = conn.execute(
            text(
                """
                SELECT id, block_key, payload_json, status, version, updated_at
                FROM automation_program_config_block
                WHERE program_id = :program_id
                ORDER BY block_key ASC
                """
            ),
            {"program_id": int(program_id)},
        ).mappings().all()
        blocks: dict[str, dict[str, Any]] = {}
        for row in rows:
            item = dict(row)
            block_key = _clean_text(item.get("block_key"))
            if not block_key:
                continue
            blocks[block_key] = {
                "id": int(item.get("id") or 0),
                "block_key": block_key,
                "payload": _json_loads(item.get("payload_json"), default={}),
                "status": _clean_text(item.get("status")) or "draft",
                "version": int(item.get("version") or 1),
                "updated_at": _stringify_datetime(item.get("updated_at")),
            }
        return blocks

    def _fetch_entry_payload(self, conn: Any, program_id: int) -> dict[str, Any]:
        rows = conn.execute(
            text(
                """
                SELECT
                    c.*,
                    b.id AS binding_id,
                    b.binding_status,
                    b.auto_enter_pool,
                    b.initial_audience_code,
                    b.priority,
                    b.entry_rule_json,
                    b.bound_at,
                    b.updated_at AS binding_updated_at
                FROM automation_program_channel_binding b
                JOIN automation_channel c ON c.id = b.channel_id
                WHERE b.program_id = :program_id
                  AND b.binding_status <> 'archived'
                ORDER BY b.priority DESC, b.id DESC
                """
            ),
            {"program_id": int(program_id)},
        ).mappings().all()
        channels = [_project_entry_channel(dict(row)) for row in rows]
        qrcode = next((item for item in channels if item.get("carrier_type") != "link" and item.get("channel_type") != "wecom_customer_acquisition"), {})
        link_rows = conn.execute(
            text(
                """
                SELECT *
                FROM wecom_customer_acquisition_links
                WHERE program_id = :program_id
                ORDER BY updated_at DESC, id DESC
                LIMIT 100
                """
            ),
            {"program_id": int(program_id)},
        ).mappings().all()
        return {
            "channels": channels,
            "qrcode_channel": dict(qrcode or {}),
            "customer_acquisition_links": [_project_customer_acquisition_link(dict(row)) for row in link_rows],
        }

    def _segmentation_view_model(self, conn: Any, payload: dict[str, Any], *, program_id: int) -> dict[str, Any]:
        normalized = _normalize_segmentation_payload(payload)
        questionnaire_id = int(normalized.get("questionnaire_id") or 0) or None
        available = self._list_available_questionnaires(conn)
        question_rows = self._questionnaire_questions(conn, questionnaire_id)
        selected = next((dict(item) for item in available if int(item.get("id") or 0) == int(questionnaire_id or 0)), {})
        if questionnaire_id and not selected:
            selected = {"id": questionnaire_id, "title": f"问卷 {questionnaire_id}", "status": "未找到", "question_count": 0}
        if selected:
            selected["questions"] = list(question_rows)
        normal_strategy = dict((normalized.get("strategies") or {}).get("normal_question_rules") or {})
        selected_question_id = int(normal_strategy.get("segmentation_question_id") or 0) or (int(question_rows[0]["id"]) if question_rows else None)
        selected_question = next((dict(item) for item in question_rows if int(item.get("id") or 0) == int(selected_question_id or 0)), {})
        option_lookup = {
            int(option.get("id") or 0): dict(option)
            for option in list(selected_question.get("options") or [])
            if int(option.get("id") or 0)
        }
        category_rows = []
        for category in list(normal_strategy.get("categories") or []):
            row = dict(category or {})
            snapshots_by_id = {
                int(item.get("id") or 0): dict(item)
                for item in list(row.get("option_snapshots") or [])
                if int(item.get("id") or 0)
            }
            row["option_snapshots"] = [
                {
                    "id": int(option_id),
                    "option_text": _clean_text((option_lookup.get(int(option_id)) or snapshots_by_id.get(int(option_id)) or {}).get("option_text"))
                    or f"选项 {int(option_id)}",
                }
                for option_id in list(row.get("option_ids") or [])
                if int(option_id or 0)
            ]
            category_rows.append(row)
        assigned_option_ids = {
            int(option_id)
            for category in category_rows
            for option_id in list((category or {}).get("option_ids") or [])
            if int(option_id or 0)
        }
        unassigned_options = [
            dict(option)
            for option in list(selected_question.get("options") or [])
            if int(option.get("id") or 0) not in assigned_option_ids
        ]
        return {
            **normalized,
            "available_questionnaires": available,
            "selected_questionnaire": selected,
            "question_rows": question_rows,
            "selected_segmentation_question": selected_question,
            "normal_question_rules": {
                "mode": _clean_text(normal_strategy.get("mode")) or "single_question_option_category",
                "core_threshold": int(normal_strategy.get("core_threshold") or 2),
                "segmentation_question_id": selected_question_id,
                "segmentation_question_title": _clean_text(selected_question.get("title")),
                "selected_question": selected_question,
                "category_rows": category_rows,
                "unassigned_options": unassigned_options,
                "legacy_rows": list(normal_strategy.get("rules") or []),
                "rows": list(normal_strategy.get("rules") or []),
            },
            "score_segments": {
                "enabled": bool(((normalized.get("strategies") or {}).get("score_segments") or {}).get("enabled")),
                "rows": list(((normalized.get("strategies") or {}).get("score_segments") or {}).get("ranges") or []),
            },
            "profile_dimension": {
                **dict(((normalized.get("strategies") or {}).get("profile_dimension") or {})),
                "available_templates": self._profile_templates(conn, int(program_id)),
            },
        }

    def _list_available_questionnaires(self, conn: Any) -> list[dict[str, Any]]:
        rows = conn.execute(
            text(
                """
                SELECT q.id, q.title, q.name, q.slug, q.is_disabled, COUNT(qq.id) AS question_count
                FROM questionnaires q
                LEFT JOIN questionnaire_questions qq ON qq.questionnaire_id = q.id
                GROUP BY q.id, q.title, q.name, q.slug, q.is_disabled
                ORDER BY q.is_disabled ASC, q.updated_at DESC, q.id DESC
                LIMIT 100
                """
            )
        ).mappings().all()
        return [
            {
                "id": int(row.get("id") or 0),
                "title": _clean_text(row.get("title")) or _clean_text(row.get("name")) or _clean_text(row.get("slug")),
                "status": "停用" if row.get("is_disabled") else "启用",
                "question_count": int(row.get("question_count") or 0),
            }
            for row in rows
        ]

    def _questionnaire_questions(self, conn: Any, questionnaire_id: int | None) -> list[dict[str, Any]]:
        normalized_id = int(questionnaire_id or 0)
        if not normalized_id:
            return []
        question_rows = conn.execute(
            text(
                """
                SELECT id, title, type, sort_order
                FROM questionnaire_questions
                WHERE questionnaire_id = :questionnaire_id
                ORDER BY sort_order ASC, id ASC
                """
            ),
            {"questionnaire_id": normalized_id},
        ).mappings().all()
        option_rows = conn.execute(
            text(
                """
                SELECT o.id, o.question_id, o.option_text, o.sort_order
                FROM questionnaire_options o
                JOIN questionnaire_questions q ON q.id = o.question_id
                WHERE q.questionnaire_id = :questionnaire_id
                ORDER BY q.sort_order ASC, o.sort_order ASC, o.id ASC
                """
            ),
            {"questionnaire_id": normalized_id},
        ).mappings().all()
        options_by_question: dict[int, list[dict[str, Any]]] = {}
        for row in option_rows:
            question_id = int(row.get("question_id") or 0)
            options_by_question.setdefault(question_id, []).append(
                {"id": int(row.get("id") or 0), "option_text": _clean_text(row.get("option_text"))}
            )
        questions: list[dict[str, Any]] = []
        for row in question_rows:
            question_type = _clean_text(row.get("type"))
            if question_type not in {"single_choice", "multi_choice"}:
                continue
            question_id = int(row.get("id") or 0)
            options = options_by_question.get(question_id, [])
            if not options:
                continue
            questions.append(
                {
                    "id": question_id,
                    "title": _clean_text(row.get("title")),
                    "question_type": question_type,
                    "sort_order": int(row.get("sort_order") or 0),
                    "options": options,
                }
            )
        return questions

    def _profile_templates(self, conn: Any, program_id: int) -> list[dict[str, Any]]:
        rows = conn.execute(
            text(
                """
                SELECT id, template_name, template_code, enabled
                FROM automation_profile_segment_template
                WHERE program_id = :program_id OR program_id IS NULL
                ORDER BY enabled DESC, updated_at DESC, id DESC
                LIMIT 100
                """
            ),
            {"program_id": int(program_id)},
        ).mappings().all()
        return [
            {
                "id": int(row.get("id") or 0),
                "template_name": _clean_text(row.get("template_name")),
                "template_code": _clean_text(row.get("template_code")),
                "enabled": bool(row.get("enabled", True)),
            }
            for row in rows
        ]

    def _fetch_operations_payload(self, conn: Any, program_id: int) -> dict[str, Any]:
        task_rows = conn.execute(
            text(
                """
                SELECT t.*, g.group_name
                FROM automation_operation_task t
                LEFT JOIN automation_operation_task_group g ON g.id = t.group_id
                WHERE t.program_id = :program_id
                ORDER BY
                    CASE t.status WHEN 'active' THEN 0 WHEN 'draft' THEN 1 WHEN 'paused' THEN 2 ELSE 3 END,
                    t.updated_at DESC,
                    t.id DESC
                LIMIT 200
                """
            ),
            {"program_id": int(program_id)},
        ).mappings().all()
        tasks = [_project_operation_task(dict(row)) for row in task_rows]
        return {
            "tasks": tasks,
            "active_count": sum(1 for item in tasks if item.get("status") == "active"),
        }

    def _project_row(self, row: dict[str, Any]) -> dict[str, Any]:
        program = {
            "id": int(row.get("id") or 0),
            "program_code": _clean_text(row.get("program_code")),
            "program_name": _clean_text(row.get("program_name")),
            "description": _clean_text(row.get("description")),
            "status": _clean_text(row.get("status")) or "draft",
            "config_json": _json_loads(row.get("config_json"), default={}),
            "created_by": _clean_text(row.get("created_by")),
            "updated_by": _clean_text(row.get("updated_by")),
            "created_at": _stringify_datetime(row.get("created_at")),
            "updated_at": _stringify_datetime(row.get("updated_at")),
        }
        summary = _program_summary(
            program,
            {
                "channel_count": row.get("channel_count"),
                "workflow_count": row.get("workflow_count"),
                "latest_execution_at": row.get("latest_execution_at"),
                "publish_state": _json_loads(row.get("publish_state"), default={}),
            },
        )
        return {"program": program, "summary": summary}


def _build_postgres_repository() -> PostgresAutomationProgramRepository:
    database_url = raw_database_url()
    if not database_url:
        raise AutomationProgramDataUnavailable("DATABASE_URL is required for automation program repository")
    return PostgresAutomationProgramRepository(create_engine(_sqlalchemy_database_url(database_url), future=True))


def list_automation_programs_payload() -> dict[str, Any]:
    if production_data_ready():
        try:
            return _build_postgres_repository().list_payload()
        except Exception as exc:  # pragma: no cover - exercised with unavailable production DBs.
            raise AutomationProgramDataUnavailable(str(exc)) from exc
    return _fixture_payload()


def get_automation_program_with_summary(program_id: int) -> dict[str, Any] | None:
    if production_data_ready():
        try:
            return _build_postgres_repository().get_program_with_summary(int(program_id))
        except Exception as exc:  # pragma: no cover - exercised with unavailable production DBs.
            raise AutomationProgramDataUnavailable(str(exc)) from exc
    if int(program_id) == int(_FIXTURE_PROGRAM["id"]):
        return {"program": deepcopy(_FIXTURE_PROGRAM), "summary": _fixture_summary()}
    return None


def get_automation_program_setup_payload(program_id: int, *, step: str = "basic") -> dict[str, Any]:
    if production_data_ready():
        try:
            return _build_postgres_repository().get_setup_payload(int(program_id), step=step)
        except Exception as exc:  # pragma: no cover - exercised with unavailable production DBs.
            raise AutomationProgramDataUnavailable(str(exc)) from exc
    if int(program_id) == int(_FIXTURE_PROGRAM["id"]):
        return _fixture_setup_payload(int(program_id), step=step)
    raise AutomationProgramDataUnavailable(f"automation program {program_id} not found")


def copy_automation_program(program_id: int, *, operator_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if production_data_ready():
        try:
            return _build_postgres_repository().copy_program(int(program_id), operator_id=operator_id, payload=payload)
        except Exception as exc:  # pragma: no cover - exercised with unavailable production DBs.
            raise AutomationProgramDataUnavailable(str(exc)) from exc
    copied_program = deepcopy(_FIXTURE_PROGRAM)
    copied_program["id"] = int(program_id) + 1000
    copied_program["program_name"] = _clean_text((payload or {}).get("program_name")) or f"{copied_program['program_name']} 副本"
    copied_program["program_code"] = _clean_text((payload or {}).get("program_code")) or f"{copied_program['program_code']}_copy"
    copied_program["status"] = "draft"
    copied_program["updated_at"] = datetime.now(UTC).isoformat()
    return {"program": copied_program, "summary": _fixture_summary()}


def update_automation_program_basic_info(program_id: int, payload: dict[str, Any], *, operator_id: str) -> dict[str, Any]:
    if production_data_ready():
        try:
            return _build_postgres_repository().update_basic_info(int(program_id), payload, operator_id=operator_id)
        except Exception as exc:  # pragma: no cover - exercised with unavailable production DBs.
            raise AutomationProgramDataUnavailable(str(exc)) from exc
    updated = deepcopy(_FIXTURE_PROGRAM)
    updated["id"] = int(program_id)
    updated["program_name"] = _clean_text(payload.get("program_name")) or updated["program_name"]
    updated["program_code"] = _clean_text(payload.get("program_code")) or updated["program_code"]
    updated["description"] = _clean_text(payload.get("description"))
    updated["status"] = _clean_text(payload.get("status")) or updated["status"]
    return {"program": updated, "summary": _fixture_summary()}


def update_automation_program_status(program_id: int, *, status: str, operator_id: str) -> dict[str, Any]:
    if production_data_ready():
        try:
            return _build_postgres_repository().update_status(int(program_id), status=status, operator_id=operator_id)
        except Exception as exc:  # pragma: no cover - exercised with unavailable production DBs.
            raise AutomationProgramDataUnavailable(str(exc)) from exc
    updated = deepcopy(_FIXTURE_PROGRAM)
    updated["id"] = int(program_id)
    updated["status"] = status
    return {"program": updated, "summary": _fixture_summary()}
