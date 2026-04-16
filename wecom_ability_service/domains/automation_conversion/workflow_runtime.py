from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from typing import Any

from ...db import get_db
from ...services import get_recent_messages_by_user
from ..tasks.service import dispatch_wecom_task
from ..user_ops import page_service as user_ops_page_service
from . import repo as legacy_repo
from .agents import DeepSeekClientError, call_deepseek_agent
from .orchestration_service import (
    _agent_context_source_sections,
    _fixed_agent_output_schema,
    _replace_agent_prompt_placeholders,
    _resolve_effective_enabled_context_sources,
    get_agent_config_detail,
)
from .workflow_definitions import (
    AGENT_BINDING_SCOPE_BEHAVIOR_TIER,
    AGENT_BINDING_SCOPE_PERSONALIZED,
    AGENT_BINDING_SCOPE_PROFILE_CATEGORY,
    AUDIENCE_CONVERTED,
    AUDIENCE_OPERATING,
    AUDIENCE_PENDING_QUESTIONNAIRE,
    GENERATION_MODE_AUTO_LAYERED_REWRITE,
    GENERATION_MODE_MANUAL_LAYERED,
    GENERATION_MODE_PERSONALIZED_SINGLE,
    NODE_TRIGGER_MODE_AUDIENCE_ENTERED,
    NODE_TRIGGER_MODE_SCHEDULED,
    RECIPIENT_FILTER_BASIS_BEHAVIOR,
    RECIPIENT_FILTER_BASIS_NONE,
    SEGMENTATION_BASIS_BEHAVIOR,
    SEGMENTATION_BASIS_NONE,
    SEGMENTATION_BASIS_PROFILE,
    WORKFLOW_STATUS_ACTIVE,
    list_supported_behavior_tiers,
)
from .workflow_service import get_conversion_workflow_model_bundle
from . import workflow_repo


DEFAULT_AUTOMATION_SENDER = "HuangYouCan"
_FINAL_EXECUTION_STATUSES = {"finished", "partial_failed", "failed"}


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_int(value: Any, *, default: int = 0, minimum: int | None = None) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        result = int(default)
    if minimum is not None:
        result = max(result, minimum)
    return result


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    text = _normalized_text(value)
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return list(parsed) if isinstance(parsed, list) else []


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


def _parse_send_time(value: Any) -> tuple[int, int]:
    text = _normalized_text(value) or "09:00"
    parsed = datetime.strptime(text, "%H:%M")
    return parsed.hour, parsed.minute


def _node_trigger_mode(node: dict[str, Any]) -> str:
    normalized = _normalized_text(node.get("trigger_mode"))
    if normalized == NODE_TRIGGER_MODE_AUDIENCE_ENTERED:
        return NODE_TRIGGER_MODE_AUDIENCE_ENTERED
    return NODE_TRIGGER_MODE_SCHEDULED


def _iso_now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _behavior_tier_items() -> list[dict[str, Any]]:
    return [dict(item) for item in list_supported_behavior_tiers()]


def _behavior_tier_for_count(message_count: int) -> dict[str, Any]:
    normalized_count = max(0, int(message_count or 0))
    for item in _behavior_tier_items():
        min_value = item.get("min_value")
        max_value = item.get("max_value")
        if min_value is not None and normalized_count < int(min_value):
            continue
        if max_value is not None and normalized_count > int(max_value):
            continue
        return dict(item)
    return dict(_behavior_tier_items()[0])


def _workflow_recipient_filter_config(workflow_bundle: dict[str, Any]) -> dict[str, Any]:
    workflow = dict(workflow_bundle.get("workflow") or {})
    basis = _normalized_text(workflow.get("recipient_filter_basis")) or RECIPIENT_FILTER_BASIS_NONE
    if basis not in {RECIPIENT_FILTER_BASIS_NONE, RECIPIENT_FILTER_BASIS_BEHAVIOR}:
        basis = RECIPIENT_FILTER_BASIS_NONE
    tier_keys = []
    seen: set[str] = set()
    allowed = {_normalized_text(item.get("tier_code")) for item in _behavior_tier_items()}
    for item in workflow.get("recipient_behavior_tier_keys") or []:
        tier_key = _normalized_text(item)
        if not tier_key or tier_key in seen or tier_key not in allowed:
            continue
        seen.add(tier_key)
        tier_keys.append(tier_key)
    if basis != RECIPIENT_FILTER_BASIS_BEHAVIOR:
        tier_keys = []
    return {
        "recipient_filter_basis": basis,
        "recipient_behavior_tier_keys": tier_keys,
    }


def _member_behavior_tier_match(member: dict[str, Any], selected_tier_keys: list[str]) -> dict[str, Any]:
    resolved = _resolve_behavior_segment_match(member)
    selected = {_normalized_text(item) for item in selected_tier_keys or [] if _normalized_text(item)}
    tier_key = _normalized_text(resolved.get("segment_key"))
    return {
        **resolved,
        "selected_tier_keys": sorted(selected),
        "matched": bool(tier_key) and tier_key in selected,
    }


def _member_matches_workflow_recipient_filter(member: dict[str, Any], workflow_bundle: dict[str, Any]) -> bool:
    config = _workflow_recipient_filter_config(workflow_bundle)
    if _normalized_text(config.get("recipient_filter_basis")) != RECIPIENT_FILTER_BASIS_BEHAVIOR:
        return True
    if not (
        int(member.get("id") or 0)
        or _normalized_text(member.get("external_contact_id"))
        or _normalized_text(member.get("phone"))
    ):
        return False
    return bool(_member_behavior_tier_match(member, list(config.get("recipient_behavior_tier_keys") or [])).get("matched"))


def _current_audience_source_snapshot(member: dict[str, Any], marketing_state: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "member_id": int(member.get("id") or 0),
        "external_contact_id": _normalized_text(member.get("external_contact_id")),
        "phone": _normalized_text(member.get("phone")),
        "current_pool": _normalized_text(member.get("current_pool")),
        "questionnaire_status": _normalized_text(member.get("questionnaire_status")),
        "questionnaire_result": _normalized_text(member.get("questionnaire_result")),
        "marketing_state": {
            "main_stage": _normalized_text((marketing_state or {}).get("main_stage")),
            "sub_stage": _normalized_text((marketing_state or {}).get("sub_stage")),
            "converted": bool((marketing_state or {}).get("converted")),
            "last_conversion_marked_at": _normalized_text((marketing_state or {}).get("last_conversion_marked_at")),
        },
    }


