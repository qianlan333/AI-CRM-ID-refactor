from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ...db import get_db
from ..class_user.service import (
    apply_class_user_status_change,
    clear_class_user_status_current,
    get_class_user_status_current,
    get_class_user_status_definition,
)
from ..archive import repo as archive_repo
from ..archive.service import extract_roomid_from_raw_payload, format_message_row, get_recent_messages_by_user
from ..group_chats.repo import get_group_chat_map
from ..questionnaire.service import get_questionnaire_detail
from . import repo

DEFAULT_SCENARIO_KEY = "signup_conversion_v1"
DEFAULT_AUTOMATION_NAME = "报名成功自动化"
DEFAULT_TARGET_EVENT = "signup_success"
DEFAULT_CHANNEL_TYPE = "text_message"
DEFAULT_CORE_THRESHOLD = 3
DEFAULT_TOP_THRESHOLD = 4
DEFAULT_QUIET_HOUR_START = 23
DEFAULT_TIMEZONE = "Asia/Shanghai"
DEFAULT_ENROLLED_SIGNUP_STATUS = "signed_999"
REQUIRED_QUESTION_RULE_COUNT = 5
VALUE_SEGMENT_SCORING_VERSION = "signup_conversion_question_hits_v1"
_VALUE_SEGMENT_RANKS = {"unknown": 0, "normal": 1, "core": 2, "top": 3}

_EXIT_SIGNUP_PREFIXES = ("signed_",)
_HIGH_INTENT_TAG_KEYWORDS = ("高意向", "待跟进", "已报价", "课程安排", "想报名")
_VALUE_SEGMENT_LABELS = {"unknown": "未知", "top": "Top", "core": "Core", "normal": "普通"}
_PHASE_LABELS = {
    "awaiting_trigger": "待触发",
    "waiting_openclaw": "待 OpenClaw 处理",
    "blocked_after_2300": "23:00 后不启动",
    "exited_signup_success": "已报名成功，退出自动化",
}
_CUSTOMER_MARKETING_STATE_LABELS = {
    ("prospect", "mobile_only"): "手机号线索",
    ("prospect", "wecom_connected"): "已加微待激活",
    ("active", "activated"): "已激活",
    ("converted", "enrolled"): "已报名成功",
}
_ROUTER_ALLOWED_STAGE_KEYS = {"prospect/wecom_connected", "active/activated"}
_ROUTER_ALLOWED_SEGMENTS = {"core", "top"}
_ROUTER_TERMINAL_DISPATCH_STATUSES = {"dispatched", "acked", "cancelled", "converted_before_dispatch"}
_ROUTER_BLOCKED_DISPATCH_STATUS = "blocked_quiet_hours"
_ROUTER_PENDING_DISPATCH_STATUS = "pending"
_OPENCLAW_ACKABLE_DISPATCH_STATUSES = {"pending", "dispatched", "acked"}


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


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


def _normalize_bool(value: Any, *, default: bool = False) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return _normalized_text(value).lower() in {"1", "true", "yes", "y", "on"}


def _normalize_int(
    value: Any,
    field_name: str,
    *,
    default: int | None = None,
    minimum: int | None = None,
    maximum: int | None = None,
    allow_none: bool = False,
) -> int | None:
    if value in (None, ""):
        if allow_none:
            return None
        if default is not None:
            return int(default)
        raise ValueError(f"{field_name} is required")
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer") from exc
    if minimum is not None and normalized < minimum:
        raise ValueError(f"{field_name} must be >= {minimum}")
    if maximum is not None and normalized > maximum:
        raise ValueError(f"{field_name} must be <= {maximum}")
    return normalized


def _normalize_option_id_list(value: Any) -> list[int]:
    raw_value = value
    if isinstance(value, str):
        raw_value = _json_loads(value, default=None)
    if not isinstance(raw_value, list):
        raise ValueError("hit_option_ids_json must be an array")
    result: list[int] = []
    seen: set[int] = set()
    for item in raw_value:
        option_id = _normalize_int(item, "hit_option_ids_json item", minimum=1)
        if option_id in seen:
            continue
        seen.add(int(option_id))
        result.append(int(option_id))
    if not result:
        raise ValueError("hit_option_ids_json must contain at least one option id")
    return result


def _validate_timezone(value: Any) -> str:
    timezone = _normalized_text(value) or DEFAULT_TIMEZONE
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("timezone is invalid") from exc
    return timezone


def _parse_timestamp(value: Any) -> datetime | None:
    text = _normalized_text(value)
    if not text:
        return None
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, pattern)
        except ValueError:
            continue
    return None


def _iso_now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _default_config_payload(*, automation_key: str = DEFAULT_SCENARIO_KEY) -> dict[str, Any]:
    return {
        "automation_key": automation_key,
        "automation_name": DEFAULT_AUTOMATION_NAME,
        "target_event": DEFAULT_TARGET_EVENT,
        "channel_type": DEFAULT_CHANNEL_TYPE,
        "enabled": True,
        "questionnaire_id": None,
        "core_threshold": DEFAULT_CORE_THRESHOLD,
        "top_threshold": DEFAULT_TOP_THRESHOLD,
        "quiet_hour_start": DEFAULT_QUIET_HOUR_START,
        "timezone": DEFAULT_TIMEZONE,
        "question_rules": [],
        "configured": False,
        "created_at": "",
        "updated_at": "",
    }


def _segment_rank(segment: str) -> int:
    return _VALUE_SEGMENT_RANKS.get(_normalized_text(segment), 0)


def _questionnaire_lookup(questionnaire_id: int) -> tuple[dict[str, Any], dict[int, dict[str, Any]], dict[int, dict[int, dict[str, Any]]]]:
    questionnaire = get_questionnaire_detail(int(questionnaire_id))
    if not questionnaire:
        raise ValueError("questionnaire not found")
    question_map: dict[int, dict[str, Any]] = {}
    option_map: dict[int, dict[int, dict[str, Any]]] = {}
    for question in questionnaire.get("questions") or []:
        question_id = int(question["id"])
        question_map[question_id] = dict(question)
        option_map[question_id] = {int(option["id"]): dict(option) for option in question.get("options") or []}
    return questionnaire, question_map, option_map


