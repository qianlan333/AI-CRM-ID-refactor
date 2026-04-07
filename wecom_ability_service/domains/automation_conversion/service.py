from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from ...db import get_db
from ...wecom_client import WeComClientError
from ..marketing_automation.service import get_customer_marketing_profile, get_signup_conversion_config, save_signup_conversion_config
from ..outbound_webhook.service import EVENT_OPENCLAW_FOCUS_MESSAGE, send_outbound_webhook
from ..questionnaire.service import get_questionnaire_detail, list_questionnaires
from . import repo
from .provider import load_channel_provider

DEFAULT_OWNER_STAFF_ID = "QianLan"
DEFAULT_CHANNEL_CODE = "default_qrcode"
DEFAULT_CHANNEL_NAME = "默认渠道二维码"
AI_PUSH_SCENE_SIDEBAR_SCRIPT = "sidebar_script"
AI_PUSH_COOLDOWN_SECONDS = 30

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
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, pattern)
        except ValueError:
            continue
    return None


def _iso_now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def default_owner_staff_id() -> str:
    return DEFAULT_OWNER_STAFF_ID


def _pool_label(pool: str) -> str:
    return POOL_LABELS.get(_normalized_text(pool), _normalized_text(pool) or "未设置")


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


def _persist_member(member: dict[str, Any] | None, payload: dict[str, Any]) -> dict[str, Any]:
    db = get_db()
    try:
        if member and member.get("id"):
            saved = repo.update_member(int(member["id"]), payload)
        else:
            saved = repo.insert_member(payload)
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
            "owner_staff_id": _normalized_text(channel.get("owner_staff_id")) or DEFAULT_OWNER_STAFF_ID,
            "status": _normalized_text(channel.get("status")) or "not_generated",
        },
        "default_owner_staff_id": DEFAULT_OWNER_STAFF_ID,
        "provider_available": load_channel_provider() is not None,
    }


def save_settings(payload: dict[str, Any]) -> dict[str, Any]:
    config_payload = {
        "enabled": _normalize_bool(payload.get("enabled", True)),
        "questionnaire_id": payload.get("questionnaire_id"),
        "core_threshold": payload.get("core_threshold"),
        "top_threshold": payload.get("top_threshold", payload.get("core_threshold")),
        "quiet_hour_start": payload.get("quiet_hour_start"),
        "timezone": payload.get("timezone"),
        "silent_threshold_days_by_pool": payload.get("silent_threshold_days_by_pool"),
        "question_rules": payload.get("question_rules"),
    }
    save_signup_conversion_config(config_payload, enforce_required_mobile_question=True)
    existing = repo.get_default_channel() or {}
    repo.save_channel(
        {
            "channel_code": DEFAULT_CHANNEL_CODE,
            "channel_name": _normalized_text(payload.get("channel_name")) or _normalized_text(existing.get("channel_name")) or DEFAULT_CHANNEL_NAME,
            "qr_url": _normalized_text(payload.get("qr_url")) or _normalized_text(existing.get("qr_url")),
            "qr_ticket": _normalized_text(payload.get("qr_ticket")) or _normalized_text(existing.get("qr_ticket")),
            "scene_value": _normalized_text(payload.get("scene_value")) or _normalized_text(existing.get("scene_value")),
            "owner_staff_id": DEFAULT_OWNER_STAFF_ID,
            "status": _normalized_text(payload.get("channel_status")) or _normalized_text(existing.get("status")) or "configured",
        }
    )
    get_db().commit()
    return get_settings_payload()


def generate_default_channel_qr(*, operator: str = "") -> dict[str, Any]:
    provider = load_channel_provider()
    if provider is None:
        return {
            "generated": False,
            "provider_available": False,
            "channel": repo.get_default_channel() or {},
            "error": "二维码 provider 未接入，当前仓库无法生成真实企微渠道二维码",
            "operator": _normalized_text(operator),
            "status_code": 501,
            "error_code": "provider_missing",
        }
    try:
        channel_payload = provider.create_default_channel(owner_staff_id=DEFAULT_OWNER_STAFF_ID)
    except ValueError as exc:
        existing = repo.get_default_channel() or {}
        saved = repo.save_channel(
            {
                "channel_code": _normalized_text(existing.get("channel_code")) or DEFAULT_CHANNEL_CODE,
                "channel_name": _normalized_text(existing.get("channel_name")) or DEFAULT_CHANNEL_NAME,
                "qr_url": _normalized_text(existing.get("qr_url")),
                "qr_ticket": _normalized_text(existing.get("qr_ticket")),
                "scene_value": _normalized_text(existing.get("scene_value")),
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
        }
    except WeComClientError as exc:
        existing = repo.get_default_channel() or {}
        saved = repo.save_channel(
            {
                "channel_code": _normalized_text(existing.get("channel_code")) or DEFAULT_CHANNEL_CODE,
                "channel_name": _normalized_text(existing.get("channel_name")) or DEFAULT_CHANNEL_NAME,
                "qr_url": _normalized_text(existing.get("qr_url")),
                "qr_ticket": _normalized_text(existing.get("qr_ticket")),
                "scene_value": _normalized_text(existing.get("scene_value")),
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
        }
    saved = repo.save_channel(
        {
            "channel_code": DEFAULT_CHANNEL_CODE,
            "channel_name": _normalized_text(channel_payload.get("channel_name")) or DEFAULT_CHANNEL_NAME,
            "qr_url": _normalized_text(channel_payload.get("qr_url")),
            "qr_ticket": _normalized_text(channel_payload.get("qr_ticket")),
            "scene_value": _normalized_text(channel_payload.get("scene_value")),
            "owner_staff_id": DEFAULT_OWNER_STAFF_ID,
            "status": _normalized_text(channel_payload.get("status")) or "active",
        }
    )
    get_db().commit()
    return {"generated": True, "provider_available": True, "channel": saved}


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
    member = _touch_member_from_sources(member, action="system_push_sync", persist_event=False)
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
    return {"cards": cards, "stage_columns": stage_columns, "counts": counts}


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


def handle_qrcode_enter_from_callback(
    *,
    external_contact_id: str,
    phone: str = "",
    payload_json: dict[str, Any] | None = None,
    operator_id: str = "",
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
        return {"handled": True, "member": _serialize_member(saved), "won_kept": True}
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
    return {"handled": True, "member": _serialize_member(saved)}
