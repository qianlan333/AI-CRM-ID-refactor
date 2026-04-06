from __future__ import annotations

from typing import Any


def _text(value: Any) -> str:
    return str(value or "").strip()


def marketing_stage_key(*, main_stage: Any = "", sub_stage: Any = "", stage_key: Any = "") -> str:
    normalized_stage_key = _text(stage_key)
    if normalized_stage_key:
        return normalized_stage_key
    normalized_main_stage = _text(main_stage)
    normalized_sub_stage = _text(sub_stage)
    if normalized_main_stage and normalized_sub_stage:
        return f"{normalized_main_stage}/{normalized_sub_stage}"
    return normalized_main_stage or normalized_sub_stage


def business_stage_label(*, main_stage: Any = "", sub_stage: Any = "", stage_key: Any = "") -> str:
    normalized_stage_key = marketing_stage_key(main_stage=main_stage, sub_stage=sub_stage, stage_key=stage_key)
    return {
        "pool/new_user": "新用户池",
        "pool/inactive_normal": "未激活普通池",
        "pool/inactive_focus": "未激活重点跟进池",
        "pool/active_normal": "激活普通池",
        "pool/active_focus": "激活重点跟进池",
        "pool/silent": "沉默池",
        "converted/enrolled": "已确认成交",
    }.get(normalized_stage_key, "暂无阶段")


def business_segment_label(segment: Any) -> str:
    normalized_segment = _text(segment).lower()
    return {
        "unknown": "未完成初判",
        "normal": "普通跟进",
        "core": "重点跟进",
        "top": "重点跟进",
        "focus": "重点跟进",
    }.get(normalized_segment, "未完成初判")


def business_eligibility_label(eligible_for_conversion: Any) -> str:
    return "会" if bool(eligible_for_conversion) else "不会"


def business_ineligible_reason(
    *,
    reason: Any = "",
    main_stage: Any = "",
    sub_stage: Any = "",
    eligible_for_conversion: Any = False,
) -> str:
    if bool(eligible_for_conversion):
        return ""
    normalized_reason = _text(reason)
    stage = marketing_stage_key(main_stage=main_stage, sub_stage=sub_stage)
    mapping = {
        "enrolled": "客户已确认成交，已退出全部营销。",
        "signup_success": "客户已确认成交，已退出全部营销。",
        "awaiting_questionnaire": "客户还在新用户池，等待提交问卷后再首次分流。",
        "trial_not_opened": "问卷已提交，等待开通试用后再进入对应池子。",
        "pool_not_openclaw_target": "客户当前池子不需要交给 OpenClaw。",
        "pool_not_focus_followup": "客户当前属于普通跟进池，暂不交给 OpenClaw。",
        "silent_pool": "客户已进入沉默池，当前只做留存记录。",
        "silent_timeout": "客户停留超时后已进入沉默池。",
        "not_eligible": "客户当前暂不参与自动化转化。",
    }
    if normalized_reason in mapping:
        return mapping[normalized_reason]
    if stage == "converted/enrolled":
        return mapping["enrolled"]
    if stage == "pool/silent":
        return mapping["silent_pool"]
    return normalized_reason or mapping["not_eligible"]


def business_marketing_display(
    *,
    main_stage: Any = "",
    sub_stage: Any = "",
    segment: Any = "",
    eligible_for_conversion: Any = False,
    ineligible_reason: Any = "",
) -> dict[str, str]:
    return {
        "stage_label": business_stage_label(main_stage=main_stage, sub_stage=sub_stage),
        "segment_label": business_segment_label(segment),
        "eligibility_label": business_eligibility_label(eligible_for_conversion),
        "ineligible_reason_label": business_ineligible_reason(
            reason=ineligible_reason,
            main_stage=main_stage,
            sub_stage=sub_stage,
            eligible_for_conversion=eligible_for_conversion,
        ),
    }


def marketing_state_change_summary(*, previous_stage: Any = "", current_stage: Any = "") -> str:
    previous_label = business_stage_label(stage_key=previous_stage)
    current_label = business_stage_label(stage_key=current_stage)
    if previous_stage and previous_stage != current_stage:
        return f"客户池子从{previous_label}变为{current_label}"
    if current_stage:
        return f"客户池子更新为{current_label}"
    return "客户池子已更新"


def value_segment_change_summary(*, previous_segment: Any = "", current_segment: Any = "") -> str:
    previous_label = business_segment_label(previous_segment)
    current_label = business_segment_label(current_segment)
    if previous_segment and previous_segment != current_segment:
        return f"客户初判从{previous_label}变为{current_label}"
    if current_segment:
        return f"客户初判更新为{current_label}"
    return "客户初判已更新"


def conversion_marked_summary(action: Any, source: Any) -> str:
    normalized_action = _text(action)
    normalized_source = _text(source)
    source_prefix = "人工" if normalized_source.startswith("sidebar") or normalized_source == "manual" or not normalized_source else "系统"
    if normalized_action == "mark_enrolled":
        return f"{source_prefix}确认客户已成交，系统已退出全部营销。"
    if normalized_action == "unmark_enrolled":
        return f"{source_prefix}撤销成交标记，系统已重新判断当前池子。"
    return "成交状态已更新。"