def _serialize_question_rule(
    row: dict[str, Any],
    *,
    question_map: dict[int, dict[str, Any]] | None = None,
    option_map: dict[int, dict[int, dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    questionnaire_question_id = int(row.get("question_id") or row.get("questionnaire_question_id") or 0)
    hit_option_ids = [
        int(option_id)
        for option_id in _json_loads(row.get("answer_match_value_json") or row.get("hit_option_ids_json"), default=[])
        if str(option_id).strip()
    ]
    question = (question_map or {}).get(questionnaire_question_id, {})
    available_options = (option_map or {}).get(questionnaire_question_id, {})
    return {
        "id": int(row.get("id") or 0),
        "questionnaire_id": _normalize_int(row.get("questionnaire_id"), "questionnaire_id", allow_none=True),
        "questionnaire_question_id": questionnaire_question_id,
        "question_title": _normalized_text(question.get("title")) or _normalized_text(row.get("rule_name")),
        "question_type": _normalized_text(question.get("type")),
        "hit_option_ids_json": hit_option_ids,
        "hit_options": [
            {"id": option_id, "option_text": _normalized_text(available_options.get(option_id, {}).get("option_text"))}
            for option_id in hit_option_ids
        ],
        "sort_order": int(row.get("sort_order") or 0),
    }


def list_signup_conversion_question_rules(*, automation_key: str = DEFAULT_SCENARIO_KEY) -> list[dict[str, Any]]:
    config_row = repo.get_marketing_automation_config(automation_key)
    if not config_row:
        return []
    payload = _json_loads(config_row.get("config_payload_json"), default={})
    questionnaire_id = _normalize_int(payload.get("questionnaire_id"), "questionnaire_id", allow_none=True)
    question_map: dict[int, dict[str, Any]] = {}
    option_map: dict[int, dict[int, dict[str, Any]]] = {}
    if questionnaire_id:
        _, question_map, option_map = _questionnaire_lookup(int(questionnaire_id))
    return [
        _serialize_question_rule(item, question_map=question_map, option_map=option_map)
        for item in repo.list_marketing_automation_question_rules(int(config_row["id"]))
    ]


def get_signup_conversion_config(*, automation_key: str = DEFAULT_SCENARIO_KEY) -> dict[str, Any]:
    defaults = _default_config_payload(automation_key=automation_key)
    row = repo.get_marketing_automation_config(automation_key)
    if not row:
        return defaults
    payload = _json_loads(row.get("config_payload_json"), default={})
    result = {
        "automation_key": _normalized_text(row.get("automation_key")) or automation_key,
        "automation_name": _normalized_text(row.get("automation_name")) or DEFAULT_AUTOMATION_NAME,
        "target_event": _normalized_text(row.get("target_event")) or DEFAULT_TARGET_EVENT,
        "channel_type": _normalized_text(row.get("channel_type")) or DEFAULT_CHANNEL_TYPE,
        "enabled": _normalized_text(row.get("status")).lower() == "active",
        "questionnaire_id": _normalize_int(payload.get("questionnaire_id"), "questionnaire_id", allow_none=True),
        "core_threshold": _normalize_int(payload.get("core_threshold"), "core_threshold", default=DEFAULT_CORE_THRESHOLD),
        "top_threshold": _normalize_int(payload.get("top_threshold"), "top_threshold", default=DEFAULT_TOP_THRESHOLD),
        "quiet_hour_start": _normalize_int(
            row.get("do_not_start_after_hour"),
            "quiet_hour_start",
            default=DEFAULT_QUIET_HOUR_START,
            minimum=0,
            maximum=23,
        ),
        "timezone": _validate_timezone(payload.get("timezone") or DEFAULT_TIMEZONE),
        "question_rules": list_signup_conversion_question_rules(automation_key=automation_key),
        "configured": True,
        "created_at": _normalized_text(row.get("created_at")),
        "updated_at": _normalized_text(row.get("updated_at")),
    }
    return result


def _normalize_question_rules(
    rules: Any,
    *,
    questionnaire_id: int,
    question_map: dict[int, dict[str, Any]],
    option_map: dict[int, dict[int, dict[str, Any]]],
) -> list[dict[str, Any]]:
    if not isinstance(rules, list):
        raise ValueError("question_rules must be an array")
    if len(rules) != REQUIRED_QUESTION_RULE_COUNT:
        raise ValueError(f"question_rules must contain exactly {REQUIRED_QUESTION_RULE_COUNT} items")
    normalized_rules: list[dict[str, Any]] = []
    seen_question_ids: set[int] = set()
    for index, item in enumerate(rules, start=1):
        if not isinstance(item, dict):
            raise ValueError("question rule must be an object")
        question_id = _normalize_int(item.get("questionnaire_question_id"), "questionnaire_question_id", minimum=1)
        assert question_id is not None
        if question_id in seen_question_ids:
            raise ValueError("question_rules cannot contain duplicate questionnaire_question_id")
        seen_question_ids.add(question_id)
        question = question_map.get(int(question_id))
        if not question:
            raise ValueError(f"question {question_id} does not belong to questionnaire {questionnaire_id}")
        if _normalized_text(question.get("type")) not in {"single_choice", "multi_choice"}:
            raise ValueError(f"question {question_id} does not support option matching")
        available_options = option_map.get(int(question_id), {})
        hit_option_ids = _normalize_option_id_list(item.get("hit_option_ids_json"))
        invalid_option_ids = [option_id for option_id in hit_option_ids if option_id not in available_options]
        if invalid_option_ids:
            raise ValueError(f"option {invalid_option_ids[0]} does not belong to question {question_id}")
        sort_order = _normalize_int(item.get("sort_order"), "sort_order", default=index, minimum=1)
        assert sort_order is not None
        normalized_rules.append(
            {
                "questionnaire_question_id": int(question_id),
                "hit_option_ids_json": hit_option_ids,
                "sort_order": int(sort_order),
                "rule_code": f"question-{question_id}",
                "rule_name": _normalized_text(question.get("title")) or f"question-{question_id}",
                "rule_payload": {"questionnaire_id": int(questionnaire_id)},
            }
        )
    normalized_rules.sort(key=lambda item: (item["sort_order"], item["questionnaire_question_id"]))
    return normalized_rules


def save_signup_conversion_config(
    payload: dict[str, Any],
    *,
    automation_key: str = DEFAULT_SCENARIO_KEY,
) -> dict[str, Any]:
    existing = get_signup_conversion_config(automation_key=automation_key)
    raw_payload = payload or {}
    questionnaire_id = _normalize_int(
        raw_payload.get("questionnaire_id", existing.get("questionnaire_id")),
        "questionnaire_id",
        minimum=1,
    )
    assert questionnaire_id is not None
    core_threshold = _normalize_int(
        raw_payload.get("core_threshold", existing.get("core_threshold")),
        "core_threshold",
        default=DEFAULT_CORE_THRESHOLD,
        minimum=0,
    )
    top_threshold = _normalize_int(
        raw_payload.get("top_threshold", existing.get("top_threshold")),
        "top_threshold",
        default=DEFAULT_TOP_THRESHOLD,
        minimum=0,
    )
    assert core_threshold is not None
    assert top_threshold is not None
    if top_threshold < core_threshold:
        raise ValueError("top_threshold must be >= core_threshold")
    quiet_hour_start = _normalize_int(
        raw_payload.get("quiet_hour_start", existing.get("quiet_hour_start")),
        "quiet_hour_start",
        default=DEFAULT_QUIET_HOUR_START,
        minimum=0,
        maximum=23,
    )
    assert quiet_hour_start is not None
    timezone = _validate_timezone(raw_payload.get("timezone", existing.get("timezone")))
    enabled = _normalize_bool(raw_payload.get("enabled", existing.get("enabled")), default=True)
    _, question_map, option_map = _questionnaire_lookup(int(questionnaire_id))
    question_rules = _normalize_question_rules(
        raw_payload.get("question_rules", existing.get("question_rules")),
        questionnaire_id=int(questionnaire_id),
        question_map=question_map,
        option_map=option_map,
    )
    db = get_db()
    try:
        row = repo.upsert_marketing_automation_config(
            automation_key=automation_key,
            automation_name=DEFAULT_AUTOMATION_NAME,
            target_event=DEFAULT_TARGET_EVENT,
            channel_type=DEFAULT_CHANNEL_TYPE,
            status="active" if enabled else "disabled",
            do_not_start_after_hour=int(quiet_hour_start),
            config_payload={
                "questionnaire_id": int(questionnaire_id),
                "core_threshold": int(core_threshold),
                "top_threshold": int(top_threshold),
                "timezone": timezone,
            },
        )
        repo.replace_marketing_automation_question_rules(
            automation_config_id=int(row["id"]),
            questionnaire_id=int(questionnaire_id),
            rules=question_rules,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return get_signup_conversion_config(automation_key=automation_key)


def _matched_question_rule_items(
    config: dict[str, Any],
    *,
    matched_question_ids: list[int],
) -> list[dict[str, Any]]:
    matched_question_id_set = {
        int(question_id)
        for question_id in matched_question_ids
        if str(question_id).strip()
    }
    if not matched_question_id_set:
        return []
    items: list[dict[str, Any]] = []
    for rule in config.get("question_rules") or []:
        question_id = int(rule.get("questionnaire_question_id") or 0)
        if question_id <= 0 or question_id not in matched_question_id_set:
            continue
        items.append(
            {
                "questionnaire_question_id": question_id,
                "question_title": _normalized_text(rule.get("question_title")),
                "hit_option_ids_json": [
                    int(option_id)
                    for option_id in rule.get("hit_option_ids_json") or []
                    if str(option_id).strip()
                ],
                "hit_options": [dict(item) for item in rule.get("hit_options") or [] if isinstance(item, dict)],
                "sort_order": int(rule.get("sort_order") or 0),
            }
        )
    return items


def _preview_ineligible_reason(marketing_state: dict[str, Any]) -> str:
    if bool(marketing_state.get("eligible_for_conversion")):
        return ""
    return (
        _normalized_text(marketing_state.get("exit_reason"))
        or _normalized_text(marketing_state.get("sub_stage"))
        or "not_eligible"
    )


def preview_signup_conversion_customer(
    *,
    external_userid: str = "",
    person_id: int | None = None,
    automation_key: str = DEFAULT_SCENARIO_KEY,
    persist: bool = True,
) -> dict[str, Any]:
    normalized_person_id = _normalize_int(person_id, "person_id", allow_none=True)
    normalized_external_userid = _normalized_text(external_userid)
    if not normalized_external_userid and normalized_person_id is None:
        raise ValueError("external_userid or person_id is required")

    config = get_signup_conversion_config(automation_key=automation_key)
    marketing_state_lookup: dict[str, Any]
    if normalized_person_id is not None:
        marketing_state_lookup = {"person_id": int(normalized_person_id)}
    else:
        marketing_state_lookup = {"external_userid": normalized_external_userid}

    marketing_state = evaluate_customer_marketing_state(
        automation_key=automation_key,
        persist=persist,
        **marketing_state_lookup,
    )

    value_segment_lookup: dict[str, Any]
    if marketing_state.get("person_id") is not None:
        value_segment_lookup = {"person_id": int(marketing_state["person_id"])}
    else:
        value_segment_lookup = {"external_userid": _normalized_text(marketing_state.get("external_userid")) or normalized_external_userid}
    value_segment = evaluate_customer_value_segment(
        automation_key=automation_key,
        persist=persist,
        **value_segment_lookup,
    )

    matched_question_ids = [
        int(question_id)
        for question_id in value_segment.get("matched_question_ids_json") or []
        if str(question_id).strip()
    ]
    matched_questions = _matched_question_rule_items(config, matched_question_ids=matched_question_ids)
    current_stage = _normalized_text(marketing_state.get("stage_key"))
    current_segment = _normalized_text(value_segment.get("segment")) or "unknown"
    return {
        "automation_key": automation_key,
        "resolved_customer": {
            "person_id": marketing_state.get("person_id"),
            "external_userid": _normalized_text(marketing_state.get("external_userid"))
            or _normalized_text(value_segment.get("external_userid")),
            "mobile": _normalized_text(((marketing_state.get("state_payload") or {}).get("mobile"))),
            "bound_external_userids": list(marketing_state.get("bound_external_userids") or []),
        },
        "config_snapshot": {
            "enabled": bool(config.get("enabled")),
            "configured": bool(config.get("configured")),
            "questionnaire_id": _normalize_int(config.get("questionnaire_id"), "questionnaire_id", allow_none=True),
            "core_threshold": int(config.get("core_threshold") or DEFAULT_CORE_THRESHOLD),
            "top_threshold": int(config.get("top_threshold") or DEFAULT_TOP_THRESHOLD),
            "quiet_hour_start": int(config.get("quiet_hour_start") or DEFAULT_QUIET_HOUR_START),
            "timezone": _normalized_text(config.get("timezone")) or DEFAULT_TIMEZONE,
        },
        "summary": {
            "current_stage": current_stage,
            "current_stage_label": _normalized_text(marketing_state.get("stage_label")),
            "current_segment": current_segment,
            "current_segment_label": _normalized_text(value_segment.get("segment_label")) or _VALUE_SEGMENT_LABELS.get(current_segment, ""),
            "matched_question_ids": matched_question_ids,
            "matched_questions": matched_questions,
            "hit_count": int(value_segment.get("hit_count") or 0),
            "eligible": bool(marketing_state.get("eligible_for_conversion")),
            "eligible_for_conversion": bool(marketing_state.get("eligible_for_conversion")),
            "ineligible_reason": _preview_ineligible_reason(marketing_state),
        },
        "marketing_state": marketing_state,
        "value_segment": value_segment,
    }


def _normalize_recompute_targets(
    *,
    external_userid: str = "",
    person_id: int | None = None,
    external_userids: list[Any] | None = None,
    person_ids: list[Any] | None = None,
) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def _add_external(value: Any) -> None:
        normalized = _normalized_text(value)
        if not normalized:
            return
        key = ("external_userid", normalized)
        if key in seen:
            return
        seen.add(key)
        targets.append({"external_userid": normalized, "person_id": None})

    def _add_person(value: Any) -> None:
        normalized = _normalize_int(value, "person_id", allow_none=True)
        if normalized is None:
            return
        key = ("person_id", str(int(normalized)))
        if key in seen:
            return
        seen.add(key)
        targets.append({"external_userid": "", "person_id": int(normalized)})

    _add_external(external_userid)
    _add_person(person_id)
    if external_userids:
        for item in external_userids:
            _add_external(item)
    if person_ids:
        for item in person_ids:
            _add_person(item)
    if not targets:
        raise ValueError("external_userid or person_id is required")
    return targets


def recompute_signup_conversion_customers(
    *,
    external_userid: str = "",
    person_id: int | None = None,
    external_userids: list[Any] | None = None,
    person_ids: list[Any] | None = None,
    automation_key: str = DEFAULT_SCENARIO_KEY,
    persist: bool = True,
) -> dict[str, Any]:
    targets = _normalize_recompute_targets(
        external_userid=external_userid,
        person_id=person_id,
        external_userids=external_userids,
        person_ids=person_ids,
    )
    items: list[dict[str, Any]] = []
    for target in targets:
        preview = preview_signup_conversion_customer(
            external_userid=_normalized_text(target.get("external_userid")),
            person_id=_normalize_int(target.get("person_id"), "person_id", allow_none=True),
            automation_key=automation_key,
            persist=persist,
        )
        preview["history_refresh"] = {
            "marketing_state_history_written": bool((preview.get("marketing_state") or {}).get("history_written")),
            "value_segment_history_written": bool((preview.get("value_segment") or {}).get("history_written")),
        }
        items.append(preview)
    result = {
        "automation_key": automation_key,
        "mode": "single" if len(items) == 1 else "batch",
        "count": len(items),
        "items": items,
    }
    if len(items) == 1:
        result["item"] = items[0]
    return result


def _value_segment_config_ready(config: dict[str, Any]) -> bool:
    return bool(
        config.get("configured")
        and config.get("enabled")
        and config.get("questionnaire_id")
        and len(config.get("question_rules") or []) == REQUIRED_QUESTION_RULE_COUNT
    )


def _serialize_current_customer_value_segment(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    segment = _normalized_text(row.get("segment")) or "unknown"
    raw_matched_question_ids = _json_loads(row.get("matched_question_ids_json"), default=[])
    if not isinstance(raw_matched_question_ids, list):
        raw_matched_question_ids = []
    matched_question_ids = [
        int(item)
        for item in raw_matched_question_ids
        if str(item).strip()
    ]
    return {
        "id": int(row.get("id") or 0),
        "external_userid": _normalized_text(row.get("external_userid")),
        "segment": segment,
        "segment_label": _VALUE_SEGMENT_LABELS.get(segment, segment),
        "segment_rank": int(row.get("segment_rank") or _segment_rank(segment)),
        "score": int(row.get("score") or 0),
        "hit_count": int(row.get("score") or 0),
        "scoring_version": _normalized_text(row.get("scoring_version")) or VALUE_SEGMENT_SCORING_VERSION,
        "computed_reason": _normalized_text(row.get("computed_reason")),
        "submission_id": _normalize_int(row.get("submission_id"), "submission_id", allow_none=True),
        "matched_question_ids_json": matched_question_ids,
        "evaluated_at": _normalized_text(row.get("evaluated_at")) or _normalized_text(row.get("computed_at")),
        "source_payload": _json_loads(row.get("source_payload_json"), default={}),
        "is_core": segment in {"core", "top"},
        "is_top": segment == "top",
        "updated_at": _normalized_text(row.get("updated_at")),
    }


def _normalize_answer_option_ids(value: Any) -> set[int]:
    raw_value = _json_loads(value, default=[])
    if not isinstance(raw_value, list):
        return set()
    return {
        int(item)
        for item in raw_value
        if str(item).strip()
    }


def _resolve_value_segment_target(
    *,
    external_userid: str,
    person_id: int | None,
) -> dict[str, Any]:
    normalized_external_userid = _normalized_text(external_userid)
    normalized_person_id = _normalize_int(person_id, "person_id", allow_none=True)
    external_userids: list[str] = []
    mobile = ""
    if normalized_external_userid:
        external_userids = [normalized_external_userid]
    elif normalized_person_id is not None:
        external_userids = repo.list_external_userids_by_person(int(normalized_person_id))
        mobile = repo.get_person_mobile(int(normalized_person_id))
        normalized_external_userid = external_userids[0] if external_userids else ""
    else:
        raise ValueError("external_userid or person_id is required")
    return {
        "external_userid": normalized_external_userid,
        "external_userids": external_userids,
        "person_id": normalized_person_id,
        "mobile": mobile,
    }


def _resolve_latest_value_segment_submission(
    questionnaire_id: int,
    *,
    target: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    submission = repo.get_latest_questionnaire_submission_for_value_segment(
        int(questionnaire_id),
        external_userids=target.get("external_userids") or [target["external_userid"]],
        mobile_snapshot=_normalized_text(target.get("mobile")),
    )
    if not submission:
        return None, []
    answers = repo.list_questionnaire_submission_answers(int(submission["id"]))
    if not answers:
        return None, []
    return submission, answers


def _compute_submission_hit_result(
    *,
    config: dict[str, Any],
    submission: dict[str, Any] | None,
    answers: list[dict[str, Any]],
) -> dict[str, Any]:
    if not submission or not answers:
        return {
            "segment": "unknown",
            "hit_count": 0,
            "matched_question_ids": [],
            "submission_id": None,
            "computed_reason": "no_valid_submission",
        }
    answers_by_question: dict[int, set[int]] = {}
    for item in answers:
        question_id = int(item.get("question_id") or 0)
        if question_id <= 0:
            continue
        answers_by_question.setdefault(question_id, set()).update(_normalize_answer_option_ids(item.get("selected_option_ids")))
    matched_question_ids: list[int] = []
    for rule in config.get("question_rules") or []:
        question_id = int(rule.get("questionnaire_question_id") or 0)
        configured_option_ids = {int(option_id) for option_id in rule.get("hit_option_ids_json") or []}
        if question_id <= 0 or not configured_option_ids:
            continue
        if answers_by_question.get(question_id, set()) & configured_option_ids:
            matched_question_ids.append(question_id)
    hit_count = len(matched_question_ids)
    top_threshold = int(config.get("top_threshold") or DEFAULT_TOP_THRESHOLD)
    core_threshold = int(config.get("core_threshold") or DEFAULT_CORE_THRESHOLD)
    if hit_count >= top_threshold:
        segment = "top"
    elif hit_count >= core_threshold:
        segment = "core"
    else:
        segment = "normal"
    return {
        "segment": segment,
        "hit_count": hit_count,
        "matched_question_ids": matched_question_ids,
        "submission_id": int(submission["id"]),
        "computed_reason": f"hit_count={hit_count};core_threshold={core_threshold};top_threshold={top_threshold}",
    }


def evaluate_customer_value_segment(
    *,
    external_userid: str = "",
    person_id: int | None = None,
    automation_key: str = DEFAULT_SCENARIO_KEY,
    persist: bool = True,
) -> dict[str, Any]:
    target = _resolve_value_segment_target(external_userid=external_userid, person_id=person_id)
    config = get_signup_conversion_config(automation_key=automation_key)
    evaluated_at = _iso_now()
    questionnaire_id = _normalize_int(config.get("questionnaire_id"), "questionnaire_id", allow_none=True)
    if not _normalized_text(target.get("external_userid")):
        result = {
            "external_userid": "",
            "person_id": target.get("person_id"),
            "questionnaire_id": questionnaire_id,
            "segment": "unknown",
            "segment_label": _VALUE_SEGMENT_LABELS["unknown"],
            "segment_rank": _segment_rank("unknown"),
            "score": 0,
            "hit_count": 0,
            "submission_id": None,
            "matched_question_ids_json": [],
            "evaluated_at": evaluated_at,
            "scoring_version": VALUE_SEGMENT_SCORING_VERSION,
            "computed_reason": "missing_external_userid",
            "source_payload": {
                "automation_key": automation_key,
                "person_id": target.get("person_id"),
                "mobile": _normalized_text(target.get("mobile")),
            },
            "is_core": False,
            "is_top": False,
            "history_written": False,
        }
        return result
    if not _value_segment_config_ready(config) or questionnaire_id is None:
        result = {
            "external_userid": target["external_userid"],
            "person_id": target.get("person_id"),
            "questionnaire_id": questionnaire_id,
            "segment": "unknown",
            "segment_label": _VALUE_SEGMENT_LABELS["unknown"],
            "segment_rank": _segment_rank("unknown"),
            "score": 0,
            "hit_count": 0,
            "submission_id": None,
            "matched_question_ids_json": [],
            "evaluated_at": evaluated_at,
            "scoring_version": VALUE_SEGMENT_SCORING_VERSION,
            "computed_reason": "automation_config_not_ready",
            "source_payload": {"automation_key": automation_key, "config_enabled": bool(config.get("enabled"))},
            "is_core": False,
            "is_top": False,
        }
    else:
        submission, answers = _resolve_latest_value_segment_submission(int(questionnaire_id), target=target)
        evaluated = _compute_submission_hit_result(config=config, submission=submission, answers=answers)
        segment = evaluated["segment"]
        result = {
            "external_userid": target["external_userid"],
            "person_id": target.get("person_id"),
            "questionnaire_id": int(questionnaire_id),
            "segment": segment,
            "segment_label": _VALUE_SEGMENT_LABELS[segment],
            "segment_rank": _segment_rank(segment),
            "score": int(evaluated["hit_count"]),
            "hit_count": int(evaluated["hit_count"]),
            "submission_id": evaluated["submission_id"],
            "matched_question_ids_json": list(evaluated["matched_question_ids"]),
            "evaluated_at": evaluated_at,
            "scoring_version": VALUE_SEGMENT_SCORING_VERSION,
            "computed_reason": _normalized_text(evaluated["computed_reason"]),
            "source_payload": {
                "automation_key": automation_key,
                "questionnaire_id": int(questionnaire_id),
                "core_threshold": int(config.get("core_threshold") or DEFAULT_CORE_THRESHOLD),
                "top_threshold": int(config.get("top_threshold") or DEFAULT_TOP_THRESHOLD),
                "latest_submission_external_userid": _normalized_text((submission or {}).get("external_userid")),
                "latest_submission_submitted_at": _normalized_text((submission or {}).get("submitted_at")),
                "person_id": target.get("person_id"),
            },
            "is_core": segment in {"core", "top"},
            "is_top": segment == "top",
        }

    if not persist:
        result["person_id"] = target.get("person_id")
        result["questionnaire_id"] = questionnaire_id
        result["history_written"] = False
        return result

    existing = _serialize_current_customer_value_segment(repo.get_customer_value_segment_current(target["external_userid"]))
    db = get_db()
    history_written = False
    try:
        if not existing or _normalized_text(existing.get("segment")) != result["segment"]:
            repo.insert_customer_value_segment_history(
                external_userid=target["external_userid"],
                segment=result["segment"],
                segment_rank=int(result["segment_rank"]),
                score=int(result["score"]),
                scoring_version=result["scoring_version"],
                change_reason="initial_compute" if not existing else "segment_changed",
                submission_id=result["submission_id"],
                matched_question_ids=result["matched_question_ids_json"],
                source_payload=result["source_payload"],
                evaluated_at=result["evaluated_at"],
            )
            history_written = True
        current = repo.upsert_customer_value_segment_current(
            external_userid=target["external_userid"],
            segment=result["segment"],
            segment_rank=int(result["segment_rank"]),
            score=int(result["score"]),
            scoring_version=result["scoring_version"],
            computed_reason=result["computed_reason"],
            submission_id=result["submission_id"],
            matched_question_ids=result["matched_question_ids_json"],
            source_payload=result["source_payload"],
            evaluated_at=result["evaluated_at"],
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    serialized_current = _serialize_current_customer_value_segment(current) or result
    serialized_current["person_id"] = target.get("person_id")
    serialized_current["questionnaire_id"] = questionnaire_id
    serialized_current["history_written"] = history_written
    return serialized_current


def _is_signup_success(signup_status: str) -> bool:
    normalized = _normalized_text(signup_status).lower()
    return any(normalized.startswith(prefix) for prefix in _EXIT_SIGNUP_PREFIXES)


def _normalize_text_list(value: Any) -> list[str]:
    raw_items = value if isinstance(value, list) else _json_loads(value, default=[])
    if not isinstance(raw_items, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        text = _normalized_text(item)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _latest_timestamp(*values: Any) -> str:
    candidates = [_normalized_text(value) for value in values if _normalized_text(value)]
    return max(candidates) if candidates else ""


def _serialize_current_customer_marketing_state(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    payload = _json_loads(row.get("state_payload_json"), default={})
    if not isinstance(payload, dict):
        payload = {}
    stored_external_userid = _normalized_text(row.get("external_userid"))
    resolved_external_userid = _normalized_text(payload.get("resolved_external_userid"))
    if not resolved_external_userid:
        resolved_external_userid = stored_external_userid
    bound_external_userids = _normalize_text_list(payload.get("bound_external_userids"))
    if not bound_external_userids and resolved_external_userid:
        bound_external_userids = [resolved_external_userid]
    person_id = _normalize_int(
        row.get("person_id") if row.get("person_id") not in (None, "") else payload.get("person_id"),
        "person_id",
        allow_none=True,
    )
    main_stage = _normalized_text(row.get("main_stage"))
    sub_stage = _normalized_text(row.get("sub_stage"))
    return {
        "id": int(row.get("id") or 0),
        "person_id": person_id,
        "storage_external_userid": stored_external_userid,
        "external_userid": resolved_external_userid,
        "bound_external_userids": bound_external_userids,
        "main_stage": main_stage,
        "sub_stage": sub_stage,
        "stage_key": f"{main_stage}/{sub_stage}" if main_stage and sub_stage else main_stage or sub_stage,
        "stage_label": _CUSTOMER_MARKETING_STATE_LABELS.get((main_stage, sub_stage), ""),
        "activated": _normalize_bool(row.get("activated")),
        "converted": _normalize_bool(row.get("converted")),
        "eligible_for_conversion": _normalize_bool(row.get("eligible_for_conversion")),
        "lifecycle_status": _normalized_text(row.get("lifecycle_status")),
        "last_activation_at": _normalized_text(row.get("last_activation_at")),
        "last_conversion_marked_at": _normalized_text(row.get("last_conversion_marked_at")),
        "last_message_at": _normalized_text(row.get("last_message_at")),
        "last_batch_id": _normalize_int(row.get("last_batch_id"), "last_batch_id", allow_none=True),
        "last_batch_status": _normalized_text(row.get("last_batch_status")),
        "last_batch_window_start": _normalized_text(row.get("last_batch_window_start")),
        "last_batch_window_end": _normalized_text(row.get("last_batch_window_end")),
        "last_trigger_message_at": _normalized_text(row.get("last_trigger_message_at")),
        "entered_at": _normalized_text(row.get("entered_at")),
        "exited_at": _normalized_text(row.get("exited_at")),
        "exit_reason": _normalized_text(row.get("exit_reason")),
        "state_payload": payload,
        "updated_at": _normalized_text(row.get("updated_at")),
        "created_at": _normalized_text(row.get("created_at")),
    }


def _customer_marketing_state_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "person_id": _normalize_int(row.get("person_id"), "person_id", allow_none=True),
        "storage_external_userid": _normalized_text(row.get("storage_external_userid")),
        "external_userid": _normalized_text(row.get("external_userid")),
        "bound_external_userids": _normalize_text_list(row.get("bound_external_userids")),
        "main_stage": _normalized_text(row.get("main_stage")),
        "sub_stage": _normalized_text(row.get("sub_stage")),
        "activated": bool(row.get("activated")),
        "converted": bool(row.get("converted")),
        "eligible_for_conversion": bool(row.get("eligible_for_conversion")),
        "lifecycle_status": _normalized_text(row.get("lifecycle_status")),
        "last_activation_at": _normalized_text(row.get("last_activation_at")),
        "last_conversion_marked_at": _normalized_text(row.get("last_conversion_marked_at")),
        "last_message_at": _normalized_text(row.get("last_message_at")),
        "last_batch_id": _normalize_int(row.get("last_batch_id"), "last_batch_id", allow_none=True),
        "last_batch_status": _normalized_text(row.get("last_batch_status")),
        "last_batch_window_start": _normalized_text(row.get("last_batch_window_start")),
        "last_batch_window_end": _normalized_text(row.get("last_batch_window_end")),
        "last_trigger_message_at": _normalized_text(row.get("last_trigger_message_at")),
        "entered_at": _normalized_text(row.get("entered_at")),
        "exited_at": _normalized_text(row.get("exited_at")),
        "exit_reason": _normalized_text(row.get("exit_reason")),
        "state_payload": row.get("state_payload") or {},
    }


def _resolve_customer_marketing_state_target(
    *,
    external_userid: str,
    person_id: int | None,
) -> dict[str, Any]:
    normalized_external_userid = _normalized_text(external_userid)
    normalized_person_id = _normalize_int(person_id, "person_id", allow_none=True)
    external_userids: list[str] = []
    mobile = ""
    if normalized_person_id is not None:
        external_userids = repo.list_external_userids_by_person(int(normalized_person_id))
        mobile = repo.get_person_mobile(int(normalized_person_id))
        if not mobile and not external_userids:
            raise LookupError("person not found")
    elif normalized_external_userid:
        binding = repo.get_binding_snapshot_for_external_userid(normalized_external_userid) or {}
        if binding:
            normalized_person_id = int(binding["person_id"])
            external_userids = repo.list_external_userids_by_person(int(normalized_person_id))
            mobile = _normalized_text(binding.get("mobile")) or repo.get_person_mobile(int(normalized_person_id))
        elif repo.has_live_external_userid(normalized_external_userid):
            external_userids = [normalized_external_userid]
            mobile = repo.get_signal_mobile_for_external_userid(normalized_external_userid)
        else:
            mobile = repo.get_signal_mobile_for_external_userid(normalized_external_userid)
    else:
        raise ValueError("external_userid or person_id is required")

    deduped_external_userids: list[str] = []
    seen_external_userids: set[str] = set()
    for item in external_userids or ([normalized_external_userid] if normalized_external_userid else []):
        normalized_item = _normalized_text(item)
        if not normalized_item or normalized_item in seen_external_userids:
            continue
        seen_external_userids.add(normalized_item)
        deduped_external_userids.append(normalized_item)

    primary_external_userid = deduped_external_userids[0] if deduped_external_userids else ""
    return {
        "person_id": normalized_person_id,
        "external_userid": primary_external_userid,
        "external_userids": deduped_external_userids,
        "mobile": _normalized_text(mobile),
    }


def _latest_converted_signal(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for row in rows:
        signup_status = _normalized_text(row.get("signup_status"))
        if not _is_signup_success(signup_status):
            continue
        candidates.append(
            {
                "external_userid": _normalized_text(row.get("external_userid")),
                "signup_status": signup_status,
                "signal_at": _latest_timestamp(row.get("set_at"), row.get("updated_at"), row.get("created_at")),
            }
        )
    if not candidates:
        return None
    candidates.sort(
        key=lambda item: (
            item["signal_at"],
            item["external_userid"],
        ),
        reverse=True,
    )
    return candidates[0]


def _latest_activation_signal(
    *,
    lead_pool_rows: list[dict[str, Any]],
    activation_source_row: dict[str, Any] | None,
) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for row in lead_pool_rows:
        if _normalized_text(row.get("huangxiaocan_activation_state")) != "activated":
            continue
        candidates.append(
            {
                "signal_source": "lead_pool_current",
                "external_userid": _normalized_text(row.get("external_userid")),
                "mobile": _normalized_text(row.get("mobile")),
                "signal_at": _latest_timestamp(row.get("updated_at"), row.get("created_at")),
            }
        )
    if activation_source_row and _normalize_bool(activation_source_row.get("is_active"), default=True):
        if _normalized_text(activation_source_row.get("activation_state")) == "activated":
            candidates.append(
                {
                    "signal_source": "huangxiaocan_activation_source",
                    "external_userid": "",
                    "mobile": _normalized_text(activation_source_row.get("mobile")),
                    "signal_at": _latest_timestamp(
                        activation_source_row.get("updated_at"),
                        activation_source_row.get("created_at"),
                    ),
                }
            )
    if not candidates:
        return None
    candidates.sort(
        key=lambda item: (
            item["signal_at"],
            item["signal_source"],
            item["external_userid"],
        ),
        reverse=True,
    )
    return candidates[0]


def evaluate_customer_marketing_state(
    *,
    external_userid: str = "",
    person_id: int | None = None,
    automation_key: str = DEFAULT_SCENARIO_KEY,
    state_payload_overrides: dict[str, Any] | None = None,
    history_change_reason: str = "",
    persist: bool = True,
) -> dict[str, Any]:
    target = _resolve_customer_marketing_state_target(external_userid=external_userid, person_id=person_id)
    stored_external_userid = _normalized_text(target.get("external_userid"))
    existing = _serialize_current_customer_marketing_state(
        repo.get_customer_marketing_state_current(
            external_userid=stored_external_userid,
            person_id=target.get("person_id"),
        )
    )
    class_status_rows = repo.list_class_status_rows(target.get("external_userids") or [])
    converted_signal = _latest_converted_signal(class_status_rows)
    lead_pool_rows = repo.list_user_ops_lead_pool_rows_for_marketing_state(
        external_userids=target.get("external_userids") or [],
        mobile=_normalized_text(target.get("mobile")),
    )
    activation_source_row = repo.get_huangxiaocan_activation_source_by_mobile(_normalized_text(target.get("mobile")))
    activation_signal = _latest_activation_signal(
        lead_pool_rows=lead_pool_rows,
        activation_source_row=activation_source_row,
    )
    activated = activation_signal is not None
    converted = converted_signal is not None
    last_activation_at = _normalized_text((activation_signal or {}).get("signal_at"))
    last_conversion_marked_at = _normalized_text((converted_signal or {}).get("signal_at"))
    last_message_at = repo.get_latest_message_at_for_external_userids(target.get("external_userids") or [])
    has_external_userid = bool(target.get("external_userids"))
    has_mobile = bool(_normalized_text(target.get("mobile")))

    if converted:
        main_stage = "converted"
        sub_stage = "enrolled"
        lifecycle_status = "converted"
        eligible_for_conversion = False
        exit_reason = "enrolled"
    elif has_mobile and not has_external_userid:
        main_stage = "prospect"
        sub_stage = "mobile_only"
        lifecycle_status = "prospect"
        eligible_for_conversion = False
        exit_reason = "missing_external_userid"
    elif activated:
        main_stage = "active"
        sub_stage = "activated"
        lifecycle_status = "active"
        eligible_for_conversion = True
        exit_reason = ""
    elif has_external_userid:
        main_stage = "prospect"
        sub_stage = "wecom_connected"
        lifecycle_status = "prospect"
        eligible_for_conversion = True
        exit_reason = ""
    else:
        raise LookupError("customer marketing state target has neither mobile nor external_userid")

    stage_key = f"{main_stage}/{sub_stage}"
    signal_reference_at = (
        last_conversion_marked_at
        if converted
        else last_activation_at
        if main_stage == "active"
        else last_message_at
    )
    entered_at = _normalized_text((existing or {}).get("entered_at"))
    if _normalized_text((existing or {}).get("stage_key")) != stage_key:
        entered_at = signal_reference_at or _iso_now()
    exited_at = last_conversion_marked_at if main_stage == "converted" else ""
    state_payload = {
        "person_id": target.get("person_id"),
        "mobile": _normalized_text(target.get("mobile")),
        "resolved_external_userid": _normalized_text(target.get("external_userid")),
        "bound_external_userids": sorted(_normalize_text_list(target.get("external_userids") or [])),
        "activated_signal_source": _normalized_text((activation_signal or {}).get("signal_source")),
        "activated_signal_external_userid": _normalized_text((activation_signal or {}).get("external_userid")),
        "converted_external_userid": _normalized_text((converted_signal or {}).get("external_userid")),
        "converted_signup_status": _normalized_text((converted_signal or {}).get("signup_status")),
    }
    if state_payload_overrides:
        state_payload.update(dict(state_payload_overrides))
    result = {
        "person_id": target.get("person_id"),
        "storage_external_userid": stored_external_userid,
        "external_userid": _normalized_text(target.get("external_userid")),
        "bound_external_userids": state_payload["bound_external_userids"],
        "main_stage": main_stage,
        "sub_stage": sub_stage,
        "stage_key": stage_key,
        "stage_label": _CUSTOMER_MARKETING_STATE_LABELS.get((main_stage, sub_stage), ""),
        "activated": activated,
        "converted": converted,
        "eligible_for_conversion": eligible_for_conversion,
        "lifecycle_status": lifecycle_status,
        "last_activation_at": last_activation_at,
        "last_conversion_marked_at": last_conversion_marked_at,
        "last_message_at": last_message_at,
        "last_batch_id": (existing or {}).get("last_batch_id"),
        "last_batch_status": _normalized_text((existing or {}).get("last_batch_status")),
        "last_batch_window_start": _normalized_text((existing or {}).get("last_batch_window_start")),
        "last_batch_window_end": _normalized_text((existing or {}).get("last_batch_window_end")),
        "last_trigger_message_at": _normalized_text((existing or {}).get("last_trigger_message_at")) or last_message_at,
        "entered_at": entered_at,
        "exited_at": exited_at,
        "exit_reason": exit_reason,
        "state_payload": state_payload,
    }

    if not persist:
        result["history_written"] = False
        return result

    existing_snapshot = _customer_marketing_state_snapshot(existing or {}) if existing else None
    result_snapshot = _customer_marketing_state_snapshot(result)
    history_written = False
    db = get_db()
    try:
        if existing_snapshot != result_snapshot:
            repo.insert_customer_marketing_state_history(
                external_userid=stored_external_userid,
                person_id=target.get("person_id"),
                automation_key=automation_key,
                main_stage=main_stage,
                sub_stage=sub_stage,
                activated=activated,
                converted=converted,
                eligible_for_conversion=eligible_for_conversion,
                batch_id=result.get("last_batch_id"),
                lifecycle_status=lifecycle_status,
                exit_reason=exit_reason,
                last_activation_at=last_activation_at,
                last_conversion_marked_at=last_conversion_marked_at,
                last_message_at=last_message_at,
                change_reason="initial_compute" if not existing else (_normalized_text(history_change_reason) or "state_changed"),
                state_payload=state_payload,
            )
            history_written = True
        current = repo.upsert_customer_marketing_state_current(
            external_userid=stored_external_userid,
            person_id=target.get("person_id"),
            automation_key=automation_key,
            main_stage=main_stage,
            sub_stage=sub_stage,
            activated=activated,
            converted=converted,
            eligible_for_conversion=eligible_for_conversion,
            lifecycle_status=lifecycle_status,
            last_activation_at=last_activation_at,
            last_conversion_marked_at=last_conversion_marked_at,
            last_message_at=last_message_at,
            last_batch_id=result.get("last_batch_id"),
            last_batch_status=result.get("last_batch_status", ""),
            last_batch_window_start=result.get("last_batch_window_start", ""),
            last_batch_window_end=result.get("last_batch_window_end", ""),
            last_trigger_message_at=result.get("last_trigger_message_at", ""),
            entered_at=entered_at,
            exited_at=exited_at,
            exit_reason=exit_reason,
            state_payload=state_payload,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    serialized = _serialize_current_customer_marketing_state(current) or result
    serialized["history_written"] = history_written
    return serialized


def _normalize_conversion_source(value: Any, *, default: str) -> str:
    return _normalized_text(value) or default


def _normalize_enrolled_signup_status(value: Any) -> str:
    normalized = _normalized_text(value) or DEFAULT_ENROLLED_SIGNUP_STATUS
    definition = get_class_user_status_definition(normalized)
    if not definition or not _is_signup_success(normalized):
        raise ValueError("signup_status must be an enrolled status")
    return normalized


def _restore_signup_status_for_unmark(external_userid: str, *, restore_signup_status: str = "") -> str:
    normalized_restore_signup_status = _normalized_text(restore_signup_status)
    if normalized_restore_signup_status:
        definition = get_class_user_status_definition(normalized_restore_signup_status)
        if not definition:
            raise ValueError("restore_signup_status is invalid")
        if _is_signup_success(normalized_restore_signup_status):
            raise ValueError("restore_signup_status must be a non-enrolled status")
        return normalized_restore_signup_status
    restore_row = repo.get_latest_class_user_restore_status(external_userid) or {}
    restored = _normalized_text(restore_row.get("old_signup_status"))
    if restored and get_class_user_status_definition(restored) and not _is_signup_success(restored):
        return restored
    return ""


def _build_class_user_snapshot_for_conversion(
    external_userid: str,
    *,
    owner_userid: str = "",
) -> dict[str, str]:
    current = get_class_user_status_current(external_userid) or {}
    base = repo.load_customer_marketing_base(external_userid)
    if not _normalized_text(base.get("external_userid")) and not current:
        raise LookupError("customer not found")
    normalized_owner_userid = (
        _normalized_text(owner_userid)
        or _normalized_text(current.get("owner_userid_snapshot"))
        or _normalized_text(base.get("owner_userid"))
    )
    return {
        "customer_name_snapshot": _normalized_text(current.get("customer_name_snapshot"))
        or _normalized_text(base.get("customer_name"))
        or external_userid,
        "owner_userid_snapshot": normalized_owner_userid,
        "mobile_snapshot": _normalized_text(current.get("mobile_snapshot")) or _normalized_text(base.get("mobile")),
    }


def _list_pending_conversion_candidate_batch_ids(
    external_userid: str,
    *,
    scenario_key: str,
) -> list[int]:
    from ..archive.service import list_message_batches, materialize_message_batches

    normalized_external_userid = _normalized_text(external_userid)
    if not normalized_external_userid:
        return []
    materialize_message_batches(window_minutes=3)
    cursor = ""
    batch_ids: list[int] = []
    seen_batch_ids: set[int] = set()
    while True:
        page = list_message_batches(status="pending", limit=200, cursor=cursor)
        items = page.get("items") or []
        for batch in items:
            batch_id = int(batch.get("id") or 0)
            if not batch_id or batch_id in seen_batch_ids:
                continue
            detail = get_signup_conversion_batch(batch_id, scenario_key=scenario_key)
            if not detail:
                continue
            candidate_external_userids = {
                _normalized_text(item.get("external_userid"))
                for item in detail.get("candidates") or []
                if _normalized_text(item.get("external_userid"))
            }
            if normalized_external_userid in candidate_external_userids:
                seen_batch_ids.add(batch_id)
                batch_ids.append(batch_id)
        cursor = _normalized_text(page.get("next_cursor"))
        if not cursor:
            break
    return batch_ids


def _cancel_pending_conversion_dispatches(
    *,
    external_userid: str,
    batch_ids: list[int],
    operator: str,
    source: str,
    scenario_key: str,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    normalized_external_userid = _normalized_text(external_userid)
    normalized_operator = _normalized_text(operator)
    normalized_source = _normalized_text(source)
    for batch_id in batch_ids:
        existing = repo.get_conversion_dispatch_log(int(batch_id), normalized_external_userid) or {}
        existing_status = _normalized_text(existing.get("dispatch_status"))
        dispatch_status = (
            "converted_before_dispatch"
            if existing_status in {"", "pending", "converted_before_dispatch"}
            else "cancelled"
        )
        row = repo.upsert_conversion_dispatch_log(
            automation_key=scenario_key,
            batch_id=int(batch_id),
            external_userid=normalized_external_userid,
            dispatch_status=dispatch_status,
            dispatch_channel="text_message",
            dispatch_payload={
                "action": "mark_enrolled",
                "operator": normalized_operator,
                "source": normalized_source,
                "previous_dispatch_status": existing_status,
            },
            dispatch_note=f"conversion marked by {normalized_source or 'unknown'}",
        )
        if row:
            results.append(row)
    return results


def mark_enrolled(
    *,
    external_userid: str,
    owner_userid: str = "",
    operator: str = "",
    source: str = "manual",
    signup_status: str = DEFAULT_ENROLLED_SIGNUP_STATUS,
    automation_key: str = DEFAULT_SCENARIO_KEY,
) -> dict[str, Any]:
    normalized_external_userid = _normalized_text(external_userid)
    if not normalized_external_userid:
        raise ValueError("external_userid is required")
    normalized_source = _normalize_conversion_source(source, default="manual")
    normalized_signup_status = _normalize_enrolled_signup_status(signup_status)
    snapshot = _build_class_user_snapshot_for_conversion(
        normalized_external_userid,
        owner_userid=owner_userid,
    )
    normalized_operator = _normalized_text(operator) or _normalized_text(snapshot.get("owner_userid_snapshot")) or normalized_source
    pending_candidate_batch_ids = _list_pending_conversion_candidate_batch_ids(
        normalized_external_userid,
        scenario_key=automation_key,
    )
    current_class_status = get_class_user_status_current(normalized_external_userid) or {}
    if _normalized_text(current_class_status.get("signup_status")) != normalized_signup_status:
        current_class_status = apply_class_user_status_change(
            external_userid=normalized_external_userid,
            signup_status=normalized_signup_status,
            set_by_userid=normalized_operator,
            customer_name_snapshot=_normalized_text(snapshot.get("customer_name_snapshot")) or normalized_external_userid,
            owner_userid_snapshot=_normalized_text(snapshot.get("owner_userid_snapshot")) or normalized_operator,
            mobile_snapshot=_normalized_text(snapshot.get("mobile_snapshot")),
        )
    marketing_state = evaluate_customer_marketing_state(
        external_userid=normalized_external_userid,
        automation_key=automation_key,
        state_payload_overrides={
            "manual_conversion_operator": normalized_operator,
            "manual_conversion_source": normalized_source,
            "manual_conversion_action": "mark_enrolled",
        },
        history_change_reason="mark_enrolled",
    )
    cancelled_dispatch_logs = _cancel_pending_conversion_dispatches(
        external_userid=normalized_external_userid,
        batch_ids=pending_candidate_batch_ids,
        operator=normalized_operator,
        source=normalized_source,
        scenario_key=automation_key,
    )
    get_db().commit()
    return {
        "external_userid": normalized_external_userid,
        "signup_status": normalized_signup_status,
        "class_user_status": current_class_status,
        "marketing_state": marketing_state,
        "pending_candidate_batch_ids": pending_candidate_batch_ids,
        "cancelled_dispatches": cancelled_dispatch_logs,
        "cancelled_dispatch_count": len(cancelled_dispatch_logs),
        "operator": normalized_operator,
        "source": normalized_source,
    }


def unmark_enrolled(
    *,
    external_userid: str,
    owner_userid: str = "",
    operator: str = "",
    source: str = "manual",
    restore_signup_status: str = "",
    automation_key: str = DEFAULT_SCENARIO_KEY,
) -> dict[str, Any]:
    normalized_external_userid = _normalized_text(external_userid)
    if not normalized_external_userid:
        raise ValueError("external_userid is required")
    normalized_source = _normalize_conversion_source(source, default="manual")
    snapshot = _build_class_user_snapshot_for_conversion(
        normalized_external_userid,
        owner_userid=owner_userid,
    )
    normalized_operator = _normalized_text(operator) or _normalized_text(snapshot.get("owner_userid_snapshot")) or normalized_source
    previous_marketing_state = repo.get_customer_marketing_state_current(external_userid=normalized_external_userid)
    target_signup_status = _restore_signup_status_for_unmark(
        normalized_external_userid,
        restore_signup_status=restore_signup_status,
    )
    current_class_status = get_class_user_status_current(normalized_external_userid) or {}
    if target_signup_status and _normalized_text(current_class_status.get("signup_status")) != target_signup_status:
        current_class_status = apply_class_user_status_change(
            external_userid=normalized_external_userid,
            signup_status=target_signup_status,
            set_by_userid=normalized_operator,
            customer_name_snapshot=_normalized_text(snapshot.get("customer_name_snapshot")) or normalized_external_userid,
            owner_userid_snapshot=_normalized_text(snapshot.get("owner_userid_snapshot")) or normalized_operator,
            mobile_snapshot=_normalized_text(snapshot.get("mobile_snapshot")),
        )
    elif not target_signup_status:
        clear_class_user_status_current(
            external_userid=normalized_external_userid,
            set_by_userid=normalized_operator,
            customer_name_snapshot=_normalized_text(snapshot.get("customer_name_snapshot")) or normalized_external_userid,
            owner_userid_snapshot=_normalized_text(snapshot.get("owner_userid_snapshot")) or normalized_operator,
            mobile_snapshot=_normalized_text(snapshot.get("mobile_snapshot")),
        )
        current_class_status = {}
    marketing_state_lookup = {
        "person_id": previous_marketing_state.get("person_id")
        if isinstance(previous_marketing_state, dict)
        else None,
        "external_userid": normalized_external_userid,
    }
    if marketing_state_lookup["person_id"] is not None:
        marketing_state = evaluate_customer_marketing_state(
            person_id=int(marketing_state_lookup["person_id"]),
            automation_key=automation_key,
            state_payload_overrides={
                "manual_conversion_operator": normalized_operator,
                "manual_conversion_source": normalized_source,
                "manual_conversion_action": "unmark_enrolled",
            },
            history_change_reason="unmark_enrolled",
        )
    else:
        marketing_state = evaluate_customer_marketing_state(
            external_userid=normalized_external_userid,
            automation_key=automation_key,
            state_payload_overrides={
                "manual_conversion_operator": normalized_operator,
                "manual_conversion_source": normalized_source,
                "manual_conversion_action": "unmark_enrolled",
            },
            history_change_reason="unmark_enrolled",
        )
    return {
        "external_userid": normalized_external_userid,
        "signup_status": target_signup_status,
        "class_user_status": current_class_status,
        "marketing_state": marketing_state,
        "operator": normalized_operator,
        "source": normalized_source,
    }


def _dedupe_tag_names(base: dict[str, Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for tag in base.get("tags") or []:
        tag_name = _normalized_text((tag or {}).get("tag_name") or (tag or {}).get("tag_id"))
        if not tag_name or tag_name in seen:
            continue
        seen.add(tag_name)
        result.append(tag_name)
    signup_label_name = _normalized_text(base.get("signup_label_name"))
    if signup_label_name and signup_label_name not in seen:
        result.append(signup_label_name)
    return result


def _compute_value_segment(base: dict[str, Any], *, config: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now()
    score = 0
    score_breakdown: dict[str, int] = {}

    if bool(base.get("is_bound")):
        score_breakdown["mobile_bound"] = 25
        score += 25
    if int(base.get("questionnaire_submission_count") or 0) > 0:
        score_breakdown["questionnaire_submitted"] = 20
        score += 20
    if _normalized_text(base.get("owner_userid")):
        score_breakdown["owner_assigned"] = 5
        score += 5

    tag_names = _dedupe_tag_names(base)
    if any(keyword in tag_name for tag_name in tag_names for keyword in _HIGH_INTENT_TAG_KEYWORDS):
        score_breakdown["high_intent_tags"] = 20
        score += 20

    last_customer_text_at = _parse_timestamp(base.get("last_customer_text_at"))
    if last_customer_text_at is not None:
        age_hours = (now - last_customer_text_at).total_seconds() / 3600
        if age_hours <= 6:
            score_breakdown["recent_customer_text_6h"] = 30
            score += 30
        elif age_hours <= 24:
            score_breakdown["recent_customer_text_24h"] = 20
            score += 20
        elif age_hours <= 72:
            score_breakdown["recent_customer_text_72h"] = 10
            score += 10

    top_threshold = int(config.get("top_threshold") or DEFAULT_TOP_THRESHOLD)
    core_threshold = int(config.get("core_threshold") or DEFAULT_CORE_THRESHOLD)
    if score >= top_threshold:
        value_segment = "top"
    elif score >= core_threshold:
        value_segment = "core"
    else:
        value_segment = "normal"

    return {
        "scenario_key": DEFAULT_SCENARIO_KEY,
        "external_userid": _normalized_text(base.get("external_userid")),
        "value_segment": value_segment,
        "segment_label": _VALUE_SEGMENT_LABELS[value_segment],
        "score": score,
        "score_breakdown": score_breakdown,
        "is_core": value_segment in {"core", "top"},
        "is_top": value_segment == "top",
    }


def _blocked_phase_label(quiet_hour_start: int) -> str:
    return f"{int(quiet_hour_start):02d}:00 后不启动"


def _build_state_payload(
    base: dict[str, Any],
    *,
    existing_state: dict[str, Any] | None,
    batch_context: dict[str, Any] | None,
) -> dict[str, Any]:
    now_text = _iso_now()
    if _is_signup_success(_normalized_text(base.get("signup_status"))):
        entered_at = _normalized_text((existing_state or {}).get("entered_at"))
        return {
            "marketing_phase": "exited_signup_success",
            "phase_label": _PHASE_LABELS["exited_signup_success"],
            "phase_reason": f"signup_status={_normalized_text(base.get('signup_status')) or 'unknown'}",
            "lifecycle_status": "exited",
            "last_batch_id": (existing_state or {}).get("last_batch_id"),
            "last_batch_status": _normalized_text((existing_state or {}).get("last_batch_status")),
            "last_batch_window_start": _normalized_text((existing_state or {}).get("last_batch_window_start")),
            "last_batch_window_end": _normalized_text((existing_state or {}).get("last_batch_window_end")),
            "last_trigger_message_at": _normalized_text((existing_state or {}).get("last_trigger_message_at"))
            or _normalized_text(base.get("last_customer_text_at"))
            or _normalized_text(base.get("last_message_at")),
            "entered_at": entered_at or now_text,
            "exited_at": now_text,
            "exit_reason": "signup_success",
            "source_payload": {
                "signup_status": _normalized_text(base.get("signup_status")),
                "last_customer_text_at": _normalized_text(base.get("last_customer_text_at")),
            },
        }

    if batch_context:
        existing_is_active = _normalized_text((existing_state or {}).get("lifecycle_status")) == "active"
        if bool(batch_context.get("blocked_after_quiet_hour")) and not existing_is_active:
            return {
                "marketing_phase": "blocked_after_2300",
                "phase_label": _blocked_phase_label(int(batch_context.get("quiet_hour_start") or DEFAULT_QUIET_HOUR_START)),
                "phase_reason": "window_start_after_quiet_hour",
                "lifecycle_status": "blocked",
                "last_batch_id": batch_context.get("batch_id"),
                "last_batch_status": _normalized_text(batch_context.get("batch_status")),
                "last_batch_window_start": _normalized_text(batch_context.get("window_start")),
                "last_batch_window_end": _normalized_text(batch_context.get("window_end")),
                "last_trigger_message_at": _normalized_text(batch_context.get("latest_customer_message_at")),
                "entered_at": now_text,
                "exited_at": "",
                "exit_reason": "",
                "source_payload": {
                    "batch_id": batch_context.get("batch_id"),
                    "eligible_message_count": int(batch_context.get("customer_text_count") or 0),
                },
            }
        return {
            "marketing_phase": "waiting_openclaw",
            "phase_label": _PHASE_LABELS["waiting_openclaw"],
            "phase_reason": "pending_text_message_batch",
            "lifecycle_status": "active",
            "last_batch_id": batch_context.get("batch_id"),
            "last_batch_status": _normalized_text(batch_context.get("batch_status")),
            "last_batch_window_start": _normalized_text(batch_context.get("window_start")),
            "last_batch_window_end": _normalized_text(batch_context.get("window_end")),
            "last_trigger_message_at": _normalized_text(batch_context.get("latest_customer_message_at")),
            "entered_at": _normalized_text((existing_state or {}).get("entered_at")) or now_text,
            "exited_at": "",
            "exit_reason": "",
            "source_payload": {
                "batch_id": batch_context.get("batch_id"),
                "eligible_message_count": int(batch_context.get("customer_text_count") or 0),
            },
        }

    if existing_state and _normalized_text(existing_state.get("lifecycle_status")) in {"active", "blocked"}:
        return {
            "marketing_phase": _normalized_text(existing_state.get("marketing_phase")),
            "phase_label": _normalized_text(existing_state.get("phase_label"))
            or _PHASE_LABELS.get(_normalized_text(existing_state.get("marketing_phase")), ""),
            "phase_reason": _normalized_text(existing_state.get("phase_reason")),
            "lifecycle_status": _normalized_text(existing_state.get("lifecycle_status")),
            "last_batch_id": existing_state.get("last_batch_id"),
            "last_batch_status": _normalized_text(existing_state.get("last_batch_status")),
            "last_batch_window_start": _normalized_text(existing_state.get("last_batch_window_start")),
            "last_batch_window_end": _normalized_text(existing_state.get("last_batch_window_end")),
            "last_trigger_message_at": _normalized_text(existing_state.get("last_trigger_message_at")),
            "entered_at": _normalized_text(existing_state.get("entered_at")),
            "exited_at": _normalized_text(existing_state.get("exited_at")),
            "exit_reason": _normalized_text(existing_state.get("exit_reason")),
            "source_payload": _json_loads(existing_state.get("source_payload_json"), default={}),
        }

    return {
        "marketing_phase": "awaiting_trigger",
        "phase_label": _PHASE_LABELS["awaiting_trigger"],
        "phase_reason": "awaiting_pending_batch",
        "lifecycle_status": "idle",
        "last_batch_id": None,
        "last_batch_status": "",
        "last_batch_window_start": "",
        "last_batch_window_end": "",
        "last_trigger_message_at": _normalized_text(base.get("last_customer_text_at")),
        "entered_at": "",
        "exited_at": "",
        "exit_reason": "",
        "source_payload": {
            "signup_status": _normalized_text(base.get("signup_status")),
            "last_customer_text_at": _normalized_text(base.get("last_customer_text_at")),
        },
    }


def _persist_value_segment(base: dict[str, Any], *, scenario_key: str, config: dict[str, Any]) -> dict[str, Any]:
    if _value_segment_config_ready(config):
        evaluated = evaluate_customer_value_segment(
            external_userid=_normalized_text(base.get("external_userid")),
            automation_key=scenario_key,
        )
        return {
            "value_segment": _normalized_text(evaluated.get("segment")),
            "segment_label": _normalized_text(evaluated.get("segment_label"))
            or _VALUE_SEGMENT_LABELS.get(_normalized_text(evaluated.get("segment")), ""),
            "score": int(evaluated.get("score") or 0),
            "score_breakdown": {
                "question_hit_count": int(evaluated.get("hit_count") or 0),
                "matched_question_ids": list(evaluated.get("matched_question_ids_json") or []),
                "submission_id": evaluated.get("submission_id"),
            },
            "is_core": bool(evaluated.get("is_core")),
            "is_top": bool(evaluated.get("is_top")),
            "updated_at": _normalized_text(evaluated.get("updated_at")) or _normalized_text(evaluated.get("evaluated_at")),
        }
    value_segment = _compute_value_segment(base, config=config)
    row = repo.upsert_marketing_value_segment_current(
        scenario_key=scenario_key,
        external_userid=_normalized_text(base.get("external_userid")),
        value_segment=value_segment["value_segment"],
        segment_label=value_segment["segment_label"],
        score=int(value_segment["score"]),
        score_breakdown=value_segment["score_breakdown"],
        source_payload={
            "is_bound": bool(base.get("is_bound")),
            "questionnaire_submission_count": int(base.get("questionnaire_submission_count") or 0),
            "last_customer_text_at": _normalized_text(base.get("last_customer_text_at")),
            "tag_names": _dedupe_tag_names(base),
            "core_threshold": int(config.get("core_threshold") or DEFAULT_CORE_THRESHOLD),
            "top_threshold": int(config.get("top_threshold") or DEFAULT_TOP_THRESHOLD),
        },
    )
    row["score_breakdown"] = _json_loads(row.get("score_breakdown_json"), default={})
    row["is_core"] = _normalized_text(row.get("value_segment")) in {"core", "top"}
    row["is_top"] = _normalized_text(row.get("value_segment")) == "top"
    return row


def _persist_marketing_state(
    base: dict[str, Any],
    *,
    scenario_key: str,
    batch_context: dict[str, Any] | None,
) -> dict[str, Any]:
    existing = repo.get_marketing_state_current(_normalized_text(base.get("external_userid")), scenario_key=scenario_key)
    payload = _build_state_payload(base, existing_state=existing, batch_context=batch_context)
    row = repo.upsert_marketing_state_current(
        scenario_key=scenario_key,
        external_userid=_normalized_text(base.get("external_userid")),
        marketing_phase=_normalized_text(payload.get("marketing_phase")),
        phase_label=_normalized_text(payload.get("phase_label")),
        phase_reason=_normalized_text(payload.get("phase_reason")),
        lifecycle_status=_normalized_text(payload.get("lifecycle_status")),
        last_batch_id=payload.get("last_batch_id"),
        last_batch_status=_normalized_text(payload.get("last_batch_status")),
        last_batch_window_start=_normalized_text(payload.get("last_batch_window_start")),
        last_batch_window_end=_normalized_text(payload.get("last_batch_window_end")),
        last_trigger_message_at=_normalized_text(payload.get("last_trigger_message_at")),
        entered_at=_normalized_text(payload.get("entered_at")),
        exited_at=_normalized_text(payload.get("exited_at")),
        exit_reason=_normalized_text(payload.get("exit_reason")),
        source_payload=payload.get("source_payload") or {},
    )
    row["source_payload"] = _json_loads(row.get("source_payload_json"), default={})
    return row


def get_customer_marketing_profile(
    external_userid: str,
    *,
    scenario_key: str = DEFAULT_SCENARIO_KEY,
    batch_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_external_userid = _normalized_text(external_userid)
    if not normalized_external_userid:
        raise ValueError("external_userid is required")
    base = repo.load_customer_marketing_base(normalized_external_userid)
    if not _normalized_text(base.get("external_userid")):
        raise LookupError("customer not found")
    config = get_signup_conversion_config(automation_key=scenario_key)
    marketing_state = _persist_marketing_state(base, scenario_key=scenario_key, batch_context=batch_context)
    value_segment = _persist_value_segment(base, scenario_key=scenario_key, config=config)
    return {
        "scenario_key": scenario_key,
        "external_userid": normalized_external_userid,
        "marketing_state": {
            "marketing_phase": _normalized_text(marketing_state.get("marketing_phase")),
            "phase_label": _normalized_text(marketing_state.get("phase_label"))
            or _PHASE_LABELS.get(_normalized_text(marketing_state.get("marketing_phase")), ""),
            "phase_reason": _normalized_text(marketing_state.get("phase_reason")),
            "lifecycle_status": _normalized_text(marketing_state.get("lifecycle_status")),
            "last_batch_id": marketing_state.get("last_batch_id"),
            "last_batch_status": _normalized_text(marketing_state.get("last_batch_status")),
            "last_batch_window_start": _normalized_text(marketing_state.get("last_batch_window_start")),
            "last_batch_window_end": _normalized_text(marketing_state.get("last_batch_window_end")),
            "last_trigger_message_at": _normalized_text(marketing_state.get("last_trigger_message_at")),
            "entered_at": _normalized_text(marketing_state.get("entered_at")),
            "exited_at": _normalized_text(marketing_state.get("exited_at")),
            "exit_reason": _normalized_text(marketing_state.get("exit_reason")),
            "updated_at": _normalized_text(marketing_state.get("updated_at")),
        },
        "value_segment": {
            "value_segment": _normalized_text(value_segment.get("value_segment")),
            "segment_label": _normalized_text(value_segment.get("segment_label"))
            or _VALUE_SEGMENT_LABELS.get(_normalized_text(value_segment.get("value_segment")), ""),
            "score": int(value_segment.get("score") or 0),
            "score_breakdown": value_segment.get("score_breakdown") or {},
            "is_core": bool(value_segment.get("is_core")),
            "is_top": bool(value_segment.get("is_top")),
            "updated_at": _normalized_text(value_segment.get("updated_at")),
        },
    }


def _load_formatted_batch(batch_id: int) -> dict[str, Any] | None:
    result = archive_repo.get_message_batch(batch_id, limit=500, cursor="")
    if not result:
        return None
    batch, rows, safe_limit, cursor_text = result
    page_rows = list(rows[:safe_limit])
    group_map = get_group_chat_map([extract_roomid_from_raw_payload(row.get("raw_payload")) for row in page_rows])
    next_cursor = str(page_rows[-1]["batch_item_id"]) if len(rows) > safe_limit and page_rows else ""
    return {
        "batch": dict(batch),
        "messages": [format_message_row(row, group_map=group_map) for row in page_rows],
        "paging": {"limit": safe_limit, "cursor": cursor_text, "next_cursor": next_cursor},
    }


def _build_batch_context(
    batch: dict[str, Any],
    messages: list[dict[str, Any]],
    external_userid: str,
    *,
    quiet_hour_start: int,
) -> dict[str, Any]:
    customer_messages = [item for item in messages if _normalized_text(item.get("external_userid")) == external_userid]
    customer_text_messages = [
        item
        for item in customer_messages
        if _normalized_text(item.get("msgtype")).lower() == "text" and _normalized_text(item.get("from")) == external_userid
    ]
    latest_customer_message_at = max((_normalized_text(item.get("send_time")) for item in customer_text_messages), default="")
    window_start = _normalized_text(batch.get("window_start"))
    window_start_dt = _parse_timestamp(window_start)
    return {
        "batch_id": int(batch.get("id") or 0),
        "batch_status": _normalized_text(batch.get("status")),
        "window_start": window_start,
        "window_end": _normalized_text(batch.get("window_end")),
        "blocked_after_quiet_hour": bool(window_start_dt is not None and window_start_dt.hour >= int(quiet_hour_start)),
        "quiet_hour_start": int(quiet_hour_start),
        "latest_customer_message_at": latest_customer_message_at,
        "customer_text_count": len(customer_text_messages),
        "candidate_messages": customer_text_messages,
    }


def _router_now(*, timezone: str) -> datetime:
    return datetime.now(ZoneInfo(_validate_timezone(timezone)))


def _router_quiet_hours_blocked(*, config: dict[str, Any]) -> bool:
    quiet_hour_start = int(config.get("quiet_hour_start") or DEFAULT_QUIET_HOUR_START)
    timezone = _normalized_text(config.get("timezone")) or DEFAULT_TIMEZONE
    return int(_router_now(timezone=timezone).hour) >= quiet_hour_start


def _serialize_dispatch_log(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    payload = row.get("dispatch_payload")
    if not isinstance(payload, dict):
        payload = _json_loads(row.get("dispatch_payload_json"), default={})
    if not isinstance(payload, dict):
        payload = {}
    result = dict(row)
    result["dispatch_payload"] = payload
    return result


def _routing_reason_from_preview(
    preview: dict[str, Any],
    *,
    dispatch_status: str = "",
    default_reason: str = "",
) -> str:
    normalized_dispatch_status = _normalized_text(dispatch_status)
    if normalized_dispatch_status == _ROUTER_BLOCKED_DISPATCH_STATUS:
        return _ROUTER_BLOCKED_DISPATCH_STATUS
    if _normalized_text(default_reason):
        return _normalized_text(default_reason)
    config_snapshot = dict(preview.get("config_snapshot") or {})
    summary = dict(preview.get("summary") or {})
    current_stage = _candidate_preview_stage(preview)
    current_segment = _candidate_preview_segment(preview)
    if not bool(config_snapshot.get("enabled")):
        return "automation_disabled"
    if not bool(summary.get("eligible_for_conversion")):
        return _normalized_text(summary.get("ineligible_reason")) or "not_eligible"
    if current_stage not in _ROUTER_ALLOWED_STAGE_KEYS:
        return "stage_not_conversion_target"
    if current_segment not in _ROUTER_ALLOWED_SEGMENTS:
        return "segment_not_core_top"
    return "eligible_by_router"


def _message_sender_role(message: dict[str, Any], *, external_userid: str, owner_userid: str) -> str:
    sender = _normalized_text(message.get("from")) or _normalized_text(message.get("sender"))
    if sender and sender == external_userid:
        return "customer"
    if sender and owner_userid and sender == owner_userid:
        return "staff"
    return "unknown"


def _build_recent_text_message_summary(
    external_userid: str,
    *,
    owner_userid: str,
    limit: int,
) -> dict[str, Any]:
    def _summarize_text(value: Any, *, max_length: int = 80) -> str:
        normalized = " ".join(_normalized_text(value).split())
        if len(normalized) <= max_length:
            return normalized
        return normalized[: max_length - 1].rstrip() + "…"

    normalized_external_userid = _normalized_text(external_userid)
    if not normalized_external_userid:
        return {
            "latest_at": "",
            "latest_customer_message_at": "",
            "latest_customer_message_summary": "",
            "latest_staff_message_at": "",
            "latest_staff_message_summary": "",
            "count": 0,
            "customer_message_count": 0,
            "staff_message_count": 0,
            "sample_size": 0,
            "samples": [],
            "summary_text": "",
        }
    safe_limit = max(1, min(int(limit), 50))
    messages = get_recent_messages_by_user(
        normalized_external_userid,
        limit=max(safe_limit, 10),
        chat_type="private",
        group_chat_map_loader=get_group_chat_map,
    )
    text_items: list[dict[str, Any]] = []
    for item in messages:
        if _normalized_text(item.get("msgtype")).lower() != "text":
            continue
        content = _normalized_text(item.get("content"))
        if not content:
            continue
        text_items.append(
            {
                "send_time": _normalized_text(item.get("send_time")),
                "sender_role": _message_sender_role(
                    item,
                    external_userid=normalized_external_userid,
                    owner_userid=_normalized_text(owner_userid),
                ),
                "content": content,
            }
        )
    preview_items = text_items[:safe_limit]
    latest_customer_message = next(
        (item for item in preview_items if _normalized_text(item.get("sender_role")) == "customer"),
        {},
    )
    latest_staff_message = next(
        (item for item in preview_items if _normalized_text(item.get("sender_role")) == "staff"),
        {},
    )
    samples = [
        {
            "send_time": _normalized_text(item.get("send_time")),
            "sender_role": _normalized_text(item.get("sender_role")),
            "excerpt": _summarize_text(item.get("content")),
        }
        for item in preview_items[:2]
    ]
    summary_parts: list[str] = []
    if latest_customer_message:
        summary_parts.append(f"customer:{_summarize_text(latest_customer_message.get('content'))}")
    if latest_staff_message:
        summary_parts.append(f"staff:{_summarize_text(latest_staff_message.get('content'))}")
    return {
        "latest_at": _normalized_text((preview_items[0] if preview_items else {}).get("send_time")),
        "latest_customer_message_at": _normalized_text(latest_customer_message.get("send_time")),
        "latest_customer_message_summary": _summarize_text(latest_customer_message.get("content")),
        "latest_staff_message_at": _normalized_text(latest_staff_message.get("send_time")),
        "latest_staff_message_summary": _summarize_text(latest_staff_message.get("content")),
        "count": len(text_items),
        "customer_message_count": sum(1 for item in text_items if _normalized_text(item.get("sender_role")) == "customer"),
        "staff_message_count": sum(1 for item in text_items if _normalized_text(item.get("sender_role")) == "staff"),
        "sample_size": len(samples),
        "samples": samples,
        "summary_text": " | ".join(summary_parts),
    }


def _build_openclaw_customer_marketing_profile(
    *,
    external_userid: str = "",
    person_id: int | None = None,
    automation_key: str = DEFAULT_SCENARIO_KEY,
    batch_id: int | None = None,
    dispatch_status: str = "",
    routing_reason: str = "",
    recent_message_limit: int = 3,
) -> dict[str, Any]:
    preview = preview_signup_conversion_customer(
        external_userid=external_userid,
        person_id=person_id,
        automation_key=automation_key,
    )
    resolved_customer = dict(preview.get("resolved_customer") or {})
    resolved_external_userid = _normalized_text(resolved_customer.get("external_userid")) or _normalized_text(external_userid)
    base = repo.load_customer_marketing_base(resolved_external_userid) if resolved_external_userid else {}
    marketing_state = dict(preview.get("marketing_state") or {})
    value_segment = dict(preview.get("value_segment") or {})
    summary = dict(preview.get("summary") or {})
    owner_userid = _normalized_text(base.get("owner_userid")) or _normalized_text(((marketing_state.get("state_payload") or {}).get("owner_userid")))
    routing = {
        "reason": _routing_reason_from_preview(
            preview,
            dispatch_status=dispatch_status,
            default_reason=routing_reason,
        ),
        "dispatch_status": _normalized_text(dispatch_status),
        "batch_id": _normalize_int(batch_id, "batch_id", allow_none=True),
        "stage_key": _normalized_text(summary.get("current_stage")),
        "segment": _normalized_text(summary.get("current_segment")) or "unknown",
        "hit_count": int(summary.get("hit_count") or 0),
        "eligible_for_conversion": bool(summary.get("eligible_for_conversion")),
        "ineligible_reason": _normalized_text(summary.get("ineligible_reason")),
    }
    return {
        "external_userid": resolved_external_userid,
        "person_id": _normalize_int(resolved_customer.get("person_id"), "person_id", allow_none=True),
        "customer": {
            "external_userid": resolved_external_userid,
            "person_id": _normalize_int(resolved_customer.get("person_id"), "person_id", allow_none=True),
            "customer_name": _normalized_text(base.get("customer_name")) or resolved_external_userid,
            "mobile": _normalized_text(resolved_customer.get("mobile")) or _normalized_text(base.get("mobile")),
            "signup_status": _normalized_text(base.get("signup_status")),
            "signup_label_name": _normalized_text(base.get("signup_label_name")),
            "is_bound": bool(base.get("is_bound")),
            "tags": _dedupe_tag_names(base),
        },
        "owner": {
            "owner_userid": owner_userid,
            "owner_display_name": _normalized_text(base.get("owner_display_name")) or owner_userid,
        },
        "marketing_state": {
            "main_stage": _normalized_text(marketing_state.get("main_stage")),
            "sub_stage": _normalized_text(marketing_state.get("sub_stage")),
            "stage_key": _normalized_text(marketing_state.get("stage_key")),
            "stage_label": _normalized_text(marketing_state.get("stage_label")),
            "eligible_for_conversion": bool(marketing_state.get("eligible_for_conversion")),
            "exit_reason": _normalized_text(marketing_state.get("exit_reason")),
            "activated": bool(marketing_state.get("activated")),
            "converted": bool(marketing_state.get("converted")),
            "last_activation_at": _normalized_text(marketing_state.get("last_activation_at")),
            "last_conversion_marked_at": _normalized_text(marketing_state.get("last_conversion_marked_at")),
            "last_message_at": _normalized_text(marketing_state.get("last_message_at")),
        },
        "value_segment": {
            "segment": _normalized_text(value_segment.get("segment")) or "unknown",
            "segment_label": _normalized_text(value_segment.get("segment_label")) or _VALUE_SEGMENT_LABELS.get(
                _normalized_text(value_segment.get("segment")) or "unknown",
                "",
            ),
            "hit_count": int(value_segment.get("hit_count") or 0),
            "matched_question_ids": list(summary.get("matched_question_ids") or []),
            "matched_questions": list(summary.get("matched_questions") or []),
            "submission_id": _normalize_int(value_segment.get("submission_id"), "submission_id", allow_none=True),
            "evaluated_at": _normalized_text(value_segment.get("evaluated_at")),
            "is_core": bool(value_segment.get("is_core")),
            "is_top": bool(value_segment.get("is_top")),
        },
        "routing": routing,
        "recent_text_summary": _build_recent_text_message_summary(
            resolved_external_userid,
            owner_userid=owner_userid,
            limit=recent_message_limit,
        ),
    }


def _serialize_conversion_batch_meta(batch: dict[str, Any]) -> dict[str, Any]:
    batch_id = int(batch.get("id") or 0)
    return {
        "id": batch_id,
        "batch_id": batch_id,
        "status": _normalized_text(batch.get("status")),
        "window_start": _normalized_text(batch.get("window_start")),
        "window_end": _normalized_text(batch.get("window_end")),
        "message_count": int(batch.get("message_count") or 0),
        "acked_at": _normalized_text(batch.get("acked_at")),
    }


def _build_openclaw_batch_candidate(
    item: dict[str, Any],
    *,
    batch_id: int,
    automation_key: str,
    recent_message_limit: int,
) -> dict[str, Any]:
    external_userid = _normalized_text(item.get("external_userid"))
    dispatch_status = _normalized_text(item.get("dispatch_status"))
    profile = _build_openclaw_customer_marketing_profile(
        external_userid=external_userid,
        automation_key=automation_key,
        batch_id=batch_id,
        dispatch_status=dispatch_status,
        routing_reason=_normalized_text(item.get("trigger_reason")),
        recent_message_limit=recent_message_limit,
    )
    return {
        "external_userid": external_userid,
        "customer_name": _normalized_text(item.get("customer_name")),
        "owner_userid": _normalized_text(item.get("owner_userid")),
        "dispatch_status": dispatch_status,
        "candidate_message_count": int(item.get("candidate_message_count") or 0),
        "latest_customer_message_at": _normalized_text(item.get("latest_customer_message_at")),
        "routing": dict(profile.get("routing") or {}),
        "marketing_profile": profile,
        "dispatch_log": _serialize_dispatch_log(item.get("dispatch_log")),
    }


def get_openclaw_customer_marketing_profile(
    *,
    external_userid: str = "",
    person_id: int | None = None,
    recent_message_limit: int = 3,
    automation_key: str = DEFAULT_SCENARIO_KEY,
) -> dict[str, Any]:
    return _build_openclaw_customer_marketing_profile(
        external_userid=external_userid,
        person_id=person_id,
        automation_key=automation_key,
        recent_message_limit=recent_message_limit,
    )


def get_conversion_batch(
    batch_id: int,
    *,
    recent_message_limit: int = 3,
    automation_key: str = DEFAULT_SCENARIO_KEY,
) -> dict[str, Any] | None:
    detail = route_signup_conversion_batch_candidates(batch_id, scenario_key=automation_key)
    if not detail:
        return None
    batch = _serialize_conversion_batch_meta(dict(detail.get("batch") or {}))
    candidates = [
        _build_openclaw_batch_candidate(
            dict(item),
            batch_id=int(batch.get("batch_id") or 0),
            automation_key=automation_key,
            recent_message_limit=recent_message_limit,
        )
        for item in detail.get("candidates") or []
        if isinstance(item, dict)
    ]
    return {
        "automation_key": automation_key,
        "batch": batch,
        "candidate_count": len(candidates),
        "blocked_count": int(detail.get("blocked_count") or 0),
        "skipped_count": int(detail.get("skipped_count") or 0),
        "quiet_hours_blocked": bool(detail.get("quiet_hours_blocked")),
        "candidates": candidates,
        "skipped_customers": list(detail.get("skipped_customers") or []),
    }


def get_pending_conversion_batches(
    *,
    limit: int = 20,
    cursor: str = "",
    automation_key: str = DEFAULT_SCENARIO_KEY,
) -> dict[str, Any]:
    raw_batches = list_signup_conversion_batches(
        limit=limit,
        cursor=cursor,
        scenario_key=automation_key,
    )
    items: list[dict[str, Any]] = []
    for row in raw_batches.get("items") or []:
        if int(row.get("candidate_count") or 0) <= 0:
            continue
        preview_items = []
        for item in row.get("candidates_preview") or []:
            preview_items.append(
                {
                    "external_userid": _normalized_text(item.get("external_userid")),
                    "customer_name": _normalized_text(item.get("customer_name")),
                    "owner_userid": _normalized_text(item.get("owner_userid")),
                    "main_stage": _normalized_text(item.get("current_stage")).split("/", 1)[0],
                    "sub_stage": _normalized_text(item.get("current_stage")).split("/", 1)[1]
                    if "/" in _normalized_text(item.get("current_stage"))
                    else "",
                    "segment": _normalized_text(item.get("value_segment")) or "unknown",
                    "hit_count": int(item.get("score") or 0),
                    "reason": "pending_text_message_batch",
                    "dispatch_status": _normalized_text(item.get("dispatch_status")) or _ROUTER_PENDING_DISPATCH_STATUS,
                }
            )
        items.append(
            {
                "id": int(row.get("id") or 0),
                "batch_id": int(row.get("id") or 0),
                "status": _normalized_text(row.get("status")),
                "window_start": _normalized_text(row.get("window_start")),
                "window_end": _normalized_text(row.get("window_end")),
                "message_count": int(row.get("message_count") or 0),
                "candidate_count": int(row.get("candidate_count") or 0),
                "candidates_preview": preview_items,
            }
        )
    return {
        "automation_key": automation_key,
        "items": items,
        "count": len(items),
        "filters": dict(raw_batches.get("filters") or {}),
        "next_cursor": _normalized_text(raw_batches.get("next_cursor")),
    }


def ack_conversion_batch(
    batch_id: int,
    *,
    acked_by: str = "",
    ack_note: str = "",
    automation_key: str = DEFAULT_SCENARIO_KEY,
) -> dict[str, Any] | None:
    detail = route_signup_conversion_batch_candidates(int(batch_id), scenario_key=automation_key)
    if not detail:
        return None
    batch = _serialize_conversion_batch_meta(dict(detail.get("batch") or {}))
    existing_logs = {
        _normalized_text(item.get("external_userid")): _serialize_dispatch_log(item)
        for item in repo.list_conversion_dispatch_logs(batch_id=int(batch_id))
    }
    acked_at = _iso_now()
    normalized_acked_by = _normalized_text(acked_by) or "openclaw"
    normalized_ack_note = _normalized_text(ack_note)
    updated_logs: list[dict[str, Any]] = []
    acknowledged_count = 0
    db = get_db()
    try:
        for candidate in detail.get("candidates") or []:
            if not isinstance(candidate, dict):
                continue
            external_userid = _normalized_text(candidate.get("external_userid"))
            if not external_userid:
                continue
            existing = existing_logs.get(external_userid) or {}
            existing_status = _normalized_text(existing.get("dispatch_status"))
            if existing_status == "acked" and _normalized_text(existing.get("acked_at")):
                updated_logs.append(existing)
                continue
            if existing_status and existing_status not in _OPENCLAW_ACKABLE_DISPATCH_STATUSES:
                continue
            payload = dict(existing.get("dispatch_payload") or {})
            payload.update(
                {
                    "acked_by": normalized_acked_by,
                    "ack_note": normalized_ack_note,
                    "ack_source": "ack_conversion_batch",
                }
            )
            row = repo.upsert_conversion_dispatch_log(
                automation_key=automation_key,
                batch_id=int(batch_id),
                external_userid=external_userid,
                dispatch_status="acked",
                dispatch_channel=_normalized_text(existing.get("dispatch_channel")) or DEFAULT_CHANNEL_TYPE,
                dispatch_payload=payload,
                dispatch_note=normalized_ack_note or f"acked by {normalized_acked_by}",
                dispatched_at=_normalized_text(existing.get("dispatched_at")) or acked_at,
                acked_at=acked_at,
            )
            acknowledged_count += 1
            updated_logs.append(_serialize_dispatch_log(row))
        db.commit()
    except Exception:
        db.rollback()
        raise
    if not updated_logs:
        updated_logs = [
            _serialize_dispatch_log(item)
            for item in repo.list_conversion_dispatch_logs(batch_id=int(batch_id))
            if _normalized_text(item.get("dispatch_status")) == "acked"
        ]
    return {
        "automation_key": automation_key,
        "batch": batch,
        "batch_id": int(batch.get("batch_id") or 0),
        "acknowledged_count": acknowledged_count,
        "dispatch_logs": updated_logs,
        "acked_at": acked_at if acknowledged_count else _normalized_text((updated_logs[0] if updated_logs else {}).get("acked_at")),
        "acked_by": normalized_acked_by,
        "ack_note": normalized_ack_note,
    }


def _ensure_router_dispatch_log(
    *,
    scenario_key: str,
    batch_context: dict[str, Any],
    external_userid: str,
    dispatch_status: str,
    preview: dict[str, Any],
    existing_log: dict[str, Any] | None,
) -> tuple[dict[str, Any], bool]:
    serialized_existing = _serialize_dispatch_log(existing_log)
    existing_status = _normalized_text(serialized_existing.get("dispatch_status"))
    if existing_status == dispatch_status:
        return serialized_existing, False
    summary = dict(preview.get("summary") or {})
    marketing_state = dict(preview.get("marketing_state") or {})
    payload = {
        "source": "marketing_candidate_router",
        "route_status": dispatch_status,
        "current_stage": _normalized_text(summary.get("current_stage")),
        "current_segment": _normalized_text(summary.get("current_segment")),
        "hit_count": int(summary.get("hit_count") or 0),
        "eligible_for_conversion": bool(summary.get("eligible_for_conversion")),
        "main_stage": _normalized_text(marketing_state.get("main_stage")),
        "sub_stage": _normalized_text(marketing_state.get("sub_stage")),
        "batch_window_start": _normalized_text(batch_context.get("window_start")),
        "batch_window_end": _normalized_text(batch_context.get("window_end")),
        "latest_customer_message_at": _normalized_text(batch_context.get("latest_customer_message_at")),
    }
    note = "candidate eligible for openclaw" if dispatch_status == _ROUTER_PENDING_DISPATCH_STATUS else "blocked by quiet hours"
    row = repo.upsert_conversion_dispatch_log(
        automation_key=scenario_key,
        batch_id=int(batch_context.get("batch_id") or 0),
        external_userid=external_userid,
        dispatch_status=dispatch_status,
        dispatch_channel=DEFAULT_CHANNEL_TYPE,
        dispatch_payload=payload,
        dispatch_note=note,
    )
    return _serialize_dispatch_log(row), True


def _candidate_skip_entry(
    external_userid: str,
    reason: str,
    *,
    dispatch_status: str = "",
) -> dict[str, Any]:
    payload = {"external_userid": external_userid, "reason": reason}
    if dispatch_status:
        payload["dispatch_status"] = dispatch_status
    return payload


def _candidate_preview_stage(preview: dict[str, Any]) -> str:
    return _normalized_text(((preview.get("summary") or {}).get("current_stage")))


def _candidate_preview_segment(preview: dict[str, Any]) -> str:
    return _normalized_text(((preview.get("summary") or {}).get("current_segment"))) or "unknown"


def _build_disabled_batch_result(
    batch_payload: dict[str, Any],
    *,
    scenario_key: str,
) -> dict[str, Any]:
    batch = dict(batch_payload.get("batch") or {})
    messages = [dict(item) for item in batch_payload.get("messages") or [] if isinstance(item, dict)]
    external_userids = sorted(
        {
            _normalized_text(item.get("external_userid"))
            for item in messages
            if _normalized_text(item.get("external_userid"))
        }
    )
    skipped_customers = [
        {"external_userid": external_userid, "reason": "automation_disabled"} for external_userid in external_userids
    ]
    return {
        "scenario_key": scenario_key,
        "batch": batch,
        "messages": messages,
        "paging": batch_payload.get("paging") or {},
        "candidates": [],
        "candidate_count": 0,
        "blocked_count": 0,
        "skipped_customers": skipped_customers,
        "skipped_count": len(skipped_customers),
    }


def route_signup_conversion_batch_candidates(
    batch_id: int,
    *,
    scenario_key: str = DEFAULT_SCENARIO_KEY,
) -> dict[str, Any] | None:
    from ..archive.service import materialize_message_batches

    materialize_message_batches(window_minutes=3)
    batch_payload = _load_formatted_batch(int(batch_id))
    if not batch_payload:
        return None
    config = get_signup_conversion_config(automation_key=scenario_key)
    if not bool(config.get("enabled")):
        return _build_disabled_batch_result(batch_payload, scenario_key=scenario_key)
    batch = dict(batch_payload.get("batch") or {})
    messages = [dict(item) for item in batch_payload.get("messages") or [] if isinstance(item, dict)]
    base_cache: dict[str, dict[str, Any]] = {}
    candidates: list[dict[str, Any]] = []
    skipped_customers: list[dict[str, Any]] = []
    blocked_count = 0
    seen_external_userids: set[str] = set()
    wrote_dispatch_logs = False
    quiet_hours_blocked = _router_quiet_hours_blocked(config=config)
    batch_status = _normalized_text(batch.get("status"))

    for message in messages:
        external_userid = _normalized_text(message.get("external_userid"))
        if not external_userid or external_userid in seen_external_userids:
            continue
        seen_external_userids.add(external_userid)
        batch_context = _build_batch_context(
            batch,
            messages,
            external_userid,
            quiet_hour_start=int(config.get("quiet_hour_start") or DEFAULT_QUIET_HOUR_START),
        )
        if int(batch_context.get("customer_text_count") or 0) <= 0:
            skipped_customers.append(_candidate_skip_entry(external_userid, "no_customer_text_trigger"))
            continue
        if batch_status != "pending":
            skipped_customers.append(_candidate_skip_entry(external_userid, "batch_not_pending"))
            continue
        base = base_cache.setdefault(external_userid, repo.load_customer_marketing_base(external_userid))
        preview = preview_signup_conversion_customer(
            external_userid=external_userid,
            automation_key=scenario_key,
        )
        current_stage = _candidate_preview_stage(preview)
        current_segment = _candidate_preview_segment(preview)
        ineligible_reason = _normalized_text(((preview.get("summary") or {}).get("ineligible_reason")))
        if current_stage not in _ROUTER_ALLOWED_STAGE_KEYS:
            skipped_customers.append(_candidate_skip_entry(external_userid, ineligible_reason or "stage_not_conversion_target"))
            continue
        if current_segment not in _ROUTER_ALLOWED_SEGMENTS:
            skipped_customers.append(_candidate_skip_entry(external_userid, "segment_not_core_top"))
            continue
        if not bool(((preview.get("summary") or {}).get("eligible_for_conversion"))):
            skipped_customers.append(_candidate_skip_entry(external_userid, ineligible_reason or "not_eligible"))
            continue

        existing_dispatch_log = _serialize_dispatch_log(repo.get_conversion_dispatch_log(int(batch_id), external_userid))
        existing_status = _normalized_text(existing_dispatch_log.get("dispatch_status"))
        if existing_status in _ROUTER_TERMINAL_DISPATCH_STATUSES:
            terminal_reason = "already_acked" if existing_status == "acked" else "already_dispatched"
            if existing_status in {"cancelled", "converted_before_dispatch"}:
                terminal_reason = existing_status
            skipped_customers.append(_candidate_skip_entry(external_userid, terminal_reason, dispatch_status=existing_status))
            continue
        if quiet_hours_blocked:
            dispatch_log, did_write = _ensure_router_dispatch_log(
                scenario_key=scenario_key,
                batch_context=batch_context,
                external_userid=external_userid,
                dispatch_status=_ROUTER_BLOCKED_DISPATCH_STATUS,
                preview=preview,
                existing_log=existing_dispatch_log,
            )
            wrote_dispatch_logs = wrote_dispatch_logs or did_write
            skipped_customers.append(
                _candidate_skip_entry(
                    external_userid,
                    "blocked_quiet_hours",
                    dispatch_status=_normalized_text(dispatch_log.get("dispatch_status")) or _ROUTER_BLOCKED_DISPATCH_STATUS,
                )
            )
            blocked_count += 1
            continue

        dispatch_log, did_write = _ensure_router_dispatch_log(
            scenario_key=scenario_key,
            batch_context=batch_context,
            external_userid=external_userid,
            dispatch_status=_ROUTER_PENDING_DISPATCH_STATUS,
            preview=preview,
            existing_log=existing_dispatch_log,
        )
        wrote_dispatch_logs = wrote_dispatch_logs or did_write
        profile = get_customer_marketing_profile(
            external_userid,
            scenario_key=scenario_key,
            batch_context=batch_context,
        )
        candidates.append(
            {
                "external_userid": external_userid,
                "customer_name": _normalized_text(base.get("customer_name")) or external_userid,
                "owner_userid": _normalized_text(base.get("owner_userid")),
                "marketing_profile": profile,
                "current_stage": current_stage,
                "current_segment": current_segment,
                "eligible_for_conversion": True,
                "dispatch_status": _normalized_text(dispatch_log.get("dispatch_status")) or _ROUTER_PENDING_DISPATCH_STATUS,
                "dispatch_log": dispatch_log,
                "trigger_reason": "pending_text_message_batch",
                "latest_customer_message_at": _normalized_text(batch_context.get("latest_customer_message_at")),
                "candidate_messages": batch_context.get("candidate_messages") or [],
                "candidate_message_count": int(batch_context.get("customer_text_count") or 0),
            }
        )

    if wrote_dispatch_logs:
        get_db().commit()

    candidates.sort(
        key=lambda item: (
            int(((((item.get("dispatch_log") or {}).get("dispatch_payload") or {}).get("hit_count")) or 0)),
            _normalized_text(item.get("latest_customer_message_at")),
            _normalized_text(item.get("external_userid")),
        ),
        reverse=True,
    )
    return {
        "scenario_key": scenario_key,
        "batch": batch,
        "messages": messages,
        "paging": batch_payload.get("paging") or {},
        "candidates": candidates,
        "candidate_count": len(candidates),
        "blocked_count": blocked_count,
        "quiet_hours_blocked": quiet_hours_blocked,
        "skipped_customers": skipped_customers,
        "skipped_count": len(skipped_customers),
    }


def get_signup_conversion_batch(batch_id: int, *, scenario_key: str = DEFAULT_SCENARIO_KEY) -> dict[str, Any] | None:
    return route_signup_conversion_batch_candidates(batch_id, scenario_key=scenario_key)


def list_signup_conversion_batches(
    *,
    limit: int = 20,
    cursor: str = "",
    scenario_key: str = DEFAULT_SCENARIO_KEY,
) -> dict[str, Any]:
    from ..archive.service import list_message_batches, materialize_message_batches

    safe_limit = max(1, min(int(limit), 50))
    config = get_signup_conversion_config(automation_key=scenario_key)
    if not bool(config.get("enabled")):
        return {
            "scenario_key": scenario_key,
            "items": [],
            "count": 0,
            "filters": {"limit": str(safe_limit), "cursor": _normalized_text(cursor)},
            "source_cursor": "",
            "next_cursor": "",
        }
    materialize_message_batches(window_minutes=3)
    pending_batches = list_message_batches(status="pending", limit=safe_limit, cursor=cursor)
    items: list[dict[str, Any]] = []
    for batch in pending_batches.get("items") or []:
        batch_id = int(batch.get("id") or 0)
        if not batch_id:
            continue
        detail = route_signup_conversion_batch_candidates(batch_id, scenario_key=scenario_key)
        if not detail:
            continue
        if int(detail.get("candidate_count") or 0) <= 0 and int(detail.get("blocked_count") or 0) <= 0:
            continue
        preview = [
            {
                "external_userid": _normalized_text(item.get("external_userid")),
                "customer_name": _normalized_text(item.get("customer_name")),
                "owner_userid": _normalized_text(item.get("owner_userid")),
                "current_stage": _normalized_text(item.get("current_stage")),
                "marketing_phase": _normalized_text((((item.get("marketing_profile") or {}).get("marketing_state") or {}).get("marketing_phase"))),
                "value_segment": _normalized_text(item.get("current_segment")),
                "score": int((((item.get("dispatch_log") or {}).get("dispatch_payload") or {}).get("hit_count") or 0)),
                "dispatch_status": _normalized_text(item.get("dispatch_status")),
            }
            for item in detail.get("candidates") or []
        ]
        items.append(
            {
                "id": batch_id,
                "status": _normalized_text(batch.get("status")),
                "window_start": _normalized_text(batch.get("window_start")),
                "window_end": _normalized_text(batch.get("window_end")),
                "message_count": int(batch.get("message_count") or 0),
                "candidate_count": int(detail.get("candidate_count") or 0),
                "blocked_count": int(detail.get("blocked_count") or 0),
                "skipped_count": int(detail.get("skipped_count") or 0),
                "candidates_preview": preview,
            }
        )
    return {
        "scenario_key": scenario_key,
        "items": items,
        "count": len(items),
        "filters": {"limit": str(safe_limit), "cursor": _normalized_text(cursor)},
        "source_cursor": _normalized_text(pending_batches.get("next_cursor")),
        "next_cursor": _normalized_text(pending_batches.get("next_cursor")),
    }