def _resolve_member_conversion_audience(member: dict[str, Any]) -> dict[str, Any]:
    marketing_state = workflow_repo.get_customer_marketing_state_current_row(
        external_userid=_normalized_text(member.get("external_contact_id")),
        person_id=int(member.get("master_customer_id") or 0) or None,
    )
    latest_submission = workflow_repo.get_latest_any_questionnaire_submission_row(
        external_contact_ids=[_normalized_text(member.get("external_contact_id"))],
        phone=_normalized_text(member.get("phone")),
    )
    current_audience_code = _normalized_text(member.get("current_audience_code"))
    current_audience_entered_at = _normalized_text(member.get("current_audience_entered_at"))
    if bool((marketing_state or {}).get("converted")) or _normalized_text((marketing_state or {}).get("main_stage")) == "converted" or _normalized_text(member.get("current_pool")) == "won":
        return {
            "audience_code": AUDIENCE_CONVERTED,
            "entered_at": current_audience_entered_at if current_audience_code == AUDIENCE_CONVERTED and current_audience_entered_at else (
                _normalized_text((marketing_state or {}).get("last_conversion_marked_at"))
                or _normalized_text((marketing_state or {}).get("entered_at"))
                or _normalized_text(member.get("updated_at"))
                or _normalized_text(member.get("joined_at"))
                or _iso_now()
            ),
            "entry_source": "marketing_state",
            "entry_reason": "customer_marketing_state_converted",
            "source_snapshot_json": _current_audience_source_snapshot(member, marketing_state),
        }
    if latest_submission or _normalized_text(member.get("questionnaire_status")) == "submitted":
        return {
            "audience_code": AUDIENCE_OPERATING,
            "entered_at": current_audience_entered_at if current_audience_code == AUDIENCE_OPERATING and current_audience_entered_at else (
                _normalized_text((latest_submission or {}).get("submitted_at"))
                or _normalized_text(member.get("updated_at"))
                or _normalized_text(member.get("joined_at"))
                or _iso_now()
            ),
            "entry_source": "questionnaire_submission" if latest_submission else "automation_member",
            "entry_reason": "questionnaire_submitted" if latest_submission else "member_questionnaire_status_submitted",
            "source_snapshot_json": _current_audience_source_snapshot(member, marketing_state),
        }
    return {
        "audience_code": AUDIENCE_PENDING_QUESTIONNAIRE,
        "entered_at": current_audience_entered_at if current_audience_code == AUDIENCE_PENDING_QUESTIONNAIRE and current_audience_entered_at else (
            _normalized_text(member.get("joined_at"))
            or _normalized_text(member.get("created_at"))
            or _normalized_text(member.get("updated_at"))
            or _iso_now()
        ),
        "entry_source": "automation_member",
        "entry_reason": "questionnaire_not_submitted",
        "source_snapshot_json": _current_audience_source_snapshot(member, marketing_state),
    }


def sync_conversion_member_audience(member: dict[str, Any]) -> dict[str, Any]:
    member_id = int(member.get("id") or 0)
    if member_id <= 0:
        return {"updated": False, "reason": "member_id_missing"}
    resolved = _resolve_member_conversion_audience(member)
    current_entry = workflow_repo.get_current_member_audience_entry_row(member_id)
    current_code = _normalized_text(member.get("current_audience_code"))
    current_entered_at = _normalized_text(member.get("current_audience_entered_at"))
    target_code = _normalized_text(resolved.get("audience_code"))
    target_entered_at = _normalized_text(resolved.get("entered_at")) or _iso_now()

    if current_entry and _normalized_text(current_entry.get("audience_code")) == target_code:
        if current_code != target_code or current_entered_at != _normalized_text(current_entry.get("entered_at")):
            workflow_repo.update_member_current_audience_row(
                member_id,
                audience_code=target_code,
                entered_at=_normalized_text(current_entry.get("entered_at")) or target_entered_at,
            )
            return {"updated": True, "member_id": member_id, "audience_code": target_code, "entered_at": _normalized_text(current_entry.get("entered_at")) or target_entered_at}
        return {"updated": False, "member_id": member_id, "audience_code": target_code, "entered_at": _normalized_text(current_entry.get("entered_at")) or target_entered_at}

    if current_entry:
        workflow_repo.close_current_member_audience_entries(
            member_id,
            exited_at=target_entered_at,
            entry_reason=_normalized_text(resolved.get("entry_reason")),
            source_snapshot_json=dict(resolved.get("source_snapshot_json") or {}),
        )

    workflow_repo.insert_member_audience_entry_row(
        {
            "member_id": member_id,
            "audience_code": target_code,
            "entered_at": target_entered_at,
            "exited_at": "",
            "is_current": True,
            "entry_source": _normalized_text(resolved.get("entry_source")) or "system",
            "entry_reason": _normalized_text(resolved.get("entry_reason")),
            "source_snapshot_json": dict(resolved.get("source_snapshot_json") or {}),
        }
    )
    workflow_repo.update_member_current_audience_row(
        member_id,
        audience_code=target_code,
        entered_at=target_entered_at,
    )
    return {"updated": True, "member_id": member_id, "audience_code": target_code, "entered_at": target_entered_at}


def sync_all_conversion_member_audiences() -> dict[str, Any]:
    scanned_count = 0
    updated_count = 0
    updated_member_ids: list[int] = []
    for member in workflow_repo.list_automation_member_rows():
        scanned_count += 1
        result = sync_conversion_member_audience(member)
        if bool(result.get("updated")):
            updated_count += 1
            updated_member_ids.append(int(result.get("member_id") or 0))
    get_db().commit()
    return {"ok": True, "scanned_count": scanned_count, "updated_count": updated_count, "updated_member_ids": updated_member_ids}


def _node_schedule_anchor_date(*, entered_at: str, send_time: str) -> datetime.date | None:
    entered_dt = _parse_timestamp(entered_at)
    if entered_dt is None:
        return None
    hour, minute = _parse_send_time(send_time)
    scheduled_same_day = entered_dt.replace(hour=hour, minute=minute, second=0, microsecond=0)
    anchor_dt = entered_dt if entered_dt <= scheduled_same_day else entered_dt + timedelta(days=1)
    return anchor_dt.date()


def _node_day_index_matches(*, entered_at: str, send_time: str, scheduled_for: str, expected_day_offset: int) -> bool:
    scheduled_dt = _parse_timestamp(scheduled_for)
    if scheduled_dt is None:
        return False
    anchor_date = _node_schedule_anchor_date(entered_at=entered_at, send_time=send_time)
    if anchor_date is None:
        return False
    day_index = (scheduled_dt.date() - anchor_date).days + 1
    return day_index == int(expected_day_offset)


def _resolve_profile_segment_match(
    *,
    member: dict[str, Any],
    workflow_bundle: dict[str, Any],
) -> dict[str, Any]:
    template_bundle = dict(workflow_bundle.get("profile_segment_template") or {})
    template = dict(template_bundle.get("template") or {})
    questionnaire_id = int(template.get("questionnaire_id") or 0)
    question_id = int(template.get("segmentation_question_id") or 0)
    if questionnaire_id <= 0 or question_id <= 0:
        return {"matched": False, "reason": "profile_segment_template_missing"}
    submission = workflow_repo.get_latest_questionnaire_submission_row(
        questionnaire_id=questionnaire_id,
        external_contact_ids=[_normalized_text(member.get("external_contact_id"))],
        phone=_normalized_text(member.get("phone")),
    )
    if not submission:
        return {"matched": False, "reason": "questionnaire_submission_missing"}
    answers = workflow_repo.list_questionnaire_submission_answer_rows(int(submission["id"]))
    answer = next((item for item in answers if int(item.get("question_id") or 0) == question_id), None)
    if not answer:
        return {"matched": False, "reason": "segmentation_question_answer_missing"}
    selected_option_ids = {
        int(option_id)
        for option_id in _json_list(answer.get("selected_option_ids"))
        if str(option_id).strip()
    }
    if not selected_option_ids:
        return {"matched": False, "reason": "selected_option_ids_empty"}
    matched_categories = [
        {
            "category_key": _normalized_text(category.get("category_key")),
            "category_name": _normalized_text(category.get("category_name")),
        }
        for category in template_bundle.get("categories") or []
        if bool(set(int(option_id) for option_id in (category.get("option_ids") or [])) & selected_option_ids)
    ]
    if len(matched_categories) != 1:
        return {
            "matched": False,
            "reason": "multiple_or_zero_profile_categories",
            "matched_categories": matched_categories,
        }
    category = dict(matched_categories[0])
    return {
        "matched": True,
        "segment_key": _normalized_text(category.get("category_key")),
        "segment_label": _normalized_text(category.get("category_name")),
        "submission_id": int(submission.get("id") or 0),
        "selected_option_ids": sorted(selected_option_ids),
    }


def _resolve_behavior_segment_match(member: dict[str, Any]) -> dict[str, Any]:
    message_count = workflow_repo.count_archived_customer_messages(_normalized_text(member.get("external_contact_id")))
    tier = _behavior_tier_for_count(message_count)
    return {
        "matched": True,
        "segment_key": _normalized_text(tier.get("tier_code")),
        "segment_label": _normalized_text(tier.get("label")),
        "message_count": int(message_count),
    }


def _resolve_workflow_segment_match(
    *,
    workflow_bundle: dict[str, Any],
    member: dict[str, Any],
) -> dict[str, Any]:
    workflow = dict(workflow_bundle.get("workflow") or {})
    segmentation_basis = _normalized_text(workflow.get("segmentation_basis")) or SEGMENTATION_BASIS_NONE
    if segmentation_basis == SEGMENTATION_BASIS_PROFILE:
        return _resolve_profile_segment_match(member=member, workflow_bundle=workflow_bundle)
    if segmentation_basis == SEGMENTATION_BASIS_BEHAVIOR:
        return _resolve_behavior_segment_match(member)
    return {"matched": False, "reason": "segmentation_none"}


def _select_agent_binding(
    *,
    workflow_bundle: dict[str, Any],
    segment_match: dict[str, Any],
) -> dict[str, Any] | None:
    workflow = dict(workflow_bundle.get("workflow") or {})
    generation_mode = _normalized_text(workflow.get("generation_mode"))
    bindings = [dict(item) for item in workflow_bundle.get("agent_bindings") or []]
    if generation_mode == GENERATION_MODE_PERSONALIZED_SINGLE:
        return next(
            (
                item
                for item in bindings
                if _normalized_text(item.get("binding_scope")) == AGENT_BINDING_SCOPE_PERSONALIZED
            ),
            None,
        )
    if not bool(segment_match.get("matched")):
        return None
    segment_key = _normalized_text(segment_match.get("segment_key"))
    binding_scope = (
        AGENT_BINDING_SCOPE_PROFILE_CATEGORY
        if _normalized_text((workflow.get("segmentation_basis"))) == SEGMENTATION_BASIS_PROFILE
        else AGENT_BINDING_SCOPE_BEHAVIOR_TIER
    )
    return next(
        (
            item
            for item in bindings
            if _normalized_text(item.get("binding_scope")) == binding_scope
            and _normalized_text(item.get("segment_key")) == segment_key
        ),
        None,
    )


def _select_manual_layered_content(
    *,
    node: dict[str, Any],
    workflow_bundle: dict[str, Any],
    segment_match: dict[str, Any],
) -> dict[str, Any]:
    del workflow_bundle
    selected_variant = None
    if bool(segment_match.get("matched")):
        selected_variant = next(
            (
                dict(item)
                for item in node.get("content_variants") or []
                if _normalized_text(item.get("segment_key")) == _normalized_text(segment_match.get("segment_key"))
            ),
            None,
        )
    if selected_variant and _normalized_text(selected_variant.get("content_text")):
        return {
            "content_text": _normalized_text(selected_variant.get("content_text")),
            "content_source": "manual_variant",
            "fallback_reason": "",
        }
    fallback_reason = (
        "segment_content_missing"
        if bool(segment_match.get("matched"))
        else (_normalized_text(segment_match.get("reason")) or "segment_not_matched")
    )
    return {
        "content_text": "",
        "content_source": "",
        "fallback_reason": fallback_reason,
    }


def _build_generation_variables(
    *,
    member: dict[str, Any],
    workflow_bundle: dict[str, Any],
    node: dict[str, Any],
    standard_content_text: str,
    segment_match: dict[str, Any],
    behavior_match: dict[str, Any],
) -> dict[str, Any]:
    from ..admin_console.customer_profile_service import get_customer_profile_tags_payload

    latest_submission = workflow_repo.get_latest_any_questionnaire_submission_row(
        external_contact_ids=[_normalized_text(member.get("external_contact_id"))],
        phone=_normalized_text(member.get("phone")),
    )
    questionnaire_answers = []
    if latest_submission:
        for answer in workflow_repo.list_questionnaire_submission_answer_rows(int(latest_submission["id"])):
            questionnaire_answers.append(
                {
                    "question_id": int(answer.get("question_id") or 0),
                    "question_title": _normalized_text(answer.get("question_title_snapshot")),
                    "selected_option_ids": _json_list(answer.get("selected_option_ids")),
                    "selected_option_texts": _json_list(answer.get("selected_option_texts_snapshot")),
                    "text_value": _normalized_text(answer.get("text_value")),
                }
            )
    recent_messages = [
        {
            "role": "客户" if _normalized_text(item.get("sender")) == _normalized_text(member.get("external_contact_id")) else "员工",
            "time": _normalized_text(item.get("send_time")),
            "content": _normalized_text(item.get("content") or item.get("message_text") or item.get("text")),
        }
        for item in get_recent_messages_by_user(_normalized_text(member.get("external_contact_id")), limit=20)
    ] if _normalized_text(member.get("external_contact_id")) else []
    tags_payload = get_customer_profile_tags_payload(external_userid=_normalized_text(member.get("external_contact_id"))) if _normalized_text(member.get("external_contact_id")) else {"tags": []}
    user_tags = [
        _normalized_text(item.get("tag_name")) or _normalized_text(item.get("tag_id"))
        for item in tags_payload.get("tags") or []
        if _normalized_text(item.get("tag_name")) or _normalized_text(item.get("tag_id"))
    ]
    workflow = dict(workflow_bundle.get("workflow") or {})
    return {
        "workflow": {
            "workflow_code": _normalized_text(workflow.get("workflow_code")),
            "workflow_name": _normalized_text(workflow.get("workflow_name")),
            "generation_mode": _normalized_text(workflow.get("generation_mode")),
            "segmentation_basis": _normalized_text(workflow.get("segmentation_basis")),
        },
        "node": {
            "node_code": _normalized_text(node.get("node_code")),
            "node_name": _normalized_text(node.get("node_name")),
            "target_audience_code": _normalized_text(node.get("target_audience_code")),
            "trigger_mode": _node_trigger_mode(node),
            "day_offset": int(node.get("day_offset") or 1),
            "send_time": _normalized_text(node.get("send_time")),
        },
        "member": {
            "member_id": int(member.get("id") or 0),
            "external_contact_id": _normalized_text(member.get("external_contact_id")),
            "phone": _normalized_text(member.get("phone")),
            "owner_staff_id": _normalized_text(member.get("owner_staff_id")),
            "current_pool": _normalized_text(member.get("current_pool")),
            "current_audience_code": _normalized_text(member.get("current_audience_code")),
            "current_audience_entered_at": _normalized_text(member.get("current_audience_entered_at")),
            "activation_status": _normalized_text(member.get("activation_status")),
        },
        "standard_content_text": _normalized_text(standard_content_text),
        "profile_segment": {
            "matched": bool(segment_match.get("matched")),
            "segment_key": _normalized_text(segment_match.get("segment_key")),
            "segment_label": _normalized_text(segment_match.get("segment_label")),
            "reason": _normalized_text(segment_match.get("reason")),
        },
        "behavior_tier": {
            "tier_code": _normalized_text(behavior_match.get("segment_key")),
            "tier_label": _normalized_text(behavior_match.get("segment_label")),
            "message_count": int(behavior_match.get("message_count") or 0),
        },
        "questionnaire": {
            "submission_id": int((latest_submission or {}).get("id") or 0) or None,
            "submitted_at": _normalized_text((latest_submission or {}).get("submitted_at")),
            "answers": questionnaire_answers,
        },
        "recent_messages": recent_messages,
        "user_tags": user_tags,
        "activation_info": {
            "activation_status": _normalized_text(member.get("activation_status")),
            "current_pool": _normalized_text(member.get("current_pool")),
            "current_audience_code": _normalized_text(member.get("current_audience_code")),
            "current_audience_entered_at": _normalized_text(member.get("current_audience_entered_at")),
        },
    }


def _build_agent_generation_request(
    *,
    agent_code: str,
    standard_content_text: str,
    variables_snapshot: dict[str, Any],
) -> tuple[str, str]:
    agent_detail = get_agent_config_detail(agent_code)
    published = dict(agent_detail.get("published") or {})
    role_prompt = _normalized_text(published.get("role_prompt"))
    task_prompt = _normalized_text(published.get("task_prompt"))
    enabled_context_sources = _resolve_effective_enabled_context_sources(
        role_prompt=role_prompt,
        task_prompt=task_prompt,
        enabled_context_sources=published.get("enabled_context_sources"),
        variables=published.get("variables") or [],
    )
    section_texts = _agent_context_source_sections(variables_snapshot, enabled_context_sources)
    role_prompt = _replace_agent_prompt_placeholders(role_prompt, section_texts)
    task_prompt = _replace_agent_prompt_placeholders(task_prompt, section_texts)
    system_prompt = "\n\n".join(
        part
        for part in [
            role_prompt,
            "你只能基于提示词里实际引用到的信息来源生成一条话术，不能臆测缺失事实。",
            "如果某类信息为空，就忽略它，不要报错。",
            "你必须只返回 JSON 对象。",
            'JSON 只允许包含字段：draft_reply。',
        ]
        if _normalized_text(part)
    )
    user_input = json.dumps(
        {
            "task_prompt": task_prompt,
            "standard_content_text": _normalized_text(standard_content_text),
            "enabled_context_sources": enabled_context_sources,
            "context_sections": section_texts,
            "variables": variables_snapshot,
            "required_output_schema": _fixed_agent_output_schema(),
        },
        ensure_ascii=False,
    )
    return system_prompt, user_input


def _generate_content_with_agent(
    *,
    member: dict[str, Any],
    workflow_bundle: dict[str, Any],
    node: dict[str, Any],
    agent_binding: dict[str, Any] | None,
    standard_content_text: str,
    segment_match: dict[str, Any],
    behavior_match: dict[str, Any],
    request_id: str,
    generation_source: str,
) -> dict[str, Any]:
    if not agent_binding:
        return {
            "content_text": _normalized_text(standard_content_text),
            "content_source": "standard_content",
            "fallback_reason": "agent_binding_missing",
            "agent_run_id": "",
            "agent_output_id": "",
            "agent_code": "",
        }
    agent_code = _normalized_text(agent_binding.get("agent_code"))
    if not agent_code:
        return {
            "content_text": _normalized_text(standard_content_text),
            "content_source": "standard_content",
            "fallback_reason": "agent_code_missing",
            "agent_run_id": "",
            "agent_output_id": "",
            "agent_code": "",
        }
    variables_snapshot = _build_generation_variables(
        member=member,
        workflow_bundle=workflow_bundle,
        node=node,
        standard_content_text=standard_content_text,
        segment_match=segment_match,
        behavior_match=behavior_match,
    )
    last_error = ""
    try:
        system_prompt, user_input = _build_agent_generation_request(
            agent_code=agent_code,
            standard_content_text=standard_content_text,
            variables_snapshot=variables_snapshot,
        )
        result = call_deepseek_agent(
            agent_code=agent_code,
            system_prompt=system_prompt,
            user_input=user_input,
            json_output=True,
            request_id=request_id,
            userid=_normalized_text(member.get("owner_staff_id")) or DEFAULT_AUTOMATION_SENDER,
            external_contact_id=_normalized_text(member.get("external_contact_id")),
            input_snapshot={
                "source": generation_source,
                "workflow_code": _normalized_text((workflow_bundle.get("workflow") or {}).get("workflow_code")),
                "node_code": _normalized_text(node.get("node_code")),
                "agent_code": agent_code,
            },
            variables_snapshot=variables_snapshot,
            source=generation_source,
        )
        latest_output = legacy_repo.deserialize_agent_output_row(
            legacy_repo.get_latest_agent_output_row_by_request_id(
                _normalized_text(result.get("request_id") or request_id),
                output_types=["agent_reply_final", "agent_reply_draft", "next_action_suggestion", "error_output"],
            )
            or {}
        )
        parsed_output = dict(result.get("parsed_output") or {})
        generated_text = (
            _normalized_text(parsed_output.get("reply_final"))
            or _normalized_text(parsed_output.get("final_reply"))
            or _normalized_text(parsed_output.get("draft_reply"))
            or _normalized_text(parsed_output.get("reply_draft"))
            or _normalized_text(latest_output.get("rendered_output_text"))
        )
        if generated_text:
            return {
                "content_text": generated_text,
                "content_source": "agent_generated",
                "fallback_reason": "",
                "agent_run_id": _normalized_text(result.get("run_id")) or _normalized_text(latest_output.get("run_id")),
                "agent_output_id": _normalized_text(latest_output.get("output_id")),
                "agent_code": agent_code,
            }
        last_error = "agent_generated_content_empty"
    except (LookupError, ValueError, DeepSeekClientError) as exc:
        last_error = str(exc)
    except Exception as exc:
        last_error = str(exc)
    return {
        "content_text": _normalized_text(standard_content_text),
        "content_source": "standard_content",
        "fallback_reason": last_error or "agent_generation_failed",
        "agent_run_id": "",
        "agent_output_id": "",
        "agent_code": "",
    }


def _send_private_message_to_member(
    *,
    member: dict[str, Any],
    content_text: str,
    operator_id: str,
    filter_snapshot: dict[str, Any],
) -> dict[str, Any]:
    sender_userid = _normalized_text(member.get("owner_staff_id")) or DEFAULT_AUTOMATION_SENDER
    task_payload, content_preview, image_count = user_ops_page_service._build_private_message_payload({"content": _normalized_text(content_text)})
    request_payload = {
        "sender": sender_userid,
        "external_userid": [_normalized_text(member.get("external_contact_id"))],
        **task_payload,
    }
    try:
        result = dispatch_wecom_task("private_message", "create_private_message_task", request_payload)
        task_results = [user_ops_page_service._build_sender_success_result(sender_userid, [{"external_userid": _normalized_text(member.get("external_contact_id")), "owner_display_name": sender_userid}], result)]
        sent_count = 1
        status = "sent"
        error_message = ""
        outbound_task_ids = [int(result["task_id"])]
    except Exception as exc:
        task_results = [user_ops_page_service._build_sender_failure_result(sender_userid, [{"external_userid": _normalized_text(member.get("external_contact_id")), "owner_display_name": sender_userid}], exc)]
        sent_count = 0
        status = "failed"
        error_message = str(exc)
        outbound_task_ids = []
    record_id = user_ops_page_service._insert_send_record(
        outbound_task_ids=outbound_task_ids,
        task_results=task_results,
        selected_count=1,
        eligible_count=1,
        sent_count=sent_count,
        skipped_count=0,
        skipped_reasons={},
        include_do_not_disturb=False,
        content_preview=content_preview,
        image_count=image_count,
        sender_userids=[sender_userid],
        filter_snapshot=filter_snapshot,
        operator=_normalized_text(operator_id) or "automation_conversion_workflow",
        status=status,
    )
    return {
        "ok": status == "sent",
        "status": status,
        "record_id": int(record_id),
        "error_message": error_message,
        "task_results": task_results,
    }


def _render_node_content(
    *,
    member: dict[str, Any],
    workflow_bundle: dict[str, Any],
    node: dict[str, Any],
    execution_request_id: str,
) -> dict[str, Any]:
    workflow = dict(workflow_bundle.get("workflow") or {})
    generation_mode = _normalized_text(workflow.get("generation_mode"))
    segment_match = _resolve_workflow_segment_match(workflow_bundle=workflow_bundle, member=member)
    behavior_match = _resolve_behavior_segment_match(member)
    standard_content_text = _normalized_text(node.get("standard_content_text"))

    if generation_mode == GENERATION_MODE_MANUAL_LAYERED:
        content = _select_manual_layered_content(
            node=node,
            workflow_bundle=workflow_bundle,
            segment_match=segment_match,
        )
        return {
            **content,
            "segment_match": segment_match,
            "behavior_match": behavior_match,
            "agent_run_id": "",
            "agent_output_id": "",
            "agent_code": "",
        }

    binding = _select_agent_binding(workflow_bundle=workflow_bundle, segment_match=segment_match if _normalized_text(workflow.get("segmentation_basis")) != SEGMENTATION_BASIS_BEHAVIOR else behavior_match)
    generated = _generate_content_with_agent(
        member=member,
        workflow_bundle=workflow_bundle,
        node=node,
        agent_binding=binding,
        standard_content_text=standard_content_text,
        segment_match=segment_match,
        behavior_match=behavior_match,
        request_id=execution_request_id,
        generation_source="automation_conversion_workflow_execution",
    )
    return {
        **generated,
        "segment_match": segment_match,
        "behavior_match": behavior_match,
    }


def _process_execution_item(
    *,
    execution: dict[str, Any],
    execution_item: dict[str, Any],
    workflow_bundle: dict[str, Any],
    node: dict[str, Any],
    audience_entry: dict[str, Any],
    operator_id: str,
) -> dict[str, Any]:
    member = workflow_repo.get_automation_member_row(int(execution_item.get("member_id") or 0)) or {}
    if not member:
        return workflow_repo.update_workflow_execution_item_row(
            int(execution_item["id"]),
            {
                **execution_item,
                "status": "skipped",
                "error_message": "automation_member_not_found",
                "content_snapshot_json": {"reason": "automation_member_not_found"},
                "rendered_content_text": "",
                "send_record_id": None,
                "sent_at": "",
            },
        )
    rendered = _render_node_content(
        member=member,
        workflow_bundle=workflow_bundle,
        node=node,
        execution_request_id=f"workflow-node-{int(node['id'])}-item-{int(execution_item['id'])}",
    )
    final_content = _normalized_text(rendered.get("content_text"))
    snapshot = {
        "workflow_code": _normalized_text((workflow_bundle.get("workflow") or {}).get("workflow_code")),
        "node_code": _normalized_text(node.get("node_code")),
        "node_name": _normalized_text(node.get("node_name")),
        "generation_mode": _normalized_text((workflow_bundle.get("workflow") or {}).get("generation_mode")),
        "segmentation_basis": _normalized_text((workflow_bundle.get("workflow") or {}).get("segmentation_basis")),
        "standard_content_text": _normalized_text(node.get("standard_content_text")),
        "rendered_content_text": final_content,
        "content_source": _normalized_text(rendered.get("content_source")),
        "fallback_reason": _normalized_text(rendered.get("fallback_reason")),
        "agent_code": _normalized_text(rendered.get("agent_code")),
        "segment_match": dict(rendered.get("segment_match") or {}),
        "behavior_match": dict(rendered.get("behavior_match") or {}),
    }
    if not _normalized_text(member.get("external_contact_id")):
        return workflow_repo.update_workflow_execution_item_row(
            int(execution_item["id"]),
            {
                **execution_item,
                "status": "skipped",
                "error_message": "missing_external_contact_id",
                "content_snapshot_json": snapshot,
                "rendered_content_text": final_content,
                "agent_code": rendered.get("agent_code"),
                "agent_run_id": rendered.get("agent_run_id"),
                "agent_output_id": rendered.get("agent_output_id"),
                "send_record_id": None,
                "sent_at": "",
            },
        )
    if not final_content:
        return workflow_repo.update_workflow_execution_item_row(
            int(execution_item["id"]),
            {
                **execution_item,
                "status": "failed",
                "error_message": "rendered_content_empty",
                "content_snapshot_json": snapshot,
                "rendered_content_text": "",
                "agent_code": rendered.get("agent_code"),
                "agent_run_id": rendered.get("agent_run_id"),
                "agent_output_id": rendered.get("agent_output_id"),
                "send_record_id": None,
                "sent_at": "",
            },
        )
    send_result = _send_private_message_to_member(
        member=member,
        content_text=final_content,
        operator_id=operator_id,
        filter_snapshot={
            "selection_mode": "automation_conversion_workflow_node",
            "workflow_id": int(execution.get("workflow_id") or 0),
            "node_id": int(execution.get("node_id") or 0),
            "execution_id": _normalized_text(execution.get("execution_id")),
            "audience_entry_id": int(audience_entry.get("id") or 0),
        },
    )
    return workflow_repo.update_workflow_execution_item_row(
        int(execution_item["id"]),
        {
            **execution_item,
            "status": "sent" if bool(send_result.get("ok")) else "failed",
            "error_message": _normalized_text(send_result.get("error_message")),
            "content_snapshot_json": snapshot,
            "rendered_content_text": final_content,
            "agent_code": rendered.get("agent_code"),
            "agent_run_id": rendered.get("agent_run_id"),
            "agent_output_id": rendered.get("agent_output_id"),
            "send_record_id": int(send_result.get("record_id") or 0) or None,
            "sent_at": _iso_now() if bool(send_result.get("ok")) else "",
        },
    )


def _upsert_node_execution_candidates(
    *,
    execution: dict[str, Any],
    node: dict[str, Any],
    workflow_bundle: dict[str, Any],
) -> dict[int, dict[str, Any]]:
    scheduled_for = _normalized_text(execution.get("scheduled_for"))
    audience_rows = workflow_repo.list_current_member_audience_rows(_normalized_text(node.get("target_audience_code")))
    audience_map: dict[int, dict[str, Any]] = {}
    trigger_mode = _node_trigger_mode(node)
    for row in audience_rows:
        entry_id = int(row.get("id") or 0)
        audience_map[entry_id] = dict(row)
        if trigger_mode == NODE_TRIGGER_MODE_SCHEDULED:
            if not _node_day_index_matches(
                entered_at=_normalized_text(row.get("entered_at")),
                send_time=_normalized_text(node.get("send_time")),
                scheduled_for=scheduled_for,
                expected_day_offset=int(node.get("day_offset") or 1),
            ):
                continue
        member = dict(row.get("member") or {})
        if not _member_matches_workflow_recipient_filter(member, workflow_bundle):
            continue
        workflow_repo.insert_workflow_execution_item_row(
            {
                "execution_id": int(execution.get("id") or 0),
                "workflow_id": int(execution.get("workflow_id") or 0),
                "node_id": int(execution.get("node_id") or 0),
                "member_id": int(row.get("member_id") or 0),
                "audience_entry_id": entry_id,
                "external_contact_id": _normalized_text((row.get("member") or {}).get("external_contact_id")),
                "rendered_content_text": "",
                "content_snapshot_json": {},
                "agent_code": "",
                "agent_run_id": "",
                "agent_output_id": "",
                "status": "pending",
                "error_message": "",
                "send_record_id": None,
                "sent_at": "",
            }
        )
    return audience_map


def _execution_summary_from_items(items: list[dict[str, Any]]) -> tuple[str, dict[str, int]]:
    success_count = sum(1 for item in items if _normalized_text(item.get("status")) == "sent")
    skipped_count = sum(1 for item in items if _normalized_text(item.get("status")) == "skipped")
    failed_count = sum(1 for item in items if _normalized_text(item.get("status")) == "failed")
    pending_count = sum(1 for item in items if _normalized_text(item.get("status")) in {"pending", "prepared"})
    if pending_count > 0:
        status = "running"
    elif success_count and (failed_count or skipped_count):
        status = "partial_failed"
    elif failed_count and not success_count and not skipped_count:
        status = "failed"
    else:
        status = "finished"
    return status, {
        "total_count": len(items),
        "success_count": success_count,
        "skipped_count": skipped_count,
        "failed_count": failed_count,
    }


def _run_due_node(
    *,
    workflow_bundle: dict[str, Any],
    node: dict[str, Any],
    operator_id: str,
) -> dict[str, Any]:
    if _node_trigger_mode(node) == NODE_TRIGGER_MODE_AUDIENCE_ENTERED:
        return _run_immediate_node(
            workflow_bundle=workflow_bundle,
            node=node,
            operator_id=operator_id,
        )

    now_dt = datetime.now()
    scheduled_for_dt = now_dt.replace(
        hour=_parse_send_time(node.get("send_time"))[0],
        minute=_parse_send_time(node.get("send_time"))[1],
        second=0,
        microsecond=0,
    )
    if now_dt < scheduled_for_dt:
        return {"ok": True, "status": "not_due_yet", "node_id": int(node.get("id") or 0)}
    scheduled_for = scheduled_for_dt.strftime("%Y-%m-%d %H:%M:%S")
    execution_key = f"acwf-{int((workflow_bundle.get('workflow') or {}).get('id') or 0)}-{int(node.get('id') or 0)}-{scheduled_for_dt.strftime('%Y%m%d%H%M')}"
    execution = workflow_repo.get_workflow_execution_row_by_execution_id(execution_key)
    if not execution:
        execution = workflow_repo.insert_workflow_execution_row(
            {
                "execution_id": execution_key,
                "workflow_id": int((workflow_bundle.get("workflow") or {}).get("id") or 0),
                "node_id": int(node.get("id") or 0),
                "trigger_type": "scheduled_poll",
                "audience_code": _normalized_text(node.get("target_audience_code")),
                "scheduled_for": scheduled_for,
                "status": "pending",
                "total_count": 0,
                "success_count": 0,
                "skipped_count": 0,
                "failed_count": 0,
                "summary_json": {},
                "finished_at": "",
            }
        ) or workflow_repo.get_workflow_execution_row_by_execution_id(execution_key)
    if not execution:
        return {"ok": False, "status": "execution_create_failed", "node_id": int(node.get("id") or 0)}
    if _normalized_text(execution.get("status")) in _FINAL_EXECUTION_STATUSES:
        return {"ok": True, "status": "already_processed", "execution_id": _normalized_text(execution.get("execution_id")), "node_id": int(node.get("id") or 0)}

    workflow_repo.update_workflow_execution_row(
        int(execution["id"]),
        {
            **execution,
            "status": "running",
            "scheduled_for": scheduled_for,
            "finished_at": "",
            "summary_json": dict(execution.get("summary_json") or {}),
        },
    )
    audience_map = _upsert_node_execution_candidates(execution=execution, node=node, workflow_bundle=workflow_bundle)
    execution_items = workflow_repo.list_workflow_execution_item_rows(int(execution["id"]))
    for item in execution_items:
        if _normalized_text(item.get("status")) != "pending":
            continue
        audience_entry = audience_map.get(int(item.get("audience_entry_id") or 0)) or {}
        _process_execution_item(
            execution=execution,
            execution_item=item,
            workflow_bundle=workflow_bundle,
            node=node,
            audience_entry=audience_entry,
            operator_id=operator_id,
        )
    refreshed_items = workflow_repo.list_workflow_execution_item_rows(int(execution["id"]))
    final_status, counters = _execution_summary_from_items(refreshed_items)
    final_execution = workflow_repo.update_workflow_execution_row(
        int(execution["id"]),
        {
            **execution,
            "status": final_status,
            "scheduled_for": scheduled_for,
            "total_count": counters["total_count"],
            "success_count": counters["success_count"],
            "skipped_count": counters["skipped_count"],
            "failed_count": counters["failed_count"],
            "summary_json": {"node_name": _normalized_text(node.get("node_name"))},
            "finished_at": _iso_now() if final_status in _FINAL_EXECUTION_STATUSES else "",
        },
    )
    return {
        "ok": True,
        "status": final_status,
        "execution": final_execution,
        "items": workflow_repo.list_workflow_execution_item_rows(int(final_execution["id"])),
    }


def _run_immediate_node(
    *,
    workflow_bundle: dict[str, Any],
    node: dict[str, Any],
    operator_id: str,
) -> dict[str, Any]:
    audience_rows = workflow_repo.list_current_member_audience_rows(_normalized_text(node.get("target_audience_code")))
    processed_executions: list[dict[str, Any]] = []
    for audience_entry in audience_rows:
        audience_entry_id = int(audience_entry.get("id") or 0)
        if audience_entry_id <= 0:
            continue
        if not _member_matches_workflow_recipient_filter(dict(audience_entry.get("member") or {}), workflow_bundle):
            continue
        execution_key = (
            f"acwf-immediate-"
            f"{int((workflow_bundle.get('workflow') or {}).get('id') or 0)}-"
            f"{int(node.get('id') or 0)}-"
            f"{audience_entry_id}"
        )
        execution = workflow_repo.get_workflow_execution_row_by_execution_id(execution_key)
        if not execution:
            execution = workflow_repo.insert_workflow_execution_row(
                {
                    "execution_id": execution_key,
                    "workflow_id": int((workflow_bundle.get("workflow") or {}).get("id") or 0),
                    "node_id": int(node.get("id") or 0),
                    "trigger_type": "scheduled_poll",
                    "audience_code": _normalized_text(node.get("target_audience_code")),
                    "scheduled_for": _normalized_text(audience_entry.get("entered_at")) or _iso_now(),
                    "status": "pending",
                    "total_count": 0,
                    "success_count": 0,
                    "skipped_count": 0,
                    "failed_count": 0,
                    "summary_json": {"audience_entry_id": audience_entry_id},
                    "finished_at": "",
                }
            ) or workflow_repo.get_workflow_execution_row_by_execution_id(execution_key)
        if not execution:
            continue
        if _normalized_text(execution.get("status")) in _FINAL_EXECUTION_STATUSES:
            processed_executions.append(execution)
            continue

        workflow_repo.update_workflow_execution_row(
            int(execution["id"]),
            {
                **execution,
                "status": "running",
                "scheduled_for": _normalized_text(audience_entry.get("entered_at")) or _iso_now(),
                "finished_at": "",
                "summary_json": {
                    **dict(execution.get("summary_json") or {}),
                    "audience_entry_id": audience_entry_id,
                },
            },
        )
        workflow_repo.insert_workflow_execution_item_row(
            {
                "execution_id": int(execution.get("id") or 0),
                "workflow_id": int(execution.get("workflow_id") or 0),
                "node_id": int(execution.get("node_id") or 0),
                "member_id": int(audience_entry.get("member_id") or 0),
                "audience_entry_id": audience_entry_id,
                "external_contact_id": _normalized_text((audience_entry.get("member") or {}).get("external_contact_id")),
                "rendered_content_text": "",
                "content_snapshot_json": {},
                "agent_pool_id": None,
                "agent_run_id": "",
                "agent_output_id": "",
                "status": "pending",
                "error_message": "",
                "send_record_id": None,
                "sent_at": "",
            }
        )
        execution_items = workflow_repo.list_workflow_execution_item_rows(int(execution["id"]))
        for item in execution_items:
            if _normalized_text(item.get("status")) != "pending":
                continue
            _process_execution_item(
                execution=execution,
                execution_item=item,
                workflow_bundle=workflow_bundle,
                node=node,
                audience_entry=audience_entry,
                operator_id=operator_id,
            )
        refreshed_items = workflow_repo.list_workflow_execution_item_rows(int(execution["id"]))
        final_status, counters = _execution_summary_from_items(refreshed_items)
        final_execution = workflow_repo.update_workflow_execution_row(
            int(execution["id"]),
            {
                **execution,
                "status": final_status,
                "scheduled_for": _normalized_text(audience_entry.get("entered_at")) or _iso_now(),
                "total_count": counters["total_count"],
                "success_count": counters["success_count"],
                "skipped_count": counters["skipped_count"],
                "failed_count": counters["failed_count"],
                "summary_json": {
                    "node_name": _normalized_text(node.get("node_name")),
                    "audience_entry_id": audience_entry_id,
                },
                "finished_at": _iso_now() if final_status in _FINAL_EXECUTION_STATUSES else "",
            },
        )
        processed_executions.append(final_execution)
    return {
        "ok": True,
        "status": "finished" if processed_executions else "no_candidates",
        "node_id": int(node.get("id") or 0),
        "executions": processed_executions,
    }


def run_due_conversion_workflows(*, operator_id: str = "", operator_type: str = "system") -> dict[str, Any]:
    sync_summary = sync_all_conversion_member_audiences()
    scanned_workflow_count = 0
    processed_node_count = 0
    execution_items: list[dict[str, Any]] = []
    for workflow_row in workflow_repo.list_workflow_rows(include_archived=False, status=WORKFLOW_STATUS_ACTIVE):
        scanned_workflow_count += 1
        workflow_bundle = get_conversion_workflow_model_bundle(int(workflow_row["id"]))
        for node in workflow_bundle.get("nodes") or []:
            if not bool(node.get("enabled")):
                continue
            processed_node_count += 1
            execution_items.append(
                _run_due_node(
                    workflow_bundle=workflow_bundle,
                    node=dict(node),
                    operator_id=_normalized_text(operator_id) or "automation_conversion_workflow_runner",
                )
            )
    get_db().commit()
    return {
        "ok": True,
        "operator_type": _normalized_text(operator_type) or "system",
        "operator_id": _normalized_text(operator_id) or "automation_conversion_workflow_runner",
        "sync_summary": sync_summary,
        "scanned_workflow_count": scanned_workflow_count,
        "processed_node_count": processed_node_count,
        "executions": execution_items,
    }
